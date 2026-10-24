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

# 4. the batch time: today's 19:00 UK (campaigns.json batch_time) unless that is under an hour away, then tomorrow's
C.NOW = dt.datetime(2026, 10, 21, 12, 0, tzinfo=dt.timezone.utc)
iso, when = C.batch_time()
assert when.strftime("%Y-%m-%d %H:%M") == "2026-10-21 19:00" and iso.endswith("Z"), (iso, when)
C.NOW = dt.datetime(2026, 10, 21, 17, 30, tzinfo=dt.timezone.utc)       # 18:30 UK
assert C.batch_time()[1].strftime("%Y-%m-%d %H:%M") == "2026-10-22 19:00"
print("4 batch time ok")

# 5. planning with a stubbed model: lengths checked, overlaps dropped, ids in order
C.PLANS = pathlib.Path(SCRATCH) / "plans"
C.transcribe = lambda cid: [{"w": f"w{i}", "s": i * 1.0, "e": i * 1.0 + 0.5} for i in range(600)]
import factpack
PROMPTS = []
factpack.gemini = lambda prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None, writing=False: (PROMPTS.append((prompt, writing, lite)), {"moments": [
    {"start": 10, "end": 40, "hook": "He opens it", "label": "Tokyo", "title": "IShowSpeed finds Tokyo"},
    {"start": 30, "end": 60, "hook": "overlaps the first", "label": "", "title": "x"},
    {"start": 100, "end": 104, "hook": "too short", "title": "x"},
    {"start": 200, "end": 300, "hook": "too long", "title": "x"},
    {"start": 400, "end": 440, "hook": "the second reveal", "label": "Paris, France", "title": "IShowSpeed and Paris", "score": 9},
    {"start": 500, "end": 540, "hook": "a dull bit", "title": "x", "score": 3}]})[1:] + ("stub",)
plan = C.plan("speed-expedia")
ids = [m["id"] for m in plan["moments"]]
assert ids == ["speed-expedia-01", "speed-expedia-02", "speed-expedia-03"], ids
by = {m["hook"]: m for m in plan["moments"]}
assert plan["moments"][0]["hook"] == "the second reveal" and plan["moments"][0]["score"] == 9     # the likeliest hit first
assert by["He opens it"]["start"] == 9.7 and by["He opens it"]["end"] == 40.4 and by["the second reveal"]["label"] == "Paris, France"
assert by["too long"]["end"] - by["too long"]["start"] == 75      # a long pick is cut to the limit (75 s since 23 October)
assert "a dull bit" not in by and PROMPTS[-1][1:] == (True, True)  # a low virality score is dropped; strong free models, never Claude
assert C.unmade("speed-expedia") == 3
plan2 = C.plan("speed-expedia")                       # the same answer again: everything overlaps what is planned
assert len(plan2["moments"]) == 3
assert "(already clipped)" in PROMPTS[-1][0]      # taken lines are marked for the planner
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
    # our own take: spoken intro over the start (stream sound dipped), our reaction on a held last frame
    dur = lambda p: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                         capture_output=True, text=True).stdout)
    for name, secs in (("i.wav", 2.0), ("o.wav", 3.0)):
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}",
                        "-ar", "24000", "-ac", "1", str(C.WORK / name)], check=True)
    C.take_voice = lambda m, i, o: (C.WORK / "i.wav", C.WORK / "o.wav")
    m2 = dict(m, id="speed-expedia-02", take_intro="Watch what happens when he opens this", take_outro="Would you have picked Tokyo? Tell us below")
    os.environ.pop("CLIPS_TAKE", None)
    camp = C.CFG["campaigns"]["speed-expedia"]; avoid = list(camp["rules"].get("avoid") or [])
    camp["rules"]["avoid"] = [a for a in avoid if "AI" not in a]           # a campaign without the AI rule: spoken take
    out2 = C.make_clip("speed-expedia", m2, words)
    assert m2["tests"]["take"] == "voice" and abs(dur(out2) - (6.0 + 3.6)) < 0.6, (m2["tests"], dur(out2))
    camp["rules"]["avoid"] = avoid + ["AI-generated video"]                 # a campaign that avoids AI: text take only
    m3 = dict(m2, id="speed-expedia-03"); out3 = C.make_clip("speed-expedia", m3, words)
    assert m3["tests"]["take"] == "text" and abs(dur(out3) - 9.5) < 0.6, (m3["tests"], dur(out3))
    camp["rules"]["avoid"] = avoid
    print("6 take ok", round(dur(out2), 1), round(dur(out3), 1))
else:
    print("6 render skipped (no ffmpeg or font here)")
print("clips ok")

# 7. parts planner: whole episodes in order, split at sentence ends, never past max_s
C.PLANS = pathlib.Path(SCRATCH) / "plans2"; C.PLANS.mkdir(exist_ok=True)
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
step = int(C.CFG.get("clips_limit_step", 2))
assert C.daily_limit() == base and C.ceiling_learn(base - 1) == base and C.ceiling_learn(base) == base + step
assert C.ceiling_learn(base + step) == base + step                     # raised today: waits
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
g, lay = C.layout_filters("full", None); assert lay == "full" and "force_original_aspect_ratio=increase,crop=1080:1920:x=min(max(iw*0.500-540" in g
g, lay = C.layout_filters("full", (0.7, 0.1, 0.1, 0.15)); assert "iw*0.750-540" in g
C.captions(words, 9.0, 18.0, ass, "lines", 330, True); assert ",8,60,60,330,1" in ass.read_text()
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
             for v, l in ((100, "full"), (120, "full"), (140, "full"), (50, "letterbox"), (60, "letterbox"), (40, "letterbox"))]
ins = C.insights(stat_rows)
assert ins["tests"]["layout"]["best"] == "full" and ins["tests"]["captions"]["best"] == "lines" and ins["campaigns"]["a"]["n"] == 6, ins["tests"]
print("10 layouts, captions, rows, insights ok")
print("clips extras 2 ok")

# 11. a comment question for a clip planned before questions existed: the model's, else a plain one; never strong language
import factpack as F
C.PLANS = pathlib.Path(SCRATCH) / "plans"; C.PLANS.mkdir(exist_ok=True)
(C.PLANS / "speed-expedia.words.json").write_text(json.dumps(words))
F.gemini = lambda prompt, schema=None, **kw: ({"question": "Where would you fly for free?"}, "stub")
m = {"id": "speed-expedia-09", "start": 9.0, "end": 18.0, "hook": "SPEED OPENS THE SUITCASE"}
assert C.question_for("speed-expedia", C.CFG["campaigns"]["speed-expedia"], m) == "Where would you fly for free?" and m["question"]
F.gemini = lambda prompt, schema=None, **kw: ({"question": "What the f**k would you do?"}, "stub")
m = {"id": "speed-expedia-10", "start": 9.0, "end": 18.0, "hook": "x"}
assert C.question_for("speed-expedia", C.CFG["campaigns"]["speed-expedia"], m).startswith("What would you have done here?"), m
F.gemini = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down"))
m = {"id": "speed-expedia-11", "start": 9.0, "end": 18.0, "hook": "x", "question": "Kept?"}
assert C.question_for("speed-expedia", C.CFG["campaigns"]["speed-expedia"], m) == "Kept?"
m = {"id": "speed-expedia-12", "start": 9.0, "end": 18.0, "hook": "x"}
assert "IShowSpeed" in C.question_for("speed-expedia", C.CFG["campaigns"]["speed-expedia"], m)
print("11 comment questions ok")

# 12. several YouTube channels per campaign: each channel has its own number, ceiling and moments
C.CFG["campaigns"] = json.loads(pathlib.Path(REPO_DIR + "/clips/campaigns.json").read_text())["campaigns"]
C.CFG["campaigns"]["tdr-mitch"]["channels"] = ["clips", "gaming"]
C.CFG["campaigns"]["tdr-jenny"].pop("channels", None)
assert C.campaign_channels("tdr-mitch") == ["clips", "gaming"] and C.channel_of("tdr-mitch") == "clips" and C.campaign_channels("tdr-jenny") == ["clips"]
C.ROOT = pathlib.Path(SCRATCH) / "root2"; (C.ROOT / "tokens").mkdir(parents=True, exist_ok=True)
for ch in ("clips", "gaming"): (C.ROOT / "tokens" / f"youtube_{ch}.enc").write_text("x")
assert "tdr-mitch" in C.channels()["gaming"] and "tdr-jenny" in C.channels()["clips"] and "tdr-jenny" not in C.channels()["gaming"]
gam = C.allocate(5, None, "gaming"); assert sum(gam.values()) == 5 and "tdr-jenny" not in gam and "speed-expedia" not in gam, gam
assert sum(C.allocate(12, None, "clips").values()) == 12
C.PLANS = pathlib.Path(SCRATCH) / "plans2"; C.PLANS.mkdir(exist_ok=True)
iso, _ = C.batch_time()
(C.PLANS / "tdr-mitch.json").write_text(json.dumps({"moments": [{"id": "tdr-mitch-01", "publish_at": iso, "channel": "gaming"}, {"id": "tdr-mitch-02", "publish_at": iso},
                                                                 {"id": "tdr-mitch-03", "publish_at": iso, "channel": "gaming", "pulled": "x"}]}))
assert C.scheduled_today("gaming") == 1 and C.scheduled_today("clips") == 1 and C.scheduled_today() == 2
assert C.mchannel("tdr-mitch", {"channel": "gaming"}) == "gaming" and C.mchannel("tdr-mitch", {}) == "clips"
assert C.ceiling_file("gaming").name == "ceiling_gaming.json" and C.ceiling_file("clips").name == "ceiling.json"
rw = C.submit_row("tdr-mitch", C.CFG["campaigns"]["tdr-mitch"], {"id": "tdr-mitch-01", "title": "t", "channel": "gaming"}, "youtube", "https://youtube.com/shorts/x", "2026-10-23 18:00")
assert rw["channel"] == "gaming"
print("12 channels ok")

# reach_share: a campaign whose minimum our clips rarely reach is weighed down; no minimum counts in full
import pathlib as _pl, tempfile as _tf
_r = _pl.Path(_tf.mkdtemp(prefix="qp-test-")); (_r / "clips").mkdir()
(_r / "clips" / "stats.csv").write_text("clip,campaign,video,privacy,hours_public,views,as_of\n"
    + "".join(f"c{i},x,v{i},public,30,{v},2026-10-22T10:00\n" for i, v in enumerate([0, 3, 40, 120, 900, 6000]))
    + "c9,x,v9,public,5,99999,2026-10-22T10:00\n")          # under 24 hours: not counted
_old = C.ROOT; C.ROOT = _r
assert C.reach_share(0) == 1.0
assert abs(C.reach_share(5000) - (1 + 1) / (6 + 4)) < 1e-9, C.reach_share(5000)
assert C.reach_share(10**9) == 0.1                            # (0 + 1) / (6 + 4)
C.ROOT = _old
print("reach share ok")


# clip test verdicts need real views: four arms of zero views never crown the first one (23 October: "letterbox" won 0-0)
C.ROOT = pathlib.Path(SCRATCH); (C.ROOT / "clips").mkdir(exist_ok=True)
zero = [{"privacy": "public", "hours_public": "30", "views": "0", "campaign": "c", **{f"test_{t}": C.TESTS[t][k % len(C.TESTS[t])] for t in C.TESTS}} for k in range(12)]
assert all(v["best"] is None for v in C.insights(zero)["tests"].values())
some = [dict(r, views="40" if r["test_layout"] == "full" else "2") for r in zero]
assert C.insights(some)["tests"]["layout"]["best"] == "full"
print("verdicts ok")

# a channel at its YouTube limit hands the clip to the campaign's next channel (gaming and irl can't be phone-verified)
import types
Y = sys.modules.get("youtube") or types.ModuleType("youtube"); sys.modules["youtube"] = Y      # no Google libraries needed here
C.PLANS = pathlib.Path(SCRATCH) / "plans_up"; C.PLANS.mkdir(exist_ok=True); C.OUT = pathlib.Path(SCRATCH) / "out_up"; C.OUT.mkdir(exist_ok=True)
(C.OUT / "speed-expedia-50.mp4").write_bytes(b"x"); (C.OUT / "speed-expedia-51.mp4").write_bytes(b"x")
(C.PLANS / "speed-expedia.json").write_text(json.dumps({"moments": [
    {"id": "speed-expedia-50", "made": "t", "file": "speed-expedia-50.mp4", "hook": "a", "title": "t", "channel": "irl", "start": 0, "end": 30},
    {"id": "speed-expedia-51", "made": "t", "file": "speed-expedia-51.mp4", "hook": "b", "title": "t", "channel": "irl", "start": 40, "end": 70}]}))
C.gh = lambda *a, **k: subprocess.CompletedProcess(a, 0)
C.clips_client = lambda ch: ch
C.add_rows = lambda rows: None
C.ceiling_learn = lambda *a, **k: None
UPS = []
def fake_upload(client, *a, **k):
    UPS.append(client)
    if client == "irl": raise RuntimeError('<HttpError 400 "The user has exceeded the number of videos they may upload." uploadLimitExceeded>')
    return f"vid{len(UPS)}"
Y.upload = fake_upload
C.campaign_channels = lambda cid: ["irl", "clips"]
import quota
quota.allow, quota.spend = (lambda *a, **k: False), (lambda *a, **k: None)
assert C.upload("speed-expedia", mode="private") == [] and UPS == []      # the Shorts' allowance comes first: the clips wait
quota.allow = lambda *a, **k: True
rows = C.upload("speed-expedia", mode="private")
ms = json.loads((C.PLANS / "speed-expedia.json").read_text())["moments"]
assert [m.get("channel") for m in ms] == ["clips", "clips"] and all(m.get("video") for m in ms), ms
assert UPS == ["irl", "clips", "clips"], UPS        # irl refused once, then skipped for the run
assert C.uploads_24h("clips") == 2 and C.uploads_24h("irl") == 0     # what a refusal settles a ceiling at
print("channel fallback ok")

# the virality score is measured against real views: bands, and a learned threshold only when high scores really earn more
rows = [{"privacy": "public", "hours_public": "30", "campaign": "c", "views": str(300 if k % 10 >= 7 else 10), "score": str(k % 10 + 1),
         **{f"test_{t}": C.TESTS[t][0] for t in C.TESTS}} for k in range(60)]
ins = C.insights(rows)
assert ins["scored_clips"] == 60 and ins["score_bands"]["8 to 10"]["mean_views"] == 300 and ins["min_score"] == 8, ins
assert C.min_score() == 8
flat = [dict(r, views="5") for r in rows]
assert C.insights(flat)["min_score"] is None and C.min_score() == C.MIN_SCORE
print("viral score ok")

# private test clips join the next batch only when asked ("promote"): the publish time on YouTube, the day's count, the
# submit rows' public time; an old test stays private
import quota
quota.allow, quota.spend = (lambda *a, **k: True), (lambda *a, **k: None)
CALLS = []
class _V:
    def update(self, part, body): CALLS.append((part, body)); return types.SimpleNamespace(execute=lambda: {})
C.clips_client = lambda ch: types.SimpleNamespace(videos=lambda: _V())
plan_p = C.PLANS / "speed-expedia.json"
pl = json.loads(plan_p.read_text())
pl["moments"].append({"id": "speed-expedia-49", "video": "old", "publish_at": "private", "channel": "clips",
                      "uploaded": (C.NOW - dt.timedelta(days=5)).isoformat(timespec="minutes")})
plan_p.write_text(json.dumps(pl))
C.ROOT = pathlib.Path(SCRATCH); (C.ROOT / "clips").mkdir(exist_ok=True)
with (C.ROOT / "clips" / "submit.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=C.SUBMIT_FIELDS); w.writeheader()
    w.writerow({"clip": "speed-expedia-50", "campaign": "speed-expedia", "public_at_uk": "private (test)", "video": "https://youtube.com/shorts/vid2"})
iso, when = C.batch_time(C.campaigns()["speed-expedia"].get("platform"))
assert C.promote_tests() == 2 and len(CALLS) == 2, CALLS
assert all(p == "status" and b["status"]["publishAt"] == iso and b["status"]["privacyStatus"] == "private" for p, b in CALLS), CALLS
ms = {m["id"]: m for m in json.loads(plan_p.read_text())["moments"]}
assert ms["speed-expedia-50"]["publish_at"] == iso and ms["speed-expedia-49"]["publish_at"] == "private"
assert C.scheduled_today("clips") == 2
row = next(csv.DictReader((C.ROOT / "clips" / "submit.csv").open()))
assert row["public_at_uk"] == when.strftime("%Y-%m-%d %H:%M"), row
assert C.promote_tests() == 0          # once only
# held back by the YouTube allowance: a marker, and the next run or prepare finishes it
C.STATE = pathlib.Path(SCRATCH) / "state"
pl = json.loads(plan_p.read_text()); pl["moments"][0].update(publish_at="private"); plan_p.write_text(json.dumps(pl))
quota.allow = lambda *a, **k: False
assert C.promote_tests() == 0 and (C.STATE / "promote.json").exists()
quota.allow = lambda *a, **k: True
assert C.promote_tests(json.loads((C.STATE / "promote.json").read_text())["hours"]) == 1 and not (C.STATE / "promote.json").exists()
print("promote ok")

# a long transcript is planned a window at a time: the stretch with the least already clipped (23 October: 144 minutes at
# once gave nothing back)
lines = [f"[{i * 6}-{i * 6 + 6}] " + "word " * 20 + ("(already clipped)" if i < 300 else "") for i in range(1000)]
w, st = C.window(lines, size=9000)
assert st >= 300 and 8000 <= sum(len(l.split()) for l in w) <= 9000 and not any(l.endswith("(already clipped)") for l in w), (st, len(w))
assert C.window(lines[:100]) == (lines[:100], 0)
print("plan window ok")

# places a campaign leaves unfilled go to the campaigns on its channel that filled theirs, strongest first; never a series
MADE, UPL = [], []
C.make = lambda cid, count=None, channel=None: (MADE.append((cid, channel)), [{"id": cid}])[1]
C.upload = lambda cid, mode=None: UPL.append(cid)
cs_ = {"a": {"rules": {}}, "b": {"rules": {}}, "c": {"rules": {}}, "s": {"rules": {"series": True}}}
shares_ = {"clips": {"a": 2, "s": 1, "b": 1, "c": 1}}
made_ = {("clips", "a"): 2, ("clips", "s"): 0, ("clips", "b"): 0, ("clips", "c"): 1}
import time as _time
assert C.spill(shares_, made_, cs_, _time.time() + 60) == 2 and MADE == [("a", "clips"), ("c", "clips")] and UPL == ["a", "c"], MADE
assert made_[("clips", "a")] == 3 and made_[("clips", "s")] == 0
MADE.clear()
assert C.spill({"clips": {"a": 2, "b": 1}}, {("clips", "a"): 2}, cs_, _time.time() - 1) == 0 and not MADE    # out of time
print("spill ok")

# a channel YouTube is not showing (8+ clips with our own take, a day old, 70% unseen) makes 4 a day until the check clears
C.ROOT = pathlib.Path(SCRATCH) / "uc"; (C.ROOT / "clips").mkdir(parents=True); (C.ROOT / "analytics").mkdir()
C.STATE = C.ROOT / "clips" / "state"
rows = [{"channel": "clips", "privacy": "public", "hours_public": "30", "views": "0", "test_take": "voice"} for _ in range(8)]
got = C.reach_check(rows)
assert got["clips"]["take_unseen"] and C.unseen_cap("clips") == 4 and C.unseen_cap("gaming") is None
assert C.unseen_cap("clips") == 4 and (C.ROOT / "analytics" / "decisions.csv").read_text().count("clips channel: 4 clips a day") == 1   # noted once
C.reach_check([dict(r, views="40") for r in rows]); assert C.unseen_cap("clips") is None
print("unseen cap ok")
