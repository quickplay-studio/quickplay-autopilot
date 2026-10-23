"""Quickplay Clips (@QuickplayClips-x9b): clips from campaign-permitted footage, made and uploaded by GitHub (clips.yml).

  python pipeline/clips.py run            every active campaign in clips/campaigns.json: source, plan, make, upload
  python pipeline/clips.py source <id>    the campaign's footage segment -> release asset clips-src/<id>.mp4 (once)
  python pipeline/clips.py plan <id>      transcript (faster-whisper) + the moments worth a clip (Gemini) -> clips/plans/<id>.json
  python pipeline/clips.py make <id>      the next clips (9:16, captions, hook, credit) -> clips/out/<clip>.mp4
  python pipeline/clips.py upload <id>    upload to Quickplay Clips, public together at batch_time; rows in clips/submit.csv
  python pipeline/clips.py stats          views, likes and comments per clip -> clips/stats.csv

Permission first: a campaign is used only while clips/campaigns.json says active and carries its rules; nothing else is
ever fetched. CLIPS_COUNT limits a run, CLIPS_MODE=private uploads without a publish time (a test Charlie can watch in
YouTube Studio). The footage segment is cut once and kept as a release asset, so a run never downloads the whole VOD
twice. Submission to the campaign stays Charlie's: clips/submit.csv lists each public clip's link and campaign.
"""
import csv, datetime as dt, json, os, pathlib, re, shutil, subprocess, sys, time
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
CFG = json.loads((ROOT / "clips" / "campaigns.json").read_text())
# A new channel's IG_<CHANNEL>_* and FB_<CHANNEL>_* secrets are named one by one in clips.yml (GitHub holds a workflow that
# passes every secret at once as "possibly malicious", 22 October), so adding a channel means adding its four lines there.
PLANS, OUT, STATE = ROOT / "clips" / "plans", ROOT / "clips" / "out", ROOT / "clips" / "state"
WORK = pathlib.Path(os.environ.get("CLIPS_WORK") or ("/mnt/clips" if os.access("/mnt", os.W_OK) else "/tmp/clips"))
RELEASE = "clips-src"
FONT = next((p for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
                         "/System/Library/Fonts/Supplemental/Arial Bold.ttf") if pathlib.Path(p).exists()), "")
CHANNEL = "https://www.youtube.com/@QuickplayClips-x9b"

PLAN_PROMPT = """You pick moments for short vertical clips (YouTube Shorts) from a transcript of {label}. The clips go on a
clipping channel under a campaign with these rules, which every clip must keep:
- {focus}
- {on_screen}
- Avoid: {avoid}
- Each clip runs {min_s} to {max_s} seconds (longer is better when the moment holds: a whole mini story keeps people
  watching), starts at a natural moment and ends on the payoff (the reaction, the punchline, the reveal), never
  mid-sentence.
Pick up to {n} moments that would go viral on their own, best first. A viral clip: the first 2 seconds already grab
(something surprising said or happening, mid-action, never a greeting or set-up); it makes sense to someone who never
saw the stream; it builds to one big payoff (a shock, a huge win or fail, a hilarious reaction, a line people will quote
or argue about in the comments); and it ends right after the payoff. Skip quiet talk, explanations and anything that
needs context. Score each 1 to 10 for how likely it is to go viral, honestly: most moments are 5 or below.
Spread them across the segment; no two may overlap. Lines marked (already clipped) are taken: never pick them.
{searches}The transcript is a list of lines with their start and end seconds:
{lines}
Hooks and titles stay family friendly and brand safe: fun, drama, chaos and wins are fine; never trauma, abuse, mental
illness, self-harm, cruelty, slurs or threats, even as a joke, and never a word the campaign's brand would not want.
Return {{"moments": [{{"start": seconds, "end": seconds, "hook": "on-screen line, 8 words or fewer, in capitals OK, what
makes someone stop (no spoilers of the payoff)", "label": "1 to 4 words to show on screen only when the rules above ask for a name (a destination, a person); otherwise empty", "title": "YouTube title under 60 characters, starts with {subject}, plain and searchable, no clickbait",
"peak": seconds of the single biggest reaction or punchline inside the moment, "question": "a short question for the
comments that viewers can answer, under 90 characters, UK English spelling (favourite, colour)", "score": 1 to 10,
"intro": "our own spoken set-up for the first seconds, 6 to 12 words, opinion and framing only, no spoiler",
"outro": "our own reaction after the payoff, 6 to 14 words, ending with a question for the comments",
"why": "one line: the grab, the payoff"}}]}}"""


def log(*a): print(*a, flush=True)


UNSAFE = re.compile(r"\b(trauma\w*|abus\w+|psycholog\w+ (destruction|damage|torture|warfare)|self[ -]harm|suicid\w*|overdos\w*|tortur\w+|"
                    r"mental(ly)? (ill\w*|breakdown)|rap(e|ed|ist)|molest\w*|nazi\w*|terror\w*)\b", re.I)      # not for a hook or title, even as a joke
PROFANE = re.compile(r"\b(f+u+c+k+\w*|f\*+\w*|s+h+i+t+\w*|s\*+t\w*|b+i+t+c+h+\w*|a+s+s+h+o+l+e+\w*|d+i+c+k+s?|p+u+s+s+y|wtf|stfu|"
                     r"n+i+g+g+\w*|r+e+t+a+r+d+\w*|w+h+o+r+e+\w*|s+l+u+t+\w*|c+u+n+t+\w*|f+a+g+\w*)\b", re.I)


def profane(words, a, b):
    """The strong words heard between a and b (the channel is family-friendly and every campaign wants brand-safe)."""
    return PROFANE.findall(" ".join(w["w"] for w in words if a <= w["s"] <= b))


def num(x):
    """A number of seconds from a model's field: 83, "83", "1:23"; None when it is nothing of the kind."""
    try: return secs(x) if ":" in str(x) else float(x)
    except (TypeError, ValueError): return None


def secs(t):
    p = [float(x) for x in str(t).split(":")]
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))


def duration(path):
    """Seconds of media in a file (ffprobe), 0 when unreadable."""
    try:
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                    capture_output=True, text=True).stdout.strip() or 0)
    except ValueError: return 0.0


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode: raise RuntimeError(f"{cmd[0]} failed: {(r.stderr or r.stdout)[-800:]}")
    return r.stdout


def campaigns(ids=()):
    cs = {k: v for k, v in CFG["campaigns"].items() if v.get("active") and v.get("source") and v.get("rules")}
    if ids: cs = {k: v for k, v in cs.items() if k in ids}
    return cs


# ----- footage -------------------------------------------------------------------------------------------------------
def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode: raise RuntimeError(f"gh {' '.join(args[:3])}: {r.stderr.strip()[:300]}")
    return r


def asset_sizes():
    """{asset name: bytes} of the clips-src release (empty when it does not exist yet)."""
    r = gh("release", "view", RELEASE, "--json", "assets", "-q", "[.assets[] | {name, size}]", check=False)
    try: return {a["name"]: int(a.get("size") or 0) for a in json.loads(r.stdout or "[]")}
    except (ValueError, TypeError): return {}


def source(cid):
    """The campaign's footage segment as a release asset (made once): the source file is downloaded to the work disk,
    the segment between start and end is cut and shrunk to 720p, and the whole download is deleted."""
    c, name = campaigns([cid])[cid], f"{cid}.mp4"
    if asset_sizes().get(name, 0) > 1_000_000 and not os.environ.get("CLIPS_REDO"): return name       # a tiny asset is a failed cut: made again
    s = c["source"]; WORK.mkdir(parents=True, exist_ok=True)
    raw = WORK / f"{cid}.raw"
    if s.get("multi"):
        seg = episodes_source(cid, c, s)
        if gh("release", "view", RELEASE, check=False).returncode:
            gh("release", "create", RELEASE, "--title", "Clips source segments", "--notes", "Campaign footage segments the clips line cuts from (permitted footage only).", "--prerelease")
        gh("release", "upload", RELEASE, str(seg), "--clobber")
        log(f"{cid}: {len(json.loads((PLANS / f'{cid}.json').read_text()).get('episodes') or [])} episodes joined and saved as release asset {name} ({seg.stat().st_size / 1e6:.0f} MB)")
        return name
    if s["kind"] == "gdrive":
        import gdown
        log(f"{cid}: downloading the source file from Google Drive")
        got = gdown.download(id=s["id"], output=str(raw), quiet=True, resume=True, retries=3)
        if not got or not raw.exists() or raw.stat().st_size < 1e6: raise RuntimeError(f"{cid}: the Drive download failed or is empty")
    elif s["kind"] == "url":
        run(["curl", "-sSL", "--retry", "3", "-o", str(raw), s["url"]])
    elif s["kind"] == "frameio":
        log(f"{cid}: downloading from Frame.io")
        frameio_download(s["url"], raw)
    elif s["kind"] == "release":        # footage Charlie attached to a release of this repo
        gh("release", "download", s["tag"], "-p", s["file"], "-O", str(raw), "--clobber")
    else: raise RuntimeError(f"{cid}: unknown source kind {s['kind']}")
    seg = WORK / name
    total = duration(raw)
    start, end = secs(s["start"]) if s.get("start") else 0.0, secs(s["end"]) if s.get("end") else total
    if start >= total - 5:          # the file is already the segment (the timestamps were for the whole stream)
        log(f"{cid}: the source runs {total / 60:.0f} minutes, so it is the segment itself; keeping all of it")
        start, end = 0.0, total
    log(f"{cid}: cutting {start:.0f}s to {end:.0f}s of {total:.0f}s ({raw.stat().st_size / 1e9:.1f} GB source)")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.2f}", "-to", f"{min(end, total):.2f}", "-i", str(raw),
           "-vf", "scale=-2:720", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(seg)]
    run(cmd); raw.unlink(missing_ok=True)
    if duration(seg) < 10: raise RuntimeError(f"{cid}: the cut segment is empty ({duration(seg):.0f} s)")
    if gh("release", "view", RELEASE, check=False).returncode:
        gh("release", "create", RELEASE, "--title", "Clips source segments", "--notes", "Campaign footage segments the clips line cuts from (permitted footage only).", "--prerelease")
    gh("release", "upload", RELEASE, str(seg), "--clobber")
    log(f"{cid}: segment saved as release asset {name} ({seg.stat().st_size / 1e6:.0f} MB)")
    return name


def frameio_download(url, out, shot=None):
    """Downloads the file behind a Frame.io share link with a headless browser (the share must allow downloads, which
    the campaigns' do): opens the page, presses Download (then Original or the largest option if a menu opens) and
    saves the file. Falls back to the first mp4 the page streams. `shot`: where to save a screenshot of the page."""
    from playwright.sync_api import sync_playwright
    out = pathlib.Path(out); media = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 900},
                                  user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36")
        page = ctx.new_page()
        page.on("response", lambda r: media.append(r.url) if re.search(r"\.(mp4|m3u8)(\?|$)", r.url) or "video" in (r.headers.get("content-type") or "") else None)
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(8000)
        names = [(b.get_attribute("aria-label") or b.inner_text() or "").strip()[:40] for b in page.locator("button").all()[:60]]
        log("  buttons:", [n for n in names if n])
        if shot: page.screenshot(path=str(shot), full_page=False)
        got = None
        for pattern in ("download", "télécharger"):
            btn = page.get_by_role("button", name=re.compile(pattern, re.I))
            if btn.count() == 0: btn = page.locator(f"[aria-label*='{pattern}' i], [data-testid*='{pattern}' i]")
            if btn.count() == 0: continue
            try:
                with page.expect_download(timeout=45000) as dl:
                    btn.first.click()
                    page.wait_for_timeout(1500)
                    for _ in range(3):          # the dialog: "Download in Browser", then a quality if it asks (Original first)
                        clicked = False
                        for opt in ("Download in Browser", "Original", "1080", "720", "Download"):
                            for role in ("button", "menuitem", "radio", "option"):
                                item = page.get_by_role(role, name=re.compile(opt, re.I))
                                if item.count() and item.first.is_visible():
                                    item.first.click(); clicked = True; break
                            if clicked: break
                        page.wait_for_timeout(1500)
                        if not clicked: break
                got = dl.value
            except Exception as e:
                log(f"  download button ({pattern}): {type(e).__name__}: {str(e)[:120]}")
                if shot: page.screenshot(path=str(shot).replace(".png", "_after.png"))
            if got: break
        if got:
            got.save_as(str(out)); log(f"  downloaded {got.suggested_filename} ({out.stat().st_size / 1e6:.0f} MB)")
        browser.close()
    if not got:
        best = sorted((u for u in media if ".mp4" in u), key=lambda u: -max([int(x) for x in re.findall(r"h264_(\d+)", u)] or [0]))
        mp4 = next((u for u in best if max([int(x) for x in re.findall(r"h264_(\d+)", u)] or [0]) >= 720), None)
        log("  media seen:", [u[:100] for u in media[:6]])
        if not mp4: raise RuntimeError("Frame.io: the download dialog did not start a download and no 720p+ mp4 was streamed")
        import requests
        with requests.get(mp4, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(1 << 20): f.write(chunk)
    return out


def frameio_assets(url):
    """The asset view links inside a Frame.io share: one (the link itself) for a single file, else every file the
    folder lists, in the page's order."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(); page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(url, wait_until="domcontentloaded", timeout=120000); page.wait_for_timeout(6000)
        final = page.url
        links = []
        for a in page.locator("a[href*='/view/']").all():
            h = a.get_attribute("href") or ""
            if h.startswith("/"): h = "https://next.frame.io" + h
            if h and h not in links: links.append(h.split("?")[0])
        browser.close()
    if "/view/" in final and not links: return [final]
    return links or [final]


def episodes_source(cid, c, s):
    """A folder of episodes (source "multi": true): each file downloaded, shrunk to 720p and joined in order into one
    segment; the episode boundaries go into the plan file so the parts planner keeps every episode whole."""
    import zipfile
    files = []
    raw = WORK / f"{cid}.raw"
    if s["kind"] == "frameio":
        frameio_download(s["url"], raw)                    # a folder's Download button gives a zip of every file
        if zipfile.is_zipfile(raw):
            folder = WORK / f"{cid}-files"; folder.mkdir(exist_ok=True)
            with zipfile.ZipFile(raw) as z:
                for info in z.infolist():
                    if info.filename.lower().endswith((".mp4", ".mov", ".m4v", ".mkv")) and not info.filename.startswith("__MACOSX"):
                        z.extract(info, folder); files.append(folder / info.filename)
            raw.unlink(missing_ok=True)
        else: files = [raw]
    else: files = [raw]
    natural = lambda p: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", p.name)]
    files.sort(key=natural)
    log(f"{cid}: {len(files)} files in the folder: " + ", ".join(f.name[:40] for f in files[:8]))
    parts, bounds, t = [], [], 0.0
    for n, src in enumerate(files, 1):
        small = WORK / f"{cid}-{n}.mp4"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf", "scale=-2:720", "-r", "30", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(small)])
        d = duration(small)
        if d < 5: log(f"{cid}: file {n} is empty, skipped"); continue
        bounds.append({"n": len(bounds) + 1, "start": round(t, 2), "end": round(t + d, 2), "file": src.name}); t += d; parts.append(small)
    if not parts: raise RuntimeError(f"{cid}: no usable files in the folder")
    lst = WORK / f"{cid}.txt"; lst.write_text("".join(f"file '{p}'\n" for p in parts))
    seg = WORK / f"{cid}.mp4"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(seg)])
    PLANS.mkdir(parents=True, exist_ok=True)
    pp = PLANS / f"{cid}.json"
    plan_ = json.loads(pp.read_text()) if pp.exists() else {"moments": []}
    plan_["episodes"] = bounds; pp.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    return seg


def segment(cid):
    """The segment file on the work disk (downloaded from the release when missing)."""
    p = WORK / f"{cid}.mp4"
    if not p.exists() or p.stat().st_size < 1_000_000:
        WORK.mkdir(parents=True, exist_ok=True)
        gh("release", "download", RELEASE, "-p", f"{cid}.mp4", "-D", str(WORK), "--clobber")
    if duration(p) < 10: raise RuntimeError(f"{cid}: the segment asset is empty; delete it from the clips-src release and run again")
    return p


# ----- transcript and moments ------------------------------------------------------------------------------------------
def transcribe(cid):
    """Word-timed transcript of the segment (faster-whisper on the CPU), kept in clips/plans/<id>.words.json."""
    p = PLANS / f"{cid}.words.json"
    if p.exists(): return json.loads(p.read_text())
    from faster_whisper import WhisperModel
    seg = segment(cid)
    wav = WORK / f"{cid}.wav"
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(seg), "-ac", "1", "-ar", "16000", str(wav)])
    model = WhisperModel(os.environ.get("WHISPER_MODEL", "small"), device="cpu", compute_type="int8")
    import wave
    import numpy as np
    with wave.open(str(wav), "rb") as f:            # the samples go in as an array, so no PyAV version can get in the way
        audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    out = []
    segs, _ = model.transcribe(audio, word_timestamps=True, language="en", vad_filter=True)
    for s in segs:
        for w in s.words or []:
            out.append({"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)})
    PLANS.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(out))
    log(f"{cid}: {len(out)} words transcribed")
    return out


def searches(subject, n=8):
    """What people type into YouTube search about the subject (Google's suggestions for GB and US, free, no key): the
    planner aligns hooks and titles with it, and the scout reads it as demand."""
    import requests
    out = []
    for gl in ("GB", "US"):
        try:
            r = requests.get("https://suggestqueries.google.com/complete/search", timeout=10,
                             params={"client": "firefox", "ds": "yt", "hl": "en", "gl": gl, "q": subject})
            out += [x for x in r.json()[1] if isinstance(x, str)]
        except Exception: pass
    return list(dict.fromkeys(out))[:n]


def lines_of(words, every=6.0):
    """The transcript as lines of about `every` seconds for the planner."""
    lines, cur, t0 = [], [], None
    for w in words:
        if t0 is None: t0 = w["s"]
        cur.append(w["w"])
        if w["e"] - t0 >= every or w["w"].endswith((".", "?", "!")) and w["e"] - t0 >= 2.5:
            lines.append(f"[{t0:.0f}-{w['e']:.0f}] " + " ".join(cur)); cur, t0 = [], None
    if cur: lines.append(f"[{t0:.0f}-{words[-1]['e']:.0f}] " + " ".join(cur))
    return lines


MIN_S, MAX_S = 25, 75        # clip length unless a campaign's rules say otherwise (Charlie, 23 October: longer clips)
MIN_SCORE = 6                # the planner's own virality score (1 to 10): below this a moment isn't worth a clip


def min_score():
    """The planner's virality score a moment needs: learned from real views (clips/insights.json min_score) once 20 or more
    scored clips have views, else MIN_SCORE."""
    try: got = json.loads((ROOT / "clips" / "insights.json").read_text()).get("min_score")
    except Exception: got = None
    return int(got) if isinstance(got, (int, float)) else MIN_SCORE


def marked(lines, done):
    """Transcript lines inside a moment already clipped are marked, so the planner stops offering them again (the 23
    October runs lost 8 of 8 picks to overlaps)."""
    out = []
    for ln in lines:
        m = re.match(r"\[(\d+)-(\d+)\]", ln)
        if m and any(int(m.group(1)) < y and int(m.group(2)) > x for x, y in done): ln += " (already clipped)"
        out.append(ln)
    return out


def plan(cid, n=8):
    """The moments worth a clip, from the transcript, checked against the rules' lengths; appended to clips/plans/<id>.json."""
    import factpack
    c = campaigns([cid])[cid]; r = c["rules"]
    words = transcribe(cid)
    if not words: raise RuntimeError(f"{cid}: no speech found in the segment")
    p = PLANS / f"{cid}.json"
    plan_ = json.loads(p.read_text()) if p.exists() else {"moments": []}
    done = [(m["start"], m["end"]) for m in plan_["moments"]]
    terms = searches(c["subject"])
    prompt = PLAN_PROMPT.format(label=c["source"].get("label", cid), focus=r["focus"], on_screen=r["on_screen"],
                                searches=(f"What people type into YouTube search about {c['subject']} right now: {'; '.join(terms)}. Prefer the "
                                          "moments those searches would want, and use their words in a hook or title when they fit.\n") if terms else "",
                                avoid="; ".join(r.get("avoid") or []), min_s=r.get("min_s", MIN_S), max_s=r.get("max_s", MAX_S), n=n,
                                subject=c["subject"], lines="\n".join(marked(lines_of(words), done)))
    ans, model = factpack.gemini(prompt, None, timeout=150, temperature=0.4, writing=True, lite=True)    # the best free models, never Claude
    total = words[-1]["e"]
    added, why = 0, {"bad time": 0, "length": 0, "overlap": 0, "no hook": 0, "low score": 0}
    if isinstance(ans, list): ans = next((x for x in ans if isinstance(x, dict) and x.get("moments")), {"moments": [x for x in ans if isinstance(x, dict) and "start" in x]})
    raw = (ans.get("moments") if isinstance(ans, dict) else None) or []
    if not raw: log(f"{cid}: the model gave no moments: {json.dumps(ans)[:300]}")
    raw = sorted((m for m in raw if isinstance(m, dict)), key=lambda m: -(num(m.get("score")) or 0))     # the likeliest hits first
    for m in raw:
        try:
            a, b = (secs(m["start"]) if ":" in str(m["start"]) else float(m["start"])), (secs(m["end"]) if ":" in str(m["end"]) else float(m["end"]))
        except (KeyError, TypeError, ValueError): why["bad time"] += 1; continue
        a, b = max(0.0, a - 0.3), min(total, b + 0.4)      # a breath before, the reaction after
        if b - a > r.get("max_s", MAX_S) + 1: b = a + r.get("max_s", MAX_S)      # a long pick is cut to the limit, the payoff is usually early
        if not r.get("min_s", MIN_S) <= b - a: why["length"] += 1; continue
        if num(m.get("score")) is not None and num(m.get("score")) < min_score(): why["low score"] += 1; continue
        if any(a < y and b > x for x, y in done): why["overlap"] += 1; continue
        hook = re.sub(r"[–—]", "-", str(m.get("hook") or "")).strip()[:60]
        if not hook: why["no hook"] += 1; continue
        if profane(words, a, b) or PROFANE.search(hook): why["profanity"] = why.get("profanity", 0) + 1; continue
        if UNSAFE.search(hook) or UNSAFE.search(str(m.get("title") or "")): why["not brand safe"] = why.get("not brand safe", 0) + 1; continue
        plan_["moments"].append({"id": f"{cid}-{len(plan_['moments']) + 1:02d}", "start": round(a, 2), "end": round(b, 2),
                                 "hook": hook, "label": str(m.get("label") or "").strip()[:40],
                                 "title": re.sub(r"[–—]", "-", str(m.get("title") or f"{c['subject']}: {hook}")).strip()[:70],
                                 "why": str(m.get("why") or "")[:200], "planned": NOW.isoformat(timespec="minutes"), "model": model,
                                 "peak": num(m.get("peak")), "score": num(m.get("score")),
                                 **{f"take_{k}": re.sub("[\u2013\u2014]", ",", str(m.get(k) or "")).strip()[:120] for k in ("intro", "outro")
                                    if m.get(k) and not PROFANE.search(str(m.get(k))) and not UNSAFE.search(str(m.get(k)))},
                                 "question": re.sub(r"[–—]", "-", str(m.get("question") or "")).strip()[:90]})
        done.append((a, b)); added += 1
    PLANS.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    log(f"{cid}: {added} of {len(raw)} moments planned ({model}), {len(plan_['moments'])} in all" + (f"; dropped {json.dumps(why)}" if len(raw) > added else "")
        + (f"; first: {json.dumps(raw[0])[:200]}" if raw and not added else ""))
    return plan_


# ----- making the clip --------------------------------------------------------------------------------------------------
def plan_parts(cid):
    """Series campaigns (rules "series"): every episode in order, split into consecutive parts of at most max_s seconds
    at sentence ends, each part a moment titled with its episode and part number. Already planned episodes are kept."""
    c = campaigns([cid])[cid]; r = c["rules"]
    words = transcribe(cid)
    p = PLANS / f"{cid}.json"
    plan_ = json.loads(p.read_text()) if p.exists() else {"moments": []}
    eps = plan_.get("episodes") or [{"n": 1, "start": 0.0, "end": words[-1]["e"] if words else duration(segment(cid))}]
    have = {m.get("episode") for m in plan_["moments"]}
    max_s, min_s = float(r.get("max_s", 55)), float(r.get("min_s", 15))
    added = 0
    for e in eps:
        if e["n"] in have: continue
        a, end = float(e["start"]), float(e["end"])
        ends = [w["e"] for w in words if a < w["e"] < end and w["w"].endswith((".", "?", "!"))]
        cuts = []
        while end - a > max_s + 1:
            hi = min(a + max_s, end - min_s)                    # the part after this one must still be long enough
            cands = [x for x in ends if a + min_s <= x <= hi]
            cut = max(cands) if cands else hi
            cuts.append(cut); a = cut
        cuts.append(end)
        a = float(e["start"]); n = len(cuts)
        for k, b in enumerate(cuts, 1):
            if profane(words, a, b):
                log(f"{cid}: episode {e['n']} part {k} has strong language, the episode is skipped"); break
            plan_["moments"].append({"id": f"{cid}-e{e['n']:02d}p{k}", "episode": e["n"], "part": k, "of": n, "start": round(a, 2), "end": round(b, 2),
                                     "hook": f"EPISODE {e['n']}, PART {k} OF {n}", "label": "", "title": f"{c['subject']} Episode {e['n']} Part {k}"[:70],
                                     "planned": NOW.isoformat(timespec="minutes"), "model": "parts"})
            a = b; added += 1
    PLANS.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    log(f"{cid}: {added} parts planned, {len(plan_['moments'])} in all")
    return plan_


def ass_time(t):
    h, rem = divmod(max(0.0, t), 3600); m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def ass_escape(s): return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def captions(words, a, b, path, style="lines", y=430, top=False):
    """Captions as an ASS file. "lines": three or four words at a time below the picture. "karaoke": the same groups
    with each word lighting up yellow as it is spoken (the style every big clipping channel uses), placed at `y`
    pixels from the bottom of the 1920-pixel frame (from the top with `top`, when the person is low in the picture)."""
    sel = [w for w in words if w["s"] >= a - 0.2 and w["e"] <= b + 0.2]
    size = 64 if style == "lines" else 70
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Cap,DejaVu Sans,{size},&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,{8 if top else 2},60,60,{y},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    if style == "lines":      # plain white: PrimaryColour is what shows when nothing is sung
        head = head.replace("&H0000FFFF,&H00FFFFFF", "&H00FFFFFF,&H0000FFFF")
    ev, group = [], []
    for w in sel:
        group.append(w)
        if len(group) >= (4 if style == "lines" else 3) or w["w"].endswith((".", "?", "!", ",")) and len(group) >= 2:
            ev.append(group); group = []
    if group: ev.append(group)
    lines = []
    for i, g in enumerate(ev):
        s0 = g[0]["s"] - a; e0 = (ev[i + 1][0]["s"] if i + 1 < len(ev) else g[-1]["e"] + 0.6) - a
        if style == "karaoke":   # \k times in centiseconds: each word turns from white to yellow as it is said
            parts, t = [], g[0]["s"]
            for x in g:
                gap = max(0, int(round((x["s"] - t) * 100))); dur = max(5, int(round((x["e"] - x["s"]) * 100)))
                parts.append((f"{{\\k{gap}}}" if gap else "") + f"{{\\k{dur}}}" + ass_escape(x["w"].upper())); t = x["e"]
            text = " ".join(parts)
        else:
            text = ass_escape(" ".join(x["w"] for x in g).upper())
        lines.append(f"Dialogue: 0,{ass_time(s0)},{ass_time(min(e0, b - a))},Cap,,0,0,0,,{text}")
    pathlib.Path(path).write_text(head + "\n".join(lines) + "\n")


def wrap(text, width=22, lines=2):
    """Text as at most `lines` lines of about `width` characters (drawtext does not wrap by itself)."""
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: out.append(cur)
    if len(out) > lines: out = out[:lines - 1] + [" ".join(out[lines - 1:])]
    return out


def drawtext(text, size, y, colour="white", box=True):
    rows = wrap(text, 22 if size >= 56 else 34)
    if len(rows) > 1 and size >= 56: size = 54
    t = "\n".join(rows).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "%%")
    extra = ":box=1:boxcolor=black@0.55:boxborderw=18" if box else ""
    return (f"drawtext=fontfile='{FONT}':text='{t}':fontsize={size}:fontcolor={colour}:x=(w-text_w)/2:y={y}:line_spacing=8"
            f":borderw=3:bordercolor=black{extra}")


def face_box(seg, a, b, every=2.0):
    """Where the person is between a and b, as (x, y, w, h) fractions of the picture: OpenCV's face detector on a frame
    every `every` seconds, detections grouped by position, and the group that is present in at least half the frames
    AND changes most over time wins (a real face talks and moves; a face-like patch of wall does not). None when no
    group qualifies."""
    try:
        import cv2, numpy as np
    except ImportError: return None
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    groups, n = {}, 0          # (round x, round y) -> [(box, 32x32 grey patch)]
    t = a + 0.5
    while t < b:
        f = WORK / "face.jpg"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(seg), "-frames:v", "1", "-q:v", "4", str(f)])
        img = cv2.imread(str(f)) if f.exists() else None
        if img is not None:
            n += 1; h, w = img.shape[:2]; grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            for (x, y, fw, fh) in casc.detectMultiScale(grey, 1.2, 6, minSize=(int(h * 0.08), int(h * 0.08))):
                key = (round(x / w, 1), round(y / h, 1))
                patch = cv2.resize(grey[y:y + fh, x:x + fw], (32, 32)).astype("float32")
                groups.setdefault(key, []).append(((x / w, y / h, fw / w, fh / h), patch))
        t += every
    if n == 0: return None
    best, score = None, -1.0
    for key, items in groups.items():
        if len(items) < max(2, n / 2): continue
        change = float(np.mean(np.std(np.stack([pt for _, pt in items]), axis=0)))     # how much the patch moves and talks
        if change > score: best, score = items, change
    log(f"  faces: {n} frames, groups " + ", ".join(f"{k}:{len(v)}" for k, v in groups.items()) + f", best change {score:.1f}")
    if not best or score < 4.0: return None
    med = lambda k: sorted(v[0][k] for v in best)[len(best) // 2]
    return (med(0), med(1), med(2), med(3))


def portrait(seg):
    """True when the source picture is taller than wide (a vertical video needs no layout, it fills the frame)."""
    try:
        w, h = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(seg)],
                              capture_output=True, text=True).stdout.strip().split(",")[:2]
        return int(h) > int(w)
    except Exception: return False


def layout_filters(layout, face):
    """The ffmpeg graph that turns the landscape picture [0:v] into the 1080x1920 canvas [v1]: "letterbox" (the picture
    centred over its own blurred copy), "full" (the picture fills the screen: a 9:16 window on the person, or the middle,
    the text placed clear of the person), "face" (the window on the face, text in fixed places), "split" (the face on
    top, the whole picture below). face: (x, y, w, h) fractions, or None (then letterbox for face and split)."""
    if layout in ("face", "split") and not face: layout = "letterbox"
    blur = "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:3,eq=brightness=-0.15[bgb];"
    if layout == "full":                                    # the picture fills the screen, the window on the person (or the middle)
        cx = min(max(face[0] + face[2] / 2, 0.2), 0.8) if face else 0.5
        return (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:x=min(max(iw*{cx:.3f}-540\\,0)\\,iw-1080):y=0[v1];", layout)
    if layout == "face":
        cx = min(max(face[0] + face[2] / 2, 0.2), 0.8)          # the window stays inside the picture
        return (f"[0:v]crop=w=ih*9/16:h=ih:x=min(max(iw*{cx:.3f}-ih*9/32\\,0)\\,iw-ih*9/16):y=0,scale=1080:1920[v1];", layout)
    if layout == "split":
        cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
        side = min(max(face[3] * 2.8, 0.3), 1.0)               # a square around the head, with room for the shoulders
        return (f"[0:v]split=2[cam][game];"
                f"[cam]crop=w=min(ih*{side:.3f}\\,iw):h=min(ih*{side:.3f}\\,iw):x=min(max(iw*{cx:.3f}-ih*{side / 2:.3f}\\,0)\\,iw-min(ih*{side:.3f}\\,iw)):"
                f"y=min(max(ih*{cy:.3f}-ih*{side / 2:.3f}\\,0)\\,ih-min(ih*{side:.3f}\\,iw)),scale=1080:1080[camS];"
                f"[game]scale=1080:-2[gameS];[camS]pad=1080:1920:0:0:black[canvas];[canvas][gameS]overlay=0:1080[v1];", layout)
    return (f"[0:v]split=2[bg][fg];{blur}[fg]scale=1080:-2[fgs];[bgb][fgs]overlay=0:(H-h)/2[v1];", "letterbox")


TESTS = {"layout": ["letterbox", "full", "split"], "captions": ["lines", "karaoke"], "punch": ["none", "zoom"],
         "length": ["as planned"], "title": ["subject first", "hook first"], "take": ["voice"]}     # take: recorded, not drawn     # "short" arm retired 23 October: longer clips


def short_end(words, a, b, peak, min_s=15, max_s=28.0):
    """For the "short" length arm: the last sentence end inside max_s of the start (after the peak, past min_s), when it
    cuts more than 4 seconds; None when the moment is short already or no sentence ends there."""
    if b - a <= max_s + 4: return None
    ends = [w["e"] for w in words if a < w["e"] <= a + max_s and str(w["w"]).strip().endswith((".", "?", "!"))
            and w["e"] - a >= max(min_s, 12) and (peak is None or w["e"] > float(peak) + 1.0)]
    return round(ends[-1] + 0.4, 2) if ends and b - ends[-1] > 4 else None


def test_plan(mid):
    """One arm per test for a clip, by its id (repeatable), weighted by clips/insights.json when it has a verdict."""
    import random
    rng = random.Random(f"clip:{mid}")
    try: ins = json.loads((ROOT / "clips" / "insights.json").read_text()).get("tests") or {}
    except Exception: ins = {}
    out = {}
    for t, arms in TESTS.items():
        best = (ins.get(t) or {}).get("best")
        out[t] = best if best in arms and rng.random() < 0.7 else rng.choice(arms)
    return out


# ----- our own take (Charlie, 23 October) ---------------------------------------------------------------------------------
# YouTube (1 October 2026) cuts the reach of re-uploads "without significant changes" and says template edits don't count,
# so every clip now carries our own commentary: a spoken set-up over the first seconds (the stream's sound dips under it)
# and our reaction after the payoff, on a held last frame with a question for the comments. It is opinion and framing,
# never a claim the footage doesn't show (the campaigns' "no made-up claims" rule). Campaigns whose rules avoid AI-made
# video get the take as on-screen text only; CLIPS_TAKE=none turns it off (tests).
TAKE_PROMPT = """You add a short spoken take of our own to a clip for a family-friendly UK clips channel, so the clip is
commentary, not a re-upload. The clip: {label}. Its on-screen hook: "{hook}". Why it was picked: {why}. What is said in
it: "{said}".
Write:
- "intro": what our narrator says over the first seconds, 6 to 12 words: sets up why to keep watching, in our own voice
  ("Watch what happens when...", "This is the moment...", "Nobody expected this from..."), without giving away the payoff;
- "outro": our reaction after the payoff, 6 to 14 words, ending with a short question viewers will answer in the comments.
Opinion and framing only: never state a fact, name or number the clip doesn't show, nothing negative about anyone, no
swearing, UK English, no dashes. Return {{"intro": "...", "outro": "..."}}"""


def take_lines(c, m, words):
    """Our intro and outro lines for a moment (planned with the moment since 23 October, else written here); None when no
    model answers or the lines break a rule."""
    if m.get("take_intro") and m.get("take_outro"): return m["take_intro"], m["take_outro"]
    import factpack
    said = " ".join(w["w"] for w in words if m["start"] <= w["s"] <= m["end"])[:900]
    try:
        ans, _ = factpack.gemini(TAKE_PROMPT.format(label=c["source"].get("label", c["subject"]), hook=m.get("hook", ""),
                                                    why=m.get("why", ""), said=said), None, timeout=90, temperature=0.6, writing=True, lite=True)
    except Exception as e:
        log(f"{m['id']}: take not written ({str(e)[:80]})"); return None
    intro, outro = (factpack.undash(str((ans or {}).get(k) or "")).strip() for k in ("intro", "outro"))
    ok = lambda t, lo, hi: lo <= len(t.split()) <= hi and not PROFANE.search(t) and not UNSAFE.search(t)
    if not (ok(intro, 4, 14) and ok(outro, 4, 16)): log(f"{m['id']}: take refused ({intro} | {outro})"[:160]); return None
    m["take_intro"], m["take_outro"] = intro, outro
    return intro, outro


def take_voice(m, intro, outro):
    """The two lines read by the house voice (Chatterbox, tts_cb.py, as the Daily Shorts): (intro wav, outro wav), or None
    when the voice model isn't installed on this runner (the take is then on-screen text)."""
    if not os.environ.get("CB_CKPT") or not shutil.which("ffmpeg"): return None
    d = WORK / f"take-{m['id']}"; d.mkdir(parents=True, exist_ok=True)
    board = d / "take.json"
    board.write_text(json.dumps({"id": m["id"], "beats": [{"say": intro}, {"say": outro}]}))
    try:
        subprocess.run([sys.executable, str(ROOT / "pipeline" / "tts_cb.py"), str(board), str(d), "--voice", "F2", "--target-wps", "2.9"],
                       check=True, capture_output=True, text=True, timeout=600, cwd=str(ROOT / "pipeline"))
        a, b = d / "cb_b00.wav", d / "cb_b01.wav"
        return (a, b) if a.exists() and b.exists() else None
    except Exception as e:
        log(f"{m['id']}: take voice failed ({str(e)[:120]})"); return None


def wav_seconds(p):
    try: return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                     capture_output=True, text=True).stdout.strip() or 0)
    except Exception: return 0.0


def make_clip(cid, m, words):
    """One 1080x1920 clip: the picture laid out by the clip's layout test (letterbox, face, split), the hook at the top,
    the label under it, captions in the clip's caption style, an optional zoom punch-in on the peak moment, the credit
    at the bottom, loudness normalised. The tests used are written on the moment."""
    c = campaigns([cid])[cid]
    OUT.mkdir(parents=True, exist_ok=True)
    seg, out = segment(cid), OUT / f"{m['id']}.mp4"
    a, b = m["start"], m["end"]
    tests = m.get("tests") or test_plan(m["id"])
    for t in TESTS:                                     # CLIPS_LAYOUT, CLIPS_CAPTIONS, CLIPS_PUNCH force an arm (tests)
        if os.environ.get(f"CLIPS_{t.upper()}") in TESTS[t]: tests[t] = os.environ[f"CLIPS_{t.upper()}"]
    if (c.get("rules") or {}).get("full_frame"): tests["layout"] = "letterbox"       # the whole picture must stay (a rule)
    elif portrait(seg) and tests["layout"] != "full": tests["layout"] = "letterbox"   # a vertical source: whole, or filling the screen
    face = face_box(seg, a, b) if tests["layout"] in ("face", "split", "full") else None
    graph, layout = layout_filters(tests["layout"], face)
    if layout != tests["layout"]: log(f"{m['id']}: {tests['layout']} layout asked, no steady face, letterbox instead")
    elif face: log(f"{m['id']}: {layout} layout, face at x {face[0]:.2f} y {face[1]:.2f} size {face[3]:.2f}")
    tests["layout"] = layout
    r = c.get("rules") or {}
    if tests.get("length") == "short" and not m.get("episode"):           # the same moment, cut to its first payoff
        nb = short_end(words, a, b, m.get("peak"), r.get("min_s", 15))
        if nb: m["end_planned"], b = b, nb; m["end"] = nb; log(f"{m['id']}: short arm, {b - a:.0f}s instead of {m['end_planned'] - a:.0f}s")
        else: tests["length"] = "as planned"
    else: tests["length"] = "as planned"
    if tests.get("title") == "hook first" and not m.get("episode"):       # the hook as the title, the subject after
        h = m["hook"].capitalize() if m["hook"].isupper() else m["hook"]
        m.setdefault("title_planned", m["title"]); m["title"] = f"{h} | {c['subject']}"[:70]
    else: tests["title"] = "subject first"
    cap_y, cap_top = {"letterbox": 430, "face": 520, "split": 140, "full": 300}[layout], False     # ASS margin from the bottom
    hook_y = 250 if layout != "split" else 60
    if layout == "full":                                    # the text goes where the person is not
        fy = face[1] + face[3] / 2 if face else 0.5
        if fy < 0.42: hook_y = 1200                         # person high: hook and captions in the lower third
        elif fy > 0.62: hook_y, cap_y, cap_top = 120, 330, True      # person low: everything at the top
        else: hook_y = 120                                  # person in the middle: hook at the top, captions at the foot
        log(f"{m['id']}: full layout, person at y {fy:.2f}, hook at {hook_y}, captions {'top' if cap_top else 'bottom'}")
    ass = WORK / f"{m['id']}.ass"; captions(words, a, b, ass, tests["captions"], cap_y, cap_top)
    credit = f"Clip from {c['subject']}, posted with permission"
    label_y = hook_y + 190
    peak = m.get("peak")
    if tests["punch"] == "zoom" and peak and a < float(peak) < b - 1.5:    # 1.5 seconds at 1.12x on the peak moment, picture only
        t0 = float(peak) - a
        graph += (f"[v1]split=2[va][vb];[vb]scale=1210:2150,crop=w=1080:h=1920:x=(iw-1080)/2:y=(ih-1920)/2[big];"
                  f"[va][big]overlay=0:0:enable='between(t,{t0:.2f},{t0 + 1.5:.2f})'[v1z];")
    else:
        graph += "[v1]null[v1z];"; tests["punch"] = "none"
    vf = (graph + f"[v1z]{drawtext(m['hook'].upper(), 62, hook_y)}[v2];"
          + (f"[v2]{drawtext(m['label'], 44, label_y, 'yellow')}[v3];" if m.get("label") else "[v2]null[v3];")
          + f"[v3]subtitles='{ass}'[v4];[v4]{drawtext(credit, 30, 1800 if layout != 'split' else 1862, 'white', False)}[v]")
    take = None if os.environ.get("CLIPS_TAKE", "").strip() == "none" or m.get("episode") else take_lines(c, m, words)
    no_ai = any(re.search(r"\bAI\b", str(x)) for x in r.get("avoid") or [])      # a campaign that avoids AI-made video
    voice = take_voice(m, *take) if take and not no_ai else None
    L = b - a
    if take:
        intro, outro = take
        i_dur = max(2.5, wav_seconds(voice[0]) + 0.3) if voice else 3.0
        o_dur = max(3.0, wav_seconds(voice[1]) + 0.6) if voice else 3.5
        # the held last frame for our reaction; the intro line sits under the hook while it is spoken
        vf = vf[:-len("[v]")] + "[vb0];" + (f"[vb0]{drawtext(intro, 46, hook_y + 330, 'white')}:enable='lt(t,{i_dur:.2f})'[vb1];"
              f"[vb1]tpad=stop_mode=clone:stop_duration={o_dur:.2f}[vb2];"
              f"[vb2]{drawtext(outro, 56, 1300, 'yellow')}:enable='gte(t,{L:.2f})'[v]")
        tests["take"] = "voice" if voice else "text"
    else:
        tests["take"] = "none"
    if voice:
        ms = int(L * 1000)
        af = (f"[0:a]aresample=48000,aformat=channel_layouts=stereo,volume='if(lt(t,{i_dur:.2f}),0.25,1)':eval=frame,apad=pad_dur={o_dur:.2f}[o];"
              f"[1:a]aresample=48000,aformat=channel_layouts=stereo,adelay=150|150[i];"
              f"[2:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[e];"
              f"[o][i][e]amix=inputs=3:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
        ins, amap = ["-i", str(voice[0]), "-i", str(voice[1])], ["-map", "[aout]"]
        vf = vf + ";" + af
    elif take:
        vf = vf + f";[0:a]apad=pad_dur={o_dur:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[aout]"; ins, amap = [], ["-map", "[aout]"]
    else:
        ins, amap = [], ["-map", "0:a", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    cmd = (["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(seg)] + ins
           + ["-filter_complex", vf, "-map", "[v]"] + amap + ["-r", "30",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(out)])
    run(cmd)
    m["tests"] = tests
    return out


def unmade(cid):
    p = PLANS / f"{cid}.json"
    if not p.exists(): return 0
    return sum(1 for m in json.loads(p.read_text()).get("moments") or [] if not m.get("made") and not m.get("skipped"))


def dark(frame):
    """True when the picture band of a frame (the middle third) is nearly black: a stream outage, a loading screen."""
    try:
        from PIL import Image, ImageStat
        im = Image.open(frame).convert("L"); w, h = im.size
        return ImageStat.Stat(im.crop((0, int(h * 0.34), w, int(h * 0.66)))).mean[0] < 22
    except Exception: return False


def frame_of(out, m):
    frames = ROOT / "clips" / "frames"; frames.mkdir(parents=True, exist_ok=True)
    f = frames / f"{m['id']}.jpg"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{(m['end'] - m['start']) * 0.3:.2f}", "-i", str(out),
                    "-frames:v", "1", "-vf", "scale=540:960", "-q:v", "6", str(f)])
    return f


def make(cid, count=None, channel=None):
    """Makes up to `count` clips of the campaign's next moments (the day's share), marking each with the channel it is
    for (the campaign's first channel when none is given)."""
    c = campaigns([cid])[cid]
    plan_p = PLANS / f"{cid}.json"
    plan_ = json.loads(plan_p.read_text()) if plan_p.exists() else {"moments": []}
    series = bool((c.get("rules") or {}).get("series"))
    todo = [m for m in plan_["moments"] if not m.get("made") and not m.get("skipped")]
    if not todo: plan_ = plan_parts(cid) if series else plan(cid); todo = [m for m in plan_["moments"] if not m.get("made") and not m.get("skipped")]
    want = int(count if count is not None else c.get("per_day", 3))
    if series: want = sum(1 for m in todo if m.get("episode") in sorted({m.get("episode") for m in todo})[:want])   # whole episodes
    words = transcribe(cid)
    made = []
    for m in todo:
        if len(made) >= want: break
        bad = profane(words, m["start"], m["end"]) or PROFANE.findall(m.get("hook", ""))
        if bad: m["skipped"] = f"profanity: {', '.join(bad[:3])}"; log(f"{m['id']}: skipped: {m['skipped']}"); continue
        if UNSAFE.search(f"{m.get('hook', '')} {m.get('title', '')}"):      # planned before the rule, or slipped through
            m["skipped"] = "not brand safe"; log(f"{m['id']}: skipped: not brand safe ({m.get('hook', '')[:40]})"); continue
        try:
            out = make_clip(cid, m, words)
            f = frame_of(out, m)
            if dark(f):             # a black screen (an outage, a loading screen): not a clip
                m["skipped"] = "dark picture"; out.unlink(missing_ok=True); log(f"{m['id']}: skipped: dark picture"); continue
            m["made"] = NOW.isoformat(timespec="minutes"); m["file"] = out.name; m["channel"] = channel or channel_of(cid); made.append(m)
            log(f"{m['id']}: made ({m['end'] - m['start']:.0f} s) {m['title']}" + (f" [{m['channel']}]" if m["channel"] != "clips" else ""))
        except Exception as e:
            m["skipped"] = f"{type(e).__name__}: {e}"[:200]; log(f"{m['id']}: skipped: {m['skipped']}")
    plan_p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    return made


# ----- uploading ------------------------------------------------------------------------------------------------------------
def channel_of(cid):
    """A campaign's first YouTube channel (campaigns.json "channel", or the first of "channels", default clips): its
    sign-in is tokens/youtube_<channel>.enc, made with the social workflow."""
    c = CFG["campaigns"].get(cid) or {}
    chans = c.get("channels") or []
    return str(chans[0] if chans else c.get("channel") or "clips")


def campaign_channels(cid):
    """Every channel a campaign posts on (Charlie, 22 October: each channel signed up to every campaign). With several,
    each channel gets different moments of the same footage: a moment is made once and carries its "channel"."""
    c = CFG["campaigns"].get(cid) or {}
    chans = [str(x) for x in (c.get("channels") or []) if x]
    return list(dict.fromkeys(chans or [channel_of(cid)]))


def mchannel(cid, m):
    """The channel a moment posts on: its own mark, else the campaign's first channel."""
    return str((m or {}).get("channel") or channel_of(cid))


def clips_client(channel="clips"):
    """A YouTube client for a clips channel (tokens/youtube_<channel>.enc, the social workflow's sign-in)."""
    import social
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    t = social.load(f"youtube_{channel}")
    if not t.get("refresh_token"): raise RuntimeError(f"the {channel} channel is not signed in (social workflow, channel {channel})")
    creds = Credentials(None, refresh_token=t["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=(t.get("scope") or "").split())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def batch_time(platform=None):
    """The next batch publish time (UK batch_time today, or tomorrow once it is under an hour away) as RFC3339 UTC.
    batch_times in campaigns.json can give a platform its own time ("Vyro": "22:00")."""
    t_str = (CFG.get("batch_times") or {}).get(str(platform or "").split(" ")[0], CFG.get("batch_time", "18:00"))
    h, mi = map(int, str(t_str).split(":"))
    uk = NOW.astimezone(UK)
    t = uk.replace(hour=h, minute=mi, second=0, microsecond=0)
    if t < uk + dt.timedelta(hours=1): t += dt.timedelta(days=1)
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"), t


def upload(cid, mode=None):
    """Uploads the made clips not yet uploaded: private, public together at batch_time (CLIPS_MODE=private: no publish time,
    a test). Each gets a row in clips/submit.csv for Charlie to paste into the campaign."""
    import youtube as Y
    c = campaigns([cid])[cid]; r = c["rules"]
    plan_p = PLANS / f"{cid}.json"
    plan_ = json.loads(plan_p.read_text())
    todo = [m for m in plan_["moments"] if m.get("made") and not m.get("video") and (OUT / m.get("file", "")).exists()]
    if not todo: log(f"{cid}: nothing to upload"); return []
    clients, refused = {}, set()
    mode = mode or os.environ.get("CLIPS_MODE", "").strip() or "batch"
    publish_at, when = (None, None) if mode == "private" else batch_time(c.get("platform"))
    rows, p = [], ROOT / "clips" / "submit.csv"
    for m in todo:
        try:
            if gh("release", "view", OUTREL, check=False).returncode:
                gh("release", "create", OUTREL, "--title", "Clips made", "--notes", "The clips as posted (for Instagram, Facebook and TikTok posting).", "--prerelease")
            gh("release", "upload", OUTREL, str(OUT / m["file"]), "--clobber")
            m["asset_url"] = f"https://github.com/{REPO}/releases/download/{OUTREL}/{m['file']}"
        except Exception as e:
            log(f"{m['id']}: clip asset not kept: {str(e)[:120]}")
        tags = [t.lstrip("#") for t in r.get("hashtags") or []] + [c["subject"]]
        desc = (f"{m['hook'].capitalize()}. {r.get('description', '')}".strip() + "\n\n" + "\n".join(r.get("hashtags") or []) + "\n\n"
                f"Clip from {c['source'].get('label', '')}, posted with the creator's permission ({c['name']}).")
        vid, own = None, mchannel(cid, m)
        # the clip's own channel first; when YouTube refuses it for its daily limit (the gaming and irl channels can't be
        # phone-verified: one number, 23 October), the campaign's other channels take it, so a made clip isn't stranded
        for ch in [own] + [x for x in campaign_channels(cid) + ["clips"] if x != own]:
            if ch in refused: continue
            try:
                if ch not in clients: clients[ch] = clips_client(ch)
                vid = Y.upload(clients[ch], OUT / m["file"], m["title"], desc, tags, "Entertainment", publish_at)
            except Exception as e:
                log(f"{m['id']}: upload failed ({ch}): {type(e).__name__}: {str(e)[:200]}")
                if "uploadLimitExceeded" in str(e) or "exceeded the number of videos" in str(e):
                    ceiling_learn(scheduled_today(ch), refused=True, channel=ch); refused.add(ch); continue
                break                                   # anything else: this clip waits for the next run
            if ch != own: m["channel"] = ch; log(f"{m['id']}: {own} is at its limit, posted on {ch} instead")
            break
        if not vid: continue
        m.update(video=vid, url=f"https://youtube.com/shorts/{vid}", uploaded=NOW.isoformat(timespec="minutes"),
                 publish_at=publish_at or "private", mode=mode)
        where = re.search(r"https://[^\s,]+", str((c.get("submit") or {}).get("where", "")))
        rows.append(submit_row(cid, c, m, "youtube", m["url"], when.strftime("%Y-%m-%d %H:%M") if when else "private (test)"))
        log(f"{m['id']}: uploaded {m['url']} ({mode})")
    plan_p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    add_rows(rows)
    return rows


OUTREL = "clips-out"
REPO = os.environ.get("GITHUB_REPOSITORY", "quickplay-studio/quickplay-autopilot")
SUBMIT_FIELDS = ["clip", "campaign", "campaign_url", "platform", "video", "public_at_uk", "title", "hashtags", "submitted", "channel"]


def submit_row(cid, c, m, platform, link, when):
    where = re.search(r"https://[^\s,]+", str((c.get("submit") or {}).get("where", "")))
    return {"clip": m["id"], "campaign": cid, "campaign_url": where.group(0) if where else c["url"], "platform": platform, "video": link,
            "public_at_uk": when, "title": m["title"], "hashtags": " ".join((c.get("rules") or {}).get("hashtags") or []), "submitted": "",
            "channel": mchannel(cid, m)}


def add_rows(rows):
    """Appends rows to clips/submit.csv, rewriting older rows into the current columns when they are short of one."""
    if not rows: return
    p = ROOT / "clips" / "submit.csv"
    old = list(csv.DictReader(p.open())) if p.exists() else []
    for r in old: r.setdefault("platform", "youtube")
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUBMIT_FIELDS, extrasaction="ignore"); w.writeheader()
        w.writerows([{k: r.get(k, "") for k in SUBMIT_FIELDS} for r in old + rows])


def social_caption(c, m):
    r = c.get("rules") or {}
    return (f"{m['hook'].capitalize()}. {r.get('description', '')}".strip() + "\n\n" + " ".join(r.get("hashtags") or [])
            + f"\n\nClip from {c['subject']}, posted with the creator's permission.")


def social_posts(force=False):
    """Instagram Reels, Facebook Reels and TikTok for every clip public on YouTube today and not posted yet, at the UK
    batch time (within 25 minutes after it, or any time with force): campaigns pay per platform, so one clip earns
    three times. Accounts: IG_CLIPS_TOKEN and IG_CLIPS_USER_ID, FB_CLIPS_PAGE_TOKEN and FB_CLIPS_PAGE_ID (repository
    secrets), tokens/tiktok_clips.enc (the social workflow's TikTok connect for the clips account). Each post gets its
    own row in clips/submit.csv. At most social_per_day posts a platform a day (a new account is ramped gently)."""
    import social as S
    uk = NOW.astimezone(UK)
    windows = {str(CFG.get("batch_time", "18:00"))} | set((CFG.get("batch_times") or {}).values())
    inside = any(0 <= (uk - uk.replace(hour=int(t.split(":")[0]), minute=int(t.split(":")[1]), second=0, microsecond=0)).total_seconds() <= 25 * 60 for t in windows)
    if not inside and not force: log("social: not a batch time"); return 0
    def accounts(channel):
        """The channel's Instagram, Facebook and TikTok sign-ins: IG_<CHANNEL>_TOKEN, IG_<CHANNEL>_USER_ID,
        FB_<CHANNEL>_PAGE_TOKEN, FB_<CHANNEL>_PAGE_ID (CLIPS for the first channel) and tokens/tiktok_<channel>.enc.
        Charlie (22 October): one Instagram (and TikTok, Facebook) account takes every kind of clip, so a channel without
        its own sign-in uses the clips channel's; a channel gets its own only when its secrets exist."""
        def one(ch):
            up = ch.upper()
            ig = {"token": os.environ.get(f"IG_{up}_TOKEN", "").strip(), "user": os.environ.get(f"IG_{up}_USER_ID", "").strip()}
            fb = None
            if os.environ.get(f"FB_{up}_PAGE_TOKEN", "").strip() and os.environ.get(f"FB_{up}_PAGE_ID", "").strip():
                os.environ["FB_PAGE_TOKEN"], os.environ["FB_PAGE_ID"] = os.environ[f"FB_{up}_PAGE_TOKEN"], os.environ[f"FB_{up}_PAGE_ID"]
                S._FB.clear()
                try: fb = S.fb_tokens()
                except Exception as e: log(f"social: Facebook ({ch}): {str(e)[:100]}")
            tt = S.load(f"tiktok_{ch}") if os.environ.get("SOCIAL_KEY") else {}
            return ig, fb, tt
        ig, fb, tt = one(channel)
        if channel != "clips":
            ig0, fb0, tt0 = one("clips")
            if not (ig["token"] and ig["user"]): ig = ig0
            if fb is None: fb = fb0
            if not tt.get("access_token"): tt = tt0
        if not (ig["token"] and ig["user"]) and os.environ.get("SOCIAL_KEY"):
            # Charlie (22 October): the main channel's Instagram (quickplaydaily, tokens/instagram.enc) takes the clips too
            try:
                main = S.ig_tokens()
                if main.get("token") and main.get("user"): ig = {"token": main["token"], "user": str(main["user"])}
            except Exception as e: log(f"social: Instagram ({channel}): {str(e)[:100]}")
        return ig, fb, tt
    have = {ch: accounts(ch) for ch in channels()}
    if not any((ig["token"] and ig["user"]) or fb or tt.get("access_token") for ig, fb, tt in have.values()):
        log("social: no Instagram, Facebook or TikTok account for the clips channel yet"); return 0
    cap, posted, rows = int(CFG.get("social_per_day", 6)), {"instagram": 0, "facebook": 0, "tiktok": 0}, []
    today = str(uk.date())
    for p in sorted(PLANS.glob("*.json")):
        if p.name.endswith(".words.json"): continue
        cid = p.stem; c = CFG["campaigns"].get(cid) or {}
        if not c.get("rules"): continue
        plan_ = json.loads(p.read_text()); changed = False
        for m in plan_.get("moments") or []:
            if not m.get("video") or m.get("pulled") or not m.get("asset_url") or m.get("publish_at") in (None, "private"): continue
            ch = mchannel(cid, m)
            ig, fb, tt = have.get(ch) or ({"token": "", "user": ""}, None, {})
            if fb: os.environ["FB_PAGE_TOKEN"], os.environ["FB_PAGE_ID"] = os.environ[f"FB_{ch.upper()}_PAGE_TOKEN"], os.environ[f"FB_{ch.upper()}_PAGE_ID"]; S._FB.clear()
            try: due = dt.datetime.fromisoformat(m["publish_at"].replace("Z", "+00:00"))
            except ValueError: continue
            if due > NOW + dt.timedelta(minutes=3) or (NOW - due) > dt.timedelta(hours=36): continue
            caption = social_caption(c, m)
            if ig["token"] and ig["user"] and not m.get("instagram") and posted["instagram"] < cap:
                try:
                    media = S.ig_post(ig, m["asset_url"], caption)
                    import requests
                    link = requests.get(f"{S.IG_API}/{media}", params={"fields": "permalink", "access_token": ig["token"]}, timeout=30).json().get("permalink", "")
                    m["instagram"] = {"media": media, "url": link, "at": NOW.isoformat(timespec="minutes")}; changed = True; posted["instagram"] += 1
                    rows.append(submit_row(cid, c, m, "instagram", link or media, today)); log(f"{m['id']}: Instagram {link}")
                except Exception as e:
                    m["instagram_error"] = f"{NOW:%Y-%m-%d %H:%M} {str(e)[:200]}"; changed = True; log(f"{m['id']}: Instagram failed: {str(e)[:160]}")
            if fb and not m.get("facebook") and posted["facebook"] < cap:
                try:
                    f = WORK / m["file"]; WORK.mkdir(parents=True, exist_ok=True)
                    if not f.exists(): gh("release", "download", OUTREL, "-p", m["file"], "-D", str(WORK), "--clobber")
                    vid = S.fb_post(fb, f, caption)
                    link = f"https://www.facebook.com/reel/{vid}"
                    m["facebook"] = {"video": vid, "url": link, "at": NOW.isoformat(timespec="minutes")}; changed = True; posted["facebook"] += 1
                    rows.append(submit_row(cid, c, m, "facebook", link, today)); log(f"{m['id']}: Facebook {link}")
                except Exception as e:
                    m["facebook_error"] = f"{NOW:%Y-%m-%d %H:%M} {str(e)[:200]}"; changed = True; log(f"{m['id']}: Facebook failed: {str(e)[:160]}")
            if tt.get("access_token") and CFG.get("tiktok") and not m.get("tiktok") and posted["tiktok"] < cap:
                try:
                    f = WORK / m["file"]; WORK.mkdir(parents=True, exist_ok=True)
                    if not f.exists(): gh("release", "download", OUTREL, "-p", m["file"], "-D", str(WORK), "--clobber")
                    pid = S.tt_post(tt, f, caption, CFG.get("tiktok_mode", "direct"))
                    m["tiktok"] = {"publish": pid, "at": NOW.isoformat(timespec="minutes")}; changed = True; posted["tiktok"] += 1
                    rows.append(submit_row(cid, c, m, "tiktok", "TikTok: open the app, the post is in your profile", today)); log(f"{m['id']}: TikTok {pid}")
                except Exception as e:
                    m["tiktok_error"] = f"{NOW:%Y-%m-%d %H:%M} {str(e)[:200]}"; changed = True; log(f"{m['id']}: TikTok failed: {str(e)[:160]}")
        if changed: p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    add_rows(rows)
    log(f"social: {posted}")
    return sum(posted.values())


def question_for(cid, c, m):
    """The planner's question for the comments; a clip planned before questions existed gets one asked now from what
    was said in it (a plain question when no model answers)."""
    if m.get("question"): return m["question"]
    q = ""
    try:
        import factpack
        wp = PLANS / f"{cid}.words.json"
        words = json.loads(wp.read_text()) if wp.exists() else []
        said = " ".join(w["w"] for w in words if m["start"] <= w["s"] <= m["end"])[:1500]
        ans, _ = factpack.gemini(f"A YouTube Short of {c['subject']} shows this moment (on-screen hook: {m.get('hook', '')}). What was said: {said}\n"
                                 "Write one short question for the comments that viewers can answer: under 90 characters, family friendly, "
                                 'no spoilers, no strong language, UK English spelling (favourite, colour). Return {"question": "..."}', None, timeout=60, temperature=0.4, lite=True)
        if isinstance(ans, list): ans = next((x for x in ans if isinstance(x, dict)), {})
        q = re.sub(r"[–—]", "-", str((ans or {}).get("question") or "")).strip()[:90]
        if PROFANE.search(q): q = ""
    except Exception as e:
        log(f"{m['id']}: no question from the model: {str(e)[:100]}")
    m["question"] = q or f"What would you have done here? More {c['subject']} clips every day."
    return m["question"]


def engage():
    """On every public clip without one: the channel's own comment (the planner's question, pinned by position as the
    first comment), and for series parts a link to the part before and after. 50 units each, inside the allowance."""
    import quota
    done = 0
    for p in sorted(PLANS.glob("*.json")):
        if p.name.endswith(".words.json"): continue
        cid = p.stem; c = CFG["campaigns"].get(cid) or {}
        if not c.get("rules"): continue
        plan_ = json.loads(p.read_text()); changed = False
        by_part = {(m.get("episode"), m.get("part")): m for m in plan_.get("moments") or [] if m.get("episode")}
        for m in plan_.get("moments") or []:
            if not m.get("video") or m.get("pulled") or m.get("publish_at") in (None, "private"): continue
            try: due = dt.datetime.fromisoformat(m["publish_at"].replace("Z", "+00:00"))
            except ValueError: continue
            if due > NOW: continue
            texts = []
            if not m.get("comment"):
                had = bool(m.get("question")); q = question_for(cid, c, m); changed = changed or not had
                if q: texts.append(("comment", q))
            if m.get("episode") and not m.get("part_links"):
                prev, nxt = by_part.get((m["episode"], m["part"] - 1)), by_part.get((m["episode"], m["part"] + 1))
                lines = [f"Part {m['part'] + 1} is here: {nxt['url']}" for _ in [0] if nxt and nxt.get("url")] + \
                        [f"Missed Part {m['part'] - 1}? {prev['url']}" for _ in [0] if prev and prev.get("url")]
                if lines and (not nxt or nxt.get("url")): texts.append(("part_links", "\n".join(lines)))
            for key, text in texts:
                if not quota.allow(50, "clip comment"): log("engage: no allowance left today"); return done
                try:
                    r = clips_client(mchannel(cid, m)).commentThreads().insert(part="snippet", body={"snippet": {"videoId": m["video"], "topLevelComment": {
                        "snippet": {"textOriginal": text[:900]}}}}).execute()
                    m[key] = r["id"]; quota.spend(50, "clip comment"); changed = True; done += 1
                except Exception as e:
                    m[key + "_error"] = str(e)[:160]; changed = True; log(f"{m['id']}: comment failed: {str(e)[:120]}")
        if changed: p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    log(f"engage: {done} comments")
    return done


def insights(rows):
    """clips/insights.json: for each test (layout, captions, punch) and each campaign, the median and mean views of public clips
    24 hours old or more, and the best arm when it has 3 clips, a mean of 20 views or more and beats the rest by 10%. test_plan() leans on it."""
    aged = [r for r in rows if r.get("privacy") == "public" and float(r.get("hours_public") or 0) >= 24]
    out = {"updated": NOW.isoformat(timespec="minutes"), "clips": len(aged), "tests": {}, "campaigns": {}}
    def med(vals): vals = sorted(vals); return vals[len(vals) // 2] if vals else None
    for t in TESTS:
        arms = {}
        for arm in TESTS[t]:
            vals = [float(r["views"] or 0) for r in aged if r.get(f"test_{t}") == arm]
            arms[arm] = {"n": len(vals), "median_views": med(vals)}
        for arm in arms:
            vals = [float(r["views"] or 0) for r in aged if r.get(f"test_{t}") == arm]
            arms[arm]["mean_views"] = round(sum(vals) / len(vals), 1) if vals else None
        ranked = sorted((a for a in arms if arms[a]["n"] >= 3), key=lambda a: -(arms[a]["mean_views"] or 0))
        top = arms[ranked[0]]["mean_views"] or 0 if ranked else 0
        second = (arms[ranked[1]]["mean_views"] or 0) if len(ranked) > 1 else 0
        best = ranked[0] if ranked and top >= 20 and top >= 1.1 * second else None     # no verdict from clips nobody watched
        out["tests"][t] = {"arms": arms, "best": best}
    # How "viral" is measured (23 October): the planner scores each moment 1 to 10 before it is cut; here that score is
    # checked against what the clip really did (views at 24 hours or more). score_bands shows whether high scores earn more;
    # min_score is the lowest score whose clips (10 or more) beat the clips under it, and plan() uses it in place of 6.
    scored = [(float(r["score"]), float(r["views"] or 0)) for r in aged if str(r.get("score", "")).strip() not in ("", "None")]
    bands = {}
    for lo, hi, name in ((0, 6, "under 6"), (6, 8, "6 to 7"), (8, 11, "8 to 10")):
        vals = [v for sc, v in scored if lo <= sc < hi]
        bands[name] = {"n": len(vals), "mean_views": round(sum(vals) / len(vals), 1) if vals else None}
    out["score_bands"], out["scored_clips"] = bands, len(scored)
    best, top = None, 0.0           # the cut whose clips at or above it average the most views (ties: the lower cut)
    for cut in range(4, 10):
        hi_, lo_ = [v for sc, v in scored if sc >= cut], [v for sc, v in scored if sc < cut]
        if len(hi_) < 10 or len(lo_) < 10: continue
        m_hi = sum(hi_) / len(hi_)
        if m_hi >= 20 and m_hi > 1.2 * (sum(lo_) / len(lo_)) and m_hi > top: best, top = cut, m_hi
    out["min_score"] = best
    for cid in {r["campaign"] for r in aged}:
        vals = [float(r["views"] or 0) for r in aged if r["campaign"] == cid]
        out["campaigns"][cid] = {"n": len(vals), "median_views": med(vals)}
    (ROOT / "clips" / "insights.json").write_text(json.dumps(out, indent=1))
    return out


def stats():
    """Views, likes and comments for every uploaded clip -> clips/stats.csv (the learning data for which campaigns,
    moments and lengths earn)."""
    import youtube as Y
    vids = {}
    for p in PLANS.glob("*.json"):
        if p.name.endswith(".words.json"): continue
        cid = p.stem
        for m in json.loads(p.read_text()).get("moments") or []:
            if m.get("video"): vids[m["video"]] = (cid, m)
    if not vids: return
    rows = []
    by_channel = {}
    for v, (cid, m) in vids.items(): by_channel.setdefault(mchannel(cid, m), []).append(v)
    for channel, ids in by_channel.items():
        yt = clips_client(channel)
        for i in range(0, len(ids), 50):
            for v in yt.videos().list(part="statistics,status", id=",".join(ids[i:i + 50])).execute().get("items", []):
                cid, m = vids[v["id"]]; st = v.get("statistics", {})
                pub = v["status"].get("publishAt") or (m.get("publish_at") if m.get("publish_at") not in (None, "private") else None) or m.get("uploaded")
                try: hours = round((NOW - dt.datetime.fromisoformat(pub.replace("Z", "+00:00"))).total_seconds() / 3600, 1)
                except Exception: hours = ""
                tests = m.get("tests") or {}
                rows.append({"clip": m["id"], "campaign": cid, "channel": channel, "video": v["id"], "seconds": round(m["end"] - m["start"]),
                             "hook_words": len(m["hook"].split()), "score": m.get("score") if m.get("score") is not None else "",
                             "hours_public": hours, "privacy": v["status"].get("privacyStatus"),
                             "views": st.get("viewCount", 0), "likes": st.get("likeCount", 0), "comments": st.get("commentCount", 0),
                             **{f"test_{t}": tests.get(t, "") for t in TESTS},
                             "instagram": (m.get("instagram") or {}).get("url", ""), "facebook": (m.get("facebook") or {}).get("url", ""),
                             **ig_numbers((m.get("instagram") or {}).get("media")),
                             "as_of": NOW.isoformat(timespec="minutes")})
    p = ROOT / "clips" / "stats.csv"
    if not rows: return
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    log(f"stats: {len(rows)} clips")
    try: ins = insights(rows); log("insights:", json.dumps({t: v["best"] for t, v in ins["tests"].items()}))
    except Exception as e: log("insights:", str(e)[:200])


def ig_numbers(media):
    """Instagram views, reach and average watch time of a clip's Reel (23 October), from analytics/cache/instagram.json:
    the clips post on the main channel's Instagram, whose insights the hourly analytics already read for every post."""
    if not media: return {"ig_views": "", "ig_reach": "", "ig_watch_s": ""}
    try: c = json.loads((ROOT / "analytics" / "cache" / "instagram.json").read_text()).get(str(media)) or {}
    except Exception: c = {}
    w = c.get("ig_reels_avg_watch_time")
    return {"ig_views": c.get("views", ""), "ig_reach": c.get("reach", ""), "ig_watch_s": round(w / 1000, 1) if w else ""}


def probe(url):
    """What a footage share link resolves to (printed to the log, so the right downloader can be written): the final
    URL after redirects, the page's size, the API-looking URLs and JSON blobs in it, and what Frame.io's public review
    API says about it."""
    import requests
    ua = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
    r = requests.get(url, headers=ua, timeout=60, allow_redirects=True)
    log("probe:", url, "->", r.url, r.status_code, len(r.text), "bytes")
    for h in r.history: log("  via", h.status_code, h.headers.get("location", "")[:200])
    found = sorted(set(re.findall(r"https://[a-z0-9.-]*frame\.io[^\s\"'<>]{0,200}", r.text)))
    for u in found[:40]: log("  url:", u)
    for m in re.finditer(r"(review_link|share|asset|project)[\w_]*\"?\s*[:=]\s*\"?([a-f0-9-]{20,40})", r.text):
        log("  id:", m.group(0)[:120])
    ids = re.findall(r"/reviews/([a-f0-9-]{36})", r.url) + re.findall(r"/share/([A-Za-z0-9_-]{6,40})", r.url)
    for rid in ids:
        for api in (f"https://api.frame.io/v2/review_links/{rid}/items", f"https://api.frame.io/v2/review_links/{rid}",
                    f"https://api.frame.io/v4/shares/{rid}", f"https://api.frame.io/v2/shares/{rid}"):
            try:
                a = requests.get(api, headers={**ua, "Accept": "application/json"}, timeout=30)
                log(f"  api {api}: {a.status_code} {a.text[:1500]}")
            except Exception as e: log(f"  api {api}: {e}")
    dump = ROOT / "status" / ("probe_" + re.sub(r"[^A-Za-z0-9]+", "_", url)[-40:] + ".html")
    dump.write_text(r.text)
    log("  html saved to", dump.name)
    if "frame.io" in r.url:
        try:
            out = WORK / "probe.bin"; WORK.mkdir(parents=True, exist_ok=True)
            frameio_download(url, out, shot=dump.with_suffix(".png"))
            log(f"  browser download worked: {out.stat().st_size / 1e6:.0f} MB, {duration(out):.0f} s of media")
        except Exception as e:
            log(f"  browser download: {type(e).__name__}: {str(e)[:300]}")
        return
    for key in ("download", "original", "media_links", "h264", "mp4", "stream", "token"):
        for m in list(re.finditer(key, r.text))[:3]:
            log(f"  {key} at {m.start()}: {re.sub(chr(10), ' ', r.text[max(0, m.start() - 120): m.start() + 240])}")


CEILING = STATE / "ceiling.json"


def ceiling_file(channel="clips"):
    """Each YouTube channel learns its own ceiling: clips/state/ceiling.json for the first channel, ceiling_<channel>.json
    for the others (Charlie, 22 October: more channels for more niches)."""
    return CEILING if channel == "clips" else STATE / f"ceiling_{channel}.json"


def channels():
    """The YouTube channels the active campaigns post on, with their campaign ids."""
    out, missing = {}, set()
    for cid in campaigns():
        for ch in campaign_channels(cid):
            if not (ROOT / "tokens" / f"youtube_{ch}.enc").exists(): missing.add(ch); continue     # not signed in yet: nothing is made for it
            out.setdefault(ch, []).append(cid)
    for ch in sorted(missing): log(f"channel {ch}: not signed in yet (tokens/youtube_{ch}.enc), skipped")
    return out


def daily_limit(channel="clips"):
    """Clips a day on a channel: its learned ceiling when there is one, else campaigns.json daily_clips."""
    base = int(CFG.get("daily_clips", 10))
    try: return max(1, int(json.loads(ceiling_file(channel).read_text()).get("limit") or base))
    except Exception: return base


def ceiling_learn(scheduled, refused=False, channel="clips"):
    """Like the main channel's quota.learn: a refusal (uploadLimitExceeded) settles the ceiling at what YouTube took;
    a filled day with no refusal in 48 hours and no rise in 24 hours lifts it by clips_limit_step, up to clips_limit_max."""
    CEILING = ceiling_file(channel)
    try: st = json.loads(CEILING.read_text())
    except Exception: st = {}
    limit, now = daily_limit(channel), NOW.isoformat(timespec="minutes")
    def age(k):
        try: return (NOW - dt.datetime.fromisoformat(st[k])).total_seconds() / 3600
        except (KeyError, ValueError, TypeError): return 1e9
    STATE.mkdir(parents=True, exist_ok=True)
    if refused:
        new = max(int(CFG.get("clips_limit_min", 4)), int(scheduled))
        st.update(limit=new, refused_at=now, refused_with=int(scheduled)); CEILING.write_text(json.dumps(st, indent=1))
        log(f"ceiling: YouTube refused an upload with {scheduled} today, the {channel} channel's limit is now {new}"); return new
    top, step = int(CFG.get("clips_limit_max", 30)), int(CFG.get("clips_limit_step", 2))
    if limit >= top or age("refused_at") < 48 or age("raised_at") < 24 or int(scheduled) < limit: return limit
    new = min(top, limit + step)
    st.update(limit=new, raised_at=now, raised_with=int(scheduled)); CEILING.write_text(json.dumps(st, indent=1))
    log(f"ceiling: a full day with no refusal, the {channel} channel's limit rises {limit} to {new}"); return new


def median_views(cid):
    """Median views of the campaign's public clips so far (clips/stats.csv), None until it has 3."""
    p = ROOT / "clips" / "stats.csv"
    if not p.exists(): return None
    vals = [float(r["views"] or 0) for r in csv.DictReader(p.open()) if r.get("campaign") == cid and r.get("privacy") == "public"
            and float(r.get("hours_public") or 0) >= 24]
    if len(vals) < 3: return None
    vals.sort(); return vals[len(vals) // 2]


def reach_share(min_views):
    """Charlie (22 October): a clip under its campaign's minimum earns nothing, so the planner weighs how often our clips
    actually reach a minimum: the smoothed share of our measured public clips (24 hours or more) with at least that many
    views, (reached + 1) / (measured + 4), never under 0.05 so a campaign keeps being tried; 1.0 with no minimum."""
    if not min_views: return 1.0
    p = ROOT / "clips" / "stats.csv"
    vals = []
    if p.exists():
        latest = {}
        for r in csv.DictReader(p.open()):
            if r.get("privacy") != "public" or float(r.get("hours_public") or 0) < 24: continue
            k = (r.get("clip"), r.get("video"))
            if k not in latest or (r.get("as_of") or "") >= (latest[k].get("as_of") or ""): latest[k] = r
        vals = [float(r.get("views") or 0) for r in latest.values()]
    return max(0.05, (sum(1 for v in vals if v >= float(min_views)) + 1) / (len(vals) + 4))


def allocate(remaining, count=None, channel=None):
    """How many clips each active campaign gets today: the day's remaining number shared by expected money (pay per
    1,000 times the campaign's median views, a 1,000-view prior until it has 3 measured clips, times how often our clips
    reach the campaign's minimum views (reach_share), with a little noise so every campaign keeps being tried), each
    capped by its per_day. The data decides, like the main channel. With a channel, only that channel's campaigns share
    the number."""
    import random
    cs = {cid: c for cid, c in campaigns().items() if channel is None or channel in campaign_channels(cid)}
    if not cs or remaining <= 0: return {}
    rng = random.Random(str(NOW.date()))
    score = {cid: c.get("pay_per_1k", 1.0) * (median_views(cid) or 1000.0) * reach_share(c.get("min_views") or 0) * rng.uniform(0.8, 1.25)
             for cid, c in cs.items()}
    order = sorted(cs, key=lambda cid: -score[cid])
    out, left = {}, remaining
    for cid in order:                                   # one each first, strongest first, then up to per_day
        cap = count if count is not None else int(cs[cid].get("per_day", 3))
        if left > 0 and cap > 0: out[cid] = 1; left -= 1
    for cid in order:
        cap = count if count is not None else int(cs[cid].get("per_day", 3))
        while left > 0 and out.get(cid, 0) < cap: out[cid] = out.get(cid, 0) + 1; left -= 1
    if count is None:                                   # the day's number is the point: past per_day, one more each round, strongest first
        more = [cid for cid in order if not (cs[cid].get("rules") or {}).get("series")]
        while left > 0 and more:
            grew = False
            for cid in more:
                if left > 0 and out.get(cid, 0) < int(cs[cid].get("per_day_max", 8)): out[cid] = out.get(cid, 0) + 1; left -= 1; grew = True
            if not grew: break
    return out


def review():
    """Before a run: any clip still waiting for its publish time whose words fail the profanity check is pulled (made
    private with no publish time) and marked, so a rule that tightened after the upload still holds."""
    pulled = 0
    for p in PLANS.glob("*.json"):
        if p.name.endswith(".words.json"): continue
        cid = p.stem; plan_ = json.loads(p.read_text()); changed = False
        wp = PLANS / f"{cid}.words.json"
        words = json.loads(wp.read_text()) if wp.exists() else []
        for m in plan_.get("moments") or []:
            if not m.get("video") or m.get("pulled") or not m.get("publish_at") or m["publish_at"] == "private": continue
            try: due = dt.datetime.fromisoformat(m["publish_at"].replace("Z", "+00:00"))
            except ValueError: continue
            bad = profane(words, m["start"], m["end"]) or PROFANE.findall(m.get("hook", ""))
            if not bad and UNSAFE.search(f"{m.get('hook', '')} {m.get('title', '')}"): bad = ["not brand safe"]
            if not bad and dark(ROOT / "clips" / "frames" / f"{m['id']}.jpg"): bad = ["dark picture"]
            if due > NOW and bad:
                try:
                    for attempt in range(4):        # YouTube answers 503 now and then
                        try:
                            clips_client(mchannel(cid, m)).videos().update(part="status", body={"id": m["video"], "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}).execute(); break
                        except Exception as e:
                            if attempt == 3 or "503" not in str(e): raise
                            time.sleep(15 * (attempt + 1))
                    m["pulled"] = (bad[0] if bad in (["dark picture"], ["not brand safe"]) else f"profanity: {', '.join(bad[:3])}"); changed = True; pulled += 1
                    log(f"{m['id']}: pulled before publishing ({m['pulled']})")
                except Exception as e:
                    log(f"{m['id']}: could not pull: {type(e).__name__}: {str(e)[:150]}")
        if changed: p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    if pulled:
        sp = ROOT / "clips" / "submit.csv"
        if sp.exists():
            rows = list(csv.DictReader(sp.open()))
            ids = {m["id"] for p in PLANS.glob("*.json") if not p.name.endswith(".words.json")
                   for m in json.loads(p.read_text()).get("moments") or [] if m.get("pulled")}
            for r in rows:
                if r["clip"] in ids: r["submitted"] = "pulled"
            with sp.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    return pulled


def scheduled_today(channel=None):
    """Clips already uploaded for the next batch (so two runs in a day share the daily number), on one channel or all."""
    iso, _ = batch_time(); n = 0
    for p in PLANS.glob("*.json"):
        if p.name.endswith(".words.json"): continue
        n += sum(1 for m in json.loads(p.read_text()).get("moments") or [] if m.get("publish_at") == iso and not m.get("pulled")
                 and (channel is None or mchannel(p.stem, m) == channel))
    return n


def page_text(url):
    """The visible text of a page, rendered (the campaign pages are built by scripts), else the raw page."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(); page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90000); page.wait_for_timeout(6000)
            text = page.inner_text("body"); browser.close()
            return re.sub(r"\s+", " ", re.sub(r"[\u2066-\u2069\u200b-\u200f\u202a-\u202e]", "", text))     # bidi isolates around the figures
    except Exception as e:
        log(f"  rendered read failed ({type(e).__name__}), raw page instead")
        import requests
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).text))


def check_campaigns():
    """Every active campaign: off when its end date has passed, or (Content Rewards, public pages) when the page says it
    is full or ended or has under clips_budget_floor dollars left. Writes clips/campaigns.json; the reason stays in why_off."""
    import requests
    changed = False
    for cid, c in CFG["campaigns"].items():
        if not c.get("active"): continue
        why = ""
        if c.get("ends") and str(NOW.date()) > str(c["ends"]): why = f"ended {c['ends']}"
        url = c.get("url") or ""
        if not why and "contentrewards.com/c/campaigns/" in url:
            try:
                text = page_text(url)
                left = re.search(r"\$\s*([\d,]+)\s*remaining", text)
                log(f"{cid}: page: " + (f"${left.group(1)} remaining" if left else "no budget figure found") + f"; {text[:90]}")
                if re.search(r"no longer accepting|campaign (has )?ended|campaign is full|not accepting (clips|submissions)", text, re.I): why = "the page says it is full or ended"
                elif left and int(left.group(1).replace(",", "")) < int(CFG.get("clips_budget_floor", 50)): why = f"budget nearly spent (${left.group(1)} left)"
                if left: c["budget_left"] = int(left.group(1).replace(",", "")); changed = True
            except Exception as e:
                log(f"{cid}: page check failed: {type(e).__name__}: {str(e)[:120]}")
        if why:
            c["active"] = False; c["why_off"] = f"Switched off {NOW.date()}: {why}."; c["off_since"] = str(NOW.date()); changed = True
            log(f"{cid}: switched off ({why})")
    if changed:
        (ROOT / "clips" / "campaigns.json").write_text(json.dumps(CFG, indent=1, ensure_ascii=False) + "\n")
    return changed


def submissions(dry=False):
    """Every public link into its campaign by GitHub (pipeline/submit.py), after the posts and comments of a batch run."""
    try:
        import submit
        submit.run(dry=dry)
    except Exception as e: log("submit:", f"{type(e).__name__}: {str(e)[:200]}")


def main(argv):
    cmd = argv[0] if argv else "run"
    ids = argv[1:]
    if cmd == "stats":
        stats()
        try: engage()
        except Exception as e: log("engage:", str(e)[:200])
        submissions()
        return
    if cmd == "social":
        social_posts(force=bool(os.environ.get("CLIPS_SOCIAL_NOW")))
        try: engage()
        except Exception as e: log("engage:", str(e)[:200])
        submissions()
        return
    if cmd == "submit":
        submissions(dry=bool(os.environ.get("SUBMIT_DRY")))
        return
    if cmd == "probe":
        for u in ids: probe(u)
        return
    count = int(os.environ["CLIPS_COUNT"]) if os.environ.get("CLIPS_COUNT", "").strip().isdigit() else None
    deadline = time.time() + 60 * float(os.environ.get("CLIPS_MINUTES") or 110)      # the job stops at 150: save what is made
    cs = campaigns()
    if cmd in ("run", "prepare"):
        try: check_campaigns()
        except Exception as e: log("campaign check:", str(e)[:200])
        cs = campaigns()
    if cmd == "run":
        try: review()
        except Exception as e: log("review:", str(e)[:200])
        private = os.environ.get("CLIPS_MODE", "").strip() == "private"       # a test never counts against the day
        shares = {}                                                            # {channel: {campaign: n}}: each channel has its own number and ceiling
        for channel, ids_on in channels().items():
            done_today = scheduled_today(channel)
            ceiling_learn(done_today, channel=channel)
            got = allocate((count or 1) * len(ids_on) if private else max(0, daily_limit(channel) - done_today), count, channel)
            if got: shares[channel] = got
        want = {}
        for channel, got in shares.items():
            for cid, n in got.items(): want[cid] = want.get(cid, 0) + n
        log("today's shares:", json.dumps(shares if len(shares) > 1 else want))
        if not want: log("the day's number is already scheduled"); return
    for cid in (ids or list(cs)):
        if cid not in cs: log(f"{cid}: not an active campaign"); continue
        if cmd == "run" and not want.get(cid): continue
        if time.time() > deadline: log(f"{cid}: out of time this run, next run continues"); break
        try:
            if cmd in ("run", "prepare", "source"): source(cid)
            n = want.get(cid, count or cs[cid].get("per_day", 3)) if cmd == "run" else (count or cs[cid].get("per_day", 3))
            planner = plan_parts if (cs[cid].get("rules") or {}).get("series") else plan
            if cmd in ("plan", "prepare") or (cmd == "run" and unmade(cid) < n): planner(cid)
            if cmd == "run":
                for channel, got in shares.items():                              # the campaign's moments, shared out by channel
                    if got.get(cid): make(cid, got[cid], channel)
            elif cmd == "make": make(cid, n)
            if cmd in ("run", "upload"): upload(cid)
        except Exception as e:
            log(f"{cid}: {type(e).__name__}: {str(e)[:300]}")
    if cmd == "run":
        try: stats()
        except Exception as e: log("stats:", str(e)[:200])


if __name__ == "__main__":
    main(sys.argv[1:])
