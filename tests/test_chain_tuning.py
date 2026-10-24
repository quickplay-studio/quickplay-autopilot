"""Offline test of the model chain's time savers (24 October, audit M7): Groq answers within its configured budget and
retries once smaller on "too large"; a provider that refuses 3 calls (or refuses the key once) is passed over for the run;
in writing mode one timeout passes a Gemini model over and the wait is writing_timeout_s; the run log names the
providers passed over."""
import pathlib as _p, sys, tempfile as _t, json, os
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import factpack as F
F.USAGE = _p.Path(_t.mkdtemp(prefix="qp-test-")) / "claude_usage.json"
F.time.sleep = lambda s: None
for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "CF_API_TOKEN", "SAMBANOVA_API_KEY",
          "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
F.CFG.update({"max_tokens": {"groq": 3500}, "provider_refusals_before_skip": 3, "writing_timeout_s": 180, "writing_timeouts_before_skip": 1})


class R:
    def __init__(self, code, data, headers=None):
        self.status_code, self.data, self.ok, self.headers = code, data, code == 200, headers or {}
        self.text = json.dumps(data); self.content = self.text.encode()
    def json(self): return self.data


BODIES, SCRIPT, TIMEOUTS = [], [], []
import requests
def post(url, json=None, timeout=None, **kw):
    BODIES.append((url, json or {})); TIMEOUTS.append(timeout)
    nxt = SCRIPT.pop(0) if SCRIPT else R(500, {"error": "no script"})
    if isinstance(nxt, Exception): raise nxt
    return nxt
requests.post = post
ok = lambda: R(200, {"choices": [{"message": {"content": '{"a": 1}'}}]})
big = lambda: R(413, {"error": {"message": "Request too large for model: tokens per minute"}})


def reset():
    F.STATE.clear(); BODIES.clear(); SCRIPT.clear(); TIMEOUTS.clear()


# 1. Groq's answer budget is 3,500; on "too large" one retry at 60% (2,100), which answers
reset(); SCRIPT[:] = [big(), ok()]
ans, why = F.openai_chat("groq:openai/gpt-oss-120b", "https://g", "k", "openai/gpt-oss-120b", "p", 60, 0.1)
assert ans == {"a": 1} and [b["max_tokens"] for _, b in BODIES] == [3500, 2100], (ans, why, BODIES)
assert F.max_tokens_for("mistral:mistral-large-latest") == 6000
# twice too large: one refusal for the provider, not spent yet
reset(); SCRIPT[:] = [big(), big()]
ans, why = F.openai_chat("groq:openai/gpt-oss-120b", "https://g", "k", "openai/gpt-oss-120b", "p", 60, 0.1)
assert ans is None and "too large" in why and F.STATE["provider_refusals"] == {"groq": 1}, (why, F.STATE)
print("budget ok")

# 2. a provider that keeps refusing is passed over for the run: three server errors on three calls, then its other models
#    are skipped without a call; a refused key does it at once
reset()
os.environ["GROQ_API_KEY"] = "k"
F.STATE["provider_models"] = {"groq": ["groq:a", "groq:b", "groq:c"]}
F.chain = lambda: ["groq:a", "groq:b", "groq:c"]
SCRIPT[:] = [R(500, {})] * 9
for _ in range(3): F.others("p", only=None)
calls = len(BODIES)
assert F.provider_skipped("groq:c") and calls <= 9, (calls, F.STATE.get("provider_refusals"))
F.others("p"); assert len(BODIES) == calls                     # nothing more asked of Groq this run
assert "groq" in F.gemini_state()["providers passed over"]
reset(); F.STATE["provider_models"] = {"groq": ["groq:a", "groq:b", "groq:c"]}
SCRIPT[:] = [R(401, {"error": "invalid key"})]
assert F.others("p") is None and len(BODIES) == 1 and F.provider_skipped("groq:b")
os.environ.pop("GROQ_API_KEY", None)
print("provider skip ok")

# 3. writing: a Gemini model that timed out once is passed over; the wait is writing_timeout_s
reset()
F.STATE["models"] = ["gemini-flash-latest", "gemma-3-27b-it"]
os.environ["GEMINI_API_KEY"] = "test"
F.writing_order = lambda: ["gemini:gemini-flash-latest", "gemini:gemma-3-27b-it"]
gem_ok = R(200, {"candidates": [{"content": {"parts": [{"text": '{"b": 2}'}]}}]})
SCRIPT[:] = [requests.exceptions.ReadTimeout("slow"), gem_ok]
ans, model = F.gemini("p", writing=True)
assert ans == {"b": 2} and model == "gemma-3-27b-it" and TIMEOUTS[0] == 180, (ans, model, TIMEOUTS)
SCRIPT[:] = [gem_ok]
ans, model = F.gemini("p", writing=True)
assert model == "gemma-3-27b-it" and not any("gemini-flash-latest" in u for u, _ in BODIES[2:]), BODIES      # passed over after 1 timeout
os.environ.pop("GEMINI_API_KEY", None)
print("writing timeouts ok")
print("chain tuning ok")
