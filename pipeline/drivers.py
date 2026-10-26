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


def channel_of(r):
    """Which of the line's channels a Short is on (shorts.csv "channel"; a row without one is the main channel's)."""
    return r.get("channel") or "main"


def dead(rows):
    """The Shorts a week old or more with views under the floor: never followed up, remade or posted about again. Each
    channel is judged against its own typical week-old Short (25 October: peers from the same channel), so a new channel's
    first Shorts are not dead by the main channel's floor, nor the main channel's by a small channel's."""
    out = []
    for ch in dict.fromkeys(channel_of(r) for r in rows):
        grp = [r for r in rows if channel_of(r) == ch]
        floor = dead_floor(grp)
        if floor is not None: out += [r for r in grp if age_days(r) >= 7 and (_f(r.get("yt_views")) or 0) < floor]
    return out


FEATURES = [("category", "Category"), ("format", "Format"), ("hook_type", "Hook style"), ("hook_len", "Hook length"),
            ("length", "Length"), ("slot", "Posting time (UK)"), ("weekday", "Day posted"), ("mood", "Music mood"),
            ("pictures", "Pictures"), ("title_style", "Title"), ("look_captions", "Captions"), ("look_voice", "Voice"),
            ("look_energy", "Camera energy"), ("look_grade", "Colour grade"), ("look_opening", "Opening"), ("look_style", "Style (text and pace)"), ("look_closing", "Closing chip"), ("sub_push", "Subscribe line"), ("follow_line", "Follow line"), ("ending", "Ending"), ("title_search", "Title wording"),
            ("first_frame", "First frame"), ("angles", "Angle research"), ("replies", "Comment replies"), ("kind", "Kind of Short"), ("source", "Topic source"), ("series", "Series"), ("franchise", "Named series"), ("writer", "Writer model"),
            ("appeal", "Appeal"), ("late", "Posted late"), ("explore", "Exploration Short"), ("title_emoji", "Title emoji"),
            ("fx_energy", "Camera energy test"), ("fx_grade", "Colour grade test"), ("fx_opening", "Opening test"), ("fx_slot", "Posting quarter test"), ("writer_arm", "Writer model test"),
            ("title_answer", "Title answer"), ("hook_named", "Hook names the lead"), ("sponsor", "Carries a campaign (sound or hashtag)")]
# Instagram's own tests (social.py, 24 October) and the categories on Instagram: scored against Instagram views
# (analyse_instagram), not YouTube's, and decided by social.py (ig_share), never put to the writer
IG_FEATURES = [("ig_trial", "Instagram trial reel"), ("ig_caption", "Instagram caption"), ("ig_hour", "Instagram posting hour"),
               ("ig_pick", "Instagram pick"), ("ig_category", "Category on Instagram")]
PIPELINE_ONLY = {"late", "explore", "fx_energy", "fx_grade", "fx_opening", "fx_slot", "writer_arm", "hook_named", "look_style", "look_closing", "sub_push", "sponsor"} | {f for f, _ in IG_FEATURES}     # measured like the rest, decided by the pipeline, never put to the writer (look_style: looks.py draws it, 2 in 3 minimal; sponsor: sponsor.pick draws it by board id)
NEVER_PAUSED = {"weekday", "late", "explore", "fx_energy", "fx_grade", "fx_opening", "fx_slot", "writer_arm", "hook_named", "title_answer", "look_style", "look_closing", "sub_push", "sponsor"} | {f for f, _ in IG_FEATURES}       # nothing the writer could leave out (a test's arms settle by their verdicts)
TESTED = ("ending", "title_search", "first_frame", "angles", "replies", "kind", "source", "series", "franchise", "writer", "title_emoji",
          "fx_energy", "fx_grade", "fx_opening", "fx_slot", "writer_arm", "title_answer", "sub_push", "sponsor")     # recorded on the board by the writer (writer.py tests); fx_*, writer_arm and title_answer as assigned (an intention-to-treat comparison); sponsor: the campaign id or "none" (sponsor.py)
# The writer's arms as the board records them (writer.TESTS "hook_type" and "length"): only these count as an assigned arm
# in features(); anything else a board carries (length "as written", when a long arm came back at a normal length) is
# scored on what the Short did
SERIES_PREFIX = re.compile(r"^\s*[^#?:|]{2,40}\s#\d+(?:\s+of\s+\d+)?\s*[:|]\s*")      # a series or franchise name and number leading a title (series.py, writer.py)
HOOK_ARMS = ("statement", "question", "number", "superlative", "twist")
LENGTH_ARMS = ("under 25 s", "25 to 34 s", "35 to 44 s", "about 60 s", "about 2 min")
# The number arm's own definition: the hook opens on a number (its first word, after at most "over", "nearly", "just" and the
# like), not a name that holds one ("Formula 1", "Shrek 2") and not a date ("23 October", "1999", "On 11 April 1970")
DIGITS = r"[$£€]?\d[\d,.]*"
NUMWORD = (r"(?:one(?! of\b| day\b)|two|three|four|five|six|seven|eight|nine|ten(?! hag\b)|eleven|twelve|twenty|thirty|forty|fifty|"
           r"sixty|seventy|eighty|ninety|hundred|thousand|million|billion)")
LEADS_WITH_NUMBER = re.compile(rf"(?:(?:over|nearly|almost|about|around|more than|at least|up to|just)\s+)?(?:{DIGITS}|{NUMWORD})\b"
                               rf"|only\s+{DIGITS}\b")
DATE_FIRST = re.compile(r"(?:on |in |back in )?(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday) )?(?:\d{1,2}(?:st|nd|rd|th)? )?"
                        r"(?:(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|(?:1[89]\d\d|20\d\d)\b)")
T90 = ((1, 6.314), (2, 2.920), (3, 2.353), (4, 2.132), (5, 2.015), (6, 1.943), (7, 1.895), (8, 1.860), (9, 1.833),
       (10, 1.812), (12, 1.782), (15, 1.753), (20, 1.725), (30, 1.697), (60, 1.671))


def hook_type(h):
    """A label for the first line as written, by the writer's own hook arms (writer.TESTS "hook_type"): question, number,
    superlative, twist, you, statement. A hook is "number" only when it opens on the number, as the number arm asks (see
    LEADS_WITH_NUMBER); until 24 October any number word or digit anywhere made it one (59 of 114 hooks, 5 of the best 8,
    among them "The Beatles recorded their entire debut album in just twelve hours", which is a statement). Superlatives
    count in the first six words, where the superlative arm puts them. Shorts that were given a hook arm are scored on the
    arm as assigned (features below), so this label only describes the rest and checks how often an arm was followed."""
    s = (h or "").strip(); low = s.lower()
    if not s: return ""
    if s.endswith("?") or re.match(r"(did you know|have you ever|ever wondered|can you guess|guess what)\b", low): return "question"
    if LEADS_WITH_NUMBER.match(low) and not DATE_FIRST.match(low): return "number"
    if re.search(r"\b(first|only|biggest|largest|fastest|most|least|never|ever|record|smallest|oldest|youngest|longest)\b",
                 " ".join(low.split()[:6])):
        return "superlative"
    if re.search(r"\b(but|actually|isn't|wasn't|instead|secret|hidden|nobody|no one|really|until)\b", low): return "twist"
    if re.search(r"\b(you|your)\b", low): return "you"
    return "statement"


def hook_used(h, arm):
    """What a hook counts as when asking whether its arm was followed (analytics.test_progress): the hook's own label, except
    that the statement arm is any plain statement of the news, so a hook leaning on "you", a twist or a superlative still
    follows it (only a question or an opening number does not)."""
    label = hook_type(h)
    return "statement" if arm == "statement" and label in ("you", "twist", "superlative") else label


def length_label(seconds):
    s = _f(seconds)
    return "" if not s else ("under 25 s" if s < 25 else "25 to 34 s" if s < 35 else "35 to 44 s" if s < 45 else "45 to 89 s" if s < 90 else "90 s or more")


def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def features(r):
    """The comparable things about one Short (shorts.csv row) as {feature: value}."""
    out = {k: (r.get(k) or "") for k in ("category", "format", "mood", "look_captions", "look_voice", "look_energy",
                                          "look_grade", "look_opening", "look_style", "look_closing")}
    # the hook and length tests are scored as assigned (content review, 24 October): a Short given a hook or length arm
    # counts under that arm whatever the text or the render came to (an intention-to-treat comparison); the rest under
    # the label of what was written (hook_type) and how long it ran
    out["hook_type"] = (r.get("arm_hook_type") if r.get("arm_hook_type") in HOOK_ARMS else "") or r.get("hook_type") or hook_type(r.get("hook"))
    hw = _f(r.get("hook_words"))
    out["hook_len"] = "" if not hw else ("8 words or fewer" if hw <= 8 else "9 to 12 words" if hw <= 12 else "13 words or more")
    out["length"] = (r.get("arm_length") if r.get("arm_length") in LENGTH_ARMS else "") or length_label(r.get("seconds"))
    out["hook_named"] = r.get("hook_named") or ""
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
    if r.get("series_name") or r.get("franchise") in ("named", "series"):       # "Science Explained #12: Why ...": the prefix's number is no title style
        t = SERIES_PREFIX.sub("", t, count=1)
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


def floor_of(floor, r):
    """The dead floor that applies to a row: one number (one channel's rows) or {channel: floor} (26 October: the
    verdicts pool every channel's Shorts, each judged against its own channel's floor)."""
    return floor.get(channel_of(r)) if isinstance(floor, dict) else floor


def pause_state(key, grp, floor, pauses, today):
    """("pause" | "retest" | None, why) for one choice, updating `pauses` (module docstring). With floors per channel
    (a dict) each row's views are scaled to the main channel's floor before the median, so a choice is paused on how its
    Shorts do against their own channel's typical Short, whichever channels they are on."""
    ref = (floor.get("main") or next((f for f in floor.values() if f), None)) if isinstance(floor, dict) else floor
    week = [r for r in grp if age_days(r) >= 7 and r.get("yt_views") not in (None, "") and floor_of(floor, r)]
    views = lambda rs: statistics.median((_f(r["yt_views"]) or 0) * ref / floor_of(floor, r) for r in rs)
    floor = ref
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


def contrast(groups):
    """{value: rows} keeping only the channels that show 2 or more of the choice's values (26 October). rel is each Short's
    views over its own channel's same-day peers, so a channel that only ever had one value of a choice (one category, one
    voice) averages about typical on it and would only drag that value's pooled lift towards 1."""
    seen = {}
    for v, grp in groups.items():
        for r in grp: seen.setdefault(channel_of(r), set()).add(v)
    keep = {ch for ch, vs in seen.items() if len(vs) >= 2}
    out = {v: [r for r in grp if channel_of(r) in keep] for v, grp in groups.items()}
    return {v: g for v, g in out.items() if g}


def analyse(rows, pauses=None, today=None):
    """rows: shorts.csv rows with 'rel' set (or None). Returns (table rows for drivers.csv, base support measures).
    `pauses`: the pause record (load_pauses()), updated in place; the caller saves it."""
    pauses = {} if pauses is None else pauses
    today = today or NOW.astimezone(UK).date().isoformat()
    # 26 October: every channel's Shorts feed one set of verdicts (Charlie: "all of them contributing to the same learning
    # model"). rel is already each Short's views over its own channel's same-day peers (analytics.relative per channel),
    # so the lifts pool as they are; the dead floors stay per channel and pause_state scales views to the main one's.
    scored = [r for r in rows if r.get("rel") not in (None, "")]
    base = _support(scored)
    floors = {ch: dead_floor([r for r in rows if channel_of(r) == ch]) for ch in dict.fromkeys(channel_of(r) for r in rows)}
    floor = floors if len(floors) > 1 else next(iter(floors.values()), None)
    cut = split_time(scored)
    table = []
    for feat, label in FEATURES:
        groups = {}
        for r in scored:
            v = features(r).get(feat)
            if v: groups.setdefault(v, []).append(r)
        groups = contrast(groups)
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


# ---------------- one model, each channel's own reading (26 October) ----------------
# Charlie, 26 October: one learning model for every channel or one each, whichever gives the best data. One pooled model,
# channel-aware: the verdicts above pool every channel (more Shorts, so proof comes sooner), and channel_table() shows each
# channel's own reading beside them, partially pooled (a channel with few Shorts reads as the pool, one with many as
# itself). A channel only departs from the pooled verdict ("push here", "cut back here") when its own Shorts pass the same
# proof gate on their own, disagree with the pool, and number EXC_N or more; writer.winners(channel) applies it.
CHANNEL_FIELDS = ["channel", "feature", "feature_label", "value", "n", "lift", "own_lift", "pooled_lift", "pooled_verdict",
                  "verdict", "exception", "why"]
EXC_N = 10


def channel_table(rows, table):
    """Rows for analytics/channel_drivers.csv: per channel, per choice with 2 or more values on that channel, per value
    with 2 or more Shorts: lift (the channel's Shorts shrunk towards the pooled lift), own_lift (shrunk towards typical,
    as the pooled table is), the pooled lift and verdict, the channel's own gate() verdict and any exception."""
    pooled = {(t["feature"], t["value"]): t for t in table}
    feats = [(r, features(r)) for r in rows if r.get("rel") not in (None, "")]
    out = []
    for ch in dict.fromkeys(channel_of(r) for r, _ in feats):
        mine = [(r, f) for r, f in feats if channel_of(r) == ch]
        cut = split_time([r for r, _ in mine])
        for feat, label in FEATURES:
            groups = {}
            for r, f in mine:
                if f.get(feat): groups.setdefault(f[feat], []).append(r)
            if len(groups) < 2: continue
            for v, grp in groups.items():
                if len(grp) < 2: continue
                logs = [_logrel(r) for r in grp]; n = len(logs)
                p = pooled.get((feat, v)) or {}
                pl = float(p.get("lift") or 1.0); pv = p.get("verdict") or ""
                own = math.exp(sum(logs) / (n + SHRINK))
                verdict, gwhy = gate(grp, own, cut)
                exc = verdict + " here" if n >= EXC_N and verdict in ("push", "cut back") and verdict != pv else ""
                out.append({"channel": ch, "feature": feat, "feature_label": label, "value": v, "n": n,
                            "lift": round(math.exp((sum(logs) + SHRINK * math.log(pl)) / (n + SHRINK)), 2),
                            "own_lift": round(own, 2), "pooled_lift": round(pl, 2), "pooled_verdict": pv, "verdict": verdict,
                            "exception": exc, "why": gwhy})
    out.sort(key=lambda t: (t["channel"], t["feature"], -t["lift"]))
    return out


# ---------------- the factorial round's verdicts (26 October) ----------------
# Every Short in the round takes an arm of every factor, 50/50 and independent (writer.test_plan), on every channel. Each
# factor is judged by a regression of log rel on its arm (as assigned), controlling for the channel, exploration Shorts
# and every other factor's arm, so the other factors' noise comes out of the comparison instead of widening it (pure
# Python, Frisch-Waugh-Lovell: residualise y and the arm on the controls, then one slope). A winner needs the 90% interval
# clear of no difference, 10 Shorts an arm, an effect of 15% or more and both halves of the data (split at the median
# posting time) pointing the same way. "even" settles a factor whose interval sits inside +/-15% with 20 an arm; "no clear
# difference" settles one whose arms both reach per_arm. A settled factor leaves the round (writer.settled); a winner is
# used on every Short and still challenged 1 in writer.RETEST.
# The opening (Charlie, 26 October: "more emphasis on hook testing"; the Partner Programme counts engaged views, about a third
# of the views): a factor that changes the first seconds (OPENING, or an evolve.py gene aimed at them) is judged on the share
# of views that stayed (engaged views / views, YouTube Analytics), the thing a hook moves, not on views, which the feed
# decides mostly before anyone has seen the hook. Its winner needs 10% (EVEN_ENG) and must not clearly cost views: the views
# fit's 90% interval below 1 for the winning arm withholds it when the loss cancels the share gain (fewer engaged views a
# Short) or is 15% or more (EVEN: the feed is showing it to clearly fewer people); views_effect shows that fit.
ROUND_FIELDS = ["round", "factor", "arm_a", "arm_b", "n_a", "n_b", "effect", "low", "high", "halves", "verdict", "winner",
                "leaning", "why", "metric", "views_effect"]
EVEN, WIN_N, EVEN_N = 0.14, 10, 20
OPENING = ("hook_type", "first_frame", "fx_opening")
EVEN_ENG, ENG_K = 0.095, 10.0       # 10% on the engaged share; ENG_K views of shrinkage toward the group's share


def metric_of(f, metrics=None):
    """What a round factor is judged on: "engaged" (the engaged share) for the opening, else "views"; `metrics` ({factor:
    metric}, analytics.round_metrics: the opening genes) overrides."""
    m = (metrics or {}).get(f)
    return m if m in ("engaged", "views") else "engaged" if f in OPENING else "views"


def engaged_pair(r):
    """(engaged views, YouTube Analytics views) of one Short, or None without them. Rows from before yt_an_views (26 October)
    rebuild the views from yt_engaged_pct."""
    try: ev = float(r.get("yt_engaged_views"))
    except (TypeError, ValueError): return None
    try: av = float(r.get("yt_an_views"))
    except (TypeError, ValueError):
        try:
            pct = float(r.get("yt_engaged_pct")); av = 100 * ev / pct if pct > 0 else None
        except (TypeError, ValueError): av = None
    if not av or av <= 0 or ev < 0: return None
    return min(ev, av), av


def assigned(r, f):
    """The arm a Short was given for a round factor, as the board recorded it (an intention-to-treat comparison). A gene
    factor ("gene:g001", pipeline/evolve.py) is read from the row's "genes" cell: "gene:g001=b;gene:g002=a"."""
    if f.startswith("gene:"):
        for part in str(r.get("genes") or "").split(";"):
            k, _, v = part.partition("=")
            if k.strip() == f: return v.strip()
        return ""
    return (r.get("arm_hook_type") if f == "hook_type" else r.get("arm_length") if f == "length" else r.get(f)) or ""


def _gs(cols):
    """An orthonormal basis of the columns (modified Gram-Schmidt), leaving out any the earlier ones already span."""
    basis = []
    for c in cols:
        v = [float(x) for x in c]
        for q in basis:
            d = sum(a * b for a, b in zip(v, q)); v = [a - d * b for a, b in zip(v, q)]
        norm = math.sqrt(sum(a * a for a in v))
        if norm > 1e-6: basis.append([a / norm for a in v])
    return basis


def _resid(y, basis):
    for q in basis:
        d = sum(a * b for a, b in zip(y, q)); y = [a - d * b for a, b in zip(y, q)]
    return y


def _slope(rows, f, arm_b, others, yf=None):
    """(beta, se, df) of log rel (or yf(row)) on the arm-B indicator, controlling for the channel, exploration and `others`
    ({factor: arms}: an arm-B and a missing indicator each); None when the arm is fully explained by the controls or df < 2."""
    n = len(rows)
    cols = [[1.0] * n]
    for ch in sorted({channel_of(r) for r in rows}): cols.append([1.0 if channel_of(r) == ch else 0.0 for r in rows])
    cols.append([1.0 if r.get("explore") == "yes" else 0.0 for r in rows])
    for g, (ga, gb) in others.items():
        cols.append([1.0 if assigned(r, g) == gb else 0.0 for r in rows])
        cols.append([0.0 if assigned(r, g) in (ga, gb) else 1.0 for r in rows])
    basis = _gs(cols)
    y = [(yf or _logrel)(r) for r in rows]
    d = [1.0 if assigned(r, f) == arm_b else 0.0 for r in rows]
    ed, ey = _resid(d, basis), _resid(y, basis)
    sdd = sum(a * a for a in ed)
    df = n - len(basis) - 1
    if sdd < 1e-6 or df < 2: return None
    beta = sum(a * b for a, b in zip(ed, ey)) / sdd
    sse = sum((b - beta * a) ** 2 for a, b in zip(ed, ey))
    return beta, math.sqrt(sse / df / sdd), df


def _fit(grp, f, b, factors, yf=None):
    others = {g: tuple(x) for g, x in factors.items() if g != f and len(x) == 2}
    fit = _slope(grp, f, b, others, yf)
    if fit and fit[2] < 20: fit = _slope(grp, f, b, {}, yf)        # too few Shorts for every control: channel and exploration only
    return fit


def round_verdicts(rows, factors, start, per_arm=70, name="round", starts=None, metrics=None):
    """Rows for analytics/round.csv, one per round factor ({factor: [arm_a, arm_b]}): the Shorts posted from `start` (a UK
    date) with 24-hour views, every channel; effect = how many times arm B's views arm A's, adjusted (above), or for an
    opening factor (metric_of) arm B's engaged share against arm A's, on the Shorts with engaged views in. `starts` ({factor:
    UK date}, evolve.py, 26 October): a contest that began later than the round judges only the Shorts from its own start,
    so a new contest never inherits the Shorts of the one it replaced. With no engaged views in `rows` at all, every factor
    is judged on views."""
    pool = [r for r in rows if r.get("rel") not in (None, "") and uk_day(r) >= str(start)]
    has_eng = any(engaged_pair(r) for r in rows)        # the data has engaged views at all (else views, as before them)
    out = []
    for f, arms_ in factors.items():
        if len(arms_) != 2: continue
        a, b = arms_
        own = max(str(start), str((starts or {}).get(f) or start))
        grp = [r for r in pool if assigned(r, f) in (a, b) and (own == str(start) or uk_day(r) >= own)]
        metric = metric_of(f, metrics) if has_eng else "views"
        vgrp, yf, even = grp, None, EVEN
        if metric == "engaged":
            grp = [r for r in grp if engaged_pair(r)]
            pairs = [engaged_pair(r) for r in grp]
            p0 = max(0.01, sum(e for e, _ in pairs) / sum(v for _, v in pairs)) if pairs else 0.3
            yf = lambda r, p0=p0: (lambda e, v: math.log((e + ENG_K * p0) / (v + ENG_K)))(*engaged_pair(r))
            even = EVEN_ENG
        na, nb = sum(assigned(r, f) == a for r in grp), sum(assigned(r, f) == b for r in grp)
        row = {"round": name, "factor": f, "arm_a": a, "arm_b": b, "n_a": na, "n_b": nb, "effect": "", "low": "", "high": "",
               "halves": "", "verdict": "too few to tell", "winner": "", "leaning": "", "why": "", "metric": metric,
               "views_effect": ""}
        out.append(row)
        if min(na, nb) < 3:
            if metric == "engaged": row["why"] = "engaged views arrive about 3 days after a Short is posted"
            continue
        fit = _fit(grp, f, b, factors, yf)
        if not fit: row["why"] = "the arm cannot be told apart from the controls yet"; continue
        beta, se, df = fit
        h = t90(df) * se
        row.update(effect=round(math.exp(beta), 2), low=round(math.exp(beta - h), 2), high=round(math.exp(beta + h), 2))
        costs_views = False
        if metric == "engaged":         # the guard: a better opening that the feed shows to clearly fewer people is no win
            vf = _fit(vgrp, f, b, factors)
            if vf:
                vb, vh = vf[0], t90(vf[2]) * vf[1]
                row["views_effect"] = round(math.exp(vb), 2)
                fewer = (vb + vh < 0) if beta > 0 else (vb - vh > 0)        # the winning arm clearly gets fewer views
                net = abs(beta) + (vb if beta > 0 else -vb)                 # log engaged views a Short, winner over loser
                costs_views = fewer and (net <= 0 or abs(vb) >= EVEN)
        cut = split_time(grp)
        halves = [_slope([r for r in grp if (str(r.get("posted")) < cut) == first], f, b, {}, yf) for first in (True, False)]
        agree = all(halves) and all(abs(x[0]) > 1e-9 for x in halves) and (halves[0][0] > 0) == (halves[1][0] > 0) == (beta > 0)
        row["halves"] = "agree" if agree else "too few" if not all(halves) else "disagree"
        clear, small = beta - h > 0 or beta + h < 0, -even < beta - h and beta + h < even
        if clear and min(na, nb) >= WIN_N and abs(beta) >= even and agree and not costs_views:
            row.update(verdict="winner", winner=b if beta > 0 else a)
        elif small and min(na, nb) >= EVEN_N:
            row["verdict"] = "even"
        elif min(na, nb) >= per_arm:
            row["verdict"] = "no clear difference"
        else:
            row["verdict"] = "running"
            if abs(beta) >= 0.05: row["leaning"] = b if beta > 0 else a
            why = []
            if not clear: why.append("the 90% interval includes no difference")
            if min(na, nb) < WIN_N: why.append(f"{WIN_N - min(na, nb)} more Shorts on the smaller arm")
            if clear and abs(beta) < even: why.append(f"clear but under {round(100 * (math.exp(even) - 1))}%")
            if clear and not agree: why.append("the two halves of the data " + ("disagree" if row["halves"] == "disagree" else "are too small"))
            if clear and costs_views: why.append("wins on engaged share but costs views")
            row["why"] = "; ".join(why)
    return out


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


# ---------------- subscribers (25 October, the subscriber push) ----------------
# 15 subscribers from 26,500 views (about 0.5 per 1,000) and 1,000 needed: each Short's subscribers gained (shorts.csv
# yt_subs_gained, YouTube Analytics) against its views, compared with the Shorts posted the same UK day, scored for the arms of
# the subscriber push (sub_push, look_closing) and for the ending, the series and the category. Written to analytics/subs.csv
# (feature "subs:<name>"), not into drivers.csv: that file's verdicts mean views (the hub counts them, log_decisions logs
# them, writer.py and looks.py act on them), and a subscriber verdict must not be read as one.
# Most Shorts gain none, so a per-Short ratio against a median of zeros says nothing. Each Short is compared in counts instead
# (indirect standardisation): its subscribers against the subscribers its views would have brought at the rate of the
# Shorts posted the same UK day (itself left out; widening to +-1, then +-3 days while fewer than 3 peers). A group's lift is
# (observed + SUBS_PRIOR) / (expected + SUBS_PRIOR), shrunk like the views lift, and the verdict follows the same proof rule
# as gate(): 5 Shorts over 2 UK days, a lift of 1.25 or more (0.8 or less), an exact Poisson 90% interval of the group's
# observed count (over its expected one) clear of typical, and the Shorts posted before and after the median posting time
# both on the same side. Only Shorts with SUBS_MIN_VIEWS views, public SUBS_MIN_AGE_DAYS days (Analytics lags a day or two).
SUB_FEATURES = [("sub_push", "Subscribe line"), ("look_closing", "Closing chip"), ("ending", "Ending"), ("series", "Series"),
                ("category", "Category")]
SUBS_FIELDS = ["feature", "feature_label", "value", "n", "days", "views", "subs", "expected", "subs_per_1k", "typical_per_1k",
               "lift", "low", "high", "verdict", "why"]
SUBS_MIN_VIEWS, SUBS_MIN_AGE_DAYS, SUBS_PRIOR = 20, 3, 2.0


def sub_features(r):
    """The comparable things about one Short for the subscriber analysis: the arms of the push, the ending, the series it is
    in ("no series" for the rest) and the category."""
    f = features(r)
    return {"sub_push": f.get("sub_push") or "", "look_closing": f.get("look_closing") or "", "ending": f.get("ending") or "",
            "series": r.get("series_name") or "no series", "category": f.get("category") or ""}


def _pois_cdf(k, lam):
    """P(X <= k) for a Poisson mean lam."""
    if lam <= 0: return 1.0
    return min(1.0, sum(math.exp(-lam + i * math.log(lam) - math.lgamma(i + 1)) for i in range(int(k) + 1)))


def poisson_ci(o, level=0.90):
    """The exact (Garwood) interval for a Poisson mean from an observed count: o=5 gives 1.97 to 10.51 at 90%, o=0 gives 0 to
    3.00 (the tests check these against the chi-squared tables)."""
    a, o = (1 - level) / 2, int(round(o))
    top, low = 10.0 * (o + 10), 0.0
    if o > 0:                                   # P(X >= o | lam) rises with lam: the lam where it reaches a
        lo, hi = 0.0, top
        for _ in range(80):
            mid = (lo + hi) / 2
            if 1 - _pois_cdf(o - 1, mid) > a: hi = mid
            else: lo = mid
        low = (lo + hi) / 2
    lo, hi = 0.0, top                           # P(X <= o | lam) falls as lam rises: the lam where it drops to a
    for _ in range(80):
        mid = (lo + hi) / 2
        if _pois_cdf(o, mid) > a: lo = mid
        else: hi = mid
    return low, (lo + hi) / 2


def subs_points(rows, now=None):
    """The Shorts that can say something about subscribers, each with its UK day, views and subscribers: at least
    SUBS_MIN_VIEWS views, public SUBS_MIN_AGE_DAYS days, and a subscribers figure from Analytics (a blank is not a zero).
    26 October: every channel's Shorts count; a Short's expected subscribers come from its own channel's same-day peers."""
    now, pts = now or NOW, []
    for r in rows:
        v, s = _f(r.get("yt_views")), _f(r.get("yt_subs_gained"))
        if v is None or s is None or v < SUBS_MIN_VIEWS: continue
        try: t = dt.datetime.fromisoformat(str(r["posted"]))
        except (KeyError, ValueError, TypeError): continue
        if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
        if (now - t).total_seconds() < SUBS_MIN_AGE_DAYS * 86400: continue
        pts.append({"r": r, "day": t.astimezone(UK).date(), "posted": str(r.get("posted")), "views": v, "subs": max(0.0, s)})
    for p in pts:                                   # the subscribers its views would have brought at the same-day peers' rate
        for w in (0, 1, 3):
            peers = [q for q in pts if q is not p and channel_of(q["r"]) == channel_of(p["r"]) and abs((q["day"] - p["day"]).days) <= w]
            if len(peers) >= 3: break
        pv = sum(q["views"] for q in peers)
        p["exp"] = p["views"] * sum(q["subs"] for q in peers) / pv if len(peers) >= 3 and pv else None
    return pts


def sub_halves(grp, cut):
    """+1 or -1 when the group's Shorts posted before and from `cut` on (2 or more each) both brought more, or both fewer,
    subscribers than expected; 0 when they disagree; None when a half has under 2 Shorts."""
    side = []
    for half in ([p for p in grp if p["posted"] < cut], [p for p in grp if p["posted"] >= cut]):
        if len(half) < 2: return None
        side.append((sum(p["subs"] for p in half) + 1) / (sum(p["exp"] for p in half) + 1))
    return 1 if min(side) > 1 else -1 if max(side) < 1 else 0


def sub_gate(grp, lift, cut):
    """(verdict, reason, (low, high) of observed over expected): gate()'s proof rule for counts (see the section's note)."""
    n, days = len(grp), len({p["day"] for p in grp})
    o, e = sum(p["subs"] for p in grp), sum(p["exp"] for p in grp)
    ci = tuple(x / e for x in poisson_ci(o)) if e > 0 else None
    big = lift >= PUSH or lift <= CUT
    if n < 3: return "too few to tell", "", ci
    if n < MIN_N or days < MIN_DAYS: return ("early sign" if big else "about typical"), f"{n} Shorts over {days} UK day(s)", ci
    if not big: return "about typical", "", ci
    up = lift >= PUSH
    clear = ci is not None and (ci[0] > 1.0 if up else ci[1] < 1.0)
    side = sub_halves(grp, cut)
    if clear and side == (1 if up else -1): return ("push" if up else "cut back"), "", ci
    why = []
    if not clear: why.append(f"90% interval {ci[0]:.2f}x to {ci[1]:.2f}x includes typical" if ci else "no subscribers expected from the peers")
    if side != (1 if up else -1): why.append("a half has under 2 Shorts" if side is None else "the two halves of the data disagree")
    return "early sign", "; ".join(why), ci


def analyse_subscribers(rows, now=None):
    """analytics/subs.csv rows (SUBS_FIELDS): for each arm or value of SUB_FEATURES, the Shorts that had it, their views,
    subscribers gained, the subscribers expected at the same-day peers' rate, subscribers per 1,000 views against the typical
    rate for those Shorts, the shrunk lift and the proof rule's verdict. Never paused, never put to the writer through the
    views recipe (subs_recipe is its own line)."""
    pts = [p for p in subs_points(rows, now) if p["exp"] is not None]
    if not pts: return []
    cut, table = split_time([p["r"] for p in pts]), []
    for feat, label in SUB_FEATURES:
        groups = {}
        for p in pts:
            v = sub_features(p["r"]).get(feat)
            if v: groups.setdefault(v, []).append(p)
        if len(groups) < 2: continue
        for v, grp in groups.items():
            o, e, views = sum(p["subs"] for p in grp), sum(p["exp"] for p in grp), sum(p["views"] for p in grp)
            lift = (o + SUBS_PRIOR) / (e + SUBS_PRIOR)
            verdict, why, ci = sub_gate(grp, lift, cut)
            table.append({"feature": f"subs:{feat}", "feature_label": f"Subscribers: {label}", "value": v, "n": len(grp),
                          "days": len({p["day"] for p in grp}), "views": int(views), "subs": int(round(o)), "expected": round(e, 2),
                          "subs_per_1k": round(1000 * o / views, 2), "typical_per_1k": round(1000 * e / views, 2), "lift": round(lift, 2),
                          "low": round(ci[0], 2) if ci else "", "high": round(ci[1], 2) if ci else "", "verdict": verdict,
                          "why": f"not proven: {why}" if why and verdict == "early sign" else why})
    table.sort(key=lambda t: (t["feature"], -t["lift"]))
    return table


def subs_summary(rows, now=None):
    """Overall subscribers per 1,000 views over the Shorts that count (subs_points) and the best Short for subscribers (most
    gained, then the higher rate): {"shorts", "views", "subs", "per_1k", "best": {"id", "title", "subs", "views", "per_1k"} or None}."""
    pts = subs_points(rows, now)
    views, subs = sum(p["views"] for p in pts), sum(p["subs"] for p in pts)
    top = max(pts, key=lambda p: (p["subs"], p["subs"] / p["views"]), default=None)
    best = ({"id": top["r"].get("short") or "", "title": top["r"].get("title") or "", "subs": int(top["subs"]), "views": int(top["views"]),
             "per_1k": round(1000 * top["subs"] / top["views"], 2)} if top and top["subs"] > 0 else None)
    return {"shorts": len(pts), "views": int(views), "subs": int(subs), "per_1k": round(1000 * subs / views, 2) if views else None, "best": best}


def subs_recipe(table, views=()):
    """Recipe lines (analytics.py puts them in insights.md's Recipe) for an arm of the subscriber push that is proven, for
    subscribers, to win or to lose: the writer's own arms (the spoken subscribe line, the ending) and the chip (a line the
    writer does not act on, labelled so writer.recipe() leaves it out). One line a feature; a "push" is read before a "cut
    back" (the same result seen from the other arm). `views`: drivers.csv rows: no line names an arm the views test has cut
    back or paused (the subscriber push must not cost views)."""
    from subscribe import ARM_PAIRS
    hurt = {(r.get("feature"), r.get("value")) for r in views if r.get("verdict") in ("cut back", "pause", "stop")}
    out, seen = [], set()
    for t in sorted(table, key=lambda t: t["verdict"] != "push"):
        f = t["feature"].removeprefix("subs:")
        if t["verdict"] not in ("push", "cut back") or f not in ("sub_push", "look_closing", "ending") or f in seen: continue
        win = t["verdict"] == "push"
        pair = ARM_PAIRS.get(f)
        if pair and (f, t["value"] if win else next((a for a in pair if a != t["value"]), "")) in hurt: continue
        seen.add(f)
        ev = f"{t['subs_per_1k']} subscribers per 1,000 views against {t['typical_per_1k']} typical, {t['n']} Shorts over {t['days']} UK days"
        if f == "sub_push":
            if (t["value"] == "spoken") == win:
                out.append(f"Subscribe line: the spoken reason wins for subscribers ({ev}): end every Short with one short, concrete "
                           "reason tied to its series or category and how often it comes, never a bare plea.")
            else:
                out.append(f"Subscribe line: a Short with no spoken line wins for subscribers ({ev}): leave the subscribe line out.")
        elif f == "ending":
            out.append(f"Ending for subscribers: {'lean towards' if win else 'use less'} {t['value']} ({ev}).")
        else:
            out.append(f"Subscribe chip: the {t['value']} ending {'wins' if win else 'loses'} for subscribers ({ev}).")
    return out


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
