"""Topic heat (Charlie, 27 October: "all of the analysis that is being done on github also needs to consider that content may
be performing well because its trending, so any bad performance may not be because of changes made").

Goal: the Partner Programme. A verdict that credits a hook, a look or a change with views a hot topic brought (or blames
one for a cold topic's) sends the recipe the wrong way; this keeps the learning honest so the views it chases are real.

Every Short gets a heat score: how hot its subject was in the world on the UK day it went out, from two free sources.
- The trends archive (trends/<day>.json, trends.py, three times a day): the subject named, whole words, on the posted day
  or the day before, in Google Trends (any country, with its news headlines; 0.7), Wikipedia's most read pages (0.5), the
  YouTube charts (0.5) or the UK news (0.3), each source counted once.
- Wikipedia's reads of the subject's article (the board's Wikipedia source, else the article its first tag finds): the
  day's or the day before's reads, sqrt(reads) / 100 up to 1.5 (10,000 reads a day: 1.0), plus a surge part when that is
  over 1.5 times the median of the 14 days before (0.4 for each doubling, up to 0.8).
Bands: hot 1.6 or more, warm 0.6 or more, else cold; "" when unknown.

How the analysis uses it: heat only ever withholds a verdict, never makes one. effect() measures how much heat moves a
number between Shorts of the same channel and UK day (the same comparison rel makes, so day luck and the archive's
coverage cancel out); when that is clear, drivers.py, changes.py, trend.py and alerts.py ask whether their verdict still
stands with every Short's number moved to an equally hot topic. One that does not is held back as not proven, with the
reason. The choices that pick the topic (source, kind, category, watch, viral, heat_band itself) keep their verdict: a
source that finds hotter topics has earned it.

Cache: analytics/heat.csv, one row a Short; a row is final 2 days after its posted day (the reads have settled) and is
measured again until then, at most MAX_NEW Shorts and MAX_SECONDS a run. "covered" says the archive had the day."""
import csv, datetime as dt, json, math, pathlib, re, statistics, time, unicodedata, urllib.parse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
CACHE = ROOT / "analytics" / "heat.csv"
ARCH = ROOT / "trends"
FIELDS = ["key", "posted_day", "subject", "heat", "arch", "wiki", "covered", "why", "measured_at"]
BANDS = ((1.6, "hot"), (0.6, "warm"))
MAX_NEW, MAX_SECONDS, MIN_N, Z = 120, 90, 30, 1.645
FINAL_DAYS = 2
POINTS = {"google_trends": 0.7, "wikipedia_top": 0.5, "youtube_charts": 0.5, "google_news_uk": 0.3}
NAMES = {"google_trends": "Google Trends", "wikipedia_top": "Wikipedia top pages", "youtube_charts": "YouTube charts",
         "google_news_uk": "UK news"}
ARCH_CAP, READS_CAP, SURGE_CAP, SURGE_AT = 2.0, 1.5, 0.8, 1.5
# words too broad to say a subject is trending (a category or a format, never a story)
GENERIC = {"music", "film", "films", "movie", "movies", "tv", "television", "gaming", "games", "game", "sport", "sports",
           "football", "tech", "technology", "science", "history", "news", "space", "animals", "animal", "food", "celebrity",
           "entertainment", "quickplay", "quickplay daily", "video", "videos", "song", "songs", "album", "world", "today",
           "facts", "fact", "the", "this", "that", "with", "from", "what", "when", "how", "why", "who", "live", "best", "new"}
SKIP_KEYS = {"url", "link", "image", "thumbnail", "id", "video_id", "channel_id", "traffic", "views", "views_per_hour"}


def band(h):
    if h in (None, ""): return ""
    h = float(h)
    return next((name for cut, name in BANDS if h >= cut), "cold")


def norm(s):
    """Lowercase, straight apostrophes, no accents, underscores as spaces: the archive and the subject compared alike."""
    s = unicodedata.normalize("NFKD", str(s or "").replace("’", "'").replace("‘", "'").replace("_", " "))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def value(r):
    """A row's heat as a float, or None."""
    try:
        v = r.get("heat")
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError): return None


def _strings(x, out):
    if isinstance(x, str):
        if not x.startswith("http"): out.append(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            if str(k).lower() not in SKIP_KEYS: _strings(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x: _strings(v, out)
    return out


_ARCH = {}


def archive(day, arch_dir=ARCH):
    """{source: one normalised text of everything it named that day} from trends/<day>.json, or None without the file."""
    key = (str(arch_dir), str(day))
    if key not in _ARCH:
        try: t = json.loads((pathlib.Path(arch_dir) / f"{day}.json").read_text(encoding="utf-8"))
        except Exception: t = None
        _ARCH[key] = None if not isinstance(t, dict) else {s: "\n".join(norm(x) for x in _strings(t.get(s), [])) for s in POINTS}
    return _ARCH[key]


def terms(wiki, phrase):
    """The names to look for: the phrase and the article (its bracketed note dropped), 4 letters or more, not a category."""
    out = []
    for x in str(phrase or "").split("|") + [re.sub(r"\s*\([^)]*\)", "", wiki or "")]:
        t = re.sub(r"^(the|a|an) ", "", " ".join(norm(x).split()).strip(" '\""))
        if len(t) >= 4 and t not in GENERIC and t not in out: out.append(t)
    return out


def arch_part(names, day, arch_dir=ARCH):
    """(points, sources named, covered): the archive's part for the posted day and the day before."""
    d = dt.date.fromisoformat(str(day))
    days = [archive(x.isoformat(), arch_dir) for x in (d, d - dt.timedelta(days=1))]
    have = [a for a in days if a]
    pats = [re.compile(rf"(?<![\w']){re.escape(t)}(?![\w])") for t in names]
    hit = [s for s in POINTS if any(p.search(a.get(s, "")) for a in have for p in pats)]
    return min(ARCH_CAP, sum(POINTS[s] for s in hit)), hit, bool(have)


def reads(article, day, get, today=None):
    """{YYYY-MM-DD: reads} of an English Wikipedia article from 16 days before `day` to `day` (to yesterday at most)."""
    d = dt.date.fromisoformat(str(day))
    end = min(d, (today or dt.datetime.now(dt.timezone.utc).date()) - dt.timedelta(days=1))
    start = d - dt.timedelta(days=16)
    if end < start: return {}
    u = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
         f"{urllib.parse.quote(article.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
    try:
        from freshness import UA
        r = get(u, headers=UA, timeout=20)
        items = r.json().get("items", []) if r.ok else []
    except Exception: items = []
    out = {}
    for it in items:
        ts = str(it.get("timestamp", ""))
        if len(ts) >= 8: out[f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"] = int(it.get("views", 0) or 0)
    return out


def wiki_part(daily, day):
    """(points, note) from an article's reads: the level (the day's or the day before's) and its surge over the usual."""
    d = dt.date.fromisoformat(str(day))
    near = [daily[x] for x in ((d.isoformat()), (d - dt.timedelta(days=1)).isoformat()) if x in daily]
    if not near: return 0.0, ""
    level = max(near)
    before = [daily[(d - dt.timedelta(days=k)).isoformat()] for k in range(2, 16) if (d - dt.timedelta(days=k)).isoformat() in daily]
    pts = min(READS_CAP, math.sqrt(level) / 100)
    note = f"{level:,} reads"
    if len(before) >= 5:
        usual = max(1.0, statistics.median(before))
        if level > SURGE_AT * usual:
            pts += min(SURGE_CAP, 0.4 * math.log2(level / usual))
        note += f", {level / usual:.1f}x its usual {usual:,.0f}"
    return pts, note


def score(wiki, phrase, day, get=None, arch_dir=ARCH, today=None):
    """(heat, arch points, wiki points, covered, why, subject) for a subject posted on UK `day`. `get` (requests.get or a
    stub) reads Wikipedia; None scores the archive alone."""
    article = wiki
    if not article and get is not None and phrase:
        try:
            from freshness import wiki_article
            article = wiki_article(phrase, get)
        except Exception: article = None
    a, hit, covered = arch_part(terms(article, phrase), day, arch_dir)
    w, note = (0.0, "")
    if article and get is not None: w, note = wiki_part(reads(article, day, get, today), day)
    why = "; ".join(x for x in ((", ".join(NAMES[s] for s in hit)), (f'Wikipedia "{article}" {note}' if note else "")) if x)
    return round(a + w, 2), round(a, 2), round(w, 2), covered, why, article or phrase or ""


# ---------------- the cache and the rows ----------------
def load(path=None):
    try:
        with open(path or CACHE, newline="", encoding="utf-8") as fh: return {r["key"]: r for r in csv.DictReader(fh) if r.get("key")}
    except Exception: return {}


def save(cache, path=None):
    p = pathlib.Path(path or CACHE); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore", restval="")
        w.writeheader(); w.writerows(sorted(cache.values(), key=lambda r: (r.get("posted_day", ""), r["key"])))


def uk_day(r):
    try: return dt.datetime.fromisoformat(str(r["posted"])).astimezone(UK).date().isoformat()
    except (KeyError, ValueError, TypeError): return str(r.get("posted_day") or "")


def key_of(r): return str(r.get("short") or r.get("youtube_url") or "")


def names_in(title):
    """The names a title carries without a board: runs of two or more capitalised words ("Peyton Manning"), "|" between."""
    runs, cur = [], []
    for w in re.sub(r"[^\w'’ ]+", " | ", str(title or "")).split():
        if w != "|" and w[:1].isupper(): cur.append(w); continue
        if len(cur) >= 2: runs.append(" ".join(cur))
        cur = []
    if len(cur) >= 2: runs.append(" ".join(cur))
    return "|".join(runs)


def phrase_of(r):
    """The subject to look for: the board's (analytics sets _phrase from freshness.subject_of), else the title's names."""
    return r.get("_phrase") or names_in(r.get("title"))


def final(c, now):
    try: return dt.date.fromisoformat(c.get("measured_at", "")[:10]) >= dt.date.fromisoformat(c["posted_day"]) + dt.timedelta(days=FINAL_DAYS)
    except Exception: return False


def attach(rows, fetch=True, get=None, now=None, path=None, arch_dir=ARCH):
    """Set heat, heat_band and heat_covered on every row (shorts.csv rows; "" when unknown), measuring the Shorts with no
    final cache row (newest first, within MAX_NEW and MAX_SECONDS) when `fetch`. Returns how many were measured."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cache = load(path)
    if fetch and get is None:
        import requests
        get = requests.get
    todo = []
    for r in rows:
        k, day = key_of(r), uk_day(r)
        c = cache.get(k)
        if k and day and fetch and not (c and c.get("posted_day") == day and final(c, now)):
            todo.append(r)
    todo.sort(key=lambda r: (key_of(r) not in cache, str(r.get("posted") or "")), reverse=True)   # unmeasured first, newest first
    t0, done = time.monotonic(), 0
    for r in todo:
        if done >= MAX_NEW or time.monotonic() - t0 > MAX_SECONDS: break
        day = uk_day(r)
        h, a, w, cov, why, subj = score(r.get("_wiki"), phrase_of(r), day, get, arch_dir, now.date())
        cache[key_of(r)] = {"key": key_of(r), "posted_day": day, "subject": subj, "heat": h, "arch": a, "wiki": w,
                            "covered": "yes" if cov else "no", "why": why, "measured_at": now.date().isoformat()}
        done += 1
    for r in rows:
        c = cache.get(key_of(r))
        ok = c and c.get("posted_day") == uk_day(r) and c.get("heat") not in (None, "")
        r["heat"] = round(float(c["heat"]), 2) if ok else ""
        r["heat_band"] = band(r["heat"])
        r["heat_covered"] = c.get("covered", "") if ok else ""
    if done: save(cache, path)
    return done


# ---------------- what heat does to a number ----------------
def group_of(r): return (r.get("channel") or "main", uk_day(r))


def _groups(rows, value_fn):
    g = {}
    for r in rows:
        h = value(r)
        if h is None: continue
        try: y = value_fn(r)
        except Exception: y = None
        if y is None: continue
        g.setdefault(group_of(r), []).append((h, float(y)))
    return {k: v for k, v in g.items() if len(v) >= 2}


def effect(rows, value_fn, min_n=MIN_N):
    """How much one point of heat moves value_fn(row) (a log number, say) between Shorts of the same channel and UK day:
    {"b", "se", "n", "groups", "clear"} (clear: |b| at least Z standard errors), or None under min_n Shorts, 5 degrees of
    freedom or no spread of heat."""
    g = _groups(rows, value_fn)
    xs, ys = [], []
    for v in g.values():
        mh, my = statistics.mean(h for h, _ in v), statistics.mean(y for _, y in v)
        for h, y in v: xs.append(h - mh); ys.append(y - my)
    n, dof = len(xs), len(xs) - len(g) - 1
    sxx = sum(x * x for x in xs)
    if n < min_n or dof < 5 or sxx < 1e-9: return None
    b = sum(x * y for x, y in zip(xs, ys)) / sxx
    s2 = sum((y - b * x) ** 2 for x, y in zip(xs, ys)) / dof
    se = math.sqrt(s2 / sxx)
    return {"b": b, "se": se, "n": n, "groups": len(g), "clear": abs(b) >= Z * se}


def centred(rows):
    """{id(row): its heat less the mean heat of its channel's other measured Shorts that UK day} (0 when unknown or alone)."""
    g = {}
    for r in rows:
        if value(r) is not None: g.setdefault(group_of(r), []).append(value(r))
    out = {}
    for r in rows:
        v, grp = value(r), g.get(group_of(r), [])
        out[id(r)] = 0.0 if v is None or len(grp) < 2 else v - statistics.mean(grp)
    return out


def shift(rows_a, rows_b):
    """Mean heat of rows_b less rows_a, on the Shorts whose day the archive covered (3 or more each), else None."""
    a = [value(r) for r in rows_a if value(r) is not None and r.get("heat_covered") == "yes"]
    b = [value(r) for r in rows_b if value(r) is not None and r.get("heat_covered") == "yes"]
    return None if len(a) < 3 or len(b) < 3 else statistics.mean(b) - statistics.mean(a)


def note(eff, what="views"):
    """One line on the measured effect, for the insights and the issues."""
    if not eff: return ""
    return (f"each point of topic heat came with {100 * (math.exp(eff['b']) - 1):+.0f}% {what} against the same day's other "
            f"Shorts ({eff['n']} Shorts, {'clear' if eff['clear'] else 'not clear'})")
