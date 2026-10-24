"""Offline test of the pause rule (Charlie, 21 October, as a permanent "stop"; a 14-day pause and retest from 24 October):
a choice whose Shorts have little to no views a week on is paused (pipeline/drivers.py), the writer leaves it out while
paused (pipeline/writer.py), then retests it on a small share; a dead Short is never remade. The old verdict "stop" is
still read as a pause."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import drivers as D

now = dt.datetime.now(dt.timezone.utc)
today = now.astimezone(D.UK).date()
def row(i, days, views, fmt, rel=1.0):
    posted = now - dt.timedelta(days=days)
    return {"short": f"T-{i:03d}", "posted": posted.isoformat(timespec="minutes"), "posted_day": str(posted.date()), "yt_views": str(views),
            "rel": rel, "format": fmt, "category": "Music", "hook": "A hook here", "seconds": "30", "slot_uk": "09:00", "title": "t"}

# 1. the dead floor: a fifth of the typical week-old Short, never under 20; needs 5 week-old Shorts
rows = [row(i, 8 + i % 3, 200, "one_detail", 1.2) for i in range(6)]
assert D.dead_floor(rows) == 40.0 and not D.dead(rows)
assert D.dead_floor(rows[:4]) is None
rows += [row(10 + i, 9 + i % 2, 5, "news_explained", 0.05) for i in range(3)] + [row(20, 2, 3, "news_explained", 0.1)]
dead = {r["short"] for r in D.dead(rows)}
assert dead == {"T-010", "T-011", "T-012"}, dead                                  # the 2-day-old one is too young to call
print("1 dead floor ok")

# 2. a pause needs 5 week-old Shorts over 2 UK days: 3 are not enough any more (24 October: small-n stops piled up)
pauses = {}
table, _ = D.analyse(rows, pauses, str(today))
v = {t["value"]: t["verdict"] for t in table if t["feature"] == "format"}
assert v["news_explained"] not in ("pause", "stop") and not pauses, (v, pauses)
rows += [row(40 + i, 8 + i % 2, 4, "news_explained", 0.05) for i in range(2)]      # now 5, on 2 days, median 5 < 0.75 x 40
table, _ = D.analyse(rows, pauses, str(today))
v = {t["value"]: t["verdict"] for t in table if t["feature"] == "format"}
assert v["news_explained"] == "pause" and v["one_detail"] not in ("pause", "stop"), v
why = next(t["why"] for t in table if t["value"] == "news_explained")
assert "under three quarters of the floor of 40" in why and "format|news_explained" in pauses, (why, pauses)
assert pauses["format|news_explained"]["until"] == str(today + dt.timedelta(days=14))
lines = D.recipe(table, rows + [row(50 + i, 1, 100, "one_detail", 1.0) for i in range(10)])
assert any(l.startswith("Paused for 14 days") and "news_explained" in l for l in lines), lines
print("2 pause verdict ok")

# 3. a narrow miss is no pause: a median just under the floor (above three quarters of it) stays in play
near = [row(i, 8 + i % 3, 200, "one_detail", 1.2) for i in range(6)] + [row(60 + i, 8 + i % 2, 35, "countdown", 0.5) for i in range(5)]
p2 = {}
t2, _ = D.analyse(near, p2, str(today))
assert {t["value"]: t["verdict"] for t in t2 if t["feature"] == "format"}["countdown"] not in ("pause", "stop") and not p2
print("3 narrow miss ok")

# 4. after 14 days: retest on a small share; retest Shorts under the floor pause it again, over it lift the pause
later = str(today + dt.timedelta(days=15))
t3, _ = D.analyse(rows, pauses, later)
assert {t["value"]: t["verdict"] for t in t3 if t["feature"] == "format"}["news_explained"] == "retest"
until = dt.date.fromisoformat(pauses["format|news_explained"]["until"])
def at(i, day, views):          # a Short posted on a given UK day, judged 9 days later
    posted = dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc)
    return {"short": f"R-{i:03d}", "posted": posted.isoformat(timespec="minutes"), "posted_day": str(day), "yt_views": str(views),
            "rel": 0.1, "format": "news_explained", "category": "Music", "hook": "h", "seconds": "30", "slot_uk": "09:00", "title": "t"}
D_NOW = D.NOW
D.NOW = dt.datetime.combine(until + dt.timedelta(days=9), dt.time(12), tzinfo=dt.timezone.utc)
retest = [at(i, until + dt.timedelta(days=i % 2), 3) for i in range(3)]
t4, _ = D.analyse(rows + retest, pauses, str(until + dt.timedelta(days=9)))
assert {t["value"]: t["verdict"] for t in t4 if t["feature"] == "format"}["news_explained"] == "pause" and pauses["format|news_explained"]["times"] == 2
good = {"format|news_explained": {"since": "2026-10-01", "until": str(until), "why": "x", "times": 1}}
t5, _ = D.analyse(rows + [dict(r, yt_views="500") for r in retest], good, str(until + dt.timedelta(days=9)))
assert not good, good                                                              # the retest beat the floor: lifted
D.NOW = D_NOW
print("4 retest ok")

# 5. the writer: a paused arm, kind or category is left out (the old "stop" too); a retested one gets a small share;
#    a dead Short is never remade
import writer as W
W.ROOT = SCRATCH; (SCRATCH / "analytics").mkdir(); (SCRATCH / "boards" / "done").mkdir(parents=True)
with (SCRATCH / "analytics" / "drivers.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["feature", "feature_label", "value", "n", "lift", "median_rel", "verdict", "why"]); w.writeheader()
    w.writerow({"feature": "hook_type", "feature_label": "Hook style", "value": "number", "n": 4, "lift": 0.1, "median_rel": 0.1, "verdict": "pause", "why": "x"})
    w.writerow({"feature": "kind", "feature_label": "Kind of Short", "value": "fiction", "n": 4, "lift": 0.1, "median_rel": 0.1, "verdict": "stop", "why": "x"})
    w.writerow({"feature": "kind", "feature_label": "Kind of Short", "value": "top list", "n": 6, "lift": 0.6, "median_rel": 0.5, "verdict": "retest", "why": "x"})
    w.writerow({"feature": "category", "feature_label": "Category", "value": "Science", "n": 4, "lift": 0.1, "median_rel": 0.1, "verdict": "pause", "why": "x"})
    w.writerow({"feature": "category", "feature_label": "Category", "value": "Tech", "n": 6, "lift": 0.6, "median_rel": 0.5, "verdict": "retest", "why": "x"})
    w.writerow({"feature": "category", "feature_label": "Category", "value": "Sport", "n": 6, "lift": 1.4, "median_rel": 1.2, "verdict": "push", "why": "x"})
assert W.stopped() == {"hook_type": {"number"}, "kind": {"fiction"}, "category": {"Science"}}
assert "number" not in W.arms("hook_type") and W.share("fiction", 3, 9) == 0 and W.share("news", 3, 9) == 3 and W.share("top list", 3, 9) == 1
b = W.boosts(); assert b["Science"] == W.STOP and b["Sport"] == 2 and b["Tech"] == -2
picks = [W.test_plan(k)[1].get("hook_type") for k in range(40)]
assert "number" not in picks and any(picks), picks
with (SCRATCH / "analytics" / "shorts.csv").open("w", newline="") as f:
    cols = ["short", "title", "posted", "posted_day", "yt_views", "views_vs_typical"]
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k: r.get(k, "") for k in cols} | {"views_vs_typical": "0.1" if r["short"] != "T-000" else "0.3"})
weak = [r["short"] for r in W.weak()]
assert "T-010" not in weak and "T-011" not in weak and "T-000" in weak, weak      # dead ones out; a weak but living one stays
print("5 writer pauses ok")
print("pause rule ok")
