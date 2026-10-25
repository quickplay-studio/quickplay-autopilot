"""Offline test of the named, numbered series, the search-led evergreen Shorts and the seasonal playbooks (pipeline/series.py and
playlists.py, hooked into writer.py, watch.py, run_board.py, engage.py, validate.py and analytics.py; Charlie, 25 October 2026).
Why: YouTube search brings 24% of our views and 11 people have subscribed after 141 Shorts, so evergreen Shorts become numbered
series ("Science Explained #12") that sit in playlists, and a big event's launch week becomes a five-part mini-series.
Stubs only: no network, no YouTube, no model; every file it writes is in a scratch folder (or removed again)."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, inspect, json, os, pathlib, sys, types
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
os.environ["WRITE_DRY"] = "1"                 # the writer marks its boards dry, as "dry 2" in requests/write.txt does
os.environ["GITHUB_WORKFLOW"] = "engage"      # whose record of the YouTube allowance the playlist calls write to (scratch below)
import series as S, playlists as PL, quota as Q
import writer as W, factpack as F, validate as V

CFG = json.loads((pathlib.Path(REPO_DIR) / "config.json").read_text())
DASHES = (chr(0x2014), chr(0x2013))           # em and en dash: never in a title, a description or a comment


def nodash(*texts):
    for t in texts: assert not any(d in str(t) for d in DASHES), t


def put(root, folder, bid, **fields):
    d = pathlib.Path(root) / "boards" / folder; d.mkdir(parents=True, exist_ok=True)
    (d / f"{bid}.json").write_text(json.dumps({"id": bid, **fields}))


# 1. the registry in config.json: a series for every category, short names, a title pattern, seeds, no dashes
reg = S.registry(CFG)
assert set(W.CATS) <= set(reg), set(W.CATS) - set(reg)
names = [s["name"] for s in reg.values()]
assert len(names) == len(set(names)) and all(len(n) <= 17 for n in names), names
for cat, spec in reg.items():
    assert all(k in spec["title"] for k in ("{name}", "{n}", "{subject}")) and len(spec["seeds"]) >= 5 and spec["about"], cat
    assert S.decorate("Why is it so? 🎮", spec["name"], 123, spec["title"]).startswith(f"{spec['name']} #123: "), cat
assert CFG["evergreen_search_per_day"] == 2 and CFG["playbook"]["angles"] == 5 and CFG["playbook"]["grace_days"] == 2
nodash(json.dumps({k: v for k, v in CFG.items() if k.startswith(("series", "playbook", "evergreen_search"))}, ensure_ascii=False))
odd = S.registry({"series": [{"name": "A"}, "junk", {"name": "B", "category": "Film", "title": "no subject here"},
                             {"name": "C", "category": "Film"}]})        # no category, not a dict, no {subject}, a second Film
assert list(odd) == ["Film"] and odd["Film"]["name"] == "B" and odd["Film"]["title"] == S.DEFAULT_TITLE, odd
print("1 registry ok")

# 2. the next number counts the boards of the series in every folder that holds a number, once each
R = SCRATCH / "numbers"
put(R, "queue", "QD-001", series_name="Science Explained", series_no=1)
put(R, "done", "QD-002", series_name="Science Explained", series_no=2)
put(R, "hold", "QD-003", series_name="Science Explained", series_no=3)
put(R, "expired", "QD-004", series_name="Science Explained", series_no=4)             # an expired board holds no number
put(R, "queue", "QD-005", series_name="Science Explained", series_no=5, mode="dry")   # a dry run never goes out
put(R, "done", "QD-006", series_name="Game Explained", series_no=1)
put(R, "ready", "QD-007", franchise="Game Facts #3")
assert S.next_number("Science Explained", root=R) == 4
assert S.next_number("Game Explained", root=R) == 2 and S.next_number("Music Explained", root=R) == 1
w1 = {"id": "QD-008", "series_name": "Science Explained", "series_no": 4}
assert S.next_number("Science Explained", [w1], R) == 5
assert S.next_number("Science Explained", [{"id": "QD-001", "series_name": "Science Explained", "series_no": 1}, w1], R) == 5   # on disk too: once
dry = {"id": "QD-009", "series_name": "Science Explained", "series_no": 4, "mode": "dry"}
assert S.next_number("Science Explained", [w1, dry], R) == 6                           # a dry run's own Shorts count on from each other
put(R, "queue", "QD-010", series_name="Science Explained", series_no=9)               # a board lost from a folder never repeats a number
assert S.next_number("Science Explained", root=R) == 10
print("2 numbering ok")

# 3. decorate: the series name and number lead, the emoji stays last, the limit holds, words go from the end
d = S.decorate
assert d("Why is the sky blue? 🔭", "Science Explained", 12) == "Science Explained #12: Why is the sky blue? 🔭"
assert d("Science Explained #3: Why is the sky blue? 🔭", "Science Explained", 12) == "Science Explained #12: Why is the sky blue? 🔭"
assert d("why is the sky blue", "Science Explained", 7) == "Science Explained #7: Why is the sky blue"
assert d("iPhone 17 battery: why it lasts 🔋", "Tech Explained", 2) == "Tech Explained #2: iPhone 17 battery: why it lasts 🔋"
assert d("Why is the sky blue?", "Science Explained", 12) == "Science Explained #12: Why is the sky blue?"      # no emoji: none added
long = d("Why do astronauts float inside the International Space Station even though gravity is still there 🚀", "Science Explained", 12)
assert len(long) <= 70 and long.startswith("Science Explained #12: Why do astronauts") and long.endswith(" 🚀"), long
assert long[len("Science Explained #12: "):-2].split()[-1].lower() not in S.STOPS, long
moon = d("Why does the Moon look bigger near the horizon than it really is at night 🌙", "Science Explained", 14)
assert len(moon) <= 70 and moon.endswith(" 🌙") and moon[:-2].split()[-1].lower() not in S.STOPS, moon        # no dangling "near" or "than"
assert len(d("x" * 80 + " 🔭", "Science Explained", 12)) <= 70                                             # one huge word: name and number only
assert d("Ballon d'Or 2026: who wins? 🏆", "Ballon d'Or", 2, also=["Ballon d'Or 2026"]) == "Ballon d'Or #2: Who wins? 🏆"
assert d("Ballon d'Or: who wins? 🏆", "Ballon d’Or", 3) == "Ballon d’Or #3: Who wins? 🏆"           # curly and straight quotes match
assert d("Why? 🔭", "Sky", 4, pattern="{name} {n} | {subject}") == "Sky 4 | Why? 🔭"
assert d("Why? 🔭", "Sky", 4, pattern="{name} {oops}: {subject}") == "Sky #4: Why? 🔭"                        # a broken pattern: the default
nodash(long, moon)
print("3 titles ok")

# 4. the description lines, the label and the creator comment
STATUS = SCRATCH / "status"; STATUS.mkdir()
S.PLAYLISTS = PL.STATE = STATUS / "playlists.json"
S.PLAYLISTS.write_text(json.dumps({"playlists": {"Science Explained": {"id": "PLSCI"}}}))
URL = "https://www.youtube.com/playlist?list=PLSCI"
SB = {"category": "Science", "series_name": "Science Explained", "series_no": 12, "series_kind": "evergreen", "series_key": "Science Explained"}
assert S.playlist_id("Science Explained", CFG) == "PLSCI" and S.playlist_url("Science Explained", CFG) == URL
assert S.playlist_id("Game Explained", CFG) == "" and S.playlist_url("Game Explained", CFG) == ""
assert S.playlist_id("Science Explained", {"series": [{"name": "Science Explained", "category": "Science", "playlist": "PLHAND"}]}) == "PLHAND"
lines = S.description_lines(SB, cfg=CFG)
assert lines[0].startswith("Science Explained #12: ") and lines[1] == f"More in the series: {URL}" and lines[-1] == "", lines
assert S.description_lines(SB, "", CFG)[1:] == [""]                         # no playlist yet: the series line alone
assert S.description_lines({"category": "Film"}, URL, CFG) == [] and S.description_lines(None) == []
c = S.comment_text("Which planet would you visit?", SB, URL)
assert c.startswith("Which planet would you visit?") and "Science Explained #12." in c and URL in c and len(c) <= 500, c
assert S.comment_text("Which planet?", SB, "").endswith("Science Explained #12.") and "playlist" not in S.comment_text("Which planet?", SB, "")
assert S.comment_text("Which planet?", {"category": "Film"}, URL) == "Which planet?"
assert len(S.comment_text("q" * 600, SB, URL)) <= 500 and URL in S.comment_text("q" * 600, SB, URL)
assert S.label({"series_name": "Ballon d'Or", "series_no": 2, "series_of": 5}) == "Ballon d'Or #2 of 5" and S.label(SB) == "Science Explained #12"
nodash(*lines, c)
import run_board as RB                                                       # the YouTube description (the render's)
track = {"title": "T", "artist": "A"}
meta = {"summary": "A short answer.", "sources": [["Wikipedia", "https://en.wikipedia.org/wiki/Sky"]], "hashtags": ["#sky"]}
desc = RB.description({**SB, "meta": meta}, [], track).split("\n")
assert desc[:2] == ["A short answer.", ""] and desc[2].startswith("Science Explained #12: ") and desc[3] == f"More in the series: {URL}", desc[:6]
assert desc[4:6] == ["", "Sources:"], desc[:7]
assert RB.description({"meta": meta}, [], track).split("\n")[:3] == ["A short answer.", "", "Sources:"]    # any other Short: as before
print("4 description and comment ok")

# 5. what people search: our own terms, Google Trends related queries (none in latest.json yet), YouTube's suggestions, On this day
CR = SCRATCH / "cand"; (CR / "analytics").mkdir(parents=True)
(CR / "analytics" / "search_terms.csv").write_text("term,views\nmark allen,185\ngodzilla minus zero,165\nelection results,300\nwhy does the moon change shape,90\n")
LATEST = {"google_trends": {"GB": [{"q": "bbc cricket", "traffic": "200+", "news": ["x"],
                                    "related": ["why is the sky blue", {"query": "how do magnets work"}, "election night"]}]},
          "wikipedia_feed": {"on_this_day": [{"page": "Windows XP", "text": "Windows XP went on retail sale.", "url": "https://en.wikipedia.org/wiki/Windows_XP", "year": 2001}]}}
asked = []


class Got:
    def __init__(self, data): self.data = data
    def json(self): return self.data


def get(url, **kw):
    q, gl = kw["params"]["q"], kw["params"]["gl"]; asked.append((q, gl))
    return Got([q, [q, f"{q} in minecraft", "why does minecraft have creepers", "minecraft election night"]])


assert [x["text"] for x in S.own_terms(CR)][:2] == ["election results", "mark allen"]            # most views first
assert S.own_terms(SCRATCH / "nothing here") == []
cands = S.candidates(LATEST, 0, CFG, CR, get, 5)
texts = [x["text"] for x in cands]
assert texts[:3] == ["mark allen", "godzilla minus zero", "why does the moon change shape"], texts     # our own traffic first
assert not [t for t in texts if "election" in t], texts                                                 # politics never becomes a Short
assert [x["text"] for x in cands if x["source"] == "Google Trends related queries"] == ["why is the sky blue", "how do magnets work"]
sug = [x for x in cands if x["source"] == "YouTube search suggestions"]
assert sug and all(x["detail"] in reg for x in sug) and all(S.norm(x["text"]) != S.norm(q) for x in sug for q, _ in asked[:1])
assert texts[-1] == "Windows XP" and cands[-1]["source"] == "Wikipedia On this day"
assert len({S.norm(t) for t in texts}) == len(texts)                                                    # GB and US give the same: once
assert {gl for _, gl in asked} == {"GB", "US"} and not [q for q, _ in asked if "election" in q]
assert S.lines_of(cands).splitlines()[0] == "1. [our search traffic, 185 views] mark allen"
real_own = S.own_terms
S.own_terms = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
cands2 = S.candidates(LATEST, 0, CFG, CR, get, 5)
S.own_terms = real_own
assert cands2 and not [x for x in cands2 if x["source"] == "our search traffic"]                         # one source fails, the rest stay
assert S.suggestions(0, CFG, get, seconds=-1) == []                                                     # out of time before the first ask
assert S.suggest("q", get=lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))) == []             # offline: nothing, no error
assert S.trends_related({"google_trends": {"GB": [{"q": "x", "traffic": "1+", "news": []}]}}) == [] and S.trends_related(None) == []
assert S.on_this_day({}) == [] and S.on_this_day(None) == []
q0, q1, q2 = (S.suggestion_queries(t, CFG) for t in (0, 1, 2))
assert len(q0) == 20 and {c for c, _ in q0} != {c for c, _ in q1}
assert {c for q in (q0, q1, q2) for c, _ in q} == set(reg)                                              # every category asked within three runs
seed = reg[q0[0][0]]["seeds"][0]
assert [q for c, q in q0 if c == q0[0][0]] == [f"why does {seed}", f"what is {seed}", f"how did {seed}", f"{seed} explained"], q0[:4]
print("5 candidates ok")

# 6. how many search-led Shorts a run writes: the evening and the morning one each, the afternoon what the day is short of
SD, DAY = SCRATCH / "due", dt.date(2030, 1, 15)
due = lambda run, cap=6, per_day=2, root=SD: S.search_due(DAY, run, cap, per_day, root)
assert (due("evening"), due("morning"), due("afternoon")) == (1, 1, 2)
put(SD, "queue", "QD-301", created=str(DAY), source="Search-led")
assert (due("evening"), due("morning"), due("afternoon")) == (1, 1, 1)
put(SD, "done", "QD-302", created=str(DAY), source="Search-led")
assert (due("evening"), due("morning"), due("afternoon")) == (0, 0, 0)                  # two made: the day is full whichever run asks
SD2 = SCRATCH / "due2"
put(SD2, "done", "QD-303", created="2030-01-14", source="Search-led")                  # another day's does not count
put(SD2, "done", "QD-304", created=str(DAY), source="Evergreen")                         # nor does another source
put(SD2, "queue", "QD-305", created=str(DAY), source="Search-led", mode="dry")          # nor a dry run, which never goes out
assert due("afternoon", root=SD2) == 2 and due("afternoon", 1, root=SD2) == 1 and due("afternoon", 0, root=SD2) == 0
assert due("afternoon", per_day=0, root=SD2) == 0 and S.search_due(DAY, "afternoon", 6, None, SD2) == CFG["evergreen_search_per_day"]
print("6 search_due ok")

# 7. seasonal playbooks: written once, five angles, one a day, the series moves on after a missed day or two
PB = SCRATCH / "playbooks.json"
ITEM = {"name": "Ballon d'Or 2026", "date": "2026-11-02", "category": "Sport",
        "angles": ["Ballon d'Or nominees", "Ballon d'Or all-time winners", "Ballon d'Or youngest winner"]}
assert S.short_name("The Hunger Games: Sunrise on the Reaping 2026") == "Hunger Games" and S.short_name("Avengers: Doomsday") == "Avengers: Doomsday"
assert S.short_name("GTA 6") == "GTA 6" and S.short_name("Ballon d'Or 2026") == "Ballon d'Or"
plan = S.ensure_playbook(ITEM, "launch", dt.date(2026, 11, 1), PB, CFG)
EV, ANG = ITEM["name"], plan["angles"]
assert plan["of"] == 5 and ANG[:3] == ITEM["angles"] and ANG[3] == "Ballon d'Or 2026 explained", plan       # its own angles first, then generic ones
assert plan["short"] == "Ballon d'Or" and plan["created"] == "2026-11-01" and plan["playlist_title"] == "Ballon d'Or 2026 in 5 Shorts | Quickplay Daily"
assert json.loads(PB.read_text())["playbooks"][EV] == plan
assert S.ensure_playbook(ITEM, "surging", dt.date(2026, 11, 3), PB, CFG) is None                               # once only
assert json.loads(PB.read_text())["playbooks"][EV]["created"] == "2026-11-01"
assert S.ensure_playbook({**ITEM, "name": "Other"}, "build-up", dt.date(2026, 11, 1), PB, CFG) is None         # not before launch or surging
assert S.ensure_playbook({**ITEM, "name": "Other", "angles": []}, "launch", dt.date(2026, 11, 1), PB, CFG) is None    # no angles, no plan
assert S.ensure_playbook({**ITEM, "name": "Dune: Part Three", "short": "Dune 3"}, "surging", dt.date(2026, 11, 1), PB, CFG)["short"] == "Dune 3"
PR = SCRATCH / "play"
D = lambda n: dt.date(2026, 11, 1) + dt.timedelta(days=n)
assert S.today_angle(EV, D(0), PB, PR, CFG) == (1, ANG[0])
put(PR, "queue", "QD-401", created=str(D(0)), series_kind="playbook", series_key=EV, series_no=1, series_name="Ballon d'Or")
assert S.today_angle(EV, D(0), PB, PR, CFG) is None                                    # one a day
assert S.progress(EV, PR) == {1: str(D(0))}
assert [S.today_angle(EV, D(n), PB, PR, CFG) for n in (1, 2, 3)] == [(2, ANG[1])] * 3  # its turn, and its grace days
assert [S.today_angle(EV, D(n), PB, PR, CFG) for n in (4, 5, 6)] == [(3, ANG[2]), (4, ANG[3]), (5, ANG[4])]     # then the series moves on
assert S.today_angle(EV, D(7), PB, PR, CFG) is None and S.today_angle("No such event", D(0), PB, PR, CFG) is None
pk = {"topic": ANG[1], "signal": f"watchlist: {EV} (launch, 1 day to go)", "category": "Sport"}
hit = S.playbook_match(pk, PB)
assert hit and hit[1] == 2 and hit[0]["event"] == EV
assert S.playbook_match({**pk, "topic": EV}, PB) is None                               # the event's main topic is no angle
assert S.playbook_match({**pk, "signal": "watchlist: Another event (launch)"}, PB) is None
assert S.playbook_match({**pk, "signal": "evergreen question"}, PB) is None
assert S.playbook_match({**pk, "topic": ANG[1].upper() + "!"}, PB)[1] == 2             # case and punctuation are ignored
print("7 playbooks ok")

# 8. which series a pack joins, the note the model gets, and the board's number and titles (the franchise test works as before)
s = S.series_for(pk, "news", "Sport", False, CFG, PB)
assert (s["kind"], s["key"], s["name"], s["no"], s["of"], s["also"]) == ("playbook", EV, "Ballon d'Or", 2, 5, [EV]), s
EVP = {"topic": "Why is the sky blue", "category": "Science", "signal": "evergreen question (search-led: our search traffic)"}
s = S.series_for(EVP, "evergreen", None, False, CFG, PB)
assert s["kind"] == "evergreen" and s["name"] == "Science Explained" and s["pattern"].endswith("{subject}")
assert S.series_for(EVP, "evergreen", None, True, CFG, PB) is None                     # the reserve is released in any order
assert S.series_for(EVP, "news", None, False, CFG, PB) is None and S.series_for(EVP, "top list", None, False, CFG, PB) is None
assert S.series_for({**EVP, "category": "Fiction"}, "evergreen", None, False, CFG, PB) is None      # a category with no series
TESTS = {"franchise": "named", "hook_type": "number"}
t2, note = S.prepare(pk, "news", TESTS, "BASE", False, CFG, PB)
assert t2["franchise"] == "series" and t2["hook_type"] == "number" and TESTS["franchise"] == "named"      # the caller's dict is left alone
assert note.startswith("BASE") and "MINI-SERIES" in note and "number 2 of 5" in note and f'"{ANG[1]}"' in note and '"Ballon d\'Or #2: "' in note, note
t3, n3 = S.prepare(EVP, "evergreen", {"franchise": "named"}, "", False, CFG, PB)
assert t3["franchise"] == "series" and n3.startswith("NUMBERED SERIES:") and '"Science Explained"' in n3 and "under 45 characters" in n3
NEWS = {"topic": "Some film news", "category": "Film", "signal": "Google Trends GB"}
assert S.prepare(NEWS, "news", TESTS, "BASE", False, CFG, PB) == (TESTS, "BASE")                         # the franchise test is untouched
assert S.prepare({**pk, "topic": EV}, "news", TESTS, "", False, CFG, PB) == (TESTS, "")
assert S.prepare(EVP, "evergreen", TESTS, "", True, CFG, PB) == (TESTS, "")                              # the reserve is left alone
NB = SCRATCH / "nb"
b = {"kind": "news", "category": "Sport", "meta": {"title": "Who has won the most Ballon d'Ors? ⚽", "alt_title": "Ballon d'Or: the record holder ⚽"}}
f = S.name_board(b, pk, [], False, PR, CFG, PB)
assert f == {"series_name": "Ballon d'Or", "series_no": 2, "series_kind": "playbook", "series_key": EV, "series_of": 5}, f
assert all(b[k] == v for k, v in f.items())
assert b["meta"]["title"] == "Ballon d'Or #2: Who has won the most Ballon d'Ors? ⚽" and b["meta"]["alt_title"] == "Ballon d'Or #2: The record holder ⚽"
eb = {"kind": "evergreen", "category": "Science", "meta": {"title": "Why is the sky blue? 🔭"}}
f = S.name_board(eb, EVP, [{"id": "QD-501", "series_name": "Science Explained", "series_no": 7}], False, NB, CFG, PB)
assert f == {"series_name": "Science Explained", "series_no": 8, "series_kind": "evergreen", "series_key": "Science Explained"}, f
assert eb["meta"]["title"] == "Science Explained #8: Why is the sky blue? 🔭" and "alt_title" not in eb["meta"]
plain = {"kind": "news", "category": "Film", "meta": {"title": "Film news"}}
assert S.name_board(plain, NEWS, [], False, NB, CFG, PB) is None and plain == {"kind": "news", "category": "Film", "meta": {"title": "Film news"}}
assert S.name_board({**eb, "reserve": True, "meta": {"title": "x"}}, EVP, [], False, NB, CFG, PB) is None      # the board's own reserve flag counts
odd = {"kind": "evergreen", "category": "Games and fun", "meta": {"title": "Why Minecraft? 🎮"}}               # the pack's category when the board's has no series
assert S.name_board(odd, {"topic": "Why Minecraft", "category": "Gaming", "signal": "evergreen question"}, [], False, NB, CFG, PB)["series_name"] == "Game Explained"
assert {"series_name", "series_no", "series_kind", "series_key", "series_of"} <= set(W.BOOKKEEPING) and "series_name" not in W.example()
# the series prefix is no subject: it does not make other Shorts "covered", and it is no title style ("#12" is not a number in the title)
done = {"id": "QD-1", "series_name": "Science Explained", "series_key": "Science Explained",
        "meta": {"title": "Science Explained #12: Why is the atmosphere blue? 🔭", "tags": ["sky"], "hashtags": ["#sky"]}}
assert W.about(done)[0] == "Why is the atmosphere blue? 🔭" and W.about({"meta": {"title": "Science Explained #12: x"}})[0] == "Science Explained #12: x"
assert not W.covered({"topic": "Science explained quantum computers", "sources": []}, [W.about(done)])
assert W.covered({"topic": "Atmosphere blue colour", "sources": []}, [W.about(done)])
import drivers as DR
sty = lambda title, **k: DR.features({"title": title, "hook": "", **k})["title_style"]
assert sty("Science Explained #12: Why is the sky blue", series_name="Science Explained") == "statement"
assert sty("Science Explained #12: Why is the sky blue?", series_name="Science Explained") == "question"
assert sty("Science Explained #12: Top 10 skies", series_name="Science Explained") == "number in title"
assert sty("Song Secrets #5: Why the chorus works", franchise="named") == "statement" and sty("Ballon d'Or #2: Who wins?", series_name="Ballon d'Or") == "question"
assert sty("Windows XP turned 25") == "number in title" and sty("Why is the sky blue?") == "question"      # no series: as before
print("8 series_for, prepare and name_board ok")

# 9. the watchlist: the playbook is written once when an item reaches launch, topics_today offers the day's angle
import watch as WT
(SCRATCH / "w").mkdir()
WT.STATE, WT.HIST = SCRATCH / "w" / "watch.json", SCRATCH / "w" / "watch.csv"
WT.CFG = {"watchlist": [{**ITEM, "terms": ["Ballon d'Or"], "angles": ITEM["angles"] + ["Ballon d'Or 2026 explained", "Ballon d'Or 2026 trophy", "Ballon d'Or 2026 ceremony"]},
                        {"name": "Dune: Part Three", "terms": ["Dune Part Three"], "date": "2026-12-01", "category": "Film",
                         "angles": ["Dune Part Three cast", "Dune Part Three trailer", "Dune Part Three book"]}]}


class Resp:
    def __init__(self, data=None, text=""): self.ok, self.data, self.text = True, data, text
    def json(self): return self.data


real_get = WT.requests.get
WT.requests.get = lambda url, **kw: (Resp({"items": [{"views": 10000} for _ in range(30)]}) if "wikimedia" in url else
                                     Resp(text="<item></item>" * 4) if "news.google" in url else Resp(["x", ["a"]]) if "suggest" in url else Resp({}))
WT.note_surge = lambda g: None
S.ROOT = SCRATCH / "wroot"                                  # no playbook boards yet
got = {g["name"]: g for g in WT.run(dt.date(2026, 11, 1))}
assert got[EV]["level"] == "launch" and got["Dune: Part Three"]["level"] == "build-up", got
pbw = WT.playbooks_path()
assert pbw == SCRATCH / "w" / "playbooks.json"
saved = json.loads(pbw.read_text())["playbooks"]
assert list(saved) == [EV] and saved[EV]["of"] == 5 and saved[EV]["created"] == "2026-11-01", saved             # only the launching item, not the build-up one
assert saved[EV]["angles"] == WT.CFG["watchlist"][0]["angles"][:5]
tops = WT.topics_today(dt.date(2026, 11, 1))
sig = "watchlist: Ballon d'Or 2026 (launch, 1 day to go)"
assert tops[:3] == [(EV, sig), ("Ballon d'Or nominees", sig), ("Ballon d'Or 2026 ceremony", sig)], tops       # main, the angle due, the one outside the playbook
assert [t for t, _ in tops if "Dune" in t] == ["Dune: Part Three", "Dune Part Three cast", "Dune Part Three trailer"], tops    # no playbook: as before
put(S.ROOT, "queue", "QD-601", created="2026-11-01", series_kind="playbook", series_key=EV, series_no=1)
assert "Ballon d'Or nominees" not in [t for t, _ in WT.topics_today(dt.date(2026, 11, 1))]                      # today's is written: no second angle
assert "Ballon d'Or all-time winners" in [t for t, _ in WT.topics_today(dt.date(2026, 11, 2))]                  # tomorrow's
WT.run(dt.date(2026, 11, 3)); assert json.loads(pbw.read_text())["playbooks"][EV]["created"] == "2026-11-01"      # not written again
WT.requests.get = real_get
S.ROOT = pathlib.Path(REPO_DIR)
print("9 watch wiring ok")

# 10. validate.py: a series title may pass 50 characters (the prefix is added after the writer), still 70 at most
ex = json.loads(W.example())
ex["meta"]["title"] = "Science Explained #12: Why is the sky blue and the sunset red 🔭"
long_title = lambda bd: [w for w in V.check(bd)[1] if w.startswith("meta.title") and "characters" in w]
assert len(ex["meta"]["title"]) <= 70 and long_title(ex), V.check(ex)[1]                # without a series it still warns
ex["series_name"] = "Science Explained"
assert not long_title(ex) and not [e for e in V.check(ex)[0] if "meta.title" in e], V.check(ex)
ex["meta"]["title"] = "S" * 71 + " 🔭"
assert [e for e in V.check(ex)[0] if "meta.title" in e]                                  # 70 is still the limit
print("10 validate ok")

# 11. analytics.py: shorts.csv carries the series name, number and kind (not the cliffhanger "series" column)
import analytics as A
AR = SCRATCH / "an"
for fd in ("done", "ready", "queue", "failed", "rejected", "reserve", "hold", "expired"): (AR / "boards" / fd).mkdir(parents=True)
(AR / "status").mkdir(); (AR / "analytics").mkdir()
(AR / "status" / "QD-901.json").write_text(json.dumps({"id": "QD-901", "video": "vid901", "title": "x", "uploaded_at": "2026-10-24T10:00:00Z"}))
(AR / "boards" / "done" / "QD-901.json").write_text(json.dumps({"id": "QD-901", "category": "Science", "kind": "evergreen", **SB, "series_no": 3,
    "test": {"franchise": "series"}, "beats": [{"say": "Hello there"}], "meta": {"title": "t"}}))
real_root, A.ROOT = A.ROOT, AR
try: row = A.our_shorts()["vid901"]
finally: A.ROOT = real_root
assert A.SERIES_COLUMNS == ("series_name", "series_no", "series_kind")
assert (row["series_name"], row["series_no"], row["series_kind"], row["franchise"]) == ("Science Explained", 3, "evergreen", "series"), row
assert "+ tuple(OPENING_COLUMNS) + SERIES_COLUMNS}" in inspect.getsource(A)            # the shorts.csv row keys (after the opening columns)
print("11 analytics ok")

# 12. the writer end to end: a stubbed afternoon run writes two search-led evergreen Shorts as numbered series Shorts
SENT = ["Minecraft is the best-selling video game of all time with over 300 million copies sold.",
        "Grand Theft Auto V is second with more than 210 million copies sold.",
        "Tetris has sold around 100 million copies in its paid mobile versions alone.",
        "Wii Sports sold 82.9 million copies, mostly bundled with the Wii.",
        "PUBG: Battlegrounds has sold 75 million copies on PC and consoles.",
        "Mario Kart 8 and its Deluxe version together sold over 75 million copies."]
TEXT = (" ".join(SENT) + " ") * 3
PROMPTS = {"search": [], "write": [], "translate": []}
ASKED = []
ex = json.loads(W.example())


def fake(prompt, schema=None, timeout=100, temperature=0.1, lite=False, **kw):
    if prompt.startswith("You pick search-led"):
        PROMPTS["search"].append(prompt)
        return {"items": [{"idea": "Why is Minecraft so popular", "category": "Gaming", "wikipedia": "Minecraft", "appeal": 5, "from": 1},
                          {"idea": "Why is the sky blue", "category": "Science", "wikipedia": "Rayleigh scattering", "appeal": 4, "from": 3},
                          {"idea": "A third idea", "category": "Music", "wikipedia": "Music", "appeal": 5, "from": 2},
                          {"idea": "A weak idea", "category": "Film", "wikipedia": "Film", "appeal": 2, "from": 4}]}, "f"
    if prompt.startswith("You check facts for a family-friendly Shorts channel. The Short is about"):
        return {"what_is_new": "", "hooks": ["Number 1 sold 300 million"], "facts": [
            {"claim": x, "evidence": [{"source": 1, "quote": x}]} for x in SENT]}, "f"
    if prompt.startswith("Translate"):
        PROMPTS["translate"].append(prompt); return {}, "f"
    if prompt.startswith("You check a YouTube Short"): return {"ok": True}, "f"
    PROMPTS["write"].append(prompt)
    bd = json.loads(json.dumps(ex))
    bd["category"] = "Science" if "Why is the sky blue" in prompt else "Sport" if "Ballon" in prompt else "Gaming"      # the facts name Minecraft in both packs: the topic decides
    bd["meta"]["title"] = f"Test {len(PROMPTS['write'])} 🎮"
    return bd, "f"


F.gemini = fake
dd = json.loads(F.OUT.read_text()); dd["mode"] = "full"
PACK = json.loads(json.dumps(dd["topics"][0])); dd["topics"] = []                   # no news: the search-led Shorts are the run
F.OUT = SCRATCH / "facts_full.json"; F.OUT.write_text(json.dumps(dd))
F.page_text = lambda url, wiki=False: (TEXT, "")
S.own_terms = lambda root=None, n=12: [{"text": "why is minecraft so popular", "source": "our search traffic", "detail": "40 views"}]
S.suggest = lambda q, gl="GB", get=None, timeout=6: (ASKED.append(q), [f"{q} for kids", "why is the sky blue"])[1]
W.reserve_count = lambda: 9
W.recent = lambda days=14: []
W.hot, W.weak = (lambda: []), (lambda: [])
W.evergreen_packs = lambda *a, **k: []
W.angles = lambda topic: []                  # the YouTube search for angles: never from a test
FAKE_DAY = dt.date(2031, 3, 4)
W.plan = lambda breaking=False, hint="": ("afternoon", FAKE_DAY, 6)
first = {n: S.next_number(n) for n in ("Game Explained", "Science Explained")}
assert S.search_due(FAKE_DAY, "afternoon", 6) == 2
before = {p.name for p in pathlib.Path("boards/queue").glob("QD-*.json")}
new = []
try:
    W.main()
    new = sorted(p for p in pathlib.Path("boards/queue").glob("QD-*.json") if p.name not in before)
    got = [json.loads(p.read_text()) for p in new]
finally:
    for p in new: p.unlink()
    for p in pathlib.Path("boards/queue").glob("QD-*.json"):
        if p.name not in before: p.unlink()
assert len(got) == 2 and {x["series_name"] for x in got} == set(first), [x.get("series_name") for x in got]
for x in got:
    name = x["series_name"]
    assert x["series_no"] == first[name] and x["series_kind"] == "evergreen" and x["series_key"] == name and "series_of" not in x, x
    assert x["kind"] == "evergreen" and x["source"] == "Search-led" and x["test"]["franchise"] == "series" and "franchise" not in x
    assert x["meta"]["title"].startswith(f"{name} #{first[name]}: ") and len(x["meta"]["title"]) <= 70, x["meta"]["title"]
    assert V.check(x)[0] == [], V.check(x)[0]
    nodash(x["meta"]["title"], x["meta"].get("alt_title", ""))
assert PROMPTS["search"] and "THE SEARCHES" in PROMPTS["search"][0] and "[our search traffic, 40 views] why is minecraft so popular" in PROMPTS["search"][0]
assert "[YouTube search suggestions, " in PROMPTS["search"][0] and any(q.startswith("why does ") for q in ASKED)
assert any('NUMBERED SERIES: this Short joins our numbered series "Game Explained"' in p for p in PROMPTS["write"]), "the model is told about the series"
assert len(PROMPTS["translate"]) == 2 and not [p for p in PROMPTS["translate"] if "Explained" in p or "#" in p], "translated from the plain title"
assert S.search_due(FAKE_DAY, "afternoon", 6) == 2                                    # a dry run never uses up the day's places
W.plan = lambda breaking=False, hint="": ("morning", FAKE_DAY, 0)                     # no places, no search-led Shorts
assert S.search_due(FAKE_DAY, "morning", 0) == 0
print("12 writer run ok")

# 12b. a watchlist item with a playbook and ONE place a day: the day's angle ranks first, has a place of its own, is one Short even
#      when its series test drew two parts, and the item's main term still gets its place
S.PLAYBOOKS = PB
(SCRATCH / "w2").mkdir()
WT.STATE = SCRATCH / "w2" / "watch.json"
WT.STATE.write_text(json.dumps({"items": [{"name": EV, "level": "launch", "places": 1, "days_to": 1, "category": "Sport", "angles": ANG, "rules": ""}]}))
SIG = f"watchlist: {EV} (launch, 1 day to go)"
dd["topics"] = [{**PACK, "topic": EV, "signal": SIG, "category": "Sport"}, {**PACK, "topic": ANG[1], "signal": SIG, "category": "Sport"}]
F.OUT.write_text(json.dumps(dd))
assert W.series_joins(dd["topics"][1], "news") and not W.series_joins(dd["topics"][0], "news") and not W.series_joins(NEWS, "news")
assert W.series_joins(EVP, "evergreen") and not W.series_joins(EVP, "evergreen", True)
W.plan = lambda breaking=False, hint="": ("morning", FAKE_DAY, 6)
real_led, real_tp = W.search_led_run, W.test_plan
W.search_led_run = lambda *a, **k: []
W.test_plan = lambda k, kind="news", explore=False: (lambda st, t: (st, {**t, "series": "two parts"}))(*real_tp(k, kind, explore))
before = {p.name for p in pathlib.Path("boards/queue").glob("QD-*.json")}
new = []
try:
    W.main()
    new = sorted(p for p in pathlib.Path("boards/queue").glob("QD-*.json") if p.name not in before)
    got = [json.loads(p.read_text()) for p in new]
finally:
    W.search_led_run, W.test_plan = real_led, real_tp
    for p in pathlib.Path("boards/queue").glob("QD-*.json"):
        if p.name not in before: p.unlink()
assert len(got) == 2, [(x["id"], x["meta"]["title"]) for x in got]
angle, mainb = got
assert (angle["series_name"], angle["series_no"], angle["series_of"], angle["series_kind"], angle["series_key"]) == ("Ballon d'Or", 2, 5, "playbook", EV), angle
assert angle["meta"]["title"].startswith("Ballon d'Or #2: ") and angle["watch"] == EV and "series" not in angle and angle["test"]["franchise"] == "series"
assert "series_name" not in mainb and mainb["watch"] == EV and "series" not in mainb         # the main term: its own place, no number, not in parts either
assert any("MINI-SERIES: this is number 2 of 5" in p for p in PROMPTS["write"])
nodash(angle["meta"]["title"], angle["meta"].get("alt_title", ""))
print("12b playbook run ok")

# 13. playlists: a fake YouTube. One playlist per series (50 units), a public Short added in series order (50 units), the link in
#     its description once (50 units), every call through the allowance guard, nothing twice, passing errors retried
Q.ROOT, Q.DIR = SCRATCH / "q", SCRATCH / "q" / "status" / "quota"
(SCRATCH / "q" / "status").mkdir(parents=True)
Q.VOLUME_P, Q.LIMIT_P = SCRATCH / "volume.json", SCRATCH / "limit.json"
for label in ("series playlist", "series playlist add", "series description"): assert Q.bucket(label) is None      # shared units, not the upload or search buckets


class Req:
    def __init__(self, yt, name, kw): self.yt, self.name, self.kw = yt, name, kw
    def execute(self): return self.yt.handle(self.name, self.kw)


class Res:
    def __init__(self, yt, kind): self.yt, self.kind = yt, kind
    def __getattr__(self, method): return lambda **kw: Req(self.yt, f"{self.kind}.{method}", kw)


class FakeYT:
    def __init__(self, playlists=None):
        self.calls, self.pl, self.items, self.snip, self.fail = [], dict(playlists or {}), {}, {}, {}
    def playlists(self): return Res(self, "playlists")
    def playlistItems(self): return Res(self, "playlistItems")
    def videos(self): return Res(self, "videos")
    def handle(self, name, kw):
        self.calls.append((name, kw))
        if self.fail.get(name): raise self.fail[name].pop(0)
        if name == "playlists.list": return {"items": [{"id": i, "snippet": {"title": t}} for t, i in self.pl.items()]}
        if name == "playlists.insert":
            assert kw["body"]["status"]["privacyStatus"] == "public"
            pid = f"PL{len(self.pl) + 1}"; self.pl[kw["body"]["snippet"]["title"]] = pid; self.items[pid] = []; return {"id": pid}
        if name == "playlistItems.list": return {"items": [{"id": "x"}] if kw["videoId"] in self.items.get(kw["playlistId"], []) else []}
        if name == "playlistItems.insert":
            sn = kw["body"]["snippet"]; self.items.setdefault(sn["playlistId"], []).append(sn["resourceId"]["videoId"]); return {"id": "i"}
        if name == "videos.list": return {"items": [{"snippet": dict(self.snip.get(kw["id"]) or {"title": "T", "description": "Original", "categoryId": "24"})}]}
        if name == "videos.update": self.snip[kw["body"]["id"]] = dict(kw["body"]["snippet"]); return {}
        raise AssertionError(name)

    def made(self, name): return [kw for n, kw in self.calls if n == name]


NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
RP = SCRATCH / "repo"; (RP / "status").mkdir(parents=True)
PLP, PBP = RP / "status" / "playlists.json", PB                                  # the playlists file here, the playbooks from section 7


def short(sid, folder="done", publish="2026-10-20T10:00:00Z", video=None, engage=None, **fields):
    put(RP, folder, sid, **fields)
    st = {"id": sid, "video": video or f"vid{sid[-3:]}", "uploaded_at": "2026-10-19T10:00:00Z"}
    if publish: st["publish_at"] = publish
    if engage: st["engage"] = engage
    (RP / "status" / f"{sid}.json").write_text(json.dumps(st))


def sbd(name, no, key=None, **kw):
    return {"category": "Science", "series_name": name, "series_no": no, "series_kind": "evergreen", "series_key": key or name, **kw}


short("QD-201", **sbd("Science Explained", 1))
short("QD-202", **sbd("Science Explained", 2))
short("QD-203", publish="2099-01-01T10:00:00Z", **sbd("Game Explained", 1))                  # scheduled, not public yet
short("QD-204", category="Film")                                                           # in no series
short("QD-205", engage={"series_playlist": "PLOLD"}, **sbd("Science Explained", 3))        # already added
short("QD-206", publish=None, **sbd("Game Explained", 2))                                    # private: no publish time
short("QD-207", **dict(sbd("Ballon d'Or", 1, EV), series_kind="playbook", series_of=5, category="Sport"))
assert [x[1]["id"] for x in PL.waiting(RP, NOW)] == ["QD-207", "QD-201", "QD-202"]         # public, in a series, not added: by series, then number
assert PL.public({"publish_at": "2026-10-25T11:59:59Z"}, NOW) and not PL.public({"publish_at": "2026-10-25T12:00:01Z"}, NOW)
assert PL.public({"publish_at": "2026-10-25T12:30:00+01:00"}, NOW) and not PL.public({}, NOW) and not PL.public({"publish_at": "soon"}, NOW)
yt = FakeYT()
spent0 = Q.state()[0]
assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 3
assert [kw["body"]["snippet"]["title"] for kw in yt.made("playlists.insert")] == ["Ballon d'Or 2026 in 5 Shorts | Quickplay Daily", "Science Explained | Quickplay Daily"]
assert [kw["body"]["snippet"]["resourceId"]["videoId"] for kw in yt.made("playlistItems.insert")] == ["vid207", "vid201", "vid202"]
assert Q.state()[0] - spent0 == 2 * 50 + 3 * 50 + 3 * 50, Q.state()                       # two playlists, three adds, three descriptions
saved = PL.load(PLP)["playlists"]
assert set(saved) == {EV, "Science Explained"} and all(v["id"] and v["kind"] for v in saved.values()), saved
assert S.playlist_id("Science Explained", CFG, PLP) == saved["Science Explained"]["id"]
for sid, vid in (("QD-201", "vid201"), ("QD-202", "vid202"), ("QD-207", "vid207")):
    e = json.loads((RP / "status" / f"{sid}.json").read_text())["engage"]
    assert e["series_playlist"] and e["series_description"] == "linked" and "series_playlist_error" not in e, (sid, e)
    assert f"list={e['series_playlist']}" in yt.snip[vid]["description"] and yt.snip[vid]["description"].startswith("Original"), yt.snip[vid]
assert "Science Explained #1. More in the series: " in yt.snip["vid201"]["description"] and "Ballon d'Or #1 of 5. More in" in yt.snip["vid207"]["description"]
for sid in ("QD-203", "QD-204", "QD-206"): assert "engage" not in json.loads((RP / "status" / f"{sid}.json").read_text()), sid
assert json.loads((RP / "status" / "QD-205.json").read_text())["engage"] == {"series_playlist": "PLOLD"}
nodash(*(v["description"] for v in yt.snip.values()), *(kw["body"]["snippet"]["title"] for kw in yt.made("playlists.insert")))
n_calls = len(yt.calls)
assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 0 and len(yt.calls) == n_calls          # nothing twice, no calls at all
short("QD-208", **sbd("Science Explained", 4))                                              # the playlist exists and the render put the link in
yt.snip["vid208"] = {"title": "T", "description": f"Science Explained #4.\nMore in the series: {S.playlist_url('Science Explained', CFG, PLP)}", "categoryId": "24"}
spent1 = Q.state()[0]
assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 1
assert len(yt.made("playlists.insert")) == 2 and not yt.made("videos.update")[3:], "no second playlist, no second description edit"
assert Q.state()[0] - spent1 == 50                                                          # the add alone
assert yt.items[saved["Science Explained"]["id"]] == ["vid201", "vid202", "vid208"], yt.items

# a passing error is tried again (and never adds a Short twice); any other error is final; three tries at most
short("QD-209", **sbd("Science Explained", 5)); short("QD-210", **sbd("Science Explained", 6))
yt.fail["playlistItems.insert"] = [OSError("HttpError 503 backendError"), PermissionError("HttpError 403 forbidden")]
assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 0
e209 = json.loads((RP / "status" / "QD-209.json").read_text())["engage"]; e210 = json.loads((RP / "status" / "QD-210.json").read_text())["engage"]
assert e209["series_playlist_tries"] == 1 and "503" in e209["series_playlist_error"] and "series_playlist" not in e209, e209
assert e210["series_playlist_tries"] == 1 and "403" in e210["series_playlist_error"]
n_ins = len(yt.made("playlistItems.insert"))
assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 1                               # the 503 is tried again, the 403 is not
e209 = json.loads((RP / "status" / "QD-209.json").read_text())["engage"]
assert e209["series_playlist"] and "series_playlist_error" not in e209 and "series_playlist_tries" not in e209
assert len(yt.made("playlistItems.insert")) == n_ins + 1 and len(yt.made("playlistItems.list")) >= 1       # the retry checked the playlist first
assert PL.tries({}, "k") == 0 and PL.tries({"k_error": "HttpError 503 x", "k_tries": 2}, "k") == 2
assert PL.tries({"k_error": "HttpError 503 x", "k_tries": 3}, "k") is None and PL.tries({"k_error": "HttpError 403 x", "k_tries": 1}, "k") is None

# the allowance guard refuses: nothing is called, nothing recorded, the next run tries again
short("QD-211", **sbd("Science Explained", 7))
real_allow, Q.allow = Q.allow, (lambda units, what="extra": False)
n_calls = len(yt.calls)
try: assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 0 and len(yt.calls) == n_calls
finally: Q.allow = real_allow
assert "engage" not in json.loads((RP / "status" / "QD-211.json").read_text())
assert PL.run(yt, RP, PLP, CFG, now=NOW, playbooks=PBP) == 1

# a playlist with the title already on the channel is reused (a run that died after the insert), a hand-set id wins, 12 adds a run
yt2 = FakeYT({"Science Explained | Quickplay Daily": "PLEXIST"})
spec = PL.spec_for(sbd("Science Explained", 1), CFG)
assert spec["title"] == "Science Explained | Quickplay Daily" and spec["kind"] == "evergreen" and PL.spec_for({"category": "Film"}, CFG) is None
assert PL.ensure(yt2, spec, SCRATCH / "fresh.json", CFG) == "PLEXIST" and not yt2.made("playlists.insert")
assert PL.load(SCRATCH / "fresh.json")["playlists"]["Science Explained"]["id"] == "PLEXIST"
yt3 = FakeYT()
hand = {"series": [{"name": "Science Explained", "category": "Science", "playlist": "PLHAND"}]}
assert PL.ensure(yt3, spec, SCRATCH / "none.json", hand) == "PLHAND" and not yt3.calls
assert PL.spec_for(dict(sbd("Ballon d'Or", 1, EV), series_kind="playbook"), CFG, PBP)["title"] == "Ballon d'Or 2026 in 5 Shorts | Quickplay Daily"
for i in range(15): short(f"QD-3{i:02d}", **sbd("Cars Explained", i + 1, category="Cars"))
yt4 = FakeYT()
assert PL.run(yt4, RP, PLP, CFG, now=NOW, playbooks=PBP) == 12 and PL.run(yt4, RP, PLP, CFG, now=NOW, playbooks=PBP) == 3
print("13 playlists ok")

# 14. engage.py: the creator comment names the series and links the playlist; the hourly run adds the Shorts (no Google libraries here)
Y = types.ModuleType("youtube"); Y.utc = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
sys.modules["youtube"] = Y
import engage as E
S.PLAYLISTS = PL.STATE = STATUS / "playlists_engage.json"
yt5 = FakeYT()
text = E.comment_for(yt5, SB, "Which planet would you visit?")
assert text.startswith("Which planet would you visit?") and "Science Explained #12." in text and "The whole series: https://www.youtube.com/playlist?list=PL1" in text, text
assert len(yt5.made("playlists.insert")) == 1 and E.comment_for(yt5, SB, "Again?").count("list=PL1") == 1 and len(yt5.made("playlists.insert")) == 1
assert E.comment_for(yt5, {"category": "Film"}, "Plain?") == "Plain?" and len(E.comment_for(yt5, SB, "q" * 900)) <= 500
yt6 = FakeYT(); yt6.fail["playlists.list"] = [OSError("boom")]
S.PLAYLISTS = PL.STATE = STATUS / "playlists_broken.json"
text = E.comment_for(yt6, SB, "Which planet?")                                              # the playlist call fails: the comment still goes, without the link
assert "Science Explained #12." in text and "playlist?list" not in text, text
S.PLAYLISTS = PL.STATE = STATUS / "playlists_run.json"
PL.ROOT = RP / "run"; (PL.ROOT / "status").mkdir(parents=True)
real_run_root = RP
put(PL.ROOT, "done", "QD-701", **sbd("Science Explained", 1))
(PL.ROOT / "status" / "QD-701.json").write_text(json.dumps({"id": "QD-701", "video": "vid701", "publish_at": "2026-10-20T10:00:00Z"}))
yt7 = FakeYT(); E.client = lambda: yt7
E.series_playlists()
assert json.loads((PL.ROOT / "status" / "QD-701.json").read_text())["engage"]["series_playlist"] == "PL1" and yt7.items["PL1"] == ["vid701"]
E.client = lambda: None; E.series_playlists()                                              # no second sign-in yet: nothing happens
src = (pathlib.Path(REPO_DIR) / "pipeline" / "engage.py").read_text()
assert "try: series_playlists()" in src and src.index("series_playlists()") < src.index("try: replies()"), "the hourly run adds the Shorts"
print("14 engage ok")
print("series ok")
