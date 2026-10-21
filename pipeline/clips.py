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
- Each clip runs {min_s} to {max_s} seconds, starts at a natural moment (a question, a reveal, a reaction) and ends on
  the payoff (the reaction, the punchline, the reveal), never mid-sentence.
Pick up to {n} moments, best first: the funniest reactions, the biggest reveals, the lines people quote. Spread them
across the segment; no two may overlap. Already made (skip anything that overlaps these): {done}.
The transcript is a list of lines with their start and end seconds:
{lines}
Return {{"moments": [{{"start": seconds, "end": seconds, "hook": "on-screen line, 8 words or fewer, in capitals OK, what
makes someone stop (no spoilers of the payoff)", "label": "1 to 4 words to show on screen only when the rules above ask for a name (a destination, a person); otherwise empty", "title": "YouTube title under 60 characters, starts with {subject}, plain and searchable, no clickbait",
"why": "one line"}}]}}"""


def log(*a): print(*a, flush=True)


PROFANE = re.compile(r"\b(f+u+c+k+\w*|f\*+\w*|s+h+i+t+\w*|s\*+t\w*|b+i+t+c+h+\w*|a+s+s+h+o+l+e+\w*|d+i+c+k+s?|p+u+s+s+y|wtf|stfu|"
                     r"n+i+g+g+\w*|r+e+t+a+r+d+\w*|w+h+o+r+e+\w*|s+l+u+t+\w*|c+u+n+t+\w*|f+a+g+\w*)\b", re.I)


def profane(words, a, b):
    """The strong words heard between a and b (the channel is family-friendly and every campaign wants brand-safe)."""
    return PROFANE.findall(" ".join(w["w"] for w in words if a <= w["s"] <= b))


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


def plan(cid, n=8):
    """The moments worth a clip, from the transcript, checked against the rules' lengths; appended to clips/plans/<id>.json."""
    import factpack
    c = campaigns([cid])[cid]; r = c["rules"]
    words = transcribe(cid)
    if not words: raise RuntimeError(f"{cid}: no speech found in the segment")
    p = PLANS / f"{cid}.json"
    plan_ = json.loads(p.read_text()) if p.exists() else {"moments": []}
    done = [(m["start"], m["end"]) for m in plan_["moments"]]
    prompt = PLAN_PROMPT.format(label=c["source"].get("label", cid), focus=r["focus"], on_screen=r["on_screen"],
                                avoid="; ".join(r.get("avoid") or []), min_s=r.get("min_s", 15), max_s=r.get("max_s", 55), n=n,
                                subject=c["subject"], done=", ".join(f"{a:.0f}-{b:.0f}s" for a, b in done) or "none",
                                lines="\n".join(lines_of(words)))
    ans, model = factpack.gemini(prompt, None, timeout=150, temperature=0.4)
    total = words[-1]["e"]
    added, why = 0, {"bad time": 0, "length": 0, "overlap": 0, "no hook": 0}
    if isinstance(ans, list): ans = next((x for x in ans if isinstance(x, dict) and x.get("moments")), {"moments": [x for x in ans if isinstance(x, dict) and "start" in x]})
    raw = (ans.get("moments") if isinstance(ans, dict) else None) or []
    if not raw: log(f"{cid}: the model gave no moments: {json.dumps(ans)[:300]}")
    for m in raw:
        try:
            a, b = (secs(m["start"]) if ":" in str(m["start"]) else float(m["start"])), (secs(m["end"]) if ":" in str(m["end"]) else float(m["end"]))
        except (KeyError, TypeError, ValueError): why["bad time"] += 1; continue
        a, b = max(0.0, a - 0.3), min(total, b + 0.4)      # a breath before, the reaction after
        if b - a > r.get("max_s", 55) + 1: b = a + r.get("max_s", 55)      # a long pick is cut to the limit, the payoff is usually early
        if not r.get("min_s", 15) <= b - a: why["length"] += 1; continue
        if any(a < y and b > x for x, y in done): why["overlap"] += 1; continue
        hook = re.sub(r"[–—]", "-", str(m.get("hook") or "")).strip()[:60]
        if not hook: why["no hook"] += 1; continue
        if profane(words, a, b) or PROFANE.search(hook): why["profanity"] = why.get("profanity", 0) + 1; continue
        plan_["moments"].append({"id": f"{cid}-{len(plan_['moments']) + 1:02d}", "start": round(a, 2), "end": round(b, 2),
                                 "hook": hook, "label": str(m.get("label") or "").strip()[:40],
                                 "title": re.sub(r"[–—]", "-", str(m.get("title") or f"{c['subject']}: {hook}")).strip()[:70],
                                 "why": str(m.get("why") or "")[:200], "planned": NOW.isoformat(timespec="minutes"), "model": model})
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


def captions(words, a, b, path):
    """Captions as an ASS file: three or four words at a time, big and bold, below the picture."""
    sel = [w for w in words if w["s"] >= a - 0.2 and w["e"] <= b + 0.2]
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,DejaVu Sans,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,430,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev, group = [], []
    for w in sel:
        group.append(w)
        if len(group) >= 4 or w["w"].endswith((".", "?", "!", ",")) and len(group) >= 2:
            ev.append(group); group = []
    if group: ev.append(group)
    lines = []
    for i, g in enumerate(ev):
        s = g[0]["s"] - a; e = (ev[i + 1][0]["s"] if i + 1 < len(ev) else g[-1]["e"] + 0.6) - a
        text = ass_escape(" ".join(x["w"] for x in g).upper())
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(min(e, b - a))},Cap,,0,0,0,,{text}")
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


def make_clip(cid, m, words):
    """One 1080x1920 clip: the landscape picture in the middle over its own blurred copy, the hook at the top, the
    destination label under it, captions below the picture, the credit at the bottom, loudness normalised."""
    c = campaigns([cid])[cid]
    OUT.mkdir(parents=True, exist_ok=True)
    seg, out = segment(cid), OUT / f"{m['id']}.mp4"
    a, b = m["start"], m["end"]
    ass = WORK / f"{m['id']}.ass"; captions(words, a, b, ass)
    credit = f"Clip from {c['subject']}, posted with permission"
    vf = ("[0:v]split=2[bg][fg];"
          "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:3,eq=brightness=-0.15[bgb];"
          "[fg]scale=1080:-2[fgs];[bgb][fgs]overlay=0:(H-h)/2[v1];"
          f"[v1]{drawtext(m['hook'].upper(), 62, 250)}[v2];"
          + (f"[v2]{drawtext(m['label'], 44, 440, 'yellow')}[v3];" if m.get("label") else "[v2]null[v3];")
          + f"[v3]subtitles='{ass}'[v4];[v4]{drawtext(credit, 30, 1800, 'white', False)}[v]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(seg),
           "-filter_complex", vf, "-map", "[v]", "-map", "0:a", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-r", "30",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", str(out)]
    run(cmd)
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


def make(cid, count=None):
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
        try:
            out = make_clip(cid, m, words)
            f = frame_of(out, m)
            if dark(f):             # a black screen (an outage, a loading screen): not a clip
                m["skipped"] = "dark picture"; out.unlink(missing_ok=True); log(f"{m['id']}: skipped: dark picture"); continue
            m["made"] = NOW.isoformat(timespec="minutes"); m["file"] = out.name; made.append(m)
            log(f"{m['id']}: made ({m['end'] - m['start']:.0f} s) {m['title']}")
        except Exception as e:
            m["skipped"] = f"{type(e).__name__}: {e}"[:200]; log(f"{m['id']}: skipped: {m['skipped']}")
    plan_p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    return made


# ----- uploading ------------------------------------------------------------------------------------------------------------
def clips_client():
    """A YouTube client for Quickplay Clips (tokens/youtube_clips.enc, the social workflow's sign-in)."""
    import social
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    t = social.load("youtube_clips")
    if not t.get("refresh_token"): raise RuntimeError("the clips channel is not signed in (social workflow, channel clips)")
    creds = Credentials(None, refresh_token=t["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=(t.get("scope") or "").split())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def batch_time():
    """The next batch publish time (UK batch_time today, or tomorrow once it is under an hour away) as RFC3339 UTC."""
    h, mi = map(int, str(CFG.get("batch_time", "18:00")).split(":"))
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
    yt = clips_client()
    mode = mode or os.environ.get("CLIPS_MODE", "").strip() or "batch"
    publish_at, when = (None, None) if mode == "private" else batch_time()
    rows, p = [], ROOT / "clips" / "submit.csv"
    for m in todo:
        tags = [t.lstrip("#") for t in r.get("hashtags") or []] + [c["subject"]]
        desc = (f"{m['hook'].capitalize()}. {r.get('description', '')}".strip() + "\n\n" + "\n".join(r.get("hashtags") or []) + "\n\n"
                f"Clip from {c['source'].get('label', '')}, posted with the creator's permission ({c['name']}).")
        try:
            vid = Y.upload(yt, OUT / m["file"], m["title"], desc, tags, "Entertainment", publish_at)
        except Exception as e:
            log(f"{m['id']}: upload failed: {type(e).__name__}: {str(e)[:200]}")
            if "uploadLimitExceeded" in str(e): ceiling_learn(scheduled_today(), refused=True); break
            continue
        m.update(video=vid, url=f"https://youtube.com/shorts/{vid}", uploaded=NOW.isoformat(timespec="minutes"),
                 publish_at=publish_at or "private", mode=mode)
        where = re.search(r"https://[^\s,]+", str((c.get("submit") or {}).get("where", "")))
        rows.append({"clip": m["id"], "campaign": cid, "campaign_url": where.group(0) if where else c["url"], "video": m["url"],
                     "public_at_uk": when.strftime("%Y-%m-%d %H:%M") if when else "private (test)", "title": m["title"],
                     "hashtags": " ".join(r.get("hashtags") or []), "submitted": ""})
        log(f"{m['id']}: uploaded {m['url']} ({mode})")
    plan_p.write_text(json.dumps(plan_, indent=1, ensure_ascii=False))
    if rows:
        new = not p.exists()
        with p.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            if new: w.writeheader()
            w.writerows(rows)
    return rows


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
    yt = clips_client()
    rows = []
    ids = list(vids)
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics,status", id=",".join(ids[i:i + 50])).execute().get("items", []):
            cid, m = vids[v["id"]]; st = v.get("statistics", {})
            pub = v["status"].get("publishAt") or m.get("uploaded")
            try: hours = round((NOW - dt.datetime.fromisoformat(pub.replace("Z", "+00:00"))).total_seconds() / 3600, 1)
            except Exception: hours = ""
            rows.append({"clip": m["id"], "campaign": cid, "video": v["id"], "seconds": round(m["end"] - m["start"]),
                         "hook_words": len(m["hook"].split()), "hours_public": hours, "privacy": v["status"].get("privacyStatus"),
                         "views": st.get("viewCount", 0), "likes": st.get("likeCount", 0), "comments": st.get("commentCount", 0),
                         "as_of": NOW.isoformat(timespec="minutes")})
    p = ROOT / "clips" / "stats.csv"
    if not rows: return
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    log(f"stats: {len(rows)} clips")


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


def daily_limit():
    """Clips a day: the learned ceiling (clips/state/ceiling.json) when there is one, else campaigns.json daily_clips."""
    base = int(CFG.get("daily_clips", 10))
    try: return max(1, int(json.loads(CEILING.read_text()).get("limit") or base))
    except Exception: return base


def ceiling_learn(scheduled, refused=False):
    """Like the main channel's quota.learn: a refusal (uploadLimitExceeded) settles the ceiling at what YouTube took;
    a filled day with no refusal in 48 hours and no rise in 24 hours lifts it by clips_limit_step, up to clips_limit_max."""
    try: st = json.loads(CEILING.read_text())
    except Exception: st = {}
    limit, now = daily_limit(), NOW.isoformat(timespec="minutes")
    def age(k):
        try: return (NOW - dt.datetime.fromisoformat(st[k])).total_seconds() / 3600
        except (KeyError, ValueError, TypeError): return 1e9
    STATE.mkdir(parents=True, exist_ok=True)
    if refused:
        new = max(int(CFG.get("clips_limit_min", 4)), int(scheduled))
        st.update(limit=new, refused_at=now, refused_with=int(scheduled)); CEILING.write_text(json.dumps(st, indent=1))
        log(f"ceiling: YouTube refused an upload with {scheduled} today, the clips channel's limit is now {new}"); return new
    top, step = int(CFG.get("clips_limit_max", 30)), int(CFG.get("clips_limit_step", 2))
    if limit >= top or age("refused_at") < 48 or age("raised_at") < 24 or int(scheduled) < limit: return limit
    new = min(top, limit + step)
    st.update(limit=new, raised_at=now, raised_with=int(scheduled)); CEILING.write_text(json.dumps(st, indent=1))
    log(f"ceiling: a full day with no refusal, the clips channel's limit rises {limit} to {new}"); return new


def median_views(cid):
    """Median views of the campaign's public clips so far (clips/stats.csv), None until it has 3."""
    p = ROOT / "clips" / "stats.csv"
    if not p.exists(): return None
    vals = [float(r["views"] or 0) for r in csv.DictReader(p.open()) if r.get("campaign") == cid and r.get("privacy") == "public"
            and float(r.get("hours_public") or 0) >= 24]
    if len(vals) < 3: return None
    vals.sort(); return vals[len(vals) // 2]


def allocate(remaining, count=None):
    """How many clips each active campaign gets today: the day's remaining number shared by expected money (pay per
    1,000 times the campaign's median views, a 1,000-view prior until it has 3 measured clips, with a little noise so
    every campaign keeps being tried), each capped by its per_day. The data decides, like the main channel."""
    import random
    cs = campaigns()
    if not cs or remaining <= 0: return {}
    rng = random.Random(str(NOW.date()))
    score = {cid: c.get("pay_per_1k", 1.0) * (median_views(cid) or 1000.0) * rng.uniform(0.8, 1.25) for cid, c in cs.items()}
    order = sorted(cs, key=lambda cid: -score[cid])
    out, left = {}, remaining
    for cid in order:                                   # one each first, strongest first, then up to per_day
        cap = count if count is not None else int(cs[cid].get("per_day", 3))
        if left > 0 and cap > 0: out[cid] = 1; left -= 1
    for cid in order:
        cap = count if count is not None else int(cs[cid].get("per_day", 3))
        while left > 0 and out.get(cid, 0) < cap: out[cid] = out.get(cid, 0) + 1; left -= 1
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
            if not bad and dark(ROOT / "clips" / "frames" / f"{m['id']}.jpg"): bad = ["dark picture"]
            if due > NOW and bad:
                try:
                    for attempt in range(4):        # YouTube answers 503 now and then
                        try:
                            clips_client().videos().update(part="status", body={"id": m["video"], "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}).execute(); break
                        except Exception as e:
                            if attempt == 3 or "503" not in str(e): raise
                            time.sleep(15 * (attempt + 1))
                    m["pulled"] = ("dark picture" if bad == ["dark picture"] else f"profanity: {', '.join(bad[:3])}"); changed = True; pulled += 1
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


def scheduled_today():
    """Clips already uploaded for the next batch (so two runs in a day share the daily number)."""
    iso, _ = batch_time(); n = 0
    for p in PLANS.glob("*.json"):
        if p.name.endswith(".words.json"): continue
        n += sum(1 for m in json.loads(p.read_text()).get("moments") or [] if m.get("publish_at") == iso and not m.get("pulled"))
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


def main(argv):
    cmd = argv[0] if argv else "run"
    ids = argv[1:]
    if cmd == "stats": stats(); return
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
        done_today = scheduled_today()
        ceiling_learn(done_today)
        want = allocate(max(0, daily_limit() - done_today), count)
        log("today's shares:", json.dumps(want))
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
            if cmd in ("run", "make"): make(cid, n)
            if cmd in ("run", "upload"): upload(cid)
        except Exception as e:
            log(f"{cid}: {type(e).__name__}: {str(e)[:300]}")
    if cmd == "run":
        try: stats()
        except Exception as e: log("stats:", str(e)[:200])


if __name__ == "__main__":
    main(sys.argv[1:])
