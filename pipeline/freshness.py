"""Late content needs a reason to go out (Charlie, 24 October: two Shorts written on 20 and 21 October went public on the
24th, after a re-queue, with nothing checking their story was still alive).

A time-sensitive Short (kind news, breaking, follow-up, remake, or a watchlist Short) is late when it would go public on a
day after its "created" day (the day it was written for, UK). Late, it goes out only when all of these hold:
- it is under 3 days late (2 for breaking): news that old is history, whatever the signals;
- its words are still true: no "today", "tonight", "yesterday", "tomorrow", "right now", "N days to go" (and no "this
  week" once the week has changed);
- the late Shorts so far have not done clearly worse than the rest (drivers.csv "Posted late": a "cut back" or "stop"
  verdict ends late uploads altogether, so the rule itself follows the data);
- and the data says its story is still alive: it is in today's Google Trends, Wikipedia top pages or YouTube charts
  (trends/latest.json), or its Wikipedia article was read at least 1.5 times its usual yesterday (the median of the 14
  days before, and at least 1,000 reads), or 10 or more news articles named it in the last 24 hours (Google News).
Otherwise it is expired: kept in boards/expired with its reason, never uploaded. Evergreen kinds (evergreen, true story,
top list, fiction, the reserve) and private or dry runs never expire.

Every decision on late content goes in analytics/late_uploads.csv (what, how late, posted or expired, the evidence), and
a late Short that goes out carries "late" in its status file, so analytics compares late Shorts with the rest.
"""
import csv, datetime as dt, json, pathlib, re, statistics, urllib.parse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
LOG = ROOT / "analytics" / "late_uploads.csv"
TIMELY = {"news", "breaking", "follow-up", "remake", "watchlist"}
EXPIRE_DAYS, DEFAULT_EXPIRE = {"breaking": 2}, 3
SURGE, MIN_READS, MIN_NEWS = 1.5, 1000, 10
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
FIELDS = ["decided_at", "id", "what", "kind", "days_late", "decision", "evidence", "where"]
NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
DAY_WORDS = re.compile(r"\b(today|tonight|yesterday|tomorrow|this (morning|afternoon|evening)|right now|just now|hours? ago|"
                       rf"last night|{NUM} days? (to go|away|left)|in {NUM} days?)\b", re.I)
WEEK_WORDS = re.compile(r"\b(this week|this weekend|next week|last week)\b", re.I)


def kind_of(b):
    return "watchlist" if b.get("watch") else str(b.get("kind") or "news")


def words_wrong(b, made, day):
    """Why the board's words are no longer true on `day`, or None."""
    m = b.get("meta") or {}
    text = " ".join([str(m.get("title", "")), str(m.get("summary", ""))] + [str(bt.get("say", "")) for bt in b.get("beats") or []])
    hit = DAY_WORDS.search(text)
    if hit and day > made: return f'its words say "{hit.group(0)}", written for {made:%A %d %B}'
    hit = WEEK_WORDS.search(text)
    if hit and day.isocalendar()[:2] != made.isocalendar()[:2]: return f'its words say "{hit.group(0)}" and the week has changed'
    return None


def subject_of(b):
    """(Wikipedia article or None, search phrase): the article a source links to, else the board's first tag (the writer
    puts the story's own name first), else the title's first words."""
    m = b.get("meta") or {}
    wiki = None
    for s in m.get("sources") or []:
        url = s[1] if isinstance(s, (list, tuple)) and len(s) > 1 else str(s)
        hit = re.search(r"en\.(?:m\.)?wikipedia\.org/wiki/([^#?\s]+)", str(url))
        if hit: wiki = urllib.parse.unquote(hit.group(1)).replace("_", " "); break
    tags = [str(t).strip() for t in m.get("tags") or [] if str(t).strip()]
    title = " ".join(re.sub(r"[^\w' ]+", " ", str(m.get("title", ""))).split()[:6])
    return wiki, (tags[0] if tags else title)


def in_trends(phrase):
    """Today's Google Trends, Wikipedia top pages or YouTube charts name the phrase (whole words)."""
    low = (phrase or "").lower().strip()
    if len(low) < 4: return False
    try: t = json.loads((ROOT / "trends" / "latest.json").read_text())
    except Exception: return False
    blob = json.dumps([t.get("google_trends"), t.get("wikipedia_top"), t.get("youtube_charts")], ensure_ascii=False).lower()
    return any(re.search(rf"\b{re.escape(x)}\b", blob) for x in {low, low.replace(" ", "_")})


def wiki_article(phrase, get):
    try:
        r = get("https://en.wikipedia.org/w/api.php", params={"action": "opensearch", "search": phrase, "limit": 1, "namespace": 0,
                                                             "format": "json"}, headers=UA, timeout=15)
        hits = r.json()[1] if r.ok else []
        return hits[0] if hits else None
    except Exception: return None


def wiki_alive(article, get, today=None):
    """(alive, evidence): yesterday's reads at least SURGE times the usual (median of the 14 days before) and MIN_READS."""
    end = (today or dt.date.today()) - dt.timedelta(days=1); start = end - dt.timedelta(days=14)
    u = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
         f"{urllib.parse.quote(article.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")      # as watch.py, which runs daily
    try:
        r = get(u, headers=UA, timeout=20)
        reads = [int(x.get("views", 0)) for x in r.json().get("items", [])] if r.ok else []
    except Exception: reads = []
    if len(reads) < 8: return False, f"Wikipedia \"{article}\": no reading history"
    usual, last = statistics.median(reads[:-1]), reads[-1]
    ok = last >= MIN_READS and last >= SURGE * max(1, usual)
    return ok, f"Wikipedia \"{article}\" read {last:,} times yesterday, {last / max(1, usual):.1f}x its usual {usual:,.0f}"


def news_alive(phrase, get):
    try:
        r = get("https://news.google.com/rss/search", params={"q": f"{phrase} when:1d", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
                headers=UA, timeout=20)
        n = len(re.findall(r"<item>", r.text)) if r.ok else 0
    except Exception: n = 0
    return n >= MIN_NEWS, f"{n} news articles on \"{phrase}\" in 24 hours"


def late_verdict():
    """The data's verdict on late Shorts so far (drivers.csv, feature "late", value "late"), or ''."""
    try:
        for r in csv.DictReader((ROOT / "analytics" / "drivers.csv").open()):
            if r.get("feature") == "late" and r.get("value") == "late":
                return r.get("verdict", ""), f"lift {r.get('lift')} over {r.get('n')} late Shorts"
    except Exception: pass
    return "", ""


def check(b, at=None, get=None, where="render", record=True):
    """None when the board may go out as it is (on time, evergreen); else {"alive", "evidence", "days_late"}: alive True
    means late but justified, False means expired. `at`: when it would go public (default now). Logged unless record is
    False (the render plan job cannot commit: record.py logs its decisions from the status files instead)."""
    at = (at or dt.datetime.now(dt.timezone.utc)).astimezone(UK)
    kind = kind_of(b)
    if kind not in TIMELY or b.get("reserve") or b.get("mode") in ("dry", "private"): return None
    try: made = dt.date.fromisoformat(str(b.get("created"))[:10])
    except ValueError: return None
    day = at.date(); late = (day - made).days
    if late < 1: return None
    limit = EXPIRE_DAYS.get(kind, DEFAULT_EXPIRE)
    verdict, vwhy = late_verdict()
    if late >= limit:
        out = {"alive": False, "evidence": f"{late} days late: {kind} Shorts expire after {limit - 1}"}
    elif wrong := words_wrong(b, made, day):
        out = {"alive": False, "evidence": wrong}
    elif verdict in ("cut back", "stop"):
        out = {"alive": False, "evidence": f"late Shorts do worse ({verdict}: {vwhy}), so none go out late"}
    else:
        if get is None:
            import requests
            get = requests.get
        wiki, phrase = subject_of(b)
        alive, ev = False, []
        if in_trends(phrase) or (wiki and in_trends(wiki)):
            alive = True; ev.append(f"\"{wiki or phrase}\" is in today's trends")
        if not alive:
            art = wiki or wiki_article(phrase, get)
            if art:
                alive, e = wiki_alive(art, get, day); ev.append(e)
        if not alive:
            alive, e = news_alive(phrase, get); ev.append(e)
        out = {"alive": alive, "evidence": "; ".join(ev) or "no signal"}
    out["days_late"] = late
    if record: log(b, out, where)
    return out


def safe_check(b, at=None, get=None, where="render", record=True):
    """check() that never stops a run: should it fail, a late time-sensitive board expires (strict), anything else goes on."""
    try: return check(b, at, get, where, record)
    except Exception as e:
        try:
            late = ((at or dt.datetime.now(dt.timezone.utc)).astimezone(UK).date() - dt.date.fromisoformat(str(b.get("created"))[:10])).days
        except Exception: return None
        if kind_of(b) not in TIMELY or b.get("reserve") or late < 1: return None
        out = {"alive": False, "evidence": f"the freshness check failed ({type(e).__name__}), so a late Short does not go out", "days_late": late}
        if record:
            try: log(b, out, where)
            except Exception: pass
        return out


def log(b, out, where):
    """A board's decision (see log_row)."""
    log_row(b.get("id", ""), (b.get("meta") or {}).get("title", ""), kind_of(b), out.get("days_late", ""),
            "posted late" if out["alive"] else "expired", out["evidence"], where)


def log_row(sid, what, kind, days_late, decision, evidence, where):
    """One line in analytics/late_uploads.csv per decision ("posted late" or "expired"); the same decision on the same
    item in the same place on the same day is kept once (the render runs several times a day)."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    if LOG.exists():
        try: rows = list(csv.DictReader(LOG.open()))
        except Exception: rows = []
    if any(r.get("id") == sid and r.get("decision") == decision and str(r.get("decided_at", ""))[:10] == f"{now:%Y-%m-%d}"
           and r.get("where") == where for r in rows[-300:]):
        return False
    new = not LOG.exists() or not LOG.stat().st_size
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new: w.writeheader()
        w.writerow({"decided_at": now.isoformat(timespec="minutes"), "id": sid, "what": str(what or "")[:90], "kind": kind,
                    "days_late": days_late, "decision": decision, "evidence": str(evidence)[:240], "where": where})
    return True
