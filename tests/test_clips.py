"""Offline test of the clips line (pipeline/clips.py): campaign loading, text wrapping, captions, the batch time, moment
planning with a stubbed model, and (when ffmpeg is here) one synthetic render."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import datetime as dt, json, os, pathlib, shutil, subprocess, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import clips as C

# 1. only active campaigns with rules and a source are used
cs = C.campaigns()
assert "speed-expedia" in cs and "forgegui-roblox" not in cs, list(cs)
assert cs["speed-expedia"]["rules"]["hashtags"] == ["#IShowSpeed", "#Expedia"]
assert C.secs("3:56:30") == 14190 and C.secs("90") == 90
print("1 campaigns ok")

# 2. wrapping and drawtext escaping
assert C.wrap("SPEED OPENS THE SUITCASE: IT'S TOKYO") == ["SPEED OPENS THE", "SUITCASE: IT'S TOKYO"]
assert len(C.wrap("one two three four five six seven eight nine ten eleven twelve", 10)) == 2
d = C.drawtext("50% off: it's here", 62, 250)
assert "50%% off\\: it’s here" in d and "fontsize=62" in d, d
print("2 wrap ok")

# 3. captions: groups of up to 4 words, times relative to the clip start, never past its end
words = [{"w": w, "s": 10 + i * 0.5, "e": 10.4 + i * 0.5} for i, w in enumerate("this is the moment speed opens the yellow suitcase and finds, a ticket".split())]
ass = pathlib.Path(SCRATCH) / "t.ass"; C.captions(words, 9.0, 18.0, ass)
lines = [l for l in ass.read_text().splitlines() if l.startswith("Dialogue:")]
assert lines and lines[0].endswith("THIS IS THE MOMENT") and "0:00:01.00" in lines[0], lines[0]
assert all(float(l.split(",")[2].split(":")[-1]) <= 9.0 for l in lines)
print("3 captions ok", len(lines), "lines")

# 4. the batch time: today's 18:00 UK unless that is under an hour away, then tomorrow's
C.NOW = dt.datetime(2026, 10, 21, 12, 0, tzinfo=dt.timezone.utc)
iso, when = C.batch_time()
assert when.strftime("%Y-%m-%d %H:%M") == "2026-10-21 18:00" and iso.endswith("Z"), (iso, when)
C.NOW = dt.datetime(2026, 10, 21, 16, 30, tzinfo=dt.timezone.utc)       # 17:30 UK
assert C.batch_time()[1].strftime("%Y-%m-%d %H:%M") == "2026-10-22 18:00"
print("4 batch time ok")

# 5. planning with a stubbed model: lengths checked, overlaps dropped, ids in order
C.PLANS = pathlib.Path(SCRATCH) / "plans"
C.transcribe = lambda cid: [{"w": f"w{i}", "s": i * 1.0, "e": i * 1.0 + 0.5} for i in range(600)]
import factpack
factpack.gemini = lambda prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None: ({"moments": [
    {"start": 10, "end": 40, "hook": "He opens it", "label": "Tokyo", "title": "IShowSpeed finds Tokyo"},
    {"start": 30, "end": 60, "hook": "overlaps the first", "label": "", "title": "x"},
    {"start": 100, "end": 104, "hook": "too short", "title": "x"},
    {"start": 200, "end": 300, "hook": "too long", "title": "x"},
    {"start": 400, "end": 440, "hook": "the second reveal", "label": "Paris, France", "title": "IShowSpeed and Paris"}]}, "stub")
plan = C.plan("speed-expedia")
ids = [m["id"] for m in plan["moments"]]
assert ids == ["speed-expedia-01", "speed-expedia-02"], ids
assert plan["moments"][0]["start"] == 9.7 and plan["moments"][0]["end"] == 40.4 and plan["moments"][1]["label"] == "Paris, France"
assert C.unmade("speed-expedia") == 2
plan2 = C.plan("speed-expedia")                       # the same answer again: everything overlaps what is planned
assert len(plan2["moments"]) == 2
print("5 planning ok")

# 6. one synthetic render, when ffmpeg is installed here
if shutil.which("ffmpeg") and C.FONT:
    C.WORK = pathlib.Path(SCRATCH); C.OUT = pathlib.Path(SCRATCH) / "out"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=12",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-shortest",
                    str(C.WORK / "speed-expedia.mp4")], check=True)
    C.transcribe = lambda cid: words
    m = {"id": "speed-expedia-01", "start": 1.0, "end": 7.0, "hook": "SPEED OPENS THE SUITCASE: it's Tokyo", "label": "Tokyo, Japan", "title": "t"}
    out = C.make_clip("speed-expedia", m, words)
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                          capture_output=True, text=True).stdout.strip()
    assert info == "1080,1920", info
    print("6 render ok", out.stat().st_size, "bytes")
else:
    print("6 render skipped (no ffmpeg or font here)")
print("clips ok")
