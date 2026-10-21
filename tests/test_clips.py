"""Offline test of the clips line (pipeline/clips.py): campaign loading, text wrapping, captions, the batch time, moment
planning with a stubbed model, and (when ffmpeg is here) one synthetic render."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import csv, datetime as dt, json, os, pathlib, shutil, subprocess, sys
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
assert ids == ["speed-expedia-01", "speed-expedia-02", "speed-expedia-03"], ids
assert plan["moments"][0]["start"] == 9.7 and plan["moments"][0]["end"] == 40.4 and plan["moments"][2]["label"] == "Paris, France"
assert plan["moments"][1]["end"] - plan["moments"][1]["start"] == 55      # a long pick is cut to the limit
assert C.unmade("speed-expedia") == 3
plan2 = C.plan("speed-expedia")                       # the same answer again: everything overlaps what is planned
assert len(plan2["moments"]) == 3
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

# 7. parts planner: whole episodes in order, split at sentence ends, never past max_s
C.PLANS = pathlib.Path(SCRATCH) / "plans2"; C.PLANS.mkdir()
ep_words = []
for i in range(0, 130):      # 130 seconds of speech, a sentence end every 10 s
    ep_words.append({"w": "word" + ("." if i % 10 == 9 else ""), "s": float(i), "e": i + 0.8})
C.transcribe = lambda cid: ep_words
C.CFG["campaigns"]["series-test"] = {"active": True, "subject": "Drama", "name": "t", "url": "x", "source": {"kind": "url", "url": "x", "multi": True, "label": "l"},
                                     "rules": {"focus": "f", "on_screen": "o", "hashtags": ["#a"], "min_s": 15, "max_s": 55, "series": "parts"}}
(C.PLANS / "series-test.json").write_text(json.dumps({"moments": [], "episodes": [{"n": 1, "start": 0.0, "end": 70.0}, {"n": 2, "start": 70.0, "end": 130.0}]}))
pl = C.plan_parts("series-test")
ms = pl["moments"]
assert [m["id"] for m in ms] == ["series-test-e01p1", "series-test-e01p2", "series-test-e02p1", "series-test-e02p2"], [m["id"] for m in ms]
assert all(m["end"] - m["start"] <= 56 for m in ms) and ms[0]["end"] == ms[1]["start"] and ms[1]["end"] == 70.0 and ms[3]["end"] == 130.0
assert ms[0]["hook"] == "EPISODE 1, PART 1 OF 2" and ms[2]["of"] == 2
print("7 parts ok")

# 8. the clips channel's ceiling: rises after a full day, settles on a refusal
C.STATE = pathlib.Path(SCRATCH) / "state"; C.CEILING = C.STATE / "ceiling.json"
base = int(C.CFG.get("daily_clips", 10))
assert C.daily_limit() == base and C.ceiling_learn(base - 1) == base and C.ceiling_learn(base) == base + 2
assert C.ceiling_learn(base + 2) == base + 2                           # raised today: waits
assert C.ceiling_learn(7, refused=True) == 7 and C.daily_limit() == 7
print("8 ceiling ok")

# 9. campaigns switch off on their end date or a spent page
C.NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
import requests as RQ
class Resp:
    def __init__(self, text): self.text = text
RQ.get = lambda url, **kw: Resp("<div>Budget</div><span>$9,331 / $9,750</span><span>$41</span> remaining <p>Accepting clips</p>")
C.CFG["campaigns"] = {"a": {"active": True, "ends": "2026-11-02", "url": "x"}, "b": {"active": True, "url": "https://contentrewards.com/c/campaigns/zz"},
                      "c": {"active": True, "ends": "2026-12-01", "url": "x"}}
orig_write = pathlib.Path.write_text
C.ROOT = pathlib.Path(SCRATCH); (C.ROOT / "clips").mkdir()
assert C.check_campaigns() is True
assert not C.CFG["campaigns"]["a"]["active"] and "ended" in C.CFG["campaigns"]["a"]["why_off"]
assert not C.CFG["campaigns"]["b"]["active"] and "budget" in C.CFG["campaigns"]["b"]["why_off"] and C.CFG["campaigns"]["b"]["budget_left"] == 41
assert C.CFG["campaigns"]["c"]["active"]
print("9 switch-off ok")
print("clips extras ok")

# 10. layouts, karaoke captions, tests, submit rows, insights
C.CFG["campaigns"] = json.loads(pathlib.Path(REPO_DIR + "/clips/campaigns.json").read_text())["campaigns"]
g, lay = C.layout_filters("face", (0.5, 0.3, 0.1, 0.15)); assert lay == "face" and "crop=w=ih*9/16" in g
g, lay = C.layout_filters("split", (0.5, 0.3, 0.1, 0.15)); assert lay == "split" and "overlay=0:1080" in g
g, lay = C.layout_filters("split", None); assert lay == "letterbox"
tp = C.test_plan("x-01"); assert set(tp) == set(C.TESTS) and all(tp[t] in C.TESTS[t] for t in tp)
C.captions(words, 9.0, 18.0, ass, "karaoke", 500)
k = ass.read_text(); assert "\\k" in k and "MarginV" in k and ",500,1" in k
rw = C.submit_row("speed-expedia", C.CFG["campaigns"]["speed-expedia"], {"id": "s-1", "title": "t"}, "instagram", "https://instagram.com/p/x", "2026-10-22")
assert rw["platform"] == "instagram" and rw["campaign_url"].startswith("https://contentrewards.com") and rw["hashtags"] == "#IShowSpeed #Expedia"
C.ROOT = pathlib.Path(SCRATCH); (C.ROOT / "clips").mkdir(exist_ok=True)
(C.ROOT / "clips" / "submit.csv").write_text("clip,campaign,campaign_url,video,public_at_uk,title,hashtags,submitted\na,c,u,v,2026-10-21 18:00,t,#h,\n")
C.add_rows([rw]); rows = list(csv.DictReader((C.ROOT / "clips" / "submit.csv").open()))
assert rows[0]["platform"] == "youtube" and rows[1]["platform"] == "instagram" and rows[1]["video"] == "https://instagram.com/p/x", rows
stat_rows = [{"campaign": "a", "privacy": "public", "hours_public": 30, "views": v, "test_layout": l, "test_captions": "lines", "test_punch": "none"}
             for v, l in ((100, "face"), (120, "face"), (140, "face"), (50, "letterbox"), (60, "letterbox"), (40, "letterbox"))]
ins = C.insights(stat_rows)
assert ins["tests"]["layout"]["best"] == "face" and ins["tests"]["captions"]["best"] == "lines" and ins["campaigns"]["a"]["n"] == 6, ins["tests"]
print("10 layouts, captions, rows, insights ok")
print("clips extras 2 ok")
