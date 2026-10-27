"""Offline test of mega trends (Charlie, 27 October: "the ballon d'or has 92.84 momentum why isnt the posting pattern
following this? there should like 5-10 different shorts about it ... make sure this is the case moving forward"): a topic
whose Wikipedia views jump 20, 50 or 90 times their usual (or 500,000 views on a jump) gets 5, 8 or 10 Shorts a day on top
of the day's number, qualifies on momentum alone, tapers to half its peak as the searches fall and ends under 3 times or
after 7 days; its daily angles may run twice, a fitting channel counts its own angles, the slots and the upload room grow
with it, a breaking check writes at most 4, and the volume test leaves its Shorts out. No live file is read; HTTP is stubbed."""
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
NAME = "Ballon d'Or 2026"
W.CFG = {"watchlist": [{"name": NAME, "terms": ["Ballon d'Or"], "wikipedia": "2026 Ballon d'Or", "date": "2026-10-27",
                        "category": "Sport", "angles": ["Ballon d'Or 2026 ceremony"], "rules": "the awards as news"}]}
W._verdicts = lambda: {}
W._MADE.clear(); W._MEGA_N = None
TODAY = dt.date(2026, 10, 27)
DAY = lambda n: TODAY + dt.timedelta(days=n)
CFG = W.viral_cfg()


def vi(latest, got=None, today=TODAY, pv=None, keep=False):
    if not keep and W.VIRAL_STATE.exists(): W.VIRAL_STATE.unlink()
    got = [] if got is None else got
    return W.viral_items(today, got, latest=latest, pv=pv or (lambda page: [10000] * 16)), got


def measured(**kw):
    g = {"name": NAME, "level": "launch", "days_to": 0, "momentum": 3.0, "places": 4, "phase": "launch",
         "angles": ["Ballon d'Or 2026 ceremony"], "rules": "the awards as news", "in": []}
    g.update(kw); return g


def put(folder, sid, **b):
    (W.BOARDS / folder / f"{sid}.json").write_text(json.dumps({"id": sid, **b}))


# 1. the tiers: 20 times usual gives 5 a day, 50 times 8, 90 times 10; 500,000 views on a jump (or a new page) the top tier
assert CFG["mega"]["tiers"] == [[20, 5], [50, 8], [90, 10]] and CFG["mega"]["end_below"] == 3, CFG["mega"]
assert W.mega_places(None) == 0 and W.mega_places(19.9) == 0
assert W.mega_places(20) == 5 and W.mega_places(49.9) == 5
assert W.mega_places(50) == 8 and W.mega_places(89) == 8
assert W.mega_places(92.84) == 10                                         # the Ballon d'Or on 27 October
assert W.mega_places(5, 600000) == 10 and W.mega_places(None, 600000) == 10   # a jump (or a page too new) with 500,000 views
assert W.mega_places(1.5, 600000) == 0                                    # big but usual: not a surge
assert W.mega_places(5, 400000) == 0                                      # a viral topic, not a mega one

# 2. the level: the current tier while the surge holds, half the peak (2 or more) while it is 3 times or more, then nothing
s = {}
assert W.mega_level(s, 92.84, None, TODAY) == 10 and s == {"mega_since": "2026-10-27", "mega_peak": 10}, s
assert W.mega_level(s, 25, None, DAY(1)) == 5 and s["mega_peak"] == 10 and s["mega_since"] == "2026-10-27", s
assert W.mega_level(s, 8, None, DAY(2)) == 5                              # off the tiers: half the peak of 10
assert W.mega_level(s, 2.9, None, DAY(3)) == 0                            # under 3 times usual: the push ends
assert W.mega_level(s, 92.84, None, DAY(7)) == 0                          # 7 days after it began, whatever the searches
s = {}
assert W.mega_level(s, 20, None, TODAY) == 5 and W.mega_level(s, 4, None, DAY(1)) == 3     # half of 5, rounded up
s = {}
assert W.mega_level(s, 4, None, TODAY) == 2 - 2 and "mega_since" not in s                 # never a tier: never a mega trend
s = {}
assert W.mega_level(s, 30, None, TODAY) == 5 and W.mega_level(s, 1.0, None, DAY(1)) == 0

# 3. a watch item at 92.84 times usual is a mega trend with no other source naming it: 10 places and every angle
out, got = vi({}, [measured(momentum=92.84, views_yesterday=None)])
g = got[0]
assert out == [] and g.get("viral") and g["mega"] == 10 and g["places"] >= 10, g
assert {"people", "rankings", "numbers", "moments", "next", "past", "latest", "why"} <= set(g["angle_map"].values()), g["angle_map"]
assert "Ballon d'Or 2026 star" in g["angles"] and g["mega_since"] == "2026-10-27" and g["mega_peak"] == 10, g
assert json.loads(W.VIRAL_STATE.read_text())[NAME]["mega_peak"] == 10
# the next day at 25 times: still pushed, at the 20 times tier
out, got = vi({}, [measured(momentum=25, views_yesterday=None, days_to=-1, level="after")], today=DAY(1), keep=True)
assert got[0]["mega"] == 5 and got[0]["places"] >= 5, got[0]
# 5 times usual and no other source: an ordinary watch item, not pushed
out, got = vi({}, [measured(momentum=5.0)])
assert out == [] and not got[0].get("viral") and not got[0].get("mega"), got[0]

# 4. a topic of our own on one source (Wikipedia top pages) qualifies on momentum alone: 25 times usual gives 5 places
surge = lambda page: [1000] * 15 + [25000]
latest = {"wikipedia_top": [{"page": "Clayface_(film)", "views": 400000}]}
out, _ = vi(latest, pv=surge)
assert [x["name"] for x in out] == ["Clayface"] and out[0]["mega"] == 5 and out[0]["places"] == 5, out
assert out[0]["category"] == "Film" and out[0]["viral"], out[0]
out, _ = vi(latest, pv=lambda page: [10000] * 15 + [50000])               # 5 times usual on one source: not enough
assert out == [], out
out, _ = vi({"wikipedia_top": [{"page": "Clayface_(film)", "views": 100000}]}, pv=surge)   # under the views floor
assert out == [], out

# 5. a mega trend's daily angle may run twice a day (different sources each time); a once angle still once
item = {"name": NAME, "viral_since": "2026-10-27", "mega": 10}
put("done", "QD-m1", created="2026-10-27", watch=NAME, test={"viral_angle": "people"}, meta={"title": "Who won it"})
W._MADE.clear()
assert W.angle_count(item, "people", TODAY) == 1
assert W.angle_due(item, "people", TODAY) and not W.angle_due(dict(item, mega=0), "people", TODAY)
put("queue", "QD-m2", created="2026-10-27", watch=NAME, test={"viral_angle": "people"}, meta={"title": "Her story"})
W._MADE.clear()
assert not W.angle_due(item, "people", TODAY)
assert W.angle_due(item, "people", DAY(1))                                # a new day: due again
put("done", "QD-m3", created="2026-10-27", watch=NAME, test={"viral_angle": "past"}, meta={"title": "Every winner"})
W._MADE.clear()
assert not W.angle_due(item, "past", DAY(2))                              # once since it went viral
# this run's boards count too
assert not W.angle_due(item, "rankings", TODAY, extra=[{"created": "2026-10-27", "watch": NAME, "test": {"viral_angle": "rankings"}}] * 2)
assert W.angle_due(item, "rankings", TODAY, extra=[{"created": "2026-10-27", "watch": NAME, "test": {"viral_angle": "rankings"}}])

# 6. a fitting channel counts its own angles; the "do not repeat" titles span every channel; a mirror is the same Short
put("done", "QD-c1", created="2026-10-27", watch=NAME, channel="clips", test={"viral_angle": "numbers"}, meta={"title": "The votes"})
put("done", "QD-c2", created="2026-10-27", watch=NAME, channel="clips", mirror_of="QD-c1", test={"viral_angle": "numbers"}, meta={"title": "Los votos"})
W._MADE.clear()
assert W.angle_count(item, "numbers", TODAY, channel="clips") == 1 and W.angle_count(item, "numbers", TODAY) == 0
assert W.angle_count(item, "people", TODAY, channel="clips") == 0 and W.angle_count(item, "people", TODAY) == 2
assert W.viral_made(NAME, "clips") == [("2026-10-27", "numbers", "The votes")]
t = W.viral_titles(item)
assert {"Who won it", "Her story", "Every winner", "The votes"} == set(t) and "Los votos" not in t, t
assert "Fresh one" in W.viral_titles(item, extra=[{"created": "2026-10-27", "watch": NAME, "meta": {"title": "Fresh one"}}])
assert W.board_title({"title": "Top"}) == "Top" and W.board_title({"meta": {"title": "Meta"}}) == "Meta" and W.board_title(None) == ""

# 7. a fact pack belongs to a mega trend when its signal names an item with mega places today
its = [{"name": NAME, "mega": 10}, {"name": "Strictly Come Dancing", "mega": 0}]
assert W.mega_item({"signal": f"watchlist: {NAME} (launch)"}, its)["name"] == NAME
assert W.mega_item({"signal": "watchlist: Strictly Come Dancing (surging)"}, its) is None
assert W.mega_item({"signal": "Google Trends GB"}, its) is None and W.mega_item({}, its) is None

# 8. the day's mega Shorts per channel: every folder but expired, read once a process
for f in list(W.BOARDS.glob("*/QD-*.json")): f.unlink()
put("queue", "QD-a1", created="2026-10-27", watch=NAME, mega="yes")
put("done", "QD-a2", created="2026-10-27", watch=NAME, mega="yes", channel="main")
put("ready", "QD-a3", created="2026-10-27", watch=NAME, mega="yes", channel="clips")
put("done", "QD-a4", created="2026-10-27", watch=NAME)                     # one of the day's 15
put("failed", "QD-a5", created="2026-10-28", watch=NAME, mega="yes")
put("expired", "QD-a6", created="2026-10-27", watch=NAME, mega="yes")      # never posted: no slot kept for it
W._MEGA_N = None
assert W.mega_boards(TODAY) == 2 and W.mega_boards("2026-10-27", "main") == 2, W._MEGA_N
assert W.mega_boards(TODAY, "clips") == 1 and W.mega_boards(DAY(1)) == 1 and W.mega_boards(DAY(2)) == 0
put("queue", "QD-a7", created="2026-10-27", watch=NAME, mega="yes")
assert W.mega_boards(TODAY) == 2 and W.mega_boards(TODAY, fresh=True) == 3   # cached until read fresh
REAL_MEGA = W.mega_boards

# 9. the slots: one more for each mega Short, in the day's widest gaps, all on the day
import plan as P, quota as Q
W.mega_boards = lambda day, channel="main": 0
UTC = dt.timezone.utc
base = [dt.datetime(2026, 10, 27, 8, 0, tzinfo=UTC) + dt.timedelta(minutes=96) * i for i in range(15)]
assert P.with_mega(base, TODAY) == base
W.mega_boards = lambda day, channel="main": {"main": 3, "clips": 2}.get(channel, 0)
more = P.with_mega(base, TODAY)
assert len(more) == 18 and set(base) <= set(more) and more == sorted(more) and len(set(more)) == 18, more
assert all(base[0] <= x < base[0] + dt.timedelta(days=1) for x in more), more
assert all(x.minute % 5 == 0 and x.second == 0 for x in set(more) - set(base)), more
assert min(b - a for a, b in zip(more, more[1:])) >= dt.timedelta(minutes=40), more
P.learned_slots = lambda n: None
P.CFG = dict(P.CFG, shorts_per_day=15)
Q.target = lambda: 15
assert len(P.day_slots(TODAY)) == 18, P.day_slots(TODAY)
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(9, 24)]
assert len(P.day_slots(TODAY)) == 18
n = max(1, int(P.channel_cfg("clips").get("per_day") or 6))
assert len(P.day_slots(TODAY, "clips")) == n + 2, P.day_slots(TODAY, "clips")
assert len(P.day_slots(TODAY, "music")) == max(1, int(P.channel_cfg("music").get("per_day") or 6))

# 10. the upload room keeps a place for each mega Short (the main channel and a signed-in fitting channel)
Q.ROOT = SCRATCH / "q"; (Q.ROOT / "status").mkdir(parents=True); (Q.ROOT / "tokens").mkdir()
per = lambda ch: max(0, int(((Q.CFG.get("shorts_channels") or {}).get(ch) or {}).get("per_day") or 6))
W.mega_boards = lambda day, channel="main": 0
assert Q.uploads_left() == 16, Q.uploads_left()                           # the day's 15 and the weekly video
W.mega_boards = lambda day, channel="main": {"main": 3, "clips": 2}.get(channel, 0) if isinstance(day, dt.date) else 0
assert Q.uploads_left() == 19, Q.uploads_left()
(Q.ROOT / "tokens" / "youtube_clips.enc").write_text("x")                 # the scratch folder's, not the studio's
assert Q.uploads_left() == 19 + per("clips") + 2, Q.uploads_left()
(Q.ROOT / "status" / "QD-u1.json").write_text(json.dumps({"uploaded_at": dt.datetime.now(UTC).isoformat(), "channel": "main"}))
assert Q.uploads_left() == 18 + per("clips") + 2, Q.uploads_left()
W.mega_boards = REAL_MEGA

# 11. the volume test leaves the mega Shorts out: out of the day's count and cohort, their 24-hour views off the day's views
import analytics as A
A.ROOT = SCRATCH / "an"; A.OUT = A.ROOT / "analytics"; A.CACHE = A.OUT / "cache"; A.CACHE.mkdir(parents=True)
(A.OUT / "hourly.csv").write_text("hour_utc,uk_day,hours,yt_gained\n" + "".join(f"2026-10-20T{h:02d}:00,2026-10-20,1,50\n" for h in range(24)))
(A.OUT / "shorts.csv").write_text("short,channel,posted,views_24h,mega\nQD-1,main,2026-10-20T10:00+00:00,100,\n"
                                  "QD-2,main,2026-10-20T11:00+00:00,300,yes\nQD-3,,2026-10-20T12:00+00:00,200,\n")
d = A.volume_days()["2026-10-20"]
assert d["n"] == 2 and d["v24"] == [100.0, 200.0] and d["mega"] == 1 and d["mega_v24"] == 300.0, d
assert d["daily"] == 900.0 and d["cohort"] == 300.0, d
(A.OUT / "shorts.csv").write_text("short,channel,posted,views_24h,mega\nQD-1,main,2026-10-20T10:00+00:00,100,\n"
                                  "QD-2,main,2026-10-20T11:00+00:00,,yes\nQD-3,,2026-10-20T12:00+00:00,200,\n")
d = A.volume_days()["2026-10-20"]
assert d["daily"] is None and d["mega_open"] == 1 and d["n"] == 2, d   # a mega Short still unmeasured: no daily figure yet
(A.OUT / "shorts.csv").write_text("short,channel,posted,views_24h\nQD-1,main,2026-10-20T10:00+00:00,100\n")
d = A.volume_days()["2026-10-20"]
assert d["n"] == 1 and d["daily"] == 1200.0 and d["mega"] == 0, d       # rows from before the column: none is mega

# 12. the writer's share: each mega item's places left for the day, half in the evening, 4 at most on a breaking check
import writer as WR
WR.ROOT = SCRATCH / "wr"
for f in ("queue", "ready", "done", "failed"): (WR.ROOT / "boards" / f).mkdir(parents=True)
mega = {"name": NAME, "mega": 10, "places": 10, "momentum": 92.84, "views_yesterday": None}
assert WR.mega_share([mega], TODAY, "morning", False) == 10
assert WR.mega_share([mega], TODAY, "evening", False) == 5
assert WR.mega_share([mega], TODAY, "morning", True) == 4
assert WR.mega_share([dict(mega, momentum=8, places=5)], TODAY, "morning", True) == 0   # tapering: no breaking writes
assert WR.mega_share([dict(mega, mega=0)], TODAY, "morning", False) == 0
assert WR.mega_share([], TODAY, "morning", False) == 0
for i in range(3): (WR.ROOT / "boards" / "queue" / f"QD-w{i}.json").write_text(json.dumps({"watch": NAME, "created": "2026-10-27"}))
(WR.ROOT / "boards" / "done" / "QD-w8.json").write_text(json.dumps({"watch": NAME, "created": "2026-10-27", "channel": "clips"}))
(WR.ROOT / "boards" / "done" / "QD-w9.json").write_text(json.dumps({"watch": NAME, "created": "2026-10-27", "series_kind": "playbook"}))
(WR.ROOT / "boards" / "done" / "QD-wa.json").write_text(json.dumps({"watch": NAME, "created": "2026-10-26"}))
assert WR.mega_share([mega], TODAY, "morning", False) == 7                 # 3 written; the clips, playbook and old ones apart
assert WR.mega_share([mega, dict(mega, name="Other")], TODAY, "morning", False) == 17

# 13. no em or en dash in what a Short may say (the mega angles) or in this test
for a in W.all_angles(CFG):
    assert "\u2013" not in a["topic"] + a["brief"] and "\u2014" not in a["topic"] + a["brief"], a
assert not any(c in _p.Path(__file__).read_text() for c in ("\u2013", "\u2014"))
assert [a["key"] for a in CFG["mega_angles"]] == ["people", "rankings", "numbers", "moments", "next", "past"]

print("mega trend: ok")
