"""Sunday's long video: the week's best Shorts in one landscape video with chapters.

Picks up to 15 Shorts that went public in the last 6 days, most viewed first (at least 6, otherwise it waits for next
week), takes each one's rendered video from its render artifact (GitHub keeps them 7 days), sets it in a 1920x1080
frame (the Short in the middle over a blurred copy, its chapter title on the left, the channel on the right), adds a
title card and an end card, and uploads it scheduled for Sunday 19:00 UK with chapters, links to the Shorts and every
image credit. Long videos build watch hours and subscribers, which the Shorts views don't.

Wednesday's long video is the explainer (pipeline/explainer.py, the same workflow): both write status/weekly-<date>.json, this
one with kind "compilation" and the explainer with kind "explainer". weekly.py also supplies the explainer's cards and fonts.
The compilation's description points to the latest explainer, and every Short links the latest long video (explainer.link_lines).

  python pipeline/weekly.py                    runs in GitHub (weekly.yml); result in status/weekly-<date>.json
  python pipeline/weekly.py --dry --ids A,B,C  builds from the given Shorts and saves the video as a draft release
                                               (weekly-test) instead of uploading
"""
import argparse, csv, datetime as dt, io, json, os, pathlib, re, subprocess, sys, tempfile, textwrap, zipfile
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
REPO = os.environ.get("GITHUB_REPOSITORY", "quickplay-studio/quickplay-autopilot")
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
W, H, FPS = 1920, 1080, 25
FIRST = dt.date(2026, 10, 25)          # the first Sunday after a full week of daily Shorts
INK, ACCENT, WHITE, MUTED = (15, 23, 32), (46, 230, 197), (245, 248, 250), (159, 176, 194)
FONTS = {"display": "https://raw.githubusercontent.com/google/fonts/main/ofl/archivoblack/ArchivoBlack-Regular.ttf",
         "body": "https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"}

def gh_json(path):
    return json.loads(subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout)

def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True)

def duration(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout)

def stamp(s):
    s = int(s); return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"

def fonts(work):
    import requests
    from PIL import ImageFont
    out = {}
    for k, url in FONTS.items():
        p = work / f"{k}.ttf"
        try:
            if not p.exists(): p.write_bytes(requests.get(url, timeout=60).content)
            ImageFont.truetype(str(p), 20); out[k] = str(p)
        except Exception:
            out[k] = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    return out

def font(fp, size):
    from PIL import ImageFont
    return ImageFont.truetype(fp, size)

def wrap(draw, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= width or not cur: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def clean_title(t):
    return re.sub(r"[^\w\s'’:,.!?&%£$€-]+$", "", t or "").strip()

def picks(ids=None):
    """[(short id, title, youtube id)] most viewed first."""
    rows = list(csv.DictReader(io.StringIO((ROOT / "analytics" / "shorts.csv").read_text())))
    if ids:
        byid = {r["short"]: r for r in rows}
        out = []
        for sid in ids:
            st = json.loads((ROOT / "status" / f"{sid}.json").read_text()) if (ROOT / "status" / f"{sid}.json").exists() else {}
            r = byid.get(sid, {})
            out.append((sid, r.get("title") or st.get("title") or sid, r.get("youtube_url", "").rsplit("/", 1)[-1] or st.get("video", "")))
        return out
    fresh = []
    for r in rows:
        try: posted = dt.datetime.fromisoformat(r["posted"])
        except (KeyError, ValueError): continue
        if r.get("short", "").startswith("QD-") and NOW - posted <= dt.timedelta(days=6):
            fresh.append((int(r.get("yt_views") or 0), r))
    fresh.sort(key=lambda x: -x[0])
    return [(r["short"], r["title"], r["youtube_url"].rsplit("/", 1)[-1]) for _, r in fresh[:15]]

def fetch(sid, work):
    """The Short's rendered video and upload details from its newest render artifact."""
    arts = [a for a in gh_json(f"repos/{REPO}/actions/artifacts?name=result-{sid}&per_page=10").get("artifacts", []) if not a.get("expired")]
    if not arts: return None
    a = max(arts, key=lambda a: a["created_at"])
    z = work / f"{sid}.zip"
    with open(z, "wb") as f:
        subprocess.run(["gh", "api", f"repos/{REPO}/actions/artifacts/{a['id']}/zip"], stdout=f, check=True)
    d = work / sid; d.mkdir(exist_ok=True)
    with zipfile.ZipFile(z) as zf: zf.extractall(d)
    vid = d / "video.mp4" if (d / "video.mp4").exists() else (d / "preview.mp4" if (d / "preview.mp4").exists() else None)
    up = json.loads((d / "upload.json").read_text()) if (d / "upload.json").exists() else {}
    return (vid, up) if vid else None

def side_overlay(path, n, total, title, fp):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    left = 656 - 2 * 48            # the Short sits in the middle 608 px
    d.text((64, 300), f"{n} OF {total}", font=font(fp["body"], 34), fill=ACCENT + (255,))
    f = font(fp["display"], 60); y = 360
    for line in wrap(d, clean_title(title).upper(), f, left)[:5]:
        d.text((64, y), line, font=f, fill=WHITE + (255,)); y += 72
    d.text((1320, 960), "@quickplaydaily", font=font(fp["body"], 34), fill=WHITE + (220,))
    im.save(path)

def card(path, big, small, fp, lines=(), fit=False):
    """A title card. fit (the explainer's chapter cards): the title shrinks from 120 to 64 points until it fits three lines, so a
    long chapter title is never cut off; otherwise two lines at 120 points, as the weekly video has always had."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
    d.ellipse([-300, -200, 700, 800], fill=(22, 60, 62)); d.ellipse([1300, 500, 2200, 1400], fill=(40, 34, 24))
    size, rows = 120, 2
    if fit:
        rows = 3
        while size > 64 and len(wrap(d, big.upper(), font(fp["display"], size), 1600)) > rows: size -= 8
    f = font(fp["display"], size); y = 300 if not fit else 270
    for line in wrap(d, big.upper(), f, 1600)[:rows]:
        d.text(((W - d.textlength(line, font=f)) / 2, y), line, font=f, fill=WHITE); y += int(size * 1.17)
    fs = font(fp["body"], 46)
    d.text(((W - d.textlength(small, font=fs)) / 2, y + 30), small, font=fs, fill=ACCENT)
    fl = font(fp["body"], 34); y += 130
    for line in lines[:5]:
        d.text(((W - d.textlength(line, font=fl)) / 2, y), line, font=fl, fill=MUTED); y += 50
    im.save(path)
    return path

def segment(src, overlay, out):
    run("ffmpeg", "-y", "-v", "error", "-i", src, "-i", overlay, "-filter_complex",
        "[0:v]split=2[a][b];[a]scale=1920:-2,crop=1920:1080,boxblur=28:2,eq=brightness=-0.14:saturation=0.85[bg];"
        "[b]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0[m];[m][1:v]overlay=0:0,fps=25,format=yuv420p[v];"
        "[0:a]aresample=48000,aformat=channel_layouts=stereo[aa]",
        "-map", "[v]", "-map", "[aa]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", out)

def still(png, secs, out):
    run("ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", secs, "-i", png, "-f", "lavfi", "-t", secs,
        "-i", "anullsrc=r=48000:cl=stereo", "-vf", "fps=25,fade=in:0:8,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-shortest", out)

def credits(up):
    """Image credits and music lines from a Short's upload description."""
    lines, sec, vis, music = (up.get("description") or "").splitlines(), None, [], []
    for ln in lines:
        s = ln.strip()
        if s.endswith(":") and s[:-1] in ("Sources", "Visuals"): sec = s[:-1]; continue
        if not s: sec = None; continue
        if s.startswith("Music:"): music.append(s); continue
        if sec == "Visuals": vis.append(s)
    return vis, music

def subject(sid, title):
    """A short name for the title: the board's first hashtag (#TaylorSwift -> Taylor Swift), else the title's opening words."""
    for d in ("done", "ready", "queue", "hold", "test"):
        bp = ROOT / "boards" / d / f"{sid}.json"
        if bp.exists():
            tags = (json.loads(bp.read_text()).get("meta") or {}).get("hashtags") or []
            if tags: return re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z][a-z])", " ", tags[0].lstrip("#"))[:28]
    t = clean_title(title)
    return " ".join(re.split(r"[:,!?]| is | has | just | was ", t, maxsplit=1)[0].split()[:3])[:28]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true"); ap.add_argument("--ids", default="")
    a = ap.parse_args()
    today = NOW.astimezone(UK).date()
    sp = ROOT / "status" / f"weekly-{today}.json"
    st = json.loads(sp.read_text()) if sp.exists() else {}
    if st.get("video") and not a.dry:
        print("already uploaded:", st["video"]); return
    if today < FIRST and not a.dry:
        print(f"the first weekly video is on {FIRST:%A %d %B}, after a full week of daily Shorts"); return
    chosen = picks([x for x in a.ids.split(",") if x] or None)
    if len(chosen) < (1 if a.dry else 6):
        st.update(state="skipped", reason=f"only {len(chosen)} Shorts public in the last 6 days", at=NOW.isoformat(timespec="minutes"))
        if not a.dry: sp.write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(st["reason"]); return
    work = pathlib.Path(tempfile.mkdtemp()); fp = fonts(work)
    segs, chapters, vis_all, music_all, used, t = [], [], [], [], [], 0.0
    got = [(sid, title, yid, fetch(sid, work)) for sid, title, yid in chosen]
    got = [g for g in got if g[3]]
    if len(got) < (1 if a.dry else 6):
        st.update(state="skipped", reason=f"only {len(got)} of {len(chosen)} Shorts still have their render files", at=NOW.isoformat(timespec="minutes"))
        if not a.dry: sp.write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(st["reason"]); return
    start = today - dt.timedelta(days=6)
    intro_png, intro = work / "intro.png", work / "intro.mp4"
    card(intro_png, "This week in trends", f"{len(got)} stories · {start.day} to {today.day} {today:%B}", fp,
         [clean_title(g[1]) for g in got[:3]])
    still(intro_png, "2.5", intro); segs.append(intro); t += duration(intro)
    for i, (sid, title, yid, (vid, up)) in enumerate(got, 1):
        ov, out = work / f"ov{i}.png", work / f"seg{i:02d}.mp4"
        side_overlay(ov, i, len(got), title, fp); segment(vid, ov, out)
        chapters.append((0.0 if i == 1 else t, clean_title(title))); t += duration(out); segs.append(out); used.append(sid)
        v, m = credits(up)
        vis_all += [x for x in v if x not in vis_all]; music_all += [x for x in m if x not in music_all]
    end_png, end = work / "end.png", work / "end.mp4"
    card(end_png, "New Shorts every day", "Subscribe to Quickplay Daily", fp)
    still(end_png, "5", end); segs.append(end)
    lst = work / "list.txt"; lst.write_text("".join(f"file '{p}'\n" for p in segs))
    final = work / "weekly.mp4"
    run("ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", final)
    names = []
    for sid, title, _, _ in got:
        s = subject(sid, title)
        if s and s.lower() not in [n.lower() for n in names]: names.append(s)
    title = f"This Week in Trends: {', '.join(names[:2])} and {names[2]}" if len(names) >= 3 else "This Week in Trends"
    while len(title) > 95 and len(names) > 2: names = names[:2]; title = f"This Week in Trends: {names[0]}, {names[1]} and More"
    desc = [f"The {len(got)} stories people searched for most this week, in one video. Every fact in these Shorts was checked "
            "against at least two reputable sources (listed under each Short).", "", "Chapters"]
    desc += [f"{stamp(c)} {n}" for c, n in chapters]
    links = [f"{clean_title(g[1])}: https://youtube.com/shorts/{g[2]}" for g in got if g[2]]
    if links: desc += ["", "The Shorts"] + links
    if vis_all: desc += ["", "Visuals"] + vis_all
    if music_all: desc += [""] + music_all
    try:                                   # the week's explainer, when there is one: the other long video links back
        import explainer
        ex = [v for v in explainer.long_videos().values() if v["kind"] == "explainer" and v["publish_at"] and v["publish_at"] <= NOW]
        if ex:
            v = max(ex, key=lambda v: v["publish_at"])
            desc[1:1] = ["", f"This week's biggest stories, explained: {v['title']} https://youtu.be/{v['id']}"]
    except Exception as e: print("explainer link skipped:", str(e)[:100])
    desc += ["", "Independent channel, not affiliated with the companies or people featured.", "", "#QuickplayDaily #Trending"]
    text = "\n".join(desc)
    if len(text) > 4900:                    # keep chapters and credits; drop the Short links first
        desc = [x for x in desc if "youtube.com/shorts/" not in x and x != "The Shorts"]; text = "\n".join(desc)[:4900]
    st.update(kind="compilation", state="built", shorts=used, title=title, chapters=[[stamp(c), n] for c, n in chapters], seconds=round(duration(final)),
              at=NOW.isoformat(timespec="minutes"))
    if a.dry:
        tag = "weekly-test"
        subprocess.run(["gh", "release", "delete", tag, "-y", "--cleanup-tag", "-R", REPO], capture_output=True)
        run("gh", "release", "create", tag, final, "--draft", "--title", tag, "--notes", text[:2000], "-R", REPO)
        print(json.dumps(st, indent=1)); return
    import youtube as Y
    if not Y.available(): raise SystemExit("YouTube secrets missing")
    yt = Y.client()
    pub = dt.datetime.combine(today, dt.time(19, 0), tzinfo=UK).astimezone(dt.timezone.utc)
    if pub < NOW + dt.timedelta(minutes=45): pub = (NOW + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    tags = ["this week in trends", "trending this week", "weekly recap"] + [n.lower() for n in names[:8]]
    try:
        vid = Y.upload(yt, final, title, text, tags, "Entertainment", pub.isoformat().replace("+00:00", "Z"))
    except Y.LimitReached as e:
        st.update(state="waiting: upload limit", error=str(e)[:200]); sp.write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print("upload limit reached, will retry"); return
    st.update(state="scheduled", video=vid, publish_at=pub.isoformat(timespec="minutes"), url=f"https://youtu.be/{vid}")
    try:                                   # a custom thumbnail needs a verified channel; fine if refused
        from PIL import Image
        from googleapiclient.http import MediaFileUpload
        thumb = work / "thumb.jpg"; Image.open(intro_png).convert("RGB").resize((1280, 720)).save(thumb, quality=90)
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
    except Exception as e: st["thumbnail_error"] = f"{type(e).__name__}: {e}"[:200]
    sp.write_text(json.dumps(st, indent=1, ensure_ascii=False)); print(json.dumps(st, indent=1))

if __name__ == "__main__":
    main()
