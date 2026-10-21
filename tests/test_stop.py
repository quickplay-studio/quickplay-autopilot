"""Offline test of the "stop" rule (Charlie, 21 October): a choice whose Shorts have little to no views a week on gets
verdict "stop" (pipeline/drivers.py), the writer never makes it again (pipeline/writer.py), and a dead Short is never
remade."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import drivers as D

now = dt.datetime.now(dt.timezone.utc)
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

# 2. the verdict: 3 week-old Shorts under the floor on 2 days -> stop; the healthy format is not
table, _ = D.analyse(rows)
v = {t["value"]: t["verdict"] for t in table if t["feature"] == "format"}
assert v["news_explained"] == "stop" and v["one_detail"] != "stop", v
why = next(t["why"] for t in table if t["value"] == "news_explained")
assert "under the floor of 40" in why, why
lines = D.recipe(table, rows + [row(30 + i, 1, 100, "one_detail", 1.0) for i in range(10)])
assert any(l.startswith("Never again") and "news_explained" in l for l in lines), lines
print("2 stop verdict ok")

# 3. the writer: a stopped arm or kind is never chosen, a dead Short is never remade
import writer as W
W.ROOT = SCRATCH; (SCRATCH / "analytics").mkdir(); (SCRATCH / "boards" / "done").mkdir(parents=True)
with (SCRATCH / "analytics" / "drivers.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["feature", "feature_label", "value", "n", "lift", "median_rel", "verdict", "why"]); w.writeheader()
    w.writerow({"feature": "hook_type", "feature_label": "Hook style", "value": "number", "n": 4, "lift": 0.1, "median_rel": 0.1, "verdict": "stop", "why": "x"})
    w.writerow({"feature": "kind", "feature_label": "Kind of Short", "value": "fiction", "n": 4, "lift": 0.1, "median_rel": 0.1, "verdict": "stop", "why": "x"})
    w.writerow({"feature": "category", "feature_label": "Category", "value": "Science", "n": 4, "lift": 0.1, "median_rel": 0.1, "verdict": "stop", "why": "x"})
    w.writerow({"feature": "category", "feature_label": "Category", "value": "Sport", "n": 6, "lift": 1.4, "median_rel": 1.2, "verdict": "push", "why": "x"})
assert W.stopped() == {"hook_type": {"number"}, "kind": {"fiction"}, "category": {"Science"}}
assert "number" not in W.arms("hook_type") and W.share("fiction", 3, 9) == 0 and W.share("news", 3, 9) == 3
b = W.boosts(); assert b["Science"] == W.STOP and b["Sport"] == 2
picks = [W.test_plan(k)[1].get("hook_type") for k in range(40)]
assert "number" not in picks and any(picks), picks
with (SCRATCH / "analytics" / "shorts.csv").open("w", newline="") as f:
    cols = ["short", "title", "posted", "posted_day", "yt_views", "views_vs_typical"]
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k: r.get(k, "") for k in cols} | {"views_vs_typical": "0.1" if r["short"] != "T-000" else "0.3"})
weak = [r["short"] for r in W.weak()]
assert "T-010" not in weak and "T-011" not in weak and "T-000" in weak, weak      # dead ones out; a weak but living one stays
print("3 writer stops ok")
print("stop rule ok")
