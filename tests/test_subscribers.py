"""Offline tests of the subscriber push (Charlie, 25 October 2026: "a subscriber push strategy baked into everything"; 15
subscribers from 26,500 views, and the Partner Programme needs 1,000). Stubs only: no network, no model.
1. config.json "sub_push" and templates/looks.json "closing": the closing chip is drawn 50/50 and apart from the style, evenly
   for an exploration Short, an old look renders with no chip; its split follows the subscribers (analytics/subs.csv) only
   with 70 Shorts an arm, and never an arm the views test has cut back;
2. subscribe.py: the handle and the subscribe link with their fallbacks, the series a board is in, the spoken line's prompt
   (never a promised day or hour that is not configured), the chip's words, the comment's first line, the description's, the
   Instagram caption's and the reply's invitation;
3. writer.py: the sub_push arm on every Short but an exploration Short, 50/50 and independent of the title arms, the proven arm
   with a Short in 5 to the other; the old "follow line" ending is folded into it; the prompt rules still format; the call sites;
4. validate.py: a spoken Short needs its ask in the last beats, a "none" Short none, no bare plea; all warnings, no errors;
5. the always-on pieces: the creator comment (series.comment_text, engage.comment_for), the description (run_board), the
   Instagram caption (social.caption, not Facebook or TikTok), a reply to a comment (engage.replies, once per thread), the
   Spanish translator's rule;
6. drivers.py: Garwood intervals, the Shorts that count, subscribers against the same UK day's Shorts with the proof rule
   (push, cut back, early sign), the summary and the Recipe lines (the views guardrail);
7. analytics.py: shorts.csv carries sub_push, the Subscribers section of insights.md, the decisions log, analytics/subs.csv;
8. render3.py and template3.html: the chip is built from the look and the board; the hub's Subscribers card (Playwright,
   skipped where it is missing)."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import collections, csv, datetime as dt, io, json, os, random, re, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "SAMBANOVA_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
REPO = _p.Path(REPO_DIR)
UTC = dt.timezone.utc
REAL = json.loads((REPO / "config.json").read_text())
(SCRATCH / "none").mkdir()
NONE = SCRATCH / "none"


def nodash(*texts):
    import validate
    for t in texts: assert not validate.DASH.search(json.dumps(t, ensure_ascii=False)), t


import subscribe as SUB, looks as LK, validate as V, drivers as D
SUB.SUBS, SUB.DRIVERS, SUB.CHANNEL = NONE / "subs.csv", NONE / "drivers.csv", NONE / "channel.json"      # nothing proven, no channel file yet
LK.DRIVERS, LK.SUBS = NONE / "drivers.csv", NONE / "subs.csv"

# 1. config and the closing chip dimension -----------------------------------------------------------------------------------
sp = REAL["sub_push"]
assert sp["on"] is True and sp["handle"].startswith("@") and 0 < sp["spoken_share"] <= 1 and isinstance(sp["cadence"], dict) and isinstance(sp["times"], dict)
assert sp["cadence"] == {} and sp["times"] == {}, "no rhythm or hour is promised until one is really kept"
nodash(sp, REAL.get("sub_push_note", ""))
cat = LK.catalogue(lab={})
cl = cat["dimensions"]["closing"]
assert cl["assign"] == {"chip": 1, "none": 1} and cl["decide_by"] == "subs" and cl["default"] == "none" and cl["options"]["chip"]["chip_seconds"] == 1.5, cl
looks = {i: LK.choose(f"QD-{i}", [], {}, cat) for i in range(3000)}
chip = sum(1 for lk in looks.values() if lk["closing"] == "chip")
assert 1350 <= chip <= 1650, chip                                                      # 50/50
for st in ("minimal", "standard"):                                                     # apart from the style test (2 in 3 minimal)
    mine = [lk for lk in looks.values() if lk["style"] == st]
    assert 0.44 <= sum(1 for lk in mine if lk["closing"] == "chip") / len(mine) <= 0.56, st
even = collections.Counter(LK.choose(f"QD-{i}", [], {}, cat, explore=True)["closing"] for i in range(2000))
assert 900 <= even["chip"] <= 1100, even
assert all(LK.choose(f"QD-{i}", [], {}, cat) == looks[i] for i in range(0, 3000, 131))      # the same Short, the same look
old = LK.resolve({"captions": "clean", "voice": "george", "energy": "steady", "grade": "natural", "opening": "image_first"}, cat)
assert old["ids"]["closing"] == "none" and not old["render"]["end_chip"], old["render"]       # a look from before the push has no chip
on = LK.resolve({"closing": "chip"}, cat)
assert on["ids"]["closing"] == "chip" and on["render"]["end_chip"] == 1.5 and on["render"]["closing"] == "chip", on["render"]
assert LK.resolve({"closing": "wobbly"}, cat)["render"]["end_chip"] == 0                  # an unknown option is the control
assert LK.describe({}, cat).endswith("standard") and "end chip" in LK.describe({"closing": "chip"}, cat) and "end chip" not in LK.describe({"closing": "none"}, cat)

# the split follows the subscribers, once both arms have 70 Shorts, and never at the cost of views
def subs_csv(*rows):
    with (NONE / "subs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, D.SUBS_FIELDS); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in D.SUBS_FIELDS})


def drivers_csv(*rows):
    with (NONE / "drivers.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["feature", "value", "n", "lift", "verdict"]); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in ("feature", "value", "n", "lift", "verdict")})


R = lambda **kw: {"feature": "subs:look_closing", "feature_label": "Subscribers: Closing chip", **kw}
wts = lambda: {k: round(v, 3) for k, v in LK.assign_weights(cat, "closing").items()}
assert wts() == {"chip": 1.0, "none": 1.0}                                              # nothing yet: as written
subs_csv(R(value="chip", n=80, verdict="push", lift=1.6), R(value="none", n=80, verdict="about typical", lift=0.9))
assert wts() == {"chip": 0.9, "none": 0.1}, wts()                                       # a proven winner gets 9 in 10
subs_csv(R(value="chip", n=80, verdict="about typical", lift=1.0), R(value="none", n=80, verdict="push", lift=1.5))
assert wts() == {"chip": 0.1, "none": 0.9}
subs_csv(R(value="chip", n=80, verdict="cut back", lift=0.6), R(value="none", n=80, verdict="about typical", lift=1.0))
assert wts() == {"chip": 0.1, "none": 0.9}, wts()                                       # a cut back chip leaves the other
subs_csv(R(value="chip", n=69, verdict="push", lift=1.6), R(value="none", n=80, verdict="about typical", lift=0.9))
assert wts() == {"chip": 1.0, "none": 1.0}                                              # 70 Shorts an arm first
subs_csv(R(value="chip", n=80, verdict="push", lift=1.6), R(value="none", n=80, verdict="about typical", lift=0.9))
drivers_csv({"feature": "look_closing", "value": "chip", "n": 80, "lift": 0.7, "verdict": "cut back"})
assert wts() == {"chip": 1.0, "none": 1.0}, wts()                                       # the views test cut the chip back: no win
drivers_csv({"feature": "look_closing", "value": "chip", "n": 80, "lift": 1.1, "verdict": "about typical"})
assert wts() == {"chip": 0.9, "none": 0.1}
drivers_csv(); subs_csv()
print("1 config and the closing chip ok")

# 2. subscribe.py -----------------------------------------------------------------------------------------------------------------
ch_json = NONE / "channel.json"
assert SUB.handle({}, {}, ch_json) == "@quickplaydaily" and SUB.handle(None) == REAL["sub_push"]["handle"]
ch_json.write_text(json.dumps({"handle": "Other", "channel_id": "UC123"}))
assert SUB.handle({}, {}, ch_json) == "@Other" and SUB.sub_url({}, {}, ch_json) == "https://www.youtube.com/@Other?sub_confirmation=1"
nohandle = {"sub_push": {"handle": ""}, "accounts": {"youtube": {"UCabc": "Quickplay Daily"}}}
ch_json.write_text(json.dumps({"checked": "x"}))
assert SUB.handle({}, nohandle, ch_json) == "" and SUB.sub_url({}, nohandle, ch_json) == "https://www.youtube.com/channel/UCabc?sub_confirmation=1"
ch_json.write_text(json.dumps({"channel_id": "UC123"}))
assert SUB.sub_url({}, nohandle, ch_json) == "https://www.youtube.com/channel/UC123?sub_confirmation=1"
assert SUB.sub_url({}, {"sub_push": {"handle": ""}}, NONE / "missing.json") == ""            # unknown: no link, never a wrong one
assert SUB.handle({"channel": "music"}) == "@quickplaymusic" and SUB.handle({"channel": "nowhere"}) == ""
assert SUB.sub_url({"channel": "music"}) == "https://www.youtube.com/@quickplaymusic?sub_confirmation=1"
assert SUB.sub_url({"channel": "nowhere"}, nohandle, ch_json) == ""                          # another channel never borrows the main one's link
assert SUB.ig_handle() == REAL["accounts"]["instagram"][0] and SUB.ig_handle({}) == ""

N12 = {"series_name": "Science Explained", "series_no": 12, "series_of": 0, "category": "Science"}
PB = {"series_name": "Ballon d'Or", "series_no": 5, "series_of": 5, "series_kind": "playbook", "category": "Sport"}
assert SUB.series_of(N12) == ("Science Explained", 12, 0, "evergreen") and SUB.series_of({"category": "Film"}) == ("", 0, 0, "")
assert SUB.series_of({"franchise": "Song Secrets #7"}) == ("Song Secrets", 7, 0, "franchise")
assert SUB.series_of({"channel_series": "Chart Watch #3"})[:2] == ("Chart Watch", 3) and SUB.series_of({"franchise": "named"}) == ("", 0, 0, "")
assert SUB.series_of({"series_name": "X", "series_no": "oops"})[1] == 0 and SUB.series_of(None) == ("", 0, 0, "")
assert SUB.next_number(N12) == 13 and SUB.next_number(PB) == 0 and SUB.next_number({"category": "Film"}) == 0
assert SUB.next_number({**PB, "series_no": 2}) == 3 and SUB.label(N12) == "Science Explained #12" and SUB.label({**PB, "series_no": 2}) == "Ballon d'Or #2 of 5"
assert SUB.label({"category": "Film"}) == ""

# the spoken line's prompt: a concrete reason, a rhythm only where it is true
a = SUB.note("spoken", "Song Secrets", "Music", {})
assert "ONE short line of 16 words or fewer" in a and 'our "Song Secrets" series' in a and "Do not promise a day or a time" in a, a
assert "bare" in a and "like and subscribe" in a and "every day" not in a.split("The shape")[0], a
assert "Song Secrets is here" not in a and "That was Song Secrets; subscribe so you don't miss the next one" in a, a          # no rhythm known: none said
b = SUB.note("spoken", "", "Gaming", {})
assert "our Gaming Shorts" in b and "It may say it comes every day." in b and "A new Gaming Short lands every day" in b, b       # a category does come daily
c = SUB.note("spoken", "Song Secrets", "Music", {"sub_push": {"cadence": {"Song Secrets": "every weekday"}, "times": {"Song Secrets": "two"}}})
assert "It may say it comes every weekday at two." in c and "Song Secrets is here every weekday at two; subscribe" in c, c
d = SUB.note("spoken", "", "", {})
assert 'tied to Quickplay Daily' in d and "Subscribe to Quickplay Daily so you don't miss the next one" in d
assert SUB.note("none", "x", "y") == SUB.NONE_NOTE and "do not ask viewers to subscribe" in SUB.NONE_NOTE and SUB.note("other") == ""
nodash(a, b, c, d, SUB.NONE_NOTE)

# the chip's words
assert SUB.chip_text(N12) == "Subscribe for Science Explained #13"
assert SUB.chip_text({"series_name": "Game Explained", "series_no": 12, "category": "Gaming"}) == "Subscribe for Game Explained #13"
assert SUB.chip_text(PB) == "Subscribe for more Ballon d'Or"                                  # the last of a playbook promises no number
assert SUB.chip_text({"franchise": "Song Secrets #7"}) == "Subscribe for Song Secrets #8"
assert SUB.chip_text({"category": "Gaming"}) == "Subscribe for more Gaming" and SUB.chip_text({}) == "Subscribe for the next one"
long_name = {"series_name": "An Extremely Long Series Name Indeed", "series_no": 3, "category": "Science"}
assert len(SUB.chip_text(long_name)) <= 40 and SUB.chip_text(long_name) == "Subscribe for more Science", SUB.chip_text(long_name)
assert SUB.chip_text({"language": "es", "chip_label": "Gaming"}) == "Suscríbete para más Gaming" and SUB.chip_text({"language": "es"}).startswith("Suscríbete")
assert "tomorrow" not in SUB.chip_text(N12).lower()                                         # no day is promised
nodash(SUB.chip_text(N12), SUB.chip_text({"language": "es"}))

# the always-on lines
URL = "https://www.youtube.com/playlist?list=PLSCI"
cm = SUB.comment_first_line(N12, URL)
assert cm == f"Science Explained #12: subscribe so you never miss the next one. The whole series: {URL}", cm
assert SUB.comment_first_line(N12, "").endswith("?sub_confirmation=1") and SUB.comment_first_line(N12, "").startswith("Science Explained #12: subscribe")
assert SUB.comment_first_line({"category": "Film"}, URL).startswith("A new Film Short every day: subscribe so you never miss one.")
assert "list=PL" not in SUB.comment_first_line({"category": "Film"}, URL) and SUB.comment_first_line({}).startswith("New Shorts every day: subscribe")
assert SUB.description_lines(N12) == ["Subscribe for the next Science Explained: https://www.youtube.com/@quickplaydaily?sub_confirmation=1", ""]
assert SUB.description_lines({"category": "Film"})[0].startswith("Subscribe so you never miss the next one: https://www.youtube.com/@quickplaydaily")
assert SUB.description_lines({"language": "es"})[0].startswith("Suscríbete para no perderte el siguiente: https://")
assert SUB.description_lines({"channel": "nowhere"}) == []                                  # no known link: nothing, not a broken line
assert SUB.ig_line(N12) == f"Follow @{SUB.ig_handle()} for the next Science Explained." and SUB.ig_line({"category": "Film"}).endswith("for a new Film Short every day.")
assert SUB.ig_line({}) == f"Follow @{SUB.ig_handle()} for a new Short every day." and SUB.ig_line(N12, {"accounts": {}}) == ""
assert SUB.reply_invite(N12) == "Subscribe for the next Science Explained." and SUB.reply_invite({"category": "Film"}) == "Subscribe for a new Film Short every day."
assert SUB.invite_reply("Thank you, glad you liked it!", N12) == "Thank you, glad you liked it! Subscribe for the next Science Explained."
assert SUB.invite_reply("Please subscribe to the channel", N12) == "Please subscribe to the channel"       # once: already asked
inv = SUB.invite_reply("word " * 90, N12)
assert len(inv) <= 300 and inv.endswith("Subscribe for the next Science Explained.") and "http" not in inv, len(inv)
assert SUB.invite_reply("", N12) == "" and len(SUB.invite_reply("q" * 400, {})) <= 300
nodash(cm, SUB.description_lines(N12), SUB.ig_line(N12), SUB.reply_invite(N12))

# the arm and the winner
assert SUB.conf({})["spoken_share"] == 0.5 and SUB.arm(3, {"sub_push": {"on": False}}) == ""
arms = [SUB.arm(k) for k in range(1000)]
assert set(arms) == {"spoken", "none"} and 440 <= arms.count("spoken") <= 560 and arms == [SUB.arm(k) for k in range(1000)]
assert 0.85 < sum(SUB.arm(k, {"sub_push": {"spoken_share": 0.9}}) == "spoken" for k in range(1000)) / 1000 < 0.95
T = lambda value, verdict, lift, feature="subs:sub_push": {"feature": feature, "value": value, "verdict": verdict, "lift": lift}
assert SUB.winner("sub_push", [], []) == "" and SUB.winner("sub_push", [T("spoken", "early sign", 2.0)], []) == ""
assert SUB.winner("sub_push", [T("spoken", "push", 2.0)], []) == "spoken" and SUB.winner("sub_push", [T("none", "push", 1.8)], []) == "none"
assert SUB.winner("sub_push", [T("none", "cut back", 0.5)], []) == "spoken"                  # the other arm of a cut back one
assert SUB.winner("look_closing", [T("chip", "cut back", 0.5, "subs:look_closing")], []) == "none"
assert SUB.winner("sub_push", [T("spoken", "push", 2.0, "subs:look_closing")], []) == ""     # another feature's verdict is not this one's
hurt = [{"feature": "sub_push", "value": "spoken", "verdict": "cut back"}]
assert SUB.winner("sub_push", [T("spoken", "push", 2.0)], hurt) == "" and SUB.winner("sub_push", [T("spoken", "push", 2.0)], [{"feature": "sub_push", "value": "spoken", "verdict": "pause"}]) == ""
assert SUB.winner("sub_push", [T("spoken", "push", 2.0)], [{"feature": "sub_push", "value": "none", "verdict": "cut back"}]) == "spoken"
won = [SUB.arm(k, rows=[T("spoken", "push", 2.0)], views_rows=[]) for k in range(100)]
assert won.count("none") == 20 and all(won[k] == "none" for k in range(0, 100, 5)), won.count("none")       # a Short in 5 tests the other arm
assert SUB.arm(5, rows=[T("spoken", "push", 2.0)], views_rows=hurt) == SUB.arm(5)                                # the views guard: back to 50/50
print("2 subscribe.py ok")

# 3. writer.py ---------------------------------------------------------------------------------------------------------------------
import writer as W
spoken = [W.with_sub_test({}, k)["sub_push"] for k in range(800)]
assert 360 <= spoken.count("spoken") <= 440, spoken.count("spoken")
assert all(W.with_sub_test({"explore": "yes"}, k) == {"explore": "yes"} for k in range(50))        # an exploration Short has no arm
assert W.with_sub_test({"sub_push": "none"}, 4) == {"sub_push": "none"}                          # a series part keeps its first part's arm
assert W.with_sub_test({"hook_type": "number"}, 4)["hook_type"] == "number" and "sub_push" in W.with_sub_test({"explore": "no"}, 4)
for bit, name in W.TITLE_BITS.items():                                                           # apart from the title arms
    for arm in W.TITLE_TESTS[bit]:
        mine = [W.with_sub_test(W.with_title_test({}, k), k) for k in range(800)]
        mine = [t for t in mine if t[bit] == arm]
        assert 0.4 <= sum(t["sub_push"] == "spoken" for t in mine) / len(mine) <= 0.6, (bit, arm)
subs_csv(R(feature="subs:sub_push", value="spoken", n=40, verdict="push", lift=2.0, subs=30))   # the file the writer reads (SUB.SUBS)
w_won = [W.with_sub_test({}, k)["sub_push"] for k in range(100)]
assert w_won.count("spoken") == 80, w_won.count("spoken")                                       # the proven arm, a Short in 5 to the other
drivers_csv({"feature": "sub_push", "value": "spoken", "n": 40, "lift": 0.6, "verdict": "cut back"})
assert W.with_sub_test({}, 7)["sub_push"] == SUB.arm(7, rows=[], views_rows=[]) and [W.with_sub_test({}, k)["sub_push"] for k in range(100)].count("spoken") < 70      # views cut it back: 50/50 again
drivers_csv(); subs_csv()
assert "follow line" not in W.TESTS["ending"] and set(W.TESTS["ending"]) == {"loop", "question"}
assert "follow line" not in W.RULES.lower() or "subscribe line" in W.RULES.lower()
rules = " ".join((W.RULES % {"moods": ["pop"]}).split())                                        # still formats: no stray percent sign
assert "Subscribe line" in rules and "16 words or fewer" in rules and "like and subscribe" in rules and "smash" in rules, rules[:200]
nodash(rules)
old_series = W._series
W._series = lambda: types.SimpleNamespace(series_for=lambda p, kind, a, reserve: {"name": "Science Explained"} if p.get("category") == "Science" else None)
nt = W.sub_note({"category": "Science"}, "news", {"sub_push": "spoken"}, "EARLIER NOTE")
assert nt.startswith("EARLIER NOTE\n\nSUBSCRIBE LINE (this Short tests a spoken") and 'our "Science Explained" series' in nt, nt
nt = W.sub_note({"category": "Music"}, "news", {"sub_push": "spoken", "franchise": "named"}, "")
assert 'our "Song Secrets" series' in nt and nt.startswith("SUBSCRIBE LINE"), nt                  # the named series of the franchise test
nt = W.sub_note({"category": "Gaming"}, "news", {"sub_push": "spoken"}, "N")
assert "our Gaming Shorts" in nt and "Do not promise" not in nt, nt
assert W.sub_note({"category": "Gaming"}, "news", {"sub_push": "none"}, "N") == "N\n\n" + SUB.NONE_NOTE
assert W.sub_note({"category": "Gaming"}, "news", {}, "N") == "N" and W.sub_note({}, "news", {"explore": "yes"}, "") == ""
W._series = lambda: (_ for _ in ()).throw(RuntimeError("no series module"))
assert 'our Gaming Shorts' in W.sub_note({"category": "Gaming"}, "news", {"sub_push": "spoken"}, "")      # an error never fails the Short
W._series = old_series
src = (REPO / "pipeline" / "writer.py").read_text()
emit = src.split("    def emit(p, ", 1)[1].split("    def emit_kind(", 1)[0]
emit_kind = src.split("    def emit_kind(", 1)[1].split("\n    def ", 1)[0]
assert "with_sub_test(" in emit and "sub_note(" in emit and "with_sub_test(" in emit_kind, "both writing paths draw the arm"
extra = src.split("def extra_channel_boards(", 1)[1].split("\ndef ", 1)[0]
assert "with_sub_test" not in extra and "sub_push" not in extra, "the other channels' boards have no arm"
assert "Subscribe line" in W.RECIPE_FIRST and "Subscribe chip" in W.RECIPE_NOT                    # the writer is told the line's result, not the chip's
print("3 writer ok")

# 4. validate.py -------------------------------------------------------------------------------------------------------------------
HOOK = "Olivia Rodrigo's new video has a surprise game show host."
FILL = "word"


def shot(name): return {"src": f"commons-search:{name}", "move": "in", "label": {"t": name, "s": "singer"}}


def board(last=None, test=None, words=78):
    beats = [{"say": HOOK, "visual": {"type": "none"}, "impact": True, "shots": [shot("Olivia Rodrigo")]}]
    per = (words - len(HOOK.split())) // 5
    for i in range(1, 6):
        beats.append({"say": " ".join([FILL] * per) + ".", "visual": {"type": "none"}, "shots": [{"src": "commons-search:Olivia Rodrigo", "move": "in"}]})
    if last: beats[-1]["say"] = last
    return {"id": "TEST-SUB-1", "created": "2026-10-25", "format": "one_detail", "category": "Music", "music": {"mood": "pop"}, "appeal": "everyone",
            "background": ["neon music club", "city night lights", "studio recording"], "beats": beats, "test": dict(test or {}),
            "meta": {"title": "Olivia Rodrigo's new video: a surprise host 🎬", "alt_title": "A surprise host in the new video 🎥",
                     "summary": "Olivia Rodrigo's new video has a surprise host.",
                     "hashtags": ["#OliviaRodrigo", "#Music", "#Pop", "#Video", "#Trending", "#GameShow", "#NewMusic", "#Chart"],
                     "tags": ["olivia rodrigo", "new video", "game show host", "pop music", "surprise cameo"], "comment": "Who would you pick as host?",
                     "sources": [["Billboard, the new video", "https://www.billboard.com/new-video"], ["BBC, the new video", "https://www.bbc.co.uk/new-video"]],
                     "facts": [["Olivia Rodrigo released a new video with a surprise host.", [1, 2]]]}}


subw = lambda b: [x for x in V.check(b)[1] if "subscri" in x.lower() or "plea" in x.lower()]
assert V.check(board()) == ([], []), V.check(board())                                            # the fixture is clean, so each warning below is the rule
LINE = "Song Secrets is here every day; subscribe so you don't miss the next one."
assert V.check(board(LINE, {"sub_push": "spoken"})) == ([], []) and V.check(board(LINE)) == ([], [])      # "subscribe" is no banned word
assert any("tests the subscribe line" in x for x in subw(board(None, {"sub_push": "spoken"})))      # spoken, but no ask in the last beats
assert any("tests having no subscribe line" in x for x in subw(board(LINE, {"sub_push": "none"})))
assert not subw(board(None, {"sub_push": "none"})) and not subw(board(LINE))                       # none and clean; no arm: the ask is allowed
early = board(LINE, {"sub_push": "spoken"}); early["beats"][-1]["say"], early["beats"][1]["say"] = "word.", LINE
assert any("tests the subscribe line" in x for x in subw(early))                                 # in the last two beats, not the middle
for plea in ("Like and subscribe for more.", "Smash that like button and subscribe.", "Hit the bell to subscribe.", "Don't forget to subscribe!"):
    assert any("never a bare" in x for x in subw(board(plea, {"sub_push": "spoken"}))), plea
    assert any("never a bare" in x for x in subw(board(plea))), plea
assert not V.check(board("Follow for the next Song Secrets: it comes every day.", {"sub_push": "spoken"}))[0]
print("4 validate ok")

# 5. the always-on pieces -----------------------------------------------------------------------------------------------------------
import series as SE, run_board as RB, social as SO
RB.long_link = lambda slot="": []          # the weekly video link reads live status/weekly-*.json (tested in test_explainer.py); keep this test offline
c1 = SE.comment_text("Which planet would you visit?", N12, URL)
assert c1.split("\n\n")[0] == cm and c1.endswith("\n\nWhich planet would you visit?") and len(c1) <= 500, c1
c2 = SE.comment_text("Which one?", {"category": "Film"}, URL)
assert c2.startswith("A new Film Short every day: subscribe") and c2.endswith("\n\nWhich one?") and "list=PL" not in c2
c3 = SE.comment_text("q" * 700, N12, URL)
assert len(c3) <= 500 and c3.startswith(cm) and c3 == (cm + "\n\n" + "q" * (500 - len(cm) - 2))
assert SE.comment_text("", N12, URL) == cm and SE.comment_text(None, N12, URL) == cm
nodash(c1, c2)
meta = {"summary": "A short answer.", "sources": [["Wikipedia", "https://en.wikipedia.org/wiki/Sky"]], "hashtags": ["#sky"]}
desc = RB.description({**N12, "meta": meta}, [], {"title": "T", "artist": "A"}).split("\n")
assert desc[:2] == ["A short answer.", ""] and desc[2] == SUB.description_lines(N12)[0] and desc[3] == "", desc[:5]    # right after the summary
assert RB.description({"meta": meta, "channel": "nowhere"}, [], {"title": "T", "artist": "A"}).split("\n")[:3] == ["A short answer.", "", "Sources:"]
real_dl, SUB.description_lines = SUB.description_lines, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
assert RB.description({"meta": meta}, [], {"title": "T", "artist": "A"}).split("\n")[:3] == ["A short answer.", "", "Sources:"]    # never fails a render
SUB.description_lines = real_dl

SO.CFG["instagram_hashtags"] = {"Gaming": ["#gaming", "#gamingnews", "#videogames"]}
bd = {"category": "Gaming", "meta": {"title": "GTA 6", "summary": "A longer summary.", "hashtags": ["#GTA6", "#Rockstar", "#Gaming", "#Shorts", "#Trailer"]},
      "beats": [{"say": "Rockstar hid one number in the GTA 6 trailer."}]}
FOLLOW = f"Follow @{SUB.ig_handle()} for a new Gaming Short every day."
for armname in ("short", "full"):
    cap = SO.caption({}, bd, "instagram", armname)
    assert cap.split("\n\n")[-1] == FOLLOW and cap.count("Follow @") == 1, (armname, cap)       # the last line, in both caption arms
assert SO.caption({}, {**bd, **N12}, "instagram", "short").endswith(f"Follow @{SUB.ig_handle()} for the next Science Explained.")
assert SO.caption({"category": "Gaming"}, {k: v for k, v in bd.items() if k != "category"}, "instagram", "short").endswith(FOLLOW)      # the status' category
for plat in ("facebook", "tiktok"): assert "Follow @" not in SO.caption({}, bd, plat), plat
real_il, SUB.ig_line = SUB.ig_line, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
assert "Follow @" not in SO.caption({}, bd, "instagram", "short") and SO.caption({}, bd, "instagram", "short").endswith("#gaming #gamingnews #videogames")
SUB.ig_line = real_il

import mirror as MI
assert "subscribe" in MI.PROMPT.lower() and "without naming the English series" in MI.PROMPT
nodash(MI.PROMPT)

# engage.py: the comment of a Short in no series (no network) and the replies' invitation, once per thread
Y = types.ModuleType("youtube"); Y.utc = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
sys.modules["youtube"] = Y
import engage as E, factpack as FP, quota as Q
class Boom:
    def __getattr__(self, k): raise AssertionError("a Short in no series makes no YouTube call")
t0 = E.comment_for(Boom(), {"category": "Film"}, "Which film?")
assert t0.startswith("A new Film Short every day: subscribe") and t0.endswith("\n\nWhich film?"), t0

RR = SCRATCH / "replies"
for d in ("status", "boards/done"): (RR / d).mkdir(parents=True)
(RR / "config.json").write_text(json.dumps({"comment_replies_per_day": 10}))
now = dt.datetime.now(UTC)
(RR / "status" / "QD-1.json").write_text(json.dumps({"id": "QD-1", "video": "vid1", "publish_at": (now - dt.timedelta(hours=5)).isoformat()}))
(RR / "boards" / "done" / "QD-1.json").write_text(json.dumps({"id": "QD-1", **N12, "test": {"replies": "on"}, "meta": {"title": "T", "summary": "S"}}))
class Exec:
    def __init__(self, v): self.v = v
    def execute(self): return self.v
class FakeYT:
    def __init__(self, threads): self.threads, self.posted = threads, []
    def channels(self): return types.SimpleNamespace(list=lambda **k: Exec({"items": [{"id": "ME"}]}))
    def commentThreads(self): return types.SimpleNamespace(list=lambda **k: Exec({"items": self.threads}))
    def comments(self): return types.SimpleNamespace(insert=lambda part, body: (self.posted.append(body["snippet"]), Exec({}))[1])
thread = lambda i, text: {"id": i, "snippet": {"topLevelComment": {"snippet": {"authorChannelId": {"value": "U" + i}, "textDisplay": text}}}}
fake = FakeYT([thread("T1", "Love this one"), thread("T2", "What song is it"), thread("T3", "Rude")])
answers = {"replies": [{"id": "T1", "reply": "Thank you, glad you liked it!", "skip": False},
                       {"id": "T2", "reply": "Please subscribe for more like it.", "skip": False},
                       {"id": "T3", "reply": "", "skip": True}]}
real = (FP.gemini, Q.allow, Q.spend, E.client, E.ROOT)
FP.gemini, Q.allow, Q.spend, E.client, E.ROOT = (lambda *a, **k: (answers, "stub")), (lambda *a, **k: True), (lambda *a, **k: None), (lambda: fake), RR
os.environ["GEMINI_API_KEY"] = "stub"
try:
    E.replies()
    assert [p["parentId"] for p in fake.posted] == ["T1", "T2"], fake.posted
    assert fake.posted[0]["textOriginal"] == "Thank you, glad you liked it! Subscribe for the next Science Explained.", fake.posted[0]
    assert fake.posted[1]["textOriginal"] == "Please subscribe for more like it." and all(len(p["textOriginal"]) <= 300 for p in fake.posted)
    rec = json.loads((RR / "status" / "replies.json").read_text())
    assert set(rec["invited"]) == {"T1", "T2"} and set(rec["done"]) == {"T1", "T2", "T3"}       # a skipped thread gets no reply, so no invitation
    E.replies()                                                                                 # the same threads again: nothing more is sent
    assert len(fake.posted) == 2, fake.posted
finally:
    FP.gemini, Q.allow, Q.spend, E.client, E.ROOT = real
    os.environ.pop("GEMINI_API_KEY", None)
print("5 always-on ok")

# 6. drivers.py ---------------------------------------------------------------------------------------------------------------------
NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
assert abs(D.poisson_ci(5)[0] - 1.97) < 0.01 and abs(D.poisson_ci(5)[1] - 10.51) < 0.01             # chi-squared tables
assert D.poisson_ci(0)[0] == 0 and abs(D.poisson_ci(0)[1] - 3.0) < 0.01 and abs(D.poisson_ci(1)[1] - 4.74) < 0.01
assert abs(D.poisson_ci(20)[0] - 13.25) < 0.02 and abs(D.poisson_ci(20)[1] - 29.06) < 0.02 and abs(D.poisson_ci(0, 0.95)[1] - 3.69) < 0.01
assert D._pois_cdf(2, 0) == 1.0 and abs(D._pois_cdf(0, 1.0) - 0.36788) < 1e-4


def srow(i, day, hour, views, subs, **kw):
    posted = dt.datetime(2026, 10, day, hour, 0, tzinfo=UTC)
    return {"short": f"QD-{i}", "posted": posted.isoformat(timespec="minutes"), "yt_views": str(views), "yt_subs_gained": "" if subs is None else str(subs),
            "category": "Music", "title": f"Short {i}", **kw}


def dataset(spoken_subs=3, none_subs=0, days=range(5, 15)):
    """Per UK day 4 Shorts of 1,000 views: spoken/none and loop/question and chip/none are balanced within the day."""
    rows, i = [], 0
    for d in days:
        for j in range(4):
            i += 1
            sp = j % 2 == 0
            rows.append(srow(i, d, 9 + 3 * j, 1000, spoken_subs(d) if callable(spoken_subs) and sp else none_subs(d) if callable(none_subs) and not sp else spoken_subs if sp else none_subs,
                             sub_push="spoken" if sp else "none", ending="loop" if j < 2 else "question",
                             look_closing="chip" if (j // 2 + d) % 2 == 0 else "none"))
    return rows


rows = dataset()
assert len(D.subs_points(rows, NOW)) == 40
extras = [srow(900, 8, 10, 10, 1, sub_push="spoken"),                  # under 20 views
          srow(901, 8, 11, 1000, None, sub_push="spoken"),              # no figure from Analytics yet: a blank is not a zero
          srow(902, 24, 11, 1000, 5, sub_push="spoken"),                # public for a day only
          srow(903, 8, 12, 1000, 5, sub_push="spoken", channel="es")]   # another channel
assert len(D.subs_points(rows + extras, NOW)) == 40 and D.analyse_subscribers(rows + extras, NOW) == D.analyse_subscribers(rows, NOW)
assert len(D.subs_points(rows + [srow(904, 8, 12, 500, 0, sub_push="none")], NOW)) == 41           # a real zero counts
tab = D.analyse_subscribers(rows, NOW)
assert all(set(t) == set(D.SUBS_FIELDS) and t["feature"].startswith("subs:") for t in tab) and tab == sorted(tab, key=lambda t: (t["feature"], -t["lift"]))
by = {(t["feature"], t["value"]): t for t in tab}
sp_, no_ = by[("subs:sub_push", "spoken")], by[("subs:sub_push", "none")]
assert sp_["verdict"] == "push" and sp_["n"] == 20 and sp_["days"] == 10 and sp_["subs"] == 60 and sp_["views"] == 20000, sp_
assert sp_["subs_per_1k"] == 3.0 and sp_["typical_per_1k"] == 1.0 and sp_["lift"] > 2.5 and sp_["low"] > 1.0, sp_            # 3 per 1,000 against 1 typical
assert no_["verdict"] == "cut back" and no_["subs_per_1k"] == 0.0 and no_["lift"] < 0.1 and no_["high"] < 1.0, no_
for key in (("subs:ending", "loop"), ("subs:ending", "question"), ("subs:look_closing", "chip"), ("subs:look_closing", "none")):
    assert by[key]["verdict"] == "about typical" and 0.9 <= by[key]["lift"] <= 1.1, by[key]               # the same-day comparison removes the confounding
assert ("subs:category", "Music") not in by and ("subs:series", "no series") not in by                      # a feature needs two groups to compare
with_series = dataset()
for r in with_series: r["series_name"] = "Song Secrets" if r["sub_push"] == "spoken" else ""
sv = {t["value"]: t for t in D.analyse_subscribers(with_series, NOW) if t["feature"] == "subs:series"}
assert set(sv) == {"Song Secrets", "no series"} and sv["Song Secrets"]["verdict"] == "push"
noise = dataset(lambda d: 1, lambda d: 1)                                                                   # the same everywhere
assert {t["verdict"] for t in D.analyse_subscribers(noise, NOW)} == {"about typical"}
# a single UK day of luck is no proof; halves that disagree are none either; too few Shorts say nothing
day1 = [srow(i, 12, 9 + i, 1000, 4 if i < 5 else 0, sub_push="spoken" if i < 5 else "none") for i in range(10)]
t1 = {t["value"]: t for t in D.analyse_subscribers(day1, NOW) if t["feature"] == "subs:sub_push"}
assert t1["spoken"]["verdict"] == "early sign" and "1 UK day" in t1["spoken"]["why"] and t1["spoken"]["lift"] > 2, t1["spoken"]
flip = dataset(lambda d: 6 if d < 10 else 0, lambda d: 0)
tf = {t["value"]: t for t in D.analyse_subscribers(flip, NOW) if t["feature"] == "subs:sub_push"}
assert tf["spoken"]["verdict"] == "early sign" and "two halves" in tf["spoken"]["why"] and tf["spoken"]["lift"] > 1.25, tf["spoken"]
few = dataset(days=range(5, 6))
assert {t["verdict"] for t in D.analyse_subscribers(few, NOW) if t["feature"] == "subs:sub_push"} <= {"too few to tell", "early sign", "about typical"}
assert D.analyse_subscribers([], NOW) == [] and D.analyse_subscribers(dataset(days=range(5, 6))[:2], NOW) == []
assert D.sub_halves([{"posted": "a", "subs": 3, "exp": 1}, {"posted": "b", "subs": 3, "exp": 1}, {"posted": "c", "subs": 3, "exp": 1}, {"posted": "d", "subs": 3, "exp": 1}], "c") == 1
assert D.sub_halves([{"posted": "a", "subs": 3, "exp": 1}, {"posted": "b", "subs": 3, "exp": 1}, {"posted": "c", "subs": 0, "exp": 1}, {"posted": "d", "subs": 0, "exp": 1}], "c") == 0
assert D.sub_halves([{"posted": "a", "subs": 0, "exp": 3}], "b") is None                                    # a half with under 2 Shorts says nothing
assert D.sub_halves([{"posted": p, "subs": 0, "exp": 3} for p in "aabb"], "b") == -1

sm = D.subs_summary(rows + extras, NOW)
assert sm["shorts"] == 40 and sm["views"] == 40000 and sm["subs"] == 60 and sm["per_1k"] == 1.5, sm
assert sm["best"] == {"id": "QD-1", "title": "Short 1", "subs": 3, "views": 1000, "per_1k": 3.0}, sm["best"]
assert D.subs_summary([], NOW) == {"shorts": 0, "views": 0, "subs": 0, "per_1k": None, "best": None}
assert D.subs_summary([srow(1, 8, 9, 100, 0)], NOW)["best"] is None                                       # none has gained one yet

rec_ = D.subs_recipe(tab)
assert len(rec_) == 1 and rec_[0].startswith("Subscribe line: the spoken reason wins for subscribers (3.0 subscribers per 1,000 views against 1.0 typical, 20 Shorts over 10 UK days)"), rec_
assert D.subs_recipe(tab, [{"feature": "sub_push", "value": "spoken", "verdict": "cut back"}]) == []        # the views test says it costs views
assert len(D.subs_recipe(tab, [{"feature": "sub_push", "value": "spoken", "verdict": "about typical"}])) == 1
chipwin = [dict(t, feature="subs:look_closing", value="chip", verdict="push", subs_per_1k=2.0, typical_per_1k=1.0, n=30, days=8) for t in tab[:1]]
cr = D.subs_recipe(chipwin)
assert len(cr) == 1 and cr[0].startswith("Subscribe chip: the chip ending wins for subscribers") and "Subscribe chip" in W.RECIPE_NOT
nonewin = [dict(no_, verdict="push", lift=1.5)]
assert D.subs_recipe(nonewin)[0].startswith("Subscribe line: a Short with no spoken line wins")
assert D.subs_recipe([dict(sp_, verdict="cut back", lift=0.5)])[0].startswith("Subscribe line: a Short with no spoken line wins")
nodash(rec_, cr)
# the features: the arms are scored for views too (the guardrail), never paused
assert ("look_closing", "Closing chip") in D.FEATURES and ("sub_push", "Subscribe line") in D.FEATURES
assert {"look_closing", "sub_push"} <= D.PIPELINE_ONLY and {"look_closing", "sub_push"} <= D.NEVER_PAUSED and "sub_push" in D.TESTED
assert D.features({"sub_push": "spoken", "look_closing": "chip"})["sub_push"] == "spoken" and D.features({"look_closing": "chip"})["look_closing"] == "chip"
print("6 drivers ok")

# 7. analytics.py -------------------------------------------------------------------------------------------------------------------
import analytics as A
A.ROOT = SCRATCH; A.OUT = SCRATCH / "analytics"; A.CACHE = A.OUT / "cache"; A.CACHE.mkdir(parents=True)
(SCRATCH / "boards" / "done").mkdir(parents=True); (SCRATCH / "status").mkdir(exist_ok=True)
(SCRATCH / "boards" / "done" / "QD-800.json").write_text(json.dumps({"id": "QD-800", "category": "Music", "format": "one_detail", "beats": [{"say": "Hello there"}],
    "test": {"sub_push": "spoken", "ending": "loop"}, "meta": {"title": "t"}}))
(SCRATCH / "status" / "QD-800.json").write_text(json.dumps({"id": "QD-800", "video": "vid800", "source": "pipeline"}))
o = A.our_shorts()["vid800"]
assert o["sub_push"] == "spoken" and o["ending"] == "loop", o                                              # the arm reaches shorts.csv
assert "sub_push" in json.dumps(A.TITLE_FACTORS) and A.TITLE_FACTORS["sub_push"] == ["spoken", "none"] and "sub_push" in A.FACTOR_LABELS
summ = D.subs_summary(rows, NOW)
sec = A.subs_section(tab, summ, {"youtube": {"subscribers": 15}})
text = "\n".join(sec)
assert sec[0].startswith("## Subscribers (") and "The channel has 15 of the 1,000 subscribers" in text, text
assert "Overall: 1.5 subscribers per 1,000 views (60 from 40,000 views over 40 Shorts)." in text, text
assert "Subscribe line: spoken 3.0 per 1,000 (60 from 20,000 views, 20 Shorts, " in text and "none 0.0 per 1,000" in text and "push" in text and "cut back" in text, text
assert "Closing chip:" in text and "Ending:" in text and "Best Short for subscribers: QD-1" in text and sec[-1] == "", text
none_yet = "\n".join(A.subs_section([], {"shorts": 0}, None))
assert "No Short is old enough to count yet" in none_yet and "channel has" not in none_yet
nobest = "\n".join(A.subs_section([], {"shorts": 3, "views": 900, "subs": 0, "per_1k": 0.0, "best": None}, None))
assert "no arm has 2 or more groups" in nobest and "none has gained one yet" in nobest
nodash(sec)
s_ = {"updated": "2026-10-25T12:00:00", "errors": {}, "ypp": {"apply_before": "2026-12-31", "days_left": 67, "views_needed_per_day": 100000},
      "youtube": {"subscribers": 15, "views_last_90_days": 26500, "views_measure": "views"}}
ins = A.insights([], s_, [], ["Subscribe line: the spoken reason wins."], {}, sec)                          # the section sits before "When people watch"
assert "## Subscribers (" in ins and ins.index("## Subscribers (") < ins.index("## When people watch") and "- Subscribe line: the spoken reason wins." in ins, ins[:800]
assert "## Subscribers" not in A.insights([], s_, [], [], {})                                               # none given: the older shape
# the decisions log: a verdict turning to push or cut back with 5 Shorts is one line, never twice, never a typical row
A.log_sub_decisions([dict(t, verdict="about typical") for t in tab])
assert not (A.OUT / "decisions.csv").exists() or not list(csv.DictReader((A.OUT / "decisions.csv").open()))
A.log_sub_decisions(tab)
dec = list(csv.DictReader((A.OUT / "decisions.csv").open()))
ch = {r["change"] for r in dec}
assert 'Lean towards subscribe line "spoken" for subscribers' in ch and 'Use less subscribe line "none" for subscribers' in ch, ch
assert all(r["by"] == "analytics (automatic)" and r["area"].startswith("Subscribers: ") and "subscribers per 1,000 views" in r["why"] for r in dec)
A.log_sub_decisions(tab)
assert len(list(csv.DictReader((A.OUT / "decisions.csv").open()))) == len(dec)                             # unchanged: nothing new
A.log_sub_decisions([dict(t, verdict="about typical") for t in tab])
assert any(r["change"].startswith("Back to normal for subscribe line") for r in csv.DictReader((A.OUT / "decisions.csv").open()))
state = json.loads((A.CACHE / "verdicts_subs.json").read_text())
assert state["subs:sub_push|spoken"]["verdict"] == "about typical"
A.log_sub_decisions([dict(sp_, n=3, verdict="push")])                                                      # under 5 Shorts: not logged
assert "subs:sub_push|spoken" not in json.loads((A.CACHE / "verdicts_subs.json").read_text())
print("7 analytics ok")

# 8. the chip is drawn from the look and the board; the hub shows the card ----------------------------------------------------------------
import render3 as R3
R3.LOOK = LK.resolve({"closing": "chip"}, cat)["render"]
assert R3.end_chip(N12) == {"text": "Subscribe for Science Explained #13", "seconds": 1.5}
assert R3.end_chip({"category": "Film"}) == {"text": "Subscribe for more Film", "seconds": 1.5}
R3.LOOK = LK.resolve({"closing": "none"}, cat)["render"]
assert R3.end_chip(N12) is None
R3.LOOK = {}
assert R3.end_chip(N12) is None
R3.LOOK = LK.resolve({"closing": "chip"}, cat)["render"]
real_ct, SUB.chip_text = SUB.chip_text, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
assert R3.end_chip(N12) is None                                                                            # never a reason to fail a render
SUB.chip_text = real_ct
tpl = (REPO / "pipeline" / "template3.html").read_text()
assert "#endchip" in tpl and 'id="endchip"' in tpl and "D.endChip" in tpl and "D.duration - (D.endChip.seconds" in tpl
src3 = (REPO / "pipeline" / "render3.py").read_text()
assert 'data["endChip"] = chip' in src3

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("8 hub card: playwright missing, skipped"); print("subscribers ok"); sys.exit(0)


def run_hub(override):
    def raw(route):
        rel = route.request.url.split("/main/", 1)[-1].split("?")[0]
        if rel in override: route.fulfill(status=200, body=override[rel]); return
        f = REPO / rel
        if rel != "analytics/subs.csv" and f.is_file(): route.fulfill(status=200, body=f.read_bytes())
        else: route.fulfill(status=404, body="")
    with sync_playwright() as pw:
        b = pw.chromium.launch(); p = b.new_context(viewport={"width": 390, "height": 844}).new_page(); errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.route("https://raw.githubusercontent.com/**", raw)
        p.route("https://api.github.com/**", lambda r: r.fulfill(status=200, content_type="application/json", body="[]"))
        for pat in ("https://fonts.**", "https://api.frankfurter.app/**", "https://open.er-api.com/**", "https://cdnjs.cloudflare.com/**"):
            p.route(pat, lambda r: r.abort())
        p.goto((REPO / "docs" / "hub.html").as_uri()); p.wait_for_timeout(2500)
        p.click('#tabs [data-tab="insights"]'); p.wait_for_timeout(300)
        txt = p.inner_text("#insights"); wide = p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        b.close()
    assert not errs, errs
    return txt, wide


buf = io.StringIO()
w_ = csv.DictWriter(buf, D.SUBS_FIELDS); w_.writeheader()
for t in tab: w_.writerow(t)
txt, wide = run_hub({"analytics/subs.csv": buf.getvalue()})
card = txt.split("Subscribers", 1)[1].split("Tests being run", 1)[0]
for want in ("Per 1,000 views", "Best Short", "of the 1,000 the Partner Programme needs", "Subscribe line", "Closing chip", "spoken", "more subscribers", "fewer subscribers", "3.00", "typical"):
    assert want in card, (want, card[:900])
assert wide, "no sideways scroll on a phone"
txt, wide = run_hub({})                                                                                    # no subs.csv yet: a plain note, no error
card = txt.split("Subscribers", 1)[1].split("Tests being run", 1)[0]
assert "filled in by the next full analytics run" in card and wide, card[:600]
print("8 chip and hub ok")
print("subscribers ok")
