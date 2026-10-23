"""What wins on Shorts for everyone else (Charlie, 23 October: competitors' top Shorts as a data source). Once a UK day,
for each category we post in (and each watchlist item), the most-viewed Shorts of the last 2 days in English from YouTube
search, with views, views an hour, length and title features. Saved to analytics/competitors.csv (60 days kept) and
summed up in analytics/competitors.md: what the winners' titles share against ours (length, numbers, questions, emoji,
how they open). The writer shows each board the week's top titles in its category as angles to beat, never to copy.

About 102 units of the YouTube allowance a search (search 100, video details 1 or 2), only when quota.allow says the day's
uploads keep their share; so about 800 units a day.

usage: python pipeline/competitors.py      (trends.yml runs it after analytics; once a UK day)
"""
import csv, datetime as dt, json, pathlib, re, statistics, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
CFG = json.loads((ROOT / "config.json").read_text())
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
OUT = ROOT / "analytics" / "competitors.csv"
MD = ROOT / "analytics" / "competitors.md"
FIELDS = ["day", "query", "category", "video", "channel", "title", "views", "hours", "views_per_hour", "seconds",
          "title_words", "has_number", "is_question", "has_emoji", "first_word"]
QUERIES = {"Gaming": "gaming facts", "Film": "movie facts", "Music": "music facts", "Sport": "football facts",
           "Tech": "tech news", "Science": "space facts", "Entertainment": "celebrity facts", "Animals": "animal facts",
           "Food": "food facts", "Cars": "car facts", "History": "history facts"}     # Shorts like ours: facts and news
ENGLISH = {"the", "a", "an", "to", "of", "in", "is", "you", "and", "this", "what", "how", "why", "when", "my", "i", "it",
           "with", "for", "on", "your", "that", "was", "are", "did", "can", "who", "most", "ever", "never", "first", "biggest"}


def english(title):
    """A title an English-speaking viewer would read: Latin script and at least two common English words (search returns
    Spanish, Hindi and Indonesian winners even when asked for English)."""
    t = str(title or "")
    if re.search(r"[^\x00-\u024F\u2000-\u2BFF\U0001F000-\U0001FAFF\s]", t): return False
    return len({w.lower() for w in re.findall(r"[A-Za-z']+", t)} & ENGLISH) >= 2
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def features(title):
    t = str(title or "")
    words = re.findall(r"[\w']+", t)
    return {"title_words": len(words), "has_number": int(bool(re.search(r"\d", t))), "is_question": int("?" in t),
            "has_emoji": int(bool(EMOJI.search(t))), "first_word": (words[0].lower() if words else "")}


def iso_seconds(d):
    m = re.fullmatch(r"P(?:\d+D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", str(d or ""))
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else ""


def search(yt, q, category):
    import quota
    if not quota.allow(102, "competitor search"): return None
    quota.spend(102, "competitor search")
    since = (NOW - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = yt.search().list(part="snippet", q=f"{q} #shorts", type="video", videoDuration="short", order="viewCount",
                         publishedAfter=since, maxResults=25, relevanceLanguage="en", regionCode="US").execute()   # US: 40% of our views
    ids = [it["id"]["videoId"] for it in r.get("items", []) if (it.get("id") or {}).get("videoId")]
    rows = []
    for v in (yt.videos().list(part="statistics,snippet,contentDetails", id=",".join(ids)).execute().get("items", []) if ids else []):
        sn, stt = v["snippet"], v.get("statistics", {})
        if not english(sn.get("title")): continue
        hrs = max(1.0, (NOW - dt.datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 3600)
        views = int(stt.get("viewCount", 0))
        rows.append({"day": str(NOW.astimezone(UK).date()), "query": q, "category": category, "video": v["id"],
                     "channel": sn.get("channelTitle", ""), "title": sn.get("title", "")[:120], "views": views,
                     "hours": round(hrs, 1), "views_per_hour": round(views / hrs), "seconds": iso_seconds(v.get("contentDetails", {}).get("duration")),
                     **features(sn.get("title"))})
    return rows


def summary(rows, ours):
    """Markdown: per category, the top titles by views an hour, and how winners' titles differ from ours."""
    L = [f"# What wins on Shorts for everyone else ({NOW.astimezone(UK):%A %d %B} UK)", "",
         "The most-viewed English Shorts of the last 2 days per category (YouTube search), against our own titles. Angles to beat, never to copy.", ""]
    def share(rs, k): return round(100 * sum(int(float(r.get(k) or 0)) for r in rs) / len(rs)) if rs else 0
    def med(rs, k):
        v = [float(r[k]) for r in rs if str(r.get(k, "")).strip() not in ("", "None")]
        return round(statistics.median(v), 1) if v else ""
    rows = [r for r in rows if str(r.get("views_per_hour", "")).strip() not in ("", "None")]
    top = sorted(rows, key=lambda r: -float(r["views_per_hour"]))[:max(10, len(rows) // 4)]
    L += ["| | Top Shorts (top quarter) | Ours (last 14 days) |", "|---|---|---|",
          f"| Title words (median) | {med(top, 'title_words')} | {med(ours, 'title_words')} |",
          f"| With a number | {share(top, 'has_number')}% | {share(ours, 'has_number')}% |",
          f"| A question | {share(top, 'is_question')}% | {share(ours, 'is_question')}% |",
          f"| With an emoji | {share(top, 'has_emoji')}% | {share(ours, 'has_emoji')}% |",
          f"| Length, seconds (median) | {med(top, 'seconds')} | {med(ours, 'seconds')} |", ""]
    for cat in sorted({r["category"] for r in rows}):
        rs = sorted((r for r in rows if r["category"] == cat), key=lambda r: -float(r["views_per_hour"]))[:5]
        L.append(f"## {cat}")
        L += [f"- {r['title']} ({int(float(r['views'])):,} views, {int(float(r['views_per_hour'])):,} an hour, {r['seconds']} s, {r['channel']})" for r in rs]
        L.append("")
    return "\n".join(L)


def ours():
    try: rows = list(csv.DictReader((ROOT / "analytics" / "shorts.csv").open()))
    except Exception: return []
    cut = str((NOW - dt.timedelta(days=14)).date())
    out = []
    for r in rows:
        if str(r.get("posted_day", "")) < cut: continue
        out.append({**features(r.get("title")), "seconds": r.get("seconds", "")})
    return out


def top_titles(category, n=4):
    """The week's best titles in a category by views an hour (for the writer's brief); [] without data."""
    try: rows = list(csv.DictReader(OUT.open()))
    except Exception: return []
    cut = str((NOW - dt.timedelta(days=7)).date())
    rs = sorted((r for r in rows if r.get("category") == category and r.get("day", "") >= cut),
                key=lambda r: -float(r.get("views_per_hour") or 0))
    seen, out = set(), []
    for r in rs:
        if r["video"] in seen: continue
        seen.add(r["video"]); out.append(f"\"{r['title']}\" ({int(float(r['views_per_hour'])):,} views an hour)")
        if len(out) == n: break
    return out


DONE_EMPTY = set()       # searches that came back with no English Shorts this run (not searched again in it)


def run(force=False):
    today = str(NOW.astimezone(UK).date())
    old = list(csv.DictReader(OUT.open())) if OUT.exists() else []
    queries = dict(QUERIES)
    try:
        for it in json.loads((ROOT / "status" / "watch.json").read_text()).get("items") or []:
            if it.get("level") != "steady": queries[f"Watch: {it['name']}"] = it["name"]
    except Exception: pass
    done = {r.get("query") for r in old if r.get("day") == today} | DONE_EMPTY
    if not force:                          # once a UK day per search; a run the allowance cut short finishes on the next
        queries = {c: q for c, q in queries.items() if q not in done}
        if not queries: print("competitors: done today already"); return []
    import youtube as Y
    yt = Y.client()
    got = []
    for cat, q in queries.items():
        try:
            rows = search(yt, q, cat.removeprefix("Watch: ") if cat.startswith("Watch: ") else cat)
        except Exception as e:
            print(f"competitors: {q}: {str(e)[:120]}"); continue
        if rows is None: print("competitors: stopped, the YouTube allowance is kept for uploads; the next run goes on"); break
        got += rows
    cut = str((NOW - dt.timedelta(days=60)).date())
    keep = [r for r in old if r.get("day", "") >= cut and not (r.get("day") == today and r.get("query") in {g["query"] for g in got})] + got
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows({k: r.get(k, "") for k in FIELDS} for r in keep)
    todays = [r for r in keep if r.get("day") == today]
    if todays: MD.write_text(summary(todays, ours()))
    print(f"competitors: {len(got)} Shorts from {len(queries)} searches")
    return got


if __name__ == "__main__":
    run(force="--force" in sys.argv)
