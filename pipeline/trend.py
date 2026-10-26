"""Is the channel getting better? (Charlie, 26 October: "make sure the improvement model is being implemented and constantly
improved with data".)

The drivers (drivers.py) judge every choice against the Shorts posted around it, which is right for telling choices apart
and blind to anything that lifts or sinks every Short alike: a render or voice change on every Short, a YouTube shift, a
recipe that has narrowed too far. This module watches the absolute numbers week on week (views at 24 hours, the share of
the Short viewed, engaged views, subscribers per 1,000 views), counts the Shorts that followed the data's rulings and what
that was worth, and flags a fall in retention, for insights.md ("Is the channel getting better") and alerts.py
(trend_alert). Pure functions over shorts.csv rows with the clock passed in, so the tests read no live file.
  python pipeline/trend.py        prints the section for the live analytics/shorts.csv
"""
import csv, datetime as dt, pathlib, statistics, sys

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


if __name__ == "__main__":
    print("\n".join(lines(trend(load_rows(), dt.datetime.now(dt.timezone.utc), verdicts()))))
