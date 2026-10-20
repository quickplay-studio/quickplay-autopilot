"""Offline test of factpack.gemini: per-minute limits wait and retry, daily limits move on, unreadable JSON is asked again."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import json, os, sys
sys.path.insert(0, REPO_DIR + "/pipeline")
import factpack as F
os.environ["GEMINI_API_KEY"] = "test"
F.time.sleep = lambda s: SLEPT.append(s)
F.STATE.clear(); F.STATE["models"] = ["gemini-flash-latest", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
SLEPT, CALLS = [], []
DAY = {"error": {"code": 429, "message": "You exceeded your current quota", "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
       "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "250"}]}]}}
MIN = {"error": {"code": 429, "message": "You exceeded your current quota", "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
       "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "quotaValue": "10"}]},
       {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"}]}}
ok = lambda text: (200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})
class R:
    def __init__(self, code, data): self.status_code, self.data, self.text, self.ok = code, data, json.dumps(data), code == 200
    def json(self): return self.data
SCRIPT = []
def post(url, **kw):
    model = url.split("/models/")[1].split(":")[0]; CALLS.append(model)
    code, data = SCRIPT.pop(0)
    return R(code, data)
import requests; requests.post = post

# 1. the main model's daily limit: marked spent with its limit, the next model answers
SCRIPT[:] = [(429, DAY), ok('{"a": 1}')]
print(F.gemini("x"), CALLS, F.STATE["quota_notes"])
assert CALLS == ["gemini-flash-latest", "gemini-3.6-flash"] and F.STATE["quota_notes"] == {"gemini-flash-latest": "daily limit 250"}

# 2. a per-minute limit waits (retryDelay + 2) and asks the same model again
CALLS.clear(); SCRIPT[:] = [(429, MIN), ok('{"b": 2}')]
print(F.gemini("x"), CALLS, SLEPT)
assert CALLS == ["gemini-3.6-flash", "gemini-3.6-flash"] and SLEPT == [23] and "gemini-3.6-flash" not in F.STATE["spent_models"]

# 3. JSON slips: a code fence and a trailing comma are forgiven; garbage is asked again
CALLS.clear(); SCRIPT[:] = [ok('```json\n{"c": [1, 2,],}\n```')]
print(F.gemini("x"))
CALLS.clear(); SCRIPT[:] = [ok('{"d": 1, oops'), ok('{"d": 1}')]
print(F.gemini("x"), CALLS)
assert CALLS == ["gemini-3.6-flash", "gemini-3.6-flash"]

# 4. lite jobs go to Lite first
CALLS.clear(); SCRIPT[:] = [ok('{"e": 1}')]
F.gemini("x", lite=True); assert CALLS == ["gemini-3.5-flash-lite"]
print(F.gemini_state())
print("gemini handling ok")
