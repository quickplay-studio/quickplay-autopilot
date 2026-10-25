"""More free topic sources for trends.py (24 October, from the free-data research). None needs a key:
- Wikipedia's featured feed: the curated In the news box and the day's selected On this day events (round anniversaries
  of firsts, openings, releases and records only), CC BY-SA, asked for with a User-Agent that names the project;
- TVmaze's schedule for GB, US and the streaming services: series and season premieres of popular shows tonight
  (CC BY-SA 4.0: credited as "TVmaze" in every topic's signal, 3 calls a run, well inside 20 calls every 10 seconds);
- Steam's most played games (Valve's ISteamChartsService) with names from SteamSpy (1 call a run, under its 1 a second):
  games new to the top 100 or climbing fast, adult-only games left out (the store's age and content notes);
- Apple's free RSS charts: albums and free apps new to a top 10 since the day before (trends/charts_more.json keeps the
  last day's lists), explicit albums and money, shopping, dating, gambling and health apps left out;
- Bluesky's trending topics (the public AppView, "unspecced", so it may change): politics and news left out;
- the Formula 1 calendar (Jolpica, the Ergast successor): a race weekend within 3 days, or a race in the last 2.
Deezer is not used: its API terms allow only non-commercial use.

Every source is optional and the lot shares one time limit (TREND_SOURCES_SECONDS; 60 unless set, 20 in the breaking
checks), so a slow source never
holds the trends run up: a source reached after the limit is noted as skipped. collect() returns compact lists for
trends/latest.json; topics() turns them into research topics, round-robin across the sources so each one is measured
every day. Each topic's signal starts with its source's own name (TVmaze, Steam, App Store, Apple albums, Bluesky,
Formula 1, Wikipedia In the news, On this day) and the topic carries "source", so drivers.csv can score the sources.
"""
import datetime as dt, html, json, pathlib, re, time
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot; "
                    "quickplay-studio@users.noreply.github.com)"}
SAVE = ROOT / "trends" / "charts_more.json"
DEADLINE = [0.0]
NOTES = []

# hard news, politics, conflict, disasters and crime: the In the news box, Bluesky and On this day are full of them
NEWS_SKIP = re.compile(
    r"\b(kill(?:s|ed|ing)?|dies|died|death|deaths|dead|attack\w*|bomb\w*|explosion\w*|earthquake\w*|flood\w*|hurricane\w*|"
    r"typhoon\w*|cyclone\w*|wildfire\w*|tsunami\w*|crash\w*|collision\w*|military|missile\w*|strikes?|protest\w*|riot\w*|"
    r"coup|sanction\w*|tariff\w*|prime minister|chancellor|parliament\w*|congress\w*|government\w*|referendum\w*|"
    r"assassinat\w*|hostage\w*|terror\w*|genocide|refugee\w*|migrant\w*|gaza|israel\w*|palestin\w*|hamas|hezbollah|"
    r"ukrain\w*|russia\w*|iran\w*|putin|zelensk\w*|netanyahu|trump|biden|harris|starmer|farage|macron|modi|scandal\w*|"
    r"lawsuit\w*|sued|abuse\w*|massacre\w*|battle\w*|invasion|invaded|execut\w*|disaster\w*|plague|pandemic|epidemic|"
    r"famine|revolution\w*|treaty|independence|regime|dictator\w*|nazi\w*|holocaust|slave\w*|hanged|sank|sinking|"
    r"shipwreck\w*|hijack\w*|kidnap\w*|politic\w*|senator\w*|governor\w*|mayor\w*|cabinet|republican\w*|democrat\w*|labour|"
    r"conservative\w*|tory|tories|nato|united nations|sentenced|prison\w*|jail\w*|guilty|charged|victim\w*|injur\w*|"
    r"fatal\w*|suicide|overdose|drugs?|shot|gun\w*|weapon\w*|nuclear|bombing|soldier\w*|army|armies|troops?|warship\w*)\b", re.I)
# what makes an anniversary worth a Short: a first, an opening, a release, a record
POSITIVE = re.compile(r"\b(first|opens?|opened|opening|releases?|released|launch\w*|premiere\w*|debut\w*|founded|discover\w*|"
                      r"record\w*|wins?|won|invent\w*|lands?|landed|landing|completed?|unveil\w*|publish\w*|introduc\w*|"
                      r"broadcast\w*|airs?|aired|inaugurat\w*|achiev\w*|climb\w*|reach\w*|orbit\w*|patent\w*|perform\w*|"
                      r"crown\w*|champion\w*|title)\b", re.I)
ROUND = (10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 100, 125, 150, 175, 200, 250, 300)
ADULT = re.compile(r"\b(hentai|sex\w*|nsfw|adult|porn\w*|nude\w*|naked|erotic\w*|waifu|casino\w*|poker|slots?|gambl\w*|bet|"
                   r"betting|lottery|loan\w*|crypto\w*|bitcoin)\b", re.I)
APP_GENRES_SKIP = {"finance", "shopping", "medical", "casino", "dating", "health & fitness", "business", "lifestyle"}
TV_TYPES_SKIP = {"news", "sports", "talk show"}
TV_MIN_WEIGHT = 85                # TVmaze's popularity weight, 0 to 100
TV_GENRES_SKIP = {"adult", "horror", "crime", "war"}
STEAM_SEXUAL = {1, 3, 4}          # store content notes: some nudity or sexual content, adult only sexual, frequent nudity

# a topic's source: the start of its signal, also put on the research topic as "source" (writer.source_of reads signals)
SOURCES = ("Wikipedia In the news", "On this day", "TVmaze", "Steam", "Apple albums", "App Store", "Bluesky", "Formula 1", "Apify")


def left():
    return DEADLINE[0] - time.monotonic()


def _get(url, what, **kw):
    """requests.get within the shared time limit; None (with a note) when the limit is reached or the call fails."""
    if left() <= 1:
        NOTES.append(f"{what}: skipped, time limit reached"); return None
    try:
        r = requests.get(url, headers=UA, timeout=min(15, max(2, left())), **kw)
        if r.status_code != 200:
            NOTES.append(f"{what}: HTTP {r.status_code}"); return None
        return r
    except Exception as e:
        NOTES.append(f"{what}: {type(e).__name__}: {str(e)[:100]}"); return None


def _json(url, what, **kw):
    r = _get(url, what, **kw)
    if r is None: return None
    try: return r.json()
    except Exception as e:
        NOTES.append(f"{what}: not JSON ({str(e)[:60]})"); return None


def _text(s):
    s = re.sub(r"<!--.*?-->", "", str(s or ""), flags=re.S)
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()


def _title(p):
    t = (p.get("titles") or {}).get("normalized") or p.get("normalizedtitle") or p.get("title") or ""
    return str(t).replace("_", " ").strip()


def _page_url(p):
    u = ((p.get("content_urls") or {}).get("desktop") or {}).get("page")
    t = _title(p)
    return u or ("https://en.wikipedia.org/wiki/" + t.replace(" ", "_") if t else None)


# ---------------- Wikipedia: In the news and On this day ----------------
def wikipedia_feed(day, skip=None):
    """{"news": [...], "on_this_day": [...]}: In the news stories without hard news, and the day's selected events that
    are round anniversaries of a first, an opening, a release or a record."""
    feed = None
    for url in (f"https://en.wikipedia.org/api/rest_v1/feed/featured/{day:%Y/%m/%d}",
                f"https://api.wikimedia.org/feed/v1/wikipedia/en/featured/{day:%Y/%m/%d}"):     # RESTBase is moving: a fallback
        feed = _json(url, "wikipedia feed")
        if feed: break
    if not feed: return {"error": "no feed"}
    news = []
    for n in feed.get("news") or []:
        story = _text(n.get("story"))
        m = re.search(r"<b>\s*<a [^>]*title=\"([^\"]+)\"", str(n.get("story") or ""))
        main = html.unescape(m.group(1)) if m else (_title((n.get("links") or [{}])[0]) if n.get("links") else "")
        if not story or not main or NEWS_SKIP.search(story) or (skip and skip.search(story)): continue
        link = next((l for l in n.get("links") or [] if _title(l) == main), None)
        news.append({"page": main, "story": story[:160],
                     "url": _page_url(link) if link else "https://en.wikipedia.org/wiki/" + main.replace(" ", "_")})
    days = []
    for e in feed.get("onthisday") or []:
        try: ago = day.year - int(e.get("year"))
        except (TypeError, ValueError): continue
        text, pages = _text(e.get("text")), e.get("pages") or []
        if ago not in ROUND or not pages or not POSITIVE.search(text) or NEWS_SKIP.search(text) or (skip and skip.search(text)): continue
        p = pages[0]
        days.append({"year": int(e["year"]), "years_ago": ago, "text": text[:160], "page": _title(p), "url": _page_url(p)})
    days.sort(key=lambda d: (-(d["years_ago"] in (25, 50, 100)), d["years_ago"] > 100, -d["years_ago"]))
    return {"news": news[:5], "on_this_day": days[:5]}


# ---------------- TVmaze: premieres tonight ----------------
def tv_tonight(day, skip=None):
    """Popular shows starting a series or a season tonight on GB and US television and the streaming services (TVmaze)."""
    out, seen = [], set()
    for where, url, params in (("GB", "https://api.tvmaze.com/schedule", {"country": "GB", "date": str(day)}),
                               ("US", "https://api.tvmaze.com/schedule", {"country": "US", "date": str(day)}),
                               ("web", "https://api.tvmaze.com/schedule/web", {"date": str(day)})):
        rows = _json(url, f"tvmaze {where}", params=params)
        if not isinstance(rows, list): continue
        for ep in rows:
            show = ep.get("show") or (ep.get("_embedded") or {}).get("show") or {}
            name = str(show.get("name") or "").strip()
            if not name or name in seen: continue
            weight = int(show.get("weight") or 0)
            genres = {str(g).lower() for g in show.get("genres") or []}
            if str(show.get("type") or "").lower() in TV_TYPES_SKIP or genres & TV_GENRES_SKIP: continue
            if where == "web" and str(show.get("language") or "") != "English": continue
            if skip and skip.search(name) or ADULT.search(name): continue
            # premieres only: a big show's weekly episode is no news (and the soaps air most nights); its final is on the
            # watchlist when it matters (Strictly, I'm a Celebrity)
            if ep.get("number") != 1 or weight < TV_MIN_WEIGHT: continue
            seen.add(name)
            net = (show.get("network") or show.get("webChannel") or {}).get("name") or ""
            what = "series premiere" if ep.get("season") == 1 else "season premiere"
            out.append({"show": name, "where": where, "what": what, "season": ep.get("season"), "episode": ep.get("number"),
                        "network": net, "time": (ep.get("airtime") or "")[:5], "weight": weight, "tvmaze": show.get("url") or ""})
    out.sort(key=lambda r: (r["what"] != "series premiere", -r["weight"]))
    return out[:8]


# ---------------- Steam: games new to the most played, or climbing ----------------
def steam(skip=None):
    """Games new to Steam's most played top 100 this week, or up 15 places or more into the top 30, with their peak players;
    names from SteamSpy (one call), and the store's age and content notes for the few picked (adult-only left out)."""
    js = _json("https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/", "steam charts")
    ranks = ((js or {}).get("response") or {}).get("ranks") or []
    if not ranks: return [{"error": "no Steam chart"}]
    if not any("last_week_rank" in r for r in ranks):           # without last week's ranks nothing can be called new or rising
        NOTES.append("steam charts: no last_week_rank in the answer"); return []
    picks = []
    for r in ranks:
        rank, last = int(r.get("rank") or 999), int(r.get("last_week_rank") or 0)
        if rank <= 50 and (last == 0 or (rank <= 30 and last - rank >= 15)):
            picks.append({"appid": r.get("appid"), "rank": rank, "last_week_rank": last or None, "peak": int(r.get("peak_in_game") or 0)})
    if not picks: return []
    names = {}
    spy = _json("https://steamspy.com/api.php", "steamspy", params={"request": "top100in2weeks"})
    if isinstance(spy, dict):
        names = {str(k): (v or {}).get("name") for k, v in spy.items() if isinstance(v, dict)}
    out = []
    for p in picks[:6]:
        det = _json("https://store.steampowered.com/api/appdetails", "steam store", params={"appids": p["appid"], "cc": "gb", "l": "english"})
        data = ((det or {}).get(str(p["appid"])) or {}).get("data") or {}
        name = data.get("name") or names.get(str(p["appid"]))
        if not name: continue
        notes = set((data.get("content_descriptors") or {}).get("ids") or [])
        try: age = int(data.get("required_age") or 0)
        except (TypeError, ValueError): age = 0
        if age >= 18 or notes & STEAM_SEXUAL or ADULT.search(name) or (skip and skip.search(name)): continue
        out.append({**p, "name": name, "move": "new" if not p["last_week_rank"] else f"up {p['last_week_rank'] - p['rank']}"})
        if len(out) == 4: break
    return out


# ---------------- Apple: albums and free apps new to a top 10 ----------------
APPLE = {"albums": "https://rss.marketingtools.apple.com/api/v2/{cc}/music/most-played/25/albums.json",
         "apps": "https://rss.marketingtools.apple.com/api/v2/{cc}/apps/top-free/25/apps.json"}


def apple_new(skip=None, countries=("gb", "us")):
    """Albums and free apps new to the GB and US top 10 since the day before (trends/charts_more.json keeps yesterday's)."""
    try: saved = json.loads(SAVE.read_text())
    except Exception: saved = {}
    today = str(dt.date.today())
    if saved.get("date") != today: saved = {"date": today, "previous": saved.get("lists") or {}, "lists": {}}
    out = {}
    for cc in countries:
        for kind, url in APPLE.items():
            js = _json(url.format(cc=cc), f"apple {kind} {cc}")
            rows = ((js or {}).get("feed") or {}).get("results") or []
            if not rows: continue
            names = []
            for x in rows[:10]:
                genres = {str(g.get("name", "")).lower() for g in x.get("genres") or [] if isinstance(g, dict)}
                label = f"{x.get('name', '')} by {x.get('artistName', '')}" if kind == "albums" else str(x.get("name", ""))
                if str(x.get("contentAdvisoryRating", "")).lower().startswith("expli") or genres & APP_GENRES_SKIP: continue
                if ADULT.search(label) or (skip and skip.search(label)): continue
                names.append(label.strip())
            key = f"{kind}_{cc}"
            saved["lists"][key] = names
            before = saved["previous"].get(key) or []
            fresh = [n for n in names if before and n not in before]
            if fresh: out[key] = fresh[:3]
    try: SAVE.write_text(json.dumps(saved, ensure_ascii=False, indent=1))
    except Exception: pass
    return out


# ---------------- Bluesky: trending topics ----------------
def bluesky(skip=None):
    """Bluesky's trending topics (getTrends, else getTrendingTopics), politics and news left out, busiest first."""
    js = _json("https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrends", "bluesky", params={"limit": 25})
    rows = (js or {}).get("trends")
    if not rows:
        js = _json("https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrendingTopics", "bluesky topics", params={"limit": 25})
        rows = (js or {}).get("topics") or []
    out = []
    for t in rows:
        name = str(t.get("displayName") or t.get("topic") or "").strip()
        cat = str(t.get("category") or "").lower()
        if not name or cat in ("politics", "news") or NEWS_SKIP.search(name) or ADULT.search(name) or (skip and skip.search(name)): continue
        out.append({"topic": name, "category": cat, "posts": int(t.get("postCount") or 0), "status": t.get("status") or ""})
    out.sort(key=lambda r: (r["status"] != "hot", -r["posts"]))
    return out[:8]


# ---------------- Formula 1: the next or the last race (Jolpica) ----------------
def formula1(day):
    """The next race if it is within 3 days, and the last race if it was in the last 2 days, with its winner."""
    out = {}
    nxt = _json("https://api.jolpi.ca/ergast/f1/current/next.json", "jolpica next")
    races = (((nxt or {}).get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
    if races:
        r = races[0]
        try: d = dt.date.fromisoformat(r["date"])
        except Exception: d = None
        if d and 0 <= (d - day).days <= 3:
            out["next"] = {"race": f"{r.get('season')} {r.get('raceName')}", "date": r["date"], "url": str(r.get("url", "")).replace("http://", "https://"),
                           "circuit": (r.get("Circuit") or {}).get("circuitName", ""), "country": ((r.get("Circuit") or {}).get("Location") or {}).get("country", "")}
    last = _json("https://api.jolpi.ca/ergast/f1/current/last/results.json", "jolpica last")
    races = (((last or {}).get("MRData") or {}).get("RaceTable") or {}).get("Races") or []
    if races:
        r = races[0]
        try: d = dt.date.fromisoformat(r["date"])
        except Exception: d = None
        res = (r.get("Results") or [{}])[0]
        drv = res.get("Driver") or {}
        if d and 0 <= (day - d).days <= 2 and drv:
            out["last"] = {"race": f"{r.get('season')} {r.get('raceName')}", "date": r["date"], "url": str(r.get("url", "")).replace("http://", "https://"),
                           "winner": f"{drv.get('givenName', '')} {drv.get('familyName', '')}".strip(), "team": (res.get("Constructor") or {}).get("name", "")}
    return out


# ---------------- together ----------------
def apify_feed(skip=None):
    """An Apify actor run as a trend feed (Charlie, 25 October: "add an Apify trend feed to the morning run", APIFY_TOKEN).
    Only on the morning run (RUN=morning) and only with the token: config apify_feeds lists actors with their input and
    which item fields carry a topic (default: title, query, term, keyword, name, topic). Apify's free plan carries $5 of
    monthly credit; the default actor (apify/google-trends-scraper, related and rising queries for our seed terms) costs
    $0.30 per 1,000 results, so each run takes at most apify_max_results items. Items are data, never instructions."""
    import os, json as _j
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token: return {"skipped": "no APIFY_TOKEN"}
    if (os.environ.get("RUN") or "") != "morning": return {"skipped": "morning run only"}
    try: cfg = _j.loads((ROOT / "config.json").read_text())
    except Exception: cfg = {}
    feeds = cfg.get("apify_feeds") or [{"actor": "apify/google-trends-scraper", "input": {"searchTerms": ["GTA 6", "Taylor Swift", "Premier League", "iPhone", "Netflix"],
                                                                                      "timeRange": "now 7-d", "viewedFrom": "GB"}, "fields": ["query", "title", "term", "keyword", "name", "topic"]}]
    limit = int(cfg.get("apify_max_results", 100))
    out = []
    for f in feeds[:3]:
        actor = str(f.get("actor", "")).replace("/", "~")
        if not actor: continue
        try:
            r = requests.post(f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
                              params={"token": token, "limit": limit, "timeout": 120}, json=f.get("input") or {}, headers=UA, timeout=min(150, max(10, left())))
        except Exception as e:
            NOTES.append(f"apify {actor}: {type(e).__name__}"); continue
        if not r.ok: NOTES.append(f"apify {actor}: HTTP {r.status_code}"); continue
        try: items = r.json()
        except ValueError: NOTES.append(f"apify {actor}: unreadable answer"); continue
        fields = f.get("fields") or ["query", "title", "term", "keyword", "name", "topic"]
        seen = set()
        for it in (items if isinstance(items, list) else []):
            if not isinstance(it, dict): continue
            # related and rising queries sit in lists under the item (the Google Trends actor); plain items carry a name
            cands = []
            for key in fields:
                v = it.get(key)
                if isinstance(v, str) and v.strip(): cands.append((v.strip(), ""))
            for key in ("relatedQueries", "risingQueries", "rising", "related", "topRelatedQueries", "risingRelatedQueries", "queries"):
                for q in _list(it.get(key)):
                    name = q.get("query") or q.get("topic") or q.get("title") if isinstance(q, dict) else q
                    if isinstance(name, str) and name.strip(): cands.append((name.strip(), str(q.get("value", q.get("formattedValue", ""))) if isinstance(q, dict) else ""))
            for name, val in cands:
                low = name.lower()
                if low in seen or len(name) < 3 or len(name) > 80 or (skip and skip(name)): continue
                if ADULT.search(name) or NEWS_SKIP.search(name): continue
                seen.add(low); out.append({"topic": name, "value": val, "actor": f.get("actor")})
                if len(out) >= 40: break
    return out[:40]


def collect(skip=None, day=None, seconds=None):
    """Every extra source within one time limit; each returns its compact list or {"error": ...}; never raises."""
    import os
    day = day or dt.date.today()
    # 60 seconds, 20 in the quick breaking checks (trends.yml's BREAKING), unless TREND_SOURCES_SECONDS says otherwise
    seconds = float(seconds if seconds is not None else os.environ.get("TREND_SOURCES_SECONDS") or (20 if os.environ.get("BREAKING") else 60))
    DEADLINE[0] = time.monotonic() + seconds
    NOTES.clear()
    out = {}
    for key, fn in (("formula1", lambda: formula1(day)), ("tv_tonight", lambda: tv_tonight(day, skip)),
                    ("wikipedia_feed", lambda: wikipedia_feed(day, skip)), ("steam", lambda: steam(skip)),
                    ("apple_new", lambda: apple_new(skip)), ("bluesky", lambda: bluesky(skip)), ("apify", lambda: apify_feed(skip))):
        if left() <= 1:
            out[key] = {"error": "skipped: time limit reached"}; NOTES.append(f"{key}: skipped, time limit reached"); continue
        try: out[key] = fn()
        except Exception as e: out[key] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    if NOTES: out["notes"] = NOTES[:12]
    return out


def _list(x):
    return x if isinstance(x, list) else []


def topics(data):
    """Research topics from collect()'s lists: dicts with q, signal, source, and wiki or kind where known. Round-robin
    across the sources (each source's best first), so every source is measured every day."""
    def day_name(iso):
        try: d = dt.date.fromisoformat(str(iso))
        except ValueError: return ""
        return f"{d:%A} {d.day} {d:%B}"
    per = {s: [] for s in SOURCES}
    f1 = data.get("formula1") if isinstance(data.get("formula1"), dict) else {}
    if f1.get("next"):
        n = f1["next"]
        per["Formula 1"].append({"q": n["race"], "signal": f"Formula 1 race weekend, {day_name(n['date'])} (Jolpica)", "wiki": n.get("url") or None})
    if f1.get("last"):
        l = f1["last"]
        per["Formula 1"].append({"q": l["race"], "signal": f"Formula 1 result, {day_name(l['date'])}: {l['winner']} won (Jolpica)", "wiki": l.get("url") or None})
    for t in _list(data.get("tv_tonight")):
        if t.get("show"):
            when = f", {t['time']}" if t.get("time") else ""
            per["TVmaze"].append({"q": t["show"], "signal": f"TVmaze {t.get('where', '')}: {t.get('what', 'premiere')} tonight{when}"})
    wf = data.get("wikipedia_feed") if isinstance(data.get("wikipedia_feed"), dict) else {}
    for n in _list(wf.get("news")):
        per["Wikipedia In the news"].append({"q": n["page"], "signal": "Wikipedia In the news", "wiki": n.get("url")})
    for e in _list(wf.get("on_this_day")):
        per["On this day"].append({"q": e["page"], "signal": f"On this day in {e['year']}, {e['years_ago']} years ago (Wikipedia)",
                                   "wiki": e.get("url"), "kind": "evergreen"})
    for g in _list(data.get("steam")):
        if g.get("name"):
            move = "new in the top 100" if g.get("move") == "new" else f"{g.get('move')} places"
            per["Steam"].append({"q": g["name"], "signal": f"Steam most played: #{g['rank']}, {move}, {g.get('peak', 0):,} players at peak"})
    an = data.get("apple_new") if isinstance(data.get("apple_new"), dict) else {}
    for cc in ("gb", "us"):
        for a in an.get(f"albums_{cc}") or []:
            per["Apple albums"].append({"q": a, "signal": f"Apple albums {cc.upper()}: new in the top 10"})
        for a in an.get(f"apps_{cc}") or []:
            per["App Store"].append({"q": a, "signal": f"App Store {cc.upper()}: new in the top 10 free apps"})
    for b in _list(data.get("bluesky")):
        if b.get("topic"):
            per["Bluesky"].append({"q": b["topic"], "signal": f"Bluesky trending, {b.get('posts', 0):,} posts" if b.get("posts") else "Bluesky trending"})
    for a in _list(data.get("apify")):
        if isinstance(a, dict) and a.get("topic"):
            per["Apify"].append({"q": a["topic"], "signal": f"Apify trend feed ({a.get('actor', 'actor')}" + (f", {a['value']}" if a.get("value") else "") + ")"})
    out, k = [], 0
    while any(len(v) > k for v in per.values()):
        for s in SOURCES:
            if len(per[s]) > k: out.append({**per[s][k], "source": s})
        k += 1
    return out
