"""Is the channel getting better? (Charlie, 26 October: "make sure the improvement model is being implemented and constantly
improved with data".)

The drivers (drivers.py) judge every choice against the Shorts posted around it, which is right for telling choices apart
and blind to anything that lifts or sinks every Short alike: a render or voice change on every Short, a YouTube shift, a
recipe that has narrowed too far. This module watches the absolute numbers week on week (views at 24 hours, the share of
the Short viewed, engaged views, subscribers per 1,000 views), counts the Shorts that followed the data's rulings and what
that was worth, and flags a fall in retention, for insights.md ("Is the channel getting better") and alerts.py
(trend_alert). Pure functions over shorts.csv rows with the clock passed in, so the tests read no live file.
Topic heat (27 October, Charlie: "content may be performing well because its trending, so any bad performance may not be
because of changes made"): each window's Shorts carry their topics' heat (heat.py, shorts.csv "heat"); when one week's topics
ran hotter or colder than the other's, the section and the retention issue say so, with what a point of heat has been worth
in views, so a rise or fall is not read as the changes' doing when the topics explain it.
  python pipeline/trend.py        prints the section for the live analytics/shorts.csv
  python pipeline/trend.py --history    writes analytics/improvement.json (the hub's improvement line; analytics.py does it every run)
"""
import csv, datetime as dt, json, math, pathlib, random, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
WEEK, RECENT_DAYS = 7, 3
FALL = 0.85                  # a metric at 85% of the earlier window or less counts as falling
MIN_WEEK, MIN_RECENT = 10, 8     # Shorts needed in the earlier window, and in the last RECENT_DAYS days, before a flag
# (shorts.csv column, label, how the window is summed up)
METRICS = (("views_24h", "Views at 24 hours", "median"), ("yt_avg_viewed_pct", "Share of the Short viewed (%)", "median"),
           ("yt_engaged_pct", "Engaged views (% of views)", "median"), ("subs_per_1k", "Subscribers per 1,000 views", "rate"))
RETENTION = METRICS[1:3]     # the two a change in the Shorts themselves moves first
HEAT_SHIFT = 0.3             # a change in the windows' mean topic heat this big is named beside the numbers


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


def _heat():
    try:
        import heat
        return heat
    except Exception:
        return None


def _logviews(r):
    import math
    v = _f(r.get("views_24h"))
    return None if v is None else math.log(max(0.05, v))


def heat_shift(rows_a, rows_b, every=None):
    """How much hotter (+) or colder (-) rows_b's topics ran than rows_a's: {"shift", "per_point"} or None. "per_point" is what one
    point of heat has been worth in 24-hour views against the same day's other Shorts (fitted on `every`, all the Shorts), only
    when that is clear; None without 3 covered Shorts a side or with a shift under HEAT_SHIFT."""
    H = _heat()
    if H is None: return None
    try:
        d = H.shift(rows_a, rows_b)
        if d is None or abs(d) < HEAT_SHIFT: return None
        out = {"shift": round(d, 2)}
        eff = H.effect(every if every is not None else list(rows_a) + list(rows_b), _logviews)
        if eff and eff["clear"]:
            import math
            out["per_point"] = round(math.exp(eff["b"]) - 1, 2)
        return out
    except Exception:
        return None


def heat_words(h, who="the later Shorts'"):
    """One clause on a heat shift for the insights and the retention issue."""
    if not h: return ""
    hot = h["shift"] > 0
    s = (f"{who} topics ran {'hotter' if hot else 'colder'} (by {abs(h['shift']):.1f} heat on the trend sources)")
    if h.get("per_point") is not None:
        s += f", and each point of heat has come with {100 * h['per_point']:+.0f}% views against the same day's other Shorts"
    return s + (f", so part of any {'rise' if hot else 'fall'} may be the topics rather than the changes")


# ---------------- the loop against the frozen control (28 October) ----------------
# "Is the learning loop improving things?" read apart from trends, the volume test and mega pushes: the control Shorts (control.py,
# shorts.csv control_arm 1) are written with the recipe frozen on 28 October, the loop's Shorts with whatever it has learned since.
# Same channel, same UK day: for each day that has both, the loop's mean log metric less the control's (a ratio once back from
# the log), averaged over the days with weights nl*nc/(nl+nc), the 90% interval from resampling the days 2,000 times. Views and
# the engaged share are heat-adjusted as the other verdicts are (heat.py: when topic heat clearly moves the number within a
# channel and day, each day's difference is moved to equally hot topics; a difference that is clear raw and not once heat is
# allowed for is called unclear). Subscribers per 1,000 views is the pooled rate of the loop's Shorts over the control's, not
# adjusted (a handful of subscribers a day has no heat to fit). The loop's Shorts here are the normal ones: no control, mega
# or viral-topic Short, news or evergreen like the control's.
CONTROL_MIN_N, CONTROL_MIN_DAYS, BOOT, LO_Q, HI_Q = 8, 3, 2000, 0.05, 0.95
CONTROL_METRICS = (("views_24h", "views at 24 hours", "log"), ("yt_engaged_pct", "engaged share of views", "log"),
                   ("subs_per_1k", "subscribers per 1,000 views", "rate"))


def _control_min():
    try:
        import control
        return int(control.settings().get("min_n", CONTROL_MIN_N))
    except Exception: return CONTROL_MIN_N


def _is_control(r): return str(r.get("control_arm") or "") == "1"


def _is_loop(r):
    """A normal Short the loop wrote: not a control, mega or viral-topic Short, of a kind a control Short can be."""
    return (not _is_control(r) and r.get("mega") != "yes" and r.get("viral") != "yes" and r.get("kind") in ("news", "evergreen")
            and (r.get("channel") or "main") == "main")


def _cluster_interval(groups, stat, seed):
    """(low, high) of stat over resamples of the groups (the days) with replacement; (None, None) when most resamples have none."""
    rng, n, vals = random.Random(seed), len(groups), []
    for _ in range(BOOT):
        v = stat([groups[rng.randrange(n)] for _ in range(n)])
        if v is not None: vals.append(v)
    if len(vals) < BOOT // 2: return None, None
    vals.sort()
    return vals[int(LO_Q * len(vals))], vals[min(len(vals) - 1, int(HI_Q * len(vals)))]


def _log_est(groups):
    """exp of the weighted mean difference over (weight, difference) groups; None without weight."""
    w = sum(g[0] for g in groups)
    return math.exp(sum(g[0] * g[1] for g in groups) / w) if w > 0 else None


def _rate_est(groups):
    """The loop's pooled rate over the control's over (subs_l, views_l, subs_c, views_c) groups; None when a pool is empty."""
    sl, vl, sc, vc = (sum(g[i] for g in groups) for i in range(4))
    return (sl / vl) / (sc / vc) if vl > 0 and vc > 0 and sc > 0 else None


def _verdict(lo, hi):
    if lo is None or hi is None: return "no interval"
    return "loop ahead" if lo > 1 else "control ahead" if hi < 1 else "no clear difference"


def _log_groups(loop, ctrl, col, slope=None):
    """[(weight, difference)] for the days having both kinds of Short measured on `col`: the loop's mean log less the control's,
    each moved to equally hot topics by `slope` (log per heat point) when given and both sides have heat. Also how many days were
    adjusted."""
    H = _heat()
    def lg(r):
        v = _f(r.get(col))
        return None if v is None else math.log(max(0.05, v))
    by = {}
    for side, rs in ((0, loop), (1, ctrl)):
        for t, r in rs:
            y = lg(r)
            if y is None: continue
            h = H.value(r) if (H is not None and slope is not None) else None
            by.setdefault((r.get("channel") or "main", _uk_day(t)), ([], []))[side].append((y, h))
    out, adj = [], 0
    for (_ch, _d), (a, b) in sorted(by.items()):
        if not a or not b: continue
        d = statistics.mean(y for y, _ in a) - statistics.mean(y for y, _ in b)
        ha, hb = [h for _, h in a if h is not None], [h for _, h in b if h is not None]
        if slope is not None and ha and hb:
            d -= slope * (statistics.mean(ha) - statistics.mean(hb)); adj += 1
        out.append((len(a) * len(b) / (len(a) + len(b)), d))
    return out, adj


def _rate_groups(loop, ctrl):
    by = {}
    for side, rs in ((0, loop), (1, ctrl)):
        for t, r in rs:
            v, sg = _f(r.get("yt_views")), _f(r.get("yt_subs_gained"))
            if v is None or sg is None: continue
            g = by.setdefault((r.get("channel") or "main", _uk_day(t)), [0.0, 0.0, 0.0, 0.0])
            g[2 * side] += sg; g[2 * side + 1] += v
    return [tuple(g) for g in by.values() if g[1] > 0 and g[3] > 0]


def loop_vs_control(rows, now, min_n=None):
    """The loop's Shorts against the control's (module comment): {"verdict", "n_control", "n_loop", "days", "min_n", "metrics":
    {col: {"label", "ratio", "lo", "hi", "adjusted", "raw": {ratio, lo, hi}, "verdict", "days"}}, "summary"}. With fewer than
    min_n control Shorts measured at 24 hours (or 3 days having both kinds) the verdict is "too few to tell (n)"."""
    min_n = _control_min() if min_n is None else min_n
    main = [(t, r) for t, r in aged(rows, now) if (r.get("channel") or "main") == "main"]
    ctrl = [(t, r) for t, r in main if _is_control(r) and _f(r.get("views_24h")) is not None]
    loop = [(t, r) for t, r in main if _is_loop(r) and _f(r.get("views_24h")) is not None]
    out = {"n_control": len(ctrl), "n_loop": len(loop), "min_n": min_n, "metrics": {}, "days": 0}
    days = {_uk_day(t) for t, _ in ctrl} & {_uk_day(t) for t, _ in loop}
    out["days"] = len(days)
    if len(ctrl) < min_n or len(days) < CONTROL_MIN_DAYS:
        out["verdict"] = f"too few to tell ({len(ctrl)})"
        out["summary"] = (f"too few to tell ({len(ctrl)}): {len(ctrl)} control Shorts public 24 hours or more, {min_n} needed over "
                          f"{CONTROL_MIN_DAYS} days or more that also have the loop's Shorts ({len(days)} so far)")
        return out
    H, every = _heat(), [r for _t, r in main]
    bits, verdicts = [], {}
    for col, label, kind in CONTROL_METRICS:
        if kind == "rate":
            groups = _rate_groups(loop, ctrl)
            est = _rate_est(groups)
            if est is None or len(groups) < CONTROL_MIN_DAYS:
                out["metrics"][col] = {"label": label, "verdict": "too few to tell", "days": len(groups)}
                bits.append(f"{label} too few to tell (the control gained {int(sum(g[2] for g in groups))} subscribers)")
                continue
            lo, hi = _cluster_interval(groups, _rate_est, f"control:{col}")
            m = {"label": label, "ratio": round(est, 2), "lo": None if lo is None else round(lo, 2), "hi": None if hi is None else round(hi, 2),
                 "adjusted": False, "verdict": _verdict(lo, hi), "days": len(groups)}
        else:
            lg = lambda r, c=col: math.log(max(0.05, _f(r.get(c)))) if _f(r.get(c)) is not None else None
            eff = None
            if H is not None:
                try: eff = H.effect(every, lg)
                except Exception: eff = None
            slope = eff["b"] if eff and eff["clear"] else None
            raw, _ = _log_groups(loop, ctrl, col)
            groups, adj = _log_groups(loop, ctrl, col, slope)
            if len(raw) < CONTROL_MIN_DAYS:
                out["metrics"][col] = {"label": label, "verdict": "too few to tell", "days": len(raw)}
                bits.append(f"{label} too few to tell"); continue
            r_est = _log_est(raw); rlo, rhi = _cluster_interval(raw, _log_est, f"control:{col}")
            est = _log_est(groups); lo, hi = (rlo, rhi) if slope is None else _cluster_interval(groups, _log_est, f"control:{col}:adj")
            v = _verdict(lo, hi)
            if slope is not None and _verdict(rlo, rhi) != "no clear difference" and v == "no clear difference":
                v = "unclear once topic heat is allowed for"
            m = {"label": label, "ratio": round(est, 2), "lo": None if lo is None else round(lo, 2), "hi": None if hi is None else round(hi, 2),
                 "adjusted": slope is not None and adj > 0, "verdict": v, "days": len(raw),
                 "raw": {"ratio": round(r_est, 2), "lo": None if rlo is None else round(rlo, 2), "hi": None if rhi is None else round(rhi, 2)}}
        out["metrics"][col] = m
        verdicts[col] = m["verdict"]
        bits.append(f"{label} {m['ratio']:.2f}x ({m['lo']} to {m['hi']})" + (", heat allowed for" if m["adjusted"] else "")
                    + ("" if m["verdict"] == "no clear difference" else f", {m['verdict']}"))
    ahead = [CONTROL_LABELS.get(c, c) for c, v in verdicts.items() if v == "loop ahead"]
    behind = [CONTROL_LABELS.get(c, c) for c, v in verdicts.items() if v == "control ahead"]
    out["verdict"] = ("loop behind control on " + ", ".join(behind) if behind else "loop ahead on " + ", ".join(ahead) if ahead
                      else "no clear difference yet")
    out["summary"] = (f"the loop's Shorts against control, as a ratio with a 90% interval: " + "; ".join(bits) + f". {len(loop)} loop and "
                      f"{len(ctrl)} control Shorts over {len(days)} days with both. Verdict: {out['verdict']}")
    return out


CONTROL_LABELS = {c: lab for c, lab, _k in CONTROL_METRICS}

def trend(rows, now, verdicts=None):
    """This week against the week before: {this, last, change: {metric: ratio}, followed: {n, of, lift}, flags: [text]}."""
    this, last = window(rows, now), window(rows, now, offset=WEEK)
    t = {"this": medians(this), "last": medians(last), "change": {}, "flags": []}
    h = heat_shift(last, this, every=[r for _t, r in aged(rows, now)])
    if h: t["heat"] = h
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
    try: t["control"] = loop_vs_control(rows, now)          # the loop against the frozen control group (28 October)
    except Exception: pass
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


def falling_heat(rows, now):
    """The heat shift between the windows falling() compares (the 7 days before, then the last RECENT_DAYS days), or None."""
    recent, before = window(rows, now, days=RECENT_DAYS), window(rows, now, days=WEEK, offset=RECENT_DAYS)
    return heat_shift(before, recent, every=[r for _t, r in aged(rows, now)])


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
        L.append(f"- Too early to say: {t['this']['n']} Shorts this week, {t['last']['n']} the week before.")
        if t.get("control"): L.append("- Loop vs frozen control: " + t["control"]["summary"] + ".")      # its own window, not the week's
        return L + [""]
    for k, label, _kind in METRICS:
        a, b, c = t["this"].get(k), t["last"].get(k), t["change"].get(k)
        if a is None and b is None: continue
        word = "" if c is None else (" (up)" if c >= 1.1 else " (down)" if c <= 0.9 else " (level)")
        L.append(f"- {label}: {a if a is not None else '?'} this week, {b if b is not None else '?'} the week before{word}.")
    f = t.get("followed")
    if f and f.get("of"):
        L.append(f"- Shorts that followed the data's rulings: {f['n']} of {f['of']}"
                 + (f", {f['lift']}x the 24-hour views of the rest." if f.get("lift") else "."))
    if t.get("heat"):
        L.append("- Topic heat: " + heat_words(t["heat"], who="this week's") + ".")
    for x in t["flags"]:
        L.append(f"- Watch: {x}. The drivers cannot see a fall that hits every Short alike; the review checks the changes of the "
                 f"last 10 days (analytics/changes.csv) and reverts what hurt.")
    if t.get("control"):
        L.append("- Loop vs frozen control: " + t["control"]["summary"] + ".")
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
    try: h["control"] = loop_vs_control(load_rows(a / "shorts.csv"), now)       # "Loop vs frozen control" (the hub's line, insights.md)
    except Exception as e: h["control"] = {"verdict": "not computed", "summary": str(e)[:100]}
    p = pathlib.Path(out or a / "improvement.json")
    p.write_text(json.dumps(h, separators=(",", ":"), ensure_ascii=False))
    return p


if __name__ == "__main__":
    if "--history" in sys.argv: print(write_history())
    else: print("\n".join(lines(trend(load_rows(), dt.datetime.now(dt.timezone.utc), verdicts()))))
