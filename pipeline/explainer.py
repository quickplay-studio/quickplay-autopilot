"""Wednesday's explainer: one 6 to 10 minute video on the week's three biggest stories (Charlie, 25 October 2026).

The second route to YouTube's Partner Programme: 8,000 watch hours in 12 months from 1 February 2027, which Shorts watch time
does not count towards, and a long video earns many times a Short per view. It also gives the week's Shorts a related long
video: every Short links the latest one in the first lines of its description (link_lines, used by run_board.description)
and in its creator comment (comment_text, engage.py). The YouTube Data API has no "related video" field for a video (checked
25 October: not in the videos resource or its revision history); Studio's own Related video setting stays the Mac's
Monday job (docs/CHROME_OCCASIONAL.md).

Two jobs (weekly.yml): the build job holds the model keys and the big install (torch, Chatterbox) and never the YouTube keys;
the upload job holds the YouTube keys and a tiny install. The steps:
  1. pick_subjects: the three subjects with most views among the Shorts of the last 7 days (analytics/shorts.csv, grouped
     by the board's first named hashtag); build_packs: their checked facts and sources (the boards' meta.facts, meta.sources)
  2. write_script: one script by the free model chain (factpack.gemini, writing order): sections of narration (1,000 to
     1,400 words), 4 to 8 picture searches each, the fact ids every claim comes from; check_script (numbers must be in the
     facts, no dashes, no excluded topics, UK dates and spelling, word counts) and fact_check (a second pass over the
     facts), with up to 2 fix rounds
  3. split_beats, run_tts: the Shorts' voice (tts_cb.py, Chatterbox, house voice F2); unclear beats are read again
  4. fetch_pictures: fetch_media.resolve (Commons first, the relevance ranker), and cards for the facts the script uses
  5. render: 1920x1080 at 25 fps, PIL frames piped to ffmpeg (slow push-ins on landscape crops, a blurred backdrop for
     portraits, weekly.py's chapter cards, small captions) with the narration and a quiet music bed
  6. upload: scheduled for Wednesday 19:00 UK and public then; chapters, links to the Shorts, every source, picture credit

  python pipeline/explainer.py due                  go=yes|no lines for GITHUB_OUTPUT (standard library only)
  python pipeline/explainer.py build --out DIR      DIR/video.mp4 and DIR/explainer.json (--dry: a test, never uploaded)
  python pipeline/explainer.py upload --out DIR     schedules DIR/video.mp4 and writes status/weekly-<Wednesday>.json
  python pipeline/explainer.py script               only the script step, printed (tries the model chain)
Everything above the build functions is standard library only: analytics.py, engage.py and run_board.py import this module.
"""
import argparse, csv, datetime as dt, hashlib, io, json, math, os, pathlib, re, subprocess, sys, tempfile
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
UK = ZoneInfo("Europe/London")
FIRST = dt.date(2026, 10, 28)           # the first Wednesday after a full week of Shorts and the first Sunday video
W, H, FPS = 1920, 1080, 25
INK, ACCENT, WHITE, MUTED = (15, 23, 32), (46, 230, 197), (245, 248, 250), (159, 176, 194)
WORDS_OK = (950, 1500)                  # what check_script accepts for the whole narration; the prompt asks for 1,100 to 1,400
HOLD, HOLD_MIN, HOLD_MAX = 6.5, 4.0, 10.0       # seconds a picture stays on screen
FADE = 0.4                              # crossfade between shots
LEAD, GAP, SEC_PAUSE, NARR_IN, TAIL, END_CARD, CARD = 0.5, 0.32, 0.9, 0.6, 1.2, 6.0, 3.4   # layout, seconds
MAX_PICS = 28                           # unique pictures in one video: their credit lines must fit the description
DESC_LIMIT = 4700                       # YouTube cuts a description at 5,000; Y.upload at 4,900
LONGFORM_FIELDS = ["date", "video", "kind", "title", "views", "watch_minutes", "watch_hours", "avg_view_seconds", "avg_view_pct",
                   "subs_gained"]


def log(*a):
    print(*a, flush=True)


def load_json(p, default=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return default


def cfg():
    """config.json "explainer": optional overrides (enabled, subjects, voice, wps, captions, music)."""
    return (load_json(ROOT / "config.json", {}) or {}).get("explainer") or {}


def key_of(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def undash(s):
    """Our rule is no en or em dashes: a range becomes "to", any other dash a comma (factpack.undash, without its imports)."""
    s = re.sub("(\\d)\\s*[\u2013\u2014]\\s*(\\d)", r"\1 to \2", str(s or ""))
    return re.sub("\\s*[\u2013\u2014]\\s*", ", ", s).strip(", ")


def stamp(s):
    s = int(s); return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


# ---------------- when ----------------
def target_day(today):
    """The Wednesday a build is for: today when it is one, else the next."""
    return today + dt.timedelta(days=(2 - today.weekday()) % 7)


def status_path(day):
    return ROOT / "status" / f"weekly-{day}.json"


def publish_time(day, now=None):
    """Wednesday 19:00 UK in UTC; the next full hour when that is under 45 minutes away (a late retry)."""
    now = now or now_utc()
    pub = dt.datetime.combine(day, dt.time(19, 0), tzinfo=UK).astimezone(dt.timezone.utc)
    if pub < now + dt.timedelta(minutes=45):
        soon = now + dt.timedelta(minutes=45)
        pub = soon.replace(minute=0, second=0, microsecond=0) + (dt.timedelta(hours=1) if soon.minute or soon.second or soon.microsecond else dt.timedelta())
    return pub


def due(now=None, event="", request=""):
    """(go, mode, why): whether a build is wanted now. mode "dry" (a test build, never uploaded) or "live". The cron runs
    on Wednesdays (the first is 28 October); a push of requests/weekly-explainer.txt asks "dry" or "now"."""
    if cfg().get("enabled") is False: return False, "", "switched off (config.json explainer.enabled)"
    now = now or now_utc()
    day = target_day(now.astimezone(UK).date())
    word = (request.split() or [""])[0].lower()
    if event == "push":
        if word == "dry": return True, "dry", f"a test build for {day}, nothing is uploaded"
        if word != "now": return False, "", "requests/weekly-explainer.txt asks for neither dry nor now"
    if day < FIRST: return False, "", f"the first explainer is on {FIRST:%A %d %B %Y}"
    st = load_json(status_path(day), {}) or {}
    if st.get("video"): return False, "", f"Wednesday {day} is already scheduled ({st['video']})"
    return True, "live", f"building for Wednesday {day}"


# ---------------- the week's subjects ----------------
GENERIC = frozenset("""shorts short fyp viral trending trend news music film films movie movies gaming games game sport sports tech
technology science entertainment animals food cars history facts didyouknow musichistory popculture celebrity celebrities breaking
update updates new latest explained uk ukcharts charts football soccer tv television video videos""".split())


def spaced(tag):
    """#TateMcRae -> Tate McRae, #Jailer2 -> Jailer 2 (a Mc or Mac prefix keeps its capital), #BABYMONSTER stays as it is."""
    t = str(tag).lstrip("#")
    return re.sub(r"(?<=[a-z])(?<!Mc)(?<!Mac)(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Z][a-z])", " ", t).strip()


def subject_of(board, title=""):
    """(label, key, keys) for a Short: the name of what it is about. The label is its first hashtag that names something (not a
    category or platform word), spaced at the capitals, or the matching search phrase when the hashtag has no capitals; failing
    that its first search phrase, else the title's opening words. keys: the normalised names of its first five hashtags and its
    first search phrase, which join subjects that are one story (#Queen and #BohemianRhapsody)."""
    m = (board or {}).get("meta") or {}
    tags = [str(t) for t in m.get("hashtags") or [] if len(key_of(t)) >= 3 and key_of(t) not in GENERIC]
    phrases = [str(p).strip() for p in m.get("tags") or [] if str(p).strip()]
    keys = {key_of(t) for t in tags[:5]} | {key_of(p) for p in phrases[:1]}
    keys.discard("")
    if tags:
        label = spaced(tags[0])
        if " " not in label:
            same = next((p for p in phrases if key_of(p) == key_of(tags[0]) and " " in p), "")
            if same: label = same.title() if same.islower() else same
    elif phrases: label = phrases[0].title() if phrases[0].islower() else phrases[0]
    else:
        t = re.sub(r"[^\w\s'’:,.!?&%£$€-]+$", "", str(title or "")).strip()
        label = " ".join(re.split(r"[:,!?]| is | has | just | was ", t, maxsplit=1)[0].split()[:3])
    label = label[:40].strip() or "This week"
    return label, key_of(label), keys


def pick_subjects(rows, board_of, now=None, n=3, days=7):
    """The n subjects with most YouTube views among the Shorts that went public in the last `days` days. rows: analytics/
    shorts.csv as dicts; board_of(id): the Short's board. Shorts are grouped by subject_of's key; two groups that name each
    other (each one's key is among the other's hashtags), or whose keys contain one another, are one story. Returns
    [{"key", "name", "views", "category", "shorts": [{"id", "title", "views", "video"}]}] most viewed first."""
    now = now or now_utc()
    items = []
    for r in rows:
        sid = str(r.get("short") or "")
        if not sid.startswith("QD-"): continue
        try: posted = dt.datetime.fromisoformat(str(r.get("posted")).replace("Z", "+00:00"))
        except ValueError: continue
        if posted.tzinfo is None: posted = posted.replace(tzinfo=dt.timezone.utc)
        if now - posted > dt.timedelta(days=days): continue
        try: views = int(float(r.get("yt_views") or 0))
        except ValueError: views = 0
        b = board_of(sid) or {}
        label, key, keys = subject_of(b, r.get("title"))
        items.append({"id": sid, "title": str(r.get("title") or ""), "views": views, "video": str(r.get("youtube_url") or "").rsplit("/", 1)[-1],
                      "label": label, "key": key, "keys": keys, "category": str(b.get("category") or "")})
    groups = {}
    for it in items: groups.setdefault(it["key"], []).append(it)
    parent = {k: k for k in groups}

    def find(k):
        while parent[k] != k: parent[k] = parent[parent[k]]; k = parent[k]
        return k
    names = {k: set().union(*(i["keys"] for i in g)) for k, g in groups.items()}
    for a in groups:
        for b in groups:
            if a < b and ((b in names[a] and a in names[b]) or (min(len(a), len(b)) >= 5 and (a in b or b in a))):
                parent[find(b)] = find(a)
    merged = {}
    for k, g in groups.items(): merged.setdefault(find(k), []).extend(g)
    out = []
    for g in merged.values():
        g.sort(key=lambda i: -i["views"])
        out.append({"key": g[0]["key"], "name": g[0]["label"], "views": sum(i["views"] for i in g), "category": next((i["category"] for i in g if i["category"]), ""),
                    "keys": sorted(set().union(*(i["keys"] for i in g))),
                    "shorts": [{k: i[k] for k in ("id", "title", "views", "video")} for i in g]})
    out.sort(key=lambda s: (-s["views"], -len(s["shorts"]), s["name"]))
    return out[:n]


# ---------------- the facts ----------------
def clean_line(s):
    return re.sub(r"\s+", " ", undash(s)).strip()


def pick_facts(board_of, sub, topics=(), max_facts=14, max_sources=9):
    """One subject's pack: facts as {"id", "claim", "sources": [pack source numbers]} and sources as {"n", "title", "url"}.
    The boards' meta.facts are [claim, [board source numbers]]: the numbers are remapped onto one source list for the whole
    subject, duplicate claims dropped, and the best supported facts (most sources) come first. Verified claims of today's
    trends/facts.json topics that name the subject are added."""
    sources, facts, seen = [], [], {}

    def add_fact(claim, nums):
        """A claim with at least one source; the same claim from another Short adds its sources to the first."""
        if not (claim and nums): return
        if key_of(claim) in seen: seen[key_of(claim)]["sources"] = sorted(set(seen[key_of(claim)]["sources"]) | set(nums))
        else: seen[key_of(claim)] = {"claim": claim, "sources": list(nums)}; facts.append(seen[key_of(claim)])

    def src_n(title, url):
        for s in sources:
            if s["url"] == url: return s["n"]
        sources.append({"n": len(sources) + 1, "title": clean_line(title), "url": url}); return len(sources)
    summaries, titles = [], []
    for sh in sub["shorts"]:
        b = board_of(sh["id"]) or {}
        m = b.get("meta") or {}
        if m.get("summary"): summaries.append(clean_line(m["summary"]))
        titles.append(sh["title"])
        smap = {}
        for k, s in enumerate(m.get("sources") or [], 1):
            if isinstance(s, (list, tuple)) and len(s) >= 2 and str(s[1]).startswith("https://"): smap[k] = src_n(s[0], s[1])
        for f in m.get("facts") or []:
            if not (isinstance(f, (list, tuple)) and len(f) == 2 and isinstance(f[1], (list, tuple))): continue
            add_fact(clean_line(f[0]), sorted({smap[k] for k in f[1] if k in smap}))
    mine = [k for k in [sub["key"]] + list(sub.get("keys") or []) if len(k) >= 5]
    for t in topics or ():
        if not isinstance(t, dict) or not any(k in key_of(t.get("topic")) for k in mine): continue
        tsrc = {}
        for k, s in enumerate(t.get("sources") or [], 1):
            if isinstance(s, (list, tuple)) and len(s) >= 2 and str(s[1]).startswith("https://"): tsrc[k] = src_n(s[0], s[1])
        for c in t.get("verified") or []:
            if not isinstance(c, dict): continue
            add_fact(clean_line(c.get("claim")), sorted({tsrc[k] for k in c.get("sources") or [] if k in tsrc}))
    facts.sort(key=lambda f: -len(f["sources"]))                 # stable: the boards' order within the same support
    facts = facts[:max_facts]
    used = sorted({n for f in facts for n in f["sources"]})
    keep = used[:max_sources]
    renum = {old: i for i, old in enumerate(keep, 1)}
    by_n = {s["n"]: s for s in sources}
    out_sources = [{"n": renum[o], "title": by_n[o]["title"], "url": by_n[o]["url"]} for o in keep]
    for f in facts: f["sources"] = [renum[n] for n in f["sources"] if n in renum]
    facts = [f for f in facts if f["sources"]]
    return facts, out_sources, summaries, titles


def build_packs(subjects, board_of, topics=()):
    """[{"id": "A", "name", "views", "category", "titles", "summaries", "shorts", "facts": [{"id": "A1", ...}], "sources"}]."""
    packs = []
    for i, sub in enumerate(subjects):
        facts, sources, summaries, titles = pick_facts(board_of, sub, topics)
        letter = "ABCDEFGH"[i]
        for j, f in enumerate(facts, 1): f["id"] = f"{letter}{j}"
        packs.append({"id": letter, "name": sub["name"], "views": sub["views"], "category": sub.get("category", ""), "titles": titles,
                      "summaries": summaries, "shorts": sub["shorts"], "facts": facts, "sources": sources})
    return packs


def pack_text(packs):
    out = []
    for p in packs:
        out.append(f"STORY {p['id']}: {p['name']} ({p['category'] or 'general'}; {p['views']:,} views on our Shorts this week)")
        if p["titles"]: out.append("Our Shorts on it (their titles are context, not facts): " + "; ".join(f'"{t}"' for t in p["titles"][:4]))
        for f in p["facts"]:
            out.append(f"{f['id']} ({len(f['sources'])} source{'s' if len(f['sources']) != 1 else ''}): {f['claim']}")
        out.append("")
    return "\n".join(out).strip()


# ---------------- the script ----------------
SCHEMA = {"type": "OBJECT", "properties": {
    "title": {"type": "STRING"}, "description": {"type": "STRING"}, "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
    "sections": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "chapter": {"type": "STRING"}, "subject": {"type": "STRING"}, "narration": {"type": "STRING"},
        "pictures": {"type": "ARRAY", "items": {"type": "STRING"}}, "uses": {"type": "ARRAY", "items": {"type": "STRING"}}},
        "required": ["chapter", "narration", "pictures"]}}},
    "required": ["title", "sections"]}

PROMPT = """You write the script of ONE long YouTube video for Quickplay Daily, a family-friendly UK channel that explains what people are searching for. The video is 7 to 9 minutes spoken and covers this week's {n} biggest stories on the channel, in this order: {names}.

THE FACTS BELOW ARE THE ONLY THINGS YOU MAY STATE AS FACT. Each has an id (A1, B3 and so on). Never add a fact, number, date, name, quote, ranking or cause that is not in them, even if you know it is true. If the facts do not say it, leave it out. The Short titles are context only.

Write like a well-read friend telling a story to a smart 14 year old: plain words, short sentences (most under 20 words), the concrete detail first, no jargon, no hype words (epic, insane, shocking, you won't believe), no lists, no brackets, no emoji, no web addresses.

Sections, in this order (5 to 8 sections):
1. Intro, 90 to 130 words. Open on the single most surprising fact from the stories (no greeting, no "welcome"). Name all {n} stories. Say what the viewer will understand by the end.
2. One section per story, 260 to 340 words each, in the order above. Tell it as a story: what happened, the details that make it interesting, why people are searching for it now. Use at least five of that story's facts.
3. A section on what links them, 150 to 230 words. This is your own point, one that no source spells out: a link, contrast or pattern across the stories, built only from the facts. Present it as your reading ("that suggests", "one way to read it"). It must not add a new fact.
4. Outro, 60 to 100 words. One line that sums the video up, then say there is a new explainer every Wednesday and a Short every day, so subscribe to Quickplay Daily.
All sections together: 1,100 to 1,400 words.

Rules (a program checks every one of them):
- UK English: colour, favourite, and dates as "20 October" (never "October 20"). No em dashes or en dashes anywhere; use a full stop or a comma.
- Family friendly. Never politics, crime, health claims, money or investing advice, adult content or gambling. Nothing about anyone's private life.
- Anonymous channel: no "I", no presenter's name; "we" at most twice.
- Never say today, tonight, yesterday or tomorrow: the video stays online for years. Name the day or date instead, using only dates the facts give.
- Spell out the numbers one to ten. Any other number must appear in the facts, written the same way.
- Do not cite Wikipedia. Name an outlet only when a claim is worth attributing to it.

For every section give 4 to 8 picture searches for Wikimedia Commons: the name of a real person, group, place, object or event from that section, 1 to 5 words, most specific first (for example "Freddie Mercury", "Wembley Stadium"). Names, not ideas. No politicians.
"subject" is the story's letter (A, B, C) for a story section and empty for the others. "uses" lists the ids of the facts the section's claims come from.
The title: under 70 characters, the main names first, plain and true, no emoji. The description: one sentence under 180 characters.

Reply with JSON only, in this shape:
{{"title": "...", "description": "...", "tags": ["8 to 12 search phrases"],
 "sections": [{{"chapter": "2 to 6 words", "subject": "A", "narration": "the spoken text as plain sentences", "pictures": ["...", "..."], "uses": ["A1", "A3"]}}]}}

STORIES AND FACTS
{packs}
"""

FIX = """Below are your script for a Quickplay Daily video and the problems a program found in it. Fix every problem and return the complete corrected script in the same JSON shape. Change only what the problems need and keep the rest word for word. Keep to the facts at the end: nothing that is not in them.

PROBLEMS
{problems}

YOUR SCRIPT
{script}

FACTS
{packs}
"""

CHECK = """You check a video script against the facts it may use. FACTS (the only things the script may state as fact):
{facts}

SCRIPT:
{script}

List every sentence of the script that states something the FACTS do not support: a number, date, name, place, quote, ranking, cause or event that is not in them, even when it is true in the real world. A sentence that only repeats or rephrases a fact is fine. A reading the script marks as its own ("that suggests", "one way to read it") is fine when it adds no new fact. If everything is supported, return an empty list.
Reply with JSON only: {{"unsupported": [{{"sentence": "...", "why": "..."}}]}}"""

CHECK_SCHEMA = {"type": "OBJECT", "properties": {"unsupported": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "sentence": {"type": "STRING"}, "why": {"type": "STRING"}}, "required": ["sentence"]}}}, "required": ["unsupported"]}

UK_SPELL = {"color": "colour", "colors": "colours", "colorful": "colourful", "colored": "coloured", "favorite": "favourite",
            "favorites": "favourites", "honor": "honour", "honors": "honours", "neighbor": "neighbour", "neighbors": "neighbours",
            "gray": "grey", "analyze": "analyse", "analyzed": "analysed", "realize": "realise", "realized": "realised",
            "organize": "organise", "organized": "organised", "recognize": "recognise", "recognized": "recognised",
            "apologize": "apologise", "defense": "defence", "offense": "offence", "theater": "theatre", "theaters": "theatres",
            "traveled": "travelled", "traveling": "travelling", "labeled": "labelled"}
UK_WORD = re.compile(r"(?<![\w'’-])(" + "|".join(sorted(UK_SPELL, key=len, reverse=True)) + r")(?![\w'’-])", re.I)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
US_DATE = re.compile(rf"\b({MONTHS}) (\d{{1,2}})(?:st|nd|rd|th)?\b(?:,? (\d{{4}}))?")
RELATIVE = re.compile(r"\b(today|tonight|yesterday|tomorrow)\b", re.I)
FIRST_PERSON = re.compile(r"\bI(?:'m|’m|'ve|’ve|'ll|’ll|'d|’d)?\s+[a-z]")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
POLITICAL = re.compile(r"white house|president|senator|congress|parliament|minister|campaign|rally|election|biden|harris|trump|obama|"
                       r"starmer|sunak|democrat|republican|labour party|conservative party", re.I)
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
                "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
                "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
                "thousand": 1000, "million": 1000000}


def uk_dates(s):
    return US_DATE.sub(lambda m: f"{int(m.group(2))} {m.group(1)}" + (f" {m.group(3)}" if m.group(3) else ""), s)


def uk_spelling(s):
    def fix(m):
        w = UK_SPELL[m.group(1).lower()]
        return w.capitalize() if m.group(1)[0].isupper() else w
    return UK_WORD.sub(fix, s)


def tidy(text):
    """Narration as plain speakable text: no markdown, links, hashtags, emoji or brackets, no dashes, UK dates and spelling."""
    s = str(text or "")
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", s)
    s = re.sub(r"https?://\S+|www\.\S+", "", s)
    s = re.sub(r"#\w+", "", s)
    s = re.sub(r"[#*_`~]+", "", s)
    s = re.sub("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]", "", s)
    s = undash(s.replace("\u2026", "..."))
    s = uk_spelling(uk_dates(s))
    return re.sub(r"\s+", " ", s).strip()


def first_of(d, *names):
    for n in names:
        if d.get(n) not in (None, "", []): return d[n]
    return None


def clean_script(raw, packs=()):
    """The model's JSON in the shape the rest expects: tidy text, lists of strings, each story section's subject letter (inferred
    from the facts it uses when the model left it out). Never raises."""
    raw = raw if isinstance(raw, dict) else {}
    ids = {p["id"] for p in packs}
    secs = []
    for s in raw.get("sections") or []:
        if not isinstance(s, dict): continue
        pics = first_of(s, "pictures", "images", "searches", "picture_searches") or []
        uses = first_of(s, "uses", "facts", "fact_ids") or []
        pics = [pics] if isinstance(pics, str) else pics
        uses = re.findall(r"[A-H]\d+", (" ".join(map(str, uses)) if isinstance(uses, (list, tuple)) else str(uses)).upper())
        subj = str(s.get("subject") or "").strip().upper()[:1]
        if subj not in ids:
            letters = [u[0] for u in uses if u[0] in ids]
            subj = max(set(letters), key=letters.count) if letters and letters.count(max(set(letters), key=letters.count)) * 2 > len(letters) else ""
        secs.append({"chapter": tidy(first_of(s, "chapter", "title", "heading"))[:60],
                     "subject": subj, "narration": tidy(first_of(s, "narration", "text", "script", "voiceover")),
                     "pictures": [re.sub(r"\s+", " ", undash(str(p))).strip(" .\"'") for p in pics if isinstance(p, (str, int))][:10],
                     "uses": list(dict.fromkeys(uses))})
    tags = raw.get("tags") or []
    return {"title": tidy(raw.get("title"))[:100], "description": tidy(raw.get("description"))[:300], "sections": secs,
            "tags": [tidy(t)[:40] for t in (tags if isinstance(tags, list) else []) if isinstance(t, str) and tidy(t)][:14]}


def pack_numbers(packs):
    text = " ".join(f["claim"] for p in packs for f in p["facts"])
    nums = set()
    for m in NUMBER.findall(text): nums.add(m.replace(",", "").rstrip(".").lstrip("0") or "0")
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in WORD_NUMBERS: nums.add(str(WORD_NUMBERS[w]))
    return nums


def word_count(s):
    return len(str(s or "").split())


def check_script(sc, packs, year=None):
    """(errors, warnings) for a cleaned script. Errors go back to the model for a fix round; a script with any left is not made."""
    e, w = [], []
    year = str(year or now_utc().year)
    secs = sc.get("sections") or []
    title = sc.get("title") or ""
    if not 12 <= len(title) <= 69: e.append(f"title: {len(title)} characters, it needs 12 to 69")
    if not 20 <= len(sc.get("description") or "") <= 200: w.append("description: one sentence of 20 to 200 characters")
    if not 5 <= len(secs) <= 8: e.append(f"sections: {len(secs)} given, it needs 5 to 8 (intro, one per story, what links them, outro)")
    total = sum(word_count(s["narration"]) for s in secs)
    if total < WORDS_OK[0]: e.append(f"narration: {total} words in all, it needs 1,100 to 1,400 (add detail from the facts, not new facts)")
    elif total > WORDS_OK[1]: e.append(f"narration: {total} words in all, it needs 1,100 to 1,400 (cut the weakest sentences)")
    known = {f["id"] for p in packs for f in p["facts"]}
    allowed = pack_numbers(packs) | {year}
    for i, s in enumerate(secs, 1):
        n, who = word_count(s["narration"]), f"section {i} ({s['chapter'] or 'no chapter title'})"
        if not 2 <= len(s["chapter"].split()) <= 8: e.append(f"{who}: the chapter title needs 2 to 8 words")
        if n < (150 if s["subject"] else 40): e.append(f"{who}: {n} words, too short" + (" for a story section (260 to 340 words)" if s["subject"] else ""))
        if n > 420: e.append(f"{who}: {n} words, too long (350 at most)")
        bad = [u for u in s["uses"] if u not in known]
        if bad: e.append(f"{who}: uses fact ids that do not exist: {', '.join(bad[:6])}")
        if s["subject"] and not [u for u in s["uses"] if u in known]: w.append(f"{who}: no fact ids in uses")
        nums = {m.replace(",", "").rstrip(".").lstrip("0") or "0" for m in NUMBER.findall(s["narration"])}
        loose = sorted(x for x in nums if x not in allowed and not (x.isdigit() and 1 <= int(x) <= 10))
        if loose: e.append(f"{who}: numbers that are not in the facts: {', '.join(loose[:6])} (use only numbers the facts give)")
        if US_DATE.search(s["narration"]): e.append(f"{who}: dates in UK order, '20 October'")
    text = " ".join([title, sc.get("description") or ""] + [s["narration"] for s in secs])
    for p in packs:
        words = [x for x in re.findall(r"[A-Za-z0-9']+", p["name"]) if len(x) >= 4] or [p["name"]]
        mine = " ".join(s["narration"] for s in secs if s["subject"] == p["id"]) or text
        if not any(x.lower() in mine.lower() for x in words): e.append(f"story {p['id']} ({p['name']}) is not named in its section")
    if not [s for s in secs if s["subject"]]: e.append("no section has a subject letter: each story needs its own section")
    for p in packs:
        if p["id"] not in {s["subject"] for s in secs}: e.append(f"story {p['id']} ({p['name']}) has no section of its own")
    banned, watch = rules()
    hits = sorted({h.lower() for h in banned.findall(text)})
    if hits: e.append(f"excluded topic or virality words: {hits}")
    if re.search(r"according to wikipedia|wikipedia (says|shows|states|lists|notes|reports)", text, re.I): e.append("never cite Wikipedia")
    rel = sorted({m.lower() for m in RELATIVE.findall(text)})
    if rel: e.append(f"never say {', '.join(rel)}: the video stays online for years; name the day or date")
    if FIRST_PERSON.search(text): e.append("anonymous channel: no 'I' or 'I'm' (we, at most twice)")
    if len(re.findall(r"\bwe\b", text, re.I)) > 3: e.append("anonymous channel: 'we' at most twice")
    watching = sorted({h.lower() for h in watch.findall(text)})
    if watching: w.append(f"check these words are fine in context: {watching}")
    return e, w


def rules():
    """The Shorts' excluded-topic and watch-word patterns (validate.py), with a copy to fall back on."""
    try:
        import validate as V
        return V.BANNED, V.WATCH
    except Exception:
        return (re.compile(r"\b(elections?|parliament\w*|politicians?|political|murder\w*|terroris\w*|porn\w*|casinos?|gambl\w*|betting|"
                           r"bookmakers?|lottery|crypto\w*|bitcoin|forex|went viral|goes viral|gone viral|viral video)\b", re.I),
                re.compile(r"\b(vote|voting|police|shooting|killed|arrest\w*|court|vaccine\w*|stocks?|shares|invest\w*)\b", re.I))


class ScriptError(Exception):
    pass


def ask_model(prompt, temperature=0.5, check=False):
    """JSON and the model's name from the free chain (factpack.gemini): the writing order for the script, the cheap models first
    for the fact check."""
    import factpack
    if check: return factpack.gemini(prompt, CHECK_SCHEMA, timeout=120, temperature=0.0, lite=True)
    return factpack.gemini(prompt, SCHEMA, timeout=240, temperature=temperature, writing=True)


def facts_flat(packs):
    return "\n".join(f"{f['id']}: {f['claim']}" for p in packs for f in p["facts"])


def fact_check(sc, packs, ask=None):
    """The sentences a second pass over the facts finds unsupported: [{"sentence", "why"}]. Raises ScriptError when no model can check."""
    ask = ask or ask_model
    script = "\n\n".join(f"[{s['chapter']}]\n{s['narration']}" for s in sc["sections"])
    prompt = CHECK.format(facts=facts_flat(packs), script=script)
    last = ""
    for attempt in range(2):
        try:
            ans, model = ask(prompt, check=True)
            if isinstance(ans, dict) and isinstance(ans.get("unsupported"), list):
                return [{"sentence": str(u.get("sentence", ""))[:400], "why": str(u.get("why", ""))[:200]} for u in ans["unsupported"]
                        if isinstance(u, dict) and str(u.get("sentence", "")).strip()], model
            last = "the check came back in the wrong shape"
        except Exception as ex:
            last = f"{type(ex).__name__}: {str(ex)[:160]}"
    raise ScriptError(f"the fact check could not run ({last})")


def write_script(packs, ask=None, rounds=2, checker=None, day=None):
    """The script: (script, info). One model call, then up to `rounds` fix rounds for whatever check_script or the fact check
    finds. Raises ScriptError when the model chain fails or a problem is left, so the week's build waits for the next run."""
    ask = ask or ask_model
    names = ", ".join(p["name"] for p in packs)
    prompt = PROMPT.format(n=len(packs), names=names, packs=pack_text(packs))
    info = {"model": "", "rounds": 0, "warnings": [], "fact_check": ""}
    try: raw, model = ask(prompt)
    except Exception as ex: raise ScriptError(f"no model answered ({type(ex).__name__}: {str(ex)[:200]})")
    sc = clean_script(raw, packs); info["model"] = model
    year = day.year if day else None
    for k in range(rounds + 1):
        errs, warns = check_script(sc, packs, year)
        unsupported = []
        if not errs:
            unsupported, cmodel = fact_check(sc, packs, checker or ask)
            info["fact_check"] = f"{cmodel}: " + ("passed" if not unsupported else f"{len(unsupported)} unsupported")
            errs = [f"not supported by the facts: \"{u['sentence']}\"" + (f" ({u['why']})" if u["why"] else "") for u in unsupported]
        if not errs:
            info["warnings"] = warns; return sc, info
        if k == rounds: raise ScriptError("problems left after the fix rounds: " + " | ".join(errs)[:900])
        info["rounds"] = k + 1
        fix = FIX.format(problems="\n".join(f"- {x}" for x in errs), script=json.dumps(sc, ensure_ascii=False), packs=pack_text(packs))
        try: raw, model = ask(fix, temperature=0.2)
        except Exception as ex: raise ScriptError(f"no model answered the fix round ({type(ex).__name__}: {str(ex)[:200]})")
        sc = clean_script(raw, packs); info["model"] = model
    raise ScriptError("unreachable")


def ensure_pictures(sc, packs):
    """Picture searches per section: tidy, no politicians, no repeats; every story section starts with its subject's name and the
    other sections carry every subject's name, so a section the model gave too few searches still has pictures to look for."""
    by = {p["id"]: p for p in packs}
    for s in sc["sections"]:
        seen, out = set(), []
        names = [by[s["subject"]]["name"]] if s["subject"] in by else [p["name"] for p in packs]
        for q in names + s["pictures"]:
            q = re.sub(r"\s+", " ", str(q)).strip()
            if not 2 <= len(q) <= 60 or POLITICAL.search(q) or key_of(q) in seen: continue
            seen.add(key_of(q)); out.append(q)
        s["pictures"] = out[:8]
    return sc


# ---------------- beats and the voice ----------------
ABBR = {"mr", "mrs", "ms", "dr", "st", "vs", "no", "jr", "sr", "inc", "ltd", "co", "etc", "feat", "approx", "prof", "gen", "lt"}
BEAT_WORDS = 26             # Chatterbox garbles a long sentence far more often than two short ones (run_board.halves)


def sentences(text):
    toks, out, cur = str(text).split(), [], []
    for i, t in enumerate(toks):
        cur.append(t)
        bare = t.lower().rstrip(".!?\"')]")
        if re.search(r"[.!?][\"')\]]*$", t) and bare not in ABBR and not re.fullmatch(r"(?:[A-Za-z]\.){2,}|[A-Z]\.", t):
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if not nxt or nxt[0].isupper() or nxt[0].isdigit() or nxt[0] in "\"'(": out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    return out


def split_long(s, limit=BEAT_WORDS):
    """A sentence over `limit` words in two, at a comma or a joining word near the middle (else at the middle)."""
    words = s.split()
    if len(words) <= limit: return [s]
    mid = len(words) / 2
    joins = {"and", "but", "so", "because", "which", "while", "when", "after", "before", "then", "with", "as", "where"}
    best = None
    for i in range(max(4, int(len(words) * 0.25)), min(len(words) - 3, int(len(words) * 0.75)) + 1):
        if words[i - 1].endswith((",", ";", ":")): score = abs(i - mid)
        elif words[i].lower().strip(",.") in joins: score = abs(i - mid) + 1
        else: continue
        if best is None or score < best[0]: best = (score, i)
    i = best[1] if best else int(mid)
    a, b = " ".join(words[:i]).rstrip(",;: "), " ".join(words[i:])
    a = a + ("" if a[-1:] in ".?!" else ".")
    return split_long(a, limit) + split_long(b[:1].upper() + b[1:], limit)


def split_beats(sections):
    """[{"sec": section index, "text", "words"}]: one beat per sentence, long ones split, a very short one joined to the next."""
    beats = []
    for si, s in enumerate(sections):
        parts = []
        for sent in sentences(s["narration"]): parts += split_long(sent)
        merged = []
        for p in parts:
            if merged and (word_count(merged[-1]) < 4 or word_count(p) < 3) and word_count(merged[-1]) + word_count(p) <= BEAT_WORDS:
                merged[-1] = merged[-1] + " " + p
            else: merged.append(p)
        for p in merged:
            if not re.search(r"[.!?]$", p): p += "."
            beats.append({"sec": si, "text": p, "words": word_count(p)})
    return beats


def sh(*cmd, cwd=None, timeout=None):
    log("$", " ".join(map(str, cmd)))
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd, timeout=timeout)


def run_tts(beats, work, voice="F2", wps=2.9, sh=sh):
    """Reads every beat with tts_cb.py (the Shorts' Chatterbox, one WAV a beat); beats the ear check found unclear are read again
    with other seeds and the clearer read kept. Returns (directory of cb_bNN.wav, manifest)."""
    board = work / "voice_board.json"
    board.write_text(json.dumps({"id": "EXPLAINER", "beats": [{"say": b["text"]} for b in beats]}))
    out = work / "voice"
    sh(sys.executable, HERE / "tts_cb.py", board, out, "--voice", voice, "--target-wps", wps, cwd=HERE, timeout=130 * 60)
    man = json.loads((out / "cb_manifest.json").read_text())
    by = {b["beat"]: b for b in man["beats"]}
    for seed in (2, 3):
        weak = sorted(i for i, b in by.items() if b["recall"] < 0.4 and beats[i]["words"] >= 4)
        if not weak: break
        again = work / f"voice{seed}"
        log(f"{len(weak)} unclear beats read again (seed {seed})")
        try: sh(sys.executable, HERE / "tts_cb.py", board, again, "--voice", voice, "--target-wps", wps, "--seed", seed,
                "--beats", ",".join(map(str, weak)), cwd=HERE, timeout=40 * 60)
        except Exception as ex:
            log(f"re-read failed: {str(ex)[:160]}"); break
        for b in json.loads((again / "cb_manifest.json").read_text())["beats"]:
            if b["recall"] > by[b["beat"]]["recall"]:
                (out / by[b["beat"]]["file"]).write_bytes((again / b["file"]).read_bytes())
                by[b["beat"]].update(recall=b["recall"], dur=b["dur"])
    man["unclear"] = sorted(i for i, b in by.items() if b["recall"] < 0.4 and beats[i]["words"] >= 4)
    return out, man


def layout(beats, durs):
    """When everything happens, in seconds. The first section starts at 0 with its words at LEAD; section k > 0 starts SEC_PAUSE
    after the last words of the one before and its first words come NARR_IN later, over its chapter card. Returns {"starts":
    when each beat's words begin, "sec": [{"index", "start", "end"}], "total", "end_card"}: a section's visuals run from its
    start to the next one's start, the last for TAIL more seconds, then the end card."""
    starts, sec, cur, t, last_end = [], {}, None, LEAD, 0.0
    for b, d in zip(beats, durs):
        k = b["sec"]
        if k != cur:
            if cur is None: sec[k] = {"start": 0.0}
            else:
                begin = last_end + SEC_PAUSE
                sec[k] = {"start": begin}; t = begin + NARR_IN
            cur = k
        starts.append(t); last_end = t + d; t = last_end + GAP
    ks = sorted(sec)
    for a, b in zip(ks, ks[1:]): sec[a]["end"] = sec[b]["start"]
    sec[ks[-1]]["end"] = last_end + TAIL
    return {"starts": starts, "sec": [dict(sec[k], index=k) for k in ks], "total": sec[ks[-1]]["end"] + END_CARD,
            "end_card": sec[ks[-1]]["end"]}


def beat_files(man, voice_dir, n):
    by = {b["beat"]: b for b in man["beats"]}
    return [voice_dir / by[i]["file"] for i in range(n)]


def audio_durations(files):
    import soundfile as sf
    return [sf.info(str(f)).duration for f in files]


def assemble_audio(files, starts, total, out):
    """One narration WAV of `total` seconds with every beat at its start time."""
    import numpy as np, soundfile as sf
    sr = sf.info(str(files[0])).samplerate
    y = np.zeros(int(math.ceil(total * sr)), dtype=np.float32)
    for f, s in zip(files, starts):
        w, wsr = sf.read(str(f), dtype="float32")
        if w.ndim > 1: w = w.mean(axis=1)
        i = int(round(s * sr))
        if i < len(y): y[i:i + len(w)] += w[:len(y) - i]
    sf.write(str(out), np.clip(y, -1.0, 1.0), sr)
    return out


def pick_music(day, work):
    """(path, credit line) of a calm track from pipeline/music (decrypted with MUSIC_KEY, like the Shorts' music); (None, "") when
    there is no key, no track or config.json explainer.music is false. A different track each week."""
    if cfg().get("music") is False: return None, ""
    cat = load_json(HERE / "music" / "catalog.json", []) or []
    pool = [c for c in cat if c.get("mood") in ("Calm", "Inspirational", "Bright")] or list(cat)
    pool.sort(key=lambda c: hashlib.sha1(f"{day}:{c.get('slug')}".encode()).hexdigest())
    key = os.environ.get("MUSIC_KEY", "")
    for c in pool[:6]:
        mp3 = HERE / "music" / f"{c['slug']}.mp3"
        if not mp3.exists():
            enc = HERE / "music" / f"{c['slug']}.mp3.enc"
            if len(key) < 8 or not enc.exists(): continue
            mp3 = work / f"{c['slug']}.mp3"
            r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", str(enc), "-out", str(mp3), "-pass", "env:MUSIC_KEY"],
                               capture_output=True)
            if r.returncode or not mp3.exists() or mp3.stat().st_size < 10000: continue
        return mp3, f"Music: {c['title']} by {c['artist']} ({c.get('source') or 'YouTube Audio Library'})"
    return None, ""


def mix_audio(narration, music, total, out):
    """The narration at -16 LUFS with the music bed under it (and faded at both ends), as one AAC-ready WAV of `total` seconds."""
    voice = "[0:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,apad[v];"
    if music:
        fc = (voice + f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.12,afade=t=in:d=3,afade=t=out:st={max(0, total - 4):.2f}:d=4[m];"
              "[v][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", narration, "-stream_loop", "-1", "-i", music, "-filter_complex", fc,
               "-map", "[a]", "-t", f"{total:.2f}", out]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", narration, "-filter_complex", voice[:-1].replace("[v]", "[a]"), "-map", "[a]", "-t", f"{total:.2f}", out]
    subprocess.run([str(c) for c in cmd], check=True)
    return out


# ---------------- pictures ----------------
CATEGORY_STOCK = {"Music": ["concert stage lights", "vinyl record player"], "Film": ["cinema screen", "film reel"],
                  "Sport": ["football stadium", "sports crowd"], "Gaming": ["video game controller", "gaming setup"],
                  "Tech": ["circuit board", "smartphone"], "Science": ["telescope night sky", "laboratory"],
                  "Entertainment": ["theatre stage", "red carpet lights"]}


IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


def section_board(day, name, section, pack, searches=None):
    """A board-shaped dict for fetch_media.resolve: one beat holding the section's picture searches as shots (Commons name
    searches, or the given shot sources). The beat's text and the subject steer the relevance ranker."""
    srcs = searches if searches is not None else [f"commons-search:{q}" for q in section["pictures"]]
    return {"id": f"EX-{day:%Y%m%d}-{name}", "category": (pack or {}).get("category", ""),
            "meta": {"tags": [pack["name"]] if pack else []},
            "beats": [{"say": section["narration"][:240], "shots": [{"src": s, "label": {"t": s.partition(":")[2].rpartition(":")[2]}} for s in srcs]}]}


def fetch_pictures(sc, packs, day, resolve=None, extras=None):
    """{section index: [{"path", "credit", "source", "relevance", "from"}]}: each section's pictures that were found, in the order
    of its searches (path absolute). Commons name searches first, then fetch_media.extras for a section with few; a section
    left with fewer than 3 asks Pixabay for its category's photos when that key is set. Never raises: a section with no
    pictures gets cards."""
    if resolve is None:
        import fetch_media
        try: fetch_media.PX.BUDGET_S = 150              # seconds of picture ranking a section may use
        except Exception: pass
        resolve, extras = fetch_media.resolve, extras or fetch_media.extras
    by = {p["id"]: p for p in packs}
    out = {}
    for k, s in enumerate(sc["sections"]):
        pack, got = by.get(s["subject"]), []

        def collect(sb):
            for shot in sb["beats"][0].get("shots") or []:
                f = HERE / str(shot.get("src", ""))
                if f.suffix.lower() in IMAGE_EXT and f.exists() and str(f) not in {g["path"] for g in got}:
                    got.append({"path": str(f), "credit": shot.get("credit", ""), "source": shot.get("source", ""),
                                "relevance": shot.get("relevance"), "from": shot.get("from", "")})
        sb = section_board(day, k, s, pack)
        try:
            resolve(sb)
            if extras and len(sb["beats"][0]["shots"]) < 6:
                try: extras(sb, per=1, cap=5, seconds=40)
                except Exception as ex: log(f"  section {k + 1}: extra photos skipped: {str(ex)[:100]}")
            collect(sb)
        except Exception as ex:
            log(f"  section {k + 1}: no Commons pictures ({str(ex)[:140]})")
        stock = CATEGORY_STOCK.get((pack or packs[0]).get("category", ""), [])[:2]
        if len(got) < 3 and stock and os.environ.get("PIXABAY_API_KEY"):
            sb2 = section_board(day, f"{k}s", s, pack, [f"pixabay:image:{q}" for q in stock])
            try: resolve(sb2); collect(sb2)
            except Exception as ex: log(f"  section {k + 1}: no stock pictures either ({str(ex)[:100]})")
        out[k] = got
        log(f"  section {k + 1} ({s['chapter']}): {len(got)} pictures")
    return out


def ahash(path):
    """A 64-bit average hash of a picture, or None when it cannot be read or is too small to fill the screen (under 600 x 360)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            if im.width < 600 or im.height < 360: return None
            g = list(im.convert("L").resize((8, 8)).getdata())
    except Exception: return None
    m = sum(g) / 64
    return sum(1 << i for i, v in enumerate(g) if v >= m)


def credit_text(p):
    return clean_line(p.get("credit", ""))[:160]


def credit_lines(pics, limit=2600):
    """One line per distinct credit of the pictures in the video: "Photo: X, CC BY-SA 4.0, via Wikimedia Commons (address)" for as
    many as fit in `limit` characters, the rest without the address."""
    seen, rows = set(), []
    for p in pics:
        c = credit_text(p)
        if c and (c, p.get("source")) not in seen:
            seen.add((c, p.get("source"))); rows.append((c, clean_line(p.get("source", ""))))
    budget = limit - sum(len(c) + 1 for c, _ in rows)
    out = []
    for c, src in rows:
        if src and len(src) + 3 <= budget: out.append(f"{c} ({src})"); budget -= len(src) + 3
        else: out.append(c)
    return out


def select_pictures(found, max_total=MAX_PICS, per_section=7, credit_room=2600):
    """The pictures the video uses, {section: [picture]} in each section's order: unreadable and tiny files out, the same photo
    found twice (a near-duplicate hash) kept once, at most `per_section` in a section and `max_total` in all, and few enough
    that every credit fits the description (`credit_room` characters). The least relevant go first, from the biggest section."""
    seen, out = [], {}
    for k in sorted(found):
        keep = []
        for p in found[k]:
            if len(keep) >= per_section: break
            h = ahash(p["path"])
            if h is None or any(bin(h ^ o).count("1") <= 6 for o in seen): continue
            seen.append(h); keep.append(dict(p, hash=h))
        out[k] = keep

    def too_many():
        flat = [p for v in out.values() for p in v]
        return len(flat) > max_total or sum(len(credit_text(p)) + 1 for p in flat) > credit_room
    while too_many():
        k = max(out, key=lambda j: len(out[j]))
        if len(out[k]) <= 1: break
        worst = min(range(len(out[k])), key=lambda i: (out[k][i].get("relevance") if isinstance(out[k][i].get("relevance"), (int, float)) else 0.5, -i))
        out[k].pop(worst)
    return out


# ---------------- what is on screen ----------------
STOP = frozenset("""that this with from they their there were have been which would about after before into over than then them also
only some such what when where while will your more most other these those just like year years week first last""".split())


def content_words(s):
    return {w for w in re.findall(r"[a-z0-9']{4,}", str(s).lower()) if w not in STOP}


def source_note(pack, fact):
    """"Source: Official Charts" for the first source of a fact: the outlet before the colon of its title, else its site."""
    by = {s["n"]: s for s in pack["sources"]}
    s = by.get((fact.get("sources") or [0])[0])
    if not s: return ""
    name = s["title"].split(":", 1)[0].strip() if ":" in s["title"] else re.sub(r"^www\.", "", re.sub(r"^https?://", "", s["url"]).split("/")[0])
    return f"Source: {name[:60]}"


def fact_cards(sc, packs, beats, durs, lay):
    """[{"t0", "t1", "text", "note", "kicker", "section"}]: up to two of the facts a story section uses, each shown while the
    narration is on it (the beat that shares most of its words), after the section's chapter card and before its end."""
    by = {f["id"]: (p, f) for p in packs for f in p["facts"]}
    secs = {s["index"]: s for s in lay["sec"]}
    out = []
    for k, s in enumerate(sc["sections"]):
        if not s["subject"] or k not in secs: continue
        mine, last = [], -99.0
        for fid in s["uses"]:
            if fid not in by or len(mine) >= 2: continue
            p, f = by[fid]
            if not 25 <= len(f["claim"]) <= 150: continue
            cw = content_words(f["claim"])
            scored = [(len(cw & content_words(b["text"])), i) for i, b in enumerate(beats) if b["sec"] == k]
            if not scored: continue
            score, i = max(scored, key=lambda x: (x[0], -x[1]))          # the best match, the first mention when several tie
            if score < min(3, len(cw)) or score < 0.5 * len(cw): continue
            t0 = max(lay["starts"][i] + 0.2, secs[k]["start"] + (CARD + 0.3 if k else 1.0))
            t1 = min(t0 + max(4.0, min(7.5, durs[i] + 1.2)), secs[k]["end"] - 0.5)
            if t1 - t0 < 3.0 or t0 < last + 5.0: continue
            last = t1
            mine.append({"t0": round(t0, 2), "t1": round(t1, 2), "text": f["claim"], "note": source_note(p, f), "kicker": p["name"], "section": k})
        out += mine
    return out


def card_image(path, text, kicker, note, fp):
    """A fact card: the claim large on the dark background, the subject above it, the source below."""
    import weekly as WK
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), INK); d = ImageDraw.Draw(im)
    d.ellipse([-300, -200, 700, 800], fill=(22, 60, 62)); d.ellipse([1300, 500, 2200, 1400], fill=(40, 34, 24))
    size = 86
    while True:
        f = WK.font(fp["display"], size); lines = WK.wrap(d, text, f, 1440)
        if len(lines) <= 5 or size <= 54: break
        size -= 6
    y0 = max(250, int((H - len(lines[:6]) * size * 1.22) / 2) - 20)
    d.rectangle([150, y0 - 10, 158, y0 + len(lines[:6]) * int(size * 1.22) + 4], fill=ACCENT)
    d.text((210, y0 - 74), kicker.upper(), font=WK.font(fp["body"], 38), fill=ACCENT)
    y = y0
    for line in lines[:6]:
        d.text((210, y), line, font=f, fill=WHITE); y += int(size * 1.22)
    if note: d.text((210, min(H - 120, y + 40)), note, font=WK.font(fp["body"], 34), fill=MUTED)
    im.save(path)
    return path


def face_focus(path):
    """The largest face of a picture as (x, y) fractions of its size, or None (YuNet through faces.py; no OpenCV, model or face: None)."""
    try:
        import cv2, faces as FC
        img = cv2.imread(str(path))
        if img is None: return None
        h, w = img.shape[:2]; sc = min(1.0, 800 / max(w, h))
        small = cv2.resize(img, (int(w * sc), int(h * sc))) if sc < 1 else img
        found = FC.yunet_faces(small, max(24, int(min(small.shape[:2]) * 0.06)))
        if found is None or len(found) == 0: return None
        x, y, fw, fh = max(found, key=lambda f: f[2] * f[3])
        return (round(float(x + fw / 2) / small.shape[1], 3), round(float(y + fh / 2) / small.shape[0], 3))
    except Exception: return None


MOVES = {"in": lambda u: (1.00 + 0.10 * u, None, None), "out": lambda u: (1.10 - 0.10 * u, None, None),
         "left": lambda u: (1.08, 0.85 - 0.70 * u, None), "right": lambda u: (1.08, 0.15 + 0.70 * u, None),
         "up": lambda u: (1.08, None, 0.85 - 0.70 * u), "down": lambda u: (1.08, None, 0.15 + 0.70 * u),
         "hold": lambda u: (1.0, None, None)}
CYCLE = ("in", "left", "out", "right", "up", "down")
CROPS = (1.0, 1.26, 1.13)             # a picture used again comes back closer, then a little closer than the full view


class Still:
    """One picture as a shot. A landscape picture fills the screen and moves slowly over it (a push in, a pull out, a pan); a
    portrait or square one is shown whole over a blurred, darkened copy of itself. frame(t, dur) is the picture t seconds into
    a shot of dur seconds; t may run a little past dur, so the move goes on under the next shot's crossfade. The window is a
    fractional box handed to PIL's resize, so the motion is smooth to a fraction of a pixel."""
    def __init__(self, src, move="in", crop=1.0, focus=None):
        from PIL import Image, ImageEnhance
        im = src if hasattr(src, "size") else Image.open(src)
        if not hasattr(src, "size"): im.draft("RGB", (2 * W, 2 * H))
        im = im.convert("RGB")
        if max(im.size) > 2560: im.thumbnail((2560, 2560), Image.LANCZOS)
        self.im, self.move, self.crop, self.focus = im, move if move in MOVES else "in", crop, focus or (0.5, 0.5)
        iw, ih = im.size
        self.cover = iw / ih >= 1.3
        if not self.cover:
            s = max(W / iw, H / ih)
            small = im.resize((max(1, int(iw * s / 4)), max(1, int(ih * s / 4))), Image.BILINEAR)
            left, top = max(0, (small.width - W // 4) // 2), max(0, (small.height - H // 4) // 2)
            from PIL import ImageFilter
            bg = small.crop((left, top, left + W // 4, top + H // 4)).resize((W // 4, H // 4)).filter(ImageFilter.GaussianBlur(7))
            self.bg = ImageEnhance.Brightness(bg.resize((W, H), Image.BILINEAR)).enhance(0.5)
            f = min(H * 0.94 / ih, W * 0.94 / iw)
            self.size = (max(2, int(iw * f)), max(2, int(ih * f)))

    def frame(self, t, dur):
        from PIL import Image
        u = min(1.25, max(0.0, t / max(dur, 0.1)))
        z, px, py = MOVES[self.move if self.cover else {"left": "in", "up": "in", "right": "out", "down": "out"}.get(self.move, self.move)](u)
        z = max(1.0, z * (self.crop if self.cover else 1.0))
        iw, ih = self.im.size
        if self.cover:
            bw = min(iw, ih * W / H); bh = bw * H / W
        else:
            bw, bh = iw, ih
        ww, wh = bw / z, bh / z
        fx, fy = self.focus
        x0 = (iw - ww) * min(1.0, max(0.0, px)) if px is not None else min(max(fx * iw - ww / 2, 0.0), iw - ww)
        y0 = (ih - wh) * min(1.0, max(0.0, py)) if py is not None else min(max(fy * ih - wh / 2, 0.0), ih - wh)
        if self.cover:
            return self.im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + ww, y0 + wh))
        out = self.bg.copy()
        fg = self.im.resize(self.size, Image.BILINEAR, box=(x0, y0, x0 + ww, y0 + wh))
        out.paste(fg, ((W - self.size[0]) // 2, (H - self.size[1]) // 2))
        return out


def plan_visuals(lay, pics, cards, sc, packs, files):
    """The video as shots in time order, each {"t0", "t1", "kind", "path", "move", "crop", "focus"}: a chapter card at the start of
    every section after the first, the section's fact cards while the narration is on them, and the section's pictures in
    between (a picture holds about HOLD seconds; when there are fewer pictures than shots they come round again closer and
    with another move). A section with no picture shows its subject's card. `files` holds the card images made so far."""
    segs, uses, n = [], {}, [0]
    by = {p["id"]: p for p in packs}

    def pic_shot(t0, t1, k):
        pool = pics.get(k) or []
        if pool:
            # the picture used least so far, in the section's order
            p = min(pool, key=lambda q: (uses.get(q["path"], 0), pool.index(q)))
            c = uses.get(p["path"], 0); uses[p["path"]] = c + 1
            segs.append({"t0": t0, "t1": t1, "kind": "pic", "path": p["path"], "crop": CROPS[c % 3], "focus": p.get("focus"),
                         "move": CYCLE[n[0] % len(CYCLE)]})
        else:
            segs.append({"t0": t0, "t1": t1, "kind": "card", "path": files["subject"][sc["sections"][k]["subject"] or "all"], "crop": 1.0, "focus": None, "move": "hold"})
        n[0] += 1

    def fill(a, b, k):
        span = b - a
        if span <= 0.05:
            if span > 0 and segs: segs[-1]["t1"] = b                    # a sliver: the shot before runs on
            return
        cnt = max(1, int(round(span / HOLD)))
        while span / cnt > HOLD_MAX: cnt += 1
        while cnt > 1 and span / cnt < HOLD_MIN: cnt -= 1
        for j in range(cnt): pic_shot(a + span * j / cnt, a + span * (j + 1) / cnt, k)
    for s in lay["sec"]:
        k, t = s["index"], s["start"]
        if k > 0:
            segs.append({"t0": t, "t1": t + CARD, "kind": "chapter", "path": files["chapter"][k], "crop": 1.0, "focus": None, "move": "hold"}); t += CARD
        mine = sorted((c for c in cards if c["section"] == k and c["t0"] >= t and c["t1"] <= s["end"]), key=lambda c: c["t0"])
        for c in mine:
            c0 = t if c["t0"] - t < 3.0 else c["t0"]
            fill(t, c0, k)
            segs.append({"t0": c0, "t1": c["t1"], "kind": "card", "path": c["path"], "crop": 1.0, "focus": None, "move": "hold"}); t = c["t1"]
        if s["end"] - t < 2.5 and segs and segs[-1]["kind"] != "chapter": segs[-1]["t1"] = s["end"]
        else: fill(t, s["end"], k)
    segs.append({"t0": lay["end_card"], "t1": lay["total"], "kind": "end", "path": files["end"], "crop": 1.0, "focus": None, "move": "hold"})
    return segs


def caption_strip(text, fp, width=1500):
    """The small caption under the picture: one to three lines on a soft dark band, as an RGBA image."""
    import weekly as WK
    from PIL import Image, ImageDraw
    f = WK.font(fp["body"], 38)
    lines = WK.wrap(ImageDraw.Draw(Image.new("RGB", (8, 8))), text, f, width - 90)[:3]
    h = 30 + 52 * len(lines)
    im = Image.new("RGBA", (width, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width - 1, h - 1], radius=20, fill=(8, 12, 18, 150))
    y = 15
    for line in lines:
        d.text(((width - d.textlength(line, font=f)) / 2, y), line, font=f, fill=WHITE + (255,)); y += 52
    return im


def render(segs, caps, total, audio, out, fp, captions=True):
    """Every frame of the video, made with PIL and piped to ffmpeg together with the audio. caps: [(t0, t1, text)]."""
    from PIL import Image
    n = int(math.ceil(total * FPS))
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
           "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", "192k", "-ar", "48000", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    stills, strips, black = {}, {}, Image.new("RGB", (W, H))

    def still(i):
        if i not in stills:
            s = segs[i]
            try: stills[i] = Still(s["path"], s["move"], s["crop"], s.get("focus"))
            except Exception as ex:
                log(f"  shot {i}: {s['path']} could not be opened ({type(ex).__name__}), a plain card instead")
                stills[i] = Still(Image.new("RGB", (W, H), INK), "hold")
            for old in [j for j in stills if j < i - 1]: del stills[old]
        return stills[i]
    i, c = 0, 0
    try:
        for fi in range(n):
            t = fi / FPS
            while i + 1 < len(segs) and t >= segs[i + 1]["t0"] - 1e-9: i += 1
            s = segs[i]
            img = still(i).frame(t - s["t0"], s["t1"] - s["t0"])
            if i > 0 and t - s["t0"] < FADE:
                p = segs[i - 1]
                img = Image.blend(still(i - 1).frame(t - p["t0"], p["t1"] - p["t0"]), img, (t - s["t0"]) / FADE)
            if t < FADE: img = Image.blend(black, img, t / FADE)
            elif t > total - 0.8: img = Image.blend(img, black, min(1.0, (t - (total - 0.8)) / 0.8))
            if captions:
                while c < len(caps) and t >= caps[c][1]: c += 1
                if c < len(caps) and caps[c][0] <= t < caps[c][1] and segs[i]["kind"] in ("pic", "card", "chapter"):
                    if c not in strips: strips[c] = caption_strip(caps[c][2], fp)
                    st = strips[c]; img.paste(st, ((W - st.width) // 2, H - st.height - 56), st)
            proc.stdin.write(img.tobytes())
            if fi % 1500 == 0: log(f"  frame {fi} of {n}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    rc = proc.wait()
    if rc: raise RuntimeError(f"ffmpeg stopped with exit code {rc} while the frames were being written")
    return out


def make_thumbnail(path, pic, names, fp):
    """The 1280 x 720 thumbnail: the lead subject's picture darkened, the names large. (A custom thumbnail needs a verified channel.)"""
    import weekly as WK
    from PIL import Image, ImageDraw, ImageEnhance
    TW, TH = 1280, 720
    im = Image.new("RGB", (TW, TH), INK)
    if pic:
        try:
            src = Image.open(pic).convert("RGB"); s = max(TW / src.width, TH / src.height)
            src = src.resize((int(src.width * s) + 1, int(src.height * s) + 1), Image.BILINEAR)
            l, t = (src.width - TW) // 2, (src.height - TH) // 2
            im = ImageEnhance.Brightness(src.crop((l, t, l + TW, t + TH))).enhance(0.5)
        except Exception: pass
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 18, TH], fill=ACCENT)
    d.text((64, 70), "THIS WEEK EXPLAINED", font=WK.font(fp["body"], 46), fill=ACCENT)
    y = 170
    for name in names[:3]:
        size = 124
        while size > 56 and d.textlength(name.upper(), font=WK.font(fp["display"], size)) > TW - 130: size -= 8
        d.text((64, y), name.upper(), font=WK.font(fp["display"], size), fill=WHITE); y += int(size * 1.2)
    im.save(path, quality=88)
    return path


def hashtag(name):
    return "#" + re.sub(r"[^A-Za-z0-9]", "", name)


def build_description(sc, packs, chapters, pics, music_line=""):
    """The video's description: the one-line summary, chapters, the Shorts on these stories, where every fact comes from (the
    sources of the packs), every picture credit and the music. Over DESC_LIMIT characters it drops the Shorts first, then the
    credits' addresses, then the sources beyond the first three of a story: chapters and the sources stay."""
    shorts = []
    for p in packs:
        shorts += [f"{s['title']}: https://youtube.com/shorts/{s['video']}" for s in p["shorts"][:2] if s.get("video")]
    tags = " ".join([hashtag(p["name"]) for p in packs if len(hashtag(p["name"])) > 2][:3] + ["#QuickplayDaily", "#Explainer"])
    foot = ["Independent channel, not affiliated with the companies or people featured. Every fact comes from the sources above.", "", tags]

    def make(with_shorts, addresses, per_story):
        L = [sc["description"], "", "Chapters"] + [f"{stamp(t)} {c}" for t, c in chapters]
        if with_shorts and shorts: L += ["", "The Shorts on these stories"] + shorts
        L += ["", "Where every fact comes from"]
        for p in packs: L += [p["name"]] + [f"{s['title']}: {s['url']}" for s in p["sources"][:per_story]]
        cr = credit_lines(pics, limit=2600 if addresses else 0)
        if cr: L += ["", "Pictures"] + cr
        if music_line: L += ["", music_line]
        return re.sub(r"[<>]", "", "\n".join(L + [""] + foot))
    for with_shorts, addresses, per_story in ((True, True, 9), (False, True, 9), (False, False, 9), (False, False, 3)):
        text = make(with_shorts, addresses, per_story)
        if len(text) <= DESC_LIMIT: return text
    return text[:DESC_LIMIT].rsplit("\n", 1)[0]


def youtube_tags(sc, packs):
    out, used = [], 0
    for t in list(sc.get("tags") or []) + [p["name"] for p in packs] + ["explainer", "this week", "quickplay daily"]:
        t = str(t).strip()
        if not t or t.lower() in {x.lower() for x in out}: continue
        if used + len(t) + 3 > 450 or len(out) >= 15: break
        out.append(t); used += len(t) + 3
    return out


# ---------------- build ----------------
def board_of(sid):
    for d in ("done", "ready", "queue", "hold", "test", "reserve", "failed", "expired"):
        p = ROOT / "boards" / d / f"{sid}.json"
        if p.exists(): return load_json(p, {}) or {}
    return {}


def shorts_rows():
    p = ROOT / "analytics" / "shorts.csv"
    return list(csv.DictReader(io.StringIO(p.read_text()))) if p.exists() else []


def build(out, dry=False, now=None, script_file="", captions=None, ask=None):
    """Makes the week's video in `out`: video.mp4, thumb.jpg and explainer.json (what was made, or why not: state "skipped" for a
    thing the next run may fix, "failed" for a crash, which is also raised). Needs the build job's install."""
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    now = now or now_utc()
    day = target_day(now.astimezone(UK).date())
    man = {"kind": "explainer", "day": str(day), "dry": bool(dry), "at": now.isoformat(timespec="minutes"), "state": "building"}

    def done(state, **kw):
        man.update(state=state, **kw)
        (out / "explainer.json").write_text(json.dumps(man, indent=1, ensure_ascii=False))
        log(f"explainer {state}: {man.get('reason') or man.get('title') or ''}")
        return man
    try:
        return _build(out, man, done, day, now, script_file, captions, ask)
    except ScriptError as ex:
        return done("skipped", reason=str(ex)[:700])
    except Exception as ex:
        done("failed", reason=f"{type(ex).__name__}: {str(ex)[:500]}")
        raise


def _build(out, man, done, day, now, script_file, captions, ask):
    import weekly as WK
    c = cfg()
    work = pathlib.Path(tempfile.mkdtemp(prefix="explainer-"))
    want = int(c.get("subjects") or 3)
    subjects = pick_subjects(shorts_rows(), board_of, now, n=want + 3)
    topics = (load_json(ROOT / "trends" / "facts.json", {}) or {}).get("topics") or []
    ranked = build_packs(subjects, board_of, topics)
    chosen = [s for s, p in zip(subjects, ranked) if len(p["facts"]) >= 4][:want]
    if len(chosen) < want:
        return done("skipped", reason=f"only {len(chosen)} subjects with 4 or more checked facts among the Shorts of the last 7 days")
    packs = build_packs(chosen, board_of, topics)
    man["subjects"] = [{"name": p["name"], "views": p["views"], "shorts": [s["id"] for s in p["shorts"]], "facts": len(p["facts"])} for p in packs]
    log("subjects:", ", ".join(f"{p['name']} ({p['views']:,} views, {len(p['facts'])} facts)" for p in packs))
    if script_file:
        sc, info = clean_script(json.loads(pathlib.Path(script_file).read_text()), packs), {"model": "file", "rounds": 0, "warnings": [], "fact_check": "not run"}
    else:
        sc, info = write_script(packs, ask=ask, day=day)
    sc = ensure_pictures(sc, packs)
    man.update(title=sc["title"], model=info["model"], fix_rounds=info["rounds"], fact_check=info["fact_check"], warnings=info["warnings"],
               words=sum(word_count(s["narration"]) for s in sc["sections"]))
    (out / "script.json").write_text(json.dumps(sc, indent=1, ensure_ascii=False))
    log(f"script: {man['words']} words in {len(sc['sections'])} sections by {info['model']} ({info['rounds']} fix rounds)")
    fp = WK.fonts(work)
    pics = select_pictures(fetch_pictures(sc, packs, day))
    total_pics = sum(len(v) for v in pics.values())
    if total_pics < 8:
        return done("skipped", reason=f"only {total_pics} usable pictures found (8 needed), the next run tries again")
    for v in pics.values():
        for p in v: p["focus"] = face_focus(p["path"]) if _aspect(p["path"]) >= 1.3 else None
    log(f"pictures: {total_pics}")
    beats = split_beats(sc["sections"])
    voice_dir, vman = run_tts(beats, work, voice=c.get("voice", "F2"), wps=float(c.get("wps", 2.9)))
    files = beat_files(vman, voice_dir, len(beats))
    durs = audio_durations(files)
    lay = layout(beats, durs)
    man.update(seconds=round(lay["total"]), unclear_beats=vman.get("unclear", []))
    if not 330 <= lay["total"] <= 660: man.setdefault("warnings", []).append(f"length {lay['total'] / 60:.1f} minutes, outside the 6 to 10 minute plan")
    narration = assemble_audio(files, lay["starts"], lay["total"], work / "narration.wav")
    music, music_line = pick_music(day, work)
    audio = mix_audio(narration, music, lay["total"], work / "audio.wav")
    cards = fact_cards(sc, packs, beats, durs, lay)
    imgs = {"chapter": {}, "subject": {}}
    for s in lay["sec"][1:]:
        k = s["index"]; sec = sc["sections"][k]
        imgs["chapter"][k] = WK.card(work / f"chapter{k}.png", sec["chapter"], (packs[[p["id"] for p in packs].index(sec["subject"])]["name"] if sec["subject"] else "Quickplay Daily"), fp, fit=True)
    for p in packs: imgs["subject"][p["id"]] = WK.card(work / f"subject{p['id']}.png", p["name"], "Quickplay Daily", fp, fit=True)
    imgs["subject"]["all"] = WK.card(work / "subjectall.png", "This week's stories", "Quickplay Daily", fp, [p["name"] for p in packs], fit=True)
    for i, cd in enumerate(cards): cd["path"] = card_image(work / f"fact{i}.png", cd["text"], cd["kicker"], cd["note"], fp)
    imgs["end"] = WK.card(work / "end.png", "New every Wednesday", "Subscribe to Quickplay Daily", fp, ["Shorts every day"], fit=True)
    segs = plan_visuals(lay, pics, cards, sc, packs, {"chapter": imgs["chapter"], "subject": imgs["subject"], "end": imgs["end"]})
    caps = [(lay["starts"][i], lay["starts"][i] + durs[i] + 0.15, b["text"]) for i, b in enumerate(beats)]
    use_captions = (c.get("captions", "small") != "off") if captions is None else captions
    render(segs, caps, lay["total"], audio, out / "video.mp4", fp, captions=use_captions)
    first = next((p["path"] for k in sorted(pics) for p in pics[k] if sc["sections"][k]["subject"] == packs[0]["id"]), None)
    make_thumbnail(out / "thumb.jpg", first, [p["name"] for p in packs], fp)
    chapters = [(s["start"], sc["sections"][s["index"]]["chapter"]) for s in lay["sec"]]
    flat = [p for k in sorted(pics) for p in pics[k]]
    man.update(chapters=[[stamp(t), n] for t, n in chapters], description=build_description(sc, packs, chapters, flat, music_line),
               tags=youtube_tags(sc, packs), pictures=total_pics, music=bool(music), voice=c.get("voice", "F2"), shorts=[s["id"] for p in packs for s in p["shorts"]])
    log(f"video: {man['seconds']} seconds, {man['words']} words, {len(segs)} shots")
    return done("built", reason="")


def _aspect(path):
    try:
        from PIL import Image
        with Image.open(path) as im: return im.width / im.height
    except Exception: return 1.0


# ---------------- upload ----------------
def save_status(day, st):
    p = status_path(day); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=1, ensure_ascii=False))


def upload(out, now=None):
    """Schedules out/video.mp4 for Wednesday 19:00 UK (public then) and records status/weekly-<Wednesday>.json. A build that was
    skipped or failed is recorded as it is; a dry build becomes a draft release (explainer-test) instead."""
    out = pathlib.Path(out)
    man = load_json(out / "explainer.json")
    if not man: log("nothing was built (no explainer.json): the build job did not finish"); return None
    now = now or now_utc()
    day = dt.date.fromisoformat(man["day"])
    st = load_json(status_path(day), {}) or {}
    if st.get("video") and not man.get("dry"): log("already scheduled:", st["video"]); return st
    if man["state"] != "built":
        if not man.get("dry"):
            st.update(kind="explainer", state=f"{man['state']}: {man.get('reason', '')}"[:300], at=now.isoformat(timespec="minutes"))
            save_status(day, st)
        log("not uploaded:", man["state"], man.get("reason", "")); return man
    video, desc = out / "video.mp4", man["description"]
    if man.get("dry"):
        repo = os.environ.get("GITHUB_REPOSITORY", "quickplay-studio/quickplay-autopilot")
        subprocess.run(["gh", "release", "delete", "explainer-test", "-y", "--cleanup-tag", "-R", repo], capture_output=True)
        sh("gh", "release", "create", "explainer-test", video, out / "thumb.jpg", "--draft", "--title", "explainer-test", "--notes", f"{man['title']}\n\n{desc}"[:20000], "-R", repo)
        return man
    import youtube as Y, quota
    if not Y.available(): raise SystemExit("YouTube secrets missing")
    base = dict(kind="explainer", title=man["title"], subjects=[s["name"] for s in man.get("subjects", [])], shorts=man.get("shorts", []),
                chapters=man.get("chapters", []), seconds=man.get("seconds"), words=man.get("words"), model=man.get("model"),
                fact_check=man.get("fact_check"), pictures=man.get("pictures"), at=now.isoformat(timespec="minutes"))
    if not quota.allow(quota.COST["upload"], "explainer upload"):
        st.update(base, state="waiting: YouTube allowance"); save_status(day, st); log("the YouTube allowance has no room now"); return st
    yt = Y.client()
    pub = publish_time(day, now)
    try:
        vid = Y.upload(yt, video, man["title"], desc, man["tags"], "Entertainment", pub.isoformat().replace("+00:00", "Z"))
    except Y.LimitReached as e:
        st.update(base, state="waiting: upload limit", error=str(e)[:200]); save_status(day, st); log("upload limit reached, will retry"); return st
    st.update(base, state="scheduled", video=vid, publish_at=pub.isoformat(timespec="minutes"), url=f"https://youtu.be/{vid}")
    st.pop("error", None)
    try: st["youtube"] = Y.video_status(yt, vid)
    except Exception as e: st["youtube_error"] = f"{type(e).__name__}: {e}"[:160]
    try:                                    # a custom thumbnail needs a verified channel; fine if refused
        from googleapiclient.http import MediaFileUpload
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(out / "thumb.jpg"))).execute()
    except Exception as e: st["thumbnail_error"] = f"{type(e).__name__}: {e}"[:200]
    save_status(day, st)
    log(json.dumps(st, indent=1))
    return st


# ---------------- the long videos and the Shorts ----------------
def long_videos(root=None):
    """{youtube id: {"id", "kind", "title", "publish_at", "day"}} for every status/weekly-*.json with a video: the Sunday
    compilation (weekly.py) and the Wednesday explainer."""
    root = pathlib.Path(root) if root else ROOT
    out = {}
    for p in sorted((root / "status").glob("weekly-*.json")):
        st = load_json(p, {})
        if not (isinstance(st, dict) and st.get("video")): continue
        try: at = dt.datetime.fromisoformat(str(st.get("publish_at")).replace("Z", "+00:00"))
        except ValueError: at = None
        if at is not None and at.tzinfo is None: at = at.replace(tzinfo=dt.timezone.utc)
        out[st["video"]] = {"id": st["video"], "kind": st.get("kind") or "compilation", "title": str(st.get("title") or "").strip(),
                            "publish_at": at, "day": p.stem.removeprefix("weekly-")}
    return out


def latest_long(at=None, root=None):
    """The newest long video that is public at `at` (default now), or None."""
    at = at or now_utc()
    live = [v for v in long_videos(root).values() if v["publish_at"] and v["publish_at"] <= at]
    return max(live, key=lambda v: v["publish_at"]) if live else None


def link_lines(at=None, root=None):
    """The line a Short's description carries near the top: the latest long video that is public when the Short is. [] when none."""
    v = latest_long(at, root)
    if not v: return []
    return [f"Watch the weekly video: {v['title']} https://youtu.be/{v['id']}" if v["title"] else f"Watch the weekly video: https://youtu.be/{v['id']}"]


def comment_text(comment, at=None, root=None):
    """The creator comment on a new Short (500 characters at most) with one line pointing to the latest long video."""
    base, v = str(comment or "").strip(), latest_long(at, root)
    if not v: return base[:500]
    line = f"The full story, in the weekly video: https://youtu.be/{v['id']}"
    return (base[:500 - len(line) - 2].rstrip() + "\n\n" + line) if base else line


def watch_report(query, today, out_dir=None, root=None, now=None):
    """Long-video watch time from YouTube Analytics. query(metrics, since=None, **kw) is analytics.youtube's own. Returns {"hours_365d",
    "rows", "source", "errors"}: the last 365 days' watch hours of long videos and live streams (what the Partner Programme
    counts), from the first of these that YouTube answers: the creatorContentType dimension, the filter the first version used,
    the sum over our long videos. rows are each long video's days since it went public (analytics/longform.csv, written when
    there is any). The old filter query evidently fails (the cached figure was null), hence the others."""
    vids, res = long_videos(root), {"hours_365d": None, "rows": [], "source": "", "errors": []}
    since = str(today - dt.timedelta(days=365))
    mins = lambda rows: sum(float(r.get("estimatedMinutesWatched") or 0) for r in rows)
    for name, run in (("creatorContentType", lambda: sum(float(r.get("estimatedMinutesWatched") or 0) for r in query(
                          "estimatedMinutesWatched", since=since, dimensions="creatorContentType")
                          if r.get("creatorContentType") in ("VIDEO_ON_DEMAND", "LIVE_STREAM"))),
                      ("filter", lambda: mins(query("estimatedMinutesWatched", since=since, filters="creatorContentType==VIDEO_ON_DEMAND"))),
                      ("our videos", lambda: mins(query("estimatedMinutesWatched", since=since, dimensions="video",
                                                        filters="video==" + ",".join(list(vids)[:400]), sort="-estimatedMinutesWatched",
                                                        maxResults=200)) if vids else None)):
        try: m = run()
        except Exception as e:
            res["errors"].append(f"{name}: {type(e).__name__}: {str(e)[:100]}"); continue
        if m is not None: res["hours_365d"], res["source"] = round(m / 60, 1), name; break
    now, answered = now or now_utc(), False
    for vid, v in vids.items():
        if not v["publish_at"] or v["publish_at"] > now: continue
        start = max(today - dt.timedelta(days=120), v["publish_at"].date())
        try:
            rows = query("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained",
                         since=str(start), dimensions="day", filters=f"video=={vid}", sort="day")
        except Exception as e:
            res["errors"].append(f"{vid}: {type(e).__name__}: {str(e)[:100]}"); continue
        answered = True
        for r in rows:
            m = float(r.get("estimatedMinutesWatched") or 0)
            res["rows"].append({"date": r.get("day", ""), "video": vid, "kind": v["kind"], "title": v["title"], "views": r.get("views", 0),
                                "watch_minutes": round(m, 1), "watch_hours": round(m / 60, 3), "avg_view_seconds": r.get("averageViewDuration", ""),
                                "avg_view_pct": round(float(r["averageViewPercentage"]), 1) if r.get("averageViewPercentage") not in (None, "") else "",
                                "subs_gained": r.get("subscribersGained", 0)})
    if res["hours_365d"] is None and answered: res["hours_365d"], res["source"] = round(sum(r["watch_minutes"] for r in res["rows"]) / 60, 1), "our videos (120 days)"
    if answered:
        p = pathlib.Path(out_dir) if out_dir else ROOT / "analytics"
        p.mkdir(parents=True, exist_ok=True)
        with open(p / "longform.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LONGFORM_FIELDS, extrasaction="ignore"); w.writeheader()
            for r in sorted(res["rows"], key=lambda r: (str(r["date"]), r["video"])): w.writerow(r)
    if res["errors"]: log("long-form watch hours:", "; ".join(res["errors"])[:300])
    return res


# ---------------- command line ----------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["due", "build", "upload", "run", "script"])
    ap.add_argument("--out", default="explainer-out")
    ap.add_argument("--dry", action="store_true", help="a test build: nothing is uploaded, the video becomes a draft release")
    ap.add_argument("--script", default="", help="a script JSON to use instead of the model chain")
    ap.add_argument("--captions", choices=["small", "off"], default="")
    a = ap.parse_args(argv)
    if a.cmd == "due":
        req = ""
        try: req = (ROOT / "requests" / "weekly-explainer.txt").read_text()
        except OSError: pass
        go, mode, why = due(event=os.environ.get("EVENT", ""), request=req)
        print(f"go={'yes' if go else 'no'}\nmode={mode}\nwhy={why}")
        return 0
    if a.cmd == "script":
        now = now_utc()
        subjects = pick_subjects(shorts_rows(), board_of, now, n=3)
        packs = build_packs(subjects, board_of, (load_json(ROOT / "trends" / "facts.json", {}) or {}).get("topics") or [])
        sc, info = write_script(packs, day=target_day(now.astimezone(UK).date()))
        print(json.dumps({"script": ensure_pictures(sc, packs), "info": info}, indent=1, ensure_ascii=False))
        return 0
    if a.cmd in ("build", "run"):
        man = build(a.out, dry=a.dry, script_file=a.script, captions=None if not a.captions else a.captions != "off")
        if a.cmd == "build": return 0
    upload(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
