"""Offline test of the watchlist (pipeline/watch.py, Charlie 23 October: be ready for GTA 6 before the searches peak):
momentum from Wikipedia views, phases from the date, surging from news or Google Trends, topics for trends.py, places a
day, a one-time issue when an item surges, the scout's heat boost and the writer's source label."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import watch as W

W.STATE, W.HIST = SCRATCH / "watch.json", SCRATCH / "watch.csv"
W.LATEST = SCRATCH / "latest.json"           # no viral topics here (tests/test_viral.py)
W.CFG = {"watchlist": [{"name": "GTA 6", "terms": ["GTA 6", "GTA VI"], "wikipedia": "Grand Theft Auto VI", "date": "2026-11-19",
                        "category": "Gaming", "angles": ["GTA 6 price", "GTA 6 map", "GTA 6 soundtrack"], "rules": "no violence"}]}
VIEWS, NEWS = [10000] * 29 + [10000], 4


class R:
    def __init__(self, data=None, text=""): self.ok, self.data, self.text = True, data, text
    def json(self): return self.data


def get(url, **kw):
    if "wikimedia" in url: return R({"items": [{"views": v} for v in VIEWS]})
    if "news.google" in url: return R(text="<item></item>" * NEWS)
    if "suggestqueries" in url: return R(["gta 6", ["gta 6 price", "gta 6 trailer 3", "gta 6 map"]])
    return R({})
W.requests.get = get
ISSUES = []
W.note_surge = lambda g: ISSUES.append(g["name"])

# 1. steady interest 27 days out: build-up, 2 places; the main term every run plus angles
got = W.run(dt.date(2026, 10, 23))[0]
assert got["phase"] == "build-up" and got["level"] == "build-up" and got["places"] == 2 and got["momentum"] == 1.0, got
tops = W.topics_today()
assert tops[0] == ("GTA 6", "watchlist: GTA 6 (build-up, 27 days to go)") and [t for t, _ in tops[1:]] == ["GTA 6 price", "GTA 6 map"], tops
assert not ISSUES
# 2. interest doubles: surging, 3 places, one issue (not again the next run)
VIEWS = [10000] * 29 + [25000]
got = W.run(dt.date(2026, 10, 24))[0]
assert got["level"] == "surging" and got["places"] == 3 and got["momentum"] == 2.5 and ISSUES == ["GTA 6"], (got, ISSUES)
W.run(dt.date(2026, 10, 24)); assert ISSUES == ["GTA 6"]
# 3. launch week whatever the numbers: 4 places; a day per row in the history
VIEWS, NEWS = [10000] * 30, 0
assert W.run(dt.date(2026, 11, 18))[0]["level"] == "launch" and W.state()["items"][0]["places"] == 4
assert len(W.HIST.read_text().strip().splitlines()) == 1 + 3
# 4. long before or long after: steady, measured only (no topics, no places); an item's own lead time
assert W.phase({"date": "2027-06-01"}, dt.date(2026, 10, 23))[1] == "steady"
assert W.phase({"date": "2026-12-10", "lead_days": 21}, dt.date(2026, 10, 23))[1] == "steady"
assert W.phase({"date": "2026-12-10", "lead_days": 21}, dt.date(2026, 11, 20))[1] == "build-up"
W.CFG["watchlist"].append({"name": "Dune: Part Three", "terms": ["Dune Part Three"], "date": "2026-12-18", "lead_days": 30,
                           "category": "Film", "angles": ["Dune Part Three cast"]})
VIEWS, NEWS = [10000] * 30, 2
got = {g["name"]: g for g in W.run(dt.date(2026, 10, 23))}
assert got["Dune: Part Three"]["level"] == "steady" and got["Dune: Part Three"]["places"] == 0, got["Dune: Part Three"]
assert not [t for t, s in W.topics_today() if "Dune" in s], W.topics_today()
NEWS = 20                                   # 20 articles a day is a big film's normal coverage, not a surge
got = {g["name"]: g for g in W.run(dt.date(2026, 10, 23))}
assert got["Dune: Part Three"]["level"] == "steady", got["Dune: Part Three"]
NEWS = 100                                  # no news history yet: a lot of news is not a surge on its own (its normal)
got = {g["name"]: g for g in W.run(dt.date(2026, 10, 23))}
assert got["Dune: Part Three"]["level"] == "steady", got["Dune: Part Three"]
VIEWS = [10000] * 29 + [16000]              # a trailer drops: Wikipedia interest jumps, surging that run whatever the date
got = {g["name"]: g for g in W.run(dt.date(2026, 10, 23))}
assert got["Dune: Part Three"]["level"] == "surging" and ("Dune: Part Three", "watchlist: Dune: Part Three (surging, 56 days to go)") in W.topics_today()
VIEWS = [10000] * 30
import csv as _csv                          # with a week of history: twice its usual is a surge
rows = list(_csv.DictReader(W.HIST.open())); f = list(rows[0].keys())
rows += [dict(rows[-1], day=f"2026-10-1{k}", name="Dune: Part Three", news_24h="25") for k in range(5)]
with W.HIST.open("w", newline="") as fh: w = _csv.DictWriter(fh, fieldnames=f); w.writeheader(); w.writerows(rows)
assert W.news_usual("Dune: Part Three", dt.date(2026, 10, 23)) == 25
NEWS = 45; assert {g["name"]: g for g in W.run(dt.date(2026, 10, 23))}["Dune: Part Three"]["level"] == "steady"
NEWS = 55; assert {g["name"]: g for g in W.run(dt.date(2026, 10, 23))}["Dune: Part Three"]["level"] == "surging"
W.CFG["watchlist"].pop()
print("watch ok")

# 5. the writer labels it Watchlist (not "Rocket launches", which also says launch), the scout adds heat
import writer
assert writer.source_of("watchlist: GTA 6 (launch, 2 days to go)") == "Watchlist"
import submit as S
S.ROOT = SCRATCH; (SCRATCH / "status").mkdir(exist_ok=True)
(SCRATCH / "status" / "watch.json").write_text(json.dumps({"items": [{"name": "GTA 6", "terms": ["GTA 6", "GTA VI"], "level": "surging"}]}))
S.requests = None
import requests as _rq
_rq.get = lambda *a, **k: R({"items": []}, "")
h, why = S.heat("GTA 6")
assert h >= 1.0 and any("watchlist" in w for w in why), (h, why)
print("watch wiring ok")

# 6. per-item launch length and ceiling (24 October, the calendar of big dates): after_days ends launch week early, places caps
#    an item below its level's places; neither field: as before
VIEWS = [10000] * 30
d0 = dt.date(2026, 10, 31)
assert W.phase({"date": "2026-10-31", "after_days": 1}, d0 + dt.timedelta(days=1))[1] == "launch"
assert W.phase({"date": "2026-10-31", "after_days": 1}, d0 + dt.timedelta(days=2))[1] == "steady"
assert W.phase({"date": "2026-10-31"}, d0 + dt.timedelta(days=7))[1] == "launch"
item = {"name": "Halloween 2026", "terms": ["Halloween"], "wikipedia": "Halloween", "date": "2026-10-31", "category": "Entertainment", "places": 2}
assert W.measure(item, d0)["places"] == 2 and W.measure({**item, "places": None}, d0)["places"] == 4
# the shipped watchlist reads: names unique, dates parse, no dashes, inactive items left out of items()
import json as _j
_cfg = _j.loads((_p.Path(REPO_DIR) / "config.json").read_text())
_names = [w["name"] for w in _cfg["watchlist"]]
assert len(_names) == len(set(_names))
for w in _cfg["watchlist"]:
    dt.date.fromisoformat(w["date"]); assert "–" not in _j.dumps(w, ensure_ascii=False) and "—" not in _j.dumps(w, ensure_ascii=False), w["name"]
assert 0 < float(_cfg.get("watch_share_max", 0.34)) <= 0.5
print("watch: per-item launch length and places ok")
