"""Offline test of the model chain behind factpack.gemini(): Gemma on the Gemini API, the keyed free providers (Groq,
Cerebras, Mistral, OpenRouter), the open model on the runner and Claude last; the writer's model choice; writer scores."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import json, math, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import factpack as F
F.USAGE = _p.Path(SCRATCH) / "claude_usage.json"     # never the real usage file
os.environ["GEMINI_API_KEY"] = "test"
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
F.time.sleep = lambda s: SLEPT.append(s)
SLEPT, CALLS, BODIES = [], [], []
DAY = {"error": {"code": 429, "message": "quota", "details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]}]}}


class R:
    def __init__(self, code, data, headers=None):
        self.status_code, self.data, self.ok, self.headers = code, data, code == 200, headers or {}
        self.text = json.dumps(data)
    def json(self): return self.data


SCRIPT = {}     # url fragment -> list of responses


def post(url, **kw):
    label = url.split("/models/")[1].split(":")[0] if "/models/" in url else url
    CALLS.append(label); BODIES.append(kw.get("json") or {})
    for frag, lst in SCRIPT.items():
        if frag in url and lst: return lst.pop(0)
    return R(500, {"error": "no script for " + url})


def get(url, **kw):
    if "groq" in url: return R(200, {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"}]})
    if "cerebras" in url: return R(200, {"data": [{"id": "gpt-oss-120b"}]})
    if "openrouter" in url: return R(200, {"data": [{"id": "a/b:free", "context_length": 8000}, {"id": "c/d:free", "context_length": 128000}, {"id": "e/f"}]})
    return R(500, {})


import requests; requests.post = post; requests.get = get
gem = lambda text: R(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})
oai = lambda text: R(200, {"choices": [{"message": {"content": text}}]})


def reset(models=("gemini-flash-latest", "gemini-3.5-flash-lite", "gemma-3-27b-it")):
    F.STATE.clear(); F.STATE["models"] = list(models); CALLS.clear(); BODIES.clear(); SCRIPT.clear()


# 1. Gemma: no JSON mode or schema sent, the fenced text answer is read; a model name without a provider stays bare
reset(); SCRIPT["gemini-flash-latest"] = [R(429, DAY)]; SCRIPT["gemini-3.5-flash-lite"] = [R(429, DAY)]
SCRIPT["gemma-3-27b-it"] = [gem('Sure!\n```json\n{"a": 1}\n```')]
ans, model = F.gemini("x", schema={"type": "OBJECT"})
assert ans == {"a": 1} and model == "gemma-3-27b-it", (ans, model)
assert "responseMimeType" not in BODIES[-1]["generationConfig"] and "responseSchema" not in BODIES[-1]["generationConfig"]
assert BODIES[-1]["contents"][0]["parts"][0]["text"].endswith("no other text.")
print("1 gemma ok", F.STATE["quota_notes"])

# 2. every Gemini model spent and no keys: the run is marked spent, as before
reset(); SCRIPT["gemma-3-27b-it"] = [R(429, DAY)]
for m in ("gemini-flash-latest", "gemini-3.5-flash-lite"): SCRIPT[m] = [R(429, DAY)]
try: F.gemini("x"); raise AssertionError("should fail")
except RuntimeError as e: print("2 no models:", e)
assert F.STATE.get("spent") and F.chain() == []

# 3. keyed providers: Groq's daily limit marks it spent, Cerebras answers; names carry the provider; lite skips nothing here
os.environ["GROQ_API_KEY"] = "g"; os.environ["CEREBRAS_API_KEY"] = "c"; os.environ["OPENROUTER_API_KEY"] = "o"
reset()
for m in ("gemini-flash-latest", "gemini-3.5-flash-lite", "gemma-3-27b-it"): SCRIPT[m] = [R(429, DAY)]
SCRIPT["api.groq.com"] = [R(429, {"error": {"message": "Rate limit reached for requests per day (RPD)"}})]
SCRIPT["api.cerebras.ai"] = [oai('{"b": 2}')]
assert F.chain() == ["groq:llama-3.3-70b-versatile", "cerebras:gpt-oss-120b", "openrouter:c/d:free", "openrouter:a/b:free"], F.chain()
ans, model = F.gemini("x")
assert ans == {"b": 2} and model == "cerebras:gpt-oss-120b", (ans, model)
assert F.STATE["quota_notes"]["groq:llama-3.3-70b-versatile"] == "daily limit"
assert BODIES[-1]["response_format"] == {"type": "json_object"} and BODIES[-1]["messages"][1]["content"] == "x"
assert not F.STATE.get("spent")
print("3 providers ok", F.gemini_state()["answers"])

# 4. a per-minute limit waits and asks the same provider again; a 400 about response_format drops JSON mode for that model
CALLS.clear(); SLEPT.clear()
SCRIPT["api.cerebras.ai"] = [R(429, {"error": "slow down"}, {"retry-after": "7"}), R(400, {"error": "response_format not supported"}), oai('<think>hm</think>{"c": 3}')]
ans, model = F.gemini("x")
assert ans == {"c": 3} and SLEPT == [9] and "response_format" not in BODIES[-1], (ans, SLEPT, BODIES[-1].keys())
print("4 waits ok")

# 5. prefer: a provider model is tried first while Gemini still has quota; a bare Gemini name goes first too
reset(); SCRIPT["api.cerebras.ai"] = [oai('{"d": 4}')]
ans, model = F.gemini("x", prefer="cerebras:gpt-oss-120b")
assert model == "cerebras:gpt-oss-120b" and CALLS == ["https://api.cerebras.ai/v1/chat/completions"], CALLS
CALLS.clear(); SCRIPT["gemini-3.5-flash-lite"] = [gem('{"e": 5}')]
ans, model = F.gemini("x", prefer="gemini:gemini-3.5-flash-lite")
assert model == "gemini-3.5-flash-lite" and CALLS == ["gemini-3.5-flash-lite"], CALLS
print("5 prefer ok")

# 6. Claude last: never for lite jobs; counted and capped per run; a stubbed CLI answers
os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "t"
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY"): os.environ.pop(k)
reset()
for m in ("gemini-flash-latest", "gemini-3.5-flash-lite", "gemma-3-27b-it"): SCRIPT[m] = [R(429, DAY)]
assert F.chain() == ["claude:sonnet"]
RUNS = []
class P:
    def __init__(self, out, code=0): self.stdout, self.stderr, self.returncode = out, "", code
import subprocess, shutil
shutil.which = lambda x: "/usr/bin/claude"
subprocess.run = lambda cmd, **kw: (RUNS.append((cmd, kw.get("input"))), P(json.dumps({"result": '{"f": 6}', "is_error": False})))[1]
try: F.gemini("x", lite=True); raise AssertionError("lite must not use Claude")
except RuntimeError as e: print("6 lite skips Claude:", e)
assert not F.STATE.get("spent")
ans, model = F.gemini("x")
assert ans == {"f": 6} and model == "claude:sonnet" and RUNS[-1][1] == "x" and "--model" in RUNS[-1][0] and "sonnet" in RUNS[-1][0]
assert F.gemini_state()["claude calls"] == 1
F.STATE["claude_calls"] = int(F.CFG.get("claude_max_per_run", 12))
try: F.gemini("x"); raise AssertionError("cap")
except RuntimeError as e: print("6 cap:", e)
assert F.STATE.get("spent") and F.STATE["quota_notes"]["claude:sonnet"] == "run cap"
os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN")

# 7. the writer's choice: Thompson sampling over writers with quota, early-try boost, never Claude; the board records it
os.environ["GROQ_API_KEY"] = "g"; os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "t"
reset()
import writer as W
stats = {"writers": {"gemini:gemini-flash-latest": {"n": 40, "score": 0.7}, "groq:llama-3.3-70b-versatile": {"n": 40, "score": 1.3}}}
saved = (W.ROOT / "analytics" / "models.json")
backup = saved.read_bytes() if saved.exists() else None
saved.write_text(json.dumps(stats))
picks = {W.choose_writer(f"QD-{i:03d}") for i in range(30)}
saved.write_bytes(backup) if backup is not None else saved.unlink()
assert "claude:sonnet" not in picks and "groq:llama-3.3-70b-versatile" in picks, picks
assert picks - {"groq:llama-3.3-70b-versatile", "gemini:gemini-flash-latest", "gemini:gemini-3.5-flash-lite", "gemini:gemma-3-27b-it"} == set()
print("7 choice ok", picks)
os.environ.pop("GROQ_API_KEY"); os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN")

# 8. writer scores from rows, like look scores
import analytics as A
rows = [{"writer": "gemini:gemini-flash-latest", "look_score": 0.8, "views_vs_typical": 0.5}, {"writer": "gemini:gemini-flash-latest", "look_score": 1.2, "views_vs_typical": 2},
        {"writer": "groq:x", "look_score": "", "views_vs_typical": ""}, {"writer": "", "look_score": 1.0}]
out = A.writer_scores(rows)["writers"]
# the score is shrunk on the log scale (24 October: one breakout at 27.7x gave a 2-Short model a score of 20.9)
shrunk = round(math.exp((math.log(0.8) + math.log(1.2)) / (2 + A.WRITER_SHRINK)), 3)
assert out["gemini:gemini-flash-latest"] == {"n": 2, "shorts": 2, "score": shrunk, "views_vs_typical": 1.25} and out["groq:x"] == {"n": 0, "shorts": 1}, out
lucky = A.writer_scores([{"writer": "w", "look_score": 27.7}, {"writer": "w", "look_score": 14.0}])["writers"]["w"]["score"]
assert lucky < 3, lucky
import drivers as D
assert "writer" in D.TESTED
print("8 scores ok")

# 9. weak Shorts for a remake: under half of typical after 48 hours, none remade yet
import csv, datetime as dt
p = W.ROOT / "analytics" / "shorts.csv"; backup = p.read_bytes() if p.exists() else None
old = (W.NOW - dt.timedelta(hours=60)).isoformat(timespec="minutes"); new = (W.NOW - dt.timedelta(hours=10)).isoformat(timespec="minutes")
p.write_text("short,title,posted,views_vs_typical\nQD-001,Weak one,%s,0.3\nQD-002,Fresh one,%s,0.2\nQD-003,Fine one,%s,1.4\n" % (old, new, old))
w = W.weak()
if backup is not None: p.write_bytes(backup)
else: p.unlink()
assert [r["short"] for r in w] == ["QD-001"], w
print("9 weak ok")
print("model chain ok")

# Wikipedia data tables become quotable rows for the fact checker (factpack.wiki_tables)
html = """<html><body><p>Intro.</p><table class="infobox"><tr><td>x</td></tr></table>
<table class="wikitable sortable"><tbody><tr><th>Rank</th><th>Title</th><th>Sales</th></tr>
<tr><td>1</td><td><a>Minecraft</a><sup>[1]</sup></td><td>300,000,000</td></tr><tr><td>2</td><td>Grand Theft Auto V</td><td>215,000,000<sup>[2]</sup></td></tr></tbody></table></body></html>"""
rows = F.wiki_tables(html)
assert rows[:3] == ["Rank | Title | Sales", "1 | Minecraft | 300,000,000", "2 | Grand Theft Auto V | 215,000,000"], rows
_, single = F.verify([{"claim": "Minecraft is number one with 300,000,000 copies sold.", "evidence": [{"source": 1, "quote": "1 | Minecraft | 300,000,000"}]}],
                     {1: F.norm("Intro.\n\n" + "\n".join(rows))}, {1: "wikipedia"})
assert len(single) == 1, single
print("wiki tables ok")


# Cloudflare Workers AI (24 October): dormant until both secrets exist; the account id goes into the base; its preferred
# models when it lists none; its free daily allocation ("neurons") used up marks the model spent
import factpack as F3, requests as _rq3
F3.STATE.clear(); F3.CFG = dict(F3.CFG, providers={})
os.environ.pop("CF_ACCOUNT_ID", None); os.environ["CF_API_TOKEN"] = "t"
assert F3.provider_base("cloudflare") is None and F3.provider_models("cloudflare") == []
F3.STATE.clear(); os.environ["CF_ACCOUNT_ID"] = "acc1"
assert F3.provider_base("cloudflare") == "https://api.cloudflare.com/client/v4/accounts/acc1/ai/v1"
class _R3:
    def __init__(self, code, data): self.status_code, self.data, self.ok, self.headers, self.text = code, data, code == 200, {}, json.dumps(data)
    def json(self): return self.data
_g, _p = _rq3.get, _rq3.post
_rq3.get = lambda url, **kw: _R3(404, {"errors": [{"message": "not found"}]})
assert F3.provider_models("cloudflare")[0] == "cloudflare:@cf/openai/gpt-oss-120b"
_rq3.post = lambda url, **kw: _R3(429, {"errors": [{"message": "You have used up your daily free allocation of 10,000 neurons"}]})
ans, why = F3.openai_chat("cloudflare:@cf/openai/gpt-oss-120b", F3.provider_base("cloudflare"), "t", "@cf/openai/gpt-oss-120b", "x", 30, 0.2)
assert ans is None and "cloudflare:@cf/openai/gpt-oss-120b" in F3.STATE["spent_models"], why
_rq3.get, _rq3.post = _g, _p
for k in ("CF_ACCOUNT_ID", "CF_API_TOKEN"): os.environ.pop(k, None)
print("cloudflare ok")
