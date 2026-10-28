"""FreeLLMAPI router (27 October 2026, Charlie: more free model capacity, never stalled when the strong free models run out
in the afternoon; today the Gemini Lite fallback fails about 3 scripts in 8).

FreeLLMAPI (github.com/tashfeenahmed/freellmapi, MIT) is a self-hosted OpenAI-compatible router over many free LLM tiers,
plus a web search endpoint. It runs per job on the GitHub runner, in Docker, bound to 127.0.0.1, and lives only as long as
the job: no state, no server, no cost. factpack.py talks to it as one more keyed provider ("freellm", env FREELLM_KEY and
FREELLM_BASE) and as a source finder (factpack.search).

  python pipeline/freellm.py start    the composite action .github/actions/freellm: pull (pinned), start, wait, export
  python pipeline/freellm.py probe    the freellm.yml check: one chat and one search through the router, written to the status file
  python pipeline/freellm.py stats    at the end of the job: calls served per platform, then stop the container
  python pipeline/freellm.py show     status/freellm.json in one line

Fails open: any problem leaves FREELLM_KEY unset and the pipeline runs exactly as before. Exit status is always 0.

What the router is given (config_json): only keys for platforms Quickplay does not already call directly (KEYS below), plus
the keyless free tiers (Kilo and OVHcloud for chat, Parallel and Keenable for search). Never GEMINI, GROQ, OPENROUTER,
MISTRAL, CF, SAMBANOVA, CEREBRAS, CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY (FORBIDDEN): those stay on the direct path so
nothing already measured changes, and no Claude token ever reaches a third party. AI Horde (volunteer commons), Cohere (terms
forbid it) and NVIDIA (evaluation-only terms) are never switched on; AI Horde, which the router would otherwise treat as
configured, gets a disabled key row. GitHub Models is not offered: the router's own source says GitHub retired it on
30 July 2026 (models.github.ai answers 200 "OK" in plain text).

The image is pinned: config.json "freellm" holds the tag (v0.16.6, the newest release at least 7 days old when this was
written, the supply-chain rule) and its digest. The first pull records the digest when it is empty; a later pull with another
digest refuses to start. Nothing secret is ever written to status/freellm.json: names, platforms, counts and times only.
"""
import datetime as dt, json, os, pathlib, re, secrets, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
STATUS = ROOT / "status" / "freellm.json"
PORT = 3001
NAME = "freellm"
IN_BOX = "/data"                    # the bind-mounted folder inside the container; FREEAPI_DB_PATH lives in it
DB_FILE = "freellmapi.db"
HISTORY = 8                         # start outcomes kept, newest last
DEFAULTS = {"on": True, "image": "ghcr.io/tashfeenahmed/freellmapi", "tag": "v0.16.6", "digest": "", "search_per_run": 20,
            "top_models": 6, "wait_s": 90}
REPO = "quickplay-studio/quickplay-autopilot"
NEW_SECRET = f"https://github.com/{REPO}/settings/secrets/actions/new"

# GitHub secret -> (router platform, what it adds, free sign-up page, what to do there). Only platforms Quickplay does not
# call directly. Names and key formats from the router's shared/types.ts and server/src/providers (a key is any string).
KEYS = {
    "TAVILY_API_KEY": ("tavily", "web search", "https://app.tavily.com/home", "copy the API key from the home page (free plan, 1,000 searches a month, no card)"),
    "EXA_API_KEY": ("exa", "web search", "https://dashboard.exa.ai/api-keys", "create an API key (free monthly search credits, no card)"),
    "FIRECRAWL_API_KEY": ("firecrawl", "web search", "https://www.firecrawl.dev/app/api-keys", "copy the API key (free plan, 1,000 credits a month, no card)"),
    "LINKUP_API_KEY": ("linkup", "web search", "https://app.linkup.so/api-keys", "create an API key (free monthly credits, no card)"),
    "OLLAMA_API_KEY": ("ollama", "chat models", "https://ollama.com/settings/keys", "create an API key (Ollama Cloud, free plan, no card)"),
    "LLM7_API_KEY": ("llm7", "chat models", "https://llm7.io", "get a free token (100 requests an hour, no card)"),
}
KEYLESS_CHAT = ("kilo", "ovh")          # free without a key: Kilo (200 requests an hour per IP), OVHcloud (2 a minute per model)
KEYLESS_SEARCH = ("parallel", "keenable")
NEVER_ON = ("aihorde",)                 # a key row is written disabled so the router cannot treat it as configured
FORBIDDEN = ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "CF_API_TOKEN", "CF_ACCOUNT_ID",
             "SAMBANOVA_API_KEY", "CEREBRAS_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")
SEARCH_PLATFORMS = {"tavily", "exa", "firecrawl", "linkup", "parallel", "keenable"}
LABEL = "quickplay"


def log(*a): print(*a, flush=True)


def now(): return dt.datetime.now(dt.timezone.utc)


def stamp(t=None): return (t or now()).isoformat(timespec="seconds")


def settings(cfg=None):
    """config.json "freellm" over the defaults."""
    if cfg is None:
        try: cfg = json.loads(CONFIG.read_text())
        except Exception: cfg = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg.get("freellm") or {}).items() if k in DEFAULTS})
    return out


# ---------- what the router is given ----------
def given_keys(env):
    """The secrets that are set and map to a router platform: {SECRET: key}. A forbidden name can never be in KEYS."""
    assert not set(KEYS) & set(FORBIDDEN)
    return {s: (env.get(s) or "").strip() for s in KEYS if (env.get(s) or "").strip()}


def config_json(env, email, password, skip=()):
    """The router's FREEAPI_CONFIG_JSON: an admin (random per run, which also closes its first-run sign-up window), the
    keyless free tiers, a disabled row for AI Horde, and a key row for each mapped secret that is set. Nothing else. skip:
    platforms the pinned image does not know (it refuses to start on one): left out."""
    keys = [{"platform": p, "label": LABEL} for p in KEYLESS_CHAT + KEYLESS_SEARCH]
    keys += [{"platform": p, "enabled": False, "label": LABEL} for p in NEVER_ON]
    got = given_keys(env)
    keys += [{"platform": KEYS[s][0], "key": got[s], "label": LABEL} for s in KEYS if s in got]
    return {"admin": {"email": email, "password": password}, "keys": [k for k in keys if k["platform"] not in skip]}


UNKNOWN = re.compile(r"unknown provider platform:\s*([A-Za-z0-9_-]+)")


def unknown_platform(sh=subprocess.run):
    """The platform the router refused to start on ("unknown provider platform: keenable": the pinned release predates it), read
    from the end of its log; None when the log says something else."""
    try:
        r = sh(["docker", "logs", "--tail", "40", NAME], capture_output=True, text=True, timeout=30)
        m = UNKNOWN.search((r.stdout or "") + (r.stderr or ""))
        return m.group(1) if m else None
    except Exception: return None


def missing_keys(env):
    return [s for s in KEYS if s not in given_keys(env)]


# ---------- the image pin ----------
def digest_check(pinned, pulled):
    """(ok, why): a pinned digest must equal the pulled one; nothing pinned yet is fine (the first pull records it)."""
    pinned, pulled = (pinned or "").strip(), (pulled or "").strip()
    if not pulled: return False, "the pulled image has no digest"
    if pinned and pinned != pulled:
        return False, f"image digest changed: pinned {pinned[:19]}, pulled {pulled[:19]}; review the release, then set config.json freellm.digest"
    return True, ""


def pin_text(text, digest):
    """config.json text with freellm.digest set, only while it is empty; None when it is not empty or not found. A text edit
    (not a rewrite), so the hand-made layout of config.json stays."""
    new, n = re.subn(r'("freellm"\s*:\s*\{[^{}]*?"digest"\s*:\s*)""', lambda m: m.group(1) + json.dumps(digest), text, count=1)
    return new if n else None


def pin(digest):
    try:
        text = CONFIG.read_text()
        new = pin_text(text, digest)
        if new: CONFIG.write_text(new); log(f"freellm: recorded the image digest in config.json ({digest[:19]})")
    except Exception as e: log("freellm: digest not recorded:", f"{type(e).__name__}: {e}"[:120])


# ---------- talking to the router ----------
def http(method, path, key=None, body=None, base=None, timeout=15):
    """(status, json or None, headers). Never raises on an HTTP error."""
    url = (base or f"http://127.0.0.1:{PORT}") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None: req.add_header("Content-Type", "application/json")
    if key: req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, code, hdr = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, code, hdr = e.read(), e.code, dict(e.headers)
    except Exception:
        return 0, None, {}
    try: return code, json.loads(raw.decode() or "null"), hdr
    except ValueError: return code, None, hdr


def read_key_db(path):
    """The unified key from the router's SQLite settings table (read only), or None."""
    con = None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        row = con.execute("SELECT value FROM settings WHERE key = 'unified_api_key'").fetchone()
        return row[0] if row and row[0] else None
    except Exception: return None
    finally:
        if con is not None:
            try: con.close()
            except Exception: pass


def read_key(folder, sh=subprocess.run, login=None):
    """The unified key: the bind mount first; else a copy of the folder taken with docker cp (the router's files belong to
    its own user, and a WAL database cannot always be read by another); else the admin session (login = (email, password))."""
    k = read_key_db(pathlib.Path(folder) / DB_FILE)
    if k: return k
    try:
        box = tempfile.mkdtemp(prefix="freellm-copy-")
        sh(["docker", "cp", f"{NAME}:{IN_BOX}/.", box], capture_output=True, timeout=60)
        k = read_key_db(pathlib.Path(box) / DB_FILE)
        shutil.rmtree(box, ignore_errors=True)
        if k: return k
    except Exception: pass
    if login:
        code, j, _ = http("POST", "/api/auth/login", body={"email": login[0], "password": login[1]})
        tok = (j or {}).get("token") if code == 200 else None
        if tok:
            code, j, _ = http("GET", "/api/settings/api-key", key=tok)
            if code == 200 and (j or {}).get("apiKey"): return j["apiKey"]
    return None


def chat_models(listing):
    """Ids of the available chat models in a /v1/models answer: the router's own entries (auto, fusion, auto:<chain>) and
    anything that cannot be called now are left out."""
    out = []
    for m in (listing or {}).get("data") or []:
        if not isinstance(m, dict) or not m.get("id"): continue
        i = str(m["id"])
        if i in ("auto", "fusion") or i.startswith("auto:"): continue
        if m.get("available") is False or m.get("execution_status") in ("needsKey", "exhausted"): continue
        out.append(i)
    return out


def live_chat_platforms(tok):
    """Platforms with an enabled key that is not known to be bad, from the admin API (/api/keys) and their model counts."""
    code, j, _ = http("GET", "/api/keys", key=tok)
    if code != 200 or not isinstance(j, list): return []
    return sorted({k.get("platform") for k in j if isinstance(k, dict) and k.get("enabled") and k.get("status") in ("healthy", "unknown", None)
                   and k.get("platform") not in SEARCH_PLATFORMS and k.get("platform") not in NEVER_ON})


def live_search(key):
    code, j, _ = http("GET", "/v1/search/engines", key=key)
    return sorted({e.get("provider") for e in (j or {}).get("data") or [] if isinstance(e, dict) and e.get("available")}) if code == 200 else []


def wait_models(key, seconds, sleep=time.sleep, clock=time.time, settle=20):
    """Poll /v1/models until it lists chat models and the count has settled, at most `seconds`. The signed catalog loads about
    10 seconds after the router starts and adds the catalog-only rows, so the count is not trusted before `settle` seconds
    have passed. Returns the ids; an empty list when none came."""
    began = clock()
    end, last, same = began + seconds, None, 0
    ids = []
    while True:
        code, j, _ = http("GET", "/v1/models?available=true", key=key)
        ids = chat_models(j) if code == 200 else []
        if ids:
            same = same + 1 if len(ids) == last else 0
            last = len(ids)
            if same >= 2 and clock() - began >= settle: return ids
        if clock() >= end: return ids
        sleep(4)


# ---------- the status file ----------
def load_status():
    try: return json.loads(STATUS.read_text())
    except Exception: return {}


def save_status(st):
    STATUS.parent.mkdir(exist_ok=True)
    STATUS.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n")


def record(st, history):
    """The run's outcome added to the kept history (newest last)."""
    h = [x for x in (history or []) if isinstance(x, dict)]
    h.append({"t": st["started"], "job": st.get("job", ""), "ok": bool(st["ok"]), "reason": st.get("reason", "")[:120]})
    return h[-HISTORY:]


def export_env(key, base):
    """Mask the key in the job log, then hand it to the later steps."""
    print(f"::add-mask::{key}", flush=True)
    path = os.environ.get("GITHUB_ENV")
    if not path: return False
    with open(path, "a") as f: f.write(f"FREELLM_KEY={key}\nFREELLM_BASE={base}\n")
    return True


def cleanup():
    subprocess.run(["docker", "rm", "-f", NAME], capture_output=True)


# ---------- start ----------
def start(env=None, sh=subprocess.run):
    env = os.environ if env is None else env
    c = settings()
    st = {"started": stamp(), "job": env.get("GITHUB_WORKFLOW", ""), "ok": False, "reason": "", "image": f"{c['image']}:{c['tag']}",
          "digest": "", "chat_platforms": [], "search_engines": [], "models": 0,
          "keys_given": sorted(given_keys(env)), "keys_missing": missing_keys(env), "dropped": [], "calls": {}}
    prev = load_status()
    secrets_in_play = []
    try:
        if not c["on"]: raise RuntimeError("switched off in config.json (freellm.on)")
        if not shutil.which("docker"): raise RuntimeError("no Docker on this runner")
        cleanup()
        pull = sh(["docker", "pull", "-q", st["image"]], capture_output=True, text=True, timeout=600)
        if pull.returncode:
            said = (pull.stderr or pull.stdout or "").strip().splitlines()
            raise RuntimeError("docker pull failed" + (": " + said[-1][:100] if said else ""))
        ins = sh(["docker", "image", "inspect", "--format", "{{index .RepoDigests 0}}|{{.Id}}", st["image"]], capture_output=True, text=True, timeout=60)
        repo_digest, _, image_id = (ins.stdout or "").strip().partition("|")
        digest = repo_digest.partition("@")[2]
        st["digest"] = digest
        ok, why = digest_check(c["digest"], digest)
        if not ok: raise RuntimeError(why)
        if not c["digest"]: pin(digest)
        runner_tmp = env.get("RUNNER_TEMP") or tempfile.gettempdir()
        enc, email, pw = secrets.token_hex(32), f"run-{secrets.token_hex(6)}@example.com", secrets.token_urlsafe(24)
        secrets_in_play = [enc, pw]
        for s in secrets_in_play: print(f"::add-mask::{s}", flush=True)
        dropped = []                                # platforms the pinned release does not know yet: left out, and the router started again
        for attempt in range(4):
            folder = tempfile.mkdtemp(prefix="freellm-data-", dir=runner_tmp)
            os.chmod(folder, 0o777)                 # the container's entrypoint hands it to its own user
            cfg_json = json.dumps(config_json(env, email, pw, dropped))
            denv = dict(os.environ, ENCRYPTION_KEY=enc, FREEAPI_CONFIG_JSON=cfg_json)       # values stay off the command line
            run = sh(["docker", "run", "-d", "--name", NAME, "-p", f"127.0.0.1:{PORT}:{PORT}", "-v", f"{folder}:{IN_BOX}",
                      "-e", "NODE_ENV=production", "-e", f"PORT={PORT}", "-e", f"FREEAPI_DB_PATH={IN_BOX}/{DB_FILE}",
                      "-e", "FREELLMAPI_UPDATE_CHECK=off", "-e", "FREEAPI_DB_DIR_HARDENING=0", "-e", "ENCRYPTION_KEY", "-e", "FREEAPI_CONFIG_JSON", image_id or st["image"]],
                     capture_output=True, text=True, env=denv, timeout=120)
            if run.returncode: raise RuntimeError("docker run failed: " + redact((run.stderr or "").strip()[-100:], secrets_in_play))
            up, stopped = False, False
            for n in range(int(c["wait_s"]) // 2):
                code, _, _ = http("GET", "/api/ping")
                if code == 200: up = True; break
                if n % 2 == 1 and not running(sh): stopped = True; break
                time.sleep(2)
            if up: break
            bad = unknown_platform(sh) if stopped else None
            if bad and bad not in dropped and attempt < 3:
                dropped.append(bad); st["dropped"] = list(dropped); log(f"freellm: this release does not know {bad}: starting again without it"); cleanup(); continue
            raise RuntimeError("the router container stopped before it answered" if stopped else f"the router did not answer within {c['wait_s']} seconds")
        st["dropped"] = dropped
        key = read_key(folder, sh, (email, pw))
        if not key: raise RuntimeError("the router's key could not be read")
        secrets_in_play.append(key)
        ids = wait_models(key, int(c["wait_s"]))
        if not ids: raise RuntimeError("the router listed no chat models within " + str(c["wait_s"]) + " seconds")
        code, j, _ = http("POST", "/api/auth/login", body={"email": email, "password": pw})
        st["chat_platforms"] = live_chat_platforms((j or {}).get("token")) if code == 200 else []
        st["search_engines"] = live_search(key)
        st["models"] = len(ids)
        st["ok"] = True
        export_env(key, f"http://127.0.0.1:{PORT}/v1")
        log(f"freellm: router up, {len(ids)} chat models on {', '.join(st['chat_platforms']) or '?'}; search: {', '.join(st['search_engines']) or 'none'}")
    except Exception as e:
        st["reason"] = redact(f"{type(e).__name__}: {e}" if not isinstance(e, RuntimeError) else str(e), secrets_in_play)[:200]
        log("freellm: not started (the pipeline runs as before):", st["reason"])
        st["detail"] = report(sh, secrets_in_play + list(given_keys(env).values()))      # what the container said, for status/freellm.json and the hub
        if st["detail"]: log(st["detail"])
        cleanup()
    st["history"] = record(st, prev.get("history"))
    save_status(st)
    return st


def running(sh=subprocess.run):
    """The container is still running (False when it is gone or has exited)."""
    try:
        r = sh(["docker", "inspect", "--format", "{{.State.Running}}", NAME], capture_output=True, text=True, timeout=30)
        return (r.stdout or "").strip() == "true"
    except Exception: return True


def report(sh=subprocess.run, values=()):
    """Why a start failed, in at most 1,500 characters: the container's state and exit code, whether the server answers from inside
    it, and the end of its log; every key and password this run made, and every key it was given, replaced by ***."""
    if not shutil.which("docker"): return ""
    out = []
    try:
        r = sh(["docker", "inspect", "--format", "state={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} error={{.State.Error}}", NAME],
               capture_output=True, text=True, timeout=30)
        out.append((r.stdout or r.stderr or "").strip())
        r = sh(["docker", "exec", NAME, "node", "-e", "fetch('http://127.0.0.1:' + (process.env.PORT || 3001) + '/api/ping')"
                ".then(r => console.log('inside: ping ' + r.status)).catch(e => console.log('inside: ' + e.message))"],
               capture_output=True, text=True, timeout=30)
        out.append((r.stdout or r.stderr or "").strip()[-200:])
        r = sh(["docker", "logs", "--tail", "30", NAME], capture_output=True, text=True, timeout=30)
        out.append("log: " + " | ".join(x.strip() for x in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-30:])[-1000:])
    except Exception as e: out.append(f"report failed: {type(e).__name__}")
    return redact(" ; ".join(x for x in out if x), list(values))[:1500]


def redact(text, values):
    for v in values:
        if v and len(v) >= 8: text = text.replace(v, "***")
    return text


# ---------- stats ----------
def stats(env=None):
    """End of job: the calls the router served, per platform (its own month-to-date ledger, which is this run's, the database
    being new), written into status/freellm.json; then the container is stopped."""
    env = os.environ if env is None else env
    key, base = (env.get("FREELLM_KEY") or "").strip(), (env.get("FREELLM_BASE") or "").strip()
    st = load_status()
    if key and base:
        code, j, _ = http("GET", "/v1/usage", key=key, base=base.removesuffix("/v1"))
        if code == 200 and isinstance(j, dict):
            st["calls"] = {r["platform"]: int(r.get("requests") or 0) for r in j.get("byPlatform") or [] if isinstance(r, dict) and r.get("platform")}
            st["calls_total"] = int(j.get("requests") or 0)
            st["tokens"] = int(j.get("tokens") or 0)
        st["finished"] = stamp()
        save_status(st)
        log("freellm: calls served", json.dumps(st.get("calls") or {}))
    cleanup()
    return st


def said(j):
    """The router's own error message from an answer body, short."""
    e = (j or {}).get("error") if isinstance(j, dict) else None
    return (str(e.get("message") if isinstance(e, dict) else e or ""))[:150]


def probe(env=None):
    """The check workflow's proof that the router works end to end: one tiny chat (which model answered, from X-Routed-Via) and
    one news search (which engine answered), what the router lists, written to status/freellm.json. A failure keeps the router's
    own message. Nothing is written when the router is not up."""
    env = os.environ if env is None else env
    key, base = (env.get("FREELLM_KEY") or "").strip(), (env.get("FREELLM_BASE") or "").strip()
    if not key or not base: return None
    root = base.removesuffix("/v1")
    out = {}
    code, j, hdr = http("POST", "/v1/chat/completions", key=key, base=root, timeout=120,
                        body={"model": "auto", "max_tokens": 16, "messages": [{"role": "user", "content": "Reply with the word OK."}]})
    via = {k.lower(): v for k, v in (hdr or {}).items()}.get("x-routed-via", "")
    out["chat"] = f"{code} via {urllib.parse.unquote(via)}"[:120] if code == 200 else f"failed ({code}): {said(j)}"
    code, j, _ = http("POST", "/v1/search", key=key, base=root, timeout=60, body={"query": "BBC News today", "max_results": 2, "topic": "news"})
    out["search"] = f"{code} via {(j or {}).get('provider')}/{(j or {}).get('engine')}, {len((j or {}).get('results') or [])} results" if code == 200 else f"failed ({code}): {said(j)}"
    code, j, _ = http("GET", "/v1/search/engines", key=key, base=root)
    out["engines"] = [f"{e.get('provider')}/{e.get('id')}{'' if e.get('available') else ' (no key)'}" for e in (j or {}).get("data") or [] if isinstance(e, dict)][:12] if code == 200 else f"failed ({code})"
    code, j, _ = http("GET", "/v1/models", key=key, base=root)
    rows = [m for m in (j or {}).get("data") or [] if isinstance(m, dict)] if code == 200 else []
    out["models"] = f"{sum(1 for m in rows if m.get('available'))} available of {len(rows)} listed"
    st = load_status()
    st["probe"] = dict(out, at=stamp())
    save_status(st)
    log("freellm: probe", json.dumps(out))
    return out


def show():
    st = load_status()
    if not st: print("no status/freellm.json yet: the first job with the router writes it"); return
    print(f"{'ok' if st.get('ok') else 'not running'} {st.get('started')} ({st.get('job')}): {st.get('models', 0)} models on "
          f"{', '.join(st.get('chat_platforms') or []) or '-'}; search {', '.join(st.get('search_engines') or []) or '-'}; "
          f"calls {st.get('calls') or {}}" + ("" if st.get("ok") else f"; {st.get('reason')}"))


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "show"
    try:
        if a == "start": start()
        elif a == "probe": probe()
        elif a == "stats": stats()
        else: show()
    except Exception as e:
        log("freellm:", f"{type(e).__name__}: {e}"[:200])
    sys.exit(0)
