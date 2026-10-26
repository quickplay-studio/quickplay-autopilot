"""Offline tests of the data report's act-early items (24 October):
1. analytics.breakouts: a Short in the top fifth at 3 hours (2x the median at 3 hours, 20+ views) is a breakout hours
   before the 24-hour numbers, trigger "3 hours"; below that, or with too few peers, it is not;
2. writer.hot: no third follow-up on one subject, nothing in a paused category, never a dead Short;
3. writer.test_plan: the factorial round gives every Short an arm of each factor, 50/50 and independent; a settled
   factor keeps its winner, challenged 1 Short in 5; exploration Shorts and days before the round are unchanged;
4. analytics.test_progress: measured Shorts per arm and how many more each needs (analytics/tests.json);
5. drivers.category_mix: a category held at a minimum until a date (Gaming 15% for the GTA 6 window), floor 7%."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import collections, csv, datetime as dt, json, os, random, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import analytics as A

# 1. the 3-hour trigger
now = A.NOW
def short(i, hours_ago, v3, views):
    return {"short": f"T-{i:03d}", "title": f"t{i}", "category": "Music", "posted": (now - dt.timedelta(hours=hours_ago)).isoformat(timespec="minutes"),
            "yt_views": views, "youtube_url": f"https://youtube.com/shorts/v{i}"}
rows, curves = [], {}
for i in range(20):                                   # 20 peers, 6 to 120 hours old, 2 to 21 views at 3 hours
    r = short(i, 6 + i * 6, 2 + i, 40); rows.append(r)
    curves[r["short"]] = {"points": [[0.5, 0], [1.0, 1], [3.0, 2 + i], [5.0, 3 + i]]}
star = short(100, 4, 60, 90); rows.append(star); curves[star["short"]] = {"points": [[0.5, 5], [3.0, 60], [4.0, 90]]}
meh = short(101, 4, 15, 20); rows.append(meh); curves[meh["short"]] = {"points": [[0.5, 1], [3.0, 15], [4.0, 20]]}
A.OUT = SCRATCH / "analytics"; A.OUT.mkdir()
got = A.breakouts(rows, curves)
hit = {b["short"]: b for b in got}
assert "T-100" in hit and hit["T-100"]["trigger"] == "3 hours" and hit["T-100"]["views_3h"] == 60, got
assert hit["T-100"]["times_typical"] >= 2 and "T-101" not in hit, got
assert list(csv.DictReader((A.OUT / "breakouts.csv").open()))[0]["trigger"] == "3 hours"
assert A.early_break(star, rows[:5], curves) is None                     # under 10 peers: no call
print("1 three-hour breakout ok")

# 2. the writer's follow-up guards
import writer as W
W.ROOT = SCRATCH
for d in ("done", "queue"): (SCRATCH / "boards" / d).mkdir(parents=True, exist_ok=True)
def board(sid, **kw): (SCRATCH / "boards" / "done" / f"{sid}.json").write_text(json.dumps({"id": sid, "meta": {"title": sid}, **kw}))
board("QD-001"); board("QD-002", follows="QD-001")                                            # QD-002: a first follow-up
board("QD-004"); board("QD-005", follows="QD-004"); board("QD-006", follows="QD-005")      # QD-006: the second follow-up of QD-004
board("QD-010", category="Science"); board("QD-020"); board("QD-030")
(A.OUT / "breakouts.csv").write_text("short,title,category,hours_public,views,typical_at_this_age,times_typical,youtube_url,trigger,views_3h,typical_3h\n"
    "QD-006,c,Music,5,90,10,9,u,3 hours,60,5\nQD-010,s,Science,5,90,10,8,u,3 hours,50,5\nQD-020,d,Music,5,90,10,7,u,3 hours,40,5\n"
    "QD-030,ok,Music,5,90,10,6,u,views for age,,\nQD-002,b,Music,5,90,10,5,u,3 hours,30,5\n")
(A.OUT / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict,why\ncategory,Category,Science,6,0.2,0.2,pause,x\n")
import drivers as DRV
_dead = DRV.dead
DRV.dead = lambda rows: [{"short": "QD-020"}]
ids = [r["short"] for r in W.hot()]
DRV.dead = _dead
assert ids == ["QD-030", "QD-002"], ids               # QD-002 is the first follow-up: a second one is still allowed
print("2 follow-up guards ok")

# 3. the factorial round
W.CFG = {**W.CFG, "test_round": {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
                                 "factors": {"hook_type": ["statement", "number"], "length": ["25 to 34 s", "35 to 44 s"],
                                             "title_search": ["search phrase", "curiosity"], "first_frame": ["cover", "photo"]}}}
(A.OUT / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict,why\n")
on = dt.date(2026, 10, 26)
plans = [W.test_plan(k, "news", today=on)[1] for k in range(400)]
for f, arms in W.CFG["test_round"]["factors"].items():
    c = collections.Counter(p[f] for p in plans)
    assert set(c) == set(arms) and all(170 <= n <= 230 for n in c.values()), (f, c)
both = collections.Counter((p["hook_type"], p["length"]) for p in plans)
assert len(both) == 4 and all(70 <= n <= 130 for n in both.values()), both                 # independent of each other
assert all(p["round"] == "round 1" and p["explore"] == "no" for p in plans)
ev = W.test_plan(3, "evergreen", today=on)[1]
assert "title_search" not in ev and ev["hook_type"] in ("statement", "number")             # NOT_FOR still applies
assert "round" not in W.test_plan(3, "news", today=dt.date(2026, 10, 24))[1]                # before the round: as before
ex = W.test_plan(3, "news", explore=True, today=on)[1]
assert ex["explore"] == "yes" and "round" not in ex
(A.OUT / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict,why\nlength,Length,35 to 44 s,80,1.6,1.5,push,x\n")
lens = [W.test_plan(k, "news", today=on)[1]["length"] for k in range(1, 101)]
assert lens.count("35 to 44 s") >= 75 and set(lens) == {"35 to 44 s", "25 to 34 s"}, collections.Counter(lens)   # winner, still challenged
assert "statement" in W.TESTS["hook_type"] and "25 to 34 s" in W.TESTS["length"]
print("3 factorial round ok")

# 4. progress of the round
A.CFG = {**A.CFG, "test_round": W.CFG["test_round"]}
prow = lambda i, day, hook, secs, v="50": {"short": f"P-{i}", "posted": f"{day}T10:00:00+00:00", "views_24h": v, "hook": hook, "seconds": secs,
                                            "title_search": "curiosity", "first_frame": "cover",
                                            "arm_hook_type": "number" if hook[0].isdigit() else "statement",      # as assigned (26 October)
                                            "arm_length": "35 to 44 s" if secs == "40" else "25 to 34 s"}
rows = [prow(i, "2026-10-26", "Taylor Swift has a new album out", "30") for i in range(10)] + \
       [prow(100 + i, "2026-10-26", "3 million people watched this", "40") for i in range(4)] + \
       [prow(200, "2026-10-20", "Taylor Swift again", "30"), prow(201, "2026-10-27", "Not measured yet", "30", v="")]
lines = A.test_progress(rows, [{"feature": "length", "value": "35 to 44 s", "verdict": "push"}], today=on)
T = json.loads((A.OUT / "tests.json").read_text())
assert T["factors"]["hook_type"]["arms"]["statement"] == {"n": 10, "needs": 60, "verdict": ""}, T["factors"]["hook_type"]
assert T["factors"]["hook_type"]["arms"]["number"]["n"] == 4, T["factors"]
L = T["factors"]["length"]                         # 26 October: only the round's own adjusted verdict settles a factor; the pooled push shows on its arm
assert L["settled"] is False and L["arms"]["35 to 44 s"]["verdict"] == "push" and L["verdict"] == "too few to tell", L
assert T["factors"]["first_frame"]["arms"]["photo"]["needs"] == 70 and not T["factors"]["first_frame"]["settled"]
assert lines[0].startswith("Tests being run (round 1") and any(l.startswith("- hook: statement 10, number 4; too few to tell") for l in lines), lines
assert A.test_progress(rows, [], today=dt.date(2026, 10, 24)) == []                         # before the round: nothing in insights.md
print("4 round progress ok")

# 5. timed category minimums and the 7% floor
DRV.ROOT = SCRATCH
(SCRATCH / "config.json").write_text(json.dumps({"category_min": {"Gaming": {"share": 0.15, "until": "2026-11-26"}}}))
crow = lambda c, v, l: {"feature": "category", "value": c, "verdict": v, "lift": l}
rows = [crow("Music", "push", 2.4), crow("Film", "early sign", 1.4), crow("Sport", "about typical", 1.0),
        crow("Science", "pause", 0.2), crow("Tech", "cut back", 0.3), crow("Gaming", "about typical", 0.8)]
mid, after = DRV.category_mix(rows, dt.date(2026, 11, 1)), DRV.category_mix(rows, dt.date(2026, 11, 27))
assert abs(mid["Gaming"] - 0.15) < 1e-9 and after["Gaming"] < 0.15 and mid["Science"] == after["Science"] == 0.0, (mid, after)
for m in (mid, after):
    assert abs(sum(m.values()) - 1) < 1e-9 and all(0.07 - 1e-9 <= v <= 0.35 + 1e-9 for k, v in m.items() if k != "Science"), m
paused = DRV.category_mix([crow("Gaming", "pause", 0.2), crow("Music", "push", 2.0), crow("Film", "about typical", 1.0)], dt.date(2026, 11, 1))
assert paused["Gaming"] == 0.0, paused                                                      # a paused category stays paused
print("5 category minimums ok")
print("act early ok")
