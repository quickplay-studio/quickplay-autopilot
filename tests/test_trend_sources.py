"""Offline test of the extra trend sources (pipeline/trend_sources.py, 24 October): each source's parsing and family
filters on stubbed answers, the shared time limit, Apple's memory of yesterday's top 10, the round-robin topics with
signals that start with their source's name, and trends.research giving them their own places without taking any from
the trends above."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, os, sys, time
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import trend_sources as TS

TS.SAVE = SCRATCH / "charts_more.json"
DAY = dt.date(2026, 10, 24)


class R:
    def __init__(self, js=None, status=200): self.status_code, self._js, self.text = status, js, json.dumps(js); self.ok = status < 400
    def json(self): return self._js


def wiki_page(title):
    return {"titles": {"normalized": title}, "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")}}}


FEED = {"news": [
    {"story": '<!--Oct 24--> In football, <b><a rel="mw:WikiLink" href="./2026_Ballon_d%27Or" title="2026 Ballon d&#039;Or">the Ballon '
              "d'Or</a></b> ceremony is held in London for the first time.", "links": [wiki_page("2026 Ballon d'Or")]},
    {"story": 'An <b><a title="2026 Example earthquake">earthquake</a></b> kills 40 people.', "links": [wiki_page("2026 Example earthquake")]},
    {"story": 'The <b><a title="2026 Example general election">general election</a></b> is won by the Example Party.',
     "links": [wiki_page("2026 Example general election")]}],
    "onthisday": [
    {"text": "The Sydney Opera House is opened.", "year": 1973, "pages": [wiki_page("Sydney Opera House")]},       # 53 years: not round
    {"text": "The first episode of Example Show is broadcast.", "year": 1976, "pages": [wiki_page("Example Show")]},   # 50: kept
    {"text": "A battle is fought and won.", "year": 1926, "pages": [wiki_page("Battle of Example")]},                  # a battle
    {"text": "The Example Bridge is opened to traffic.", "year": 2016, "pages": [wiki_page("Example Bridge")]}]}       # 10: kept

TV = {"GB": [
    {"name": "Episode 1", "season": 1, "number": 1, "airtime": "20:00", "show": {"name": "Cosy Bake Off", "type": "Reality", "genres": ["Food"], "weight": 92,
                                                                              "network": {"name": "Channel 4"}, "url": "https://www.tvmaze.com/shows/1"}},
    {"name": "Episode 120", "season": 40, "number": 120, "airtime": "19:30", "show": {"name": "Daily Soap", "type": "Scripted", "genres": ["Drama"], "weight": 99}},
    {"name": "Bulletin", "season": 2026, "number": 1, "show": {"name": "Evening News", "type": "News", "genres": [], "weight": 95}},
    {"name": "Pilot", "season": 1, "number": 1, "show": {"name": "Night Terrors", "type": "Scripted", "genres": ["Horror"], "weight": 91}},
    {"name": "Pilot", "season": 1, "number": 1, "show": {"name": "Small Show", "type": "Scripted", "genres": ["Comedy"], "weight": 40}}],
    "US": [{"name": "Premiere", "season": 3, "number": 1, "airtime": "21:00", "show": {"name": "Space Rangers", "type": "Scripted", "genres": ["Science-Fiction"],
                                                                                   "weight": 88, "network": {"name": "Example Network"}}}],
    "web": [{"name": "Chapter One", "season": 1, "number": 1, "_embedded": {"show": {"name": "Big Streaming Hit", "type": "Scripted", "genres": ["Fantasy"],
                                                                                   "weight": 96, "language": "English", "webChannel": {"name": "Netflix"}}}},
            {"name": "Ep 1", "season": 1, "number": 1, "_embedded": {"show": {"name": "Foreign Drama", "type": "Scripted", "genres": ["Drama"], "weight": 97,
                                                                             "language": "Korean"}}}]}

STEAM = {"response": {"ranks": [
    {"rank": 1, "appid": 730, "last_week_rank": 1, "peak_in_game": 1500000},
    {"rank": 12, "appid": 111, "last_week_rank": 0, "peak_in_game": 250000},       # new: kept
    {"rank": 20, "appid": 222, "last_week_rank": 45, "peak_in_game": 90000},       # up 25: kept
    {"rank": 25, "appid": 333, "last_week_rank": 0, "peak_in_game": 50000},        # new but adult only: left out
    {"rank": 28, "appid": 444, "last_week_rank": 30, "peak_in_game": 40000}]}}     # up 2: not news
SPY = {"111": {"name": "Cosy Farm"}, "222": {"name": "Space Racers"}, "333": {"name": "Some Game"}}
STORE = {"111": {"success": True, "data": {"name": "Cosy Farm", "required_age": 0}},
         "222": {"success": True, "data": {"name": "Space Racers", "required_age": "0", "content_descriptors": {"ids": [2, 5]}}},
         "333": {"success": True, "data": {"name": "Some Game", "required_age": 18}}}


def apple_feed(kind, cc, extra):
    base = ([{"name": f"Album {i}", "artistName": f"Artist {i}"} for i in range(1, 10)] if kind == "albums" else
            [{"name": f"App {i}", "genres": [{"name": "Games"}]} for i in range(1, 10)])
    return {"feed": {"results": extra + base}}


APPLE_EXTRA = {("albums", "gb"): [{"name": "New Album", "artistName": "New Artist"},
                                  {"name": "Rude Album", "artistName": "Rude Artist", "contentAdvisoryRating": "Explict"}],
               ("apps", "gb"): [{"name": "Money Now", "genres": [{"name": "Finance"}]}, {"name": "Puzzle Pals", "genres": [{"name": "Games"}]}],
               ("albums", "us"): [], ("apps", "us"): []}

BSKY = {"trends": [{"topic": "election", "displayName": "Example Election", "category": "politics", "postCount": 90000, "status": "hot"},
                   {"topic": "derby", "displayName": "North London Derby", "category": "sports", "postCount": 5000, "status": "hot"},
                   {"topic": "trailer", "displayName": "Big Film Trailer", "category": "pop-culture", "postCount": 9000, "status": "warm"},
                   {"topic": "trump", "displayName": "Trump", "category": "", "postCount": 70000, "status": "hot"}]}

F1_NEXT = {"MRData": {"RaceTable": {"Races": [{"season": "2026", "raceName": "Mexico City Grand Prix", "date": str(DAY + dt.timedelta(days=1)),
                                               "url": "http://en.wikipedia.org/wiki/2026_Mexico_City_Grand_Prix",
                                               "Circuit": {"circuitName": "Autodromo Hermanos Rodriguez", "Location": {"country": "Mexico"}}}]}}}
F1_LAST = {"MRData": {"RaceTable": {"Races": [{"season": "2026", "raceName": "United States Grand Prix", "date": str(DAY - dt.timedelta(days=6)),
                                               "url": "http://en.wikipedia.org/wiki/2026_United_States_Grand_Prix",
                                               "Results": [{"Driver": {"givenName": "Ann", "familyName": "Racer"}, "Constructor": {"name": "Team"}}]}]}}}
CALLS, SLOW = [], [0.0]


def get(url, params=None, headers=None, timeout=None):
    CALLS.append(url)
    assert "QuickplayAutopilot" in (headers or {}).get("User-Agent", ""), "every call names the project"
    if SLOW[0]: time.sleep(SLOW[0])
    p = params or {}
    if "feed/featured" in url: return R(FEED) if "en.wikipedia.org" in url else R(None, 503)
    if "tvmaze.com/schedule/web" in url: return R(TV["web"])
    if "tvmaze.com/schedule" in url: return R(TV[p.get("country")])
    if "GetMostPlayedGames" in url: return R(STEAM)
    if "steamspy" in url: return R(SPY)
    if "appdetails" in url: return R({str(p["appids"]): STORE.get(str(p["appids"]), {"success": False})})
    if "marketingtools.apple.com" in url:
        cc = url.split("/api/v2/")[1].split("/")[0]; kind = "albums" if "albums" in url else "apps"
        return R(apple_feed(kind, cc, APPLE_EXTRA[(kind, cc)]))
    if "getTrends" in url: return R(BSKY)
    if "jolpi.ca" in url: return R(F1_NEXT if "next" in url else F1_LAST)
    return R(None, 404)


TS.requests.get = get
SKIP = __import__("re").compile(r"\b(election|vote|minister|president|betting|odds)\b", __import__("re").I)
TS.DEADLINE[0] = time.monotonic() + 60

# 1. Wikipedia: In the news without hard news or politics; On this day only round anniversaries of firsts and openings
wf = TS.wikipedia_feed(DAY, SKIP)
assert [n["page"] for n in wf["news"]] == ["2026 Ballon d'Or"], wf["news"]
assert wf["news"][0]["url"].startswith("https://en.wikipedia.org/wiki/2026_Ballon")
assert [(e["page"], e["years_ago"]) for e in wf["on_this_day"]] == [("Example Show", 50), ("Example Bridge", 10)], wf["on_this_day"]
# 2. TVmaze: premieres of popular shows only; news, horror, soaps, small shows and other languages left out
tv = TS.tv_tonight(DAY, SKIP)
assert [(t["show"], t["what"]) for t in tv] == [("Big Streaming Hit", "series premiere"), ("Cosy Bake Off", "series premiere"),
                                                ("Space Rangers", "season premiere")], tv
# 3. Steam: new to the top 100 or up 15 places into the top 30, adult-only left out
st = TS.steam(SKIP)
assert [(g["name"], g["move"]) for g in st] == [("Cosy Farm", "new"), ("Space Racers", "up 25")], st
# ... and with no last week's ranks in the answer nothing is called new
_s = STEAM; STEAM = {"response": {"ranks": [{"rank": 1, "appid": 111, "peak_in_game": 9}]}}
assert TS.steam(SKIP) == [] and any("last_week_rank" in n for n in TS.NOTES); STEAM = _s
# 4. Apple: nothing new on the first day (no yesterday to compare), then only the clean new entries
assert TS.apple_new(SKIP) == {}
saved = json.loads(TS.SAVE.read_text())
assert saved["lists"]["albums_gb"][0] == "New Album by New Artist" and "Rude Album by Rude Artist" not in saved["lists"]["albums_gb"]
yesterday = {"date": str(dt.date.today() - dt.timedelta(days=1)),
             "lists": {"albums_gb": [f"Album {i} by Artist {i}" for i in range(1, 10)], "apps_gb": [f"App {i}" for i in range(1, 10)],
                       "albums_us": [f"Album {i} by Artist {i}" for i in range(1, 10)], "apps_us": [f"App {i}" for i in range(1, 10)]}}
TS.SAVE.write_text(json.dumps(yesterday))
an = TS.apple_new(SKIP)
assert an == {"albums_gb": ["New Album by New Artist"], "apps_gb": ["Puzzle Pals"]}, an
# 5. Bluesky: politics and hard news left out, hot first
bs = TS.bluesky(SKIP)
assert [b["topic"] for b in bs] == ["North London Derby", "Big Film Trailer"], bs
# 6. Formula 1: tomorrow's race; last week's race is too old for a result Short
f1 = TS.formula1(DAY)
assert f1["next"]["race"] == "2026 Mexico City Grand Prix" and f1["next"]["url"].startswith("https://") and "last" not in f1, f1

# 7. collect(): everything within the time limit, never raises; a limit of zero skips every source at once
TS.SAVE.write_text(json.dumps(yesterday))
data = TS.collect(SKIP, day=DAY, seconds=30)
for k in ("formula1", "tv_tonight", "wikipedia_feed", "steam", "apple_new", "bluesky"): assert k in data, (k, data.keys())
n0 = len(CALLS)
skipped = TS.collect(SKIP, day=DAY, seconds=0)
assert len(CALLS) == n0 and all(str(v.get("error", "")).startswith("skipped") for k, v in skipped.items() if k != "notes"), skipped
# a slow network: the run stops calling once the limit is reached instead of waiting for every source
SLOW[0] = 0.4; t0 = time.monotonic()
slow = TS.collect(SKIP, day=DAY, seconds=1.5)
SLOW[0] = 0.0
assert time.monotonic() - t0 < 5 and any("time limit" in n for n in slow.get("notes", [])), slow.get("notes")

# 8. topics(): round-robin, one per source first, signals that start with the source's name, On this day as evergreen
data["formula1"] = f1
tops = TS.topics(data)
present = [x for x in TS.SOURCES if any(t["source"] == x for t in tops)]        # Apify is empty without a token
first = [t["source"] for t in tops[:len(present)]]
assert first == present, first
by = {}
for t in tops: by.setdefault(t["source"], t)          # each source's best
assert by["On this day"]["kind"] == "evergreen" and by["On this day"]["signal"].startswith("On this day in 1976, 50 years ago")
assert by["TVmaze"]["signal"] == "TVmaze web: series premiere tonight" and by["Steam"]["signal"].startswith("Steam most played: #12, new in the top 100")
assert by["Formula 1"]["signal"] == "Formula 1 race weekend, Sunday 25 October (Jolpica)", by["Formula 1"]
for t in tops:
    assert t["signal"].startswith(t["source"].split(" In ")[0] if t["source"] != "On this day" else "On this day"), t
    assert not any(ord(c) in (0x2013, 0x2014) for c in t["signal"]), t["signal"]      # no en or em dashes
# the writer's source labels: never a wrong existing family (Other until the writer learns the new names)
import writer as W
allowed = {"Wikipedia In the news": {"Wikipedia"}, "On this day": {"Wikipedia"}, "Apple albums": {"Apple Music"}}
for t in tops:
    got = W.source_of(t["signal"])
    assert got in {"Other", t["source"]} | allowed.get(t["source"], set()), (t["signal"], got)

# 9. trends.research(): the extra topics get their own places after the first 30 with articles, and every trend above
#    keeps its place
import trends as T
now = dt.datetime.now(dt.timezone.utc)
T._feed_items = lambda url: []
T._wiki_url = lambda q: "https://en.wikipedia.org/wiki/" + q.replace(" ", "_")
SEARCHED = []
def news_search(q):
    SEARCHED.append(q)
    return [{"title": f"{q} latest", "url": f"https://www.bbc.co.uk/news/{abs(hash(q))}", "when": now, "outlet": "BBC", "words": set(T._words(q + " latest"))}]
T._news_search = news_search
data.update({"date": str(DAY), "google_trends": {"GB": [{"q": f"Topic {chr(65 + i)}{chr(65 + i)} story", "traffic": "10K+"} for i in range(12)],
                                                 "US": [{"q": f"Subject {chr(65 + i)}{chr(65 + i)} match", "traffic": "5K+"} for i in range(12)]},
             "wikipedia_top": [{"page": f"Page {chr(65 + i)}{chr(65 + i)} person", "views": 100000} for i in range(12)]})
pack = T.research(data)
tp = pack["topics"]
extra = [t for t in tp if t.get("source")]
assert 1 <= len(extra) <= T.EXTRA_SLOTS and len({t["source"] for t in extra}) == len(extra), [t["topic"] for t in extra]
pos = [i for i, t in enumerate(tp) if t.get("source")]
main_with = [t for t in tp if not t.get("source") and t["articles"]]
assert len(main_with) == 30 and pos[0] == 30, (len(main_with), pos[:3])
assert sum(1 for q in SEARCHED if q in {x["q"] for x in TS.topics(data)}) <= T.EXTRA_SEARCHES
assert all(t.get("signal", "").startswith(t["source"].split(" In ")[0]) for t in extra)
print("trend sources ok:", ", ".join(f"{t['source']}: {t['topic']}" for t in extra))

# 10. the Apify trend feed (25 October): only on the morning run and only with APIFY_TOKEN; items are data, filtered like
#     every source; each topic carries the Apify source label
import os as _os
POSTS = []
def post(url, params=None, json=None, headers=None, timeout=None):
    POSTS.append((url, params, json))
    return R([{"searchTerm": "GTA 6", "relatedQueries": [{"query": "gta 6 release date", "value": "Breakout"}, {"query": "gta 6 casino", "value": "+500%"}]},
              {"title": "Taylor Swift new album", "query": "taylor swift"}, {"query": "ab"}])
TS.requests.post = post
_os.environ.pop("APIFY_TOKEN", None); _os.environ["RUN"] = "morning"
assert TS.apify_feed() == {"skipped": "no APIFY_TOKEN"}
_os.environ["APIFY_TOKEN"] = "t"; _os.environ["RUN"] = "afternoon"
assert TS.apify_feed() == {"skipped": "morning run only"} and not POSTS
_os.environ["RUN"] = "morning"
TS.DEADLINE[0] = TS.time.monotonic() + 60
got = TS.apify_feed()
names = [g["topic"] for g in got]
assert "gta 6 release date" in names and "taylor swift" in names and "Taylor Swift new album" in names, names
assert "gta 6 casino" not in names and "ab" not in names, names            # gambling word dropped, too short dropped
assert POSTS[0][0].endswith("/acts/apify~google-trends-scraper/run-sync-get-dataset-items") and POSTS[0][1]["token"] == "t"
tops = TS.topics({"apify": got})
assert any(t["source"] == "Apify" and t["signal"].startswith("Apify trend feed") for t in tops), tops[:2]
assert W.source_of("Apify trend feed (apify/google-trends-scraper, Breakout)") == "Apify"
_os.environ.pop("APIFY_TOKEN", None); _os.environ.pop("RUN", None)
print("apify feed ok")
