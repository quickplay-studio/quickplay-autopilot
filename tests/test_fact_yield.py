"""Offline test of the fact yield fixes (23 October evening: 4 of 35 places filled): a slightly misquoted sentence still
counts when the page holds nearly all its words and every number; a wrong number never does; a thin Lite answer gets a
second opinion from the strongest free writers; narration that cites Wikipedia is fixed, not dropped."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import factpack as F
F.USAGE = _p.Path(SCRATCH) / "claude_usage.json"
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
os.environ["GEMINI_API_KEY"] = "test"
F.time.sleep = lambda s: None

PAGE = ("The 1966 World Cup trophy was stolen in London in March 1966. A week later a dog named Pickles found it wrapped "
        "in newspaper under a hedge in Norwood, south London. Pickles became a national hero overnight. "
        "1 | Wembley Stadium | 90,000 | London")
texts, kinds = {1: F.norm(PAGE)}, {1: "wikipedia"}

# 1. exact quotes pass as before; a misquote (a word changed, one dropped) is matched to the page's own words
v, s = F.verify([
    {"claim": "Pickles the dog found the trophy a week later.", "evidence": [{"source": 1, "quote": "A week later a dog named Pickles found it wrapped in newspaper under a hedge"}]},
    {"claim": "A dog called Pickles found the trophy under a hedge in Norwood.", "evidence": [{"source": "1", "quote": "a week later a dog called Pickles found it wrapped in a newspaper under the hedge in Norwood"}]},
    {"claim": "Wembley holds 90,000 people.", "evidence": [{"source": 1, "quote": "1 | Wembley Stadium | 90,000 | London"}]},
], texts, kinds)
assert len(s) == 3, s
assert "pickles found it wrapped in newspaper under a hedge in norwood" in s[1]["evidence"]["1"], s[1]
# 2. a wrong number, or a quote the page doesn't hold, never passes; a repeated claim counts once
v, s = F.verify([
    {"claim": "Wembley holds 95,000 people.", "evidence": [{"source": 1, "quote": "1 | Wembley Stadium | 95,000 | London"}]},
    {"claim": "The trophy was found in Paris.", "evidence": [{"source": 1, "quote": "the trophy was found by police in Paris after a long search"}]},
    {"claim": "Pickles became a national hero.", "evidence": [{"source": 1, "quote": "Pickles became a national hero overnight."}]},
    {"claim": "Pickles became a national hero.", "evidence": [{"source": 1, "quote": "Pickles became a national hero overnight."}]},
], texts, kinds)
assert [x["claim"] for x in s] == ["Pickles became a national hero."], s
print("1-2 verify ok")

# 3. second opinion: Lite finds 1 fact, a strong free model finds more; both are checked together, Claude never asked
reset_calls = []
def fake(prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None, writing=False):
    reset_calls.append((lite, writing))
    if not writing: return {"what_is_new": "", "hooks": ["A dog saved the World Cup"], "facts": [
        {"claim": "Pickles became a national hero.", "evidence": [{"source": 1, "quote": "Pickles became a national hero overnight."}]}]}, "gemini-3.5-flash-lite"
    return {"facts": [{"claim": "The trophy was stolen in London in March 1966.", "evidence": [{"source": 1, "quote": "The 1966 World Cup trophy was stolen in London in March 1966."}]},
                      {"claim": "Pickles became a national hero.", "evidence": [{"source": 1, "quote": "Pickles became a national hero overnight."}]}]}, "groq:openai/gpt-oss-120b"
real = F.gemini; F.gemini = fake
ans, v, s, model = F.facts_from("x", texts, kinds, want=2)
assert len(s) == 2 and model == "gemini-3.5-flash-lite + groq:openai/gpt-oss-120b" and reset_calls == [(True, False), (True, True)], (s, model, reset_calls)
assert ans["hooks"] == ["A dog saved the World Cup"] and F.STATE["second_opinions"] == 1
reset_calls.clear(); ans, v, s, model = F.facts_from("x", texts, kinds, want=1)      # enough already: no second call
assert reset_calls == [(True, False)]
F.gemini = real
print("3 second opinion ok")

# 4. lite jobs in the writing order never reach Claude
os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "t"
F.STATE.clear(); F.STATE["models"] = ["gemini-3.5-flash-lite"]; F.STATE["spent_models"] = {"gemini-3.5-flash-lite"}
called = []
F.claude_call = lambda *a, **k: (called.append(1), ({"x": 1}, None))[1]
try: F.gemini("x", writing=True, lite=True); raise AssertionError("should fail")
except RuntimeError: pass
assert not called
os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN")
print("4 no Claude for facts ok")

# 5. narration citing Wikipedia is fixed, not failed
import writer as W, validate
b = {"beats": [{"say": "According to Wikipedia, a dog called Pickles found it."}, {"say": "It holds 90,000 fans, according to Wikipedia."}]}
W.unwiki(b)
assert [x["say"] for x in b["beats"]] == ["A dog called Pickles found it.", "It holds 90,000 fans."], b
assert "a reference" in W.pack_text({"topic": "t", "sources": [["T", "https://en.wikipedia.org/wiki/T", "Wikipedia", ""]], "verified": [], "one_source": []})
print("5 unwiki ok")
print("fact yield ok")
