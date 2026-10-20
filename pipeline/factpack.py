"""Fact packs for the writer runs: checked facts per trending topic, so a Claude run reads them instead of opening every
page itself (the biggest part of each run's work).

usage:
  python pipeline/factpack.py build          GitHub, after trends.py: trends/research.json -> trends/facts.json
  python pipeline/factpack.py show           one line per topic: number, topic, verified and one-source facts
  python pipeline/factpack.py show 3 7 12    those topics' packs: sources, verified facts (with the evidence), one-source
                                             facts, what is new, hook ideas

How a pack is built: for each topic in trends/research.json (Charlie's requests first, then the top trends, at most
`factpack_topics` in config.json), GitHub downloads the listed articles and the Wikipedia page and keeps their text.
Google's Gemini (GEMINI_API_KEY) lists the facts those pages state, each with the exact sentence from every page that
says it. A fact counts as verified only when those sentences are found word for word in two different pages (one
Wikipedia page at most) and every number in the fact appears in them; a fact found in one page only is listed apart.
Evidence is kept to 25 words a page, with the outlet and link.
"""
import datetime as dt, json, os, pathlib, re, sys, time, unicodedata, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
OUT = ROOT / "trends" / "facts.json"
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0 Safari/537.36", "Accept-Language": "en-GB,en;q=0.9"}
WIKI_UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
PAGE_CHARS = 7000           # text sent per page: the top of an article holds the story
SCHEMA = {"type": "OBJECT", "properties": {
    "what_is_new": {"type": "STRING"},
    "hooks": {"type": "ARRAY", "items": {"type": "STRING"}},
    "facts": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "claim": {"type": "STRING"},
        "evidence": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "source": {"type": "INTEGER"}, "quote": {"type": "STRING"}}, "required": ["source", "quote"]}}},
        "required": ["claim", "evidence"]}}},
    "required": ["what_is_new", "facts"]}
PROMPT = """You check facts for a family-friendly news Shorts channel. Topic: "{topic}". Today is {today}.
Below are {n} pages, numbered. Using ONLY these pages, list up to 14 facts about the topic that a viewer would find
interesting, newest and most surprising first: what happened, dates, numbers, names, records, release details, results.
First give the facts that TWO OR MORE pages state (each page in its own words), then at most 4 that only one page states.
For each fact:
- "claim": one plain sentence in UK English. Copy names, numbers and dates exactly as the pages write them. No dashes.
- "evidence": one entry for EVERY page that states the fact (check every page, a Wikipedia page counts too): the page
  number and the exact sentence from that page that states it, copied character for character (do not change, shorten
  or join sentences), at most 40 words.
Leave out opinions, rumours, predictions, and anything about politics, crime, health or money advice.
"what_is_new": one sentence on what changed in the last two days, or "" if nothing did.
"hooks": up to 3 openings of 12 words or fewer, each built only on facts above.

{pages}"""
TRIAGE_PROMPT = """You pick topics for a family-friendly UK Shorts channel about gaming, film and TV, music, sport, celebrities,
streamers and creators, tech launches and space. Never: politics, crime, health, money or investing, adult content,
gambling, deaths, or a website people only want to visit (a news site, an email service, an app store).
Below are today's trending topics with their headlines. Return the numbers of the topics worth a Short, best first
(biggest audience and freshest story first), at most {limit}, each with its category: Gaming, Film, Music, Sport, Tech,
Science or Entertainment. Topics marked REQUEST were asked for by the channel owner: keep them unless they break a rule.

{lines}"""
TRIAGE_SCHEMA = {"type": "OBJECT", "properties": {"picks": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "n": {"type": "INTEGER"}, "category": {"type": "STRING"}}, "required": ["n", "category"]}}}, "required": ["picks"]}
THINKING = [{"thinkingConfig": {"thinkingLevel": "low"}}, {"thinkingConfig": {"thinkingBudget": 512}}, {}]
STATE = {}


def norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = s.translate({0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"', 0x00A0: " "})
    s = re.sub("[‐-―−]", "-", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def undash(s):
    """Our rule is no en or em dashes: a range becomes "to", any other dash a comma."""
    s = re.sub("(\\d)\\s*[\u2013\u2014]\\s*(\\d)", r"\1 to \2", str(s or ""))
    return re.sub("\\s*[\u2013\u2014]\\s*", ", ", s).strip(", ")


def digits(s):
    return re.sub(r"[,.]", "", s)


def page_text(url, wiki=False):
    """The page's readable text, and its share picture (og:image) for the image ideas."""
    import requests, trafilatura
    try:
        r = requests.get(url, headers=WIKI_UA if wiki else BROWSER, timeout=20)
        if not r.ok: return "", ""
        m = re.search(r'<meta[^>]+?property=["\']og:image["\'][^>]+?content=["\']([^"\']+)', r.text, re.I) or \
            re.search(r'<meta[^>]+?content=["\']([^"\']+)["\'][^>]+?property=["\']og:image["\']', r.text, re.I)
        txt = (trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or "")[:PAGE_CHARS]
        return txt, (m.group(1) if m else "")
    except Exception:
        return "", ""


def image_ideas(got):
    """Real pictures of the subject found on the pages: a Wikipedia page's lead photo when it lives on Commons (free
    licence), and an official page's own share picture. News outlets' pictures are licensed, so never offered."""
    import fetch_media
    ideas = []
    import html
    for s, txt, img in got:
        img = html.unescape(img or "").split("?")[0]
        if not img: continue
        host = re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*", r"\1", s["url"].lower()))
        if s["kind"] == "wikipedia":
            m = re.search(r"/wikipedia/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/]+)", img)
            if m: ideas.append(f"commons:File:{urllib.parse.unquote(m.group(1))}")
        elif not any(host == o or host.endswith("." + o) for o in fetch_media.OUTLETS):
            ideas.append(f"page:{s['url']}")
    return list(dict.fromkeys(ideas))


def models(key):
    """Gemini API models this key can use: the configured one first, then Flash models (stable before preview, newest
    first, Lite last), then the biggest Gemma instruction models (open models with their own, much bigger free limits)."""
    import requests
    if "models" not in STATE:
        names, gemma = [], []
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                             headers={"x-goog-api-key": key}, timeout=30)
            for m in r.json().get("models", []):
                n = m.get("name", "").split("/")[-1]
                if "generateContent" not in (m.get("supportedGenerationMethods") or []) or re.search(r"image|tts|live|audio|embed|exp", n):
                    continue
                if "flash" in n: names.append(n)
                elif n.startswith("gemma") and n.endswith("-it"): gemma.append(n)
        except Exception: pass
        want = CFG.get("gemini_model", "gemini-flash-latest")
        ver = lambda n: max([float(v) for v in re.findall(r"\d+(?:\.\d+)?", n)] or [0])
        ordered = sorted(set(names) - {want}, key=lambda n: ("lite" in n, "preview" in n, -ver(n)))   # Lite last: a bigger free quota
        size = lambda n: (-ver(n.split("-")[1]) if "-" in n else 0, -max([float(v) for v in re.findall(r"(\d+)b", n)] or [0]))
        STATE["models"] = [want] + ordered + sorted(set(gemma), key=size)[:3]
        print("Gemini models:", STATE["models"][:5], "+", len(STATE["models"]) - 5 if len(STATE["models"]) > 5 else 0)
    return STATE["models"]


def loads_loose(text):
    """A model's JSON, forgiving the slips models make: a code fence or a thinking block around it, a trailing comma,
    words before or after it."""
    s = re.sub(r"(?s)<think>.*?</think>", "", text or "").strip()
    s = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", s)
    for t in (s, s[s.find("{"):s.rfind("}") + 1] if "{" in s and "}" in s else None):
        if t is None: continue
        try: return json.loads(t or "{}")
        except ValueError:
            try: return json.loads(re.sub(r",\s*([}\]])", r"\1", t))
            except ValueError: pass
    raise ValueError("no readable JSON")


def gemini(prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None):
    """JSON from the first model that answers, and that model's name. Gemini first: a model out of its free daily quota, or
    retired (404), is skipped for the rest of the run, so every other model gets its turn (each has its own quota); a
    per-minute limit waits and tries again, and so does an answer that isn't readable JSON. lite: simple jobs (triage,
    fact extraction, translations, replies) try the Lite models first, which have the biggest free quota, and save the
    others for writing and checking. When every Gemini API model (Flash, then Gemma) is spent or failing, the chain goes
    on (others()): the keyed free providers, the open model on this runner, and Claude last. prefer: a model name (as
    returned) to try first, so the writer can test models against each other."""
    import requests
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    spent = STATE.setdefault("spent_models", set())
    notes = STATE.setdefault("quota_notes", {})         # which limit each spent model hit, for the run's log
    last = "no Gemini model answered"
    slow = STATE.setdefault("slow_models", {})          # timeouts this run: after 2, the model is passed over
    if prefer and ":" in prefer and not prefer.startswith("gemini:"):
        got = others(prompt, timeout, temperature, lite, only=prefer)
        if got: return got
    prefer = (prefer or "").removeprefix("gemini:")
    todo = [m for m in (models(key) if key else []) if m not in spent and slow.get(m, 0) < 2]
    if lite: todo.sort(key=lambda m: "lite" not in m)
    if prefer in todo: todo.remove(prefer); todo.insert(0, prefer)
    for model in todo:
        timed_out = False
        gemma = model.startswith("gemma")              # no JSON mode, no thinking settings: plain text, read loosely
        for think in ([{}] if gemma else [STATE["think"][model]] if model in STATE.get("think", {}) else THINKING):
            gen = {"temperature": temperature} if gemma else {"temperature": temperature, "responseMimeType": "application/json", **think}
            if schema and not gemma: gen["responseSchema"] = schema
            text = prompt + ("\n\nReply with the JSON only, no other text." if gemma else "")
            body = {"contents": [{"role": "user", "parts": [{"text": text}]}], "generationConfig": gen}
            for attempt in range(3):
                try:
                    r = requests.post(API.format(model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                      json=body, timeout=timeout)
                except requests.exceptions.RequestException as e:      # too slow or unreachable: the next model tries
                    slow[model] = slow.get(model, 0) + 1; last = f"{model}: {type(e).__name__}"; timed_out = True; break
                if r.status_code == 429:
                    per_day = "perday" in r.text.lower().replace("_", "")
                    wait = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                    cap = re.search(r'"quotaValue":\s*"(\d+)', r.text)
                    if per_day or attempt == 2:                         # the next model has its own quota
                        spent.add(model); last = f"{model}: free quota used up"
                        notes[model] = ("daily limit" if per_day else "per-minute limit, 3 tries") + (f" {cap.group(1)}" if cap else "")
                        break
                    last = f"{model}: per-minute limit"; time.sleep(min(65, int(wait.group(1)) + 2) if wait else 20 * (attempt + 1)); continue
                if r.status_code in (500, 502, 503, 504):
                    last = f"{model}: {r.status_code}"; time.sleep(12 * (attempt + 1)); continue
                if r.ok:
                    parts = (((r.json().get("candidates") or [{}])[0].get("content")) or {}).get("parts") or []
                    STATE.setdefault("think", {})[model] = think
                    try:
                        ans = loads_loose("".join(p.get("text", "") for p in parts if not p.get("thought")))
                        count(model); return ans, model
                    except ValueError as e: last = f"{model}: unreadable JSON ({str(e)[:60]})"; continue     # ask again
                last = f"{model}: {r.status_code} {r.text[:150]}"
                if r.status_code == 404: spent.add(model)          # retired or not offered to this key: never again this run
                break
            if timed_out or model in spent or not ("think" in last.lower() and " 400 " in f" {last} "): break   # a refused thinking setting tries the next
    got = others(prompt, timeout, temperature, lite)
    if got: return got
    if not todo: last = "no Gemini model is answering (free quota used up or too slow)"
    if STATE.get("last_other"): last += "; " + STATE["last_other"]
    if all(m in spent for m in models(key) if key) and STATE.get("others_spent"): STATE["spent"] = True
    raise RuntimeError(last)


def count(model):
    c = STATE.setdefault("calls", {}); c[model] = c.get(model, 0) + 1


# Other companies' free tiers, all OpenAI-style, used only when Charlie has added the key as a repository secret. The model
# lists are preferences: each provider's own /models list decides what is offered today (config.json "providers" overrides).
PROVIDERS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1",
             ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "moonshotai/kimi-k2-instruct", "qwen/qwen3-32b"]),
    "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
                 ["gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507", "llama-3.3-70b"]),
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1", ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"]),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", []),       # its ":free" models, biggest context first
}
NOT_TEXT = re.compile(r"whisper|tts|guard|embed|playai|distil|vision|ocr|moderation|audio|transcri|image|prompt-guard|compound", re.I)
JSON_ONLY = "Reply with one JSON value only, no other text."
LOCAL_PORT = 8089


def provider_models(name):
    """The models of one keyed provider to try, in order: configured ones, else its preferences it still offers, else
    the first few chat models it lists."""
    cache = STATE.setdefault("provider_models", {})
    if name in cache: return cache[name]
    env, base, pref = PROVIDERS[name]
    key = os.environ.get(env, "").strip()
    got = []
    if key:
        cfg = (CFG.get("providers") or {}).get(name)
        if cfg: got = list(cfg)
        else:
            import requests
            ids, meta = [], {}
            try:
                r = requests.get(base + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
                for m in (r.json().get("data") or []) if r.ok else []:
                    if m.get("id") and not NOT_TEXT.search(m["id"]): ids.append(m["id"]); meta[m["id"]] = m
            except Exception: pass
            if name == "openrouter":
                free = [i for i in ids if i.endswith(":free")]
                got = sorted(free, key=lambda i: -int(meta[i].get("context_length") or 0))[:4]
            elif ids:
                got = [m for m in pref if m in ids] or ids[:3]
            else: got = pref
    cache[name] = [f"{name}:{m}" for m in got]
    return cache[name]


def chain():
    """Every model after the Gemini API ones, in the order they are tried."""
    out = [m for n in PROVIDERS for m in provider_models(n)]
    if os.environ.get("LLAMA_SERVER"): out.append("local:" + local_name())
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip(): out.append("claude:" + CFG.get("claude_model", "sonnet"))
    return out


def local_name():
    return re.sub(r"(?i)\.gguf$", "", (CFG.get("local_model") or LOCAL_MODEL).rsplit("/", 1)[-1]).lower()


LOCAL_MODEL = "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"


def local_start():
    """Starts llama-server with the open model (downloaded once per run) and waits until it answers. False if it can't."""
    if "local_ok" in STATE: return STATE["local_ok"]
    import requests, subprocess
    STATE["local_ok"] = False
    url = CFG.get("local_model") or LOCAL_MODEL
    path = pathlib.Path("/tmp") / url.rsplit("/", 1)[-1]
    try:
        if not path.exists():
            print("local model: downloading", url, flush=True)
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(str(path) + ".part", "wb") as f:
                    for chunk in r.iter_content(1 << 20): f.write(chunk)
            os.replace(str(path) + ".part", path)
        log = open("/tmp/llama-server.log", "ab")
        subprocess.Popen([os.environ["LLAMA_SERVER"], "-m", str(path), "--port", str(LOCAL_PORT), "-c", "16384",
                          "-t", str(os.cpu_count() or 4)], stdout=log, stderr=log)
        for _ in range(120):
            try:
                if requests.get(f"http://127.0.0.1:{LOCAL_PORT}/health", timeout=5).ok: STATE["local_ok"] = True; break
            except Exception: pass
            time.sleep(5)
    except Exception as e:
        print("local model:", str(e)[:200])
    print("local model ready" if STATE["local_ok"] else "local model: not running")
    return STATE["local_ok"]


def openai_chat(label, base, key, model, prompt, timeout, temperature):
    """One OpenAI-style model. Returns (json, None), or (None, why). Marks the model spent on a daily limit, a refused key
    or a retired model; waits on a per-minute limit; asks again when the answer isn't readable JSON."""
    import requests
    spent, notes = STATE.setdefault("spent_models", set()), STATE.setdefault("quota_notes", {})
    slow = STATE.setdefault("slow_models", {})
    nojson = STATE.setdefault("no_json_mode", set())
    why = f"{label}: no answer"
    for attempt in range(3):
        body = {"model": model, "temperature": temperature, "max_tokens": 6000,
                "messages": [{"role": "system", "content": JSON_ONLY}, {"role": "user", "content": prompt}]}
        if label not in nojson: body["response_format"] = {"type": "json_object"}
        try:
            r = requests.post(base + "/chat/completions", json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except requests.exceptions.RequestException as e:
            slow[label] = slow.get(label, 0) + 1; return None, f"{label}: {type(e).__name__}"
        t = r.text.lower()
        if r.status_code == 429:
            ra = r.headers.get("retry-after") or ""
            ra = float(ra) if re.fullmatch(r"\d+(\.\d+)?", ra) else None
            per_day = bool(re.search(r"per day|daily|\brpd\b|\btpd\b|requests_per_day|tokens_per_day|quota|credits", t)) or (ra or 0) > 120
            if per_day or attempt == 2:
                spent.add(label); notes[label] = "daily limit" if per_day else "per-minute limit, 3 tries"
                return None, f"{label}: free quota used up"
            time.sleep(min(65, ra + 2) if ra else 20 * (attempt + 1)); why = f"{label}: per-minute limit"; continue
        if r.status_code in (401, 403):
            spent.add(label); notes[label] = f"key refused ({r.status_code})"; return None, f"{label}: key refused"
        if r.status_code == 404:
            spent.add(label); return None, f"{label}: not offered (404)"
        if r.status_code == 413 or "context" in t and "length" in t or "too large" in t:
            return None, f"{label}: prompt too large"
        if r.status_code == 400 and label not in nojson and ("response_format" in t or "json" in t):
            nojson.add(label); continue
        if r.status_code >= 500:
            why = f"{label}: {r.status_code}"; time.sleep(12 * (attempt + 1)); continue
        if not r.ok: return None, f"{label}: {r.status_code} {r.text[:150]}"
        try:
            msg = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            ans = loads_loose(msg); count(label); return ans, None
        except ValueError as e: why = f"{label}: unreadable JSON ({str(e)[:60]})"
    return None, why


def claude_call(label, prompt, timeout):
    """Claude Code in print mode with Charlie's subscription token (CLAUDE_CODE_OAUTH_TOKEN), no tools, in an empty folder
    so no project files load. At most claude_max_per_run calls a run (config.json), so his Claude allowance lasts."""
    import shutil, subprocess, tempfile
    spent, notes = STATE.setdefault("spent_models", set()), STATE.setdefault("quota_notes", {})
    if STATE.get("claude_calls", 0) >= int(CFG.get("claude_max_per_run", 12)):
        spent.add(label); notes[label] = "run cap"; return None, f"{label}: run cap reached"
    exe = shutil.which("claude")
    if not exe: spent.add(label); return None, f"{label}: CLI not installed"
    STATE["claude_calls"] = STATE.get("claude_calls", 0) + 1
    try:
        r = subprocess.run([exe, "-p", "--output-format", "json", "--model", label.split(":", 1)[1], "--tools", "",
                            "--system-prompt", JSON_ONLY, "--no-session-persistence", "--max-turns", "2"],
                           input=prompt, capture_output=True, text=True, timeout=max(timeout, 300), cwd=tempfile.mkdtemp())
        out = json.loads(r.stdout or "{}")
    except subprocess.TimeoutExpired: return None, f"{label}: timeout"
    except ValueError: return None, f"{label}: {(r.stderr or r.stdout)[:150]}"
    res = str(out.get("result") or "")
    if out.get("is_error") or r.returncode:
        if re.search(r"limit|quota|credit|auth|login|token", res, re.I):
            spent.add(label); notes[label] = res[:80]
        return None, f"{label}: {res[:150]}"
    try:
        ans = loads_loose(res); count(label); return ans, None
    except ValueError as e: return None, f"{label}: unreadable JSON ({str(e)[:60]})"


def others(prompt, timeout=100, temperature=0.1, lite=False, only=None):
    """The rest of the chain after the Gemini API: keyed free providers, the open model on this runner, then Claude (never
    for lite jobs: Charlie's allowance goes on writing and checking Shorts, not fact extraction). Returns (json, model)
    from the first that answers, else None (and marks the chain spent when nothing is left)."""
    spent, slow = STATE.setdefault("spent_models", set()), STATE.setdefault("slow_models", {})
    todo = [m for m in chain() if m not in spent and slow.get(m, 0) < 2 and not (lite and m.startswith("claude:"))]
    if only: todo = [m for m in todo if m == only]
    for label in todo:
        prov, model = label.split(":", 1)
        if prov in PROVIDERS:
            ans, why = openai_chat(label, PROVIDERS[prov][1], os.environ.get(PROVIDERS[prov][0], "").strip(), model, prompt,
                                   timeout, temperature)
        elif prov == "local":
            if not local_start(): spent.add(label); continue
            ans, why = openai_chat(label, f"http://127.0.0.1:{LOCAL_PORT}/v1", "none", local_name(), prompt, max(timeout, 900), temperature)
        elif prov == "claude":
            ans, why = claude_call(label, prompt, timeout)
        else: continue
        if ans is not None: return ans, label
        STATE["last_other"] = why
    if not only and all(m in spent for m in chain()): STATE["others_spent"] = True
    return None


def gemini_state():
    """How the run's model calls went, for the logs: models out of quota (and which limit), timeouts, answers per model,
    the keyed providers in use and how many Claude calls the run made."""
    return {"out of quota": STATE.get("quota_notes") or {}, "retired": sorted(set(STATE.get("spent_models") or []) - set(STATE.get("quota_notes") or {})),
            "timeouts": STATE.get("slow_models") or {}, "answers": STATE.get("calls") or {},
            "providers": [n for n in PROVIDERS if os.environ.get(PROVIDERS[n][0], "").strip()],
            "local": bool(os.environ.get("LLAMA_SERVER")), "claude calls": STATE.get("claude_calls", 0)}


def triage(topics, limit):
    """One short Gemini call picks the topics worth a pack (skips news sites, mail services and banned subjects)."""
    def line(i, t):
        req = "REQUEST " if t.get("signal") == "Charlie's request" else ""
        heads = " | ".join(a["title"] for a in (t.get("articles") or [])[:3])
        return f"{i}. {req}{t['topic']} ({t.get('signal', '')}): {heads}"
    lines = "\n".join(line(i, t) for i, t in enumerate(topics, 1))
    try:
        ans, _ = gemini(TRIAGE_PROMPT.format(limit=limit, lines=lines), TRIAGE_SCHEMA, timeout=90, lite=True)
        picks = [(p["n"], p.get("category", "")) for p in ans.get("picks") or [] if isinstance(p.get("n"), int) and 1 <= p["n"] <= len(topics)]
        if picks: return list(dict.fromkeys(picks))[:limit]
    except Exception as e:
        print("triage failed:", e)
    skip = re.compile(r"\b(bbc|news|live|mail|login|weather|deaths|google play|app store|election|police|court|murder)\b", re.I)
    return [(i, "") for i, t in enumerate(topics, 1) if not skip.search(t["topic"])][:limit]


def verify(facts, texts, kinds):
    """Keep a fact only where its evidence sentences really are in the pages (word for word) and its numbers match."""
    verified, single = [], []
    for f in facts or []:
        claim = undash(re.sub(r"\s+", " ", str(f.get("claim") or "")).strip())
        if not claim: continue
        good = {}
        for e in f.get("evidence") or []:
            n, q = e.get("source"), str(e.get("quote") or "").strip()
            if isinstance(n, int) and n in texts and len(norm(q)) >= 12 and norm(q) in texts[n] and n not in good:
                good[n] = " ".join(q.split()[:25])
        joined = digits(norm(" ".join(good.values())))
        if not all(digits(x) in joined for x in re.findall(r"\d[\d,.]*\d|\d", claim)): continue
        wiki = sum(1 for n in good if kinds[n] == "wikipedia")
        entry = {"claim": claim, "sources": sorted(good), "evidence": {str(n): good[n] for n in sorted(good)}}
        if len(good) - max(0, wiki - 1) >= 2: verified.append(entry)
        elif good: single.append(entry)
    return verified, single


def build():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY not set: no fact packs"); return
    research = json.loads((ROOT / "trends" / "research.json").read_text())
    today = str(dt.date.today())
    limit, start = int(os.environ.get("FACTPACK_TOPICS") or CFG.get("factpack_topics", 20)), time.time()
    packs, model, errors = [], None, []
    topics = research.get("topics") or []
    for i, cat in triage(topics, limit):
        t = topics[i - 1]
        if time.time() - start > 22 * 60 or STATE.get("spent"): break
        srcs = [dict(a, kind="article") for a in t.get("articles") or []]
        if t.get("wikipedia"): srcs.append({"outlet": "Wikipedia", "title": t["topic"], "url": t["wikipedia"], "published": "", "kind": "wikipedia"})
        got = []
        for s in srcs:
            txt, img = page_text(s["url"], wiki=s["kind"] == "wikipedia")
            if len(txt) >= 400: got.append((s, txt, img))
        images = image_ideas(got)
        got = [(s, txt) for s, txt, img in got]
        if not got: continue                          # one page will do: a one-source fact is used with its source named
        pages = "\n\n".join(f"[{k}] {s['outlet']} · {s['title']} · {s.get('published') or 'undated'} · {s['url']}\n{txt}"
                            for k, (s, txt) in enumerate(got, 1))
        try:
            ans, model = gemini(PROMPT.format(topic=t["topic"], today=today, n=len(got), pages=pages), SCHEMA, lite=True)
        except Exception as e:
            errors.append(f"{t['topic']}: {e}"[:200]); continue
        texts = {k: norm(txt) for k, (s, txt) in enumerate(got, 1)}
        kinds = {k: s["kind"] for k, (s, txt) in enumerate(got, 1)}
        verified, single = verify(ans.get("facts"), texts, kinds)
        hooks = [undash(h) for h in ans.get("hooks") or []][:3]
        packs.append({"n": i, "topic": t["topic"], "signal": t.get("signal", ""), "category": cat,
                      "what_is_new": ans.get("what_is_new", ""), "hooks": hooks,
                      "sources": [[s["title"], s["url"], s["outlet"], s.get("published", "")] for s, _ in got],
                      "verified": verified, "one_source": single, "images": images})
        print(f"{t['topic']}: {len(verified)} verified, {len(single)} one-source, {len(got)} pages")
        time.sleep(float(CFG.get("gemini_gap_seconds", 7)))     # inside the free tier's requests a minute
    if not packs:
        print("no packs built", errors[:3]); return
    OUT.write_text(json.dumps({"date": today, "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                               "model": model, "mode": "breaking" if os.environ.get("BREAKING") else "full",
                               "run": os.environ.get("RUN", ""), "errors": errors[:10], "topics": packs}, ensure_ascii=False, indent=1))
    print(f"{len(packs)} packs, {sum(len(p['verified']) for p in packs)} verified facts")
    print("gemini:", json.dumps(gemini_state()))


def show(nums):
    if not OUT.exists(): print("no fact packs yet: open the sources as usual"); return
    d = json.loads(OUT.read_text())
    print(f"fact packs built {d.get('built')} ({d.get('model')}); topic numbers match trends/research.json")
    for p in d["topics"]:
        if not nums:
            print(f"{p['n']}. {p['topic']} ({p['signal']}): {len(p['verified'])} verified, {len(p['one_source'])} one-source, "
                  f"{len(p['sources'])} sources"); continue
        if p["n"] not in nums: continue
        print(f"\n## {p['n']}. {p['topic']} ({p['signal']})")
        if p.get("what_is_new"): print("new:", p["what_is_new"])
        for h in p.get("hooks") or []: print("hook idea:", h)
        print("sources (copy into meta.sources in this order):")
        for k, s in enumerate(p["sources"], 1): print(f"  [{k}] {s[2]} · {s[0]} · {s[3]} · {s[1]}")
        print("verified (two sources, checked word for word):")
        for f in p["verified"]:
            print(f"  - {f['claim']} {f['sources']}")
            for k, q in f["evidence"].items(): print(f"      [{k}] \"{q}\"")
        if p.get("images"):
            print("real pictures to use as shots:", " · ".join(p["images"]))
        if p["one_source"]:
            print("one source only (needs a second before use):")
            for f in p["one_source"]: print(f"  - {f['claim']} {f['sources']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build": build()
    else: show({int(x) for x in sys.argv[2:] if x.isdigit()})
