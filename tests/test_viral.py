"""Offline test of viral topics (pipeline/watch.py viral_items, Charlie 27 October: "the balloon dor is going viral so i need
this pushed lots ... for any viral topics this is just an example"): a topic named by 3+ free source families and jumping on
Wikipedia is pushed for up to a week with several angles, each tested as an arm; unsafe, grim, political, short, meta and
uncategorised topics are never picked up; the angles come round once or daily and never repeat what was made. No live file is
read; HTTP is stubbed."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import watch as W

W.STATE, W.HIST = SCRATCH / "watch.json", SCRATCH / "watch.csv"
W.VIRAL_STATE, W.LATEST, W.BOARDS = SCRATCH / "viral.json", SCRATCH / "latest.json", SCRATCH / "boards"
for d in ("queue", "ready", "done", "failed", "expired"): (W.BOARDS / d).mkdir(parents=True)
W.CFG = {"watchlist": [{"name": "Ballon d'Or 2026", "terms": ["Ballon d'Or"], "wikipedia": "2026 Ballon d'Or", "date": "2026-10-27",
                        "category": "Sport", "angles": ["Ballon d'Or 2026 ceremony"], "rules": "the awards as news"}]}
W._verdicts = lambda: {}
W._MADE.clear()
TODAY = dt.date(2026, 10, 27)
CFG = W.viral_cfg()
JUMP = lambda page: [10000] * 15 + [50000]           # five times its usual: a jump
FLAT = lambda page: [10000] * 16                     # its usual: no jump
NEW = lambda page: [9000, 40000, 90000]              # a page a few days old counts


def one(title, page=None, heads=None, cat="entertainment", views=400000, wiki=True, abroad=True):
    """trends/latest.json naming one topic in Wikipedia top pages, Google Trends (UK and abroad) and the UK news."""
    heads = [f"{title} is the talk of the week"] if heads is None else heads
    out = {"google_trends": {"GB": [{"q": title, "news": [{"title": h} for h in heads]}]}, "google_news_uk": {cat: list(heads)}}
    if abroad: out["google_trends"]["US"] = [{"q": title}]
    if wiki: out["wikipedia_top"] = [{"page": page or title.replace(" ", "_"), "views": views}]
    return out


def both(*ls):
    out = {"google_trends": {}, "google_news_uk": {}, "wikipedia_top": []}
    for l in ls:
        for cc, rows in l.get("google_trends", {}).items(): out["google_trends"].setdefault(cc, []).extend(rows)
        for sec, heads in l.get("google_news_uk", {}).items(): out["google_news_uk"].setdefault(sec, []).extend(heads)
        out["wikipedia_top"] += l.get("wikipedia_top", [])
    return out


def vi(latest, got=None, today=TODAY, pv=JUMP, keep=False):
    if not keep and W.VIRAL_STATE.exists(): W.VIRAL_STATE.unlink()
    got = [] if got is None else got
    return W.viral_items(today, got, latest=latest, pv=pv), got


def measured(**kw):
    g = {"name": "Ballon d'Or 2026", "level": "launch", "days_to": 0, "momentum": 3.0, "places": 4, "phase": "launch",
         "angles": ["Ballon d'Or 2026 ceremony"], "rules": "the awards as news", "in": []}
    g.update(kw); return g


# 1. names: accents, curly apostrophes and a year either side all match
assert W.norm("Ballon d’Or") == W.norm("BALLON D'OR") == "ballon d or"
assert W.bare("2026 Ballon d'Or") == W.bare("Ballon d'Or 2026") == "ballon d or"
assert W._title("Clayface_(film)") == ("Clayface", "film") and W._title("Clayface") == ("Clayface", "")
assert W._momentum(JUMP(None)) == 5.0 and W._momentum(FLAT(None)) == 1.0 and W._momentum(NEW(None)) is None

# 2. an auto item: a film named everywhere, jumping on Wikipedia
CLAY = one("Clayface", page="Clayface_(film)", heads=["Clayface film opens in cinemas"])
out, _ = vi(CLAY)
assert [g["name"] for g in out] == ["Clayface"], out
c = out[0]
assert c["auto"] and c["viral"] and c["phase"] == "viral" and c["category"] == "Film" and c["wikipedia"] == "Clayface_(film)", c
assert c["level"] == "surging" and c["places"] == CFG["places"] == 4 and c["viral_since"] == "2026-10-27"
assert set(c["angle_map"].values()) == {"latest", "why", "reaction", "records", "explained", "facts"}
assert c["angles"][0] == "Clayface" and "Clayface analysis" in c["angles"] and "Clayface history and records" in c["angles"]
assert "No event or broadcast footage" in c["rules"] and set(c["in"]) >= {"Google Trends", "UK news", "Wikipedia top pages"}
assert json.loads(W.VIRAL_STATE.read_text())["Clayface"]["first_seen"] == "2026-10-27"
assert vi(CLAY, pv=FLAT)[0] == []                                          # no jump on Wikipedia: not viral
assert [g["name"] for g in vi(CLAY, pv=NEW)[0]] == ["Clayface"]            # a brand new page counts

# 3. never picked up: too few sources, unsafe, political, grim, short, meta pages, no category, a negative story
assert vi(one("Clayface", page="Clayface_(film)", abroad=False, heads=[]))[0] == []                         # 2 families
assert vi(one("Adult Swim"))[0] == []
assert vi(one("General election 2026"))[0] == []
assert vi(one("Pat Example", heads=["Pat Example, the prime minister, speaks"] * 2))[0] == []
assert vi(one("Pat Example", heads=["Pat Example died aged 80"]))[0] == []
assert vi(one("Pat Example", heads=["Pat Example tribute concert"]))[0] == []
assert vi(one("Pat Example", heads=["Pat Example slammed in feud", "Pat Example backlash grows"]))[0] == []
assert vi(one("UFC"))[0] == []                                              # too short to match safely
assert vi(one("Deaths in 2026"))[0] == [] and vi(one("List of best films"))[0] == []
assert vi(one("Mystery Thing", cat="world"))[0] == []                      # no category: not a story of ours
assert vi(one("Clayface", page="Clayface_(film)", views=1000, abroad=True, heads=[]))[0] == []             # under min_wiki_views, 2 left

# 4. at most max_items auto items at once; the same story under a second name is not a second item
three = both(CLAY, one("Moonfall Rising", page="Moonfall_Rising_(film)"), one("Starlight Parade", page="Starlight_Parade_(song)"))
assert len(vi(three)[0]) == CFG["max_items"] == 2
dup = both(CLAY, one("Basil Karlo", heads=["Clayface star Basil Karlo"] * 2, page="Basil_Karlo_(film)"))
assert [g["name"] for g in vi(dup)[0]] == ["Clayface"]

# 5. a watchlist item that goes viral is lifted in place: viral angles, the viral places, its own rules kept
BALLON = one("Ballon d'Or", page="2026_Ballon_d'Or", heads=["Ballon d'Or 2026 winner named in Paris"], cat="sports")
out, got = vi(BALLON, got=[measured()])
assert out == [] and got[0]["viral"] and got[0]["level"] == "launch" and got[0]["places"] == 4, got
assert got[0]["angles"][0] == "Ballon d'Or 2026" and "Ballon d'Or 2026 reaction" in got[0]["angles"]
assert "Ballon d'Or 2026 ceremony" not in got[0]["angles"]                 # its own angles only before the day
assert got[0]["rules"].startswith("the awards as news") and "never predictions" in got[0]["rules"]
_, got = vi(BALLON, got=[measured(days_to=5, level="surging", places=3)])
assert got[0]["places"] == 4 and got[0]["level"] == "surging" and got[0]["angles"][-1] == "Ballon d'Or 2026 ceremony"
_, got = vi(BALLON, got=[measured(momentum=1.2)])                          # quiet on Wikipedia, only a Wikipedia top page
assert not got[0].get("viral")
_, got = vi(one("Ballon d'Or", heads=["Ballon d'Or 2026 winner named in Paris"], cat="sports", wiki=False), got=[measured(momentum=1.2)])
assert got[0].get("viral")                                                 # in Google Trends: lifted whatever its momentum
_, got = vi(one("Ballon d'Or", heads=["Ballon d'Or night as winner died aged 90"] * 2, cat="sports"), got=[measured()])
assert not got[0].get("viral")                                             # a grim turn stops the push

# 6. the rolling state: hot yesterday or today keeps it; a week from its first day ends it; a gap of 4 days starts afresh
assert len(vi(CLAY)[0]) == 1
assert len(vi({}, today=TODAY + dt.timedelta(days=1), keep=True)[0]) == 1   # hot yesterday
assert vi({}, today=TODAY + dt.timedelta(days=2), keep=True)[0] == []
out, _ = vi(CLAY, today=TODAY + dt.timedelta(days=3), keep=True)          # back within 3 days: the same push, day 4
assert out[0]["viral_since"] == "2026-10-27" and out[0]["angles"][0] == "Clayface history and records"
for d in (4, 5, 6): assert vi(CLAY, today=TODAY + dt.timedelta(days=d), keep=True)[0][0]["viral_since"] == "2026-10-27"
assert vi(CLAY, today=TODAY + dt.timedelta(days=7), keep=True)[0] == []    # a week old: done, however hot
out, _ = vi(CLAY, today=TODAY + dt.timedelta(days=12), keep=True)          # 5 days quiet, then hot again: a new push
assert out[0]["viral_since"] == "2026-11-08"
vi({}, today=TODAY + dt.timedelta(days=50), keep=True)
assert "Clayface" not in json.loads(W.VIRAL_STATE.read_text())             # the state forgets after 30 days
vi(BALLON, got=[measured()])
assert vi({}, got=[], today=TODAY + dt.timedelta(days=1), keep=True)[0] == []   # a watch item taken off the list

# 7. the angles' order: "push" first, "cut back" last, paused left out, else a different lead each day
assert W.angle_order(CFG, TODAY, TODAY)[0] == "latest" and W.angle_order(CFG, TODAY, TODAY + dt.timedelta(days=1))[0] == "why"
W._verdicts = lambda: {"why": "push", "facts": "cut back", "reaction": "paused 14 days"}
assert W.angle_order(CFG, TODAY, TODAY) == ["why", "latest", "records", "explained", "facts"]
W._verdicts = lambda: {k["key"]: "paused" for k in CFG["angles"]}
assert len(W.angle_order(CFG, TODAY, TODAY)) == 6                          # all paused: none left out
W._verdicts = lambda: {}

# 8. what was made: once angles once a push, daily angles once a day, a Spanish mirror is the same Short
CL = vi(CLAY)[0][0]
def board(i, angle, created="2026-10-27", **kw):
    b = {"id": f"QD-{i}", "created": created, "watch": "Clayface", "title": f"Clayface {angle} {i}", "test": {"viral_angle": angle}}
    b.update(kw); (W.BOARDS / "done" / f"QD-{i}.json").write_text(json.dumps(b))
board(1, "why"); board(2, "facts"); board(3, "reaction", mirror_of="QD-9")
W._MADE.clear()
assert [k for _, k, _ in W.viral_made("Clayface")] == ["facts", "why"]                 # oldest first, then by angle
assert not W.angle_due(CL, "why", TODAY) and not W.angle_due(CL, "why", TODAY + dt.timedelta(days=2))
assert W.angle_due(dict(CL, viral_since="2026-11-08"), "why", "2026-11-08")    # a new push: the analysis again
assert not W.angle_due(CL, "facts", TODAY) and W.angle_due(CL, "facts", TODAY + dt.timedelta(days=1))
assert W.angle_due(CL, "reaction", TODAY)
assert not W.angle_due(CL, "reaction", TODAY, extra=[{"watch": "Clayface", "created": "2026-10-27", "test": {"viral_angle": "reaction"}}])
assert W.viral_titles(CL) == ["Clayface facts 2", "Clayface why 1"]
assert W.viral_titles(CL, extra=[{"watch": "Clayface", "created": "2026-10-28", "title": "New one"}])[-1] == "New one"

# 9. trends.py's topics: the item, then its due angles; the made ones wait
W.STATE.write_text(json.dumps({"items": [CL]}))
tt = W.topics_today(TODAY)
names = [t for t, _ in tt]
assert names[0] == "Clayface" and all(s == "watchlist: Clayface (surging)" for _, s in tt), tt
assert "Clayface analysis" not in names and "Clayface facts" not in names and "Clayface reaction" in names, names
assert "Clayface facts" in [t for t, _ in W.topics_today(TODAY + dt.timedelta(days=1))]

# 10. a topic's angle by its signal (the fact packs and the writer read it)
items_ = [CL, {"name": "GTA 6", "angle_map": {"gta 6 price": "x"}}]
assert W.viral_key({"topic": "Clayface analysis", "signal": "watchlist: Clayface (surging)"}, items_) == "why"
assert W.viral_key({"topic": "Clayface analysis", "signal": "Google Trends"}, items_) is None
assert W.viral_key({"topic": "GTA 6 price", "signal": "watchlist: GTA 6 (build-up)"}, items_) is None   # not viral
assert W.viral_key({"topic": "Clayface cast", "signal": "watchlist: Clayface (surging)"}, items_) is None

# 11. the writer: a viral angle is covered only by the same articles, never by a title naming the item
import writer as WR
p = {"topic": "Clayface reaction", "signal": "watchlist: Clayface (surging)",
     "sources": [["", "https://a.com/1"], ["", "https://b.com/2"], ["", "https://c.com/3"]]}
seen = [("Clayface reaction from the fans", "", {"https://z.com/9"})]
assert WR.covered(p, seen) and not WR.covered(p, seen, urls_only=True)
assert WR.covered(p, [("Anything", "", {"https://a.com/1", "https://b.com/2"})], urls_only=True)
assert not WR.covered(p, [("Clayface box office", "", set())])            # names the item, not the angle

# 12. the settings: on, with every angle naming the topic, and no dashes anywhere a reader sees
live = json.loads((_p.Path(REPO_DIR) / "config.json").read_text())["viral"]
assert live["on"] is True and live["min_sources"] >= 3 and live["days"] <= 7
keys = [a["key"] for a in CFG["angles"]]
assert len(keys) == len(set(keys)) and all("{name}" in a["topic"] and a["repeat"] in ("once", "daily") for a in CFG["angles"])
for s in [CFG["rules"]] + [a["brief"] for a in CFG["angles"]] + [json.dumps(live)]:
    assert "\u2013" not in s and "\u2014" not in s, s
print("viral ok")
