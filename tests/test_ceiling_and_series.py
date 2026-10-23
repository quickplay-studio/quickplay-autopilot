"""Offline test of the learning upload ceiling (quota.py), series notes for two and three parts, trend-tied sources and
the search terms the planner sees."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import datetime as dt, json, os, pathlib, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import quota as Q

# 1. the ceiling: starts at config daily_limit, rises after a filled day, settles where YouTube refuses
Q.LIMIT_P = pathlib.Path(SCRATCH) / "upload_limit.json"
DECIDED = []
Q._decide = lambda change, why, evidence: DECIDED.append(change)
base = int(Q.CFG.get("daily_limit", 24))
assert Q.daily_limit() == base
assert Q.learn(base - 5) == base and not DECIDED                     # the day was not filled: no change
assert Q.learn(base - 1) == base + int(Q.CFG.get("upload_limit_step", 6)) and DECIDED == [f"Upload ceiling {base} to {base + 6}"]
assert Q.learn(base + 5) == base + 6                                  # raised less than a day ago: waits
st = json.loads(Q.LIMIT_P.read_text()); st["raised_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)).isoformat(timespec="minutes")
Q.LIMIT_P.write_text(json.dumps(st))
assert Q.learn(base + 5) == base + 12
assert Q.refused(base + 3) == base + 3 and Q.daily_limit() == base + 3 and DECIDED[-1] == f"Upload ceiling {base + 12} to {base + 3}"
assert Q.learn(base + 3) == base + 3                                  # refused within 48 hours: no raise
st = json.loads(Q.LIMIT_P.read_text()); st["refused_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=49)).isoformat(timespec="minutes")
st["raised_at"] = st["refused_at"]; Q.LIMIT_P.write_text(json.dumps(st))
assert Q.learn(base + 3) == base + 9
for _ in range(20):
    st = json.loads(Q.LIMIT_P.read_text()); st["raised_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=25)).isoformat(timespec="minutes")
    Q.LIMIT_P.write_text(json.dumps(st)); Q.learn(999)
assert Q.daily_limit() == int(Q.CFG.get("upload_limit_max", 72)), Q.daily_limit()
assert Q.refused(3) == int(Q.CFG.get("upload_limit_min", 10))        # never under the floor
print("1 ceiling ok", DECIDED[:2], "...", DECIDED[-1])

# 2. the writer's day follows the ceiling (with no chosen number a day), and never passes the chosen number (15)
import writer as W
Q.VOLUME_P = pathlib.Path(SCRATCH) / "volume.json"
chosen = Q.CFG.get("shorts_per_day"); Q.CFG["shorts_per_day"] = 0
Q.LIMIT_P.write_text(json.dumps({"limit": 60}))
run, day, cap = W.plan(False, "morning")
runs = W.CFG["runs"]
assert cap <= 60 and cap >= 60 * runs["morning"] // sum(runs.values()) - 1, (cap, runs)
Q.CFG["shorts_per_day"] = 15
assert W.plan(False, "morning")[2] <= 15
Q.CFG["shorts_per_day"] = chosen
Q.LIMIT_P.write_text(json.dumps({"limit": 40}))
print("2 writer plan ok", cap)

# 3. series notes for two and three parts
assert "Part 1 of 2" in W.part_note(1, 2) and "(Part 1)" in W.part_note(1, 2)
m = W.part_note(2, 3, "T", "said")
assert "Part 2 of 3" in m and "cliffhanger for Part 3" in m and '"T"' in m and "said" in m
l = W.part_note(3, 3, "T", "said")
assert "Part 3 of 3" in l and "land the" in l and "(Part 3)" in l
assert W.PART2_NOTE.startswith("SERIES: this is Part 2 of 2")
assert "three parts" in W.TESTS["series"] and "series" not in W.NOT_FOR.get("news", ())
print("3 part notes ok")

# 4. trend-tied and follow-up sources are their own driver values; the planner sees our search terms
assert W.source_of("evergreen top list (trending: Zelda)") == "Trend-tied"
assert W.source_of("evergreen top list") == "Evergreen" and W.source_of("follow-up of QD-034 (5.2x)") == "Follow-up"
assert 0.25 <= W.trend_share() <= 0.75
p = W.ROOT / "analytics" / "search_terms.csv"; backup = p.read_bytes() if p.exists() else None
p.write_text("term,views\nhow was tetris made,40\nzelda remake,120\n")
terms = W.search_terms()
if backup is not None: p.write_bytes(backup)
else: p.unlink()
assert terms == ["zelda remake", "how was tetris made"], terms
print("4 sources ok")
print("ceiling and series ok")
