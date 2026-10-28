"""Offline test of the FreeLLMAPI router in the line (27 October, pipeline/freellm.py, factpack.py, keys.py): the router's config
holds only the keys for platforms Quickplay does not call directly and never a Gemini, Groq, Claude or other main key; the
provider is dormant without FREELLM_KEY; its model list is read, filtered and cut to the top 6; freellm:auto is recorded as the
model that answered (X-Routed-Via); the writer test ignores freellm labels; web search is capped and off without the key and its
extra sources pass the trend finder's outlet list; the image digest guard; the hub rows. HTTP and Docker are stubbed.
Dashes are written as escapes: no em or en dash in this file."""
import json, os, pathlib as _p, sqlite3, sys, tempfile
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(tempfile.mkdtemp(prefix="qp-freellm-"))
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
for k in ("FREELLM_KEY", "FREELLM_BASE", "GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "CF_API_TOKEN",
          "SAMBANOVA_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN"):
    os.environ.pop(k, None)
os.environ["GEMINI_API_KEY"] = "test"
import freellm as FL
import factpack as F
import keys as K
FL.STATUS = SCRATCH / "freellm.json"; K.FREELLM = FL.STATUS            # never the real status file
F.USAGE = SCRATCH / "claude_usage.json"
EM, EN = chr(0x2014), chr(0x2013)      # written as code points: this file holds no em or en dash
BASE = "http://127.0.0.1:3001/v1"

# 1. the router's config: keyless tiers, a disabled AI Horde, and only the mapped secrets that are set; never a main key
env = {"TAVILY_API_KEY": "tvly-1", "OLLAMA_API_KEY": " oll-2 ", "EXA_API_KEY": "", "GEMINI_API_KEY": "gem-SECRET", "GROQ_API_KEY": "groq-SECRET",
       "OPENROUTER_API_KEY": "or-SECRET", "MISTRAL_API_KEY": "mis-SECRET", "CF_API_TOKEN": "cf-SECRET", "CF_ACCOUNT_ID": "acct-SECRET",
       "SAMBANOVA_API_KEY": "sn-SECRET", "CEREBRAS_API_KEY": "cb-SECRET", "CLAUDE_CODE_OAUTH_TOKEN": "claude-SECRET", "ANTHROPIC_API_KEY": "anth-SECRET"}
cfg = FL.config_json(env, "run@example.com", "pw-pw-pw-pw")
text = json.dumps(cfg)
assert "SECRET" not in text, "a main key reached the router's config"
assert not set(FL.KEYS) & set(FL.FORBIDDEN), "a forbidden secret is mapped"
assert cfg["admin"] == {"email": "run@example.com", "password": "pw-pw-pw-pw"}
plats = {k["platform"]: k for k in cfg["keys"]}
assert set(plats) == {"kilo", "ovh", "parallel", "keenable", "aihorde", "tavily", "ollama"}, sorted(plats)
assert plats["tavily"]["key"] == "tvly-1" and plats["ollama"]["key"] == "oll-2", "keys are trimmed"
assert all("key" not in plats[p] for p in ("kilo", "ovh", "parallel", "keenable")), "keyless tiers carry no key"
assert plats["aihorde"]["enabled"] is False, "AI Horde (volunteer commons) is never switched on"
assert not {"cohere", "nvidia", "github", "custom"} & set(plats) and "customProviders" not in cfg
assert FL.missing_keys(env) == ["EXA_API_KEY", "FIRECRAWL_API_KEY", "LINKUP_API_KEY", "LLM7_API_KEY"], FL.missing_keys(env)
assert {s: v[0] for s, v in FL.KEYS.items()} == {"TAVILY_API_KEY": "tavily", "EXA_API_KEY": "exa", "FIRECRAWL_API_KEY": "firecrawl",
                                               "LINKUP_API_KEY": "linkup", "OLLAMA_API_KEY": "ollama", "LLM7_API_KEY": "llm7"}
empty = FL.config_json({}, "a@example.com", "x" * 12)
assert {k["platform"] for k in empty["keys"]} == {"kilo", "ovh", "parallel", "keenable", "aihorde"} and all("key" not in k for k in empty["keys"])
print("1 config ok")

# 2. the image digest guard and the pin
assert FL.digest_check("", "sha256:" + "a" * 64)[0], "nothing pinned yet: the first pull records it"
assert FL.digest_check("sha256:" + "a" * 64, "sha256:" + "a" * 64)[0]
ok, why = FL.digest_check("sha256:" + "a" * 64, "sha256:" + "b" * 64)
assert not ok and "changed" in why, (ok, why)
assert not FL.digest_check("sha256:" + "a" * 64, "")[0], "no digest, no start"
import re as _re
cfg_text = _re.sub(r'("freellm"\s*:\s*\{[^{}]*?"digest"\s*:\s*)"[^"]*"', r'\1""', _p.Path("config.json").read_text(), count=1)       # as first written: no digest yet
pinned = FL.pin_text(cfg_text, "sha256:" + "c" * 64)
assert pinned and json.loads(pinned)["freellm"]["digest"] == "sha256:" + "c" * 64 and json.loads(pinned)["viral"] == json.loads(cfg_text)["viral"]
assert pinned.replace("sha256:" + "c" * 64, "") == cfg_text, "only the digest changed: the hand-made layout stays"
assert FL.pin_text(pinned, "sha256:" + "d" * 64) is None, "a recorded digest is never overwritten"
assert json.loads(cfg_text)["freellm"]["tag"] == "v0.16.6" and json.loads(cfg_text)["freellm"]["search_per_run"] == 20
print("2 digest ok")

# 3. the unified key is read from the router's SQLite settings table (read only); the router's own model entries are not models
db = SCRATCH / FL.DB_FILE
con = sqlite3.connect(db); con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
con.execute("INSERT INTO settings VALUES ('unified_api_key', 'freellmapi-abc')"); con.commit(); con.close()
assert FL.read_key_db(db) == "freellmapi-abc" and FL.read_key_db(SCRATCH / "none.db") is None
LISTING = {"object": "list", "data": [
    {"id": "auto", "available": True}, {"id": "fusion", "available": True}, {"id": "auto:coding", "available": True},
    {"id": "gpt-oss-120b", "available": True, "execution_status": "ready"}, {"id": "llama-3.1-8b-instant", "available": True},
    {"id": "kimi-k2-instruct", "available": True}, {"id": "whisper-large-v3", "available": True}, {"id": "deepseek-v3.1", "available": True},
    {"id": "qwen3-235b-a22b", "available": True}, {"id": "llama-3.3-70b", "available": True}, {"id": "mistral-medium", "available": True},
    {"id": "gemma-3-27b", "available": True}, {"id": "glm-4.6", "available": True}, {"id": "spent-one", "available": True, "execution_status": "exhausted"},
    {"id": "nokey-one", "available": False, "execution_status": "needsKey"}]}
ids = FL.chat_models(LISTING)
assert "auto" not in ids and "fusion" not in ids and "auto:coding" not in ids and "spent-one" not in ids and "nokey-one" not in ids, ids
assert ids[:2] == ["gpt-oss-120b", "llama-3.1-8b-instant"] and len(ids) == 10, ids
print("3 key and models ok")

# 4. the provider is dormant without FREELLM_KEY: no models, no catch-all, nothing in the chain or the writing order, no call made
class R:
    def __init__(self, code, data, headers=None):
        self.status_code, self.data, self.ok, self.headers = code, data, code == 200, headers or {}
        self.text = json.dumps(data)
    def json(self): return self.data


GETS, POSTS, REPLY = [], [], {}


def get(url, **kw):
    GETS.append(url)
    if url == BASE + "/models": return R(200, LISTING)
    return R(500, {})


def post(url, **kw):
    POSTS.append((url, kw.get("json"), kw.get("headers")))
    if url.endswith("/search"): return REPLY.get("search") or R(500, {})
    return REPLY.get("chat") or R(500, {})


import requests; requests.get, requests.post = get, post
F.time.sleep = lambda s: None
GEM = ["gemini-flash-latest", "gemini-3.5-flash-lite", "gemma-3-27b-it"]


def reset():
    F.STATE.clear(); F.STATE["models"] = list(GEM); GETS.clear(); POSTS.clear(); REPLY.clear()


reset()
assert F.provider_models("freellm") == [] and F.catch_all() == [] and not F.freellm_on()
assert not any(m.startswith("freellm:") for m in F.chain() + F.writing_order())
assert F.search("anything") == [] and POSTS == [] and not any("127.0.0.1" in u for u in GETS), "dormant: no search, no call"
os.environ["FREELLM_KEY"] = "freellmapi-abc"
assert F.provider_models("freellm") == [] and not F.freellm_on(), "a key without the base is still dormant"
print("4 dormant ok")

# 5. models parsing: text models only, usable ones, quality() order (the router's order breaks ties), top 6 (config top_models)
os.environ["FREELLM_BASE"] = BASE + "/"
reset()
got = F.provider_models("freellm")
assert got == ["freellm:gpt-oss-120b", "freellm:kimi-k2-instruct", "freellm:deepseek-v3.1", "freellm:qwen3-235b-a22b", "freellm:glm-4.6", "freellm:llama-3.3-70b"], got
assert F.quality("freellm:llama-3.3-70b") == 4 and F.quality("freellm:gpt-oss-120b") == 5 and BASE + "/models" in GETS
assert F.catch_all() == ["freellm:auto"] and F.chain()[-1] == "freellm:auto" and F.chain()[:6] == got, F.chain()
order = F.writing_order()
i_auto, i_lite = order.index("freellm:auto"), order.index("gemini:gemini-3.5-flash-lite")
assert i_auto == i_lite - 1, "freellm:auto is the last keyed entry, just before Gemini Lite"
assert all(order.index(m) < order.index("gemini:gemini-flash-latest") for m in got[:5]), "the strong ones come before Gemini Flash"
F.CFG.setdefault("freellm", {})["top_models"] = 8
reset(); got8 = F.provider_models("freellm")
assert len(got8) == 8 and "freellm:gemma-3-27b" in got8 and F.quality("freellm:gemma-3-27b") < 4
o8 = F.writing_order()
assert o8.index("freellm:gemma-3-27b") > o8.index("gemini:gemma-3-27b-it") and o8.index("freellm:gemma-3-27b") < o8.index("freellm:auto"), o8
F.CFG["freellm"]["top_models"] = 6
reset()
print("5 models ok", got[:3])

# 6. freellm:auto is recorded as the model that answered (X-Routed-Via), never "auto"; named models keep their label
def chat(content='{"a": 1}', via=None):
    return R(200, {"choices": [{"message": {"content": content}}]}, {"X-Routed-Via": via} if via else {})


reset(); REPLY["chat"] = chat(via="ovh/gpt-oss-120b")
ans, label = F.others("p", only="freellm:auto")
assert ans == {"a": 1} and label == "freellm:ovh/gpt-oss-120b", (ans, label)
assert POSTS[-1][0] == BASE + "/chat/completions" and POSTS[-1][1]["model"] == "auto" and POSTS[-1][2]["Authorization"] == "Bearer freellmapi-abc"
assert F.STATE["calls"] == {"freellm:ovh/gpt-oss-120b": 1}, F.STATE["calls"]
assert F.quality(label) == 5 and F.writer_arm_of(label) == "other", "the real model is judged by its own name, outside the writer test"
reset(); REPLY["chat"] = chat(via="kilo/nvidia%2Fnemotron-3-super-120b-a12b%3Afree")
assert F.others("p", only="freellm:auto")[1] == "freellm:kilo/nvidia/nemotron-3-super-120b-a12b:free"
reset(); REPLY["chat"] = chat(via=None)
assert F.others("p", only="freellm:auto")[1] == "freellm:auto", "no header: the label stays (nothing to read)"
reset(); REPLY["chat"] = chat(via="ovh/gpt-oss-120b")
ans, label = F.others("p", only="freellm:kimi-k2-instruct")
assert label == "freellm:kimi-k2-instruct" and POSTS[-1][1]["model"] == "kimi-k2-instruct", "a named model keeps its own label"
# through the one door, writing=True: the fallback walks to the router when everything before it is spent
reset(); REPLY["chat"] = chat(via="ovh/gpt-oss-120b")
F.STATE["spent_models"] = {"gemini-flash-latest", "gemini-3.5-flash-lite", "gemma-3-27b-it"} | set(F.provider_models("freellm"))
ans, label = F.gemini("p", writing=True)
assert label == "freellm:ovh/gpt-oss-120b", label
print("6 auto label ok")

# 7. the writer test and the writer's first choice
assert F.writer_arm_of("groq:openai/gpt-oss-120b") == "gpt-oss-120b" and F.writer_arm_of("freellm:gpt-oss-120b") == "other"
assert F.writer_arm_of("freellm:ovh/gpt-oss-120b") == "other" and F.writer_arm_of("gemini:gemini-flash-latest") == "gemini flash"
reset()
assert F.writer_test_label("gpt-oss-120b", order=["freellm:gpt-oss-120b", "groq:openai/gpt-oss-120b"]) == "groq:openai/gpt-oss-120b"
assert F.writer_test_label("gpt-oss-120b", order=["freellm:gpt-oss-120b"]) is None, "a freellm model never serves the arm"
import writer as W
reset()
picks = {W.choose_writer(f"QD-{i:03d}") for i in range(60)}
assert "freellm:auto" not in picks and None not in picks, picks
assert all(not str(p).startswith("claude:") for p in picks)
print("7 writer ok", len(picks))

# 8. web search: off without the key, capped by config freellm.search_per_run, one call shape, failures are empty
HITS = {"results": [{"title": "Big news", "url": "https://www.bbc.co.uk/news/a", "content": "c", "score": 0.9},
                    {"title": "Blog", "url": "https://someblog.example/x", "content": "c"},
                    {"title": "Again", "url": "https://www.bbc.co.uk/news/b", "content": "c"},
                    {"title": "Guardian", "url": "https://www.theguardian.com/x", "content": "c"},
                    {"title": "Police shooting at the match", "url": "https://www.reuters.com/y", "content": "c"},
                    {"title": "Known", "url": "https://apnews.com/seen", "content": "c"}, {"title": "no url"}]}
reset(); REPLY["search"] = R(200, HITS)
os.environ.pop("FREELLM_KEY")
assert F.search("topic") == [] and POSTS == [], "no key, no search"
os.environ["FREELLM_KEY"] = "freellmapi-abc"
F.CFG["freellm"]["search_per_run"] = 2
r1 = F.search("topic one")
assert POSTS[-1][0] == BASE + "/search" and POSTS[-1][1] == {"query": "topic one", "max_results": 5, "topic": "news"}, POSTS[-1]
assert len(r1) == 5 and r1[0]["url"] == "https://www.bbc.co.uk/news/a", "at most max_results hits, those with a link"
F.search("topic two")
assert F.search("topic three") == [] and len(POSTS) == 2, "capped at search_per_run"
reset(); F.CFG["freellm"]["search_per_run"] = 20; REPLY["search"] = R(502, {})
assert F.search("x") == [] and F.STATE["searches"] == 1, "a failed search is empty and still counts"
reset(); REPLY["search"] = R(200, HITS)
src = F.search_sources("Topic", {"https://apnews.com/seen", "AP"})
assert [(s["outlet"], s["url"]) for s in src] == [("BBC", "https://www.bbc.co.uk/news/a"), ("Guardian", "https://www.theguardian.com/x")], src
assert all(s["kind"] == "article" and s["published"] == "" for s in src), "reputable outlets only, one an outlet, the finder's headline filter"
print("8 search ok")

# 9. build(): a thin topic (under 3 pages) gets the search results' pages as extra sources, a full one does not; facts still go through facts_from
F.ROOT = SCRATCH; F.OUT = SCRATCH / "facts.json"
(SCRATCH / "trends").mkdir(); F.OUT = SCRATCH / "trends" / "facts.json"
topics = [{"topic": "Zzyzx Quokka Festival opens", "signal": "test", "wikipedia": "", "articles": [
              {"outlet": "BBC", "title": "t", "url": "https://www.bbc.co.uk/news/one", "published": "2026-10-27"}]},
          {"topic": "Wibble Glorp Cup final", "signal": "test", "wikipedia": "https://en.wikipedia.org/wiki/W", "articles": [
              {"outlet": "BBC", "title": "t", "url": "https://www.bbc.co.uk/news/w1", "published": ""},
              {"outlet": "Sky News", "title": "t", "url": "https://news.sky.com/w2", "published": ""}]}]
(SCRATCH / "trends" / "research.json").write_text(json.dumps({"topics": topics}))
os.environ["BREAKING"] = ""
FETCHED, SEARCHED = [], []
def fake_page(url, wiki=False):
    FETCHED.append(url); return "Some words about the story. " * 40, ""
F.page_text = fake_page
F.triage = lambda ts, limit: [(1, "Music"), (2, "Sport")]
F.search = lambda q, n=5: (SEARCHED.append(q), [{"title": "More on it", "url": "https://www.theguardian.com/more", "content": "c"},
                                                {"title": "Other", "url": "https://www.reuters.com/other", "content": "c"}])[1]
PAGES = []
def fake_facts(prompt, texts, kinds, want=4):
    PAGES.append(sorted(kinds.values()))
    return {"what_is_new": "x", "hooks": []}, [], [], "stub"
F.facts_from = fake_facts
F.CFG["factpack_topics"] = 5
reset(); F.STATE["models"] = list(GEM)
F.build()
d = json.loads(F.OUT.read_text())
by = {p["topic"]: p for p in d["topics"]}
thin, full = by["Zzyzx Quokka Festival opens"], by["Wibble Glorp Cup final"]
assert SEARCHED == ["Zzyzx Quokka Festival opens"], ("only the thin topic searches", SEARCHED)
assert len(thin["sources"]) == 3 and thin["sources"][1][1] == "https://www.theguardian.com/more" and thin["sources"][2][2] == "Reuters", thin["sources"]
assert len(full["sources"]) == 3 and PAGES[0] == ["article"] * 3 and PAGES[1] == ["article", "article", "wikipedia"], PAGES
assert F.STATE["search_sources"] == 2
print("9 build ok")

# 10. the hub rows (keys.py): the router itself and one optional row per key; a missing optional key never opens an issue
import datetime as dt
T = dt.datetime(2026, 10, 27, 12, 0, tzinfo=dt.timezone.utc)
rows = K.router_key_rows({"TAVILY_API_KEY": "t"}, {"ok": True, "chat_platforms": ["kilo"], "search_engines": ["tavily", "parallel"]}, T)
byid = {r["id"]: r for r in rows}
assert set(byid) == set(FL.KEYS) and byid["TAVILY_API_KEY"]["status"] == "ok" and byid["EXA_API_KEY"]["status"] == "missing"
for secret, r in byid.items():
    assert r["group"] == "AI models" and r["for"] == "freellm" and not K.problem(r), "optional rows open no issue"
    if r["status"] == "missing":
        assert r["needed"] is False and any(secret in s and K.SECRETS + "/new" in s for s in r["fix"]), r["fix"]
        assert FL.KEYS[secret][2] in r["fix"][0], "the free sign-up link comes first"
assert "https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new" in byid["EXA_API_KEY"]["fix"][1]
lost = K.router_key_rows({"LLM7_API_KEY": "x"}, {"ok": True, "chat_platforms": ["kilo"], "search_engines": []}, T)[-1]
assert lost["status"] == "failing" and not K.problem(lost), "a key the router did not list is shown, never an issue"
assert K.router_row({}, T)["status"] == "missing" and not K.problem(K.router_row({}, T))
good = K.router_row({"ok": True, "started": "2026-10-27T11:00:00+00:00", "job": "write", "models": 31, "chat_platforms": ["kilo", "ovh"],
                     "search_engines": ["parallel"], "calls": {"kilo": 4, "ovh": 1}}, T)
assert good["status"] == "ok" and "31 chat models on kilo, ovh" in good["detail"] and "served 5 calls" in good["detail"], good["detail"]
down = lambda n: {"ok": False, "started": "2026-10-27T11:00:00+00:00", "reason": "docker pull failed", "history": [{"ok": True}] + [{"ok": False}] * n}
r1, r2, r3 = K.router_row(down(1), T), K.router_row(down(2), T), K.router_row(down(3), T)
assert [r["status"] for r in (r1, r2, r3)] == ["failing"] * 3 and [K.problem(r) for r in (r1, r2, r3)] == [False, False, True], "an issue only after 3 failed starts in a row"


class GH:
    def __init__(self): self.open, self.log = {}, []
    def open_issues(self): return dict(self.open)
    def raise_issue(self, title, body, labels=None, howto=None):
        self.log.append(title); self.open.setdefault(title, 200 + len(self.log)); return self.open[title]
    def close_issue(self, number, comment): self.open = {t: n for t, n in self.open.items() if n != number}


A = GH()
allrows = [r3] + K.router_key_rows({}, {}, T)
K.announce(allrows, {}, T, A); K.announce(allrows, {r["id"]: r for r in allrows}, T, A)
assert A.log == ["\U0001f511 Fix needed: " + K.ROUTER_WHAT], ("one issue for a failing router, none for the missing keys", A.log)
print("10 hub rows ok")

# 10b. start(), with Docker and the router stubbed: fails open on a pull failure or a changed digest, and on success hands the key on
import subprocess as sp
FL.cleanup = lambda: None
FL.CONFIG = SCRATCH / "config.json"; FL.CONFIG.write_text(cfg_text)           # a copy: the digest is recorded in it, never in the real one
GH_ENV = SCRATCH / "github_env"
START_ENV = {"GITHUB_WORKFLOW": "write", "RUNNER_TEMP": str(SCRATCH), "GITHUB_ENV": str(GH_ENV), "TAVILY_API_KEY": "tvly-9", "GROQ_API_KEY": "groq-SECRET",
             "CLAUDE_CODE_OAUTH_TOKEN": "claude-SECRET"}
os.environ["GITHUB_ENV"] = str(GH_ENV)
RAN = []


def fake_sh(pull_code=0, digest="sha256:" + "a" * 64):
    def sh(cmd, **kw):
        RAN.append((cmd, kw.get("env")))
        if cmd[:2] == ["docker", "pull"]: return sp.CompletedProcess(cmd, pull_code, "", "boom: toomanyrequests" if pull_code else "")
        if cmd[:3] == ["docker", "image", "inspect"]: return sp.CompletedProcess(cmd, 0, f"ghcr.io/tashfeenahmed/freellmapi@{digest}|sha256:imageid\n", "")
        return sp.CompletedProcess(cmd, 0, "container-id\n", "")
    return sh


FL.save_status({})
st = FL.start(START_ENV, fake_sh(pull_code=1))
assert not st["ok"] and "docker pull failed" in st["reason"] and not GH_ENV.exists(), "a failed pull: no key handed on, the job runs as before"
assert json.loads(FL.STATUS.read_text())["history"][-1]["ok"] is False and not any(c[0][:2] == ["docker", "run"] for c in RAN)
FL.settings = lambda cfg=None: dict(FL.DEFAULTS, digest="sha256:" + "a" * 64)
RAN.clear(); st = FL.start(START_ENV, fake_sh(digest="sha256:" + "b" * 64))
assert not st["ok"] and "digest changed" in st["reason"] and not any(c[0][:2] == ["docker", "run"] for c in RAN), "a changed digest refuses to start"
FL.settings = lambda cfg=None: dict(FL.DEFAULTS)
FL.http = lambda method, path, key=None, body=None, base=None, timeout=15: {
    "/api/ping": (200, {"ok": True}, {}), "/v1/models?available=true": (200, LISTING, {}), "/api/auth/login": (200, {"token": "tok"}, {}),
    "/api/keys": (200, [{"platform": "kilo", "enabled": True, "status": "unknown"}, {"platform": "ovh", "enabled": True, "status": "healthy"},
                        {"platform": "tavily", "enabled": True, "status": "unknown"}, {"platform": "aihorde", "enabled": False, "status": "unknown"}], {}),
    "/v1/search/engines": (200, {"data": [{"provider": "parallel", "available": True}, {"provider": "keenable", "available": False}]}, {})}[path]
FL.read_key = lambda folder, sh=None, login=None: "freellmapi-run-key"
FL.wait_models = lambda key, seconds, **kw: FL.chat_models(LISTING)
RAN.clear(); st = FL.start(START_ENV, fake_sh())
assert st["ok"] and st["digest"] == "sha256:" + "a" * 64 and st["models"] == 10 and st["chat_platforms"] == ["kilo", "ovh"], st
assert st["search_engines"] == ["parallel"] and st["keys_given"] == ["TAVILY_API_KEY"] and "EXA_API_KEY" in st["keys_missing"], st
assert "FREELLM_KEY=freellmapi-run-key" in GH_ENV.read_text() and f"FREELLM_BASE={BASE}" in GH_ENV.read_text()
run = next(c for c in RAN if c[0][:2] == ["docker", "run"])
assert "127.0.0.1:3001:3001" in run[0] and "FREEAPI_CONFIG_JSON" in run[0] and run[0][-1] == "sha256:imageid", run[0]
assert not any("tvly-9" in a or "SECRET" in a for a in run[0]), "no key on the docker command line"
sent = json.loads(run[1]["FREEAPI_CONFIG_JSON"])
assert "SECRET" not in json.dumps(sent) and {k["platform"] for k in sent["keys"]} >= {"kilo", "ovh", "parallel", "keenable", "tavily"}
assert len(run[1]["ENCRYPTION_KEY"]) == 64 and run[1]["ENCRYPTION_KEY"] != "0" * 64
saved_status = FL.STATUS.read_text()
assert "tvly-9" not in saved_status and "freellmapi-run-key" not in saved_status and "SECRET" not in saved_status, "no key in status/freellm.json"
assert json.loads(FL.CONFIG.read_text())["freellm"]["digest"] == "sha256:" + "a" * 64, "the first pull records the digest in config.json"
# stats: the calls the router served, per platform
FL.http = lambda method, path, key=None, body=None, base=None, timeout=15: (200, {"requests": 5, "tokens": 900, "byPlatform": [
    {"platform": "ovh", "requests": 3, "tokens": 700}, {"platform": "parallel", "requests": 2, "tokens": 5}]}, {})
st = FL.stats({"FREELLM_KEY": "freellmapi-run-key", "FREELLM_BASE": BASE})
assert st["calls"] == {"ovh": 3, "parallel": 2} and st["calls_total"] == 5 and st["ok"] and json.loads(FL.STATUS.read_text())["calls"]["ovh"] == 3
print("10b start ok")

# 10c. a failed start says why, without a key: the container's state, whether it answers inside, the end of its log
def sh_report(cmd, **kw):
    if cmd[1] == "inspect" and "Running" in cmd[3]: return sp.CompletedProcess(cmd, 0, "false\n", "")
    if cmd[1] == "inspect": return sp.CompletedProcess(cmd, 0, "state=exited exit=1 oom=false error=\n", "")
    if cmd[1] == "exec": return sp.CompletedProcess(cmd, 0, "", "Error: No such container")
    return sp.CompletedProcess(cmd, 0, "boot ok\nInvalid ENCRYPTION_KEY abc123SECRETVALUE\n", "")
rep = FL.report(sh_report, ["abc123SECRETVALUE"])
assert "state=exited exit=1" in rep and "Invalid ENCRYPTION_KEY ***" in rep and "SECRETVALUE" not in rep and len(rep) <= 1500, rep
assert FL.running(sh_report) is False
assert FL.running(lambda *a, **k: (_ for _ in ()).throw(OSError("no docker"))) is True, "unknown is not 'stopped'"
# probe: one chat and one search, kept in the status file; nothing without the router
FL.save_status({"ok": True})
assert FL.probe({}) is None
def fake_http(method, path, key=None, body=None, base=None, timeout=15):
    if path == "/v1/chat/completions": return 200, {"choices": []}, {"X-Routed-Via": "ovh/gpt-oss-120b"}
    if path == "/v1/search/engines": return 200, {"data": [{"provider": "parallel", "id": "parallel-search", "available": True}, {"provider": "tavily", "id": "tavily-search", "available": False}]}, {}
    if path == "/v1/models": return 200, {"data": [{"id": "a", "available": True}, {"id": "b", "available": False}]}, {}
    return 200, {"provider": "parallel", "engine": "parallel-search", "results": [{"url": "u"}]}, {}
FL.http = fake_http
pr = FL.probe({"FREELLM_KEY": "k", "FREELLM_BASE": BASE})
assert pr["chat"] == "200 via ovh/gpt-oss-120b" and pr["search"] == "200 via parallel/parallel-search, 1 results", pr
assert pr["engines"] == ["parallel/parallel-search", "tavily/tavily-search (no key)"] and pr["models"] == "1 available of 2 listed", pr
assert json.loads(FL.STATUS.read_text())["probe"]["chat"] == pr["chat"]
FL.http = lambda method, path, key=None, body=None, base=None, timeout=15: (404, {"error": {"message": "Model 'auto' is not in the catalog."}}, {}) if path == "/v1/chat/completions" else (503, {"error": {"message": "No search key configured."}}, {})
bad = FL.probe({"FREELLM_KEY": "k", "FREELLM_BASE": BASE})
assert bad["chat"] == "failed (404): Model 'auto' is not in the catalog." and bad["search"] == "failed (503): No search key configured.", bad
print("10c report and probe ok")

# 10d. a release that does not know a platform (v0.16.6 had no Keenable) stops with "unknown provider platform": start again without it
RUNS = []
def sh_old_release(cmd, **kw):
    if cmd[:2] == ["docker", "run"]: RUNS.append(json.loads(kw["env"]["FREEAPI_CONFIG_JSON"])); return sp.CompletedProcess(cmd, 0, "id\n", "")
    if cmd[:2] == ["docker", "pull"]: return sp.CompletedProcess(cmd, 0, "", "")
    if cmd[:3] == ["docker", "image", "inspect"]: return sp.CompletedProcess(cmd, 0, "ghcr.io/x@sha256:" + "a" * 64 + "|sha256:imageid\n", "")
    if cmd[1] == "inspect": return sp.CompletedProcess(cmd, 0, "false\n" if len(RUNS) == 1 else "true\n", "")
    if cmd[1] == "logs": return sp.CompletedProcess(cmd, 0, "[server] Failed to start:\nunknown provider platform: keenable\n", "")
    return sp.CompletedProcess(cmd, 0, "", "")
FL.http = lambda method, path, key=None, body=None, base=None, timeout=15: (0, None, {}) if path == "/api/ping" and len(RUNS) == 1 else {
    "/api/ping": (200, {}, {}), "/v1/models?available=true": (200, LISTING, {}), "/api/auth/login": (200, {"token": "tok"}, {}),
    "/api/keys": (200, [{"platform": "kilo", "enabled": True, "status": "unknown"}], {}), "/v1/search/engines": (200, {"data": []}, {})}[path]
GH_ENV.write_text("")
st = FL.start(START_ENV, sh_old_release)
assert st["ok"] and st["dropped"] == ["keenable"] and len(RUNS) == 2, (st, len(RUNS))
assert "keenable" in {k["platform"] for k in RUNS[0]["keys"]} and "keenable" not in {k["platform"] for k in RUNS[1]["keys"]}, "second start without it"
assert {k["platform"] for k in RUNS[1]["keys"]} >= {"kilo", "ovh", "parallel", "tavily"}
print("10d old release ok")

# 11. the files themselves: no em or en dash, and the workflows pass the optional secrets only
for f in ("pipeline/freellm.py", "pipeline/keys.py", "pipeline/factpack.py", "tests/test_freellm.py", ".github/actions/freellm/action.yml", ".github/workflows/freellm.yml"):
    s = _p.Path(f).read_text()
    assert EM not in s and EN not in s, f + " has an em or en dash"
act = _p.Path(".github/actions/freellm/action.yml").read_text()
act = act[act.index("inputs:"):]            # past the description, which names the keys it never takes
for bad in ("GEMINI", "GROQ", "OPENROUTER", "MISTRAL", "CF_", "SAMBANOVA", "CLAUDE", "ANTHROPIC", "CEREBRAS"):
    assert bad not in act, bad
chk = _p.Path(".github/workflows/freellm.yml").read_text()
assert chk.count("uses: ./.github/actions/freellm") == 3 and "mode: probe" in chk and "mode: stats" in chk and "requests/freellm*" in chk
for wf in ("trends", "write", "evolve"):
    t = _p.Path(f".github/workflows/{wf}.yml").read_text()
    assert t.count("uses: ./.github/actions/freellm") == 2 and "mode: stats" in t, wf
    start = t.index("uses: ./.github/actions/freellm")
    block = t[start:start + 600].split("\n      - ")[0]
    assert "continue-on-error: true" in block and "TAVILY_API_KEY" in block
    assert "GEMINI_API_KEY" not in block and "GROQ" not in block and "CLAUDE" not in block, wf
secrets_ok = set(json.loads(_p.Path("config.json").read_text())["accounts"]["secrets"])
assert set(FL.KEYS) <= secrets_ok, "the identity audit must know the new secrets"
print("11 files ok")
print("freellm ok")
