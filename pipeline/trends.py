"""Daily trend shortlist for the script writer, from free sources. Writes trends/latest.json and trends/<date>.json.

Sources: Google Trends daily searches (GB, US), YouTube's most-popular charts (GB, US; all and gaming),
English Wikipedia's most-read pages yesterday, and this channel's own last-7-days performance.
Kept small on purpose: titles and numbers only, so reading it costs Claude very little.
"""
import datetime as dt, json, os, pathlib, re, sys, xml.etree.ElementTree as ET
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
SKIP = re.compile(r"\b(election|vote|minister|president|senate|war|shooting|murder|killed|police|court|trial|arrest|"
                  r"cancer|vaccine|crypto|bitcoin|stock|shares|betting|odds|casino|lottery|porn|onlyfans)\b", re.I)

def google_trends(geo):
    try:
        x = ET.fromstring(requests.get(f"https://trends.google.com/trending/rss?geo={geo}", headers=UA, timeout=30).content)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        out = []
        for it in x.iter("item"):
            title = it.findtext("title", "")
            out.append({"q": title, "traffic": it.findtext("ht:approx_traffic", "", ns),
                        "news": [n.findtext("ht:news_item_title", "", ns) for n in it.findall("ht:news_item", ns)][:2]})
        return [o for o in out if not SKIP.search(o["q"] + " " + " ".join(o["news"]))][:25]
    except Exception as e:
        return [{"error": str(e)[:200]}]

def youtube_charts(yt):
    out = {}
    now = dt.datetime.now(dt.timezone.utc)
    for region in ("GB", "US"):
        for cat in ("", "20"):
            kw = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": 25}
            if cat: kw["videoCategoryId"] = cat
            try: items = yt.videos().list(**kw).execute()["items"]
            except Exception as e: out[f"{region}{'-gaming' if cat else ''}"] = [{"error": str(e)[:200]}]; continue
            rows = []
            for v in items:
                hrs = max(1, (now - dt.datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 3600)
                views = int(v["statistics"].get("viewCount", 0))
                t = v["snippet"]["title"]
                if SKIP.search(t): continue
                rows.append({"title": t, "channel": v["snippet"]["channelTitle"], "views": views, "views_per_hour": round(views / hrs)})
            out[f"{region}{'-gaming' if cat else ''}"] = sorted(rows, key=lambda r: -r["views_per_hour"])[:15]
    return out

def wikipedia_top():
    arts, err = None, ""
    for back in (1, 2):         # yesterday's list is often not published until later in the day
        d = dt.date.today() - dt.timedelta(days=back)
        try:
            arts = requests.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{d:%Y/%m/%d}",
                                headers=UA, timeout=30).json()["items"][0]["articles"]
            break
        except Exception as e: err = str(e)[:200]
    if arts is None: return [{"error": err}]
    junk = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "File:", "Help:")
    return [{"page": a["article"].replace("_", " "), "views": a["views"]} for a in arts
            if not a["article"].startswith(junk) and not SKIP.search(a["article"].replace("_", " "))][:30]

def own_channel():
    import youtube as Y
    from googleapiclient.discovery import build
    try:
        ya = build("youtubeAnalytics", "v2", credentials=Y.creds(), cache_discovery=False)
        end = dt.date.today(); start = end - dt.timedelta(days=7)
        r = ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end), dimensions="video",
                               metrics="views,averageViewPercentage,subscribersGained", sort="-views", maxResults=25).execute()
        ids = [row[0] for row in r.get("rows", [])]
        titles = {}
        if ids:
            for v in Y.client().videos().list(part="snippet", id=",".join(ids)).execute()["items"]:
                titles[v["id"]] = v["snippet"]["title"]
        return [{"title": titles.get(row[0], row[0]), "views": row[1], "avg_viewed_pct": round(row[2]), "subs": row[3]} for row in r.get("rows", [])]
    except Exception as e:
        return [{"error": str(e)[:200]}]

def main():
    import youtube as Y
    data = {"date": str(dt.date.today()), "google_trends": {g: google_trends(g) for g in ("GB", "US")},
            "wikipedia_top": wikipedia_top()}
    if Y.available():
        data["youtube_charts"] = youtube_charts(Y.client())
        data["our_last_7_days"] = own_channel()
    d = ROOT / "trends"; d.mkdir(exist_ok=True)
    txt = json.dumps(data, indent=1, ensure_ascii=False)
    (d / "latest.json").write_text(txt); (d / f"{data['date']}.json").write_text(txt)
    print("trends written", len(txt), "bytes")
    try:
        pack = research(data)
        (d / "research.json").write_text(json.dumps(pack, indent=1, ensure_ascii=False))
        print("research pack:", len(pack["topics"]), "topics")
    except Exception as e:
        print("research pack failed:", e)

# ---------------- research pack ----------------
# Recent articles from reputable outlets (their own RSS feeds, so the links are the outlets' own pages) matched to the
# top trends, plus each trend's Wikipedia page. The writer opens these first instead of searching from scratch.
FEEDS = {
    "BBC": ["https://feeds.bbci.co.uk/news/rss.xml", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
            "https://feeds.bbci.co.uk/news/technology/rss.xml", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
            "https://feeds.bbci.co.uk/sport/rss.xml"],
    "Guardian": ["https://www.theguardian.com/uk/rss", "https://www.theguardian.com/games/rss", "https://www.theguardian.com/film/rss",
                 "https://www.theguardian.com/music/rss", "https://www.theguardian.com/uk/sport/rss",
                 "https://www.theguardian.com/uk/technology/rss", "https://www.theguardian.com/science/rss",
                 "https://www.theguardian.com/tv-and-radio/rss"],
    "The Verge": ["https://www.theverge.com/rss/index.xml"],
    "IGN": ["https://feeds.feedburner.com/ign/all"],
    "Eurogamer": ["https://www.eurogamer.net/feed"],
    "Polygon": ["https://www.polygon.com/rss/index.xml"],
    "Variety": ["https://variety.com/feed/"],
    "Billboard": ["https://www.billboard.com/feed/"],
    "ESPN": ["https://www.espn.com/espn/rss/news"],
    "Sky Sports": ["https://www.skysports.com/rss/12040"],
    "NASA": ["https://www.nasa.gov/news-release/feed/"],
}
STOP = set("the and for with from that this your you are was has have not but its into over after about what when how why "
           "who official video music audio lyric lyrics live full new feat ft vs v hd 4k episode season part".split())

def _words(t):
    return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) >= 2 and w not in STOP]

def _feed_items(url):
    try:
        x = ET.fromstring(requests.get(url, headers=UA, timeout=20).content)
    except Exception:
        return []
    out, atom = [], "{http://www.w3.org/2005/Atom}"
    for it in list(x.iter("item")) + list(x.iter(atom + "entry")):
        title = (it.findtext("title") or it.findtext(atom + "title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not link:
            le = it.find(atom + "link"); link = le.get("href", "") if le is not None else ""
        when = it.findtext("pubDate") or it.findtext(atom + "published") or it.findtext(atom + "updated") or ""
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or it.findtext(atom + "summary") or "")
        try:
            from email.utils import parsedate_to_datetime
            t = parsedate_to_datetime(when) if "," in when else dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
            if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
        except Exception:
            t = None
        if title and link.startswith("http"): out.append({"title": title, "url": link, "when": t, "text": f"{title} {desc}"})
    return out

def _wiki_url(q):
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=15,
                         params={"action": "opensearch", "search": q, "limit": 1, "namespace": 0, "format": "json"}).json()
        return r[3][0] if r and len(r) > 3 and r[3] else None
    except Exception:
        return None

def research(data):
    now = dt.datetime.now(dt.timezone.utc)
    items = []
    for outlet, urls in FEEDS.items():
        for u in urls:
            for it in _feed_items(u):
                if it["when"] and now - it["when"] > dt.timedelta(hours=72): continue
                it["outlet"] = outlet; it["words"] = set(_words(it["text"])); items.append(it)
    topics, seen = [], set()
    def add(q, signal, wiki=None):
        key = " ".join(_words(q))
        if not key or key in seen or SKIP.search(q): return
        seen.add(key)
        ws = _words(q)
        need = len(ws) if len(ws) <= 3 else -(-len(ws) * 3 // 5)
        hits = [it for it in items if sum(w in it["words"] for w in ws) >= need]
        hits.sort(key=lambda it: it["when"] or now - dt.timedelta(days=3), reverse=True)
        arts, outlets = [], set()
        for it in hits:                       # newest first, one per outlet before repeats
            if it["outlet"] in outlets or any(a["url"] == it["url"] for a in arts): continue
            outlets.add(it["outlet"]); arts.append(it)
            if len(arts) == 4: break
        urls = {a["url"] for a in arts}
        for t in topics:                      # the same story under a longer name (a trailer title, say): skip it
            if urls and urls <= {a["url"] for a in t["articles"]} and len(set(ws) & set(_words(t["topic"]))) >= 2: return
        wiki = wiki or _wiki_url(q)
        if arts or wiki:
            topics.append({"topic": q, "signal": signal, "wikipedia": wiki,
                           "articles": [{"outlet": a["outlet"], "title": a["title"][:140], "url": a["url"],
                                         "published": a["when"].isoformat(timespec="minutes") if a["when"] else ""} for a in arts]})
    for geo in ("GB", "US"):
        for t in (data.get("google_trends") or {}).get(geo, [])[:12]:
            if t.get("q"): add(t["q"], f"Google Trends {geo} {t.get('traffic', '')}".strip())
    for w in (data.get("wikipedia_top") or [])[:12]:
        if w.get("page"): add(w["page"], f"Wikipedia {w.get('views', 0):,} views", "https://en.wikipedia.org/wiki/" + w["page"].replace(" ", "_"))
    for chart, rows in (data.get("youtube_charts") or {}).items():
        for r in rows[:6]:
            if r.get("title"):
                t = re.split(r"\s[|(\[]|\s[-:]\s", r["title"])[0]
                add(t, f"YouTube {chart} {r.get('views_per_hour', 0):,}/h")
    return {"date": data.get("date"), "note": "Open these first; still check each claim on two of them (CLAUDE.md, Facts).",
            "topics": [t for t in topics if t["articles"]][:20] + [t for t in topics if not t["articles"]][:5]}

if __name__ == "__main__":
    main()
