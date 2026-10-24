"""Offline test of the 24 October title and originality changes: one 50-character title limit, the title emoji test
(writer.TITLE_TESTS: 50/50 by Short number, independent of the replies test, locked to a winner once drivers.csv says
"push"), the shape() and validator rules that hold each arm, and the prompt text (originality, statement hooks)."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "SAMBANOVA_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
import writer as W, validate as V

# 1. the prompt: one 50-character limit, held-back titles, no question titles, an emoji only when the style line asks;
#    originality (a point of the Short's own, from the pack's facts only) and statement hooks
rules = W.RULES % {"moods": ["upbeat"]}
assert "under 50 characters" in rules and "under 70" not in rules and "hold the answer back" in rules
assert "Never a question" in rules and "only as the style line" in rules
assert "Your own point" in rules and "never add an outside fact" in rules and "never follow an article's" in rules
assert "plain statement" in rules and "one_detail" in rules
assert "under 50 characters" in W.TRANSLATE and "under 70" not in W.TRANSLATE and "under 70" not in W.EDIT
assert "before the emoji if it has one" in W.PART_MID and "before the emoji if it has one" in W.PART_LAST
print("1 prompt ok")

# 2. the arm: 50/50 by number, every pairing with the replies test (k % 2) made, a series keeps one arm
W.ROOT = SCRATCH; (SCRATCH / "analytics").mkdir()
arms = [W.title_arm(k) for k in range(8)]
assert arms.count("emoji") == 4 and arms.count("none") == 4, arms
pairs = {(W.title_arm(k), "on" if k % 2 == 0 else "off") for k in range(8)}
assert len(pairs) == 4, pairs
assert W.with_title_test({"title_emoji": "none", "replies": "on"}, 0)["title_emoji"] == "none"
assert W.with_title_test({"replies": "on"}, 2)["title_emoji"] == W.title_arm(2)
note = W.style_note({"replies": "on", "title_emoji": "none"})
assert "Title emoji: none" in note and note.startswith("STYLE FOR THIS SHORT"), note
assert "exactly one emoji" in W.style_note({"title_emoji": "emoji"})
# a clear winner in drivers.csv: that arm, with every RETEST-th Short still trying the other
(SCRATCH / "analytics" / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict\n"
                                                 "title_emoji,Title emoji,none,12,1.4,1.3,push\ntitle_emoji,Title emoji,emoji,12,0.7,0.7,cut back\n")
won = [W.title_arm(k) for k in range(1, 21)]
assert won.count("emoji") == 20 // W.RETEST and all(a == "none" for k, a in zip(range(1, 21), won) if k % W.RETEST), won
(SCRATCH / "analytics" / "drivers.csv").unlink()
print("2 arm ok")

# 3. shape(): a "none" board loses the emoji the model added anyway; an "emoji" board keeps its title
b = {"meta": {"title": "LISA's Tarantino video: the detail you missed 🎬", "alt_title": "The Tarantino nod in LISA's video 🎥"}, "beats": []}
W.shape(b, {"title_emoji": "none"})
assert b["meta"]["title"] == "LISA's Tarantino video: the detail you missed" and b["meta"]["alt_title"] == "The Tarantino nod in LISA's video", b
b2 = {"meta": {"title": "Ballon d'Or: the detail nobody saw ⚽"}, "beats": []}
W.shape(b2, {"title_emoji": "emoji"})
assert b2["meta"]["title"].endswith("⚽")
print("3 shape ok")

# 4. the validator holds each arm; over 50 characters is a warning (one fixing round), over 70 an error
base = json.loads(sorted((_p.Path(REPO_DIR) / "boards" / "done").glob("QD-*.json"))[-1].read_text())
base["id"] = "TEST-TITLES-1"
base.pop("franchise", None); base.pop("series", None)
def errs(title, arm=None, alt=None):
    x = json.loads(json.dumps(base))
    x["meta"]["title"] = title
    x["meta"]["alt_title"] = alt if alt is not None else title
    x["test"] = dict(x.get("test") or {}, **({"title_emoji": arm} if arm else {}))
    if not arm: x["test"].pop("title_emoji", None)
    return V.check(x)
TITLE_ERRS = lambda es: [e for e in es if e.startswith("meta.title") or e.startswith("meta.alt_title")]
e, w = errs("Raye's billion streams: the detail behind it", "none")
assert not TITLE_ERRS(e), e
e, w = errs("Raye's billion streams: the detail behind it 🎉", "none")
assert any("no emoji" in x for x in TITLE_ERRS(e)), e
e, w = errs("Raye's billion streams: the detail behind it", "emoji")
assert any("end with one emoji" in x for x in TITLE_ERRS(e)), e
e, w = errs("Raye's billion streams: the detail behind it 🎉", "emoji")
assert not TITLE_ERRS(e), e
e, w = errs("Raye's billion streams: the detail behind it")           # a board from before the test: the old rule
assert any("end with one emoji" in x for x in TITLE_ERRS(e)), e
e, w = errs("Raye's billion streams: the detail behind the song that conquered 🎉", "emoji")
assert not TITLE_ERRS(e) and any(x.startswith("meta.title:") and "under 50" in x for x in w), (e, w)
e, w = errs("Raye's billion streams: the detail behind the song that conquered the whole wide world 🎉", "emoji")
assert any("1 to 70" in x for x in TITLE_ERRS(e)), e
e, w = errs("Raye's billion streams: the detail behind it", "none", alt="The song behind Raye's billion 🎉")
assert any(x.startswith("meta.alt_title") and "no emoji" in x for x in e), e
print("4 validator ok")
print("writer titles ok")
