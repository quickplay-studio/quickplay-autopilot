"""The sameness guard (Charlie, 28 October 2026; goal: the Partner Programme).

YouTube's inauthentic-content policy (July 2025, clarified July 2026) refuses monetisation to a channel whose videos "feel
interchangeable" or look template-made. The learning loop converges on one winning recipe and then repeats it, which is how a
channel ends up there, so this module measures how alike the channel's Shorts are and the writer (writer.py) acts on it.

Per pair of boards of one channel, a 0 to 1 similarity from five parts, weighted (config "sameness": "weights"):
- narration: word 3-gram shingles (Jaccard) on the words as said, the content words (names, numbers, nouns: the same story told
  in other words still scores) and the skeleton (names and numbers replaced by tokens, so one script pattern told about two
  subjects still scores), 30%, 50% and 20%;
- title: the title with its series prefix, emoji, names and numbers replaced by tokens (NAME, NUM), compared as word and
  word-pair sets: "NAME: the detail you missed" against the same pattern scores 1;
- opening: the first beat's skeleton, the hook type and the first frame;
- look: the look and voice choices that two boards share (known only once a Short is rendered: the status file holds them);
- structure: the same format, the same named series.
A part nothing is known about is left out and the weights of the others are scaled up, so a board that has no look yet (the
writer checks a draft) is compared on the other four.
Per board: the highest similarity to any Short of the same channel in the last window_days days and which Short it was (check).
Per channel and UK day: the mean pairwise similarity over the window ending that day (the channel score) and the share of the
window taken by the commonest recipe (format + hook type + look + series), analytics/sameness.csv and analytics/sameness.md.
Standard library only (the write workflow installs no numpy).
  python pipeline/sameness.py             writes analytics/sameness.csv and .md
  python pipeline/sameness.py --calibrate prints the distributions the thresholds in config.json come from
"""
import collections, csv, datetime as dt, json, pathlib, re, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "analytics"
FOLDERS = ("done", "ready", "queue")         # a board that is, or is about to be, a published Short (no failed, rejected or expired)
DEFAULTS = {"on": True, "window_days": 14, "max_pair": 0.30, "recipe_share_max": 0.35, "alert": 0.20, "alert_days": 2,
            "max_boards": 300, "weights": {"narration": 0.4, "title": 0.25, "opening": 0.2, "look": 0.05, "structure": 0.1}}
LOOK_DIMS = ("captions", "voice", "energy", "grade", "opening", "style", "closing")
# words that start a title or a line without being a name
FUNC = {"the", "a", "an", "how", "why", "what", "who", "when", "where", "which", "this", "that", "these", "those", "every",
        "all", "inside", "behind", "top", "you", "your", "meet", "big", "new", "it", "its", "in", "on", "at", "for", "from",
        "with", "and", "but", "or", "no", "not", "is", "are", "was", "were", "do", "does", "did", "one", "two", "three", "if",
        "we", "our", "they", "their", "he", "she", "his", "her", "i", "my", "so", "now", "just", "here", "there", "yes"}


# words that carry no subject (the content-word part of the narration similarity keeps names, numbers and nouns)
STOP = FUNC | {"has", "have", "had", "been", "will", "would", "can", "could", "than", "then", "into", "out", "over", "about", "after",
               "before", "more", "most", "some", "also", "only", "even", "very", "much", "many", "other", "own", "same", "such",
               "like", "what's", "that's", "it's", "who's", "him", "them", "up", "off", "get", "got", "make", "made", "one's",
               "being", "because", "while", "which", "through", "still", "never", "ever", "every", "each", "back", "first", "last"}


def conf(cfg=None):
    """config.json "sameness" over the defaults (weights merged)."""
    if cfg is None:
        try: cfg = json.loads((ROOT / "config.json").read_text())
        except Exception: cfg = {}
    c = {**DEFAULTS, **((cfg or {}).get("sameness") or {})}
    c["weights"] = {**DEFAULTS["weights"], **(((cfg or {}).get("sameness") or {}).get("weights") or {})}
    return c


def on(cfg=None):
    return bool(conf(cfg).get("on"))


# ---------------- text to features ----------------
def norm(t):
    return str(t or "").replace("’", "'").replace("‘", "'")


def words(text):
    return re.findall(r"[a-z0-9']+", norm(text).lower())


def mask_tokens(text):
    """The text as a token list with every name replaced by NAME and every number by NUM (a run of either is one token); other
    words lower case; sentence ends as "."; a colon kept (a title's shape)."""
    toks = re.findall(r"[^\W_]+(?:'[^\W_]+)?|[:;.!?|]", norm(text))
    out, start = [], True
    for i, t in enumerate(toks):
        if t in ":;.!?|":
            out.append(":" if t == ":" else "."); start = t in ".!?|"; continue
        low = t.lower()
        if any(c.isdigit() for c in t): m = "NUM"
        elif t[:1].isupper() and low not in FUNC and (not start or (i + 1 < len(toks) and toks[i + 1][:1].isupper())): m = "NAME"
        else: m = low
        if not (m in ("NAME", "NUM") and out and out[-1] == m): out.append(m)
        start = False
    return out


def shingles(toks, n=3):
    return set(zip(*[toks[i:] for i in range(n)])) if len(toks) >= n else set()


def pattern_set(toks):
    """Words (not the tokens) and word pairs of a masked token list: what a shared phrasing looks like as a set."""
    return {t for t in toks if t not in ("NAME", "NUM", ".", ":")} | set(zip(toks, toks[1:]))


def strip_title(title):
    """A title without its series prefix ("Film Facts #3: ...") and emoji."""
    t = re.sub(r"^[^:]{2,40}\s#\d+:\s*", "", norm(title).strip())
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s:'\-|]", " ", t)).strip()


def cosine(a, b):
    """Cosine of two sets read as 0/1 vectors: shared / sqrt(size a * size b)."""
    if not a or not b: return 0.0
    i = len(a & b)
    return i / (len(a) * len(b)) ** 0.5 if i else 0.0


def jaccard(a, b):
    if not a or not b: return 0.0
    i = len(a & b)
    return i / (len(a) + len(b) - i) if i else 0.0


# ---------------- a board as a profile ----------------
def _hook_type(hook):
    try:
        import drivers
        return drivers.hook_type(hook)
    except Exception:
        return ""


def series_of(b):
    s = b.get("series_name") or str(b.get("channel_series") or "") or str(b.get("franchise") or "")
    return re.sub(r"\s*#\d+\s*$", "", str(s)).strip()


def look_of(b, root=None):
    """The board's look (a dict of choices), else the one in its status file (status/<id>.json), else None."""
    lk = b.get("look")
    if not isinstance(lk, dict):
        try:
            st = json.loads(((root or ROOT) / "status" / f"{b.get('id')}.json").read_text())
            lk = st.get("look") if isinstance(st, dict) else None
        except Exception: lk = None
    return {k: str(v) for k, v in lk.items() if k in LOOK_DIMS and v} if isinstance(lk, dict) else None


def profile(b, look=None):
    """The features of one board that the similarity compares. `look`: its look choices when they are known."""
    beats = b.get("beats") or []
    say = [str((x or {}).get("say") or "") for x in beats if isinstance(x, dict)]
    toks = mask_tokens(" ".join(say))
    first = say[0] if say else ""
    t = b.get("test") if isinstance(b.get("test"), dict) else {}
    title = str((b.get("meta") or {}).get("title") or "")
    mt = mask_tokens(strip_title(title))
    ws = words(" ".join(say))
    return {"id": str(b.get("id") or ""), "channel": b.get("channel") or "main", "day": str(b.get("created") or ""),
            "mode": b.get("mode") or "", "title": title,
            "raw": shingles(ws), "skel": shingles(toks), "content": {w for w in ws if w not in STOP and len(w) > 2}, "title_set": pattern_set(mt), "title_pat": " ".join(mt),
            "open_set": pattern_set(mask_tokens(first)), "hook": first,
            "hook_type": str(t.get("hook_type") or _hook_type(first)), "first_frame": str(t.get("first_frame") or ""),
            "format": str(b.get("format") or ""), "series": series_of(b), "look": look or None}


# ---------------- similarity ----------------
def parts(p, q):
    """{part: 0..1 or None} for two profiles."""
    out = {"narration": 0.3 * jaccard(p["raw"], q["raw"]) + 0.5 * cosine(p["content"], q["content"]) + 0.2 * jaccard(p["skel"], q["skel"]),
           "title": jaccard(p["title_set"], q["title_set"])}
    o = []        # the hook type and first frame are two-armed tests: half of all pairs agree, so they count for less than the words
    if p["hook_type"] and q["hook_type"]: o.append(1.0 if p["hook_type"] == q["hook_type"] else 0.0)
    if p["first_frame"] and q["first_frame"]: o.append(1.0 if p["first_frame"] == q["first_frame"] else 0.0)
    out["opening"] = 0.7 * jaccard(p["open_set"], q["open_set"]) + 0.3 * (sum(o) / len(o) if o else 0.0)
    a, b = p.get("look") or {}, q.get("look") or {}
    shared = [d for d in LOOK_DIMS if a.get(d) and b.get(d)]
    out["look"] = sum(1.0 for d in shared if a[d] == b[d]) / len(shared) if shared else None
    s = []
    if p["format"] and q["format"]: s.append(1.0 if p["format"] == q["format"] else 0.0)
    if p["series"] or q["series"]: s.append(1.0 if p["series"] == q["series"] else 0.0)
    out["structure"] = sum(s) / len(s) if s else None
    return out


def combine(pt, weights):
    w = {k: float(weights.get(k, 0)) for k, v in pt.items() if v is not None}
    tot = sum(w.values())
    return sum(w[k] * pt[k] for k in w) / tot if tot > 0 else 0.0


def score(p, q, weights=None):
    return combine(parts(p, q), weights or DEFAULTS["weights"])


def explain(p, q, pt, weights=None):
    """What matched, in words for the rewrite prompt and the log: the parts that carry the score, and the phrases shared."""
    w = weights or DEFAULTS["weights"]
    bits = sorted(((float(w.get(k, 0)) * v, k, v) for k, v in pt.items() if v), reverse=True)
    said = []
    for _c, k, v in bits[:3]:
        if v < 0.15: continue
        if k == "narration":
            sh = sorted(" ".join(g) for g in (p["raw"] & q["raw"]))[:3]
            said.append("narration (" + (f"shared phrases: {', '.join(repr(s) for s in sh)}" if sh else "the same sentence patterns") + ")")
        elif k == "title": said.append(f"title pattern ('{q['title_pat']}' against '{p['title_pat']}')")
        elif k == "opening": said.append(f"opening (the first line, '{q['hook']}')" + (f", both a {p['hook_type']} hook" if p["hook_type"] and p["hook_type"] == q["hook_type"] else ""))
        elif k == "look": said.append("look and voice")
        elif k == "structure": said.append("the same format" + (f" ({p['format']})" if p["format"] and p["format"] == q["format"] else "") + (f" and series ({p['series']})" if p["series"] and p["series"] == q["series"] else ""))
    return "; ".join(said) or "nothing stands out"


def check(p, others, cfg=None):
    """The highest similarity of profile p to any of `others` (the same channel's recent Shorts) and which one:
    {"max", "with", "title", "parts", "matched"}; max 0 without others. A board is not compared with itself."""
    w = conf(cfg)["weights"]
    best = {"max": 0.0, "with": "", "title": "", "parts": {}, "matched": ""}
    for q in others:
        if q["id"] and q["id"] == p["id"]: continue
        pt = parts(p, q)
        s = combine(pt, w)
        if s > best["max"]: best = {"max": s, "with": q["id"], "title": q["title"], "parts": pt, "matched": "", "_q": q}
    if best.get("_q"):
        q = best.pop("_q"); best["matched"] = explain(p, q, best["parts"], w)
    best.pop("_q", None)
    best["max"] = round(best["max"], 3)
    return best


# ---------------- recipes ----------------
def recipe_key(p, with_look=True):
    """The recipe a board follows: format + hook type + look (its caption and style choices) + series, "|" between; a part
    nothing is known about is left blank."""
    lk = p.get("look") or {}
    look = "+".join(x for x in (lk.get("style"), lk.get("captions")) if x) if with_look else ""
    return "|".join((p["format"], p["hook_type"], look, p["series"]))


def recipe_label(key):
    f = key.split("|")
    names = ("format", "hook", "look", "series")
    return ", ".join(f"{n} {v}" for n, v in zip(names, f) if v) or "no recipe fields"


def top_recipe(window):
    """(recipe key, its share of the window) for the commonest recipe; ("", 0) for an empty window."""
    if not window: return "", 0.0
    c = collections.Counter(recipe_key(p) for p in window)
    key, n = c.most_common(1)[0]
    return key, n / len(window)


def share_of(p, window):
    """The share of the window (this board included) that follows p's recipe on the fields known now (the look is not: a draft
    has none, so its look matches anything)."""
    key = recipe_key(p, with_look=False)
    n = 1 + sum(1 for q in window if q["id"] != p["id"] and recipe_key(q, with_look=False) == key)
    return n / (1 + sum(1 for q in window if q["id"] != p["id"]))


def over_recipe(window, cfg=None):
    """The recipe (key, share) that already holds recipe_share_max of the window, or None. The writer (writer.py) picks another
    format for the slot while one does."""
    key, share = top_recipe(window)
    return (key, share) if key and share >= conf(cfg)["recipe_share_max"] and len(window) >= 10 else None


# ---------------- loading ----------------
def _day(s):
    try: return dt.date.fromisoformat(str(s)[:10])
    except ValueError: return None


def load_profiles(root=None, today=None, days=None, folders=FOLDERS, with_look=True):
    """Profiles of the boards created within `days` days of `today` or later (all of them without `days`), in `folders`, a dry
    run never. {channel: [profile]}, oldest first."""
    root = pathlib.Path(root or ROOT)
    cut = (today - dt.timedelta(days=days)) if (today and days) else None
    out = {}
    for d in folders:
        for f in sorted((root / "boards" / d).glob("QD-*.json")):
            try: b = json.loads(f.read_text())
            except Exception: continue
            if not isinstance(b, dict) or not b.get("beats") or b.get("mode") == "dry" or b.get("reserve") and d == "reserve": continue
            day = _day(b.get("created"))
            if day is None or (cut and day < cut): continue
            out.setdefault(b.get("channel") or "main", []).append(profile(b, look_of(b, root) if with_look and d != "queue" else None))
    for v in out.values(): v.sort(key=lambda p: (p["day"], p["id"]))
    return out


def in_window(profiles, day, days):
    """The profiles created in the `days` days ending on `day` (a date)."""
    lo = day - dt.timedelta(days=days - 1)
    return [p for p in profiles if (d := _day(p["day"])) is not None and lo <= d <= day]


# ---------------- channel scores ----------------
def mean_pairwise(window, cfg=None):
    """Mean similarity over every pair of the window; None for fewer than 2 boards."""
    if len(window) < 2: return None
    w = conf(cfg)["weights"]
    tot = n = 0
    for i in range(len(window)):
        for j in range(i):
            tot += combine(parts(window[i], window[j]), w); n += 1
    return tot / n


def channel_rows(by_channel, today, cfg=None, back=14):
    """analytics/sameness.csv rows for the last `back` UK days ending on `today`: one a channel and day with 2 or more boards in
    the window."""
    c = conf(cfg); rows = []
    for ch, ps in sorted(by_channel.items()):
        for k in range(back):
            day = today - dt.timedelta(days=back - 1 - k)
            win = in_window(ps, day, c["window_days"])
            win = win[-int(c["max_boards"]):]
            s = mean_pairwise(win, cfg)
            if s is None: continue
            key, share = top_recipe(win)
            rows.append({"channel": ch, "day": day.isoformat(), "score": round(s, 4), "top_recipe": key, "share": round(share, 3),
                         "boards": len(win)})
    return rows


FIELDS = ["channel", "day", "score", "top_recipe", "share", "boards"]


def write_outputs(root=None, today=None, cfg=None, by_channel=None):
    """Write analytics/sameness.csv (the last 14 days recomputed, older rows kept) and analytics/sameness.md. Returns the rows."""
    root = pathlib.Path(root or ROOT); c = conf(cfg)
    today = today or dt.datetime.now(dt.timezone.utc).astimezone(__import__("zoneinfo").ZoneInfo("Europe/London")).date()
    by_channel = by_channel if by_channel is not None else load_profiles(root, today, c["window_days"] + 14)
    rows = channel_rows(by_channel, today, cfg)
    out = root / "analytics"; out.mkdir(exist_ok=True)
    keep = []
    try:
        lo = (today - dt.timedelta(days=13)).isoformat()
        keep = [r for r in csv.DictReader((out / "sameness.csv").open()) if r.get("day") and r["day"] < lo]
    except OSError: pass
    with (out / "sameness.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore"); w.writeheader(); w.writerows(keep + rows)
    (out / "sameness.md").write_text("\n".join(summary_lines(by_channel, rows, today, cfg)) + "\n")
    return rows


def pair_extremes(profiles, cfg=None, n=3, since=None):
    """The n most alike pairs among the profiles created on or after `since` (compared with all): [(score, p, q)]."""
    w = conf(cfg)["weights"]; best = []
    new = [p for p in profiles if since is None or (_day(p["day"]) and _day(p["day"]) >= since)]
    for p in new:
        for q in profiles:
            if q["id"] >= p["id"] and q in new: continue
            best.append((combine(parts(p, q), w), p, q))
    return sorted(best, key=lambda x: -x[0])[:n]


def summary_lines(by_channel, rows, today, cfg=None):
    c = conf(cfg)
    L = ["# Sameness (does the channel look interchangeable?)", "",
         f"Updated {today}. YouTube's inauthentic-content policy refuses monetisation to channels whose videos feel interchangeable or "
         f"template-made. Score: mean pairwise similarity (0 to 1) of a channel's Shorts over {c['window_days']} days "
         f"(pipeline/sameness.py: narration, title pattern, opening, look, format and series). The writer rewrites, then drops, a "
         f"draft over {c['max_pair']} against any recent Short, and picks another format when one recipe holds "
         f"{round(100 * c['recipe_share_max'])}% of the window. An issue opens when a channel's score is over {c['alert']} two days running.", ""]
    for ch in sorted(by_channel):
        mine = [r for r in rows if r["channel"] == ch]
        if not mine: L.append(f"- {ch}: too few boards to score."); continue
        last = mine[-1]
        L.append(f"- {ch}: score {last['score']} on {last['day']} over {last['boards']} boards (alert at {c['alert']}); commonest recipe "
                 f"{round(100 * float(last['share']))}% of the window: {recipe_label(last['top_recipe'])}.")
        ex = pair_extremes(by_channel[ch], cfg, 2, today - dt.timedelta(days=6)) if len(by_channel[ch]) < 400 else []
        for s, p, q in ex:
            L.append(f"  - most alike this week: {p['id']} \"{p['title'][:60]}\" and {q['id']} \"{q['title'][:60]}\" ({s:.2f})")
    return L


# ---------------- calibration ----------------
def percentile(xs, q):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * q
    lo = int(k); hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def calibrate(by_channel, cfg=None):
    """The distributions the thresholds come from, per channel: every pair of boards within the window of each other (pairs),
    each board's highest similarity to the boards before it within the window (best, what check() tests), the commonest
    recipe's share of each board's window (shares). Percentiles 50, 90, 97, 99."""
    c = conf(cfg); w = c["weights"]; out = {}
    for ch, ps in by_channel.items():
        pairs, best, shares = [], [], []
        for i, p in enumerate(ps):
            dp = _day(p["day"])
            prior = [q for q in ps[:i] if dp and _day(q["day"]) and (dp - _day(q["day"])).days <= c["window_days"]]
            sc = [combine(parts(p, q), w) for q in prior]
            pairs += sc
            if sc: best.append(max(sc))
            if len(prior) >= 10: shares.append(top_recipe(prior + [p])[1])
        q = lambda xs: {k: round(percentile(xs, v), 3) for k, v in (("p50", .5), ("p90", .9), ("p97", .97), ("p99", .99))} if xs else {}
        out[ch] = {"boards": len(ps), "pairs": len(pairs), "pair": q(pairs), "best": q(best), "shares": q(shares),
                   "best_over_pair_p97": round(sum(1 for b in best if pairs and b > percentile(pairs, .97)) / max(1, len(best)), 3)}
    return out


if __name__ == "__main__":
    today = dt.datetime.now(dt.timezone.utc).date()
    if "--calibrate" in sys.argv:
        print(json.dumps(calibrate(load_profiles(None, today, 120)), indent=1))
    else:
        rows = write_outputs(today=today)
        print(f"sameness: {len(rows)} rows; latest " + "; ".join(f"{r['channel']} {r['score']}" for r in rows[-3:]))
