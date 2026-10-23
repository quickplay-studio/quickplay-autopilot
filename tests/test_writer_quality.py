"""Offline test of the writer quality upgrade (Charlie, 23 October): the writing order by quality, Claude as capped editor
and test arm, and the writer and editor scores."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import json, os, sys, random
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import factpack as F
os.environ["GEMINI_API_KEY"] = "test"
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
F.time.sleep = lambda s: None
CALLS = []


class R:
    def __init__(self, code, data):
        self.status_code, self.data, self.ok, self.headers, self.text = code, data, code == 200, {}, json.dumps(data)
    def json(self): return self.data


SCRIPT = {}


def post(url, **kw):
    CALLS.append(url.split("/models/")[1].split(":")[0] if "/models/" in url else url)
    for frag, lst in SCRIPT.items():
        if frag in url and lst: return lst.pop(0)
    return R(500, {"error": "no script"})


def get(url, **kw):
    if "groq" in url: return R(200, {"data": [{"id": i} for i in ("llama-3.1-8b-instant", "qwen/qwen3-32b", "llama-3.3-70b-versatile",
                                                                     "moonshotai/kimi-k2-instruct", "meta-llama/llama-4-scout-17b-16e-instruct",
                                                                     "whisper-large-v3")]})
    if "openrouter" in url: return R(200, {"data": [{"id": "qwen/qwen2.5-vl-72b-instruct:free", "context_length": 128000},
                                                    {"id": "deepseek/deepseek-chat-v3-0324:free", "context_length": 64000},
                                                    {"id": "openai/gpt-oss-20b:free", "context_length": 128000}]})
    return R(500, {})


import requests; requests.post = post; requests.get = get
gem = lambda text: R(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})
oai = lambda text: R(200, {"choices": [{"message": {"content": text}}]})
GEM = ("gemini-flash-latest", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemma-3-27b-it")


def reset():
    F.STATE.clear(); F.STATE["models"] = list(GEM); CALLS.clear(); SCRIPT.clear()


# 1. quality and writing order: big keyed models, Flash, Gemma, weaker keyed, then Lite, local, Claude
assert F.quality("groq:moonshotai/kimi-k2-instruct") == 5 and F.quality("openrouter:qwen/qwen2.5-vl-72b-instruct:free") == 1
assert F.quality("groq:llama-3.1-8b-instant") == 1 and F.quality("groq:llama-3.3-70b-versatile") == 4
os.environ["GROQ_API_KEY"] = "g"; os.environ["OPENROUTER_API_KEY"] = "o"; os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "t"
os.environ["LLAMA_SERVER"] = "/x/llama-server"
reset()
order = F.writing_order()
assert F.provider_models("groq")[:2] == ["groq:moonshotai/kimi-k2-instruct", "groq:llama-3.3-70b-versatile"], F.provider_models("groq")
assert F.provider_models("openrouter")[0] == "openrouter:deepseek/deepseek-chat-v3-0324:free", F.provider_models("openrouter")
i = order.index
assert i("groq:moonshotai/kimi-k2-instruct") < i("gemini:gemini-flash-latest") < i("gemini:gemma-3-27b-it") < i("groq:qwen/qwen3-32b")
assert i("groq:qwen/qwen3-32b") < i("gemini:gemini-3.5-flash-lite") < order.index("local:" + F.local_name()) < i("claude:sonnet") == len(order) - 1
assert "groq:whisper-large-v3" not in order
print("1 order ok", order[:4])
os.environ.pop("LLAMA_SERVER")

# 2. writing=True: Groq's Kimi writes first; a spent Kimi passes to the next, Gemini Flash gets 240 seconds
reset(); SCRIPT["api.groq.com"] = [oai('{"w": 1}')]
ans, model = F.gemini("x", writing=True, timeout=150)
assert model == "groq:moonshotai/kimi-k2-instruct" and CALLS == ["https://api.groq.com/openai/v1/chat/completions"], (model, CALLS)
reset()
for m in F.provider_models("groq") + F.provider_models("openrouter"): F.STATE["spent_models"] = F.STATE.get("spent_models", set()) | {m}
TIMEOUTS = []
def post2(url, **kw):
    TIMEOUTS.append(kw.get("timeout")); return post(url, **kw)
requests.post = post2
SCRIPT["gemini-flash-latest"] = [gem('{"w": 2}')]
ans, model = F.gemini("x", writing=True, timeout=150)
assert model == "gemini-flash-latest" and TIMEOUTS == [240], (model, TIMEOUTS)
requests.post = post
# Lite only after every other free model; jobs that aren't writing keep the old order (Gemini first)
reset()
for m in F.provider_models("groq") + F.provider_models("openrouter") + ["gemini-flash-latest", "gemini-3.6-flash", "gemma-3-27b-it"]:
    F.STATE.setdefault("spent_models", set()).add(m)
SCRIPT["gemini-3.5-flash-lite"] = [gem('{"w": 3}')]
assert F.gemini("x", writing=True)[1] == "gemini-3.5-flash-lite"
reset(); SCRIPT["gemini-flash-latest"] = [gem('{"w": 4}')]
assert F.gemini("x")[1] == "gemini-flash-latest" and CALLS == ["gemini-flash-latest"]
# a preferred model goes first in the writing order too
reset(); SCRIPT["gemini-3.6-flash"] = [gem('{"w": 5}')]
assert F.gemini("x", writing=True, prefer="gemini:gemini-3.6-flash")[1] == "gemini-3.6-flash" and CALLS == ["gemini-3.6-flash"]
# a prompt too large for one model (Groq's tokens-a-minute cap) skips that call only; the fourth time, the model is passed over
reset(); SCRIPT["api.groq.com"] = [R(413, {"error": {"message": "Request too large on tokens per minute (TPM)"}}), oai('{"w": 6}')]
SCRIPT["openrouter.ai"] = [oai('{"w": 7}')]
assert F.gemini("big", writing=True)[1] == "openrouter:deepseek/deepseek-chat-v3-0324:free"
assert F.gemini("small", writing=True)[1] == "groq:moonshotai/kimi-k2-instruct"
F.STATE["too_large"] = {"groq:moonshotai/kimi-k2-instruct": 3}; SCRIPT["api.groq.com"] = [R(413, {"error": "too large"})]
F.openai_chat("groq:moonshotai/kimi-k2-instruct", "https://api.groq.com/openai/v1", "g", "m", "x", 10, 0.1)
assert "groq:moonshotai/kimi-k2-instruct" in F.STATE["spent_models"]
print("2 writing chain ok")

# 3. choose_writer: never Lite, local or Claude; untested strong models are favoured by the order
import writer as W
reset()
W.ROOT = SCRATCH; (SCRATCH / "analytics").mkdir(); (SCRATCH / "status").mkdir()
W.USAGE = SCRATCH / "status" / "claude_usage.json"
picks = [W.choose_writer(f"QD-{n:03d}") for n in range(60)]
assert not any(p.startswith("claude:") or "lite" in p for p in picks), set(picks)
assert picks.count("groq:moonshotai/kimi-k2-instruct") > picks.count("gemini:gemma-3-27b-it"), picks
print("3 choice ok")

# 4. Claude's test arm: about 1 board in 4, capped per UK day
arm = [W.claude_arm(f"QD-{n:03d}") for n in range(200)]
share = sum(1 for a in arm if a) / len(arm)
assert 0.15 < share < 0.35 and set(arm) <= {None, "claude:sonnet"}, share
W.USAGE.write_text(json.dumps({"day": W.usage()["day"], "edits": 0, "writes": 8}))
assert not any(W.claude_arm(f"QD-{n:03d}") for n in range(50))
W.USAGE.write_text(json.dumps({"day": "2020-01-01", "edits": 99, "writes": 99}))
assert W.usage()["writes"] == 0                                  # a new UK day starts at zero
# a Claude arm that doesn't earn more views fades
(SCRATCH / "analytics" / "models.json").write_text(json.dumps({"writers": {"claude:sonnet": {"n": 8, "views_vs_typical": 0.5},
    "gemini:gemini-flash-latest": {"n": 20, "views_vs_typical": 1.0}}, "editors": {"claude": {"n": 10, "views_vs_typical": 0.6},
    "none": {"n": 30, "views_vs_typical": 1.2}}}))
w, e = W.claude_shares()
assert w < 0.1 and e < 0.3, (w, e)
(SCRATCH / "analytics" / "models.json").unlink()
assert W.claude_shares() == (0.25, 1.0)
print("4 arm ok")

# 5. the editor: a good edit is kept and recorded; one that drops a number or adds a dash keeps the original
board = {"id": "QD-500", "writer": "groq:moonshotai/kimi-k2-instruct", "meta": {"title": "Old title", "alt_title": "Alt", "comment": "Which?", "facts": []},
         "beats": [{"say": "Minecraft has sold 300 million copies worldwide"}, {"say": "Middle line here"}, {"say": "That is the most ever"}]}
CHECKS = []
W.validate.check = lambda b: ([], [])
W.fact_check = lambda b, p: CHECKS.append(b["meta"]["title"]) or []
reply = {}
W.factpack.claude_call = lambda label, prompt, timeout: (reply["v"], None)
reply["v"] = {"title": "The game that sold 300 million", "alt_title": "Bigger than Tetris?", "comment": "Have you played it?",
              "first": "Minecraft sold 300 million copies around the world", "last": "Nothing has ever sold more"}
b, note = W.claude_edit(board, {}, "news", "n")
assert b["editor"] == "claude" and b["meta"]["title"] == "The game that sold 300 million" and b["beats"][0]["say"].startswith("Minecraft sold")
assert board["meta"]["title"] == "Old title" and "edited by Claude" in note and W.usage()["edits"] == 1 and CHECKS
reply["v"] = {"title": "New — title", "first": "Minecraft sold a lot of copies worldwide, honestly"}
b, note = W.claude_edit(dict(board, id="QD-501"), {}, "news", "n")
assert "editor" not in b and b["meta"]["title"] == "Old title" and "kept the original" in note, note
W.fact_check = lambda b, p: ["beat 1: not in the pack"]
reply["v"] = {"title": "Fine title"}
b, note = W.claude_edit(dict(board, id="QD-502"), {}, "news", "n")
assert "editor" not in b and "not in the pack" in note
b, note = W.claude_edit(dict(board, id="QD-503", writer="claude:sonnet"), {}, "news", "n")    # Claude never edits its own
assert note == "n"
W.USAGE.write_text(json.dumps({"day": W.usage()["day"], "edits": 24, "writes": 0}))
assert W.claude_edit(dict(board, id="QD-504"), {}, "news", "n")[1] == "n"
print("5 editor ok")

# 6. scores: writers, editors (Claude-written left out) and pairs
import analytics as A
rows = [{"writer": "groq:k", "editor": "claude", "look_score": 1.2, "views_vs_typical": 2},
        {"writer": "groq:k", "editor": "", "look_score": 0.8, "views_vs_typical": 1},
        {"writer": "claude:sonnet", "editor": "", "look_score": 1.0, "views_vs_typical": 1}]
out = A.writer_scores(rows)
assert set(out["editors"]) == {"claude", "none"} and out["editors"]["none"]["n"] == 1
assert set(out["combos"]) == {"groq:k + claude", "groq:k + no edit", "claude:sonnet + no edit"} and out["writers"]["groq:k"]["n"] == 2
print("6 scores ok")
for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"): os.environ.pop(k, None)
print("writer quality ok")
