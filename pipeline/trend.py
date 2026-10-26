"""Is the channel getting better? (Charlie, 26 October: "make sure the improvement model is being implemented and constantly
improved with data".)

The drivers (drivers.py) judge every choice against the Shorts posted around it, which is right for telling choices apart
and blind to anything that lifts or sinks every Short alike: a render or voice change on every Short, a YouTube shift, a
recipe that has narrowed too far. This module watches the absolute numbers week on week (views at 24 hours, the share of
the Short viewed, engaged views, subscribers per 1,000 views), counts the Shorts that followed the data's rulings and what
that was worth, and flags a fall in retention, for insights.md ("Is the channel getting better") and alerts.py
(trend_alert). Pure functions over shorts.csv rows with the clock passed in, so the tests read no live file.
  python pipeline/trend.py        prints the section for the live analytics/shorts.csv
  python pipeline/trend.py --history    writes analytics/improvement.json (the hub's improvement line; analytics.py does it every run)
"""
import csv, datetime as dt, json, pathlib, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
WEEK, RECENT_DAYS = 7, 3
FALL = 0.85                  # a metric at 85% of the earlier window or less counts as falling
MIN_WEEK, MIN_RECENT = 10, 8     # Shorts needed in the earlier window, and in the last RECENT_DAYS days, before a flag
# (shorts.csv column, label, how the window is summed up)
METRICS = (("views_24h", "Views at 24 hours", "median"), ("yt_avg_viewed_pct", "Share of the Short viewed (%)", "median"),
           ("yt_engaged_pct", "Engaged views (% of views)", "median"), ("subs_per_1k", "Subscribers per 1,000 views", "rate"))
RETENTION = METRICS[1:3]     # the two a change in the Shorts themselves moves first


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def utc(s):
    t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def load_rows(path=None):
    p = pathlib.Path(path or ROOT / "analytics" / "shorts.csv")
    try: return list(csv.DictReader(p.open(encoding="utf-8")))
    except OSError: return []


def verdicts(path=None):
    """{feature: {value: verdict}} from analytics/drivers.csv."""
    out = {}
    for r in load_rows(path or ROOT / "analytics" / "drivers.csv"):
        out.setdefault(r.get("feature"), {})[r.get("value")] = r.get("verdict")
    return out


def aged(rows, now, hours=24):
    """(posted, row) for the Shorts public for `hours` or more."""
    out = []
    for r in rows:
        try: t = utc(r.get("posted"))
        except (TypeError, ValueError): continue
        if (now - t).total_seconds() >= hours * 3600: out.append((t, r))
    return out


def window(rows, now, days=WEEK, offset=0):
    """The Shorts posted in the `days` days ending `offset` days ago, public 24 hours or more."""
    end = now - dt.timedelta(days=offset)
    start = end - dt.timedelta(days=days)
    return [r for t, r in aged(rows, now) if start <= t < end]


def medians(rs):
    """{metric: value} over a window: medians, and subscribers gained per 1,000 views as one rate; None without data."""
    out = {"n": len(rs)}
    for k, _label, kind in METRICS:
        if kind == "rate":
            subs = sum(_f(r.get("yt_subs_gained")) or 0 for r in rs)
            views = sum(_f(r.get("yt_views")) or 0 for r in rs)
            out[k] = round(1000 * subs / views, 2) if views else None
        else:
            v = [_f(r.get(k)) for r in rs if _f(r.get(k)) is not None]
            out[k] = round(statistics.median(v), 1) if v else None
    return out


def followed(r, verdicts):
    """Whether a Short's choices follow the data: at least one "push" choice and no "cut back", paused or stopped one (the
    weekly report's measure since 21 October, here for every day)."""
    try:
        import drivers
        feats = drivers.features(r)
    except Exception:
        return False
    vs = [verdicts.get(k, {}).get(val) for k, val in feats.items() if val]
    return ("push" in vs) and not any(x in ("cut back", "stop", "pause") for x in vs)


def trend(rows, now, verdicts=None):
    """This week against the week before: {this, last, change: {metric: ratio}, followed: {n, of, lift}, flags: [text]}."""
    this, last = window(rows, now), window(rows, now, offset=WEEK)
    t = {"this": medians(this), "last": medians(last), "change": {}, "flags": []}
    for k, _label, _kind in METRICS:
        a, b = t["this"].get(k), t["last"].get(k)
        if a is not None and b: t["change"][k] = round(a / b, 2)
    if verdicts:
        fol = [r for r in this if followed(r, verdicts)]
        rest = [r for r in this if r not in fol]
        t["followed"] = {"n": len(fol), "of": len(this)}
        a, b = medians(fol).get("views_24h"), medians(rest).get("views_24h")
        if fol and rest and a is not None and b: t["followed"]["lift"] = round(a / b, 2)
    if t["this"]["n"] >= MIN_WEEK and t["last"]["n"] >= MIN_WEEK:
        for k, label, _kind in RETENTION:
            c = t["change"].get(k)
            if c is not None and c <= FALL:
                t["flags"].append(f"{label} down {round(100 * (1 - c))}% on the week before ({t['this'][k]} against {t['last'][k]} "
                                  f"over {t['this']['n']} and {t['last']['n']} Shorts)")
    return t


def falling(rows, now):
    """The retention check behind alerts.trend_alert: the last RECENT_DAYS days' Shorts against the 7 days before them, on the
    share viewed and engaged views. [(label, recent, before, n_recent, n_before)] for each that fell to FALL or less; [] when
    fine, or with fewer than MIN_RECENT recent or MIN_WEEK earlier Shorts."""
    recent, before = window(rows, now, days=RECENT_DAYS), window(rows, now, days=WEEK, offset=RECENT_DAYS)
    if len(recent) < MIN_RECENT or len(before) < MIN_WEEK: return []
    a, b = medians(recent), medians(before)
    return [(label, a[k], b[k], len(recent), len(before)) for k, label, _kind in RETENTION
            if a.get(k) is not None and b.get(k) and a[k] / b[k] <= FALL]


def recent_changes(days=10, now=None, path=None):
    """The ledger's changes (analytics/changes.csv) of the last `days` days: the suspects when retention falls."""
    now = now or dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=days)).date().isoformat()
    return [r for r in load_rows(path or ROOT / "analytics" / "changes.csv")
            if (r.get("date") or "") >= since and r.get("status") != "reverted"]


def lines(t):
    """The insights.md section, for the writer's reviewers and the weekly review."""
    L = ["## Is the channel getting better (this week against the week before; Shorts public 24 hours or more)"]
    if t["this"]["n"] < 3 or t["last"]["n"] < 3:
        return L + [f"- Too early to say: {t['this']['n']} Shorts this week, {t['last']['n']} the week before.", ""]
    for k, label, _kind in METRICS:
        a, b, c = t["this"].get(k), t["last"].get(k), t["change"].get(k)
        if a is None and b is None: continue
        word = "" if c is None else (" (up)" if c >= 1.1 else " (down)" if c <= 0.9 else " (level)")
        L.append(f"- {label}: {a if a is not None else '?'} this week, {b if b is not None else '?'} the week before{word}.")
    f = t.get("followed")
    if f and f.get("of"):
        L.append(f"- Shorts that followed the data's rulings: {f['n']} of {f['of']}"
                 + (f", {f['lift']}x the 24-hour views of the rest." if f.get("lift") else "."))
    for x in t["flags"]:
        L.append(f"- Watch: {x}. The drivers cannot see a fall that hits every Short alike; the review checks the changes of the "
                 f"last 10 days (analytics/changes.csv) and reverts what hurt.")
    L.append(f"- Shorts measured: {t['this']['n']} this week, {t['last']['n']} the week before.")
    return L + [""]


# The improvement line (Charlie, 26 October: "implement the improvement line / history of improvement within the dashboard to
# show the improvement visually"): analytics/improvement.json, the hub's Overview chart "Getting better?". One value a UK day
# for each number the goal moves, with every ledger change (changes.csv) and the Recipe's automatic changes (decisions.csv)
# on the same days, so a change can be read against the line after it. Written by analytics.py on every run.
HISTORY_DAYS = 120          # days kept in the file
MIN_N = 3                   # Shorts needed in a 7-day window before its median is drawn
GROUPS = ("all", "main", "clips", "irl", "gaming")
YPP = {"subs": 500, "views": 3_000_000, "subs_2027": 1000, "shorts_pool_2027": 10_000_000, "views_2027": 20_000_000,
       "from_2027": "2027-02-01"}
_ENG = ["yt_views_day", "uploads_day", "engaged_share", "feed_pick", "held_3s"]
# (key, label, unit, scope, the ledger targets that aim at it, what it shows)
HISTORY = (
    ("engaged_day", "Engaged views a day", "views", "channel", _ENG,
     "Quickplay Daily's engaged views each day, YouTube's own figure (about 3 days behind): the views the Partner Programme counts."),
    ("engaged_90d", "Engaged views, last 90 days", "views", "channel", _ENG,
     "The Partner Programme's count for Quickplay Daily: 3M in 90 days for the expanded tier; from 1 February 2027, 10M in the Shorts pool."),
    ("subscribers", "Subscribers", "subscribers", "channel", ["subs_per_1k"],
     "Quickplay Daily's subscribers at each day's last reading: 500 for the expanded tier, 1,000 for full YPP."),
    ("engaged_pct", "Views that stayed past the opening (%)", "%", "short", ["engaged_share", "held_3s"],
     "Median engaged share per Short: the hook's job. About a third now; every point here multiplies every view."),
    ("engaged_24h", "Engaged views per Short at 24 hours", "views", "short", ["engaged_share", "yt_views_24h", "yt_rel"],
     "Median per Short: views at 24 hours times its engaged share (an estimate; the share is YouTube's, about 3 days behind)."),
    ("views_24h", "Views per Short at 24 hours", "views", "short", ["yt_views_24h", "yt_rel", "feed_pick", "dead_share"],
     "Median per Short, from the hourly counts."),
    ("viewed_pct", "Share of the Short viewed (%)", "%", "short", ["avg_viewed_pct", "held_3s"],
     "Median per Short: how much of each Short people watch."),
    ("subs_per_1k", "Subscribers per 1,000 views", "subscribers", "short", ["subs_per_1k"],
     "Subscribers gained over views, across the Shorts in the window."),
)


def _uk_day(t):
    try:
        import zoneinfo
        return t.astimezone(zoneinfo.ZoneInfo("Europe/London")).date()
    except Exception:
        return t.astimezone(dt.timezone.utc).date()


def _short_value(key, rs):
    """One per-Short metric over a set of Shorts: the median (subscribers per 1,000 views: one rate); None without data."""
    if key == "subs_per_1k":
        rs = [r for r in rs if _f(r.get("yt_views"))]
        views = sum(_f(r.get("yt_views")) for r in rs)
        return round(1000 * sum(_f(r.get("yt_subs_gained")) or 0 for r in rs) / views, 2) if views else None
    col = {"engaged_pct": "yt_engaged_pct", "viewed_pct": "yt_avg_viewed_pct", "views_24h": "views_24h"}.get(key)
    if col: v = [_f(r.get(col)) for r in rs if _f(r.get(col)) is not None]
    else:       # engaged_24h: views at 24 hours times the engaged share
        v = [_f(r.get("views_24h")) * _f(r.get("yt_engaged_pct")) / 100 for r in rs
             if _f(r.get("views_24h")) is not None and _f(r.get("yt_engaged_pct")) is not None]
    return round(statistics.median(v), 1) if v else None


def _measured(key, r):
    """Whether a Short carries the numbers `key` is made of (the window's n counts these only)."""
    need = {"engaged_pct": ("yt_engaged_pct",), "viewed_pct": ("yt_avg_viewed_pct",), "views_24h": ("views_24h",),
            "engaged_24h": ("views_24h", "yt_engaged_pct"), "subs_per_1k": ("yt_views", "yt_subs_gained")}[key]
    return all(_f(r.get(c)) is not None for c in need)


def history(rows, now, daily=None, changes=None, decisions=None, days=HISTORY_DAYS):
    """The improvement line's data (analytics/improvement.json): {updated, goal, metrics, days, channel, shorts, changes, recipe}.
    days: the UK days from the first Short or daily figure to today (the last `days`). channel: Quickplay Daily's own series
    from daily.csv, a value or None for each day (engaged views a day and its 7-day average, the 90-day engaged total over the
    days YouTube has reported, subscribers). shorts: per channel group (all, main, clips, irl, gaming) and per-Short metric,
    "day" (that day's Shorts) and "week" (the 7 days ending that day, the line, None under MIN_N Shorts measured) and "n" (the week's
    Shorts measured), over Shorts public 24 hours or more by `now`; the group's "n" counts the week's Shorts, "posted" the day's. changes: every ledger row (id, date, area,
    change, target, status, verdict, result). recipe: {day: {"n", "items"}} for the Recipe's automatic changes."""
    today = _uk_day(now)
    public = []
    for t, r in aged(rows, now):
        public.append((_uk_day(t), r))
    daily = daily or []
    starts = [d for d, _ in public] + [dt.date.fromisoformat(h["day"]) for h in daily if (h.get("day") or "")[:4].isdigit()]
    first = max(min(starts, default=today), today - dt.timedelta(days=days - 1))
    span = [first + dt.timedelta(days=i) for i in range((today - first).days + 1)]
    out = {"updated": now.isoformat(timespec="minutes"), "goal": YPP, "min_n": MIN_N,
           "metrics": [{"key": k, "label": lab, "unit": u, "scope": s, "targets": tg, "note": note}
                       for k, lab, u, s, tg, note in HISTORY],
           "days": [d.isoformat() for d in span]}
    # Quickplay Daily's own daily figures (daily.csv): YouTube's engaged views a day and the subscriber snapshots
    eng = {h["day"]: _f(h.get("yt_engaged_views_day")) for h in daily if h.get("source") == "youtube_daily"}
    subs = {h["day"]: _f(h.get("yt_followers")) for h in daily if h.get("source") == "snapshot" and _f(h.get("yt_followers")) is not None}
    all_eng = sorted((d, v) for d, v in eng.items() if v is not None)
    ch = {"engaged_day": [], "engaged_day_7d": [], "engaged_90d": [], "subscribers": []}
    for d in span:
        ds = d.isoformat()
        ch["engaged_day"].append(eng.get(ds))
        last7 = [eng[x.isoformat()] for x in (d - dt.timedelta(days=i) for i in range(7)) if eng.get(x.isoformat()) is not None]
        reported = bool(all_eng) and all_eng[0][0] <= ds <= all_eng[-1][0]     # YouTube has reported up to this day
        ch["engaged_day_7d"].append(round(sum(last7) / len(last7)) if reported and len(last7) >= MIN_N else None)
        lo = (d - dt.timedelta(days=89)).isoformat()
        win = [v for x, v in all_eng if lo <= x <= ds]
        ch["engaged_90d"].append(round(sum(win)) if reported else None)
        ch["subscribers"].append(subs.get(ds))
    out["channel"] = ch
    shorts = {}
    for g in GROUPS:
        mine = [(d, r) for d, r in public if g == "all" or (r.get("channel") or "main") == g]
        if g != "all" and not mine: continue
        by_day = {}
        for d, r in mine: by_day.setdefault(d, []).append(r)
        gs = {"n": [], "posted": [sum(1 for d2, _ in mine if d2 == d) for d in span]}
        for k, _lab, _u, scope, _tg, _note in HISTORY:
            if scope != "short": continue
            gs[k] = {"day": [], "week": [], "n": []}
        for d in span:
            week = [r for x in range(7) for r in by_day.get(d - dt.timedelta(days=x), [])]
            gs["n"].append(len(week))
            for k in gs:
                if k in ("n", "posted"): continue
                dm = [r for r in by_day.get(d, []) if _measured(k, r)]
                wm = [r for r in week if _measured(k, r)]
                gs[k]["day"].append(_short_value(k, dm) if dm else None)
                gs[k]["week"].append(_short_value(k, wm) if len(wm) >= MIN_N else None)
                gs[k]["n"].append(len(wm))
        shorts[g] = gs
    out["shorts"] = shorts
    lo = span[0].isoformat()
    out["changes"] = [{k: (r.get(k) or "")[:400] for k in ("id", "date", "area", "change", "target", "status", "verdict", "result")}
                      for r in (changes or []) if (r.get("date") or "") >= lo and r.get("id")]
    rec = {}
    for r in decisions or []:
        d = r.get("date") or ""
        if d < lo: continue
        x = rec.setdefault(d, {"n": 0, "items": []})
        x["n"] += 1
        if len(x["items"]) < 4: x["items"].append(f"{r.get('area', '')}: {r.get('change', '')}"[:160])
    out["recipe"] = rec
    return out


def write_history(now=None, out=None, src=None):
    """Write improvement.json from the analytics files in `src` (analytics/ by default) beside them; the path written."""
    now = now or dt.datetime.now(dt.timezone.utc)
    a = pathlib.Path(src or ROOT / "analytics")
    h = history(load_rows(a / "shorts.csv"), now, load_rows(a / "daily.csv"), load_rows(a / "changes.csv"),
                load_rows(a / "decisions.csv"))
    p = pathlib.Path(out or a / "improvement.json")
    p.write_text(json.dumps(h, separators=(",", ":"), ensure_ascii=False))
    return p


if __name__ == "__main__":
    if "--history" in sys.argv: print(write_history())
    else: print("\n".join(lines(trend(load_rows(), dt.datetime.now(dt.timezone.utc), verdicts()))))
