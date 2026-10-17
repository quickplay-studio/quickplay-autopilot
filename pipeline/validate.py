"""Check boards before they are queued. The morning session runs it before pushing; GitHub runs it again before rendering
and rejects any board with errors (it goes to boards/failed with the reasons).

usage: python pipeline/validate.py boards/queue/QD-101.json [more.json ...]     exit code 1 if any board has errors
Standard library only.
"""
import datetime as dt, json, pathlib, re, sys, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATS = {"Gaming", "Film", "Music", "Sport", "Tech", "Science", "Entertainment"}
VISUALS = {"none", "title", "stat", "cards", "quote", "date", "versus", "timeline", "bars"}
MODES = {"schedule", "private", "none", "dry"}
SRC = re.compile(r"^(commons:File:.+|commons-search:.+|pixabay:(video|image):.+|url:https://.+)$")
DASH = re.compile("[—–]")
# Clear signs of an excluded topic: the board is rejected.
BANNED = re.compile(r"\b(elections?|parliament\w*|politicians?|political|murder\w*|terroris\w*|porn\w*|onlyfans|nsfw|casinos?|"
                    r"gambl\w*|betting|bookmakers?|lottery|crypto\w*|bitcoin|forex|went viral|goes viral|gone viral|viral video|"
                    r"million views|billion views)\b", re.I)
# Words that are often fine but worth a second look: printed as warnings only.
WATCH = re.compile(r"\b(vote|voting|police|shooting|shot dead|killed|arrest\w*|court|cure[sd]?|vaccine\w*|president|minister|"
                   r"stocks?|shares|invest\w*|viral|views)\b", re.I)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
US_DATE = re.compile(rf"\b({MONTHS}) \d{{1,2}}(st|nd|rd|th)?\b")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")

def _formats():
    return {f["id"] for f in json.loads((ROOT / "templates" / "formats.json").read_text())["formats"]}

def _config():
    return json.loads((ROOT / "config.json").read_text())

def _catalog():
    return {c["slug"] for c in json.loads((ROOT / "pipeline" / "music" / "catalog.json").read_text())}

def _ids_elsewhere(path):
    out = {}
    for d in ("queue", "ready", "done", "failed", "hold", "rejected"):
        for p in (ROOT / "boards" / d).glob("*.json"):
            if path and p.resolve() == pathlib.Path(path).resolve(): continue
            try: out[json.loads(p.read_text()).get("id")] = p
            except Exception: pass
    return out

def check(b, path=None):
    """Returns (errors, warnings) for one board dict."""
    e, w = [], []
    sid = b.get("id", "")
    if not re.fullmatch(r"QD-\d{3,}|TEST-[A-Z0-9-]+", sid): e.append("id: QD-### (next free number)")
    elif sid in _ids_elsewhere(path): e.append(f"id: {sid} is already used, take the next free number")
    elif sid.startswith("QD-") and int(sid[3:]) < int(_config().get("first_id", 1)): e.append(f"id: numbers start at QD-{int(_config()['first_id']):03d}")
    if b.get("format") not in _formats(): e.append(f"format: one of {sorted(_formats())}")
    if b.get("category") not in CATS: e.append(f"category: one of {sorted(CATS)}")
    if b.get("mode", "schedule") not in MODES: e.append(f"mode: one of {sorted(MODES)}")
    try: dt.date.fromisoformat(b.get("created", ""))
    except ValueError: e.append("created: today's date as YYYY-MM-DD")
    if b.get("publish_at"):
        try: dt.datetime.strptime(b["publish_at"], "%Y-%m-%d %H:%M")
        except ValueError: e.append("publish_at: YYYY-MM-DD HH:MM (UK time)")
    mu = b.get("music") or {}
    moods = set(_config().get("music_moods", {}))
    if mu.get("slug") and mu["slug"] not in _catalog(): e.append("music.slug: not in pipeline/music/catalog.json")
    if mu.get("mood") and mu["mood"] not in moods: e.append(f"music.mood: one of {sorted(moods)}")
    if not mu.get("slug") and not mu.get("mood"): w.append("music: no mood given, a track will be picked by category")

    beats = b.get("beats") or []
    if not 3 <= len(beats) <= 14: e.append("beats: 3 to 14")
    total = 0
    for i, bt in enumerate(beats):
        say = (bt.get("say") or "").strip()
        n = len(say.split()); total += n
        if not say: e.append(f"beat {i}: say is empty")
        if "cap" in bt and len(str(bt["cap"]).split()) != n: e.append(f"beat {i}: cap needs the same number of words as say")
        v = bt.get("visual") or {"type": "none"}
        if v.get("type") not in VISUALS: e.append(f"beat {i}: visual type must be one of {sorted(VISUALS)}")
        shots = bt.get("shots") or []
        if len(shots) > 4: e.append(f"beat {i}: at most 4 shots")
        if not shots and v.get("type") == "none": e.append(f"beat {i}: needs at least one shot or a graphic")
        for s in shots:
            src = s.get("src", "")
            if not SRC.match(src): e.append(f"beat {i}: src {src!r} is not a supported form")
            if src.startswith("url:") and not (s.get("credit") and s.get("source")): e.append(f"beat {i}: url shots need credit and source")
    if not 50 <= total <= 135: e.append(f"narration: {total} words, needs 55 to 125 (20 to 45 seconds)")
    elif not 55 <= total <= 125: w.append(f"narration: {total} words, best between 55 and 125")

    m = b.get("meta") or {}
    title = m.get("title") or ""
    if not 1 <= len(title) <= 70: e.append("meta.title: 1 to 70 characters")
    if not EMOJI.search(title[-2:]): e.append("meta.title: end with one emoji")
    if not (m.get("summary") or "").strip(): e.append("meta.summary: 1 to 2 sentences")
    tags = [t for t in (m.get("hashtags") or []) if str(t).lower() != "#shorts"]
    bad_tags = [t for t in tags if not re.fullmatch(r"#\w{2,40}", str(t))]
    if bad_tags: e.append(f"meta.hashtags: letters, numbers and _ only, after one #: {bad_tags[:3]}")
    if len({str(t).lower() for t in tags}) != len(tags): e.append("meta.hashtags: duplicates")
    if not 8 <= len(tags) <= 15: e.append(f"meta.hashtags: {len(tags)} given, needs 8 to 15 (most relevant first; #Shorts is added for YouTube)")
    kw = m.get("tags") or []
    if not isinstance(kw, list) or any(not isinstance(t, str) or not t.strip() for t in kw):
        e.append("meta.tags: a list of search phrases")
    elif len(kw) < 5: w.append("meta.tags: add 5 to 15 search phrases (YouTube's tags field)")
    if b.get("flag") is not None and not str(b.get("flag")).strip(): e.append("flag: one line saying why, or leave it out")
    if "tiktok" in b and not isinstance(b["tiktok"], bool): e.append("tiktok: true (one of the day's 5 TikTok picks) or false")
    if "look" in b:            # normally left out: GitHub picks the look (templates/looks.json)
        try:
            cat = json.loads((ROOT / "templates" / "looks.json").read_text())["dimensions"]
            lk = b["look"]
            if not isinstance(lk, dict): e.append("look: an object such as {\"captions\": \"pop\"}, or leave it out")
            else:
                for d, v in lk.items():
                    if d not in cat: e.append(f"look.{d}: one of {sorted(cat)}")
                    elif v not in cat[d]["options"] or cat[d]["options"][v].get("retired"):
                        e.append(f"look.{d}: one of {sorted(k for k, o in cat[d]['options'].items() if not o.get('retired'))}")
        except (OSError, ValueError, KeyError): pass
    if m.get("comment") and (len(str(m["comment"])) > 100 or "http" in str(m["comment"])): e.append("meta.comment: under 100 characters, no links")
    alt = str(m.get("alt_title") or "")
    if alt and (len(alt) > 70 or not EMOJI.search(alt[-2:])): e.append("meta.alt_title: under 70 characters, one emoji at the end")
    if not m.get("comment") or not alt: w.append("meta.comment and meta.alt_title: add both (comment question, backup title)")
    srcs = m.get("sources") or []
    bad = [s for s in srcs if not (isinstance(s, list) and len(s) == 2 and str(s[1]).startswith("https://"))]
    if bad: e.append("meta.sources: each one [title, https url]")
    sites = {urllib.parse.urlparse(s[1]).netloc.lower().removeprefix("www.") for s in srcs if s not in bad}
    if len(srcs) < 2 or len(sites) < 2: e.append("meta.sources: at least 2 sources from 2 different sites")
    facts = m.get("facts") or []
    if not facts: e.append("meta.facts: list every factual claim as [claim, [source numbers]]")
    for f in facts:
        if not (isinstance(f, list) and len(f) == 2 and isinstance(f[1], list)):
            e.append("meta.facts: each one [claim, [source numbers]]"); continue
        nums = set(f[1])
        if any(not isinstance(k, int) or not 1 <= k <= len(srcs) for k in nums):
            e.append(f"meta.facts: source numbers run from 1 to {len(srcs)} ({str(f[0])[:40]})")
        elif len(nums) < 2:
            e.append(f"meta.facts: needs 2 sources: {str(f[0])[:60]}")

    blob = json.dumps(b, ensure_ascii=False)
    if DASH.search(blob): e.append("no em dashes or en dashes anywhere")
    text = " ".join([bt.get("say", "") for bt in beats] + [title, m.get("summary", "")])
    us = sorted({m.group(0) for m in US_DATE.finditer(text)})
    if us: e.append(f"UK date style: write '20 October', not {us}")
    hits = sorted({h.lower() for h in BANNED.findall(text)})
    if hits: e.append(f"excluded topic or virality words: {hits}")
    watch = sorted({h.lower() for h in WATCH.findall(text)})
    if watch: w.append(f"check these words are fine in context: {watch}")
    return e, w

def main(paths):
    bad = 0
    for p in paths:
        try: b = json.loads(pathlib.Path(p).read_text())
        except Exception as ex:
            print(f"{p}: not valid JSON ({ex})"); bad += 1; continue
        errs, warns = check(b, p)
        print(f"{p}: {'OK' if not errs else 'ERRORS'}")
        for x in errs: print("  error:", x)
        for x in warns: print("  warning:", x)
        bad += bool(errs)
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
