"""The change ledger (Charlie, 24 October): "an improvement programme for the improvement programme ... everything data
driven and recorded so when you change something it's recorded to see if that made a positive change or not", and "if
data is leading down a route of improvement that sacrifices other parts of the project then we need analysis on this".

Every change to the system (code, config, a rule) gets a row in analytics/changes.csv: what changed and why it should
help, the one metric it should move (target), the metrics it must not hurt (guardrails), the windows compared (7 days
before it went live, 7 after) and the day to check it (check_on). From that day `check` compares medians:
- "too early": under 5 Shorts, clips or days on a side (checked again each run; final 14 days after check_on);
- "better" or "worse": the target moved 10% or more the right or the wrong way; otherwise "no change";
- "trade-off": the target got better or held while a guardrail got more than 15% worse. An issue opens ("⚖️ A change
  helped one thing and hurt another") until a session marks the row kept or reverted (`set CH-007 --status kept`);
- "overlapped": another change aimed at the same target went live inside the same windows, so neither is credited on its
  own. The numbers still show what they did together, and a trade-off between them still raises the issue.
Every metric is the main channel's, except for a change that adds a channel (area channels, 25 October): its target is
measured over the whole line's Shorts (analytics/shorts.csv has every channel, with a channel column), its guardrails stay
the main channel's.
Before and after is what happened, not proof: channel growth, news days and other changes move the numbers too.

The writer's automatic recipe changes (analytics/decisions.csv, by "analytics (automatic)") are scored once each when
their check_on day has passed, on whether the data's call held up out of sample: the chosen value's Shorts against the
Shorts posted around them (views_vs_typical) in the week after, and how much the writer used the value before and after.
"better" means the call was right (a pushed choice kept beating typical, a cut one kept trailing); "worse" means it faded
or recovered, the automatic recipe chasing noise. These rows never count as overlapping (dozens move every day).

  python pipeline/changes.py add --area shorts --change "..." --hypothesis "..." --target yt_views_24h \
         --guardrails "uploads_day;dead_share" [--date 2026-10-24] [--before 7] [--after 7] [--by "Claude (session)"]
  python pipeline/changes.py check         (analytics.yml, every hour after the numbers)
  python pipeline/changes.py list          (one screen)
  python pipeline/changes.py set CH-007 --status kept|reverted|live
  python pipeline/changes.py metrics       (the metric names a target or guardrail can use)
"""
import argparse, csv, datetime as dt, io, json, math, pathlib, re, statistics, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
UK = ZoneInfo("Europe/London")
FIELDS = ["id", "date", "area", "change", "hypothesis", "target", "guardrails", "before_days", "after_days", "check_on",
          "status", "verdict", "result", "by"]
AREAS = ("shorts", "clips", "instagram", "facebook", "tiktok", "writer", "models", "schedule", "quota", "data", "channels", "longform")
STATUSES = ("live", "checked", "kept", "reverted")
AUTO = "analytics (automatic)"
MIN_N, MOVE, BREAK, GRACE = 5, 0.10, 0.15, 14        # per side; a 10% move counts; a guardrail 15% worse is broken; final after 14 days
DEAD_MIN, DEAD_SHARE = 20, 0.2                     # as drivers.py: dead = under a fifth of the typical week-old Short's views
TRADE_TITLE = "⚖️ A change helped one thing and hurt another"


def ledger_path(): return ROOT / "analytics" / "changes.csv"
def alert_path(): return ROOT / "analytics" / "cache" / "changes_alert.json"


def rows_of(rel):
    p = ROOT / rel
    if not p.exists(): return []
    try: return list(csv.DictReader(io.StringIO(p.read_text())))
    except Exception: return []


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError): return None


def day_of(s):
    """UK date of an ISO time ("2026-10-24T13:00+00:00"), or of a UK "YYYY-MM-DD HH:MM" / "YYYY-MM-DD"."""
    s = str(s or "").strip()
    if not s: return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (t.astimezone(UK) if t.tzinfo else t).date()
    except ValueError: return None


def med(vals):
    v = [x for x in vals if x is not None]
    return (statistics.median(v), len(v)) if v else (None, 0)


# ---------------- the data, read once per run ----------------
class Data:
    def __init__(self, today=None, now=None):
        self.now = now or dt.datetime.now(dt.timezone.utc)
        self.today = today or self.now.astimezone(UK).date()
        self.all_shorts = rows_of("analytics/shorts.csv")
        for r in self.all_shorts: r["_day"] = day_of(r.get("posted"))
        # every metric is the main channel's (25 October: shorts.csv also holds the Daily line's other channels, with their
        # own channel column); only a change that adds a channel (area "channels") is judged on all of them, see line()
        self.shorts = [r for r in self.all_shorts if (r.get("channel") or "main") == "main"]
        self.daily = rows_of("analytics/daily.csv")
        self.longform = rows_of("analytics/longform.csv")        # the long videos' watch time by day (explainer.watch_report)
        self.cstats = rows_of("clips/stats.csv")
        for r in self.cstats:
            t = None
            try: t = dt.datetime.fromisoformat(str(r.get("as_of")).replace("Z", "+00:00")) - dt.timedelta(hours=num(r.get("hours_public")) or 0)
            except (TypeError, ValueError): pass
            r["_day"] = t.astimezone(UK).date() if t and t.tzinfo else None
        self.submit = rows_of("clips/submit.csv")
        try: self.camps = json.loads((ROOT / "clips" / "campaigns.json").read_text()).get("campaigns") or {}
        except Exception: self.camps = {}
        aged = [num(r.get("yt_views")) for r in self.shorts if r["_day"] and self.age_days(r) >= 7]
        aged = [v for v in aged if v is not None]
        self.floor = max(DEAD_MIN, DEAD_SHARE * statistics.median(aged)) if len(aged) >= 5 else None

    def age_days(self, r):
        try: return (self.now - dt.datetime.fromisoformat(str(r.get("posted")).replace("Z", "+00:00"))).total_seconds() / 86400
        except (TypeError, ValueError): return 0.0

    def line(self):
        """This data with every channel's Shorts in `shorts`: what a change that adds a channel is judged on, so the
        target (subscribers per 1,000 views, views at 24 hours) is the whole line's, while its guardrails stay the main
        channel's (a new channel must not cost the main one uploads or categories)."""
        import copy
        d = copy.copy(self); d.shorts = self.all_shorts
        return d

    def shorts_in(self, a, b): return [r for r in self.shorts if r["_day"] and a <= r["_day"] < b]
    def clips_in(self, a, b): return [r for r in self.cstats if r["_day"] and a <= r["_day"] < b and r.get("privacy") == "public"]

    def days(self, a, b, start, end=None):
        """The complete days of [a, b) the data covers: from `start` up to `end` (exclusive: the first day the data has not
        finished, so a stopped feed never reads as days of zero) and never today."""
        out, d, stop = [], a, min(x for x in (end, self.today) if x)
        while d < b:
            if start and start <= d < stop: out.append(d)
            d += dt.timedelta(days=1)
        return out

    def shorts_end(self):
        """The last day analytics ran (daily.csv snapshot): Shorts posted before it are all in shorts.csv."""
        return first([day_of(r.get("day")) for r in self.daily if r.get("source") == "snapshot"], last=True)

    def clips_end(self):
        """The day after the latest clip stats (the nightly 22:30 UTC run sees the whole day's batch)."""
        d = first([day_of(r.get("as_of")) for r in self.cstats], last=True)
        return d + dt.timedelta(days=1) if d else None


# ---------------- metrics: name -> (label, better, format, function(data, a, b) -> (value, n)) ----------------
def m_field(field, rows="shorts"):
    def fn(D, a, b):
        src = D.shorts_in(a, b) if rows == "shorts" else D.clips_in(a, b)
        return med([num(r.get(field)) for r in src])
    return fn


def m_views_24h(D, a, b): return m_field("views_24h")(D, a, b)
def rel24(r):
    """views_vs_typical where it is the 24-hour figure (views_24h measured): a younger Short's stand-in, views an hour
    against older peers, runs high, so it is left out of before and after comparisons."""
    return num(r.get("views_vs_typical")) if num(r.get("views_24h")) is not None else None


def m_rel(D, a, b): return med([rel24(r) for r in D.shorts_in(a, b)])


def m_dead(D, a, b):
    if D.floor is None: return None, 0
    aged = [num(r.get("yt_views")) for r in D.shorts_in(a, b) if D.age_days(r) >= 7]
    aged = [v for v in aged if v is not None]
    return (sum(1 for v in aged if v < D.floor) / len(aged), len(aged)) if aged else (None, 0)


def m_feed_pick(D, a, b):
    """The share of Shorts the Shorts feed picks up in their first 3 hours: 20 or more views at 3 hours (views_3h, from
    the hourly curves). The data report of 24 October: 27% of Shorts, holding 77% of the 24-hour views."""
    v = [num(r.get("views_3h")) for r in D.shorts_in(a, b)]
    v = [x for x in v if x is not None]
    return (sum(1 for x in v if x >= 20) / len(v), len(v)) if v else (None, 0)


def m_subs(D, a, b):
    pairs = [(num(r.get("yt_subs_gained")), num(r.get("yt_views"))) for r in D.shorts_in(a, b)]
    pairs = [(s, v) for s, v in pairs if s is not None and v is not None]
    views = sum(v for _, v in pairs)
    return (1000 * sum(s for s, _ in pairs) / views, len(pairs)) if views else (None, len(pairs))


def m_mix(D, a, b):
    """The effective number of categories posted: exp of the entropy of the category mix (4 equal categories: 4.0)."""
    cats = [r.get("category") for r in D.shorts_in(a, b) if r.get("category")]
    if not cats: return None, 0
    shares = [cats.count(c) / len(cats) for c in set(cats)]
    return math.exp(-sum(p * math.log(p) for p in shares)), len(cats)


def per_day(counter, start_of, end_of, zero_fill=True):
    """A day metric: the median over the window's covered days of counter(D)[day]. Counts (zero_fill) read a covered day
    with nothing as 0; measured series use only the days they have."""
    def fn(D, a, b):
        counts = counter(D)
        ds = D.days(a, b, start_of(D), end_of(D))
        if not zero_fill: ds = [d for d in ds if d in counts]
        if not ds: return None, 0
        return statistics.median([counts.get(d, 0) for d in ds]), len(ds)
    return fn


def first(days, last=False):
    days = [d for d in days if d]
    return (max(days) if last else min(days)) if days else None


def shorts_per_day(D):
    out = {}
    for r in D.shorts:
        if r["_day"]: out[r["_day"]] = out.get(r["_day"], 0) + 1
    return out


def yt_views_per_day(D):
    """Views a day: the gain between consecutive daily snapshots of the channel total (UTC days), else YouTube
    Analytics' own daily figure."""
    snaps = {day_of(r.get("day")): num(r.get("yt_views_total")) for r in D.daily if r.get("source") == "snapshot"}
    out = {}
    for d, tot in snaps.items():
        prev = snaps.get(d - dt.timedelta(days=1)) if d else None
        if d and tot is not None and prev is not None: out[d] = tot - prev
    for r in D.daily:
        d = day_of(r.get("day"))
        if d and d not in out and r.get("source") == "youtube_daily" and num(r.get("yt_views_day")) is not None: out[d] = num(r["yt_views_day"])
    return out


def longform_hours_per_day(D):
    """Watch hours a day on the long videos (analytics/longform.csv): the compilation and the explainer together."""
    out = {}
    for r in D.longform:
        d, h = day_of(r.get("date")), num(r.get("watch_hours"))
        if d and h is not None: out[d] = out.get(d, 0) + h
    return out


def yt_views_start(D):
    v = yt_views_per_day(D)
    return min(v) if v else None


def is_clip_row(r): return r.get("platform", "youtube") == "youtube" and re.match(r"\d{4}-\d\d-\d\d \d", str(r.get("public_at_uk", ""))) and r.get("submitted") != "pulled"


def clips_per_day(D):
    out = {}
    for r in D.submit:
        if is_clip_row(r):
            d = day_of(r["public_at_uk"]); out[d] = out.get(d, 0) + 1
    return out


def submissions_per_day(D):
    out = {}
    for r in D.submit:
        s = str(r.get("submitted") or "")
        if re.match(r"\d{4}-\d\d-\d\d", s):
            d = day_of(s[:10]); out[d] = out.get(d, 0) + 1
    return out


def submit_start(D): return first([day_of(r.get("public_at_uk")) for r in D.submit if is_clip_row(r)])


def m_clip_views(D, a, b):
    return med([num(r.get("views")) for r in D.clips_in(a, b) if (num(r.get("hours_public")) or 0) >= 24])


def m_clip_min(D, a, b):
    hits, n = 0, 0
    for r in D.clips_in(a, b):
        need = num((D.camps.get(r.get("campaign")) or {}).get("min_views"))
        if not need or (num(r.get("hours_public")) or 0) < 24: continue
        n += 1; hits += (num(r.get("views")) or 0) >= need
    return (hits / n, n) if n else (None, 0)


def m_clip_ig(D, a, b): return med([num(r.get("ig_views")) for r in D.clips_in(a, b)])


METRICS = {
    "yt_views_24h": ("YouTube views per Short at 24 hours", "higher", "{:,.0f}", m_views_24h),
    "yt_rel": ("Shorts views against the Shorts around them", "higher", "{:.2f}x", m_rel),
    "dead_share": ("share of dead Shorts a week on", "lower", "{:.0%}", m_dead),
    "feed_pick": ("share of Shorts the feed picks up (20+ views at 3 hours)", "higher", "{:.0%}", m_feed_pick),
    "uploads_day": ("Shorts posted a day", "higher", "{:.0f}", per_day(shorts_per_day, lambda D: first([r["_day"] for r in D.shorts]), Data.shorts_end)),
    "yt_views_day": ("YouTube views a day", "higher", "{:,.0f}", per_day(yt_views_per_day, yt_views_start, lambda D: None, zero_fill=False)),
    "watch_hours_day": ("long-video watch hours a day", "higher", "{:.1f}", per_day(longform_hours_per_day, yt_views_start, Data.shorts_end)),
    "avg_viewed_pct": ("average viewed %", "higher", "{:.0f}%", m_field("yt_avg_viewed_pct")),
    "held_3s": ("still watching at 3 seconds", "higher", "{:.0f}%", m_field("yt_held_3s_pct")),
    "subs_per_1k": ("subscribers per 1,000 views", "higher", "{:.2f}", m_subs),
    "category_mix": ("categories in the mix (effective number)", "higher", "{:.1f}", m_mix),
    "ig_views": ("Instagram views per Reel", "higher", "{:,.0f}", m_field("ig_views")),
    "fb_views": ("Facebook plays per Reel", "higher", "{:,.0f}", m_field("fb_views")),
    "clips_day": ("clips public a day", "higher", "{:.0f}", per_day(clips_per_day, submit_start, Data.clips_end)),
    "clip_views": ("views per clip a day on", "higher", "{:,.0f}", m_clip_views),
    "clip_min_share": ("share of clips reaching their campaign minimum", "higher", "{:.0%}", m_clip_min),
    "clip_ig_views": ("Instagram views per clip", "higher", "{:,.0f}", m_clip_ig),
    "submissions_day": ("clip submissions a day", "higher", "{:.0f}", per_day(submissions_per_day, submit_start, Data.clips_end)),
}


def fmt(name, v):
    return "none" if v is None else METRICS[name][2].format(v)


def improvement(vb, va, better):
    """The move the right way as a share of before (+0.2: 20% better), or None."""
    if vb is None or va is None: return None
    diff = (0.0 if va == vb else (1.0 if va > vb else -1.0)) if vb == 0 else (va - vb) / abs(vb)
    return diff if better == "higher" else -diff


def raw_pct(vb, va):
    if vb is None or va is None: return ""
    if vb == 0: return "new" if va else "+0%"
    return f"{(va - vb) / abs(vb):+.0%}"


# ---------------- the ledger ----------------
def load():
    return rows_of("analytics/changes.csv")


def save(rows):
    p = ledger_path(); p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
    w.writeheader(); w.writerows([{k: r.get(k, "") for k in FIELDS} for r in rows])
    p.write_text(buf.getvalue())


def next_id(rows):
    n = max([int(m.group(1)) for r in rows for m in [re.fullmatch(r"CH-(\d+)", str(r.get("id", "")))] if m] or [0])
    return f"CH-{n + 1:03d}"


def add(area, change, hypothesis, target, guardrails="", date=None, before=7, after=7, by="Claude (session)", rows=None):
    """A new ledger row (live until its check_on day). Returns the row; saves unless `rows` is given."""
    if area not in AREAS: raise ValueError(f"area must be one of {', '.join(AREAS)}")
    guards = [g.strip() for g in re.split(r"[;,]", guardrails or "") if g.strip()]
    for m in [target] + guards:
        if m not in METRICS: raise ValueError(f"unknown metric {m!r}: python pipeline/changes.py metrics")
    d = dt.date.fromisoformat(date) if date else dt.datetime.now(UK).date()
    own = rows is None
    rows = load() if own else rows
    row = {"id": next_id(rows), "date": str(d), "area": area, "change": change.strip(), "hypothesis": hypothesis.strip(),
           "target": target, "guardrails": ";".join(guards), "before_days": str(int(before)), "after_days": str(int(after)),
           "check_on": str(d + dt.timedelta(days=int(after))), "status": "live", "verdict": "", "result": "", "by": by}
    rows.append(row)
    if own: save(rows)
    return row


def windows(r):
    d0 = dt.date.fromisoformat(r["date"]); b = int(r.get("before_days") or 7); a = int(r.get("after_days") or 7)
    return d0, (d0 - dt.timedelta(days=b), d0), (d0, d0 + dt.timedelta(days=a))


def check_day(r):
    try: return dt.date.fromisoformat(r["check_on"])
    except (KeyError, ValueError): return windows(r)[2][1]


def overlaps(r, rows):
    d0, (b0, _), (_, a1) = windows(r)
    out = []
    for o in rows:
        if o is r or o.get("id") == r.get("id") or o.get("by") == AUTO or o.get("target") != r.get("target"): continue
        try: od = dt.date.fromisoformat(o["date"])
        except (KeyError, ValueError): continue
        if b0 <= od < a1: out.append(o["id"])
    return out


def judge(r, D, rows):
    """Fill one system row's verdict, result and status from the data (rows past check_on only)."""
    if r.get("status") in ("kept", "reverted") or (r.get("status") == "checked" and r.get("verdict")): return r
    if D.today < check_day(r): return r
    name = r["target"]
    if name not in METRICS: r.update(verdict="too early", result=f"unknown target {name}", status="checked"); return r
    label, better, _, fn = METRICS[name]
    _, before, after = windows(r)
    DT = D.line() if r.get("area") == "channels" else D       # a new channel is judged on the whole line, its guardrails on the main channel
    vb, nb = fn(DT, *before); va, na = fn(DT, *after)
    guards, broken = [], []
    for g in [x.strip() for x in (r.get("guardrails") or "").split(";") if x.strip() in METRICS]:
        gl, gbet, _, gfn = METRICS[g]
        gb, gnb = gfn(D, *before); ga, gna = gfn(D, *after)
        imp = improvement(gb, ga, gbet)
        if gnb < MIN_N or gna < MIN_N or imp is None: guards.append(f"{gl} too few to tell"); continue
        bad = imp <= -BREAK
        guards.append(f"{gl} {fmt(g, gb)} -> {fmt(g, ga)} {'BROKEN' if bad else 'ok'} ({raw_pct(gb, ga)})")
        if bad: broken.append(gl)
    res = f"{label} {fmt(name, vb)} -> {fmt(name, va)} ({raw_pct(vb, va) or 'no figure'}, n {nb}/{na})"
    if guards: res += "; guardrails: " + "; ".join(guards)
    other = overlaps(r, rows)
    final = D.today >= check_day(r) + dt.timedelta(days=GRACE)
    imp = improvement(vb, va, better)
    if nb < MIN_N or na < MIN_N or imp is None:
        r.update(verdict="too early", result=res + f"; needs {MIN_N} a side", status="checked" if final else "live")
        return r
    verdict = "better" if imp >= MOVE else "worse" if imp <= -MOVE else "no change"
    if broken and verdict in ("better", "no change"): verdict = "trade-off"
    if other:
        res += f"; overlaps {', '.join(other)} (same target, same weeks: credited together)"
        if verdict == "trade-off": res += "; together a trade-off"
        verdict = "overlapped"
    r.update(verdict=verdict, result=res, status="checked")
    return r


# ---------------- the writer's automatic recipe changes (decisions.csv) ----------------
EVID = re.compile(r"drivers\.csv: (\w+) = (.*?), n \d+, lift")


def import_decisions(rows, D):
    """One ledger row per automatic decision whose check_on day has passed (never twice)."""
    have = {(r.get("date"), r.get("change")) for r in rows if r.get("by") == AUTO}
    added = 0
    for d in rows_of("analytics/decisions.csv"):
        if d.get("by") != AUTO or not EVID.search(d.get("evidence", "")): continue
        try: on = dt.date.fromisoformat(d.get("check_on", "")); day = dt.date.fromisoformat(d.get("date", ""))
        except ValueError: continue
        change = "Recipe: " + d.get("change", "")
        if on > D.today or (d["date"], change) in have: continue
        rows.append({"id": next_id(rows), "date": d["date"], "area": "writer", "change": change,
                     "hypothesis": f"{d.get('why', '')} [{d.get('evidence', '')}]", "target": "yt_rel", "guardrails": "uploads_day",
                     "before_days": str(max(1, (on - day).days)), "after_days": str(max(1, (on - day).days)), "check_on": str(on),
                     "status": "live", "verdict": "", "result": "", "by": AUTO})
        have.add((d["date"], change)); added += 1
    return added


def judge_auto(r, D):
    """Did the data's call hold up in the week after? The value's Shorts against the week's other Shorts that recorded
    the same choice (both against their own peers, views_vs_typical at 24 hours), so the channel's growth or a slow news
    week moves both sides alike; and how much the writer used the value before and after."""
    if r.get("status") in ("kept", "reverted") or (r.get("status") == "checked" and r.get("verdict")): return r
    if D.today < check_day(r): return r
    m = EVID.search(r.get("hypothesis", ""))
    if not m: r.update(verdict="too early", result="no feature in the evidence", status="checked"); return r
    import drivers as DRV
    feat, value = m.group(1), m.group(2)
    _, before, after = windows(r)
    def split(a, b):
        """(the value's Shorts, the other Shorts that recorded this choice, the value's share of those that did)."""
        vals = [(x, DRV.features(x).get(feat)) for x in D.shorts_in(a, b)]
        hit = [x for x, v in vals if v == value]; rest = [x for x, v in vals if v and v != value]
        return hit, rest, (len(hit) / (len(hit) + len(rest)) if hit or rest else None)
    _, _, ub = split(*before); hit, rest, ua = split(*after)
    vh, nh = med([rel24(x) for x in hit]); vo, no = med([rel24(x) for x in rest])
    usage = f"used in {ub:.0%} of Shorts before, {ua:.0%} after" if ub is not None and ua is not None else "use not measured"
    final = D.today >= check_day(r) + dt.timedelta(days=GRACE)
    if nh < MIN_N or no < MIN_N or not vo:
        r.update(verdict="too early", result=f"\"{value}\" {nh} Shorts against {no} others measured at 24 hours; {usage}; needs {MIN_N} each",
                 status="checked" if final else "live"); return r
    x = vh / vo
    res = f"\"{value}\" Shorts after: {x:.2f}x the week's other Shorts (n {nh} against {no}); {usage}"
    ch = r.get("change", "")
    if "Lean towards" in ch:
        verdict, why = ("better", "held up") if x >= 1.1 else ("worse", "faded: the lift was noise") if x <= 0.9 else ("no change", "back near the rest")
    elif "Use less" in ch or "Never again" in ch or "Stop" in ch:
        verdict, why = ("better", "confirmed weak") if x <= 0.9 else ("worse", "recovered: the cut was wrong") if x >= 1.1 else ("no change", "back near the rest")
    else:
        # back to normal: small weekly samples swing, so only a clear gap (a third or more either way) calls it premature
        verdict, why = ("no change", "level with the rest, as expected") if 0.67 < x < 1.5 else ("worse", "still apart from the rest")
    r.update(verdict=verdict, result=f"{why}: {res}", status="checked")
    return r


# ---------------- trade-off alert ----------------
def open_tradeoffs(rows):
    return [r for r in rows if r.get("status") == "checked" and (r.get("verdict") == "trade-off" or
            (r.get("verdict") == "overlapped" and "together a trade-off" in r.get("result", "")))]


def alert(rows, raise_issue=None, clear=None):
    """Opens the trade-off issue when a new one appears; closes it when none is open. Returns the open ids."""
    if raise_issue is None or clear is None:
        import alerts as A
        raise_issue, clear = raise_issue or A.raise_issue, clear or A.clear
    ids = sorted(r["id"] for r in open_tradeoffs(rows))
    p = alert_path()
    try: was = json.loads(p.read_text()).get("open") or []
    except Exception: was = []
    if ids and set(ids) - set(was):
        body = ["A change moved its target the right way while a guardrail got more than 15% worse "
                "(analytics/changes.csv). Decide: keep it (the gain is worth it) or revert it.", ""]
        body += [f"- {r['id']} ({r['date']}, {r['area']}): {r['change']}. {r['result']}" for r in open_tradeoffs(rows)]
        body += ["", "Then, in a Claude session: python pipeline/changes.py set <id> --status kept (or reverted). "
                 "The issue closes when none is left open."]
        raise_issue(TRADE_TITLE, "\n".join(body))
    elif not ids and was:
        clear(TRADE_TITLE, "No change is hurting a guardrail now (every trade-off was kept or reverted).")
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({"open": ids}))
    return ids


def check(today=None, now=None, raise_issue=None, clear=None, notify=True):
    rows = load()
    D = Data(today=today, now=now)
    added = import_decisions(rows, D)
    for r in rows:
        try: judge_auto(r, D) if r.get("by") == AUTO else judge(r, D, rows)
        except Exception as e: print(f"{r.get('id')}: not checked: {type(e).__name__}: {e}", file=sys.stderr)
    save(rows)
    ids = alert(rows, raise_issue, clear) if notify else [r["id"] for r in open_tradeoffs(rows)]
    done = [r for r in rows if r.get("status") == "checked" and r.get("by") != AUTO]
    print(f"changes: {len(rows)} rows ({added} automatic decisions added), {len(done)} checked, open trade-offs: {', '.join(ids) or 'none'}")
    return rows


def due(start, end, rows=None):
    """What came due between two dates (check_on inside [start, end]): (system rows, automatic rows)."""
    rows = load() if rows is None else rows
    inside = [r for r in rows if r.get("check_on") and str(start) <= r["check_on"] <= str(end)]
    return [r for r in inside if r.get("by") != AUTO], [r for r in inside if r.get("by") == AUTO]


def calls_record(auto):
    """How often the automatic recipe's calls held up: (right, wrong, level) among the checked ones."""
    right = sum(1 for r in auto if r.get("verdict") == "better")
    wrong = sum(1 for r in auto if r.get("verdict") == "worse")
    return right, wrong, sum(1 for r in auto if r.get("verdict") == "no change")


def show(rows=None, width=150):
    rows = load() if rows is None else rows
    out = []
    for r in rows[-40:]:
        line = f"{r['id']} {r['date']} {r['area']:<9} {r.get('status', ''):<8} {r.get('verdict') or '-':<11} {r['change'][:70]}"
        if r.get("result"): line += f" | {r['result']}"
        out.append(line[:width])
    print("\n".join(out) or "no changes yet")


def main(argv=None):
    ap = argparse.ArgumentParser(description="the change ledger (analytics/changes.csv)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--area", required=True, choices=AREAS); a.add_argument("--change", required=True)
    a.add_argument("--hypothesis", required=True); a.add_argument("--target", required=True, choices=sorted(METRICS))
    a.add_argument("--guardrails", default=""); a.add_argument("--date"); a.add_argument("--before", type=int, default=7)
    a.add_argument("--after", type=int, default=7); a.add_argument("--by", default="Claude (session)")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("--status", required=True, choices=STATUSES)
    sub.add_parser("check"); sub.add_parser("list"); sub.add_parser("metrics")
    x = ap.parse_args(argv)
    if x.cmd == "add":
        r = add(x.area, x.change, x.hypothesis, x.target, x.guardrails, x.date, x.before, x.after, x.by)
        print(f"{r['id']} added: checked from {r['check_on']} ({METRICS[r['target']][0]})")
    elif x.cmd == "set":
        rows = load(); r = next((r for r in rows if r["id"] == x.id), None)
        if r is None: sys.exit(f"no change {x.id}")
        r["status"] = x.status; save(rows); print(f"{x.id}: {x.status}")
    elif x.cmd == "check": check()
    elif x.cmd == "list": show()
    elif x.cmd == "metrics":
        for k, (label, better, _, _) in METRICS.items(): print(f"{k:<16} {label} ({better} is better)")


if __name__ == "__main__":
    main()
