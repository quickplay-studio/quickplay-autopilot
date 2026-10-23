"""Offline test of the fewer-better test (Charlie, 23 October): 15 Shorts a day is the target under the learned ceiling,
and after 7 days the channel's daily views decide whether it stays or goes back to 40."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import quota as Q, analytics as A

Q.VOLUME_P = SCRATCH / "volume.json"; Q.LIMIT_P = SCRATCH / "limit.json"
Q.CFG = dict(Q.CFG, daily_limit=40, shorts_per_day=15)
assert Q.daily_limit() == 40 and Q.target() == 15
Q.VOLUME_P.write_text(json.dumps({"per_day": 40})); assert Q.target() == 40
Q.LIMIT_P.write_text(json.dumps({"limit": 12})); Q.VOLUME_P.unlink(); assert Q.target() == 12     # never above what YouTube allows
Q.LIMIT_P.unlink()

A.ROOT, A.OUT = SCRATCH, SCRATCH / "analytics"; A.OUT.mkdir(); (SCRATCH / "status").mkdir()
A.CFG = dict(A.CFG, volume_test={"start": "2026-10-24", "days": 7, "per_day": 15, "before": 40})
def daily(before_a_day, during_a_day):
    rows, total = ["day,source,yt_views_total"], 10000
    d = dt.date(2026, 10, 17)
    while d <= dt.date(2026, 11, 1):
        rows.append(f"{d},snapshot,{total}"); total += before_a_day if d < dt.date(2026, 10, 24) else during_a_day; d += dt.timedelta(days=1)
    (A.OUT / "daily.csv").write_text("\n".join(rows) + "\n")
daily(3000, 3200)
assert A.volume_test(dt.date(2026, 10, 30)) is None                      # still running
v = A.volume_test(dt.date(2026, 11, 1))
assert v["per_day"] == 15 and v["verdict"] == "kept" and v["views_a_day_before"] == 3000, v
assert "Keep 15" in (A.OUT / "decisions.csv").read_text()
assert A.volume_test(dt.date(2026, 11, 2)) is None                        # judged once
(SCRATCH / "status" / "volume.json").unlink(); daily(3000, 2000)
assert A.volume_test(dt.date(2026, 11, 1))["per_day"] == 40               # views fell a third: back to 40
print("volume ok")
