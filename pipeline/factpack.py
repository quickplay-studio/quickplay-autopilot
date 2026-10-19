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
import datetime as dt, json, os, pathlib, re, sys, time, unicodedata

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
Below are {n} pages, numbered. Using ONLY these pages, list up to 12 facts about the topic that a viewer would find
interesting, newest and most surprising first: what happened, dates, numbers, names, records, release details, results.
For each fact:
- "claim": one plain sentence in UK English. Copy names, numbers and dates exactly as the pages write them. No dashes.
- "evidence": for EVERY page that states the fact, the page number and the exact sentence from that page that states it,
  copied character for character (do not change, shorten or join sentences), at most 40 words.
Leave out opinions, rumours, predictions, and anything about politics, crime, health or money advice.
"what_is_new": one sentence on what changed in the last two days, or "" if nothing did.
"hooks": up to 3 openings of 12 words or fewer, each built only on facts above.

{pages}"""


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
    import requests, trafilatura
    try:
        r = requests.get(url, headers=WIKI_UA if wiki else BROWSER, timeout=20)
        if not r.ok: return ""
        return (trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or "")[:PAGE_CHARS]
    except Exception:
        return ""


def gemini(prompt):
    import requests
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    models = [CFG.get("gemini_model", "gemini-flash-latest"), "gemini-2.5-flash"]
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": SCHEMA}}
    last = ""
    for model in dict.fromkeys(models):
        for attempt in range(4):
            r = requests.post(API.format(model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                              json=body, timeout=180)
            if r.status_code == 404: last = f"{model}: not found"; break
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"{model}: {r.status_code}"; time.sleep(15 * (attempt + 1)); continue
            if not r.ok: raise RuntimeError(f"{model}: {r.status_code} {r.text[:200]}")
            parts = (((r.json().get("candidates") or [{}])[0].get("content")) or {}).get("parts") or []
            return json.loads("".join(p.get("text", "") for p in parts) or "{}"), model
    raise RuntimeError(last or "no Gemini model answered")


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
    limit, start = int(CFG.get("factpack_topics", 20)), time.time()
    packs, model, errors = [], None, []
    for i, t in enumerate(research.get("topics") or []):
        if len(packs) >= limit or time.time() - start > 14 * 60: break
        srcs = [dict(a, kind="article") for a in t.get("articles") or []]
        if t.get("wikipedia"): srcs.append({"outlet": "Wikipedia", "title": t["topic"], "url": t["wikipedia"], "published": "", "kind": "wikipedia"})
        got = []
        for s in srcs:
            txt = page_text(s["url"], wiki=s["kind"] == "wikipedia")
            if len(txt) >= 400: got.append((s, txt))
        if len(got) < 2: continue                     # two pages are the least a fact can be checked against
        pages = "\n\n".join(f"[{k}] {s['outlet']} · {s['title']} · {s.get('published') or 'undated'} · {s['url']}\n{txt}"
                            for k, (s, txt) in enumerate(got, 1))
        try:
            ans, model = gemini(PROMPT.format(topic=t["topic"], today=today, n=len(got), pages=pages))
        except Exception as e:
            errors.append(f"{t['topic']}: {e}"[:200]); continue
        texts = {k: norm(txt) for k, (s, txt) in enumerate(got, 1)}
        kinds = {k: s["kind"] for k, (s, txt) in enumerate(got, 1)}
        verified, single = verify(ans.get("facts"), texts, kinds)
        hooks = [undash(h) for h in ans.get("hooks") or []][:3]
        packs.append({"n": i + 1, "topic": t["topic"], "signal": t.get("signal", ""),
                      "what_is_new": ans.get("what_is_new", ""), "hooks": hooks,
                      "sources": [[s["title"], s["url"], s["outlet"], s.get("published", "")] for s, _ in got],
                      "verified": verified, "one_source": single})
        print(f"{t['topic']}: {len(verified)} verified, {len(single)} one-source, {len(got)} pages")
        time.sleep(float(CFG.get("gemini_gap_seconds", 7)))     # inside the free tier's requests a minute
    if not packs:
        print("no packs built", errors[:3]); return
    OUT.write_text(json.dumps({"date": today, "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
                               "model": model, "errors": errors[:10], "topics": packs}, ensure_ascii=False, indent=1))
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
        if p["one_source"]:
            print("one source only (needs a second before use):")
            for f in p["one_source"]: print(f"  - {f['claim']} {f['sources']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build": build()
    else: show({int(x) for x in sys.argv[2:] if x.isdigit()})
