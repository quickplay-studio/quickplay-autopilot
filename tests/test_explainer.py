"""Offline test of the Wednesday explainer (pipeline/explainer.py), stubs only: no model, voice, network or YouTube is touched.
1. dates: the Wednesday a build is for, 19:00 UK in UTC (GMT and BST), when a run is due (first 28 October 2026, never twice)
2. the week's subjects from analytics/shorts.csv, joined when they are one story; the fact packs and their sources
3. the script: cleaning, every rule of check_script, the fix rounds and the second fact check (stubbed model)
4. beats, the voice's re-reads, the timeline, picture selection, fact cards, the shots of the video
5. a real small render (PIL frames piped to ffmpeg) and the whole build with stubbed voice and pictures
6. the description (chapters, sources, credits, the length budget), the upload and the status file
7. the links to the Shorts (description, creator comment) and the long-form watch hours (analytics/longform.csv, the ledger)
8. weekly.yml: two jobs, the model keys only in the build, the YouTube keys only in the upload"""
import contextlib, csv, datetime as dt, io, json, os, pathlib, random, shutil, subprocess, sys, tempfile, types
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
import explainer as X

UTC = dt.timezone.utc
TMP = pathlib.Path(tempfile.mkdtemp(prefix="qp-explainer-"))
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FP = {"display": DEJAVU, "body": DEJAVU}
NOW = dt.datetime(2026, 10, 28, 8, 40, tzinfo=UTC)
DASHES = "\u2013\u2014"


def fresh(name):
    d = TMP / name; shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True); return d


@contextlib.contextmanager
def quiet():
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf): yield
    except BaseException:
        sys.stdout.write(buf.getvalue()[-3000:]); raise


@contextlib.contextmanager
def stubbed(**mods):
    old = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try: yield
    finally:
        for k, v in old.items():
            if v is None: sys.modules.pop(k, None)
            else: sys.modules[k] = v


def raises(exc, fn, *a, **k):
    try: fn(*a, **k)
    except exc as e: return e
    raise AssertionError(f"{fn.__name__} did not raise {exc.__name__}")


# 1. dates ---------------------------------------------------------------------------------------------------------------
assert X.target_day(dt.date(2026, 10, 28)) == dt.date(2026, 10, 28)
assert X.target_day(dt.date(2026, 10, 25)) == dt.date(2026, 10, 28)           # a Sunday looks ahead to Wednesday
assert X.target_day(dt.date(2026, 10, 29)) == dt.date(2026, 11, 4)
assert X.FIRST == dt.date(2026, 10, 28) and X.FIRST.weekday() == 2
d28 = dt.date(2026, 10, 28)
assert X.publish_time(d28, dt.datetime(2026, 10, 28, 5, 10, tzinfo=UTC)) == dt.datetime(2026, 10, 28, 19, 0, tzinfo=UTC)   # GMT
assert X.publish_time(dt.date(2027, 6, 2), dt.datetime(2027, 6, 2, 5, 10, tzinfo=UTC)) == dt.datetime(2027, 6, 2, 18, 0, tzinfo=UTC)   # BST
assert X.publish_time(d28, dt.datetime(2026, 10, 28, 18, 15, tzinfo=UTC)).hour == 19                  # 45 minutes ahead is enough
for h, m in ((18, 16), (18, 30), (19, 50), (20, 15), (23, 40)):                                         # a late retry: the next full hour
    now = dt.datetime(2026, 10, 28, h, m, tzinfo=UTC)
    p = X.publish_time(d28, now)
    assert p.minute == 0 and p >= now + dt.timedelta(minutes=45) and p - now < dt.timedelta(hours=2), (h, m, p)
assert X.stamp(5) == "0:05" and X.stamp(62) == "1:02" and X.stamp(3725) == "1:02:05"

root = X.ROOT = fresh("due")
wed_early = dt.datetime(2026, 10, 28, 5, 10, tzinfo=UTC)
assert X.due(wed_early)[:2] == (True, "live")
assert X.due(dt.datetime(2026, 10, 25, 10, 0, tzinfo=UTC))[:2] == (True, "live")                       # Sunday: the coming Wednesday
assert X.due(dt.datetime(2026, 10, 21, 5, 10, tzinfo=UTC))[0] is False                                 # before the first explainer
assert X.due(wed_early, "push", "dry\n")[:2] == (True, "dry")
assert X.due(wed_early, "push", "now")[:2] == (True, "live")
assert X.due(wed_early, "push", "")[0] is False and X.due(wed_early, "push", "later")[0] is False
(root / "status").mkdir()
(root / "status" / "weekly-2026-10-28.json").write_text(json.dumps({"kind": "explainer", "state": "skipped: no model answered"}))
assert X.due(wed_early)[0] is True, "a skipped week is built again by the next run"
(root / "status" / "weekly-2026-10-28.json").write_text(json.dumps({"kind": "explainer", "video": "abc123", "state": "scheduled"}))
go, mode, why = X.due(wed_early)
assert go is False and "abc123" in why, "a scheduled week is never built twice"
assert X.due(wed_early, "push", "dry")[0] is True, "a dry test still runs"
(root / "config.json").write_text(json.dumps({"explainer": {"enabled": False}}))
assert X.due(wed_early, "push", "dry")[0] is False and X.due(dt.datetime(2026, 11, 4, 5, 10, tzinfo=UTC))[0] is False
(root / "config.json").write_text("{}")
buf = io.StringIO()
with contextlib.redirect_stdout(buf): assert X.main(["due"]) == 0
assert buf.getvalue().startswith("go=") and "mode=" in buf.getvalue() and "why=" in buf.getvalue()


# 2. subjects ------------------------------------------------------------------------------------------------------------
def row(i, title, views, days_ago=1.5):
    return {"short": f"QD-{i:03d}", "title": title, "yt_views": str(views), "posted": (NOW - dt.timedelta(days=days_ago)).isoformat(),
            "youtube_url": f"https://youtube.com/shorts/VID{i:03d}"}


def board(hashtags, tags, category="Music"):
    return {"category": category, "meta": {"hashtags": hashtags, "tags": tags}}


BOARDS = {"QD-001": board(["#TateMcRae", "#Shorts"], ["tate mcrae", "sports car"]), "QD-002": board(["#TateMcRae"], ["tate mcrae"]),
          "QD-003": board(["#Queen", "#BohemianRhapsody"], ["queen"]), "QD-004": board(["#BohemianRhapsody", "#Queen"], ["bohemian rhapsody"]),
          "QD-005": board(["#Jailer2"], ["jailer 2"], "Film"), "QD-006": board(["#HollowKnight"], ["hollow knight"], "Gaming"),
          "QD-007": board(["#Oasis"], ["oasis"])}
ROWS = [row(1, "Tate McRae is back", 5000), row(2, "Tate McRae sold out", 3000), row(3, "Queen at Live Aid", 4000),
        row(4, "Bohemian Rhapsody turns fifty", 2500), row(5, "Jailer 2 is coming", 1000), row(6, "Hollow Knight news", 900),
        row(7, "Oasis tickets", 99999, days_ago=10), dict(row(8, "A test", 77777), short="TEST-1")]
picks = X.pick_subjects(ROWS, BOARDS.get, NOW)
assert [s["name"] for s in picks] == ["Tate McRae", "Queen", "Jailer 2"], [s["name"] for s in picks]     # Oasis is too old, TEST-1 is no Short
assert [s["views"] for s in picks] == [8000, 6500, 1000]
assert [s["id"] for s in picks[1]["shorts"]] == ["QD-003", "QD-004"], "#Queen and #BohemianRhapsody are one story"
assert picks[0]["shorts"][0]["video"] == "VID001" and picks[0]["category"] == "Music"
assert X.pick_subjects(ROWS, BOARDS.get, NOW, n=2)[1]["name"] == "Queen" and len(X.pick_subjects([], BOARDS.get, NOW)) == 0
assert X.spaced("#TateMcRae") == "Tate McRae" and X.spaced("Jailer2") == "Jailer 2" and X.spaced("BABYMONSTER") == "BABYMONSTER"
assert X.subject_of({}, "Tate McRae just dropped a new song")[0] == "Tate McRae"
assert X.subject_of({"meta": {"tags": ["hollow knight"]}})[0] == "Hollow Knight"
assert X.subject_of({"meta": {"hashtags": ["#Shorts", "#fyp"], "tags": ["sports car"]}})[0] == "Sports Car"

# packs: sources renumbered across a subject's Shorts, duplicates joined, unsourced and non-https facts out, trends added
B1 = {"category": "Music", "meta": {"summary": "Tate McRae is back \u2014 with a hit.",
      "sources": [["Official Charts: Sports Car", "https://www.officialcharts.com/a"], ["BBC News: tour", "https://www.bbc.co.uk/b"],
                  ["Insecure", "http://insecure.example/c"]],
      "facts": [["Tate McRae released the single Sports Car in 2025", [1, 2]], ["The song reached number one in the UK", [1]],
                ["A fact only the insecure source gives", [3]], ["A fact with no source", []], "not a fact", ["Short pair", "x"]]}}
B2 = {"category": "Music", "meta": {"sources": [["Official Charts: Sports Car", "https://www.officialcharts.com/a"], ["Billboard: Tate", "https://www.billboard.com/d"]],
      "facts": [["Tate McRae released the single Sports Car in 2025.", [1]], ["She toured Europe and the UK in 2025 \u2014 a long run", [2]],
                ["Her album has 14 tracks", [2]]]}}
bo = {"QD-001": B1, "QD-002": B2}.get
sub = {"key": "tatemcrae", "name": "Tate McRae", "views": 8000, "category": "Music", "keys": ["tatemcrae", "sportscar"],
       "shorts": [{"id": "QD-001", "title": "Tate McRae is back", "views": 5000, "video": "VID001"},
                  {"id": "QD-002", "title": "Tate McRae sold out", "views": 3000, "video": "VID002"}]}
topics = [{"topic": "Tate McRae Sports Car chart run", "sources": [["NME: chart", "https://www.nme.com/e"]],
           "verified": [{"claim": "Sports Car spent six weeks in the top ten", "sources": [1]}, {"claim": "No source here", "sources": []}]},
          {"topic": "Something unrelated", "sources": [["X: y", "https://x.example/z"]], "verified": [{"claim": "Unrelated fact", "sources": [1]}]}]
pk = X.build_packs([sub], bo, topics)[0]
claims = [f["claim"] for f in pk["facts"]]
assert pk["id"] == "A" and [f["id"] for f in pk["facts"]] == ["A1", "A2", "A3", "A4", "A5"], claims
assert claims[0] == "Tate McRae released the single Sports Car in 2025" and pk["facts"][0]["sources"] == [1, 2], "the best supported fact first"
assert not any("insecure" in c or "no source" in c.lower() or "Unrelated" in c for c in claims)
assert any(c.startswith("She toured Europe and the UK in 2025, a long run") for c in claims), "dashes become commas"
assert "Sports Car spent six weeks in the top ten" in claims
assert [s["n"] for s in pk["sources"]] == list(range(1, len(pk["sources"]) + 1)) and all(s["url"].startswith("https://") for s in pk["sources"])
assert all(n <= len(pk["sources"]) for f in pk["facts"] for n in f["sources"]) and len(pk["sources"]) == 4
assert pk["summaries"] == ["Tate McRae is back, with a hit."]
txt = X.pack_text([pk])
assert txt.startswith("STORY A: Tate McRae (Music; 8,000 views") and "A1 (2 sources): Tate McRae released" in txt


# 3. the script -----------------------------------------------------------------------------------------------------------
def mk_board(sid, hashtags, tags, category, claims, summary="A summary."):
    return {"id": sid, "category": category, "meta": {"hashtags": hashtags, "tags": tags, "summary": summary,
            "sources": [[f"Outlet {i}: {sid} story", f"https://example.com/{sid}/{i}"] for i in (1, 2, 3)],
            "facts": [[c, [1 + k % 3, 1 + (k + 1) % 3]] for k, c in enumerate(claims)]}}


TATE = ["Tate McRae released the single Sports Car in 2025", "Sports Car reached number one in the UK singles chart",
        "She toured arenas across Europe and the UK in 2025", "The song was written with a team of songwriters",
        "Her album So Close to What has 14 tracks"]
QUEEN = ["Queen formed in London in 1970", "Bohemian Rhapsody lasts nearly six minutes", "The song was released as a single in 1975",
         "It spent nine weeks at number one in the UK", "Freddie Mercury wrote the song"]
JAILER = ["Jailer 2 is the sequel to the film Jailer", "The film stars Rajinikanth", "It is a Tamil language action film",
          "Production began in 2025", "The first film was released in 2023"]
FILLER = ["People have been searching for it all week, and the reasons are easy to see.",
          "It is the sort of story that starts small and then spreads from one person to the next.",
          "Here is what makes it interesting, one detail at a time.", "The details matter, so it helps to take them slowly and in order.",
          "Fans noticed the change first, and then everyone else caught up.", "That is why so many people wanted a clear answer.",
          "It also shows how a single idea can travel a long way in a short time.", "Put together, those details explain why the story kept growing."]


def write_fixture(root, third=True):
    for d in ("analytics", "boards/done", "trends", "status"): (root / d).mkdir(parents=True, exist_ok=True)
    specs = [(101, ["#TateMcRae"], ["tate mcrae"], "Music", TATE[:3], 5000), (102, ["#TateMcRae"], ["tate mcrae"], "Music", TATE[3:], 3000),
             (103, ["#Queen", "#BohemianRhapsody"], ["queen"], "Music", QUEEN[:3], 4000),
             (104, ["#BohemianRhapsody", "#Queen"], ["bohemian rhapsody"], "Music", QUEEN[3:], 2500)]
    if third: specs += [(105, ["#Jailer2"], ["jailer 2"], "Film", JAILER, 2000), (106, ["#HollowKnight"], ["hollow knight"], "Gaming", ["Hollow Knight is a game"], 900)]
    rows = []
    for i, tags, phrases, cat, cl, views in specs:
        sid = f"QD-{i}"
        (root / "boards" / "done" / f"{sid}.json").write_text(json.dumps(mk_board(sid, tags, phrases, cat, cl)))
        rows.append({"short": sid, "title": f"{phrases[0].title()} short {i}", "yt_views": views, "posted": (NOW - dt.timedelta(days=2)).isoformat(),
                     "youtube_url": f"https://youtube.com/shorts/V{i}"})
    with open(root / "analytics" / "shorts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["short", "title", "yt_views", "posted", "youtube_url"]); w.writeheader(); w.writerows(rows)


def story_text(name, claims, words):
    sents = [f"{name} is the next story of the week."] + [c.rstrip(".") + "." for c in claims]
    i = 0
    while sum(len(s.split()) for s in sents) < words: sents.append(FILLER[i % len(FILLER)]); i += 1
    return " ".join(sents)


def good_raw(packs):
    names = ", ".join(p["name"] for p in packs[:-1]) + f" and {packs[-1]['name']}"
    secs = [{"chapter": "The week in three stories", "subject": "", "pictures": [packs[0]["name"]], "uses": [],
             "narration": f"{names} are the three stories people searched for most this week. " + " ".join(FILLER[:7])}]
    for p in packs:
        secs.append({"chapter": f"The story of {p['name']}", "subject": p["id"], "pictures": [p["name"], "Wembley Stadium"],
                     "uses": [f["id"] for f in p["facts"][:3]], "narration": story_text(p["name"], [f["claim"] for f in p["facts"][:5]], 290)})
    secs.append({"chapter": "What links them", "subject": "", "pictures": [p["name"] for p in packs], "uses": [],
                 "narration": "One way to read it is that all three stories grew from a single detail. " + " ".join(FILLER * 2)[:1200]})
    secs.append({"chapter": "Until next Wednesday", "subject": "", "pictures": [packs[1]["name"]], "uses": [],
                 "narration": "That is the week in three stories. " + " ".join(FILLER[:4]) + " There is a new explainer every Wednesday and a Short every day, so subscribe to Quickplay Daily."})
    return {"title": f"{packs[0]['name']}, {packs[1]['name']} and {packs[2]['name']} explained", "description": "The three stories people searched for most this week, in plain words.",
            "tags": ["weekly explainer", "tate mcrae", "queen", "jailer 2"], "sections": secs}


FIXR = X.ROOT = fresh("fixture"); write_fixture(FIXR)
SUBS = X.pick_subjects(X.shorts_rows(), X.board_of, NOW, n=6)
assert [s["name"] for s in SUBS][:3] == ["Tate McRae", "Queen", "Jailer 2"], [s["name"] for s in SUBS]
PACKS = X.build_packs(SUBS[:3], X.board_of)
assert all(len(p["facts"]) == 5 for p in PACKS) and PACKS[0]["facts"][0]["id"] == "A1" and PACKS[2]["facts"][4]["id"] == "C5"
GOOD = X.clean_script(good_raw(PACKS), PACKS)
errs, warns = X.check_script(GOOD, PACKS, 2026)
assert errs == [], errs
words = sum(X.word_count(s["narration"]) for s in GOOD["sections"])
assert 1000 <= words <= 1450 and len(GOOD["sections"]) == 6 and len(GOOD["title"]) < 70, words

# clean_script: UK dates and spelling, no dashes, hashtags or links, the subject inferred from the facts a section uses
cs = X.clean_script({"title": "A title \u2014 with #hashtag", "tags": ["one \u2013 two", 5, ""], "sections": [
    {"chapter": "Colour", "narration": "It came out on October 20, 2025. The color was gray (see www.x.com). Visit https://x.example now \U0001F600 *really*.",
     "uses": ["B1", "B2", "A1"], "pictures": "Freddie Mercury"}, {"title": "Second", "text": "More.", "subject": "z", "facts": "C1, C2"}, "junk",
    {"narration": "No subject.", "uses": ["A1", "B1"]}]}, PACKS)
s0 = cs["sections"][0]
assert cs["title"] == "A title, with" and cs["tags"] == ["one, two"], cs
assert "20 October 2025" in s0["narration"] and "colour" in s0["narration"] and "grey" in s0["narration"]
assert "http" not in s0["narration"] and "www" not in s0["narration"] and "*" not in s0["narration"] and "\U0001F600" not in s0["narration"]
assert s0["subject"] == "B" and s0["uses"] == ["B1", "B2", "A1"] and s0["pictures"] == ["Freddie Mercury"]
assert cs["sections"][1]["subject"] == "C" and cs["sections"][1]["narration"] == "More." and cs["sections"][1]["chapter"] == "Second"
assert cs["sections"][2]["subject"] == "", "a tie between stories names none"
assert not any(c in json.dumps(cs, ensure_ascii=False) for c in DASHES)
assert X.clean_script(None, PACKS) == {"title": "", "description": "", "sections": [], "tags": []}

# check_script: every rule has a failing case
import copy


def broken(fn):
    sc = copy.deepcopy(GOOD); fn(sc); return X.check_script(sc, PACKS, 2026)[0]


def has(errs, text): return any(text in e for e in errs)


assert has(broken(lambda s: s.update(title="Short")), "title")
assert has(broken(lambda s: s.update(title="x" * 80)), "title")
assert has(broken(lambda s: s["sections"].pop(1)), "story A (Tate McRae) has no section of its own")
assert has(broken(lambda s: s["sections"].__delitem__(slice(3, 5))), "sections: 4 given")
assert has(broken(lambda s: s["sections"][1].update(narration="Tate McRae. Short.")), "too short")
assert has(broken(lambda s: s["sections"][2].update(narration=s["sections"][2]["narration"] + " Queen " * 200)), "too long")
assert has(broken(lambda s: [x.update(narration=x["narration"][:400]) for x in s["sections"]]), "words in all")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " It sold 4,321 copies in 1987.")), "numbers that are not in the facts")
assert not has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " It sold 2025 copies in ten days.")), "numbers")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " On October 20 it changed.")), "UK order")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " Today it is everywhere.")), "never say today")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " Tomorrow brings more.")), "tomorrow")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " I think it is great.")), "no 'I'")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " We said so. We saw it. We know. We agree.")), "'we'")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " Then the election began.")), "excluded topic")
assert has(broken(lambda s: s["sections"][1].update(narration=s["sections"][1]["narration"] + " According to Wikipedia it is true.")), "Wikipedia")
assert has(broken(lambda s: s["sections"][1].update(uses=["A1", "Z9"])), "do not exist")
assert has(broken(lambda s: s["sections"][2].update(narration=s["sections"][2]["narration"].replace("Queen", "The band").replace("Bohemian", "The"))), "story B")
assert has(broken(lambda s: s["sections"][3].update(subject="B")), "story C") and has(broken(lambda s: s["sections"][3].update(chapter="Hi")), "chapter title")
assert has(broken(lambda s: [x.update(subject="") for x in s["sections"]]), "no section has a subject letter")
assert not has(broken(lambda s: s["sections"][2].update(narration=s["sections"][2]["narration"] + " Police said.")), "excluded"), "a watch word is only a warning"
assert any("police" in w for w in X.check_script(dict(copy.deepcopy(GOOD), description="Police said this week's three stories."), PACKS, 2026)[1])


# write_script: the model chain is stubbed; the fix rounds and the second fact check
class Ask:
    def __init__(self, scripts, unsupported=(), check_error=None):
        self.scripts, self.unsupported, self.check_error, self.calls = list(scripts), list(unsupported), check_error, []

    def __call__(self, prompt, temperature=0.5, check=False):
        self.calls.append(("check" if check else "write", prompt))
        if check:
            if self.check_error: raise self.check_error
            return {"unsupported": self.unsupported.pop(0) if self.unsupported else []}, "stub-check"
        s = self.scripts.pop(0) if len(self.scripts) > 1 else self.scripts[0]
        if isinstance(s, Exception): raise s
        return s, "stub-writer"


RAW = good_raw(PACKS)
ask = Ask([RAW])
sc, info = X.write_script(PACKS, ask=ask, day=dt.date(2026, 10, 28))
assert info["rounds"] == 0 and info["model"] == "stub-writer" and info["fact_check"] == "stub-check: passed" and sc == GOOD
assert [c[0] for c in ask.calls] == ["write", "check"] and "STORY A: Tate McRae" in ask.calls[0][1] and "A1:" in ask.calls[1][1]
short = copy.deepcopy(RAW); short["sections"][1]["narration"] = "Tate McRae is back."
ask = Ask([short, RAW])
sc, info = X.write_script(PACKS, ask=ask)
assert info["rounds"] == 1 and [c[0] for c in ask.calls] == ["write", "write", "check"] and "PROBLEMS" in ask.calls[1][1] and "too short" in ask.calls[1][1]
ask = Ask([RAW], unsupported=[[{"sentence": "Queen sold ten million copies.", "why": "no such fact"}], []])
sc, info = X.write_script(PACKS, ask=ask)
assert info["rounds"] == 1 and 'not supported by the facts: "Queen sold ten million copies."' in ask.calls[2][1]
e = raises(X.ScriptError, X.write_script, PACKS, ask=Ask([short]))
assert "problems left" in str(e)
e = raises(X.ScriptError, X.write_script, PACKS, ask=Ask([RuntimeError("boom")]))
assert "no model answered" in str(e)
e = raises(X.ScriptError, X.write_script, PACKS, ask=Ask([RAW], check_error=RuntimeError("quota")))
assert "fact check could not run" in str(e)
e = raises(X.ScriptError, X.write_script, PACKS, ask=Ask([RAW], unsupported=[[{"sentence": "x y z"}]] * 3), rounds=1)
assert "not supported" in str(e)

# pictures searches per section
sc2 = {"sections": [{"subject": "A", "pictures": ["Donald Trump White House", "tate mcrae", "Sports  Car", "sports car", "x", "Arena"]},
                    {"subject": "", "pictures": ["Wembley Stadium"]}]}
X.ensure_pictures(sc2, PACKS)
assert sc2["sections"][0]["pictures"] == ["Tate McRae", "Sports Car", "Arena"], sc2["sections"][0]["pictures"]
assert sc2["sections"][1]["pictures"] == ["Tate McRae", "Queen", "Jailer 2", "Wembley Stadium"]


# 4. beats, the voice, the timeline ----------------------------------------------------------------------------------------
assert X.sentences("Hello there. World is big. 3 men came.") == ["Hello there.", "World is big.", "3 men came."]
text = ("Mr. Smith met Dr. Jones at 5 p.m. on Tuesday. They talked for an hour. Yes. Then the long sentence follows and it keeps going with many "
        "words so that it has to be split somewhere near the middle because the voice model garbles anything longer than twenty six words in one go, "
        "which would be a problem.")
bt = X.split_beats([{"narration": text}, {"narration": "Second section here."}])
assert all(b["words"] <= X.BEAT_WORDS for b in bt) and bt[-1]["sec"] == 1 and all(b["text"][-1] in ".!?" for b in bt)
assert bt[0]["text"].startswith("Mr. Smith met Dr. Jones") and any("Yes." in b["text"] and "hour" in b["text"] for b in bt), [b["text"] for b in bt]
import re
tok = lambda s: re.findall(r"[a-z']+", s.lower())
assert tok(" ".join(b["text"] for b in bt if b["sec"] == 0)) == tok(text), "splitting loses no word"
assert len([b for b in bt if b["sec"] == 0]) == 4, [b["text"] for b in bt]
assert [b["text"] for b in X.split_beats([{"narration": "A short one."}])] == ["A short one."]

# run_tts: unclear beats are read again with another seed and the clearer read kept
work = fresh("tts")
tb = [{"text": "One two three four five six seven eight nine ten.", "words": 10}, {"text": "Unclear words here for me.", "words": 8},
      {"text": "Ok.", "words": 2}, {"text": "A good beat with plenty of words in it.", "words": 12}]
calls = []


def fake_sh(*cmd, cwd=None, timeout=None):
    cmd = [str(c) for c in cmd]; calls.append(cmd)
    out = pathlib.Path(cmd[3]); out.mkdir(parents=True, exist_ok=True)
    again = "--seed" in cmd
    idx = [int(x) for x in cmd[cmd.index("--beats") + 1].split(",")] if "--beats" in cmd else range(len(tb))
    man = {"beats": []}
    for i in idx:
        (out / f"cb_b{i:02d}.wav").write_bytes(b"new" if again else b"old")
        man["beats"].append({"beat": i, "file": f"cb_b{i:02d}.wav", "dur": 1.0, "text": "", "recall": 0.9 if again else {1: 0.1, 2: 0.2}.get(i, 0.95)})
    (out / "cb_manifest.json").write_text(json.dumps(man))


with quiet(): vdir, vman = X.run_tts(tb, work, sh=fake_sh)
assert len(calls) == 2 and "--seed" in calls[1] and calls[1][calls[1].index("--beats") + 1] == "1", calls[1]    # beat 2 has under 4 words: not read again
assert (vdir / "cb_b01.wav").read_bytes() == b"new" and (vdir / "cb_b02.wav").read_bytes() == b"old" and (vdir / "cb_b00.wav").read_bytes() == b"old"
assert vman["unclear"] == [] and "--voice" in calls[0] and calls[0][calls[0].index("--voice") + 1] == "F2"
assert json.loads((work / "voice_board.json").read_text())["beats"][1] == {"say": "Unclear words here for me."}
work = fresh("tts2"); calls.clear()


def failing_sh(*cmd, cwd=None, timeout=None):
    if "--seed" in [str(c) for c in cmd]: raise RuntimeError("tts crashed")
    fake_sh(*cmd, cwd=cwd, timeout=timeout)


with quiet(): vdir, vman = X.run_tts(tb, work, sh=failing_sh)
assert vman["unclear"] == [1], "a failed re-read keeps the first read"

# the timeline
B3 = [{"sec": 0}, {"sec": 0}, {"sec": 1}]
lay = X.layout(B3, [3.0, 2.0, 4.0])
assert [round(x, 2) for x in lay["starts"]] == [0.5, 3.82, 7.32], lay["starts"]
assert [(s["index"], round(s["start"], 2), round(s["end"], 2)) for s in lay["sec"]] == [(0, 0.0, 6.72), (1, 6.72, 12.52)], lay["sec"]
assert round(lay["end_card"], 2) == 12.52 and round(lay["total"], 2) == 18.52


# pictures: unreadable and tiny files out, near-duplicates once, caps by section and by the description's credit room
from PIL import Image


def make_img(path, seed, size=(800, 500)):
    r = random.Random(seed)
    im = Image.new("L", (8, 8)); im.putdata([r.randrange(256) for _ in range(64)])
    im.resize(size, Image.NEAREST).convert("RGB").save(path)
    return str(path)


PD = fresh("pics")
img = {i: make_img(PD / f"p{i}.png", i) for i in range(1, 10)}
shutil.copy(img[2], PD / "p2copy.png")
make_img(PD / "tiny.png", 99, size=(300, 200))
(PD / "broken.png").write_bytes(b"not a picture")


def pic(path, rel=None, credit="Photo: X, CC BY 4.0, via Wikimedia Commons"):
    return {"path": str(path), "credit": credit, "source": "https://commons.wikimedia.org/wiki/File:" + pathlib.Path(path).name, "relevance": rel}


assert X.ahash(PD / "tiny.png") is None and X.ahash(PD / "broken.png") is None and X.ahash(img[1]) is not None
assert X.ahash(img[2]) == X.ahash(PD / "p2copy.png") and X.ahash(img[1]) != X.ahash(img[3])
found = {0: [pic(img[1], .9), pic(img[2], .8), pic(PD / "p2copy.png"), pic(PD / "tiny.png"), pic(PD / "broken.png")],
         1: [pic(img[1], .9), pic(img[3], .9), pic(img[4], .2), pic(img[5], .8), pic(img[6], .7), pic(img[7], .6)]}
sel = X.select_pictures(found, max_total=100, per_section=4, credit_room=10000)
assert [p["path"] for p in sel[0]] == [img[1], img[2]] and [p["path"] for p in sel[1]] == [img[3], img[4], img[5], img[6]], sel
sel = X.select_pictures(found, max_total=5, per_section=4, credit_room=10000)
assert sum(len(v) for v in sel.values()) == 5 and img[4] not in [p["path"] for p in sel[1]], "the least relevant of the biggest section goes first"
one = {0: [pic(img[i], credit="C" * 99) for i in range(1, 7)]}
assert len(X.select_pictures(one, credit_room=350)[0]) == 3 and len(X.select_pictures(one, credit_room=5)[0]) == 1
cr = X.credit_lines([pic("a.jpg"), pic("a.jpg"), pic("b.jpg", credit="Photo: Y, CC0, via Wikimedia Commons"), {"credit": ""}], limit=2600)
assert len(cr) == 2 and cr[0].endswith("(https://commons.wikimedia.org/wiki/File:a.jpg)") and cr[1].startswith("Photo: Y")
assert X.credit_lines([pic("a.jpg")], limit=0) == ["Photo: X, CC BY 4.0, via Wikimedia Commons"]

# fact cards: a story section shows up to two of its facts on screen while the narration is on them
pk1 = {"id": "A", "name": "Tate McRae", "facts": [{"id": "A1", "claim": "Tate McRae released the single Sports Car in 2025", "sources": [1]},
                                                  {"id": "A2", "claim": "Too short", "sources": [1]},
                                                  {"id": "A3", "claim": "A fact the narration never mentions at all anywhere", "sources": [1]}],
       "sources": [{"n": 1, "title": "Official Charts: Sports Car", "url": "https://www.officialcharts.com/a"}]}
sc3 = {"sections": [{"chapter": "Intro", "subject": "", "narration": "x", "uses": []},
                    {"chapter": "Tate McRae", "subject": "A", "narration": "x", "uses": ["A1", "A2", "A3", "Q9"]}]}
tbeats = [{"sec": 0, "text": "Intro one."}, {"sec": 0, "text": "Intro two."}] + [{"sec": 1, "text": t} for t in (
    "Some opening words.", "More opening words.", "Tate McRae released the single Sports Car in 2025.", "Then other things happened.", "The end.")]
tdurs = [3.0] * len(tbeats)
tlay = X.layout(tbeats, tdurs)
cards = X.fact_cards(sc3, [pk1], tbeats, tdurs, tlay)
assert len(cards) == 1 and cards[0]["text"] == pk1["facts"][0]["claim"] and cards[0]["note"] == "Source: Official Charts", cards
s1 = tlay["sec"][1]
assert cards[0]["section"] == 1 and cards[0]["kicker"] == "Tate McRae" and cards[0]["t0"] >= s1["start"] + X.CARD + 0.3 - 1e-6
assert cards[0]["t1"] <= s1["end"] - 0.5 + 1e-6 and cards[0]["t1"] - cards[0]["t0"] >= 3.0
assert X.source_note({"sources": [{"n": 1, "title": "No colon", "url": "https://www.example.com/x"}]}, {"sources": [1]}) == "Source: example.com"

# the shots: contiguous, a chapter card at each section start after the first, fact cards, pictures round again, subject cards
files = {"chapter": {1: "chapter1.png"}, "subject": {"A": "subjA.png", "all": "all.png"}, "end": "end.png"}
big = [{"sec": 0}] * 3 + [{"sec": 1}] * 4
blay = X.layout(big, [10.0, 10.0, 10.0, 8.0, 8.0, 8.0, 8.0])
bsc = {"sections": [{"chapter": "Intro", "subject": "", "pictures": [], "narration": "x", "uses": []},
                    {"chapter": "Story", "subject": "A", "pictures": [], "narration": "x", "uses": []}]}
with_pics = {0: [{"path": "/p/a.jpg"}], 1: [{"path": "/p/b.jpg"}, {"path": "/p/c.jpg"}]}
bcards = [{"t0": 20.0, "t1": 25.0, "text": "t", "note": "", "kicker": "k", "section": 1, "path": "card.png"}]
segs = X.plan_visuals(blay, with_pics, [dict(c, t0=blay["sec"][1]["start"] + 10, t1=blay["sec"][1]["start"] + 15) for c in bcards], bsc, [pk1], files)
assert segs[0]["t0"] == 0 and segs[-1]["kind"] == "end" and segs[-1]["path"] == "end.png" and abs(segs[-1]["t1"] - blay["total"]) < 1e-6
assert all(abs(a["t1"] - b["t0"]) < 1e-6 for a, b in zip(segs, segs[1:])), "no gap and no overlap"
ch = [s for s in segs if s["kind"] == "chapter"]
assert len(ch) == 1 and ch[0]["path"] == "chapter1.png" and abs(ch[0]["t0"] - blay["sec"][1]["start"]) < 1e-6 and abs(ch[0]["t1"] - ch[0]["t0"] - X.CARD) < 1e-6
assert len([s for s in segs if s["kind"] == "card"]) == 1
pics_used = [s for s in segs if s["kind"] == "pic"]
assert {s["path"] for s in pics_used} == {"/p/a.jpg", "/p/b.jpg", "/p/c.jpg"} and all(s["t1"] - s["t0"] <= X.HOLD_MAX + 1e-6 for s in pics_used)
sec0 = [s for s in pics_used if s["path"] == "/p/a.jpg"]
assert len(sec0) >= 4 and len({s["crop"] for s in sec0}) >= 2 and len({s["move"] for s in sec0}) >= 3, "one picture repeated comes back closer, with other moves"
nopic = X.plan_visuals(blay, {0: [], 1: []}, [], bsc, [pk1], files)
assert [s["path"] for s in nopic if s["kind"] == "card"] and {s["path"] for s in nopic if s["kind"] == "card"} == {"all.png", "subjA.png"}
assert all(abs(a["t1"] - b["t0"]) < 1e-6 for a, b in zip(nopic, nopic[1:]))
assert X.youtube_tags({"tags": ["Tate McRae", "tate mcrae", "x" * 30]}, PACKS)[:2] == ["Tate McRae", "x" * 30]
assert sum(len(t) + 3 for t in X.youtube_tags({"tags": [f"tag {i} " + "z" * 40 for i in range(30)]}, PACKS)) <= 450


# 5. a real small render ---------------------------------------------------------------------------------------------------
HAVE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe") and pathlib.Path(DEJAVU).exists())
W0, H0, F0 = X.W, X.H, X.FPS
X.W, X.H, X.FPS = 320, 180, 10


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height", "-of", "json", str(path)],
                       capture_output=True, text=True)
    j = json.loads(r.stdout); return float(j["format"]["duration"]), {s["codec_name"]: (s.get("width"), s.get("height")) for s in j["streams"]}


try:
    land, port = make_img(PD / "land.png", 11, (1600, 900)), make_img(PD / "port.png", 12, (600, 900))
    s_land, s_port = X.Still(land, "in"), X.Still(port, "left")
    assert s_land.cover and not s_port.cover
    for st in (s_land, s_port):
        a, b = st.frame(0, 5), st.frame(5, 5)
        assert a.size == b.size == (320, 180) and a.tobytes() != b.tobytes(), "the picture moves"
        assert st.frame(7, 5).size == (320, 180), "a move runs on under the next shot's crossfade"
    assert X.Still(land, "nonsense", 1.26, (0.2, 0.3)).frame(1, 5).size == (320, 180)
    if HAVE:
        sil = TMP / "silence.wav"
        import numpy as np, soundfile as sf
        sf.write(str(sil), np.zeros(48000 * 3, dtype="float32"), 48000)
        rsegs = [{"t0": 0, "t1": 1.2, "kind": "pic", "path": land, "move": "in", "crop": 1.0, "focus": None},
                 {"t0": 1.2, "t1": 2.2, "kind": "pic", "path": port, "move": "left", "crop": 1.0, "focus": None},
                 {"t0": 2.2, "t1": 3.0, "kind": "card", "path": str(TMP / "does-not-exist.png"), "move": "hold", "crop": 1.0, "focus": None}]
        for caps_on in (True, False):
            out = TMP / f"small-{caps_on}.mp4"
            with quiet(): X.render(rsegs, [(0.5, 2.5, "A small caption for the test.")], 3.0, sil, out, FP, captions=caps_on)
            dur, streams = probe(out)
            assert abs(dur - 3.0) < 0.3 and streams.get("h264") == (320, 180) and "aac" in streams, (dur, streams)
        # the audio: beats placed on one track, then the mix with no music bed
        w1 = TMP / "b1.wav"; sf.write(str(w1), np.full(2400, 0.5, dtype="float32"), 24000)
        nar = X.assemble_audio([w1, w1], [0.5, 1.5], 2.5, TMP / "nar.wav")
        y, sr = sf.read(str(nar)); assert sr == 24000 and len(y) == 60000 and abs(y[int(0.55 * sr)] - 0.5) < 1e-4 and y[int(1.2 * sr)] == 0 and abs(y[int(1.55 * sr)] - 0.5) < 1e-4
        X.mix_audio(nar, None, 2.5, TMP / "mix.wav")
        assert abs(probe(TMP / "mix.wav")[0] - 2.5) < 0.2
        # cards and thumbnail, with the module's own sizes restored for the real 1920 x 1080 layout
        X.W, X.H = W0, H0
        import weekly as WK
        c1 = WK.card(TMP / "c1.png", "A very long chapter title that needs three lines to fit on the card at all", "Tate McRae", FP, fit=True)
        c2 = WK.card(TMP / "c2.png", "Two lines", "Quickplay Daily", FP)
        assert Image.open(c1).size == (1920, 1080) == Image.open(c2).size
        fc = X.card_image(TMP / "fact.png", "Tate McRae released the single Sports Car in 2025 and it went to number one", "Tate McRae", "Source: Official Charts", FP)
        assert Image.open(fc).size == (1920, 1080)
        th = X.make_thumbnail(TMP / "thumb.jpg", land, ["Tate McRae", "Queen", "Jailer 2"], FP)
        assert Image.open(th).size == (1280, 720)
        assert X.caption_strip("A caption that is long enough to need a second line when it is drawn on the strip " * 2, FP).size[0] == 1500
finally:
    X.W, X.H, X.FPS = W0, H0, F0


# the whole build: stubbed model, voice and pictures; a small real render
def fake_tts(beats, work, voice="F2", wps=2.9, sh=None):
    import numpy as np, soundfile as sf
    out = work / "voice"; out.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(24000 * 0.25)) / 24000
    for i in range(len(beats)): sf.write(str(out / f"cb_b{i:02d}.wav"), (0.2 * np.sin(2 * np.pi * (180 + 7 * (i % 9)) * t)).astype("float32"), 24000)
    return out, {"beats": [{"beat": i, "file": f"cb_b{i:02d}.wav", "dur": 0.25, "recall": 1.0, "text": b["text"]} for i, b in enumerate(beats)], "unclear": []}


def fake_fetch(sc, packs, day, resolve=None, extras=None):
    return {k: [pic(make_img(PD / f"s{k}-{j}.png", 100 + 3 * k + j), .9, credit=f"Photo: Person {3 * k + j}, CC BY 4.0, via Wikimedia Commons") for j in range(3)]
            for k in range(len(sc["sections"]))}


if HAVE:
    import weekly as WK
    keep = (X.run_tts, X.fetch_pictures, WK.fonts, X.W, X.H, X.FPS)
    X.run_tts, X.fetch_pictures, WK.fonts = fake_tts, fake_fetch, lambda work: FP
    X.W, X.H, X.FPS = 320, 180, 10
    os.environ.pop("MUSIC_KEY", None)
    try:
        X.ROOT = FIXR
        out = TMP / "build-out"
        with quiet(): man = X.build(out, now=NOW, ask=Ask([RAW]))
        assert man["state"] == "built", man
        saved = json.loads((out / "explainer.json").read_text())
        assert saved["state"] == "built" and saved["day"] == "2026-10-28" and saved["dry"] is False
        assert [s["name"] for s in saved["subjects"]] == ["Tate McRae", "Queen", "Jailer 2"] and saved["model"] == "stub-writer"
        assert saved["fact_check"].endswith("passed") and 1000 <= saved["words"] <= 1450 and saved["pictures"] >= 8
        assert (out / "video.mp4").stat().st_size > 10000 and (out / "thumb.jpg").exists() and (out / "script.json").exists()
        assert saved["chapters"][0] == ["0:00", "The week in three stories"] and len(saved["chapters"]) == 6
        dur, streams = probe(out / "video.mp4")
        assert abs(dur - saved["seconds"]) < 3 and streams.get("h264") == (320, 180), (dur, saved["seconds"], streams)
        assert any("outside the 6 to 10 minute plan" in w for w in saved["warnings"]), "a short test video is flagged"
        d = saved["description"]
        assert d.startswith("The three stories people searched for most") and "Chapters\n0:00 The week in three stories\n" in d and len(d) <= X.DESC_LIMIT
        assert "https://example.com/QD-101/1" in d and "https://youtube.com/shorts/V101" in d and "Photo: Person 0" in d and "#QuickplayDaily" in d
        assert saved["tags"][0] == "weekly explainer" and "tate mcrae" in [t.lower() for t in saved["tags"]] and saved["shorts"][0] == "QD-101"
        assert not any(c in d + saved["title"] for c in DASHES)

        # a week with two stories is skipped, not built
        two = X.ROOT = fresh("two-subjects"); write_fixture(two, third=False)
        with quiet(): man2 = X.build(TMP / "two-out", now=NOW, ask=Ask([RAW]))
        assert man2["state"] == "skipped" and "only 2 subjects" in man2["reason"], man2
        X.ROOT = FIXR
        with quiet(): man3 = X.build(TMP / "nomodel-out", now=NOW, ask=Ask([RuntimeError("all models busy")]))
        assert man3["state"] == "skipped" and "no model answered" in man3["reason"], man3
        X.fetch_pictures = lambda sc, packs, day, **k: {}
        with quiet(): man4 = X.build(TMP / "nopics-out", now=NOW, ask=Ask([RAW]))
        assert man4["state"] == "skipped" and "usable pictures" in man4["reason"], man4
        # a script file stands in for the model chain; a dry build says so
        X.fetch_pictures = fake_fetch
        sf_path = TMP / "script-in.json"; sf_path.write_text(json.dumps(RAW))
        with quiet(): man5 = X.build(TMP / "file-out", dry=True, now=NOW, script_file=str(sf_path), captions=False)
        assert man5["state"] == "built" and man5["dry"] is True and man5["model"] == "file" and man5["fact_check"] == "not run"
        # a crash is recorded as failed and raised
        def down(*a, **k): raise RuntimeError("the voice is down")
        X.run_tts = down
        with quiet(): raises(RuntimeError, X.build, TMP / "crash-out", now=NOW, ask=Ask([RAW]))
        crashed = json.loads((TMP / "crash-out" / "explainer.json").read_text())
        assert crashed["state"] == "failed" and "the voice is down" in crashed["reason"]
    finally:
        X.run_tts, X.fetch_pictures, WK.fonts, X.W, X.H, X.FPS = keep
else:
    print("explainer: render parts skipped (no ffmpeg, ffprobe or DejaVu font)")


# 6. description and upload -------------------------------------------------------------------------------------------------
dsc = {"description": "The three stories people searched for most this week."}
chapters = [(0.0, "Intro"), (62.0, "Tate McRae"), (3725.0, "Outro")]
dpk = [{"id": "A", "name": "Tate McRae", "shorts": [{"title": "Short A", "video": "VID001"}, {"title": "No id", "video": ""}],
        "sources": [{"n": i, "title": f"Outlet {i}: story", "url": f"https://example.com/a/{i}"} for i in (1, 2)]},
       {"id": "B", "name": "Queen", "shorts": [{"title": "Short B", "video": "VID003"}], "sources": [{"n": 1, "title": "Q: s", "url": "https://example.com/b/1"}]}]
dpics = [{"credit": "Photo: A, CC BY 4.0, via Wikimedia Commons", "source": "https://commons.wikimedia.org/wiki/File:A.jpg"}]
desc = X.build_description(dsc, dpk, chapters, dpics, "Music: Calm Piano by Someone (YouTube Audio Library)")
assert desc.startswith("The three stories") and "Chapters\n0:00 Intro\n1:02 Tate McRae\n1:02:05 Outro\n" in desc
assert "Short A: https://youtube.com/shorts/VID001" in desc and "No id" not in desc and "Short B: https://youtube.com/shorts/VID003" in desc
assert "Outlet 2: story: https://example.com/a/2" in desc and "Photo: A, CC BY 4.0, via Wikimedia Commons (https://commons.wikimedia.org/wiki/File:A.jpg)" in desc
assert "Music: Calm Piano" in desc and desc.rstrip().endswith("#TateMcRae #Queen #QuickplayDaily #Explainer") and "<" not in desc
assert not any(c in desc for c in DASHES)
many = [{"id": p, "name": n, "shorts": [{"title": "S" * 40, "video": "VID"}],
         "sources": [{"n": i, "title": "T" * 60, "url": f"https://example.com/{p}/" + "x" * 70 + str(i)} for i in range(1, 10)]} for p, n in (("A", "Alpha"), ("B", "Beta"), ("C", "Gamma"))]
manypics = [{"credit": f"Photo: Person {i}, CC BY-SA 4.0, via Wikimedia Commons", "source": f"https://commons.wikimedia.org/wiki/File:Person{i}.jpg"} for i in range(24)]
d2 = X.build_description(dsc, many, chapters, manypics)
assert len(d2) <= X.DESC_LIMIT and "Chapters" in d2 and "The Shorts on these stories" not in d2 and "Where every fact comes from" in d2
for n in ("Alpha", "Beta", "Gamma"): assert f"\n{n}\nT" in d2
heavy = [dict(p, sources=[dict(s, title="T" * 90, url=s["url"] + "y" * 80) for s in p["sources"]]) for p in many]
d3 = X.build_description(dsc, heavy, chapters, manypics)
assert len(d3) <= X.DESC_LIMIT and d3.count("https://example.com/A/") == 3 and "commons.wikimedia.org/wiki/File:Person1.jpg" not in d3, "sources beyond 3 and credit addresses go last"
assert X.hashtag("Jailer 2") == "#Jailer2"

# upload, with the YouTube module stubbed
UP = TMP / "upload-out"; UP.mkdir()
built = {"kind": "explainer", "day": "2026-10-28", "dry": False, "state": "built", "title": "Tate McRae, Queen and Jailer 2 explained", "description": desc,
         "tags": ["a", "b"], "subjects": [{"name": "Tate McRae"}, {"name": "Queen"}], "shorts": ["QD-101"], "chapters": [["0:00", "Intro"]], "seconds": 480,
         "words": 1200, "model": "m", "fact_check": "m: passed", "pictures": 20}
(UP / "video.mp4").write_bytes(b"video"); (UP / "thumb.jpg").write_bytes(b"thumb")
sent, spent = [], []


class LimitReached(Exception): pass


class FakeYT:
    def thumbnails(self): raise RuntimeError("thumbnails need a verified channel")


def make_y(limit=False):
    m = types.ModuleType("youtube")
    m.LimitReached, m.available, m.client = LimitReached, lambda: True, lambda: FakeYT()

    def up(yt, path, title, description, tags, category="Entertainment", publish_at=None, **k):
        if limit: raise LimitReached("uploadLimitExceeded")
        sent.append({"path": str(path), "title": title, "description": description, "tags": tags, "category": category, "publish_at": publish_at}); return "VID123"
    m.upload, m.video_status = up, lambda yt, vid: {"privacy": "private", "publishAt": "x"}
    return m


def make_q(ok=True):
    m = types.ModuleType("quota"); m.COST = {"upload": 100}
    m.allow = lambda units, what="extra": (spent.append((units, what)), ok)[1]
    return m


UR = X.ROOT = fresh("upload-root")
assert X.upload(TMP / "nowhere", NOW) is None
(UP / "explainer.json").write_text(json.dumps(dict(built, state="skipped", reason="only 2 subjects")))
r = X.upload(UP, NOW)
st = json.loads((UR / "status" / "weekly-2026-10-28.json").read_text())
assert r["state"] == "skipped" and st["kind"] == "explainer" and st["state"].startswith("skipped: only 2 subjects") and "video" not in st
(UP / "explainer.json").write_text(json.dumps(built))
with stubbed(youtube=make_y(), quota=make_q(ok=False)):
    st = X.upload(UP, NOW)
assert st["state"] == "waiting: YouTube allowance" and not sent and spent[-1] == (100, "explainer upload")
with stubbed(youtube=make_y(limit=True), quota=make_q()):
    st = X.upload(UP, NOW)
assert st["state"] == "waiting: upload limit" and "video" not in st and not sent
with stubbed(youtube=make_y(), quota=make_q()):
    st = X.upload(UP, NOW)
assert st["state"] == "scheduled" and st["video"] == "VID123" and st["url"] == "https://youtu.be/VID123" and st["kind"] == "explainer"
assert st["publish_at"] == "2026-10-28T19:00+00:00" and "thumbnail_error" in st and st["youtube"]["privacy"] == "private" and "error" not in st
assert sent[0]["publish_at"] == "2026-10-28T19:00:00Z" and sent[0]["category"] == "Entertainment" and sent[0]["title"] == built["title"] and sent[0]["tags"] == ["a", "b"]
assert st["subjects"] == ["Tate McRae", "Queen"] and st["shorts"] == ["QD-101"] and st["seconds"] == 480
n_sent = len(sent)
with stubbed(youtube=make_y(), quota=make_q()):
    again = X.upload(UP, NOW)
assert len(sent) == n_sent and again["video"] == "VID123", "a week already scheduled is never uploaded twice"
assert X.latest_long(dt.datetime(2026, 10, 28, 19, 5, tzinfo=UTC))["id"] == "VID123" and X.latest_long(dt.datetime(2026, 10, 28, 18, 0, tzinfo=UTC)) is None
# a dry build becomes a draft release and no status file
DR = X.ROOT = fresh("dry-root")
ran = []
real_sub, real_sh = X.subprocess, X.sh
X.subprocess = types.SimpleNamespace(run=lambda cmd, **k: ran.append([str(c) for c in cmd]), Popen=real_sub.Popen)
X.sh = lambda *cmd, **k: ran.append([str(c) for c in cmd])
try:
    (UP / "explainer.json").write_text(json.dumps(dict(built, dry=True)))
    with quiet(): X.upload(UP, NOW)
finally:
    X.subprocess, X.sh = real_sub, real_sh
assert any(c[:3] == ["gh", "release", "create"] and "--draft" in c and "explainer-test" in c for c in ran) and not (DR / "status").exists(), ran


# 7. the long videos and the Shorts ------------------------------------------------------------------------------------------
LR = X.ROOT = fresh("links"); (LR / "status").mkdir()
for name, js in (("2026-10-18", {"video": "AAA", "title": "Weekly Quickplay: the best of the week", "publish_at": "2026-10-18T18:00:00Z"}),
                 ("2026-10-25", {"kind": "compilation", "video": "BBB", "title": "Compilation two", "publish_at": "2026-10-25T19:00:00Z"}),
                 ("2026-10-28", {"kind": "explainer", "video": "CCC", "title": "Tate McRae, Queen and Jailer 2 explained", "publish_at": "2026-10-28T19:00+00:00"}),
                 ("2026-11-01", {"video": "DDD", "publish_at": "garbage"}), ("2026-11-04", {"kind": "explainer", "state": "skipped: no model"})):
    (LR / "status" / f"weekly-{name}.json").write_text(json.dumps(js))
(LR / "status" / "QD-001.json").write_text(json.dumps({"video": "SHORT1"}))
lv = X.long_videos()
assert sorted(lv) == ["AAA", "BBB", "CCC", "DDD"] and lv["AAA"]["kind"] == "compilation" and lv["CCC"]["kind"] == "explainer" and lv["DDD"]["publish_at"] is None
t = lambda *a: dt.datetime(*a, tzinfo=UTC)
assert X.latest_long(t(2026, 10, 27, 12))["id"] == "BBB" and X.latest_long(t(2026, 10, 28, 18, 59))["id"] == "BBB"
assert X.latest_long(t(2026, 10, 28, 19))["id"] == "CCC" and X.latest_long(t(2026, 10, 1)) is None and X.latest_long(t(2026, 10, 18, 18))["id"] == "AAA"
assert X.link_lines(t(2026, 10, 29)) == ["Watch the weekly video: Tate McRae, Queen and Jailer 2 explained https://youtu.be/CCC"] and X.link_lines(t(2026, 9, 1)) == []
c1 = X.comment_text("Which one surprised you most?", t(2026, 10, 29))
assert c1 == "Which one surprised you most?\n\nThe full story, in the weekly video: https://youtu.be/CCC"
c2 = X.comment_text("q" * 700, t(2026, 10, 29))
assert len(c2) <= 500 and c2.endswith("https://youtu.be/CCC") and c2.startswith("qqq")
assert X.comment_text("q" * 700, t(2026, 9, 1)) == "q" * 500 and X.comment_text("", t(2026, 10, 29)).endswith("CCC") and X.comment_text(None, t(2026, 9, 1)) == ""

import run_board as RB
sb = {"meta": {"summary": "A summary.", "sources": [["Outlet", "https://example.com/1"]], "hashtags": ["#Test"]}}
track = {"title": "Song", "artist": "Artist"}
d_new = RB.description(sb, [], track, "2026-10-29T15:00:00Z")
lines = d_new.split("\n")
assert lines[0] == "A summary." and lines[2].startswith("Subscribe") and "sub_confirmation=1" in lines[2], lines[:3]      # the subscriber push (25 October) comes first
assert lines[4].startswith("Watch the weekly video: Tate McRae, Queen and Jailer 2 explained https://youtu.be/CCC") and lines[6] == "Sources:", lines[:8]
assert "youtu.be/BBB" in RB.description(sb, [], track, "2026-10-27T15:00:00Z") and "youtu.be/BBB" in RB.description(sb, [], track, "2026-10-27T15:00:00")
assert "weekly video" not in RB.description(sb, [], track, "2026-10-01T15:00:00Z") and "Sources:" in RB.description(sb, [], track, "not a time")
assert RB.description(sb, [], track).split("\n")[:2] == ["A summary.", ""], "the old call, with no slot, still works"
with stubbed(social=types.ModuleType("social"), yt_connect=types.ModuleType("yt_connect"), youtube=types.ModuleType("youtube")):
    import engage as EN
assert EN.long_mention("Which one?", t(2026, 10, 29)).endswith("https://youtu.be/CCC") and EN.long_mention("Which one?", t(2026, 9, 1)) == "Which one?"
assert EN.long_mention("q" * 600, "not a time") == "q" * 500, "any failure leaves the comment as it was"

# watch hours: three ways to ask YouTube, then each long video's days
PAST = dt.datetime(2026, 11, 2, tzinfo=UTC)
TODAY = dt.date(2026, 11, 2)


class Q:
    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def __call__(self, metrics, since=None, **kw):
        self.calls.append((metrics, since, kw))
        if kw.get("dimensions") == "creatorContentType":
            if "ctype" in self.fail: raise RuntimeError("400 invalid dimension")
            return [{"creatorContentType": "VIDEO_ON_DEMAND", "estimatedMinutesWatched": 600}, {"creatorContentType": "SHORTS", "estimatedMinutesWatched": 99999},
                    {"creatorContentType": "LIVE_STREAM", "estimatedMinutesWatched": 60}]
        if kw.get("filters") == "creatorContentType==VIDEO_ON_DEMAND":
            if "filter" in self.fail: raise RuntimeError("400 bad filter")
            return [{"estimatedMinutesWatched": 300}]
        if kw.get("dimensions") == "video":
            if "video" in self.fail: raise RuntimeError("403")
            return [{"video": "AAA", "estimatedMinutesWatched": 120}, {"video": "CCC", "estimatedMinutesWatched": 30}]
        if kw.get("dimensions") == "day":
            if "day" in self.fail: raise RuntimeError("500")
            vid = kw["filters"].split("==")[1]
            return [{"day": "2026-10-28", "views": 40, "estimatedMinutesWatched": 90, "averageViewDuration": 200, "averageViewPercentage": 55.55, "subscribersGained": 2},
                    {"day": "2026-10-29", "views": 10, "estimatedMinutesWatched": 30, "averageViewDuration": 150, "averageViewPercentage": 40, "subscribersGained": 0}] if vid == "CCC" else \
                   [{"day": "2026-10-28", "views": 5, "estimatedMinutesWatched": 12, "averageViewDuration": 100, "averageViewPercentage": 20, "subscribersGained": 0}]
        raise AssertionError(kw)


OD = fresh("longform-out")
q = Q()
with quiet(): rep = X.watch_report(q, TODAY, OD, now=PAST)
assert rep["hours_365d"] == 11.0 and rep["source"] == "creatorContentType" and rep["errors"] == [], rep      # long videos and live streams, never Shorts
rows = list(csv.DictReader(open(OD / "longform.csv")))
assert list(rows[0]) == X.LONGFORM_FIELDS and len(rows) == 4, rows        # AAA, BBB and CCC went public; DDD has no date and the skipped week has no video
r_ccc = [r for r in rows if r["video"] == "CCC" and r["date"] == "2026-10-28"][0]
assert r_ccc["views"] == "40" and r_ccc["watch_minutes"] == "90.0" and r_ccc["watch_hours"] == "1.5" and r_ccc["kind"] == "explainer" and r_ccc["subs_gained"] == "2"
assert abs(float(r_ccc["avg_view_pct"]) - 55.5) < 0.11 and r_ccc["title"].startswith("Tate McRae")
since = {c[2]["filters"]: c[1] for c in q.calls if c[2].get("dimensions") == "day"}
assert since == {"video==CCC": "2026-10-28", "video==AAA": "2026-10-18", "video==BBB": "2026-10-25"}, "each video is asked from the day it went public"
with quiet(): rep = X.watch_report(Q(fail=["ctype"]), TODAY, fresh("lf2"), now=PAST)
assert rep["hours_365d"] == 5.0 and rep["source"] == "filter" and len(rep["errors"]) == 1
with quiet(): rep = X.watch_report(Q(fail=["ctype", "filter"]), TODAY, fresh("lf3"), now=PAST)
assert rep["hours_365d"] == 2.5 and rep["source"] == "our videos"
with quiet(): rep = X.watch_report(Q(fail=["ctype", "filter", "video"]), TODAY, fresh("lf4"), now=PAST)
assert rep["hours_365d"] == round((12 + 12 + 90 + 30) / 60, 1) and rep["source"].startswith("our videos") and len(rep["errors"]) == 3
od5 = fresh("lf5")
with quiet(): rep = X.watch_report(Q(fail=["ctype", "filter", "video", "day"]), TODAY, od5, now=PAST)
assert rep["hours_365d"] is None and rep["rows"] == [] and len(rep["errors"]) == 6 and not (od5 / "longform.csv").exists()
X.ROOT = fresh("no-videos")
with quiet(): rep = X.watch_report(Q(fail=["filter"]), TODAY, fresh("lf6"), now=PAST)
assert rep["hours_365d"] == 11.0 and not (TMP / "lf6" / "longform.csv").exists(), "no long video yet: no file, the figure still comes"
with quiet(): rep = X.watch_report(Q(fail=["ctype", "filter"]), TODAY, fresh("lf7"), now=PAST)
assert rep["hours_365d"] is None

# the ledger can judge a change by long-video watch hours
import changes as C
assert "longform" in C.AREAS and "watch_hours_day" in C.METRICS and C.METRICS["watch_hours_day"][1] == "higher"
D = types.SimpleNamespace(longform=[{"date": "2026-10-28", "watch_hours": "1.5"}, {"date": "2026-10-28", "watch_hours": "0.5"},
                                    {"date": "2026-10-29", "watch_hours": "2"}, {"date": "", "watch_hours": "9"}, {"date": "2026-10-30", "watch_hours": "x"}])
per = C.longform_hours_per_day(D)
assert sorted(per.values()) == [2.0, 2.0] and per[C.day_of("2026-10-28")] == 2.0 and len(per) == 2, per


# 8. weekly.yml -------------------------------------------------------------------------------------------------------------
wy = (REPO / ".github" / "workflows" / "weekly.yml").read_text()
head, rest = wy.split("\n  explainer:\n", 1)
build_job, upload_job = rest.split("\n  explainer-upload:\n", 1)
for cron in ("10 15 * * 0", "10 21 * * 0", "10 9 * * 1", "10 5 * * 3", "40 8 * * 3", "40 12 * * 3"): assert f"cron: '{cron}'" in wy, cron
assert "needs: explainer" in upload_job and "identity.py gate" in upload_job and "identity.py gate" in head
assert "YT_" not in build_job and "SOCIAL_KEY" not in build_job, "the build job never holds the YouTube keys"
for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "MUSIC_KEY", "CB_CKPT"): assert k in build_job and k not in upload_job, k
assert "CLAUDE_CODE_OAUTH_TOKEN" not in wy and "ANTHROPIC" not in wy, "Claude is left out of the explainer chain"
assert "YT_REFRESH_TOKEN" in upload_job and "torch" not in upload_job and "explainer.py upload" in upload_job and "pull -q --rebase" in upload_job
assert "explainer.py due" in build_job and "uploaded-prior-to P7D" in build_job and "pip==26.2.1" in build_job

# no em or en dashes in what this change wrote
for f in ("pipeline/explainer.py", "tests/test_explainer.py", ".github/workflows/weekly.yml", "pipeline/weekly.py"):
    body = (REPO / f).read_text()
    assert not any(c in body for c in DASHES), f"{f}: an em or en dash"
print("explainer ok")
