"""Offline test of pipeline/trend.py and the two alerts built on it (26 October): week-on-week medians, the rulings-followed
count and its worth, the retention flag, alerts.trend_alert opening and closing its issue, alerts.recipe_stale_check, and
the insights section's text. No live file is read."""
import pathlib as _p, sys, os, json, datetime as dt, tempfile
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import trend as T, alerts as A

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
DASHES = ("–", "—")


def row(days_ago, viewed, engaged, views24=100, views=200, subs=0, fmt="one_detail", cat="Music", hours=0):
    posted = (NOW - dt.timedelta(days=days_ago, hours=hours)).isoformat()
    return {"short": f"QD-{days_ago}-{hours}-{viewed}-{cat}", "posted": posted, "title": "A title", "hook": "A hook.", "category": cat,
            "format": fmt, "mood": "pop", "yt_views": views, "views_24h": views24, "yt_avg_viewed_pct": viewed,
            "yt_engaged_pct": engaged, "yt_subs_gained": subs}


# 1. two clean weeks: the week before at 55% viewed and 30% engaged, this week at 40% and 24% (a fall); one Short too young to count
last = [row(d, 55, 30, views24=80, subs=1) for d in range(8, 14) for _ in range(2)]
this = [row(d, 40, 24, views24=120 if i % 2 else 60, cat="Tech" if d == 2 else "Music") for d in range(1, 7) for i in range(2)]
young = [row(0, 90, 90, hours=3)]
V = {"format": {"one_detail": "push"}, "category": {"Tech": "cut back"}}
t = T.trend(last + this + young, NOW, V)
assert t["this"]["n"] == 12 and t["last"]["n"] == 12, (t["this"], t["last"])           # the 3-hour-old Short is not counted
assert t["this"]["yt_avg_viewed_pct"] == 40 and t["last"]["yt_avg_viewed_pct"] == 55
assert t["change"]["yt_avg_viewed_pct"] == 0.73 and t["change"]["yt_engaged_pct"] == 0.8, t["change"]
assert t["last"]["subs_per_1k"] == 5.0 and t["this"]["subs_per_1k"] == 0.0, (t["last"], t["this"])    # 12 subscribers from 2,400 views
assert len(t["flags"]) == 2 and t["flags"][0].startswith("Share of the Short viewed (%) down 27%"), t["flags"]
assert t["followed"] == {"n": 10, "of": 12, "lift": 1.0}, t["followed"]             # the two Tech Shorts carry a cut-back choice
L = T.lines(t)
assert L[0].startswith("## Is the channel getting better") and any("followed the data's rulings: 10 of 12, 1.0x" in x for x in L), L
assert sum(1 for x in L if x.startswith("- Watch:")) == 2 and not any(c in "\n".join(L) for c in DASHES)
few = T.trend(last[:4] + this[:4], NOW, V)
assert few["flags"] == [] and "Too early" not in "\n".join(T.lines(few))             # 4 and 4 Shorts: enough to show, not to flag
assert "Too early" in "\n".join(T.lines(T.trend(last[:2], NOW)))
print("1 trend ok")

# 2. falling: the last 3 days against the 7 days before them
before = [row(d, 55, 30) for d in range(4, 10) for _ in range(2)]
recent = [row(d, 40, 24, hours=h) for d in (1, 2) for h in (0, 6, 12, 18)] + [row(3, 40, 24)]
f = T.falling(before + recent, NOW)
assert [x[0] for x in f] == ["Share of the Short viewed (%)", "Engaged views (% of views)"] and f[0][1:] == (40.0, 55.0, 9, 12), f
assert T.falling(before + recent[:7], NOW) == []                                      # 7 recent Shorts: too few to say
fine = before + [row(d, 52, 29, hours=h) for d in (1, 2) for h in (0, 6, 12, 18)] + [row(3, 52, 29)]
assert T.falling(fine, NOW) == []
print("2 falling ok")

# 3. the alerts: trend_alert opens with the numbers and the suspects and closes when fine; recipe_stale_check reads summary.json
RAISED, CLOSED, BODIES = [], [], []
A.raise_issue = lambda title, body, labels=None, howto=None: (RAISED.append(title), BODIES.append(body))
A.clear = lambda title, body: CLOSED.append(title)
A.NOW = NOW
T.load_rows = lambda path=None: before + recent
T.recent_changes = lambda days=10, now=None, path=None: [{"id": "CH-090", "date": "2026-10-24", "area": "shorts",
                                                           "change": "every picture fills the screen", "status": "live"}]
A.trend_alert()
assert RAISED == ["📉 Retention is falling: viewers leave the Shorts sooner than last week"], RAISED
assert "40.0 over the last 9 Shorts (3 days), 55.0 over the 12 Shorts" in BODIES[0] and "CH-090" in BODIES[0], BODIES[0]
T.load_rows = lambda path=None: fine
A.trend_alert()
assert CLOSED == RAISED, CLOSED
tmp = _p.Path(tempfile.mkdtemp(prefix="qp-trend-")); (tmp / "analytics").mkdir()
A.ROOT = tmp
RAISED.clear(); CLOSED.clear()
summary = tmp / "analytics" / "summary.json"
summary.write_text(json.dumps({"updated": NOW.isoformat(), "full_updated": (NOW - dt.timedelta(hours=20)).isoformat()}))
A.recipe_stale_check()
assert RAISED == [f"⚠️ The recipe has not refreshed for over {A.RECIPE_STALE_HOURS} hours (the full analytics run inside trends)"] and "20 hours ago" in BODIES[-1], (RAISED, BODIES[-1])
summary.write_text(json.dumps({"updated": NOW.isoformat(), "full_updated": (NOW - dt.timedelta(hours=2)).isoformat()}))
A.recipe_stale_check()
assert CLOSED == RAISED, CLOSED
summary.unlink(); RAISED.clear(); CLOSED.clear()
A.recipe_stale_check()
assert RAISED == [] and CLOSED == []                                                   # no summary yet: nothing to say
assert not any(c in "\n".join(BODIES) for c in DASHES)
print("3 alerts ok")
print("trend ok")
