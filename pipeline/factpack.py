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
Reply as JSON: {{"what_is_new": "...", "hooks": ["..."], "facts": [{{"claim": "...", "evidence": [{{"source": 1, "quote": "..."}}]}}]}}

{pages}"""
TRIAGE_PROMPT = """You pick topics for a family-friendly UK Shorts channel about gaming, film and TV, music, sport, celebrities,
streamers and creators, tech launches, space, animals and nature, food, cars and history. Never: politics, crime, health, money or investing, adult content,
gambling, deaths, or a website people only want to visit (a news site, an email service, an app store), or a practical
search with no story in it (film or cinema times, weather, tickets, opening hours, near me, how to log in).
Below are today's trending topics with their headlines. Return the numbers of the topics worth a Short, best first
(biggest audience and freshest story first), at most {limit}, each with its category: Gaming, Film, Music, Sport, Tech,
Science, Entertainment, Animals, Food, Cars or History. Topics marked REQUEST were asked for by the channel owner or are on its watchlist: keep them
unless they break a rule (a game rated for adults is fine as entertainment news).

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


def wiki_tables(html, tables=2, rows=25):
    """The rows of a Wikipedia page's first data tables ("wikitable"), one line each, cells joined with " | ", reference
    marks dropped: a list article's ranking (best-selling games, highest-grossing films) lives there, not in its prose."""
    from html.parser import HTMLParser
    class P(HTMLParser):
        def __init__(self):
            super().__init__(); self.out, self.table, self.row, self.cell, self.depth, self.skip = [], None, None, None, 0, 0
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "table":
                self.depth += 1
                if self.table is None and self.depth == 1 and "wikitable" in (a.get("class") or ""): self.table = []
            elif self.table is not None and tag == "tr": self.row = []
            elif self.table is not None and tag in ("td", "th") and self.row is not None: self.cell = []
            elif tag in ("sup", "style", "script"): self.skip += 1
        def handle_endtag(self, tag):
            if tag == "table":
                if self.table is not None and self.depth == 1: self.out.append(self.table); self.table = None
                self.depth = max(0, self.depth - 1)
            elif self.table is not None and tag == "tr" and self.row is not None:
                if any(c.strip() for c in self.row): self.table.append(self.row)
                self.row = None
            elif self.table is not None and tag in ("td", "th") and self.cell is not None and self.row is not None:
                self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip()); self.cell = None
            elif tag in ("sup", "style", "script"): self.skip = max(0, self.skip - 1)
        def handle_data(self, data):
            if self.cell is not None and not self.skip: self.cell.append(data)
    try:
        p = P(); p.feed(html); p.close()
    except Exception: return []
    lines = []
    for t in p.out[:tables]:
        lines += [" | ".join(c for c in r if c) for r in t[:rows + 1]]
        lines.append("")
    return lines


def page_text(url, wiki=False):
    """The page's readable text, and its share picture (og:image) for the image ideas. A Wikipedia page adds the rows of
    its first data tables after the prose (wiki_tables), inside the same character budget."""
    import requests, trafilatura
    try:
        r = requests.get(url, headers=WIKI_UA if wiki else BROWSER, timeout=20)
        if not r.ok: return "", ""
        m = re.search(r'<meta[^>]+?property=["\']og:image["\'][^>]+?content=["\']([^"\']+)', r.text, re.I) or \
            re.search(r'<meta[^>]+?content=["\']([^"\']+)["\'][^>]+?property=["\']og:image["\']', r.text, re.I)
        txt = trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or ""
        if wiki:
            rows = "\n".join(wiki_tables(r.text))
            if rows.strip(): txt = txt[:max(2000, PAGE_CHARS - len(rows) - 2)] + "\n\n" + rows
        return txt[:PAGE_CHARS + 4000] if wiki else txt[:PAGE_CHARS], (m.group(1) if m else "")
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
    words before or after it. An empty reply is not an answer (23 October: two free models replied with nothing, read as
    {}, and the clip planner took "no moments" from them three times over, 22 minutes, instead of asking the next model)."""
    s = re.sub(r"(?s)<think>.*?</think>", "", text or "").strip()
    s = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", s)
    if not s: raise ValueError("empty answer")
    for t in (s, s[s.find("{"):s.rfind("}") + 1] if "{" in s and "}" in s else None):
        if not t: continue
        try: return json.loads(t)
        except ValueError:
            try: return json.loads(re.sub(r",\s*([}\]])", r"\1", t))
            except ValueError: pass
    raise ValueError("no readable JSON")


def gemini(prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None, writing=False):
    """JSON from the first model that answers, and that model's name. Gemini first: a model out of its free daily quota, or
    retired (404), is skipped for the rest of the run, so every other model gets its turn (each has its own quota); a
    per-minute limit waits and tries again, and so does an answer that isn't readable JSON. lite: simple jobs (triage,
    fact extraction, translations, replies) try the Lite models first, which have the biggest free quota, and save the
    others for writing and checking. When every Gemini API model (Flash, then Gemma) is spent or failing, the chain goes
    on (others()): the keyed free providers, the open model on this runner, and Claude last. prefer: a model name (as
    returned) to try first, so the writer can test models against each other. writing: a Short's script and its fix rounds
    go by writing quality instead (writing_order: the strongest keyed models, Gemini Flash with 240 seconds, Gemma, then
    Lite, the runner's model and Claude only when everything else failed)."""
    import requests
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    spent = STATE.setdefault("spent_models", set())
    notes = STATE.setdefault("quota_notes", {})         # which limit each spent model hit, for the run's log
    last = "no Gemini model answered"
    slow = STATE.setdefault("slow_models", {})          # timeouts this run: after 2, the model is passed over
    if writing:                                        # writing: by quality, not provider (writing_order)
        # (24 October, audit M7) a script that hasn't come back in writing_timeout_s (180) won't: one timeout passes a model
        # over for the run (writing_timeouts_before_skip), so the next model gets the time
        cap, wait = int(CFG.get("writing_timeouts_before_skip", 1)), int(CFG.get("writing_timeout_s", 180))
        order = writing_order()
        want = prefer if prefer and ":" in prefer else f"gemini:{prefer}" if prefer else ""
        if want in order: order.remove(want); order.insert(0, want)
        for label in order:
            if label.startswith("gemini:"):
                model = label[7:]
                if model in spent or slow.get(model, 0) >= cap: continue
                ans, why = gem_one(model, key, prompt, schema, max(timeout, wait), temperature)
                if ans is not None: return ans, model
                last = why
            elif not (lite and label.startswith("claude:")):          # lite: never Claude
                got = others(prompt, timeout, temperature, only=label, slow_cap=cap)
                if got: return got
                last = STATE.get("last_other") or last
        if all(m in spent for m in models(key) if key) and all(m in spent for m in chain()): STATE["spent"] = True
        raise RuntimeError(last)
    if prefer and ":" in prefer and not prefer.startswith("gemini:"):
        got = others(prompt, timeout, temperature, lite, only=prefer)
        if got: return got
    prefer = (prefer or "").removeprefix("gemini:")
    todo = [m for m in (models(key) if key else []) if m not in spent and slow.get(m, 0) < 2]
    if lite: todo.sort(key=lambda m: "lite" not in m)
    if prefer in todo: todo.remove(prefer); todo.insert(0, prefer)
    for model in todo:
        ans, why = gem_one(model, key, prompt, schema, timeout, temperature)
        if ans is not None: return ans, model
        last = why
    got = others(prompt, timeout, temperature, lite)
    if got: return got
    if not todo: last = "no Gemini model is answering (free quota used up or too slow)"
    if STATE.get("last_other"): last += "; " + STATE["last_other"]
    if all(m in spent for m in models(key) if key) and STATE.get("others_spent"): STATE["spent"] = True
    raise RuntimeError(last)


def gem_one(model, key, prompt, schema, timeout, temperature):
    """One Gemini API model: (json, None), or (None, why). A daily limit or a 404 marks it spent for the run, a timeout
    counts against it, a per-minute limit waits, an unreadable answer asks again."""
    import requests
    spent, notes = STATE.setdefault("spent_models", set()), STATE.setdefault("quota_notes", {})
    slow = STATE.setdefault("slow_models", {})
    last = f"{model}: no answer"
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
                    count(model); return ans, None
                except ValueError as e:
                    if "empty" in str(e):                  # nothing came back (blocked, or its thinking used every token): the next model
                        last = f"{model}: empty answer"; empty_answer(model); break
                    last = f"{model}: unreadable JSON ({str(e)[:60]})"; continue     # ask again
            last = f"{model}: {r.status_code} {r.text[:150]}"
            if r.status_code == 404: spent.add(model)          # retired or not offered to this key: never again this run
            break
        if timed_out or model in spent or not ("think" in last.lower() and " 400 " in f" {last} "): break   # a refused thinking setting tries the next
    return None, last


def count(model):
    c = STATE.setdefault("calls", {}); c[model] = c.get(model, 0) + 1


def empty_answer(model):
    """A model that replied with nothing: counted for the run's log; twice in a run and it is passed over (like a model
    that timed out twice)."""
    e = STATE.setdefault("empty", {}); e[model] = e.get(model, 0) + 1
    if e[model] >= 2: STATE.setdefault("slow_models", {})[model] = 2


# Other companies' free tiers, all OpenAI-style, used only when Charlie has added the key as a repository secret. The model
# lists are preferences: each provider's own /models list decides what is offered today (config.json "providers" overrides).
PROVIDERS = {
    # Groq (24 October: its limits page lists gpt-oss-120b, gpt-oss-20b and qwen3.8-27b, 1,000 requests a day each;
    # Llama 3.3 70B and Kimi K2 are gone, and its /models list decides anyway)
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1",
             ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]),
    "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1",
                 ["gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507", "llama-3.3-70b"]),
    "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1", ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"]),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", []),       # its ":free" models, biggest context first
    # Cloudflare Workers AI (24 October): free 10,000 "neurons" a day on the free plan, no card, commercial use allowed; a
    # Short's board costs about 400 neurons on gpt-oss-120b, so about 25 a day. Dormant until Charlie adds CF_ACCOUNT_ID and
    # CF_API_TOKEN (a token with Workers AI permission) as repository secrets. Big Llama output is costly in neurons, so
    # gpt-oss-120b first, then the cheap Qwen.
    "cloudflare": ("CF_API_TOKEN", "https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1",
                   ["@cf/openai/gpt-oss-120b", "@cf/qwen/qwen3-30b-a3b-fp8", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"]),
    # SambaNova Cloud (24 October): free while no payment method is linked, no card; DeepSeek-V3.1, gpt-oss-120b and
    # Meta-Llama-3.3-70B-Instruct get 20 requests a minute and 20 a day each (docs.sambanova.ai, rate limits). Only those
    # are tried (FREE_ONLY), whatever else its /models lists. Dormant until Charlie adds SAMBANOVA_API_KEY.
    "sambanova": ("SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1", ["DeepSeek-V3.1", "gpt-oss-120b", "Meta-Llama-3.3-70B-Instruct"]),
}
FREE_ONLY = {"sambanova"}      # providers whose free tier covers only the models listed above


def provider_base(name):
    """A provider's API base, with the Cloudflare account id filled in; None when a needed id is missing."""
    base = PROVIDERS[name][1]
    if "{CF_ACCOUNT_ID}" in base:
        acct = os.environ.get("CF_ACCOUNT_ID", "").strip()
        return base.replace("{CF_ACCOUNT_ID}", acct) if acct else None
    return base
NOT_TEXT = re.compile(r"whisper|tts|guard|embed|playai|distil|vision|ocr|moderation|audio|transcri|image|prompt-guard|compound"
                      r"|orpheus|speech|voice", re.I)      # Groq lists its Orpheus voices with the chat models (24 October)
JSON_ONLY = "Reply with one JSON value only, no other text."
FACT_SHAPE = 'Reply as JSON: {"what_is_new": "...", "hooks": ["..."], "facts": [{"claim": "...", "evidence": [{"source": 1, "quote": "..."}]}]}'
LOCAL_PORT = 8089


# How well a model writes, roughly, from its name: big general chat models (5) before mid-size (4), unknown (3), small,
# coder or vision models (1 or 2). Used for the writing order only; the data (analytics/models.json) decides after that.
TOP = re.compile(r"kimi-k2|gpt-oss-120b|deepseek-(?:r1|v3|chat)|qwen-?3-235b|qwen3-max|maverick|mistral-large|405b|glm-4\.[5-9](?!-air)|hermes-?4"
                 r"|gpt-5(?!-mini|-nano)|gpt-4\.1(?!-mini|-nano)|gpt-4o(?!-mini)|grok-[34](?!-mini)", re.I)
MID = re.compile(r"70b|72b|qwen3-next|mistral-medium|gemini-|llama-3\.3|command-a|gpt-5-mini|gpt-4\.1-mini|gpt-4o-mini", re.I)
SMALL = re.compile(r"vision|\bvl\b|-vl|mini|nano|tiny|small|scout|coder|math|\b(?:[0-9]|1[0-9])b\b|-(?:[0-9]|1[0-9])b", re.I)


def quality(label):
    pre, _, rest = label.partition(":")
    name = (rest if pre in PROVIDERS or pre in ("gemini", "local", "claude") else label).lower()
    if re.search(r"vision|\bvl\b|-vl", name): return 1          # picture readers write worse
    if TOP.search(name): return 5
    if MID.search(name): return 4
    size = max([float(v) for v in re.findall(r"(\d+(?:\.\d+)?)b\b", name)] or [0])
    if SMALL.search(name) or 0 < size < 20: return 1
    if size >= 100: return 5
    if size >= 60: return 4
    return 2 if size else 3


def writing_order():
    """The models a Short's script is written by, best writer first: the strongest keyed free models (quality 4 or 5),
    Gemini Flash, Gemma, the weaker keyed models, then only when all else failed Gemini Lite, the runner's model and
    Claude (capped)."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    gem = models(key) if key else []
    keyed = sorted((m for n in PROVIDERS for m in provider_models(n)), key=lambda m: -quality(m))
    flash = [f"gemini:{m}" for m in gem if not m.startswith("gemma") and "lite" not in m]
    gemma = [f"gemini:{m}" for m in gem if m.startswith("gemma")]
    lite = [f"gemini:{m}" for m in gem if "lite" in m and not m.startswith("gemma")]
    rest = [m for m in chain() if m.startswith(("local:", "claude:"))]
    return [m for m in keyed if quality(m) >= 4] + flash + gemma + [m for m in keyed if quality(m) < 4] + lite + rest


# The writer-model test (24 October, data report item 7): groq gpt-oss-120b (2.61x day-adjusted, n 7) against Gemini Flash
# (41% of a day's boards on 2 measured Shorts), randomised by board number for the writing step only, so the comparison
# is fair (each board's arm decided before anything about it is known). config "writer_test": {start, until, share,
# arms}; a board outside the share, or written while either arm has no model left this run, is not in the test.
WRITER_ARMS = {"gpt-oss-120b": lambda l: "gpt-oss-120b" in l.lower(),
               "gemini flash": lambda l: l.startswith("gemini:") and "flash" in l.lower() and "lite" not in l.lower()}


def writer_arm_of(label):
    """The writer-test arm a model label (as factpack.gemini returns it, or writer.writer_name) belongs to, or "other"."""
    lab = str(label or "")
    lab = lab if ":" in lab else f"gemini:{lab}"
    return next((a for a, hit in WRITER_ARMS.items() if hit(lab)), "other")


def writer_test_label(arm, order=None):
    """The model that serves one arm now: the first label of the writing order in that arm, not spent or slowed this run
    (groq's gpt-oss-120b first, the one the data measured), or None."""
    spent, slow = STATE.get("spent_models") or set(), STATE.get("slow_models") or {}
    cap = int(CFG.get("writing_timeouts_before_skip", 1))
    try: order = list(order if order is not None else writing_order())
    except Exception: return None
    ok = [l for l in order if WRITER_ARMS[arm](l) and l not in spent and l.split(":", 1)[-1] not in spent
          and slow.get(l, 0) < cap and slow.get(l.split(":", 1)[-1], 0) < cap]
    ok.sort(key=lambda l: not l.startswith("groq:"))
    return ok[0] if ok else None


def writer_test(k, today=None, order=None):
    """(arm, label) for board number k: arm "" (not in the test) or one of WRITER_ARMS, 50/50 by k with its own seed
    (independent of the factorial round, the replies and the title tests); label the model that serves it now, None when
    the board is outside the test. Only while both arms have a model this run, so neither arm is favoured by availability."""
    t = CFG.get("writer_test") or {}
    arms = [a for a in t.get("arms") or [] if a in WRITER_ARMS]
    if len(arms) != 2: return "", None
    if today is None:
        from zoneinfo import ZoneInfo
        today = dt.datetime.now(ZoneInfo("Europe/London")).date()
    try:
        if today < dt.date.fromisoformat(str(t.get("start"))) or (t.get("until") and today > dt.date.fromisoformat(str(t["until"]))): return "", None
    except ValueError: return "", None
    import random
    rng = random.Random(f"writer-test:{k}")
    if rng.random() >= float(t.get("share", 0.6)): return "", None
    labels = {a: writer_test_label(a, order) for a in arms}
    if not all(labels.values()): return "", None
    arm = arms[0] if rng.random() < 0.5 else arms[1]
    return arm, labels[arm]


def provider_models(name):
    """The models of one keyed provider to try, in order: configured ones, else the best writers it lists today (quality,
    its preferences breaking ties; OpenRouter's ":free" ones only)."""
    cache = STATE.setdefault("provider_models", {})
    if name in cache: return cache[name]
    env, base, pref = PROVIDERS[name]
    key = os.environ.get(env, "").strip()
    base = provider_base(name)
    got = []
    if key and base:
        cfg = (CFG.get("providers") or {}).get(name)
        if cfg: got = list(cfg)
        else:
            import requests
            ids, meta = [], {}
            try:
                r = requests.get(base + "/models", headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=30)
                data = r.json() if r.ok else []
                for m in (data if isinstance(data, list) else data.get("data") or []):
                    if not isinstance(m, dict) or not m.get("id") or NOT_TEXT.search(m["id"]): continue
                    ids.append(m["id"]); meta[m["id"]] = m
            except Exception: pass
            if name == "openrouter":
                free = [i for i in ids if i.endswith(":free")]
                got = sorted(free, key=lambda i: (-quality(i), -int(meta[i].get("context_length") or 0)))[:4]
            else:
                if name in FREE_ONLY: ids = [i for i in ids if i in pref]      # its free tier covers only these: paid ones never tried
                # the best writers it offers today, its preferences breaking ties; its own list unreadable: the preferences
                got = sorted(ids, key=lambda i: (-quality(i), pref.index(i) if i in pref else len(pref)))[:4] if ids else pref
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
    budget, shrunk = max_tokens_for(label), False
    for attempt in range(3):
        body = {"model": model, "temperature": temperature, "max_tokens": budget,
                "messages": [{"role": "system", "content": JSON_ONLY}, {"role": "user", "content": prompt}]}
        if label not in nojson: body["response_format"] = {"type": "json_object"}
        try:
            r = requests.post(base + "/chat/completions", json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except requests.exceptions.RequestException as e:
            slow[label] = slow.get(label, 0) + 1; refused(label); return None, f"{label}: {type(e).__name__}"
        t = r.text.lower() if not r.ok else ""
        if r.status_code == 429:
            ra = r.headers.get("retry-after") or ""
            ra = float(ra) if re.fullmatch(r"\d+(\.\d+)?", ra) else None
            per_day = bool(re.search(r"per[ _-]day|daily|\brpd\b|\btpd\b|quota|credits|86400", t)) or (ra or 0) > 120
            if per_day or attempt == 2:
                spent.add(label); notes[label] = "daily limit" if per_day else "per-minute limit, 3 tries"
                if not per_day: refused(label)                 # a daily limit is this model's alone; a minute limit is the provider's
                return None, f"{label}: free quota used up"
            time.sleep(min(65, ra + 2) if ra else 20 * (attempt + 1)); why = f"{label}: per-minute limit"; continue
        if r.status_code in (401, 403):
            spent.add(label); notes[label] = f"key refused ({r.status_code})"
            r_ = STATE.setdefault("provider_refusals", {}); prov = provider_of(label)
            if prov: r_[prov] = max(r_.get(prov, 0), int(CFG.get("provider_refusals_before_skip", 3)))   # a refused key refuses every model
            return None, f"{label}: key refused"
        if "neurons" in t and re.search(r"used up|exceed|limit|allocation", t):        # Cloudflare's free daily allocation
            spent.add(label); notes[label] = "daily limit (neurons)"; return None, f"{label}: free quota used up"
        if r.status_code == 404:
            spent.add(label); return None, f"{label}: not offered (404)"
        if r.status_code == 413 or ("context" in t and "length" in t) or "too large" in t:
            if not shrunk and budget > 1500:                # once: a smaller answer budget often fits the minute's tokens
                budget, shrunk = max(1500, int(budget * 0.6)), True; continue
            big = STATE.setdefault("too_large", {}); big[label] = big.get(label, 0) + 1     # this prompt is too big, a smaller one may fit
            refused(label)
            if big[label] >= 4: spent.add(label); notes[label] = "prompt too large, 4 times"     # (Groq's free tier caps tokens a minute)
            return None, f"{label}: prompt too large"
        if r.status_code == 400 and label not in nojson and ("response_format" in t or "json" in t):
            nojson.add(label); continue
        if r.status_code >= 500:
            why = f"{label}: {r.status_code}"
            if attempt == 2: refused(label); break
            time.sleep(12 * (attempt + 1)); continue
        if not r.ok: return None, f"{label}: {r.status_code} {r.text[:150]}"
        ch0 = {}
        try:
            ch0 = (r.json().get("choices") or [{}])[0] or {}
            msg = (ch0.get("message") or {}).get("content") or ""
            ans = loads_loose(msg); count(label); return ans, None
        except ValueError as e:
            if "empty" in str(e):                          # nothing came back: the next model, not this one three times
                empty_answer(label)
                return None, f"{label}: empty answer" + (" (cut off at its token limit)" if ch0.get("finish_reason") == "length" else "")
            why = f"{label}: unreadable JSON ({str(e)[:60]})"
    return None, why


USAGE = ROOT / "status" / "claude_usage.json"


def claude_usage():
    """Today's Claude use (UK day) and the last 14 days, from status/claude_usage.json: every call, the editor's edits,
    the boards Claude wrote, and how the last call went. The hub shows it (Charlie, 23 October: his allowance)."""
    import datetime as _dt
    from zoneinfo import ZoneInfo
    day = str(_dt.datetime.now(ZoneInfo("Europe/London")).date())
    try: u = json.loads(USAGE.read_text())
    except Exception: u = {}
    hist = u.get("history") or {}
    if u.get("day") and u.get("day") != day:
        hist[u["day"]] = {k: int(u.get(k) or 0) for k in ("calls", "edits", "writes")}
        u = {"day": day, "calls": 0, "edits": 0, "writes": 0, "last": u.get("last"), "last_at": u.get("last_at")}
    u.setdefault("day", day)
    for k in ("calls", "edits", "writes"): u[k] = int(u.get(k) or 0)
    u["history"] = dict(sorted(hist.items())[-14:])
    u["caps"] = {"edits": int(CFG.get("claude_edits_per_day", 24)), "writes": int(CFG.get("claude_writes_per_day", 8)),
                 "calls per run": int(CFG.get("claude_max_per_run", 12))}
    return u


def claude_note(what=None, last=None):
    """Counts one use (what: calls, edits or writes) and/or records how the last call went."""
    import datetime as _dt
    u = claude_usage()
    if what: u[what] = u.get(what, 0) + 1
    if last is not None: u["last"], u["last_at"] = last, _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes")
    try: USAGE.parent.mkdir(exist_ok=True); USAGE.write_text(json.dumps(u, indent=1))
    except Exception: pass
    return u


def claude_call(label, prompt, timeout):
    """Claude Code in print mode with Charlie's subscription token (CLAUDE_CODE_OAUTH_TOKEN), no tools, in an empty folder
    so no project files load. At most claude_max_per_run calls a run (config.json), so his Claude allowance lasts."""
    import shutil, subprocess, tempfile
    spent, notes = STATE.setdefault("spent_models", set()), STATE.setdefault("quota_notes", {})
    if STATE.get("claude_calls", 0) >= int(CFG.get("claude_max_per_run", 12)):
        spent.add(label); notes[label] = "run cap"; return None, f"{label}: run cap reached"
    exe = shutil.which("claude")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not exe and not api_key: spent.add(label); return None, f"{label}: CLI not installed"
    STATE["claude_calls"] = STATE.get("claude_calls", 0) + 1
    claude_note("calls")
    if api_key:
        # Charlie's monthly API credits (24 October: a Max plan's credits cover the Claude API, not Claude Code, and leave
        # his chat allowance alone), so the pipeline's few calls draw on them first: the Messages API, no CLI
        return claude_api(label, prompt, api_key, timeout)
    try:
        r = subprocess.run([exe, "-p", "--output-format", "json", "--model", label.split(":", 1)[1], "--tools", "",
                            "--system-prompt", JSON_ONLY, "--no-session-persistence", "--max-turns", "2"],
                           input=prompt, capture_output=True, text=True, timeout=max(timeout, 300), cwd=tempfile.mkdtemp())
        out = json.loads(r.stdout or "{}")
    except subprocess.TimeoutExpired: claude_note(last="timeout"); return None, f"{label}: timeout"
    except ValueError: return None, f"{label}: {(r.stderr or r.stdout)[:150]}"
    res = str(out.get("result") or "")
    claude_note(last="ok" if not (out.get("is_error") or r.returncode) else res[:120])
    if out.get("is_error") or r.returncode:
        if re.search(r"limit|quota|credit|auth|login|token", res, re.I):
            spent.add(label); notes[label] = res[:80]
        return None, f"{label}: {res[:150]}"
    try:
        ans = loads_loose(res); count(label); return ans, None
    except ValueError as e: return None, f"{label}: unreadable JSON ({str(e)[:60]})"


API_MODELS = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5", "haiku": "claude-haiku-5-5"}     # the CLI's aliases as API ids (platform.claude.com models overview, 24 October 2026; config claude_api_models overrides)


def claude_api(label, prompt, api_key, timeout):
    """One Messages API call (ANTHROPIC_API_KEY: Charlie's monthly API credits), the same JSON-only contract as the CLI."""
    import requests
    spent, notes = STATE.setdefault("spent_models", set()), STATE.setdefault("quota_notes", {})
    alias = label.split(":", 1)[1]
    model = (CFG.get("claude_api_models") or {}).get(alias) or API_MODELS.get(alias, alias)
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=max(timeout, 120),
                          headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                          json={"model": model, "max_tokens": 4000, "system": JSON_ONLY, "messages": [{"role": "user", "content": prompt}],
                                **({"effort": CFG["claude_api_effort"]} if CFG.get("claude_api_effort") else {})})
    except Exception as e: claude_note(last=type(e).__name__); return None, f"{label}: {type(e).__name__}"
    if r.status_code != 200:
        text = r.text[:160]
        claude_note(last=f"HTTP {r.status_code}")
        if r.status_code in (401, 402, 403, 429) or re.search(r"credit|billing|limit|quota", text, re.I):
            spent.add(label); notes[label] = f"API {r.status_code}"
        return None, f"{label}: API {r.status_code}: {text}"
    try: res = "".join(b.get("text", "") for b in r.json().get("content") or [] if b.get("type") == "text")
    except ValueError: return None, f"{label}: unreadable API answer"
    claude_note(last="ok (API)")
    try:
        ans = loads_loose(res); count(label); return ans, None
    except ValueError as e: return None, f"{label}: unreadable JSON ({str(e)[:60]})"


def provider_of(label):
    prov = str(label).split(":", 1)[0]
    return prov if prov in PROVIDERS else None


def refused(label):
    """A keyed provider refused or failed a call (too large, a limit after its retries, a server error, a refused key, a
    timeout): counted per provider; at provider_refusals_before_skip (3) its other models are passed over for the run, so
    a provider that is down or over its per-minute tokens doesn't cost a wait on every model (24 October, audit M7)."""
    prov = provider_of(label)
    if not prov: return
    r = STATE.setdefault("provider_refusals", {}); r[prov] = r.get(prov, 0) + 1


def provider_skipped(label):
    prov = provider_of(label)
    return bool(prov) and (STATE.get("provider_refusals") or {}).get(prov, 0) >= int(CFG.get("provider_refusals_before_skip", 3))


def max_tokens_for(label):
    """The answer budget for one call: config max_tokens by label or provider (Groq 3500: its free tier counts the prompt
    and max_tokens against the model's tokens a minute, so 6,000 on a 4,500-token prompt was refused as too large)."""
    caps = CFG.get("max_tokens") or {}
    return int(caps.get(label) or caps.get(str(label).split(":", 1)[0]) or 6000)


def others(prompt, timeout=100, temperature=0.1, lite=False, only=None, slow_cap=2):
    """The rest of the chain after the Gemini API: keyed free providers, the open model on this runner, then Claude (never
    for lite jobs: Charlie's allowance goes on writing and checking Shorts, not fact extraction). Returns (json, model)
    from the first that answers, else None (and marks the chain spent when nothing is left)."""
    spent, slow = STATE.setdefault("spent_models", set()), STATE.setdefault("slow_models", {})
    todo = [m for m in chain() if m not in spent and slow.get(m, 0) < slow_cap and not (lite and m.startswith("claude:"))]
    if only: todo = [m for m in todo if m == only]
    for label in todo:
        if provider_skipped(label): continue                 # this provider kept refusing this run
        prov, model = label.split(":", 1)
        if prov in PROVIDERS:
            ans, why = openai_chat(label, provider_base(prov), os.environ.get(PROVIDERS[prov][0], "").strip(), model, prompt,
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
            "timeouts": STATE.get("slow_models") or {}, "answers": STATE.get("calls") or {}, "empty answers": STATE.get("empty") or {},
            "providers": [n for n in PROVIDERS if os.environ.get(PROVIDERS[n][0], "").strip()],
            "local": bool(os.environ.get("LLAMA_SERVER")), "claude calls": STATE.get("claude_calls", 0),
            "second opinions": STATE.get("second_opinions", 0),
            "providers passed over": sorted(k for k, v in (STATE.get("provider_refusals") or {}).items()
                                            if v >= int(CFG.get("provider_refusals_before_skip", 3)))}


def triage(topics, limit):
    """One short Gemini call picks the topics worth a pack (skips news sites, mail services and banned subjects)."""
    def line(i, t):
        req = "REQUEST " if t.get("signal") == "Charlie's request" or str(t.get("signal", "")).startswith("watchlist") else ""
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


def toks(s):
    return re.findall(r"[a-z0-9]+", digits(norm(s)))


def near(q, text, cache):
    """The page's own words for a quote a model copied slightly wrong: the shortest stretch of the page holding at least
    85% of the quote's words (and every number in it), at most twice its length. None when the page doesn't say it."""
    qt = toks(q)
    if len(qt) < 5: return None
    pt = cache.get(id(text)) or cache.setdefault(id(text), toks(text))
    where = {}
    for i, t in enumerate(pt): where.setdefault(t, []).append(i)
    anchors = sorted({t for t in qt if t in where}, key=lambda t: len(where[t]))
    if not anchors: return None
    nums = {t for t in qt if t.isdigit()}
    from collections import Counter
    need, cq = 0.85 * len(qt), Counter(qt)
    for a in anchors[:2]:
        for i in where[a][:40]:
            lo, hi = max(0, i - len(qt)), min(len(pt), i + len(qt) + 1)
            win = pt[lo:hi]
            cw = Counter(win)
            if sum(min(c, cw[t]) for t, c in cq.items()) < need or not nums <= set(win): continue
            hit = [k for k, t in enumerate(win) if t in cq]
            return " ".join(win[hit[0]:hit[-1] + 1][:40])
    return None


def verify(facts, texts, kinds):
    """Keep a fact only where its evidence really is in the pages and its numbers match: the quote word for word, or
    (models misquote) the stretch of the page that holds nearly all its words and every number (near())."""
    verified, single, cache = [], [], {}
    for f in facts or []:
        if not isinstance(f, dict): continue
        claim = undash(re.sub(r"\s+", " ", str(f.get("claim") or "")).strip())
        if not claim: continue
        good = {}
        for e in f.get("evidence") or []:
            if not isinstance(e, dict): continue
            n, q = e.get("source"), str(e.get("quote") or "").strip()
            if isinstance(n, str) and n.isdigit(): n = int(n)
            if not isinstance(n, int) or n not in texts or n in good or len(norm(q)) < 12: continue
            if norm(q) in texts[n]: good[n] = " ".join(q.split()[:25])
            else:
                got = near(q, texts[n], cache)
                if got: good[n] = got
        joined = digits(norm(" ".join(good.values())))
        if not all(digits(x) in joined for x in re.findall(r"\d[\d,.]*\d|\d", claim)): continue
        if any(norm(claim) == norm(x["claim"]) for x in verified + single): continue      # two models, one fact
        wiki = sum(1 for n in good if kinds[n] == "wikipedia")
        entry = {"claim": claim, "sources": sorted(good), "evidence": {str(n): good[n] for n in sorted(good)}}
        if len(good) - max(0, wiki - 1) >= 2: verified.append(entry)
        elif good: single.append(entry)
    return verified, single


def facts_from(prompt, texts, kinds, want=4):
    """Facts for a pack: a Lite model first (the biggest free quota); when fewer than `want` survive the check, the
    strongest free writers (writing_order, never Claude) read the same pages and both answers are checked together.
    Returns (answer, verified, single, model)."""
    ans, model = gemini(prompt, SCHEMA, lite=True)
    ans = ans if isinstance(ans, dict) else {}
    verified, single = verify(ans.get("facts"), texts, kinds)
    if len(verified) + len(single) < want and not STATE.get("spent"):
        try:
            more, m2 = gemini(prompt, SCHEMA, writing=True, lite=True)
            if isinstance(more, dict) and more.get("facts"):
                facts = (ans.get("facts") or []) + (more.get("facts") or [])
                v2, s2 = verify(facts, texts, kinds)
                if len(v2) + len(s2) > len(verified) + len(single):
                    verified, single, model = v2, s2, f"{model} + {m2}"
                    ans = {**more, **{k: v for k, v in ans.items() if v and k != "facts"}}
                    STATE["second_opinions"] = STATE.get("second_opinions", 0) + 1
        except RuntimeError as e:
            print("second opinion:", str(e)[:120])
    return ans, verified, single, model


def build():
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY not set: no fact packs"); return
    research = json.loads((ROOT / "trends" / "research.json").read_text())
    today = str(dt.date.today())
    limit, start = int(os.environ.get("FACTPACK_TOPICS") or CFG.get("factpack_topics", 20)), time.time()
    packs, model, errors = [], None, []
    topics = research.get("topics") or []
    try:                                              # topics a recent Short covered get no pack: the writer would skip them
        import writer as W
        seen, done_before = W.recent(), W.covered
    except Exception as e:
        seen, done_before = [], None; print("recent Shorts not read:", str(e)[:100])
    skipped = []
    for i, cat in triage(topics, limit * 2):          # spares, so covered topics don't leave places empty
        t = topics[i - 1]
        if len(packs) >= limit or time.time() - start > 22 * 60 or STATE.get("spent"): break
        if done_before and t.get("signal") != "Charlie's request" and done_before(
                {"topic": t["topic"], "signal": t.get("signal", ""),
                 "sources": [[a.get("title", ""), a.get("url", "")] for a in t.get("articles") or []]}, seen):
            skipped.append(t["topic"]); continue
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
        texts = {k: norm(txt) for k, (s, txt) in enumerate(got, 1)}
        kinds = {k: s["kind"] for k, (s, txt) in enumerate(got, 1)}
        try:
            ans, verified, single, model = facts_from(PROMPT.format(topic=t["topic"], today=today, n=len(got), pages=pages), texts, kinds)
        except Exception as e:
            errors.append(f"{t['topic']}: {e}"[:200]); continue
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
    if skipped: print("covered recently, no pack:", "; ".join(skipped)[:300])
    print(f"{len(packs)} packs, {sum(len(p['verified']) for p in packs)} verified facts, "
          f"{sum(len(p['one_source']) for p in packs)} one-source")
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
