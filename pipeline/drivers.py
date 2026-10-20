"""What drives views: every Short is compared with Shorts posted around the same time (so channel growth doesn't skew it),
then grouped by each thing we choose (category, format, hook, length, posting time, look...). Called by analytics.py.

Outcome per Short ("rel"): YouTube views 24 hours after posting divided by the median of Shorts posted within 3 days of
it (1.0 = typical). Shorts measured before hourly snapshots began use views an hour against the same peers instead.
Per group: lift = exp(shrunken mean of log rel), shrunk towards 1.0 with weight 3, so two lucky Shorts can't look
like a trend. Verdicts need 5 or more Shorts: "push" at 1.25 or more, "cut back" at 0.8 or less.
"""
import datetime as dt, math, re, statistics
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
SHRINK, MIN_N, PUSH, CUT = 3, 5, 1.25, 0.8
FEATURES = [("category", "Category"), ("format", "Format"), ("hook_type", "Hook style"), ("hook_len", "Hook length"),
            ("length", "Length"), ("slot", "Posting time (UK)"), ("weekday", "Day posted"), ("mood", "Music mood"),
            ("pictures", "Pictures"), ("title_style", "Title"), ("look_captions", "Captions"), ("look_voice", "Voice"),
            ("look_energy", "Camera energy"), ("look_grade", "Colour grade"), ("look_opening", "Opening"), ("follow_line", "Follow line"), ("ending", "Ending"), ("title_search", "Title wording"),
            ("first_frame", "First frame"), ("angles", "Angle research"), ("replies", "Comment replies"), ("kind", "Kind of Short"), ("source", "Topic source"), ("series", "Series"), ("writer", "Writer model")]
TESTED = ("ending", "title_search", "first_frame", "angles", "replies", "kind", "source", "series", "writer")     # recorded on the board by the writer (writer.py tests)
NUM = r"\b(one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|hundred|thousand|million|billion)\b"

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
    out["length"] = "" if not s else ("under 25 s" if s < 25 else "25 to 34 s" if s < 35 else "35 to 44 s" if s < 45 else "45 s or more")
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

def analyse(rows):
    """rows: shorts.csv rows with 'rel' set (or None). Returns (table rows for drivers.csv, base support measures)."""
    scored = [r for r in rows if r.get("rel") not in (None, "")]
    base = _support(scored)
    table = []
    for feat, label in FEATURES:
        groups = {}
        for r in scored:
            v = features(r).get(feat)
            if v: groups.setdefault(v, []).append(r)
        if len(groups) < 2: continue
        for v, grp in groups.items():
            logs = [math.log(max(0.05, float(r["rel"]))) for r in grp]
            n = len(logs); lift = math.exp(sum(logs) / (n + SHRINK))
            days = len({r.get("posted_day") for r in grp})        # one day's luck (or one weekday seen once) proves little
            verdict = ("too few to tell" if n < 3 else "early sign" if n < MIN_N or days < 2 else
                       "push" if lift >= PUSH else "cut back" if lift <= CUT else "about typical")
            sup = _support(grp)
            table.append({"feature": feat, "feature_label": label, "value": v, "n": n, "lift": round(lift, 2),
                          "median_rel": round(statistics.median(float(r["rel"]) for r in grp), 2), "verdict": verdict,
                          "held_3s_pct": round(sup["yt_held_3s_pct"]) if sup["yt_held_3s_pct"] is not None else "",
                          "avg_viewed_pct": round(sup["yt_avg_viewed_pct"]) if sup["yt_avg_viewed_pct"] is not None else "",
                          "subs_per_1k": round(sup["subs_per_1k"], 1) if sup["subs_per_1k"] is not None else "",
                          "shares_per_1k": round(sup["shares_per_1k"], 1) if sup["shares_per_1k"] is not None else "",
                          "why": _why(sup, base, lift >= 1) if n >= 3 and abs(math.log(lift)) >= math.log(1.1) else ""})
    table.sort(key=lambda t: (t["feature"], -t["lift"]))
    return table, base

def recipe(table, rows):
    """What the writer should lean towards, from solid results only (5 or more Shorts), as lines of text."""
    solid = [t for t in table if t["n"] >= MIN_N]
    if len([r for r in rows if r.get("rel") not in (None, "")]) < 15 or not solid:
        return ["Not enough measured Shorts yet (15 needed, each public for 24 hours): keep the variety rules and spread "
                "categories, formats and hook styles evenly so the comparison fills in fast."]
    L = []
    n_scored = len([r for r in rows if r.get("rel") not in (None, "")])
    cats = [t for t in table if t["feature"] == "category" and t["n"] >= 3]
    if cats and n_scored >= 40:
        # a daily mix in proportion to each category's lift, at least 10% for any category we have measured, and 20% kept
        # for whatever trends hardest so new categories keep getting tested
        w = {t["value"]: max(0.5, t["lift"]) for t in cats}
        tot = sum(w.values()); share = {k: max(0.1, 0.8 * x / tot) for k, x in w.items()}
        scale = 0.8 / sum(share.values()); share = {k: s * scale for k, s in share.items()}
        L.append("Category mix for the day (80% from results, 20% exploring): " +
                 ", ".join(f"{k} {round(100 * s)}%" for k, s in sorted(share.items(), key=lambda kv: -kv[1])) +
                 "; the remaining 20% on whatever trends hardest, any category.")
    elif cats:
        up = [t for t in sorted(cats, key=lambda t: -t["lift"]) if t["lift"] >= 1.1]
        down = [t for t in sorted(cats, key=lambda t: t["lift"]) if t["lift"] <= 0.9]
        if up or down:
            L.append(f"Category (early, {n_scored} Shorts measured; a full mix from 40): " +
                     "; ".join(([("lean towards " + ", ".join(f"{t['value']} ({t['lift']}x, {t['n']} Shorts)" for t in up))] if up else []) +
                               ([("ease off " + ", ".join(f"{t['value']} ({t['lift']}x, {t['n']} Shorts)" for t in down))] if down else [])) +
                     ", while still covering at least 3 categories a day.")
    for feat, label in FEATURES[1:]:
        push = [t for t in solid if t["feature"] == feat and t["verdict"] == "push"]
        cut = [t for t in solid if t["feature"] == feat and t["verdict"] == "cut back"]
        if push or cut:
            parts = []
            if push: parts.append("lean towards " + ", ".join(f"{t['value']} ({t['lift']}x, {t['n']} Shorts)" for t in push))
            if cut: parts.append("use less " + ", ".join(f"{t['value']} ({t['lift']}x, {t['n']} Shorts)" for t in cut))
            L.append(f"{label}: " + "; ".join(parts) + ".")
    return L or ["Nothing stands clearly above or below typical yet: keep the variety rules and the spread of categories."]
