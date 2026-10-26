"""Offline test of pipeline/trend.py and the two alerts built on it (26 October): week-on-week medians, the rulings-followed
count and its worth, the retention flag, the hub's improvement line (history, write_history), alerts.trend_alert opening and
closing its issue, alerts.recipe_stale_check, and the insights section's text. No live file is read."""
import pathlib as _p, sys, os, json, csv, datetime as dt, tempfile
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

# 3. the improvement line (analytics/improvement.json, the hub's chart): a main Short a day for 10 days, two IRL Shorts,
# one too young to count, YouTube's engaged views for 18 to 23 October and two subscriber readings
H = [row(d, 50, 30 + d, views24=10 * d, views=1000, subs=2) for d in range(1, 11)]
IRL = [dict(row(d, 50, 20, views24=10, views=1000), short=f"QI-{d}", channel="irl") for d in (2, 3)]
YOUNG = [row(0, 90, 90, hours=3)]
DAILY = [{"day": f"2026-10-{18 + i}", "source": "youtube_daily", "yt_engaged_views_day": str(100 * (i + 1))} for i in range(6)]
DAILY += [{"day": "2026-10-20", "source": "snapshot", "yt_followers": "5"}, {"day": "2026-10-25", "source": "snapshot", "yt_followers": "16"}]
CH = [{"id": "CH-001", "date": "2026-09-01", "area": "shorts", "change": "too old"},
      {"id": "CH-096", "date": "2026-10-26", "area": "clips", "change": "x" * 500, "target": "engaged_share", "status": "live"},
      {"id": "", "date": "2026-10-25", "change": "no id"}]
DEC = [{"date": "2026-10-22", "area": "hook", "change": f"rule {i}"} for i in range(5)] + [{"date": "2026-10-01", "area": "old", "change": "x"}]
h = T.history(H + IRL + YOUNG, NOW, DAILY, CH, DEC)
D = h["days"]; ix = D.index
assert D[0] == "2026-10-16" and D[-1] == "2026-10-26" and len(D) == 11, D
assert set(h) == {"updated", "goal", "min_n", "metrics", "days", "channel", "shorts", "changes", "recipe"} and h["goal"] == T.YPP
assert [m["key"] for m in h["metrics"]] == ["engaged_day", "engaged_90d", "subscribers", "engaged_pct", "engaged_24h",
                                            "views_24h", "viewed_pct", "subs_per_1k"], h["metrics"]
assert len(T.history(H, NOW, days=5)["days"]) == 5
c = h["channel"]
assert all(len(v) == 11 for v in c.values()), c
assert c["engaged_day"][ix("2026-10-19")] == 200 and c["engaged_day"][ix("2026-10-24")] is None
assert c["engaged_day_7d"][ix("2026-10-18")] is None and c["engaged_day_7d"][ix("2026-10-20")] == 200   # 3 days needed
assert c["engaged_day_7d"][ix("2026-10-23")] == 350 and c["engaged_day_7d"][ix("2026-10-24")] is None   # stops at the last reported day
assert c["engaged_90d"][ix("2026-10-23")] == 2100 and c["engaged_90d"][ix("2026-10-17")] is None and c["engaged_90d"][-1] is None
assert c["subscribers"][ix("2026-10-20")] == 5 and c["subscribers"][ix("2026-10-25")] == 16 and c["subscribers"][ix("2026-10-21")] is None
S = h["shorts"]
assert set(S) == {"all", "main", "irl"} and set(T.history([], NOW)["shorts"]) == {"all"}, set(S)   # empty groups skipped, "all" kept
m = S["main"]
assert m["posted"][-1] == 0 and m["posted"][ix("2026-10-25")] == 1 and S["all"]["posted"][ix("2026-10-24")] == 2   # 24 hours old only
assert m["engaged_pct"]["week"][-1] == 33.5 and m["engaged_pct"]["n"][-1] == 6, m["engaged_pct"]            # the 6 main Shorts of 20 to 25 October
assert m["engaged_pct"]["day"][ix("2026-10-25")] == 31 and m["engaged_pct"]["day"][-1] is None
assert m["engaged_pct"]["week"][1] is None and m["engaged_pct"]["week"][2] == 39.0                          # under 3 measured: no line
assert S["all"]["engaged_pct"]["week"][-1] == 32.5 and S["irl"]["engaged_pct"]["day"][ix("2026-10-23")] == 20
assert m["views_24h"]["week"][-1] == 35.0 and m["subs_per_1k"]["week"][-1] == 2.0 and m["engaged_24h"]["day"][ix("2026-10-25")] == 3.1
assert [x["id"] for x in h["changes"]] == ["CH-096"] and len(h["changes"][0]["change"]) == 400, h["changes"]
assert h["recipe"] == {"2026-10-22": {"n": 5, "items": [f"hook: rule {i}" for i in range(4)]}}, h["recipe"]
assert not any(ch in "".join(x["label"] + x["note"] for x in h["metrics"]) for ch in DASHES)
tmpH = _p.Path(tempfile.mkdtemp(prefix="qp-improve-"))
for name, rs in (("shorts.csv", H + IRL + YOUNG), ("daily.csv", DAILY), ("changes.csv", CH)):
    keys = list(dict.fromkeys(k for r in rs for k in r))
    with open(tmpH / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, restval=""); w.writeheader(); w.writerows(rs)
p = T.write_history(NOW, src=tmpH)                                                     # no decisions.csv: an empty recipe
J = json.loads(p.read_text(encoding="utf-8"))
assert p.name == "improvement.json" and J["days"] == D and J["recipe"] == {} and set(J["shorts"]) == {"all", "main", "irl"}, (p, set(J["shorts"]))
assert J["shorts"]["main"]["engaged_pct"]["week"][-1] == 33.5 and J["channel"]["engaged_90d"][ix("2026-10-23")] == 2100
print("3 improvement line ok")

# 4. the alerts: trend_alert opens with the numbers and the suspects and closes when fine; recipe_stale_check reads summary.json
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
print("4 alerts ok")
print("trend ok")
