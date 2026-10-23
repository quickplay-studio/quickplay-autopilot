"""Daily trend shortlist for the script writer, from free sources. Writes trends/latest.json and trends/<date>.json.

Sources: Google Trends daily searches (GB, US, AU, CA, IE), YouTube's most-popular charts (GB, US: all, gaming, music,
sport, entertainment, science and tech), Google News top stories (UK: entertainment, sport, technology, science),
English Wikipedia's most-read pages, and this channel's own last 7 days. (Reddit refuses GitHub's servers, so it isn't used.)
Every source is optional: one that fails is noted and the rest still run. Kept small on purpose: titles and numbers
only, so reading it costs Claude very little. research() adds trends/research.json: reputable articles per topic.
Scheduled events too: rocket launches in the next 48 hours (Launch Library 2, no key), yesterday's football results
and the next two days' big matches (football-data.org, FOOTBALL_DATA_TOKEN), and Apple Music's most-played songs
in GB, US, ES, BR and MX with the songs new to each top 25 since the day before (Apple's free charts, no key).
"""
import datetime as dt, json, os, pathlib, re, sys, xml.etree.ElementTree as ET
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
SKIP = re.compile(r"\b(election|vote|minister|president|senate|war|shooting|murder|killed|police|court|trial|arrest|"
                  r"cancer|vaccine|crypto|bitcoin|stock|shares|betting|odds|casino|lottery|porn|onlyfans|"
                  r"movie times|showtimes|near me|login|log in|weather)\b", re.I)     # practical searches carry no story

def google_trends(geo, n=25):
    try:
        x = ET.fromstring(requests.get(f"https://trends.google.com/trending/rss?geo={geo}", headers=UA, timeout=30).content)
        ns = {"ht": "https://trends.google.com/trending/rss"}
        out = []
        for it in x.iter("item"):
            title = it.findtext("title", "")
            out.append({"q": title, "traffic": it.findtext("ht:approx_traffic", "", ns),
                        "news": [n.findtext("ht:news_item_title", "", ns) for n in it.findall("ht:news_item", ns)][:2]})
        return [o for o in out if not SKIP.search(o["q"] + " " + " ".join(o["news"]))][:n]
    except Exception as e:
        return [{"error": str(e)[:200]}]

def youtube_charts(yt):
    out = {}
    now = dt.datetime.now(dt.timezone.utc)
    cats = {"": "", "20": "-gaming", "10": "-music", "17": "-sport", "24": "-entertainment", "28": "-tech"}
    for region in ("GB", "US"):
        for cat, suffix in cats.items():
            kw = {"part": "snippet,statistics", "chart": "mostPopular", "regionCode": region, "maxResults": 25}
            if cat: kw["videoCategoryId"] = cat
            try: items = yt.videos().list(**kw).execute()["items"]
            except Exception as e: out[f"{region}{suffix}"] = [{"error": str(e)[:200]}]; continue
            rows = []
            for v in items:
                hrs = max(1, (now - dt.datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 3600)
                views = int(v["statistics"].get("viewCount", 0))
                t = v["snippet"]["title"]
                if SKIP.search(t): continue
                rows.append({"title": t, "channel": v["snippet"]["channelTitle"], "views": views, "views_per_hour": round(views / hrs)})
            out[f"{region}{suffix}"] = sorted(rows, key=lambda r: -r["views_per_hour"])[:15 if not cat else 6]
    return out

def wikipedia_top():
    arts, err = None, ""
    for back in (1, 2, 3):      # yesterday's list is often not published until later in the day
        d = dt.date.today() - dt.timedelta(days=back)
        try:
            r = requests.get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia.org/all-access/{d:%Y/%m/%d}",
                             headers=UA, timeout=30)
            arts = r.json()["items"][0]["articles"]
            break
        except Exception as e: err = f"{d}: HTTP {getattr(r, 'status_code', '?')} {getattr(r, 'text', '')[:150]} ({e})"[:300]
    if arts is None: return [{"error": err}]
    junk = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "File:", "Help:")
    return [{"page": a["article"].replace("_", " "), "views": a["views"]} for a in arts
            if not a["article"].startswith(junk) and not SKIP.search(a["article"].replace("_", " "))][:20]

def google_news():
    """Top stories in the UK edition of Google News, per section: 'headline (outlet)'."""
    out = {}
    for sec in ("ENTERTAINMENT", "SPORTS", "TECHNOLOGY", "SCIENCE"):
        try:
            x = ET.fromstring(requests.get(f"https://news.google.com/rss/headlines/section/topic/{sec}?hl=en-GB&gl=GB&ceid=GB:en",
                                           headers=UA, timeout=30).content)
            rows = []
            for it in x.iter("item"):
                t = (it.findtext("title") or "").strip()
                if t and not SKIP.search(t): rows.append(t[:140])
            out[sec.lower()] = rows[:8]
        except Exception as e:
            out[sec.lower()] = [f"error: {str(e)[:150]}"]
    return out

def reddit_popular():
    """The day's most upvoted posts across Reddit (titles only: a lead for what people are talking about, never a source)."""
    try:
        r = requests.get("https://www.reddit.com/r/popular/top.json", params={"t": "day", "limit": 50}, headers=UA, timeout=30)
        posts = r.json()["data"]["children"]
    except Exception as e:
        return [{"error": f"HTTP {getattr(locals().get('r'), 'status_code', '?')} {str(e)[:150]}"}]
    out = []
    for p in posts:
        d = p.get("data", {})
        if d.get("over_18") or SKIP.search(d.get("title", "")): continue
        out.append({"title": d.get("title", "")[:140], "sub": d.get("subreddit"), "score": d.get("score")})
    return out[:15]

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
    data = {"date": str(dt.date.today()),
            "google_trends": {**{g: google_trends(g, 20) for g in ("GB", "US")}, **{g: google_trends(g, 8) for g in ("AU", "CA", "IE")}},
            "google_news_uk": google_news(), "wikipedia_top": wikipedia_top()}
    data["launches"] = launches()
    fb = football()
    if fb: data["football"] = fb
    data["music_charts"] = music_charts()
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

# ---------------- scheduled events: launches, matches, music charts ----------------
def launches(hours=48):
    """Rocket launches in the next `hours` (Launch Library 2, free, no key): when, who, what, and an official page."""
    try:
        now = dt.datetime.now(dt.timezone.utc)
        r = requests.get("https://ll.thespacedevs.com/2.3.0/launches/upcoming/", headers=UA, timeout=30,
                         params={"limit": 8, "mode": "normal", "net__lte": (now + dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}).json()
        out = []
        for l in r.get("results") or []:
            urls = l.get("info_urls") or l.get("infoURLs") or []
            info = next((u.get("url") if isinstance(u, dict) else u for u in urls), "")
            out.append({"name": l.get("name"), "net_utc": l.get("net"), "status": (l.get("status") or {}).get("abbrev"),
                        "provider": (l.get("launch_service_provider") or {}).get("name"),
                        "mission": ((l.get("mission") or {}).get("description") or "")[:200],
                        "pad": ((l.get("pad") or {}).get("location") or {}).get("name"), "info": info})
        return out
    except Exception as e:
        return [{"error": str(e)[:120]}]

FOOTBALL = {"PL": "Premier League", "CL": "Champions League", "PD": "La Liga", "SA": "Serie A", "BL1": "Bundesliga",
            "FL1": "Ligue 1", "ELC": "Championship", "BSA": "Brasileirao"}

def football():
    """Yesterday's results and the next two days' matches in the big competitions (football-data.org)."""
    tok = os.environ.get("FOOTBALL_DATA_TOKEN", "").strip()
    if not tok: return None
    today = dt.date.today()
    try:
        r = requests.get("https://api.football-data.org/v4/matches", headers={"X-Auth-Token": tok}, timeout=30,
                         params={"dateFrom": str(today - dt.timedelta(days=1)), "dateTo": str(today + dt.timedelta(days=2)),
                                 "competitions": ",".join(FOOTBALL)}).json()
        res, fix = [], []
        for m in r.get("matches") or []:
            team = lambda t: (t or {}).get("shortName") or (t or {}).get("name") or "?"
            row = {"competition": FOOTBALL.get((m.get("competition") or {}).get("code"), (m.get("competition") or {}).get("name")),
                   "home": team(m.get("homeTeam")), "away": team(m.get("awayTeam")), "kickoff_utc": m.get("utcDate")}
            if m.get("status") == "FINISHED":
                ft = (m.get("score") or {}).get("fullTime") or {}
                row["score"] = f"{ft.get('home')}-{ft.get('away')}"; res.append(row)
            elif m.get("status") in ("SCHEDULED", "TIMED"): fix.append(row)
        return {"results": res[:20], "fixtures": fix[:20]} if (res or fix) else {"note": r.get("message", "no matches")}
    except Exception as e:
        return {"error": str(e)[:120]}

CHART_COUNTRIES = ("gb", "us", "es", "br", "mx")

def music_charts():
    """Apple Music's most-played songs per country (free charts, no key): the top 5, and songs new to the top 25 since
    the day before (trends/charts.json keeps the last day's lists)."""
    p = ROOT / "trends" / "charts.json"
    try: saved = json.loads(p.read_text())
    except Exception: saved = {}
    today = str(dt.date.today())
    if saved.get("date") != today: saved = {"date": today, "previous": saved.get("charts") or {}, "charts": {}}
    out = {}
    for cc in CHART_COUNTRIES:
        try:
            feed = requests.get(f"https://rss.marketingtools.apple.com/api/v2/{cc}/music/most-played/25/songs.json",
                                headers=UA, timeout=30).json()["feed"]["results"]
            songs = [f"{x['name']} by {x['artistName']}" for x in feed]
        except Exception as e:
            out[cc] = {"error": str(e)[:80]}; continue
        saved["charts"][cc] = songs
        before = saved["previous"].get(cc) or []
        out[cc] = {"top5": songs[:5], "new_in_top25": [x for x in songs if before and x not in before][:5]}
    try: p.write_text(json.dumps(saved, ensure_ascii=False, indent=1))
    except Exception: pass
    return out

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
    "Sky News": ["https://feeds.skynews.com/feeds/rss/home.xml", "https://feeds.skynews.com/feeds/rss/entertainment.xml",
                 "https://feeds.skynews.com/feeds/rss/technology.xml"],
    "BBC Sport": ["https://feeds.bbci.co.uk/sport/football/rss.xml"],
    "TechCrunch": ["https://techcrunch.com/feed/"],
    "Engadget": ["https://www.engadget.com/rss.xml"],
    "PC Gamer": ["https://www.pcgamer.com/rss/"],
    "GameSpot": ["https://www.gamespot.com/feeds/news/"],
    "NME": ["https://www.nme.com/feed"],
    "Rolling Stone": ["https://www.rollingstone.com/feed/"],
    "The Hollywood Reporter": ["https://www.hollywoodreporter.com/feed/"],
    "Deadline": ["https://deadline.com/feed/"],
    "Space.com": ["https://www.space.com/feeds/all"],
    "Apple Newsroom": ["https://www.apple.com/newsroom/rss-feed.rss"],          # official sources
    "PlayStation Blog": ["https://blog.playstation.com/feed/"],
    "Xbox Wire": ["https://news.xbox.com/en-us/feed/"],
}
# outlets a per-topic news search may return that count as reputable (CLAUDE.md, Facts); anything else is dropped
REPUTABLE = {"bbc.co.uk": "BBC", "bbc.com": "BBC", "theguardian.com": "Guardian", "reuters.com": "Reuters", "apnews.com": "AP",
             "theverge.com": "The Verge", "ign.com": "IGN", "eurogamer.net": "Eurogamer", "variety.com": "Variety",
             "billboard.com": "Billboard", "espn.com": "ESPN", "espn.co.uk": "ESPN", "skysports.com": "Sky Sports",
             "news.sky.com": "Sky News", "nasa.gov": "NASA", "apple.com": "Apple", "techcrunch.com": "TechCrunch",
             "engadget.com": "Engadget", "arstechnica.com": "Ars Technica", "wired.com": "Wired", "polygon.com": "Polygon",
             "pcgamer.com": "PC Gamer", "gamespot.com": "GameSpot", "nme.com": "NME", "rollingstone.com": "Rolling Stone",
             "hollywoodreporter.com": "The Hollywood Reporter", "deadline.com": "Deadline", "space.com": "Space.com",
             "independent.co.uk": "The Independent", "telegraph.co.uk": "The Telegraph", "standard.co.uk": "Evening Standard",
             "nytimes.com": "New York Times", "washingtonpost.com": "Washington Post", "cnn.com": "CNN", "nbcnews.com": "NBC News",
             "cbsnews.com": "CBS News", "abcnews.go.com": "ABC News", "usatoday.com": "USA Today", "nature.com": "Nature",
             "newscientist.com": "New Scientist", "nationalgeographic.com": "National Geographic", "premierleague.com": "Premier League",
             "uefa.com": "UEFA", "nfl.com": "NFL", "blog.playstation.com": "PlayStation Blog", "news.xbox.com": "Xbox Wire",
             "nintendo.com": "Nintendo", "rockstargames.com": "Rockstar Games", "netflix.com": "Netflix", "spacex.com": "SpaceX",
             "officialcharts.com": "Official Charts", "9to5mac.com": "9to5Mac", "macrumors.com": "MacRumors"}
STOP = set("the and for with from that this your you are was has have not but its into over after about what when how why "
           "who official video music audio lyric lyrics live full new feat ft vs v hd 4k episode season part".split())

ALIASES = [(r"\bgrand theft auto\b", "gta"), (r"\bman(?:chester)? utd\b", "manchester united"),
           (r"\bman city\b", "manchester city"), (r"\bviii\b", "8"), (r"\bvii\b", "7"), (r"\bvi\b", "6"),
           (r"\biv\b", "4"), (r"\biii\b", "3"), (r"\bii\b", "2")]

def _words(t):
    t = t.lower()
    for a, b in ALIASES: t = re.sub(a, b, t)
    return [w for w in re.findall(r"[a-z0-9]+", t) if (len(w) >= 2 or w.isdigit()) and w not in STOP]

def _news_search(q):
    """Recent articles about q from Bing News, kept only when the outlet is on the REPUTABLE list (real outlet links)."""
    import urllib.parse as up
    try:
        x = ET.fromstring(requests.get("https://www.bing.com/news/search", params={"q": q, "format": "rss", "setlang": "en-GB"},
                                       headers=UA, timeout=20).content)
    except Exception:
        return []
    out = []
    for it in x.iter("item"):
        link = it.findtext("link") or ""
        real = up.parse_qs(up.urlparse(link).query).get("url", [link])[0]
        host = up.urlparse(real).netloc.lower().removeprefix("www.")
        outlet = next((v for k, v in REPUTABLE.items() if host == k or host.endswith("." + k)), None)
        if not outlet: continue
        when = it.findtext("pubDate") or ""
        try:
            from email.utils import parsedate_to_datetime
            t = parsedate_to_datetime(when)
        except Exception:
            t = None
        title = (it.findtext("title") or "").strip()
        out.append({"title": title, "url": real, "when": t, "outlet": outlet, "words": set(_words(title))})
    return out

def requested_topics():
    """Charlie's open requests from trends/requests.md (the lines under 'Requested' headings)."""
    p = ROOT / "trends" / "requests.md"
    if not p.exists(): return []
    out, on = [], False
    for ln in p.read_text().splitlines():
        if ln.startswith("## "): on = ln.lower().startswith("## requested"); continue
        if on and ln.startswith("- "):
            t = re.sub(r"\s*\([^)]*\)", "", ln[2:]).replace('"', "").strip()
            head, _, tail = t.partition(":")
            out.append((head if len(head.split()) >= 4 or not tail else f"{head} {tail}").strip()[:80])
    return [t for t in out if t]

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
    topics, seen, searches = [], set(), [0]
    def add(q, signal, wiki=None, vetted=False):
        key = " ".join(_words(q))
        if not key or key in seen or (SKIP.search(q) and not vetted): return
        seen.add(key)
        ws = _words(q)
        longest = max(ws, key=len)
        need = 1 if len(ws) == 1 else (len(ws) - 1 if len(ws) <= 3 else -(-len(ws) * 3 // 5))
        hits = [it for it in items if sum(w in it["words"] for w in ws) >= need and longest in it["words"]]
        if len(hits) < 3 and searches[0] < 40:          # top up from a news search for this topic
            searches[0] += 1
            key2 = sorted(ws, key=len, reverse=True)[:2]      # the search already did the matching: the headline only has
            hits += [it for it in _news_search(q) if any(w in it["words"] for w in key2)]   # to name the topic's main word
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
                                         "published": a["when"].strftime("%Y-%m-%d") if a["when"] else ""} for a in arts]})
    for q in requested_topics():                  # Charlie's own requests first
        add(q, "Charlie's request", vetted=True)
    try:                                          # then the watchlist (pipeline/watch.py): big events coming or surging
        import watch
        for q, sig in watch.topics_today(): add(q, sig, vetted=True)
    except Exception as e: print("watchlist:", str(e)[:120])
    for l in [x for x in data.get("launches") or [] if x.get("name")][:2]:      # then what is happening on a schedule
        add(l["name"], f"rocket launch {str(l.get('net_utc', ''))[:16].replace('T', ' ')} UTC ({l.get('status') or '?'})")
    for m in ((data.get("football") or {}).get("fixtures") or [])[:3]:
        add(f"{m['home']} vs {m['away']}", f"{m['competition']}, {str(m.get('kickoff_utc', ''))[:16].replace('T', ' ')} UTC")
    for cc in ("gb", "us"):
        for song in (((data.get("music_charts") or {}).get(cc) or {}).get("new_in_top25") or [])[:2]:
            add(song, f"Apple Music {cc.upper()}: new in the top 25")
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
            "topics": [t for t in topics if t["articles"]][:30] + [t for t in topics if not t["articles"]][:8]}

if __name__ == "__main__":
    main()
