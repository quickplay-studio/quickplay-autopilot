"""Offline test of the content review's changes (24 October): the hook names the lead the title names (V4), no question,
"Did you know" or date opening unless the arm asks (V1, V2), each length arm held to its range (V3), the title answer test
(writer.TITLE_TESTS "title_answer", stated against held back), the prompts (writer RULES, the notes, the arms, Claude's
editor), round 1 scored on the arms as assigned (drivers.features, analytics), the hook label that matches the arms
(drivers.hook_type), and the Recipe the writer is given (writer.recipe).

All four validator rules are warnings: a board with one gets a fixing round (writer.write_board), never an error."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, glob, json, os, re, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "SAMBANOVA_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
import validate as V, drivers as D, writer as W, analytics as A, factpack as F

# nothing below reads or writes the live data: the writer, analytics and Claude's usage log work in the scratch folder
for d in ("analytics", "boards/done", "boards/queue", "status"): (SCRATCH / d).mkdir(parents=True, exist_ok=True)
W.ROOT = SCRATCH
F.USAGE = SCRATCH / "status" / "claude_usage.json"
A.ROOT = SCRATCH; A.OUT = SCRATCH / "analytics"; A.CACHE = A.OUT / "cache"; A.CACHE.mkdir(exist_ok=True)

# ---------------------------------------------------------------- a clean board to bend
TITLE = "Olivia Rodrigo's new video: a surprise host 🎬"
HOOK = "Olivia Rodrigo's new video has a surprise game show host."
FILL = "word"        # narration padding: a neutral word the validator has no view on


def shot(name, label=True):
    return {"src": f"commons-search:{name}", "move": "in", **({"label": {"t": name, "s": "singer"}} if label else {})}


BASE = {
    "id": "TEST-HOOKS-1", "created": "2026-10-24", "format": "one_detail", "category": "Music", "music": {"mood": "pop"},
    "appeal": "everyone", "background": ["neon music club", "city night lights", "studio recording"],
    "beats": [{"say": HOOK, "visual": {"type": "none"}, "impact": True, "shots": [shot("Olivia Rodrigo")]}]
             + [{"say": f"Beat {i} " + " ".join([FILL] * 9) + ".", "visual": {"type": "none"}, "shots": [shot("Olivia Rodrigo", i % 2 == 0)]} for i in range(1, 6)],
    "meta": {"title": TITLE, "alt_title": "A surprise host in the new video 🎥", "summary": "Olivia Rodrigo's new video has a surprise host.",
             "hashtags": ["#OliviaRodrigo", "#Music", "#Pop", "#Video", "#Trending", "#GameShow", "#NewMusic", "#Chart"],
             "tags": ["olivia rodrigo", "new video", "game show host", "pop music", "surprise cameo"],
             "comment": "Who would you pick as host?",
             "sources": [["Billboard, the new video", "https://www.billboard.com/new-video"], ["BBC, the new video", "https://www.bbc.co.uk/new-video"]],
             "facts": [["Olivia Rodrigo released a new video with a surprise host.", [1, 2]]]},
}


def board(hook=HOOK, title=TITLE, label="Olivia Rodrigo", test=None, words=78):
    """A copy of BASE with this first line, title and lead label (None: the board labels nobody) and narration padded to
    exactly `words` words (78: inside the best range of the default and of the "under 25 s" and "25 to 34 s" arms)."""
    x = json.loads(json.dumps(BASE))
    x["meta"]["title"] = title
    x["test"] = dict(test or {})
    x["beats"][0]["say"] = hook
    for bt in x["beats"]:
        for s in bt["shots"]: s.pop("label", None)
    if label: x["beats"][0]["shots"][0]["label"] = {"t": label, "s": "singer"}
    if words:
        n, rest = len(hook.split()), x["beats"][1:]
        per = (words - n) // len(rest)
        for i, bt in enumerate(rest):
            k = per if i < len(rest) - 1 else words - n - per * (len(rest) - 1)
            bt["say"] = " ".join([FILL] * k) + "."
    return x


def warns(b): return V.check(b)[1]
def errs(b): return V.check(b)[0]


assert V.check(board()) == ([], []), V.check(board())      # the fixture is clean, so every warning below is the rule under test
assert sum(len(bt["say"].split()) for bt in board()["beats"]) == 78
print("0 fixture ok")

# ---------------------------------------------------------------- V1: no question or "Did you know" opening
Q = "beat 0: open with a plain statement"
v1 = lambda b: [x for x in warns(b) if x.startswith(Q)]
for h in ("Did you know Olivia Rodrigo hid a game show host in her video?", "Did you know Olivia Rodrigo hid a host in her video",
          "Have you ever seen Olivia Rodrigo's host?", "Ever wondered who hosts Olivia Rodrigo's video", "Can you guess Olivia Rodrigo's host",
          "Guess what Olivia Rodrigo did", "Why did Olivia Rodrigo hide a game show host in her new video?",
          "Olivia Rodrigo hid a host in her video. Who?", "Olivia Rodrigo hid a host in her new video, but why?"):
    assert v1(board(h)) and not errs(board(h)), h             # a warning (one fixing round), never an error
for h in (HOOK, "Olivia Rodrigo's video hides a host.", "Olivia Rodrigo hid a host in her new video, and fans went quiet for a long while after that, wondering?"):
    assert not v1(board(h)) or h.endswith("?") or "?" in h, h  # statements pass (the last one asks late, and ends with a mark: warns)
assert not v1(board("Olivia Rodrigo hid a host in her video, and fans have not stopped talking about it since last Friday night."))
assert not v1(board("Did you know Olivia Rodrigo hid a host in her video?", test={"hook_type": "question"}))     # the question arm may ask
assert not v1(board("Who hosts Olivia Rodrigo's video?", test={"hook_type": "question"}))
for arm in ("statement", "number", "superlative", "twist"):                                                    # no other arm may
    assert v1(board("Did you know Olivia Rodrigo hid a host?", test={"hook_type": arm})), arm
print("1 question openings ok")

# ---------------------------------------------------------------- V2: no date-first opening
DATE = "beat 0: lead with the person and the result"
v2 = lambda h: [x for x in warns(board(h)) if x.startswith(DATE)]
for h in ("On 11 April 1970, Apollo 13 launched for the Moon.", "In 1999, Manchester United won the treble.", "Back in 1985, Queen stole Live Aid.",
          "Tuesday 20 October brought Olivia Rodrigo a new video.", "October 1976 was when Queen recorded it.", "11 April 1970 was a big day.",
          "20 October: Olivia Rodrigo's new video drops.", "2026 was the year Olivia Rodrigo hit it big.", "1st May was the day Queen played."):
    assert v2(h) and not errs(board(h)), h
for h in ("16 times: Olivia Rodrigo topped the chart.", "1,000 fans saw Olivia Rodrigo's surprise.", "Olivia Rodrigo's video from 2026 has a host.",
          "Olivia Rodrigo hit number one on 20 October.", "Five fans waited outside Olivia Rodrigo's show.", "11 Emmy nominations for Olivia Rodrigo."):
    assert not v2(h), h
print("2 date openings ok")

# ---------------------------------------------------------------- V3: each length arm is held to its own range
LEN = "narration: "
RANGES = {"": (70, 125), "under 25 s": (58, 80), "25 to 34 s": (75, 100), "35 to 44 s": (100, 125), "about 60 s": (150, 180), "about 2 min": (280, 340)}
for arm, (lo, hi) in RANGES.items():
    t = {"length": arm} if arm else {}
    for n, ok in ((lo, True), (hi, True), ((lo + hi) // 2, True), (lo - 1, False), (hi + 1, False)):
        got = [x for x in warns(board(words=n, test=t)) if x.startswith(LEN)]
        assert bool(got) != ok and not [x for x in errs(board(words=n, test=t)) if x.startswith(LEN)], (arm, n, got)
        if not ok: assert f"{n} words, best between {lo} and {hi}" in got[0], got
# the hard limits are unchanged: 50 to 135 words for a normal length, an error outside
for arm in ("", "under 25 s", "25 to 34 s", "35 to 44 s"):
    t = {"length": arm} if arm else {}
    assert not [x for x in errs(board(words=50, test=t)) if x.startswith(LEN)] and not [x for x in errs(board(words=135, test=t)) if x.startswith(LEN)]
    assert [x for x in errs(board(words=49, test=t)) if x.startswith(LEN)] and [x for x in errs(board(words=136, test=t)) if x.startswith(LEN)], arm
# the prompt and the validator agree: each arm's own "N to M words" sits inside the range it is held to
for arm, text in W.TESTS["length"].items():
    m = re.search(r"(\d+) to (\d+) words", text)
    assert m and RANGES[arm][0] <= int(m.group(1)) and int(m.group(2)) <= RANGES[arm][1], (arm, text)
print("3 length arms ok")

# ---------------------------------------------------------------- V4: the lead the title names is named in the hook's first five words
LEAD = "in the first five words"
v4 = lambda b: [x for x in warns(b) if x.endswith(", as the title does") or LEAD in x]
assert not v4(board("Olivia Rodrigo's new video has a surprise game show host: David Byrne."))            # QD-034: 5.42x
w = v4(board("David Byrne turns game show host in Olivia Rodrigo's new video."))                          # QD-052: 0.27x
assert w == ["beat 0: name Olivia Rodrigo in the first five words, as the title does"] and not errs(board("David Byrne turns game show host in Olivia Rodrigo's new video."))
assert not v4(board("16 times: Olivia Rodrigo topped the chart this year."))                              # a number hook that names her by the fourth word
assert v4(board("Sixteen weeks after the launch, Olivia Rodrigo topped the chart."))                     # the sixth word is too late
assert not v4(board("Olivia Rodrigo’s new video has a host."))                                            # a curly apostrophe
assert not v4(board("OLIVIA RODRIGO hid a host in her video."))                                           # case does not matter
assert not v4(board("Who hosts the show in the new video?", test={"hook_type": "question"}))              # the question and twist arms are let off
assert not v4(board("You might think pop stars host nothing, but this one does.", test={"hook_type": "twist"}))
for arm in ("statement", "number", "superlative"): assert v4(board("David Byrne hosts the new video.", test={"hook_type": arm})), arm
assert not v4(board("David Byrne turns game show host in the video.", label=None))                        # no label on screen: no lead to check
assert not v4(board("David Byrne turns game show host in the video.", label="Billie Eilish"))             # a labelled name the title does not use
assert not v4(board("Hosts change.", title="Zero Dark Thirty: a new look 🎬", label="Olivia Rodrigo"))
assert V.hook_lead(board(label="Olivia Rodrigo")) == "Olivia Rodrigo" and V.hook_lead(board(label="David Byrne")) == ""
assert V.hook_lead(board(label="Olivia Rodrigo", title="The new video from Olivia Rodrigo has a host 🎬")) == "Olivia Rodrigo"
assert V.lead_named("Olivia Rodrigo", "Olivia sings.") and V.lead_named("Olivia Rodrigo", "A singer sings, and Olivia waits.")          # the fifth word
assert not V.lead_named("Olivia Rodrigo", "A singer sings, and then Olivia waits.")                                                        # the sixth
b = board("Olivia Rodrigo hid a host.", label="Olivia Rodrigo")
b["beats"][1]["shots"][0]["label"] = {"t": "David Byrne", "s": "musician"}                                  # the lead may be labelled on a later beat
assert V.hook_lead(b) == "Olivia Rodrigo"
b = board("David Byrne hosts.", label=None); b["beats"][2]["shots"][0]["label"] = {"t": "Olivia Rodrigo", "s": "singer"}
assert v4(b)
print("4 lead name ok")

# every rule at once: four warnings, no errors, and the same board with its arms (question, 35 to 44 s) keeps only what no arm excuses
both = board("On 11 April 1970, why did David Byrne host the new video?", words=62)
got = warns(both)
assert len(got) == 4 and {x.split(":")[0] for x in got} == {"beat 0", "narration"} and not errs(both), got
assert not any(x.startswith(Q) for x in warns(dict(both, test={"hook_type": "question"})))
print("4b all four are warnings ok")

# the writer gives a board with a warning one fixing round with the warning as the instruction; if the fix fails, the first board stays
asked, ANSWERS = [], []
def fake_gemini(prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None, writing=False):
    asked.append(prompt)
    return (ANSWERS.pop(0) if ANSWERS else None), "gemini-3.7-flash-lite"
F.gemini = fake_gemini
W.factpack.writer_test = lambda k, today=None, order=None: ("", None)
W.claude_arm = lambda sid: None; W.choose_writer = lambda sid: None
W.clean = lambda a: dict(a); W.unwiki = lambda b: None; W.pack_text = lambda p: "the pack"
W.BG.fill = lambda b: 0; W.media_problems = lambda b: []; W.fact_check = lambda b, p: []
day = dt.date(2026, 10, 25)
TESTS_ON = {"hook_type": "statement", "length": "25 to 34 s", "title_emoji": "emoji", "title_answer": "stated"}
bad_first = board("David Byrne turns game show host in Olivia Rodrigo's new video.", words=84, test=TESTS_ON)
fixed = board("Olivia Rodrigo's new video has a surprise game show host.", words=84, test=TESTS_ON)
del asked[:]; ANSWERS[:] = [json.loads(json.dumps(bad_first)), json.loads(json.dumps(fixed))]
got, note = W.write_board({}, "TEST-HOOKS-1", day, "head", tests=dict(TESTS_ON))
assert len(asked) == 2 and "name Olivia Rodrigo in the first five words" in asked[1] and "It fails these checks" in asked[1], asked[1][-300:]
assert got["beats"][0]["say"] == fixed["beats"][0]["say"] and "0 warnings" in note, note
assert got["test"] == TESTS_ON                                                          # every arm rides on the board's test field
del asked[:]; ANSWERS[:] = [json.loads(json.dumps(bad_first)), {"beats": [], "meta": {}}]      # the fix breaks the board: the first one stays
got, note = W.write_board({}, "TEST-HOOKS-1", day, "head", tests=dict(TESTS_ON))
assert len(asked) == 2 and got["beats"][0]["say"] == bad_first["beats"][0]["say"] and "1 warnings" in note, note
del asked[:]; ANSWERS[:] = [json.loads(json.dumps(bad_first))]                                 # no answer to the fix: the first one stays
got, note = W.write_board({}, "TEST-HOOKS-1", day, "head", tests=dict(TESTS_ON))
assert len(asked) == 2 and got["beats"][0]["say"] == bad_first["beats"][0]["say"], note
del asked[:]; ANSWERS[:] = [json.loads(json.dumps(fixed))]                                     # a clean board: no second call
got, note = W.write_board({}, "TEST-HOOKS-1", day, "head", tests=dict(TESTS_ON))
assert len(asked) == 1 and "0 warnings" in note
print("4c fixing round ok")

# ---------------------------------------------------------------- the real boards still read: the new rules only ever warn
n = 0
for p in sorted(glob.glob("boards/done/QD-*.json")):
    b = json.load(open(p))
    e, w = V.check(b, p)
    assert not [x for x in e if x.startswith("malformed")], (p, e)
    n += 1
print(f"4d {n} real boards read ok")

# ---------------------------------------------------------------- the hook arms and the label that matches them
for arm in ("statement", "question", "number", "superlative", "twist"): assert arm in W.TESTS["hook_type"], arm
assert "best-known person, band or team first" in W.TESTS["hook_type"]["statement"]
assert "best-known name by the fourth word" in W.TESTS["hook_type"]["number"] and "Rod Stewart" in W.TESTS["hook_type"]["number"]
assert W.TESTS["hook_type"]["question"].startswith("Open with a question")
for h, want in [("The Beatles recorded their entire debut album in just twelve hours.", "statement"),       # the review's 59 of 114
                ("Taylor Swift's single Patient Zero spent a third week at number one.", "statement"),
                ("Rod Stewart dominated MTV's launch, appearing 16 times in the first day.", "statement"),
                ("Formula 1 is officially heading to Africa in the 2030s.", "statement"),               # a name that holds a number
                ("Shrek 2 Remastered was just revealed with a surprise trailer.", "statement"),
                ("The 50-year-old snooker legend suffered a shocking defeat.", "statement"),
                ("Ten Hag was sacked on Monday.", "statement"),
                ("One of the most-watched bands ever returns.", "superlative"),
                ("One day in 1985 changed rock for good.", "statement"),
                ("Hundreds of fans queued outside.", "statement"),
                ("On 11 April 1970, Apollo 13 launched.", "statement"), ("In 1999, Manchester United won.", "statement"),      # a date is not a number hook
                ("23 October brings a new BBC drama.", "statement"), ("2026 was the year Olivia Rodrigo hit it big.", "statement"),
                ("16 times: Rod Stewart owned MTV's first day.", "number"), ("Five point five five minutes was once too long for radio.", "number"),
                ("Over 5 million fans streamed it in a day.", "number"), ("Over five million fans streamed it in a day.", "number"),
                ("Nine terrifying new monsters invade your maze.", "number"), ("11 Emmy nominations could not save Palm Royale.", "number"),
                ("1.9 billion people watched the concert.", "number"), ("$15 million was raked in on its debut.", "number"),
                ("Just 3 seconds separate the two.", "number"), ("Only 3 seconds remained.", "number"), ("One massive track has five billion streams.", "number"),
                ("Ten million fans watched.", "number"), ("1,000 fans saw it.", "number"),
                ("Only one team has ever won Champions twice.", "superlative"), ("The first video ever shown on MTV had a fitting title.", "superlative"),
                ("You might think rookie pop groups stay local, but BABYMONSTER went global.", "twist"),
                ("Your favourite Netflix rom-com just dropped its third season.", "you"),
                ("Is White Christmas really the best selling song of all time?", "question"), ("Did you know an octopus has three hearts", "question"),
                ("Can you guess the highest grossing superhero movie?", "question"), ("Why do golf balls have dimples?", "question"), ("", "")]:
    assert D.hook_type(h) == want, (h, D.hook_type(h), want)
# every arm's own example hook gets its own label (the number arm's: the number first, then the name by the fourth word)
assert D.hook_type("16 times: Rod Stewart owned MTV's first day.") == "number" and V.lead_named("Rod Stewart", "16 times: Rod Stewart owned MTV's first day.")
# the statement arm is any plain hook when asking whether it was followed; a question or an opening number is not
assert D.hook_used("Your next match feels different.", "statement") == "statement" and D.hook_used("Is it over?", "statement") == "question"
assert D.hook_used("16 times: Rod Stewart owned MTV's first day.", "statement") == "number" and D.hook_used("16 times: Rod", "number") == "number"
assert D.hook_used("Your next match feels different.", "number") == "you" and D.hook_used("The first text message was two words.", "superlative") == "superlative"
print("5 hook label ok")

# ---------------------------------------------------------------- round 1 is scored as assigned
assert [D.length_label(s) for s in (None, "", 24.9, 25, 34.9, 35, 44.9, 45, 89, 90)] == ["", "", "under 25 s", "25 to 34 s", "25 to 34 s", "35 to 44 s", "35 to 44 s", "45 to 89 s", "45 to 89 s", "90 s or more"]
r = {"hook": "16 times: Rod Stewart owned MTV's first day.", "hook_type": "number", "arm_hook_type": "statement", "seconds": "41",
     "arm_length": "25 to 34 s", "hook_named": "yes", "title_answer": "stated", "posted": "2026-10-25T09:00:00+00:00"}
f = D.features(r)
assert f["hook_type"] == "statement" and f["length"] == "25 to 34 s" and f["hook_named"] == "yes" and f["title_answer"] == "stated", f   # the arm, not the text
f = D.features({"hook": "16 times: Rod Stewart owned MTV's first day.", "hook_type": "number", "seconds": "41"})        # no arm: what was written, how long it ran
assert f["hook_type"] == "number" and f["length"] == "35 to 44 s" and f["hook_named"] == "" and f["title_answer"] == "", f
assert D.features({"hook": "x is back", "seconds": "30"})["hook_type"] == "statement"
for arm in D.HOOK_ARMS: assert D.features({"hook": "x", "arm_hook_type": arm})["hook_type"] == arm
for arm in D.LENGTH_ARMS: assert D.features({"seconds": "30", "arm_length": arm})["length"] == arm
assert D.features({"hook": "Plain news.", "arm_hook_type": "as written", "arm_length": "as written", "seconds": "30"})["length"] == "25 to 34 s"
assert D.features({"hook": "Plain news.", "arm_hook_type": "as written"})["hook_type"] == "statement"                    # an arm the table does not know
assert set(W.TESTS["hook_type"]) == set(D.HOOK_ARMS) and set(W.TESTS["length"]) == set(D.LENGTH_ARMS)                  # one list of arms in both
assert {"title_answer", "hook_named"} <= {k for k, _ in D.FEATURES} and "title_answer" in D.TESTED
assert "hook_named" in D.PIPELINE_ONLY and "hook_named" in D.NEVER_PAUSED and "title_answer" in D.NEVER_PAUSED and "title_answer" not in D.PIPELINE_ONLY
# the title answer test reaches the table as assigned: 2 arms, 6 Shorts each on 3 UK days, a clear gap
rows = [{"short": f"QD-{i}", "posted": f"2026-10-{25 + i % 3}T{8 + i % 8:02d}:00:00+00:00", "rel": 2.6 if i % 2 else 0.5, "hook": "x",
         "title_answer": "stated" if i % 2 else "held back", "views_24h": "10", "yt_views": "10", "category": "Music", "format": "one_detail"} for i in range(24)]
tab = {(t["feature"], t["value"]): t for t in D.analyse(rows, {}, "2026-10-30")[0]}
assert tab[("title_answer", "stated")]["verdict"] == "push" and tab[("title_answer", "held back")]["verdict"] == "cut back", tab
assert not any(t["verdict"] in D.PAUSED for k, t in tab.items() if k[0] == "title_answer")
print("6 scored as assigned ok")

# ---------------------------------------------------------------- analytics records the arms on shorts.csv
board_a = board("Olivia Rodrigo's new video has a surprise game show host.", test={"hook_type": "statement", "length": "25 to 34 s", "title_answer": "held back"})
board_a.update(id="QD-950", kind="news", source="Google Trends")
(SCRATCH / "boards" / "done" / "QD-950.json").write_text(json.dumps(board_a))
(SCRATCH / "status" / "QD-950.json").write_text(json.dumps({"id": "QD-950", "video": "vid950", "source": "pipeline", "qa": {"duration": 31.2}}))
board_b = board("David Byrne turns game show host in Olivia Rodrigo's new video.")
board_b.update(id="QD-951", kind="news", source="Google Trends")
(SCRATCH / "boards" / "done" / "QD-951.json").write_text(json.dumps(board_b))
(SCRATCH / "status" / "QD-951.json").write_text(json.dumps({"id": "QD-951", "video": "vid951", "source": "pipeline"}))
ours = A.our_shorts()
o = ours["vid950"]
assert (o["arm_hook_type"], o["arm_length"], o["title_answer"], o["hook_named"]) == ("statement", "25 to 34 s", "held back", "yes"), o
assert set(A.ARM_COLUMNS) <= set(o) and ours["vid951"]["hook_named"] == "no" and ours["vid951"]["arm_hook_type"] == "" and ours["vid951"]["title_answer"] == ""
assert A.hook_named(board("David Byrne hosts.", label=None)) == "" and A.hook_named({}) == "" and A.hook_named({"beats": "x", "meta": []}) == ""
src = open("pipeline/analytics.py").read()
assert src.count("ARM_COLUMNS") >= 3 and '"writer_arm_used") + ARM_COLUMNS' in src       # the shorts.csv row takes every one of them
# the round's progress counts the arms as assigned and how often the text followed them; the title tests ride along
A.CFG["test_round"] = {"name": "round 1", "start": "2026-10-25", "per_arm": 70, "factors": {"hook_type": ["statement", "number"], "length": ["25 to 34 s", "35 to 44 s"]}}
A.CFG["writer_test"] = {}
mk = lambda i, **kw: {"short": f"QD-{960 + i}", "posted": "2026-10-26T09:00:00+00:00", "views_24h": "40", "hook": "Olivia Rodrigo hid a host.", "seconds": "30", **kw}
rows = [mk(0, arm_hook_type="statement", arm_length="25 to 34 s", title_answer="stated", title_emoji="emoji"),
        mk(1, arm_hook_type="number", arm_length="35 to 44 s", hook="16 times: Rod Stewart owned MTV's first day.", seconds="38", title_answer="held back", title_emoji="none"),
        mk(2, arm_hook_type="number", arm_length="35 to 44 s", seconds="30", title_answer="held back"),            # the arm not followed: a plain hook, 30 s
        mk(3, arm_hook_type="statement", arm_length="25 to 34 s", hook="Your next match feels different.", title_answer="stated"),
        mk(4, hook="Plain news.", seconds="40")]                                                                  # no arm: counted by the text and the seconds
lines = A.test_progress(rows, [], today=dt.date(2026, 10, 27))
t = json.loads((A.OUT / "tests.json").read_text())["factors"]
assert t["hook_type"]["arms"]["statement"]["n"] == 3 and t["hook_type"]["arms"]["number"]["n"] == 2, t["hook_type"]
assert t["hook_type"]["followed_pct"] == 80 and t["length"]["followed_pct"] == 80, (t["hook_type"], t["length"])     # 4 of 5 followed
assert t["length"]["arms"]["25 to 34 s"]["n"] == 2 and t["length"]["arms"]["35 to 44 s"]["n"] == 3
assert t["title_answer"]["arms"] == {"stated": {"n": 2, "needs": 68, "verdict": ""}, "held back": {"n": 2, "needs": 68, "verdict": ""}}, t["title_answer"]
assert t["title_emoji"]["arms"]["emoji"]["n"] == 1 and t["title_answer"]["label"].startswith("title answer")
assert any(l.startswith("- title answer") for l in lines)
print("7 recording ok")

# ---------------------------------------------------------------- the title answer test: stated against held back
ans = [W.title_arm(k, "title_answer") for k in range(16)]
assert ans.count("stated") == 8 and ans.count("held back") == 8 and ans[:4] == ["stated"] * 4 and ans[4:8] == ["held back"] * 4, ans
assert [W.title_arm(k) for k in range(8)] == ["emoji", "emoji", "none", "none"] * 2                        # the emoji test is as it was
assert len({(W.title_arm(k, "title_answer"), W.title_arm(k), k % 2) for k in range(16)}) == 8             # independent of the emoji and replies tests
for kind in ("news", "breaking", "follow-up", "remake"):
    t = W.with_title_test({"replies": "on"}, 5, kind)
    assert t["title_answer"] == W.title_arm(5, "title_answer") and t["title_emoji"] == W.title_arm(5) and t["replies"] == "on", (kind, t)
for kind in ("evergreen", "top list", "true story", "fiction"):                                            # kinds with their own title form
    t = W.with_title_test({}, 5, kind)
    assert "title_answer" not in t and t["title_emoji"] == W.title_arm(5), (kind, t)
assert W.with_title_test({"title_answer": "stated", "title_emoji": "none"}, 4) == {"title_answer": "stated", "title_emoji": "none"}      # a series part keeps its arms
assert W.with_title_test({}, 4) == {"title_emoji": W.title_arm(4), "title_answer": W.title_arm(4, "title_answer")}
# once the data gives one arm "push", it takes 4 Shorts in 5 and the other every 5th (RETEST), like the emoji test
(SCRATCH / "analytics" / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict\n"
    "title_answer,Title answer,stated,40,1.4,1.3,push\ntitle_answer,Title answer,held back,40,0.7,0.7,cut back\n")
won = [W.title_arm(k, "title_answer") for k in range(1, 21)]
assert won.count("stated") == 16 and won.count("held back") == 4 and [k for k in range(1, 21) if W.title_arm(k, "title_answer") == "held back"] == [5, 10, 15, 20], won
assert [W.title_arm(k) for k in range(8)] == ["emoji", "emoji", "none", "none"] * 2                        # the emoji test did not move with it
(SCRATCH / "analytics" / "drivers.csv").unlink()
# the style line carries the arm, and the prompt agrees with it
assert W.TITLE_TESTS["title_answer"].keys() == {"stated", "held back"}
s = W.style_note({"title_answer": "stated"}); h = W.style_note({"title_answer": "held back"})
assert "say the news the first line says" in s and "Tate McRae" in s and "hold the answer back" in h and "LISA" in h, (s, h)
both_ = W.style_note({"title_emoji": "none", "title_answer": "held back"})
assert "No emoji anywhere" in both_ and "hold the answer back" in both_
rules = W.RULES % {"moods": ["pop"]}
assert "as the style line's title answer says" in rules and "hold the answer back" in rules and "Never a question" in rules and "only as the style line" in rules
print("8 title answer test ok")

# ---------------------------------------------------------------- the prompts (E1 to E6)
assert "first four\n  words name the best-known person, band or team in the pack" in rules and "never a co-star, outlet or date\n  first" in rules
assert "or the\n  title when no person is in the story" in rules and "Open with a question or a twist only when the style line below asks for one" in rules
assert '"Did you know"' in rules and "speaking to the viewer's own experience" not in rules and "what just changed, or how it ended" in rules
assert "(count them; a length in the style line below sets its own range)" in rules and "70 to 110 words" in rules
assert "open on how it ended, naming who" in W.STORY_NOTE and "never on a date or the set-up" in W.STORY_NOTE and "tell it in order like a storyteller" not in W.STORY_NOTE
assert "never open with a question" in W.EVERGREEN_NOTE and "the answer's most surprising fact, said plainly" in W.EVERGREEN_NOTE
assert "question people type" in W.EVERGREEN_NOTE                                                          # the title stays a question: it serves search
assert "as a plain statement of its figure" in W.COUNTDOWN_NOTE and "without naming it" in W.COUNTDOWN_NOTE
assert W.RULES.count("%") == W.RULES.count("%(moods)s") == 1                                              # only the moods placeholder
print("9 prompts ok")

# ---------------------------------------------------------------- Claude's editor follows the same hook and title rules
os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "test"
W.CFG = dict(W.CFG, claude_edit_share=1.0, claude_edits_per_day=10000, claude_model="sonnet")
W.fact_check = lambda b, p: []
PROMPTS, REPLY = [], {}
W.factpack.claude_call = lambda label, prompt, timeout: (PROMPTS.append(prompt) or REPLY["v"], None)
good = {"title": "Olivia Rodrigo hosts a surprise 🎬", "alt_title": "A host nobody saw coming 🎥", "comment": "Who would you pick?",
        "first": "Olivia Rodrigo's new video has a surprise game show host.", "last": "Beat 5 word word word word word word word word word."}
REPLY["v"] = good
for i, (arm, want_in, want_out) in enumerate([("stated", "the news the first line says", "detail promised but held back"),
                                              ("held back", "detail promised but held back", "the news the first line says"),
                                              (None, "detail promised but held back", "the news the first line says")]):
    bb = board(words=78, test={"title_answer": arm} if arm else {}); bb["id"] = f"TEST-EDIT-{i}"
    out, note = W.claude_edit(bb, {}, "news", "n")
    p = PROMPTS[-1]
    assert want_in in p and want_out not in p and "{title_way}" not in p and "{emoji}" not in p, (arm, p[:900])
    assert "first four words of the first line" in p and "co-star" in p and '"Did you know" or a date' in p and "a number hook still opens on its number" in p
    assert "the best-known name in its first four" in p and "never a question" in p and "under 50 characters" in p
    assert out.get("editor") == "claude" and out["meta"]["title"] == good["title"], note
assert "Tate McRae hits number one in Australia" in PROMPTS[0] and "LISA's Tarantino" in PROMPTS[1]
# the editor may not make the hook worse: a rewrite that pushes the lead name out of the first five words keeps the original board
REPLY["v"] = dict(good, first="Everyone is talking about the new video with Olivia Rodrigo.")
bb = board(words=78); bb["id"] = "TEST-EDIT-9"
out, note = W.claude_edit(bb, {}, "news", "n")
assert "editor" not in out and out["beats"][0]["say"] == HOOK and "kept the original" in note and "more warnings" in note, note
REPLY["v"] = dict(good, first="Did Olivia Rodrigo's new video really have a surprise host?")                           # nor a question
bb = board(words=78); bb["id"] = "TEST-EDIT-8"
out, note = W.claude_edit(bb, {}, "news", "n")
assert "editor" not in out and out["beats"][0]["say"] == HOOK and "kept the original" in note and "more warnings" in note, note
REPLY["v"] = dict(good, first="On 11 April 2026 Olivia Rodrigo's new video had a surprise host.")                      # nor a date
bb = board(words=78); bb["id"] = "TEST-EDIT-7"
out, note = W.claude_edit(bb, {}, "news", "n")
assert "editor" not in out and out["beats"][0]["say"] == HOOK and "more warnings" in note, note
bb = board("Did Olivia Rodrigo's new video really have a surprise host?", words=78, test={"hook_type": "question"}); bb["id"] = "TEST-EDIT-6"
REPLY["v"] = dict(good, first="Did Olivia Rodrigo's new video really hide a surprise host?")                           # a question arm stays a question
out, note = W.claude_edit(bb, {}, "news", "n")
assert out.get("editor") == "claude" and out["beats"][0]["say"].endswith("?"), note
os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN")
print("10 editor ok")

# ---------------------------------------------------------------- the Recipe the writer is given
RECIPE = ("# Insights\n\n## Recipe from the data (the writer follows this; Charlie's requests and breaking news still come first)\n"
          '- Follow up QD-076 ("How Barbara Palvin was discovered ✨"): 55.6x the views. Write one follow-up in the next run.\n'
          "- Category mix for the day (80% from results): Music 17%, Film 17%.\n"
          "- Format: lean towards news_explained (1.63x, 18 Shorts), one_detail (1.52x, 26 Shorts); use less story (0.51x, 16 Shorts).\n"
          "- Posting time (UK): lean towards 08:00 to 10:59 (2.27x, 16 Shorts).\n"
          "- Day posted: lean towards Friday (1.42x, 18 Shorts).\n"
          "- Music mood: lean towards action (2.01x, 10 Shorts); use less tech (0.35x, 5 Shorts).\n"
          "- Pictures: lean towards mostly stock footage (2.19x, 5 Shorts).\n"
          "- Title: use less question (0.58x, 14 Shorts).\n"
          "- Captions: lean towards pop (2.96x, 6 Shorts).\n"
          "- Voice: lean towards george (1.45x, 32 Shorts).\n"
          "- Camera energy: lean towards steady (1.37x, 47 Shorts).\n"
          "- Comment replies: use less off (0.73x, 36 Shorts).\n"
          "- Kind of Short: lean towards breaking (1.42x, 8 Shorts).\n"
          "- Writer model: use less gemini:gemini-flash-latest (0.72x, 8 Shorts).\n"
          "- Hook style: lean towards statement (1.75x, 24 Shorts); use less question (0.38x, 9 Shorts).\n"
          "- Length: lean towards 25 to 34 s (1.26x, 57 Shorts); use less under 25 s (0.68x, 27 Shorts).\n"
          '- Paused for 14 days (a week on, little to no views), then retested: format "story"; music mood "tech".\n'
          "- Title answer: lean towards stated (1.4x, 40 Shorts).\n"
          "- Hook length: lean towards 13 words or more (1.23x, 30 Shorts).\n"
          "- Tests being run (round 1, from 2026-10-25: every Short takes an arm of each, 50/50; an arm settles at 70 measured Shorts). Shorts measured so far:\n"
          "- - hook type: statement 3 (needs 67 more), number 2 (needs 68 more); about 14 more days at today's rate\n"
          "- - length: 25 to 34 s 2 (needs 68 more), 35 to 44 s 3 (needs 67 more); about 14 more days at today's rate\n"
          "- The Shorts feed brings 76% of views: the first second decides everything, so lead with the strongest real image and a hook of 8 words or fewer.\n"
          "- US viewers are 40% (UK 13%): pick stories that matter in both, and keep UK spelling.\n\n## What drives views\n- other\n")
(SCRATCH / "analytics" / "insights.md").write_text(RECIPE)
rec = W.recipe()
lines = rec.splitlines()
assert lines[0].startswith("(Where a STYLE FOR THIS SHORT line below differs") and all(l.startswith("- ") for l in lines[1:]), lines
labels = [l[2:].split(":", 1)[0].split(" (", 1)[0] for l in lines[1:]]
assert labels[:5] == ["Hook style", "Length", "Format", "Hook length", "Paused for 14 days"], labels      # the robust verdicts first, then the pauses
assert labels[5:] == ["Title", "Title answer", "Music mood", "The Shorts feed brings 76% of views", "US viewers are 40%"], labels
for gone in ("Follow up", "Category mix", "Posting time", "Day posted", "Pictures", "Captions", "Voice", "Camera energy", "Comment replies",
             "Kind of Short", "Writer model", "Tests being run", "hook type", "- - "):
    assert gone not in rec, gone                                                                          # the pipeline's own, the planner's, and the tests' progress
assert "a hook of 8 words or fewer" not in rec and "the best-known name in the hook's first four words" in rec     # an older file's stale cap
assert "use less question (0.38x" in rec and "format \"story\"" in rec
# a budget: whole lines only, the robust ones first, and never a cut line
many = RECIPE.replace("- Title: use less question", "- Title: " + "lean towards something very long indeed, " * 40 + "use less question")
(SCRATCH / "analytics" / "insights.md").write_text(many)
rec2 = W.recipe()
body = rec2.splitlines()[1:]
assert sum(len(l) + 1 for l in body) <= W.RECIPE_BUDGET and all(l.endswith((".", ")")) for l in body), (len(rec2), body)
assert body[0].startswith("- Hook style") and body[1].startswith("- Length") and body[2].startswith("- Format")
assert not any(l.startswith("- Title:") for l in body)                                                    # the line that does not fit is left out, not cut
(SCRATCH / "analytics" / "insights.md").write_text("# x\n\n## Recipe from the data\n- Not enough measured Shorts yet (15 needed): keep the variety rules.\n\n## Next\n")
assert "Not enough measured Shorts yet" in W.recipe()                                                     # the "too early" line is guidance too
(SCRATCH / "analytics" / "insights.md").write_text("# x\n\n## Recipe from the data\n- Follow up QD-1: x.\n- Posting time (UK): y.\n\n## Next\n")
assert W.recipe() == ""                                                                                   # nothing it can act on: nothing, not a heading
(SCRATCH / "analytics" / "insights.md").write_text("# x\n\n## Something else\n- a\n")
assert W.recipe() == ""
(SCRATCH / "analytics" / "insights.md").unlink()
assert W.recipe() == ""
# the real file (whatever it holds today) reaches the writer whole lines, inside the budget
W.ROOT = _p.Path(REPO_DIR)
real = W.recipe()
assert sum(len(l) + 1 for l in real.splitlines()[1:]) <= W.RECIPE_BUDGET and all(l.startswith("- ") for l in real.splitlines()[1:]), real
assert not any(g in real for g in ("Follow up", "Category mix", "Posting time", "Pictures:", "Tests being run"))
W.ROOT = SCRATCH
# the audience line no longer asks for a short hook (3 Shorts of evidence): it asks for the name in the hook's first four words
aud = {"channel": {"traffic": [{"insightTrafficSourceType": "SHORTS", "views": 800}, {"insightTrafficSourceType": "YT_SEARCH", "views": 100}],
                   "countries": [{"country": "US", "views": 400}, {"country": "GB", "views": 100}]}}
line = A.audience_recipe(aud)[0]
assert "89% of views" in line and "best-known name in the hook's first four words" in line and "8 words" not in line, line
print("11 recipe ok")
print("validate hooks ok")
