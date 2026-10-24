"""Offline test of the fewer-better test (Charlie, 23 October): 15 Shorts a day is the target under the learned ceiling.
24 October: judged after 14 days on each UK day's views and the day's Shorts' 24-hour views, with intervals (the data
report): kept unless both are clearly lower."""
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
# the allowance keeps room for the planned Shorts still to come today (target, 15), not the ceiling (40): 24 October
_root = Q.ROOT; Q.ROOT = SCRATCH / "q"; (Q.ROOT / "status").mkdir(parents=True)
for i in range(5): (Q.ROOT / "status" / f"QD-9{i:02d}.json").write_text(json.dumps({"uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat()}))
assert Q.uploads_left() == 15 + 1 - 5, Q.uploads_left()
Q.ROOT = _root

A.ROOT, A.OUT = SCRATCH, SCRATCH / "analytics"; A.OUT.mkdir(); (SCRATCH / "status").mkdir()
A.CFG = dict(A.CFG, volume_test={"start": "2026-10-24", "days": 14, "per_day": 15, "before": 40, "ledger": "CH-011"})
import changes as CH
CH.ROOT = SCRATCH
CH.save([{"id": "CH-011", "date": "2026-10-24", "area": "shorts", "change": "Fewer, better: 15 a day", "hypothesis": "h",
          "target": "yt_views_day", "guardrails": "", "before_days": "7", "after_days": "7", "check_on": "2026-10-31", "status": "live",
          "verdict": "", "result": "", "by": "Claude"}])
import random as _r


def days(before, during, noise=0.0, seed=1):
    """hourly.csv and shorts.csv for 10 October to 8 November (UK days): before 24 October 24 Shorts a day, then 15;
    `before` and `during` are (daily views, 24-hour views a Short), each day's numbers jittered by `noise`."""
    rng = _r.Random(seed)
    hours, shorts, d, k = ["hour_utc,uk_day,uk_hour,uk_weekday,hours,yt_total,yt_gained"], ["short,posted,views_24h"], dt.date(2026, 10, 10), 0
    while d <= dt.date(2026, 11, 8):
        dv, per = before if d < dt.date(2026, 10, 24) else during
        n = 24 if d < dt.date(2026, 10, 24) else 15
        j = 1 + rng.uniform(-noise, noise)
        for h in range(24): hours.append(f"{d}T{h:02d}:00Z,{d},{h},Mon,1,0,{dv * j / 24:.1f}")
        for i in range(n):
            k += 1; shorts.append(f"QD-{k:03d},{d}T{10 + i // 4:02d}:{(i % 4) * 15:02d}:00+00:00,{per * j:.0f}")
        d += dt.timedelta(days=1)
    (A.OUT / "hourly.csv").write_text("\n".join(hours) + "\n"); (A.OUT / "shorts.csv").write_text("\n".join(shorts) + "\n")


# 1. while it runs: the reading so far, the test number kept, the ledger row moved to the judging day
days((3000, 60), (3100, 100))
v = A.volume_test(dt.date(2026, 10, 30))
assert v["verdict"] is None and v["per_day"] == 15 and "day 6 of 14" in v["why"], v
assert v["reading"]["shorts_a_day"] == {"during": 15, "before": 24} and v["reading"]["daily_views"]["days"] == [6, 14], v["reading"]
assert json.loads((SCRATCH / "status" / "volume.json").read_text())["per_day"] == 15
row = CH.load()[0]; assert row["check_on"] == "2026-11-08" and row["after_days"] == "14" and row["status"] == "live", row
# 2. judged on 8 November: views held (cohort of 15 at 100 against 24 at 60 is about 1.04x), so 15 stays
v = A.volume_test(dt.date(2026, 11, 8))
assert v["verdict"] == "kept" and v["per_day"] == 15, v
assert 0.95 <= v["reading"]["daily_views"]["ratio"] <= 1.1 and v["reading"]["median_24h_per_short"] == {"during": 100.0, "before": 60.0}, v["reading"]
assert "Keep 15" in (A.OUT / "decisions.csv").read_text()
row = CH.load()[0]; assert row["status"] == "checked" and row["verdict"] == "no change" and "volume test kept" in row["result"], row
assert A.volume_test(dt.date(2026, 11, 9)) is None                         # judged once
# 3. clearly fewer views a day and from the day's Shorts: back to the 24 a day before
(SCRATCH / "status" / "volume.json").unlink()
CH.save([{**CH.load()[0], "status": "live", "verdict": "", "result": ""}])
days((3000, 60), (1800, 60), noise=0.1)
v = A.volume_test(dt.date(2026, 11, 8))
assert v["verdict"] == "back" and v["per_day"] == 24 and v["reading"]["daily_views"]["hi"] < 0.9, v
assert CH.load()[0]["verdict"] == "worse"
# 4. lower on average but too noisy to be clear: 15 stays (the 7-day ratio would have gone back on 0.85)
(SCRATCH / "status" / "volume.json").unlink()
days((3000, 60), (2550, 60), noise=0.6, seed=4)
v = A.volume_test(dt.date(2026, 11, 8))
assert v["verdict"] == "kept" and v["reading"]["daily_views"]["hi"] >= 0.9, v
# 5. too few measured days on the judging day: extended, nothing decided
(SCRATCH / "status" / "volume.json").unlink(); (A.OUT / "hourly.csv").write_text("hour_utc,uk_day,uk_hour,uk_weekday,hours,yt_total,yt_gained\n")
v = A.volume_test(dt.date(2026, 11, 8))
assert v["verdict"] is None and v["why"].startswith("extended"), v
# 6. the interval helper: a constant ratio has a zero-width interval
r = A.ratio_ci([2.0] * 5, [1.0] * 5)
assert r["ratio"] == 2.0 and r["lo"] == 2.0 and r["hi"] == 2.0 and r["days"] == [5, 5], r
assert A.ratio_ci([], [1.0]) is None and A.ratio_ci([1.0], [0.0]) is None
print("volume ok")
