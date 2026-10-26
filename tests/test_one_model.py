"""Offline tests of the one pooled, channel-aware learning model (26 October):
1. drivers.round_verdicts: a real arm effect becomes a "winner" adjusted for the channel; no effect settles as "even";
   too few Shorts stays "too few to tell"; Shorts before the round's start are left out;
2. drivers.channel_table: each channel's reading beside the pooled one, and an exception only with 10+ of its own Shorts
   that pass the gate and disagree with the pool;
3. writer.winners(channel) applies round.csv winners and the channel's exceptions; writer.settled() takes a factor out
   of the round and the plan;
4. writer.channel_tests: no series or franchise on a channel, no posting-hour arm on the Americas grid;
5. looks.arm_option: "lab" is the dimension's newest active lab option."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, os, random, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import drivers as DRV

# 1. the round's adjusted verdicts
rng = random.Random(7)
def short(i, day, ch, hook, frame, rel):
    return {"short": f"R-{i}", "channel": ch, "posted": f"2026-10-{day}T12:00:00+00:00", "rel": rel,
            "arm_hook_type": hook, "first_frame": frame}
rows = []
for i in range(60):
    day, ch = 25 + i % 4, ("main", "music")[i % 3 == 0]
    hook, frame = ("statement", "number")[i % 2], ("cover", "photo")[(i // 2) % 2]
    base = 1.6 if ch == "music" else 1.0                     # a channel effect the regression must take out
    rows.append(short(i, day, ch, hook, frame, base * (1.7 if hook == "number" else 1.0) * rng.uniform(0.85, 1.18)))
rows.append(short(999, 20, "main", "number", "cover", 50.0))           # before the round: left out
F = {"hook_type": ["statement", "number"], "first_frame": ["cover", "photo"]}
V = {r["factor"]: r for r in DRV.round_verdicts(rows, F, "2026-10-25", per_arm=70, name="round 1")}
h = V["hook_type"]
assert h["verdict"] == "winner" and h["winner"] == "number" and h["halves"] == "agree", h
assert 1.5 <= h["effect"] <= 1.9 and h["low"] > 1 and h["n_a"] + h["n_b"] == 60, h
f = V["first_frame"]
assert f["verdict"] == "even" and f["winner"] == "" and 0.87 < f["low"] <= f["high"] < 1.15, f
few = DRV.round_verdicts(rows[:4], F, "2026-10-25")
assert all(r["verdict"] == "too few to tell" for r in few), few
noisy = [{**r, "rel": r["rel"] * rng.choice((0.3, 3.0))} for r in rows[:60]]
assert DRV.round_verdicts(noisy, {"first_frame": F["first_frame"]}, "2026-10-25")[0]["verdict"] == "running"
print("1 round verdicts ok")

# 2. each channel's own reading
crow = lambda i, ch, day, end, rel: {"short": f"C-{i}", "channel": ch, "posted": f"2026-10-{day}T12:00:00+00:00", "rel": rel, "ending": end}
rows = [crow(i, "music", 25 + i % 3, ("loop", "question")[i % 2], (1.0 if i % 2 == 0 else 2.2) * rng.uniform(0.9, 1.1)) for i in range(24)]
rows += [crow(100 + i, "main", 25 + i % 3, ("loop", "question")[i % 2], rng.uniform(0.9, 1.1)) for i in range(40)]
table = [{"feature": "ending", "value": "question", "lift": 1.2, "verdict": "about typical"},
         {"feature": "ending", "value": "loop", "lift": 1.0, "verdict": "about typical"}]
T = {(t["channel"], t["value"]): t for t in DRV.channel_table(rows, table) if t["feature"] == "ending"}
q = T[("music", "question")]
assert q["n"] == 12 and q["verdict"] == "push" and q["exception"] == "push here", q
assert 1.2 < q["own_lift"] < q["lift"] < 2.2 and q["pooled_lift"] == 1.2, q     # shrunk towards the pool, not towards typical
assert T[("main", "question")]["exception"] == "", T[("main", "question")]
short_rows = [r for r in rows if r["channel"] == "main" or int(r["short"][2:]) < 16]       # 8 a side on music: no exception yet
assert DRV.channel_table(short_rows, table) and all(t["exception"] == "" for t in DRV.channel_table(short_rows, table))
agree = [{**t, "verdict": "push"} if t["value"] == "question" else t for t in table]
assert {(t["channel"], t["value"]): t for t in DRV.channel_table(rows, agree)}[("music", "question")]["exception"] == ""   # agrees with the pool
print("2 channel table ok")

# 3. the writer reads both
import writer as W
W.ROOT = SCRATCH
(SCRATCH / "analytics").mkdir()
def put(name, fields, items):
    with (SCRATCH / "analytics" / name).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(items)
put("drivers.csv", ["feature", "value", "lift", "verdict"], [{"feature": "length", "value": "35 to 44 s", "lift": "1.4", "verdict": "push"}])
put("round.csv", DRV.ROUND_FIELDS, [{"round": "round 1", "factor": "hook_type", "verdict": "winner", "winner": "number"},
                                    {"round": "round 1", "factor": "length", "verdict": "winner", "winner": "25 to 34 s"},
                                    {"round": "round 1", "factor": "first_frame", "verdict": "even"},
                                    {"round": "round 1", "factor": "angles", "verdict": "no clear difference"},
                                    {"round": "round 1", "factor": "ending", "verdict": "running", "leaning": "loop"}])
put("channel_drivers.csv", DRV.CHANNEL_FIELDS, [{"channel": "music", "feature": "ending", "value": "question", "exception": "push here"},
                                                {"channel": "music", "feature": "hook_type", "value": "number", "exception": "cut back here"},
                                                {"channel": "irl", "feature": "ending", "value": "loop", "exception": "push here"}])
assert W.winners() == {"length": "25 to 34 s", "hook_type": "number"}, W.winners()          # the round's adjusted verdict wins
assert W.winners("main") == W.winners()
assert W.winners("music") == {"length": "25 to 34 s", "ending": "question"}, W.winners("music")
assert W.winners("irl") == {"length": "25 to 34 s", "hook_type": "number", "ending": "loop"}, W.winners("irl")
assert W.settled() == {"first_frame", "angles"}, W.settled()
W.stopped = lambda: {}
W.CFG["test_round"] = {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
                       "factors": {"hook_type": ["statement", "number"], "first_frame": ["cover", "photo"],
                                   "angles": ["shown", "hidden"], "ending": ["loop", "question"]}}
on = dt.date(2026, 10, 27)
plans = [W.test_plan(k, "news", today=on, channel="music")[1] for k in range(200)]
assert not any({"first_frame", "angles"} & set(p) for p in plans), plans[0]                 # settled: out of the round and the rotation
assert all(p.get("round") == "round 1" for p in plans)
endings = [p["ending"] for p in plans]
assert set(endings) == {"loop", "question"} and endings.count("question") > endings.count("loop") * 2, endings.count("question")   # music's exception, still challenged
assert {p["hook_type"] for p in plans} == {"statement", "number"}
print("3 writer winners and settled ok")

# 4. what a channel's boards leave out
t = {"series": "part", "franchise": "named", "fx_slot": "06:00 to 12:00", "fx_energy": "lab", "ending": "loop", "round": "round 1"}
assert W.channel_tests(t, {}) == {"fx_slot": "06:00 to 12:00", "fx_energy": "lab", "ending": "loop", "round": "round 1"}
assert W.channel_tests(t, {"slot_grid": "americas"}) == {"fx_energy": "lab", "ending": "loop", "round": "round 1"}
print("4 channel tests ok")

# 5. the "lab" arm
import looks as LK
cat = {"dimensions": {"energy": {"options": {"steady": {}, "lab-energy-1019": {"lab": True, "born": "2026-10-19", "retired": True},
                                             "lab-energy-1024": {"lab": True, "born": "2026-10-24"},
                                             "lab-energy-1022": {"lab": True, "born": "2026-10-22"}}},
                      "grade": {"options": {"natural": {}}}}}
assert LK.arm_option(cat, "energy", "lab") == "lab-energy-1024"
assert LK.arm_option(cat, "energy", "steady") == "steady"
assert LK.arm_option(cat, "energy", "lab-energy-1019") is None                              # retired: chosen as usual
assert LK.arm_option(cat, "grade", "lab") is None and LK.arm_option(cat, "opening", "lab") is None
print("5 lab arm ok")
print("one model ok")
