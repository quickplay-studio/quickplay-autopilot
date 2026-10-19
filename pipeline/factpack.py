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
    """Flash models this key can use: the configured one first, then stable before preview, newest first."""
    import requests
    if "models" not in STATE:
        names = []
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": 200},
                             headers={"x-goog-api-key": key}, timeout=30)
            for m in r.json().get("models", []):
                n = m.get("name", "").split("/")[-1]
                if "generateContent" in (m.get("supportedGenerationMethods") or []) and "flash" in n \
                        and not re.search(r"image|tts|live|audio|embed|exp", n):
                    names.append(n)
        except Exception: pass
        want = CFG.get("gemini_model", "gemini-flash-latest")
        ver = lambda n: max([float(v) for v in re.findall(r"\d+(?:\.\d+)?", n)] or [0])
        ordered = sorted(set(names) - {want}, key=lambda n: ("lite" in n, "preview" in n, -ver(n)))   # Lite last: a bigger free quota
        STATE["models"] = [want] + ordered
        print("Gemini models:", STATE["models"][:5])
    return STATE["models"]


def gemini(prompt, schema=None, timeout=100, temperature=0.1, lite=False):
    """JSON from the first Gemini model that answers. A model out of free quota, or retired (404), is skipped for the rest
    of the run, so every other model gets its turn (each has its own quota). lite: simple jobs (translations, replies) try
    the Lite models first, which have the biggest free quota, and save the others for writing and checking."""
    import requests
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    spent = STATE.setdefault("spent_models", set())
    last = "no Gemini model answered"
    todo = [m for m in models(key) if m not in spent]
    if lite: todo.sort(key=lambda m: "lite" not in m)
    if not todo: STATE["spent"] = True; raise RuntimeError("every Gemini model's free quota is used up for now")
    for model in todo:
        for think in ([STATE["think"][model]] if model in STATE.get("think", {}) else THINKING):
            gen = {"temperature": temperature, "responseMimeType": "application/json", **think}
            if schema: gen["responseSchema"] = schema
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
            for attempt in range(3):
                try:
                    r = requests.post(API.format(model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                      json=body, timeout=timeout)
                except requests.exceptions.RequestException as e:
                    raise RuntimeError(f"{model}: {type(e).__name__}")       # too slow: give up on this topic
                if r.status_code == 429 and ("quota" in r.text.lower() or attempt == 2):
                    spent.add(model); last = f"{model}: free quota used up"; break      # the next model has its own quota
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"{model}: {r.status_code}"; time.sleep(12 * (attempt + 1)); continue
                if r.ok:
                    parts = (((r.json().get("candidates") or [{}])[0].get("content")) or {}).get("parts") or []
                    STATE.setdefault("think", {})[model] = think
                    return json.loads("".join(p.get("text", "") for p in parts if not p.get("thought")) or "{}"), model
                last = f"{model}: {r.status_code} {r.text[:150]}"
                if r.status_code == 404: spent.add(model)          # retired or not offered to this key: never again this run
                break
            if model in spent or not ("think" in last.lower() and " 400 " in f" {last} "): break   # a refused thinking setting tries the next
    raise RuntimeError(last)


def triage(topics, limit):
    """One short Gemini call picks the topics worth a pack (skips news sites, mail services and banned subjects)."""
    def line(i, t):
        req = "REQUEST " if t.get("signal") == "Charlie's request" else ""
        heads = " | ".join(a["title"] for a in (t.get("articles") or [])[:3])
        return f"{i}. {req}{t['topic']} ({t.get('signal', '')}): {heads}"
    lines = "\n".join(line(i, t) for i, t in enumerate(topics, 1))
    try:
        ans, _ = gemini(TRIAGE_PROMPT.format(limit=limit, lines=lines), TRIAGE_SCHEMA, timeout=90)
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
        if time.time() - start > 14 * 60 or STATE.get("spent"): break
        srcs = [dict(a, kind="article") for a in t.get("articles") or []]
        if t.get("wikipedia"): srcs.append({"outlet": "Wikipedia", "title": t["topic"], "url": t["wikipedia"], "published": "", "kind": "wikipedia"})
        got = []
        for s in srcs:
            txt, img = page_text(s["url"], wiki=s["kind"] == "wikipedia")
            if len(txt) >= 400: got.append((s, txt, img))
        images = image_ideas(got)
        got = [(s, txt) for s, txt, img in got]
        if len(got) < 2: continue                     # two pages are the least a fact can be checked against
        pages = "\n\n".join(f"[{k}] {s['outlet']} · {s['title']} · {s.get('published') or 'undated'} · {s['url']}\n{txt}"
                            for k, (s, txt) in enumerate(got, 1))
        try:
            ans, model = gemini(PROMPT.format(topic=t["topic"], today=today, n=len(got), pages=pages), SCHEMA)
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
                               "model": model, "mode": "breaking" if os.environ.get("BREAKING") else "full", "errors": errors[:10], "topics": packs}, ensure_ascii=False, indent=1))
    print(f"{len(packs)} packs, {sum(len(p['verified']) for p in packs)} verified facts")


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
