"""What drives views. Every Short is compared with the Shorts posted the same UK day, then grouped by each thing we choose
(category, format, hook, length, posting time, look and the rest). analytics.py calls it.

Outcome per Short ("rel"): its YouTube views 24 hours after posting, divided by the median for the Shorts posted the same
UK day. 1.0 is typical. When a day has fewer than 3 measured Shorts, the comparison widens to ±1 day, then ±3 days.
analytics.relative() computes it. Same-day peers take out each day's luck. On 24 October, with peers from ±3 days, 21% of
the variance sat between posting days; with same-day peers it was 2%. The weekday, colour grade and title-colon "effects"
were that luck. A Short under 24 hours old waits: there is no views-an-hour stand-in, which ran 2 to 6x high.

Per group, lift = exp(sum of log rel / (n + SHRINK)), with SHRINK 12 (was 3), so a few lucky Shorts can't make a
trend. SHRINK_NOTE gives the evidence from 24 October.

Verdicts (24 October repair). On that day's 105 measured Shorts:
- the old rule gave 51 "push" or "cut back" verdicts, where shuffled data (no real effect anywhere) gave 37.5 on average;
- this rule gives 11, where shuffled data gives 3.9.
- "push" or "cut back" needs all of these:
  - 5 or more Shorts over 2 or more UK days;
  - a lift of at least 1.25 (or at most 0.8);
  - a 90% interval of the group's mean log rel clear of 1.0;
  - Shorts posted before and after the median posting time both on the same side.
- "early sign": the lift passes 1.25 or 0.8 without that proof. "about typical" otherwise. "too few to tell" under 3 Shorts.
- "pause" (21 October, then a permanent "stop"; a 14-day pause from 24 October). It needs:
  - 5 or more of the choice's Shorts a week old, over 2 or more UK days;
  - their median views under three quarters of the dead floor. The floor is a fifth of the typical week-old Short's views,
    and at least 20.

  The writer leaves the choice out for 14 days (analytics/cache/pauses.json). Then comes "retest": a small share again,
  judged only on the Shorts made after the pause. A median under the floor pauses it again; one over the floor lifts it.
  Weekday, the late flag and exploration are measured but never paused (nothing to leave out).
A dead Short (under the floor a week on) is never followed up or remade (dead()).
"""
import datetime as dt, json, math, pathlib, re, statistics
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
ROOT = pathlib.Path(__file__).resolve().parent.parent
SHRINK, MIN_N, MIN_DAYS, PUSH, CUT = 12, 5, 2, 1.25, 0.8
SHRINK_NOTE = ("24 October, same-day peers. The within-to-between variance ratio (the weight a feature's own data asks for) "
               "is 3.6 to 12.4 for the choices with a real signal: title wording 3.6, posting time 5.1, first frame 6.3, "
               "category 10.5, camera energy 12.4. It is 36 to 117 for length, kind, format and writer. Hook, mood, voice, "
               "grade, opening, ending and replies have no measurable signal at all. Leaving one UK day out, the summed lifts "
               "rank the held-out day's Shorts as well with 3 to 15 (rank correlation 0.37 to 0.39) and worse from 20 (0.35). "
               "12 suits the choices that matter; the verdict gate deals with the noise.")
DEAD_MIN, DEAD_SHARE = 20, 0.2          # the dead floor: a fifth of the typical week-old Short's views, at least 20
PAUSE_N, PAUSE_DAYS, PAUSE_MARGIN, PAUSE_FOR, RETEST_N = 5, 2, 0.75, 14, 3
PAUSES = ROOT / "analytics" / "cache" / "pauses.json"
NOW = dt.datetime.now(dt.timezone.utc)
PAUSED = ("pause", "stop")              # "stop" is the old name, still read wherever a verdict is read
METHOD = ("same-UK-day peers, shrink 12, push or cut back only when the 90% interval clears typical and both halves "
          "of the data agree, 14-day pause and retest instead of a permanent stop (24 October)")


def age_days(r):
    try: return (NOW - dt.datetime.fromisoformat(r["posted"])).total_seconds() / 86400
    except (KeyError, ValueError, TypeError): return 0.0


def uk_day(r):
    """The UK date a Short was posted (the two-day checks count UK days: posted_day is the UTC date)."""
    try: return dt.datetime.fromisoformat(str(r["posted"])).astimezone(UK).date().isoformat()
    except (KeyError, ValueError, TypeError): return str(r.get("posted_day") or "")


def dead_floor(rows):
    """Views a Short must have a week after posting not to count as dead: DEAD_SHARE of the typical week-old Short's
    views, never under DEAD_MIN; None until 5 Shorts are a week old."""
    aged = [_f(r.get("yt_views")) for r in rows if age_days(r) >= 7 and r.get("yt_views") not in (None, "")]
    aged = [v for v in aged if v is not None]
    return max(DEAD_MIN, DEAD_SHARE * statistics.median(aged)) if len(aged) >= 5 else None


def dead(rows):
    """The Shorts a week old or more with views under the floor: never followed up, remade or posted about again."""
    floor = dead_floor(rows)
    if floor is None: return []
    return [r for r in rows if age_days(r) >= 7 and (_f(r.get("yt_views")) or 0) < floor]


FEATURES = [("category", "Category"), ("format", "Format"), ("hook_type", "Hook style"), ("hook_len", "Hook length"),
            ("length", "Length"), ("slot", "Posting time (UK)"), ("weekday", "Day posted"), ("mood", "Music mood"),
            ("pictures", "Pictures"), ("title_style", "Title"), ("look_captions", "Captions"), ("look_voice", "Voice"),
            ("look_energy", "Camera energy"), ("look_grade", "Colour grade"), ("look_opening", "Opening"), ("follow_line", "Follow line"), ("ending", "Ending"), ("title_search", "Title wording"),
            ("first_frame", "First frame"), ("angles", "Angle research"), ("replies", "Comment replies"), ("kind", "Kind of Short"), ("source", "Topic source"), ("series", "Series"), ("franchise", "Named series"), ("writer", "Writer model"),
            ("appeal", "Appeal"), ("late", "Posted late"), ("explore", "Exploration Short"), ("title_emoji", "Title emoji")]
# Instagram's own tests (social.py, 24 October) and the categories on Instagram: scored against Instagram views
# (analyse_instagram), not YouTube's, and decided by social.py (ig_share), never put to the writer
IG_FEATURES = [("ig_trial", "Instagram trial reel"), ("ig_caption", "Instagram caption"), ("ig_hour", "Instagram posting hour"),
               ("ig_pick", "Instagram pick"), ("ig_category", "Category on Instagram")]
PIPELINE_ONLY = {"late", "explore"} | {f for f, _ in IG_FEATURES}     # measured like the rest, decided by the pipeline
NEVER_PAUSED = {"weekday", "late", "explore"} | {f for f, _ in IG_FEATURES}       # nothing the writer could leave out
TESTED = ("ending", "title_search", "first_frame", "angles", "replies", "kind", "source", "series", "franchise", "writer", "title_emoji")     # recorded on the board by the writer (writer.py tests)
NUM = r"\b(one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|hundred|thousand|million|billion)\b"
T90 = ((1, 6.314), (2, 2.920), (3, 2.353), (4, 2.132), (5, 2.015), (6, 1.943), (7, 1.895), (8, 1.860), (9, 1.833),
       (10, 1.812), (12, 1.782), (15, 1.753), (20, 1.725), (30, 1.697), (60, 1.671))


def hook_type(h):
    """A rough label for the first line, so hooks can be compared: question, number, superlative, twist, you, statement."""
    s = (h or "").strip(); low = s.lower()
    if not s: return ""
    if s.endswith("?"): return "question"
    if re.search(r"\d", s) or re.search(NUM, low): return "number"
    if re.search(r"\b(first|only|biggest|largest|fastest|most|least|never|ever|record|smallest|oldest|youngest|longest)\b", low):
        return "superlative"
    if re.search(r"\b(but|actually|isn't|wasn't|instead|secret|hidden|nobody|no one|really|until)\b", low): return "twist"
    if re.search(r"\b(you|your)\b", low): return "you"
    return "statement"


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def features(r):
    """The comparable things about one Short (shorts.csv row) as {feature: value}."""
    out = {k: (r.get(k) or "") for k in ("category", "format", "mood", "look_captions", "look_voice", "look_energy",
                                          "look_grade", "look_opening")}
    out["hook_type"] = r.get("hook_type") or hook_type(r.get("hook"))
    hw = _f(r.get("hook_words"))
    out["hook_len"] = "" if not hw else ("8 words or fewer" if hw <= 8 else "9 to 12 words" if hw <= 12 else "13 words or more")
    s = _f(r.get("seconds"))
    out["length"] = "" if not s else ("under 25 s" if s < 25 else "25 to 34 s" if s < 35 else "35 to 44 s" if s < 45 else "45 to 89 s" if s < 90 else "90 s or more")
    out["appeal"] = r.get("appeal") or ""
    slot = r.get("slot_uk") or ""
    if slot:
        h = int(slot[:2])
        out["slot"] = ("08:00 to 10:59" if 8 <= h < 11 else "11:00 to 13:59" if 11 <= h < 14 else "14:00 to 16:59" if 14 <= h < 17
                       else "17:00 to 19:59" if 17 <= h < 20 else "20:00 to 22:59" if 20 <= h < 23 else "other times")
    else: out["slot"] = ""
    try: out["weekday"] = dt.datetime.fromisoformat(r["posted"]).astimezone(UK).strftime("%A")
    except Exception: out["weekday"] = ""
    rs = _f(r.get("real_share"))
    out["pictures"] = "" if rs is None else ("mostly real pictures" if rs >= 0.5 else "mostly stock footage")
    t = r.get("title") or ""
    out["title_style"] = "question" if "?" in t else ("number in title" if re.search(r"\d", t) else "statement") if t else ""
    out["follow_line"] = r.get("follow_line") or ""
    for k in TESTED: out[k] = r.get(k) or ""
    out["late"] = r.get("late") or ""          # "late" or "on time" (freshness.py): judged for the late-upload rule
    out["explore"] = r.get("explore") or ""    # "yes" for the day's exploration Shorts (writer.py), "no" for the rest
    return out


def _med(vals):
    v = [x for x in vals if x is not None]
    return statistics.median(v) if v else None


def _per_k(rows, field):
    v = [(_f(r.get(field)), _f(r.get("yt_views"))) for r in rows]
    v = [1000 * a / b for a, b in v if a is not None and b]
    return statistics.median(v) if v else None


SUPPORT = [("yt_held_3s_pct", "still watching at 3 seconds", "{:.0f}%"), ("yt_avg_viewed_pct", "average viewed", "{:.0f}%"),
           ("yt_engaged_pct", "engaged views", "{:.0f}%"), ("subs_per_1k", "subscribers per 1,000 views", "{:.1f}"),
           ("shares_per_1k", "shares per 1,000 views", "{:.1f}"), ("likes_per_1k", "likes per 1,000 views", "{:.0f}")]


def _support(rows):
    out = {}
    for f, _, _ in SUPPORT[:3]: out[f] = _med(_f(r.get(f)) for r in rows)
    out["subs_per_1k"] = _per_k(rows, "yt_subs_gained")
    out["shares_per_1k"] = _per_k(rows, "yt_shares")
    out["likes_per_1k"] = _per_k(rows, "yt_likes")
    return out


def _why(grp, base, up):
    """The two supporting measures that differ most from the channel's typical Short, in the direction of the result."""
    diffs = []
    for f, label, fmt in SUPPORT:
        a, b = grp.get(f), base.get(f)
        if a is None or b is None or not b: continue
        d = a / b - 1
        if (d > 0) == up and abs(d) >= 0.08: diffs.append((abs(d), f"{label} {fmt.format(a)} vs {fmt.format(b)} typical"))
    return "; ".join(t for _, t in sorted(diffs, reverse=True)[:2])


def _logrel(r): return math.log(max(0.05, float(r["rel"])))


def t90(df):
    """The two-sided 90% t quantile for df degrees of freedom."""
    for d, t in T90:
        if df <= d: return t
    return 1.645


def interval(logs):
    """The 90% interval of a group's typical rel (exp of the mean log rel, t-based), or None under 2 Shorts."""
    n = len(logs)
    if n < 2: return None
    m, h = statistics.mean(logs), t90(n - 1) * statistics.stdev(logs) / math.sqrt(n)
    return math.exp(m - h), math.exp(m + h)


def split_time(scored):
    """The posting time that splits the measured Shorts into two halves (the median)."""
    ts = sorted(str(r.get("posted")) for r in scored if r.get("posted"))
    return ts[len(ts) // 2] if ts else ""


def halves_side(grp, cut):
    """+1 or -1 when the group's Shorts posted before `cut` and from `cut` on (2 or more each) are both above or both
    below typical; 0 when they disagree or a half has under 2 Shorts."""
    a = [_logrel(r) for r in grp if str(r.get("posted")) < cut]
    b = [_logrel(r) for r in grp if str(r.get("posted")) >= cut]
    if len(a) < 2 or len(b) < 2: return 0
    ma, mb = statistics.mean(a), statistics.mean(b)
    return 1 if ma > 0 and mb > 0 else -1 if ma < 0 and mb < 0 else 0


def gate(grp, lift, cut):
    """(verdict, reason): "push" or "cut back" only when the effect is proven (module docstring), else "early sign",
    "about typical" or "too few to tell"."""
    n, days = len(grp), len({uk_day(r) for r in grp})
    if n < 3: return "too few to tell", ""
    big = lift >= PUSH or lift <= CUT
    if n < MIN_N or days < MIN_DAYS: return ("early sign" if big else "about typical"), f"{n} Shorts over {days} UK day(s)"
    if not big: return "about typical", ""
    ci = interval([_logrel(r) for r in grp])
    up = lift >= PUSH
    clear = ci is not None and (ci[0] > 1.0 if up else ci[1] < 1.0)
    side = halves_side(grp, cut)
    if clear and side == (1 if up else -1): return ("push" if up else "cut back"), ""
    why = []
    if not clear: why.append(f"90% interval {ci[0]:.2f}x to {ci[1]:.2f}x includes typical" if ci else "no interval")
    if side != (1 if up else -1): why.append("the two halves of the data disagree" if side else "a half has under 2 Shorts")
    return "early sign", "; ".join(why)


# ---------------- pauses (the 14-day replacement for "stop") ----------------
def load_pauses(path=None):
    try: return json.loads(pathlib.Path(path or PAUSES).read_text())
    except Exception: return {}


def save_pauses(pauses, path=None):
    p = pathlib.Path(path or PAUSES); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pauses, indent=1, sort_keys=True))


def pause_state(key, grp, floor, pauses, today):
    """("pause" | "retest" | None, why) for one choice, updating `pauses` (module docstring)."""
    week = [r for r in grp if age_days(r) >= 7 and r.get("yt_views") not in (None, "")]
    views = lambda rs: statistics.median(_f(r["yt_views"]) or 0 for r in rs)
    st = pauses.get(key)
    if st:
        until = st.get("until", "")
        if today < until: return "pause", f"paused {st.get('since')} to {until}: {st.get('why', '')}"
        new = [r for r in week if uk_day(r) >= until]           # judged only on the Shorts made after the pause
        if floor is not None and len(new) >= RETEST_N and len({uk_day(r) for r in new}) >= 2:
            med = views(new)
            if med < PAUSE_MARGIN * floor:
                st.update(since=today, until=str(dt.date.fromisoformat(today) + dt.timedelta(days=PAUSE_FOR)), times=int(st.get("times", 1)) + 1,
                          why=f"retest: {len(new)} new Shorts a week old with a median of {med:.0f} views, under the floor of {floor:.0f}")
                return "pause", f"paused again {today} to {st['until']}: {st['why']}"
            if med >= floor:
                pauses.pop(key, None); return None, ""          # the retest beat the floor: the pause is lifted
        return "retest", f"back on a small share after a pause ({st.get('since')} to {until}); {len(new)} retest Shorts a week old so far"
    if floor is None: return None, ""
    days = {uk_day(r) for r in week}
    if len(week) >= PAUSE_N and len(days) >= PAUSE_DAYS:
        med = views(week)
        if med < PAUSE_MARGIN * floor:
            until = str(dt.date.fromisoformat(today) + dt.timedelta(days=PAUSE_FOR))
            why = (f"{len(week)} Shorts a week old over {len(days)} UK days with a median of {med:.0f} views, under three "
                   f"quarters of the floor of {floor:.0f}")
            pauses[key] = {"since": today, "until": until, "why": why, "times": 1}
            return "pause", f"paused {today} to {until}: {why}"
    return None, ""


def analyse(rows, pauses=None, today=None):
    """rows: shorts.csv rows with 'rel' set (or None). Returns (table rows for drivers.csv, base support measures).
    `pauses`: the pause record (load_pauses()), updated in place; the caller saves it."""
    pauses = {} if pauses is None else pauses
    today = today or NOW.astimezone(UK).date().isoformat()
    scored = [r for r in rows if r.get("rel") not in (None, "")]
    base = _support(scored)
    floor = dead_floor(rows)
    cut = split_time(scored)
    table = []
    for feat, label in FEATURES:
        groups = {}
        for r in scored:
            v = features(r).get(feat)
            if v: groups.setdefault(v, []).append(r)
        if len(groups) < 2: continue
        for v, grp in groups.items():
            logs = [_logrel(r) for r in grp]
            n = len(logs); lift = math.exp(sum(logs) / (n + SHRINK))
            verdict, gwhy = gate(grp, lift, cut)
            pv, pwhy = (None, "") if feat in NEVER_PAUSED else pause_state(f"{feat}|{v}", grp, floor, pauses, today)
            if pv: verdict = pv
            sup = _support(grp)
            why = pwhy if pv else (_why(sup, base, lift >= 1) if n >= 3 and abs(math.log(lift)) >= math.log(1.1) else "")
            if gwhy and verdict == "early sign": why = "; ".join(x for x in (why, f"not proven: {gwhy}") if x)
            table.append({"feature": feat, "feature_label": label, "value": v, "n": n, "lift": round(lift, 2),
                          "median_rel": round(statistics.median(float(r["rel"]) for r in grp), 2), "verdict": verdict,
                          "held_3s_pct": round(sup["yt_held_3s_pct"]) if sup["yt_held_3s_pct"] is not None else "",
                          "avg_viewed_pct": round(sup["yt_avg_viewed_pct"]) if sup["yt_avg_viewed_pct"] is not None else "",
                          "subs_per_1k": round(sup["subs_per_1k"], 1) if sup["subs_per_1k"] is not None else "",
                          "shares_per_1k": round(sup["shares_per_1k"], 1) if sup["shares_per_1k"] is not None else "",
                          "why": why})
    table.sort(key=lambda t: (t["feature"], -t["lift"]))
    return table, base


# ---------------- Instagram (24 October) ----------------
def ig_features(r):
    """The comparable things about one Reel (shorts.csv row) for analyse_instagram."""
    return {"ig_trial": r.get("ig_trial") or "", "ig_caption": r.get("ig_caption") or "", "ig_hour": r.get("ig_hour") or "",
            "ig_pick": r.get("ig_pick") or "", "ig_category": r.get("category") or ""}


def ig_rel_rows(rows, now=None):
    """Reels posted to Instagram a day ago or more, each a copy of its shorts.csv row with "rel" = its Instagram views over
    the median of the Reels posted to Instagram the same UK day (widening to ±1, then ±3 days when a day has under 3)
    and "posted" = when it went to Instagram, so gate() counts Instagram's own days and halves."""
    now = now or NOW
    pts = []
    for r in rows:
        v, at = _f(r.get("ig_views")), r.get("ig_posted")
        if v is None or not at: continue
        try: t = dt.datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        except ValueError: continue
        if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
        if (now - t).total_seconds() < 86400: continue          # a Reel under a day old waits
        pts.append((t.astimezone(UK).date(), v, t, r))
    out = []
    for day, v, t, r in pts:
        for w in (0, 1, 3):
            peers = [pv for pd, pv, _, _ in pts if abs((pd - day).days) <= w]
            if len(peers) >= 3: break
        med = statistics.median(peers) if peers else 0
        if med > 0: out.append({**r, "rel": v / med, "posted": t.isoformat()})
    return out


def analyse_instagram(rows, now=None):
    """Instagram's own tests (trial reel, caption, posting hour, how the Reel was picked) and the categories on Instagram,
    each against Instagram views (ig_rel_rows), as drivers.csv rows. The same shrinkage and proof gate as analyse(); never
    paused, never put to the writer (PIPELINE_ONLY): social.ig_share reads the verdicts (a proven arm gets 80% of Reels,
    never all, so the test keeps measuring)."""
    pseudo = ig_rel_rows(rows, now)
    if not pseudo: return []
    cut, table = split_time(pseudo), []
    for feat, label in IG_FEATURES:
        groups = {}
        for r in pseudo:
            v = ig_features(r).get(feat)
            if v: groups.setdefault(v, []).append(r)
        if len(groups) < 2: continue
        for v, grp in groups.items():
            logs = [_logrel(r) for r in grp]
            n = len(logs); lift = math.exp(sum(logs) / (n + SHRINK))
            verdict, gwhy = gate(grp, lift, cut)
            table.append({"feature": feat, "feature_label": label, "value": v, "n": n, "lift": round(lift, 2),
                          "median_rel": round(statistics.median(float(r["rel"]) for r in grp), 2), "verdict": verdict,
                          "held_3s_pct": "", "avg_viewed_pct": "", "subs_per_1k": "", "shares_per_1k": "",
                          "why": "against Instagram views" + (f"; not proven: {gwhy}" if gwhy and verdict == "early sign" else "")})
    table.sort(key=lambda t: (t["feature"], -t["lift"]))
    return table


# ---------------- the category mix (shared by the recipe and writer.category_shares) ----------------
CAT_FLOOR, CAT_CAP, RETEST_SHARE = 0.07, 0.35, 0.05     # floor 7% (data report, 24 October: 5% left 4 categories at 0.6 a day)


def timed_mins(today=None):
    """Categories held at a minimum share until a date (config category_min, e.g. Gaming 15% until the GTA 6 window
    closes on 26 November: the data report's diversity item). {category: share} for the minimums still in force."""
    try: cfg = json.loads((ROOT / "config.json").read_text()).get("category_min") or {}
    except Exception: cfg = {}
    today = today or dt.datetime.now(UK).date()
    out = {}
    for cat, m in cfg.items():
        try:
            if today <= dt.date.fromisoformat(str(m.get("until"))): out[cat] = float(m.get("share") or 0)
        except (ValueError, AttributeError, TypeError): continue
    return out


def category_mix(rows, today=None):
    """Each category's share of the day's Shorts from drivers.csv rows (feature "category"): weight lift squared, at least
    CAT_FLOOR and at most CAT_CAP each, so no category drops out of measurement and none takes over (24 October: the old
    mix gave Music 33%, Film 32%, Sport 20% and 4% to each of the rest); a paused category gets none, one being retested
    RETEST_SHARE. {} without category rows."""
    w, fixed = {}, {}
    for r in rows:
        if r.get("feature") != "category" or not r.get("value"): continue
        v = r.get("verdict")
        if v in PAUSED: fixed[r["value"]] = 0.0; continue
        if v == "retest": fixed[r["value"]] = RETEST_SHARE; continue
        try: lift = float(r.get("lift") or 1)
        except ValueError: continue
        w[r["value"]] = max(0.2, lift) ** 2
    if not w: return {k: v for k, v in fixed.items()} if fixed else {}
    out = _clamp(w, fixed)
    # a category held at a minimum until a date (timed_mins, config category_min) is fixed at it when the data gives it
    # less, and the rest is shared out again within the floor and cap (a paused category stays paused)
    lift = {k: m for k, m in timed_mins(today).items() if out.get(k) != 0.0 and out.get(k, 0.0) < m and k not in fixed}
    if lift and sum(lift.values()) + sum(fixed.values()) < 1:
        out = _clamp({k: x for k, x in w.items() if k not in lift}, {**fixed, **lift})
    return out


def _clamp(w, fixed):
    """Shares from weights `w` in the room `fixed` leaves, each within [CAT_FLOOR, CAT_CAP], normalised with `fixed`."""
    room = max(0.0, 1.0 - sum(fixed.values()))
    if not w: return dict(fixed)
    share = {k: room * x / sum(w.values()) for k, x in w.items()}
    held = set()
    for _ in range(30):          # clamp to [floor, cap] and hand what is freed or taken to the categories still free
        lo = {k for k, s in share.items() if s < CAT_FLOOR - 1e-12 and k not in held}
        hi = {k for k, s in share.items() if s > CAT_CAP + 1e-12 and k not in held}
        if not lo and not hi: break
        for k in lo: share[k] = CAT_FLOOR
        for k in hi: share[k] = CAT_CAP
        held |= lo | hi
        free = [k for k in share if k not in held]
        left = room - sum(share[k] for k in held)
        if not free or left <= 0: break
        tot = sum(w[k] for k in free)
        for k in free: share[k] = left * w[k] / tot
    out = {**share, **fixed}
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()} if tot else out


def recipe(table, rows):
    """What the writer should lean towards, from proven results only, as lines of text."""
    solid = [t for t in table if t["n"] >= MIN_N]
    n_scored = len([r for r in rows if r.get("rel") not in (None, "")])
    if n_scored < 15 or not solid:
        return ["Not enough measured Shorts yet (15 needed, each public for 24 hours): keep the variety rules and spread "
                "categories, formats and hook styles evenly so the comparison fills in fast."]
    L = []
    cats = [t for t in table if t["feature"] == "category" and t["n"] >= 3]
    if cats:
        mix = category_mix(cats)
        L.append("Category mix for the day (from the data, every category at least 5% and none over 35%, and 1 Short in 5 "
                 "an exploration Short in any category): " + ", ".join(f"{k} {round(100 * s)}%" for k, s in sorted(mix.items(), key=lambda kv: -kv[1])) + ".")
    for feat, label in FEATURES[1:]:
        if feat in PIPELINE_ONLY: continue      # not the writer's choice: the pipeline reads those verdicts itself
        push = [t for t in solid if t["feature"] == feat and t["verdict"] == "push"]
        cut = [t for t in solid if t["feature"] == feat and t["verdict"] == "cut back"]
        if push or cut:
            parts = []
            if push: parts.append("lean towards " + ", ".join(f"{t['value']} ({t['lift']}x, {t['n']} Shorts)" for t in push))
            if cut: parts.append("use less " + ", ".join(f"{t['value']} ({t['lift']}x, {t['n']} Shorts)" for t in cut))
            L.append(f"{label}: " + "; ".join(parts) + ".")
    pauses = [t for t in table if t["verdict"] in PAUSED and t["feature"] not in PIPELINE_ONLY]
    if pauses:
        L.append("Paused for 14 days (a week on, little to no views), then retested: " +
                 "; ".join(f"{t['feature_label'].lower()} \"{t['value']}\"" for t in pauses) + ".")
    return L or ["Nothing stands clearly above or below typical yet: keep the variety rules and the spread of categories."]
