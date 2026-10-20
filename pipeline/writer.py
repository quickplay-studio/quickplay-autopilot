"""The script writer, on GitHub with Google's Gemini, so no Claude run is needed (Charlie, 19 October).

usage: python pipeline/writer.py            (write.yml runs it after each trends run; WRITE_COUNT and WRITE_DRY optional)

For the run's capacity (config runs: morning before 09:00 UTC and afternoon write for today, evening for tomorrow, never
past daily_limit), it takes the day's fact packs (trends/facts.json) in their best-first order, skips topics covered in
the last 14 days and anything Gemini would flag, and has Gemini write a board from the pack alone, shaped like a good
past board. pipeline/validate.py checks it; Gemini fixes what fails (twice at most); a board that still fails is dropped.
Boards go to boards/queue for render.yml.
"""
import csv, datetime as dt, json, math, os, pathlib, random, re, sys, urllib.parse, time
import requests
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import background as BG, factpack, validate

CFG = json.loads((ROOT / "config.json").read_text())
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
CATS = ["Gaming", "Film", "Music", "Sport", "Tech", "Science", "Entertainment"]

RULES = """You write one YouTube Short script ("board") as JSON for Quickplay Daily: an anonymous, family-friendly UK channel about
gaming, film and TV, music, sport, celebrities, streamers and creators, tech launches and space. Every rule must hold.
- UK English and UK style: "Tuesday 20 October", "20 million pounds", colour, favourite. Never use an en dash or an em dash
  anywhere (use commas, colons or full stops).
- Never politics, crime, health claims, money or investing advice, adult content or gambling. Explore the subject itself;
  never talk about views, virality or why something went viral.
- Facts: use ONLY the facts in the pack below. A "verified" fact can be stated plainly. A "one source" fact must name its
  source in the narration ("Variety says", "according to the BBC"). Anything unconfirmed must be said to be unconfirmed and
  who is saying it. Never invent anything. Copy names, numbers and dates exactly as the pack writes them.
- Beat 1 (the hook): the most surprising true detail in 12 words or fewer, never "X is back" or a slow intro. Put
  "impact": true on the hook and on the payoff beat.
- 5 to 9 beats, 70 to 110 words of narration in total, one or two sentences per beat.
- Ending: land the payoff, then either a line that loops back into the hook or a short question viewers can answer.
- Neat and minimal: at most 3 beats with a graphic ("visual" not {"type": "none"}), few words on each graphic.
- Real footage first: at least 4 in 5 shots show the actual subject, and beat 1's shots always do. In order: the pack's
  real pictures, "commons-search:Full Name" for each person (add "label": {"t": "Full Name", "s": "who they are"} the
  first time each person appears), "nasa:video:words" or "nasa:image:words" for space, "page:https://..." for an official
  page's own picture (a studio, publisher, label, team or agency; never a news site). Stock ("pixabay:video:2 to 4
  concrete words") only when nothing real exists, at most 1 in 5 shots, never on beat 1.
- Shots: 1 to 3 per beat, a new shot every 2 to 3 seconds (about every 6 to 8 words): later shots in a beat take "at"
  (the word number the cut lands on); "move" is one of in, out, left, right, up, down, still.
- "background": 3 stock video searches (2 to 4 are allowed), each 2 to 4 concrete lower case words, for the clips that play
  softly blurred and darkened behind the whole Short, one after another. Describe the WORLD of the story as a camera would
  film it: "football stadium night", "concert stage lights", "neon gaming setup", "cinema auditorium screen", "galaxy stars
  nebula", "server room lights". Never a person's name, a team, a brand, a game or film title, or an event. For a space story
  start one with "nasa:" ("nasa:earth from orbit") to use NASA's own footage. They are not shots: they never count towards
  the 1 in 5 stock limit and are never mentioned in the narration.
- Graphics: {"type": "none"} or one of: title {kicker, lines[], highlight[indexes]}, stat {value, label, sub},
  cards {items[{icon, t, s}]}, quote {text, by}, date {month, day, weekday, label, sub},
  versus {items: [2 x {label, value, sub}]}, timeline {items[{y, t}]}, bars {items[{label, value, w 0 to 1}]}.
  Icons are lucide icon names.
- meta.title: under 50 characters, the searchable name first (person, game, film, team), then the curiosity, exactly one
  emoji at the end, never promising what the Short doesn't deliver (a question title for anything unconfirmed).
  meta.alt_title: a second title with a different angle, same rules. meta.summary: one or two sentences.
- meta.hashtags: 8 to 15, exact names first, then the franchise or show, the category, then one or two broad ones such as
  #Trending or #Gaming; never #viral or anything unrelated. meta.tags: 5 to 15 phrases people would search.
  meta.comment: one question viewers can answer, under 100 characters, no links.
- meta.sources: the pack's sources as [title, url] in the same order. meta.facts: every claim you used as
  [claim, [source numbers from the pack]].
- "format": one of the format ids below. "category": one of Gaming, Film, Music, Sport, Tech, Science, Entertainment.
  "music": {"mood": one of %(moods)s}.
- Lead with what is new today (the pack's "What is new"). If the pack has nothing new from the last few days, return
  {"skip": "nothing new"}.
- Say only what the facts say. Never add details, motives, quotes or loaded words ("clashed", "slammed", "macho") the
  pack doesn't state, and never name Wikipedia in the narration.
- Pictures: each page: address gives one picture, so use it at most twice. At least half the beats need a
  "commons-search:" shot (a person, team, venue or event), because page: pictures often can't be fetched.
- If a person under 18 is at the centre of the story, or it comes close to the banned subjects, return {"skip": "why"}.
Return only the JSON board, shaped exactly like the example (leave out "id" and "created")."""


def board(f):
    try: return json.loads(f.read_text())
    except Exception: return {}


def about(b):
    """What a board covered: its title, its title with tags and hashtags, and its source pages."""
    m = b.get("meta") or {}
    title = str(m.get("title", ""))
    text = " ".join([title] + [str(t) for t in (m.get("tags") or []) + (m.get("hashtags") or [])])
    return title, text, {s[1] for s in m.get("sources") or [] if isinstance(s, list) and len(s) > 1}


def recent(days=14):
    """What the last 14 days of boards covered (queue, ready, done, reserve and failed)."""
    cut, out = str((NOW - dt.timedelta(days=days)).date()), []
    for d in ("queue", "ready", "done", "reserve", "failed"):
        for f in (ROOT / "boards" / d).glob("QD-*.json"):
            b = board(f)
            if str(b.get("created", "")) >= cut: out.append(about(b))
    return out


def covered(p, seen):
    """Covered: a recent board cites one of the pack's articles (Wikipedia pages don't count: many stories share one), or
    its title shares two of the topic's longer words."""
    words = {w for w in re.findall(r"[a-z0-9]+", p["topic"].lower()) if len(w) > 3}
    urls = {s[1] for s in p.get("sources") or [] if len(s) > 1 and "wikipedia.org" not in str(s[1])}
    for title, _, srcs in seen:
        if urls & srcs: return True
        if words and len(words & set(re.findall(r"[a-z0-9]+", title.lower()))) >= min(2, len(words)): return True
    return False


def day_formats(day):
    """The target day's formats so far, oldest first (at least 3 a day, never the same twice in a row)."""
    got = []
    for d in ("queue", "ready", "done"):
        for p in (ROOT / "boards" / d).glob("QD-*.json"):
            try: b = json.loads(p.read_text())
            except Exception: continue
            if b.get("created") == str(day) and b.get("format"): got.append((b["id"], b["format"]))
    return [f for _, f in sorted(got)]


def next_id():
    used = set()
    for p in list((ROOT / "boards").glob("*/QD-*.json")) + list((ROOT / "status").glob("QD-*.json")):
        m = re.fullmatch(r"QD-(\d+)", p.stem)
        if m: used.add(int(m.group(1)))
    n = max([int(CFG.get("first_id", 1)) - 1] + list(used)) + 1
    return n


def plan(breaking=False, hint=""):
    """Target day and how many to write. The run is WRITE_RUN (a request line such as "afternoon 8"), else the trends
    schedule that built the packs (facts.json "run"), else the clock (UTC); a breaking-news check writes today, at most a
    few. A day runs from slot_first to slot_first (its slots cover 24 hours), so a run after midnight UK still fills
    tonight; the evening run writes the day that starts next morning."""
    uk = NOW.astimezone(UK)
    hint = os.environ.get("WRITE_RUN", "").strip().lower() or hint
    run = "breaking" if breaking else hint if hint in ("morning", "afternoon", "evening") else \
        "morning" if NOW.hour < 11 else "afternoon" if NOW.hour < 17 else "evening"
    h, m = map(int, str(CFG.get("slot_first", "07:30")).split(":"))
    base = (uk - dt.timedelta(hours=h, minutes=m)).date()      # a posting day runs from slot_first to slot_first (all 24 hours)
    day = base + dt.timedelta(days=1 if run == "evening" else 0)
    made = 0
    for d in ("queue", "ready", "done", "failed"):
        for p in (ROOT / "boards" / d).glob("QD-*.json"):
            try: b = json.loads(p.read_text())
            except Exception: continue
            if b.get("created") == str(day) and not b.get("reserve"): made += 1
    import quota
    limit = quota.daily_limit() - (1 if day.weekday() == 6 else 0)
    runs = {k: int(v) for k, v in (CFG.get("runs") or {}).items() if str(v).isdigit()}
    per_run = share("breaking", 2, 4) if breaking else max(1, -(-runs.get(run, 6) * quota.daily_limit() // max(1, sum(runs.values()))))
    if run == "afternoon": per_run = min(max(30, limit * 3 // 4), max(per_run, limit - made))     # the day's last run makes up anything the morning missed
    cap = min(per_run, max(0, limit - made))
    if os.environ.get("WRITE_COUNT", "").strip().isdigit(): cap = int(os.environ["WRITE_COUNT"])
    return run, day, cap


def example():
    """The newest finished board closest to the rules (fewest validator warnings, least stock), as the shape to copy."""
    best, free = None, f"QD-{next_id():03d}"
    done = sorted((ROOT / "boards" / "done").glob("QD-*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0), reverse=True)
    for p in done[:20]:
        try: b = json.loads(p.read_text())
        except Exception: continue
        for k in ("id", "created", "tiktok", "look", "flag", "bgvideo"): b.pop(k, None)
        if b.get("mode") or b.get("reserve"): continue
        if not b.get("background"): b["background"] = BG.fallback(b)[:3]       # older boards predate the field: show its shape
        errs, warns = validate.check({"id": free, "created": str(NOW.date()), **b})
        stock = sum(str(s.get("src", "")).startswith("pixabay:") for bt in b.get("beats", []) for s in bt.get("shots") or [])
        if best is None or (len(errs), len(warns), stock) < best[0]: best = ((len(errs), len(warns), stock), b)
    return json.dumps(best[1], ensure_ascii=False, separators=(",", ":")) if best else "{}"


def formats():
    f = json.loads((ROOT / "templates" / "formats.json").read_text())
    out = []
    for x in f.get("formats", []):
        if x.get("retired"): continue
        roles = " > ".join(b.get("role", "") for b in x.get("beats", []))
        out.append(f"- {x['id']}: {x.get('name', '')}. Use when: {x.get('use_when', '')} Beats: {roles}")
    return "\n".join(out)


def recipe():
    p = ROOT / "analytics" / "insights.md"
    if not p.exists(): return ""
    s = p.read_text()
    m = re.search(r"## Recipe.*?(?=\n## )", s, re.S)
    return (m.group(0) if m else "")[:900]


def pack_text(p):
    lines = [f"TOPIC: {p['topic']} (trend signal: {p.get('signal', '')}; category hint: {p.get('category', '')})"]
    if p.get("what_is_new"): lines.append(f"What is new: {p['what_is_new']}")
    lines.append("Sources (number: outlet, title, date, url):")
    for k, s in enumerate(p["sources"], 1): lines.append(f"  {k}: {s[2]}, {s[0]}, {s[3]}, {s[1]}")
    lines.append("Verified facts (two sources):")
    for f in p["verified"]: lines.append(f"  - {f['claim']} {f['sources']}")
    if p.get("one_source"):
        lines.append("One source facts (name the source if used):")
        for f in p["one_source"]: lines.append(f"  - {f['claim']} {f['sources']}")
    if p.get("images"): lines.append("Real pictures to use as shots: " + ", ".join(p["images"]))
    if p.get("hooks"): lines.append("Hook ideas: " + " | ".join(p["hooks"]))
    return "\n".join(lines)


def clean(x):
    """No en or em dashes anywhere in what the writer returns."""
    if isinstance(x, str): return factpack.undash(x) if re.search("[–—]", x) else x
    if isinstance(x, list): return [clean(v) for v in x]
    if isinstance(x, dict): return {k: clean(v) for k, v in x.items()}
    return x


CHECK = """You check a YouTube Short script against its fact pack before it is published. Report a problem only when the
title or a beat states something WRONG:
- a specific fact the pack doesn't support or that contradicts it: a number, date, name, place, event, record, ranking,
  result or quote (rounding that keeps the meaning is fine, such as "more than 140 million" said as "140 million");
- something negative or loaded about a real person that the pack doesn't support (such as "clashed" or "furious"), or
  anything about crime, illness, relationships or deaths that isn't in the pack;
- a rumour, leak or report presented as confirmed when the pack says it isn't.
Never report enthusiastic or descriptive words (incredible, talented, iconic, huge), the hook's framing, questions, a fair
paraphrase, or details left out. Return {"ok": true} when nothing is wrong, otherwise {"ok": false, "problems": [{"beat":
<number from 1, or 0 for the title>, "issue": "<what is wrong, and what the pack says>"}]}."""


def fact_check(b, p):
    """Gemini reads the title and narration against the pack: the problems it finds (none when all is supported)."""
    beats = "\n".join(f"{k}. {x.get('say', '')}" for k, x in enumerate(b.get("beats") or [], 1))
    ans, _ = factpack.gemini(CHECK + "\n\nTHE PACK\n" + pack_text(p) + f"\n\nTHE SCRIPT\n0. {(b.get('meta') or {}).get('title', '')}\n"
                             + beats, None, timeout=100, temperature=0.0, lite=True)
    if not isinstance(ans, dict) or ans.get("ok") is not False: return []
    return [f"beat {x.get('beat')}: {x.get('issue')}" for x in ans.get("problems") or [] if isinstance(x, dict)][:6]


def media_problems(b):
    """page: pictures are often refused, so at least half the beats need a shot that reliably resolves."""
    beats = b.get("beats") or []
    sure = sum(any(str(s.get("src", "")).startswith(("commons", "nasa:", "openverse:")) for s in x.get("shots") or []) for x in beats)
    if sure * 2 >= len(beats): return []
    return [f"media: only {sure} of {len(beats)} beats have a commons-search:, commons:, openverse: or nasa: shot; add "
            "commons-search shots of the people, teams, venues or events to at least half the beats (page: pictures often fail)"]


def boosts(feature="category"):
    """How far the data moves a pack up (or down) the list for one feature (its category, or where the topic came from,
    analytics/drivers.csv): "push" 2 places up, an early sign 1; below typical the same way down ("cut back" 2)."""
    p, out = ROOT / "analytics" / "drivers.csv", {}
    if not p.exists(): return out
    for r in csv.DictReader(p.open()):
        if r.get("feature") != feature: continue
        try: lift = float(r.get("lift") or 0)
        except ValueError: continue
        v = r.get("verdict")
        if v == "push" and lift > 1: out[r.get("value")] = 2
        elif v == "cut back": out[r.get("value")] = -2
        elif v == "early sign": out[r.get("value")] = 1 if lift > 1.15 else -1 if lift < 0.85 else 0
    return out


def source_of(signal):
    """Where a topic came from, from its pack's trend signal, so the data can learn which sources find winners."""
    s = str(signal or "").lower()
    for key, name in (("request", "Requests"), ("trending:", "Trend-tied"), ("follow-up", "Follow-up"), ("evergreen", "Evergreen"), ("music", "YouTube music"), ("youtube", "YouTube"),
                      ("wikipedia", "Wikipedia"), ("google trends", "Google Trends"), ("launch", "Rocket launches"),
                      ("rocket", "Rocket launches"), ("football", "Football"), ("fixture", "Football"), ("apple", "Apple Music"),
                      ("chart", "Apple Music"), ("news", "News")):
        if key in s: return name
    return "Other"


def hot():
    """Our Shorts at 3x or more the usual views for their age in their first 3 days (analytics/breakouts.csv), strongest
    first, with no follow-up yet: a fresh pack on the same subject is written first, as a follow-up."""
    p = ROOT / "analytics" / "breakouts.csv"
    if not p.exists(): return []
    done = {board(f).get("follows") for f in (ROOT / "boards").glob("*/QD-*.json")}
    rows = []
    times = float(CFG.get("breakout_times", 2))
    for r in csv.DictReader(p.open()):
        try: x, h = float(r.get("times_typical") or 0), float(r.get("hours_public") or 999)
        except ValueError: continue
        if x < times or h > 72 or r.get("short") in done: continue
        f = next((ROOT / "boards").glob(f"*/{r.get('short')}.json"), None)
        r["_about"] = about(board(f)) if f else (r.get("title", ""), r.get("title", ""), set())
        r["_board"] = f
        rows.append((x, r))
    return [r for _, r in sorted(rows, key=lambda t: -t[0])]


def weak():
    """Our Shorts that scored under half of typical after 48 hours (analytics/shorts.csv) with no remake yet, weakest first.
    Deleting a weak Short gives no upload back and loses its slow search views, so it stays up; a remake on the same
    subject, while it still trends, is the second try (one a day)."""
    p = ROOT / "analytics" / "shorts.csv"
    if not p.exists(): return []
    done = {board(f).get("remakes") for f in (ROOT / "boards").glob("*/QD-*.json")}
    rows = []
    for r in csv.DictReader(p.open()):
        try:
            x = float(r.get("views_vs_typical") or "")
            age = (NOW - dt.datetime.fromisoformat(r["posted"])).total_seconds() / 3600 if r.get("posted") else 0
        except ValueError: continue
        if x >= 0.5 or age < 48 or age > 14 * 24 or r.get("short") in done or not r.get("short"): continue
        f = next((ROOT / "boards").glob(f"*/{r['short']}.json"), None)
        r["_about"] = about(board(f)) if f else (r.get("title", ""), r.get("title", ""), set())
        rows.append((x, r))
    return [r for _, r in sorted(rows, key=lambda t: t[0])]


REMAKE_NOTE = ("REMAKE: our Short \"{title}\" on this subject got under half our usual views. Write a second try on the same "
               "subject from this pack: a different angle, a different hook and a different title (never a repeat of that "
               "title's wording), opening on the most surprising fact the first Short didn't lead with.")

def followup_pack(r, seen):
    """A pack for a follow-up when no fresh pack covers the breakout's subject: the next chapter from the original Short's
    own pages (its sources, Wikipedia first), checked word for word like an evergreen pack."""
    b = board(r["_board"]) if r.get("_board") else {}
    m = b.get("meta") or {}
    urls = [u for _, u in [x[:2] for x in m.get("sources") or [] if isinstance(x, list) and len(x) > 1]]
    urls = sorted(dict.fromkeys(urls), key=lambda u: "wikipedia.org" not in u)[:2]
    q = f"More about {m.get('title', r.get('title', ''))}: the next chapter, the detail viewers ask about, or the history behind it"
    facts, srcs, texts, img = [], [], {}, ""
    for u in urls:
        try:
            txt, im = factpack.page_text(u, wiki="wikipedia.org" in u)
            if len(txt) < 800: continue
            got, _ = factpack.gemini(EVERGREEN_FACTS.format(q=q, how=HOW["evergreen"], title=m.get("title", ""), url=u, text=txt),
                                     factpack.SCHEMA, timeout=100, lite=True)
        except Exception as e:
            print("follow-up pack:", u, str(e)[:120]); continue
        n = len(srcs) + 1
        _, single = factpack.verify((got or {}).get("facts"), {1: factpack.norm(txt)}, {1: "wikipedia" if "wikipedia.org" in u else "article"})
        for f in single: f["sources"] = [n]
        facts += single; srcs.append([m.get("title", ""), u, "Wikipedia" if "wikipedia.org" in u else "", ""]); img = img or im
        if not img and im: img = im
        if len(facts) >= 6: break
    if len(facts) < 3: return None
    return {"topic": str(m.get("title", r.get("title", ""))), "kind": "news", "signal": f"follow-up of {r.get('short')} ({r.get('times_typical')}x)",
            "category": b.get("category") or r.get("category", ""), "what_is_new": "", "hooks": [], "sources": srcs,
            "verified": [], "one_source": facts, "images": [f"commons:File:{img.rsplit('/', 1)[-1]}"] if img and "commons" in img else []}


EVERGREEN_PLAN = """You plan evergreen YouTube Shorts for Quickplay Daily (family-friendly, UK English): things people search for
and watch all year, not news, in these categories (strongest first): {cats}. Suggest {n} ideas, best first: {kinds}.
- "question": a question people type into YouTube (Why, How, What, Who or Which, or the first or the biggest).
- "top list": a top 10 (or top 5) ranking people search for ("Top 10 best-selling video games"), from a Wikipedia list
  article that ranks them with figures.
- "true story": a remarkable true story (an unlikely record, a famous mix-up, a comeback, a mystery solved), told from one
  Wikipedia article about the event or the person.
Each is about something famous (a game, film, show, song, artist, band, team, player, record or space mission) and comes
from one English Wikipedia article. Never politics, crime, health, money, adult themes, deaths or a person under 18.
{trending}Nothing on these recent Shorts: {recent}.
Return {{"items": [{{"kind": "question, top list or true story", "idea": "the question, list or story in a few words",
"category": "Gaming, Film, Music, Sport, Tech, Science or Entertainment", "wikipedia": "the exact article title",
"trending": "the trending subject it rides, or empty"}}]}}"""
SEARCH_ASK = ("Searches that already bring us viewers (people type these into YouTube; plan more Shorts those searches would "
              "find, on the next question or the next entry of the same subject): {terms}. ")
TRENDING_ASK = ("Subjects trending today: {subjects}. Make about {n} of the ideas ride these subjects (people are searching them "
                "now): a top 10 ranking from a Wikipedia list about the subject, its series, franchise, team, artist or sport "
                "(\"Top 10 best-selling Zelda games\", \"Top 10 highest-grossing video game films\"), or a remarkable true "
                "story from its history; the rest on anything famous. ")

EVERGREEN_FACTS = """You check facts for a family-friendly Shorts channel. The Short is about: "{q}". Below is one
encyclopedia article. Using ONLY this article, {how} For each fact:
- "claim": one plain sentence in UK English. Copy names, numbers and dates exactly as the article writes them. No dashes.
- "evidence": [{{"source": 1, "quote": the exact text from the article that states it, copied character for
  character, at most 40 words}}].
Leave out opinions, rumours, and anything about politics, crime, health or money advice.
"what_is_new": "". "hooks": up to 3 openings of 12 words or fewer, each built only on facts above.

[1] Wikipedia · {title} · {url}
{text}"""

HOW = {"evergreen": "list up to 10 facts that answer the question or make the answer more surprising: names, dates, "
                    "numbers, records, firsts.",
       "top list": "list the ranked entries from the top down (number 1 first, up to number 10), one fact each with its "
                   "rank, name and figure, as the article gives them.",
       "true story": "list up to 12 facts that tell the story in order: who, where and when, what happened, the turn, and "
                     "how it ended."}
MIN_FACTS = {"evergreen": 3, "top list": 5, "true story": 5}

EVERGREEN_NOTE = ("EVERGREEN: this Short answers the question in the topic for people searching it at any time of year. It "
                  "is not news: ignore the rule about what is new, and never say today, this week or recently. Title it as "
                  "the question people type, with the searchable name early. Its facts come from one encyclopedia article: "
                  "state them plainly and never name the source.")
COUNTDOWN_NOTE = ("COUNTDOWN: count down the ranked list in the pack, from the lowest entry it gives (number 10, or as many as "
                  "there are) to number 1, one or two entries a beat, each with its figure; tease number 1 in the hook without "
                  "naming it and save it for the last beat. Use the \"countdown\" format and at most one bars graphic, for the "
                  "top three. Title it as people search the list (\"Top 10 best-selling games ever\"). Its facts come from one "
                  "encyclopedia article: state them plainly and never name the source.")
STORY_NOTE = ("TRUE STORY: tell it in order like a storyteller: a gripping first line, the set-up, what happened, the turn and "
              "how it ended. Use the \"story\" format. Real photos of the people and places in every beat (commons-search with "
              "full names), never stock for people. Title it as the story (\"The day ...\", \"How ...\"). Its facts come from one "
              "encyclopedia article: state them plainly and never name the source.")
FICTION_NOTE = ("FICTION: this Short is an ORIGINAL short story (the topic is its premise), not news and not about real people, so "
                "the facts rule and the real pictures rule don't apply. Tell it in the \"story\" format with a twist ending, 90 to "
                "120 words, family-friendly. The title says it is a story (\"... | a short story\" before the emoji) and the "
                "summary starts \"An original short story.\" Every beat's shots are game footage: write each src as \"gameplay:\" plus 2 to 4 words of "
                "satisfying, game-like motion (our own gameplay recordings play when we have them, otherwise stock video of those "
                "words), the same kind all the way through (\"gameplay:parkour rooftop run\", \"gameplay:racing track onboard\", "
                "\"gameplay:marble run\", \"gameplay:skateboard street ride\"), and \"background\" searches the same kind in plain "
                "words (no prefix). "
                "Copy meta.sources and meta.facts from the pack exactly.")
FICTION_PLAN = """You write premises for original, family-friendly short stories told in 30 seconds on YouTube Shorts:
gripping, a little eerie or funny, with a twist ending, set in worlds our viewers love (games, films, music, sport, space,
the internet). No real people, brands or crimes, nothing too scary for children. Not like these recent ones: {recent}.
Return {{"premise": "one sentence", "category": "Gaming, Film, Music, Sport, Tech, Science or Entertainment"}}"""
PART_FIRST = ("SERIES: this is Part 1 of {of}. Cover the first part only (for a countdown, the lowest entries of the list; for "
              "a story, up to the first turning point; for news, what happened first) and end on a cliffhanger line that makes "
              "viewers want Part 2, such as \"Number 1 is in Part 2\" or \"What happened next is in Part 2\". End the title "
              "with \"(Part 1)\" before the emoji.")
PART_MID = ("SERIES: this is Part {n} of {of}, following our Short \"{title}\", whose narration was: {said} Open with a five-word "
            "recap that makes sense on its own, carry on (the middle of the list, or what happened next) without repeating "
            "earlier parts, and end on a cliffhanger for Part {next}. End the title with \"(Part {n})\" before the emoji.")
PART_LAST = ("SERIES: this is Part {n} of {of}, following our Short \"{title}\", whose narration was: {said} Open with a five-word "
             "recap that makes sense on its own, then finish it (the top of the list, or what happened next) and land the "
             "payoff. Don't repeat the earlier parts. End the title with \"(Part {n})\" before the emoji.")
PART1_NOTE, PART2_NOTE = PART_FIRST.format(of=2), PART_LAST.replace("{n}", "2").replace("{of}", "2")     # kept for tests


def part_note(n, of, title="", said=""):
    if n == 1: return PART_FIRST.format(of=of)
    t = PART_LAST if n == of else PART_MID
    return t.replace("{n}", str(n)).replace("{of}", str(of)).replace("{next}", str(n + 1)).replace("{title}", title).replace("{said}", said)


KIND_NOTE = {"evergreen": EVERGREEN_NOTE, "top list": COUNTDOWN_NOTE, "true story": STORY_NOTE, "fiction": FICTION_NOTE}


def reserve_count():
    """Evergreen Shorts waiting in the reserve, or on their way there."""
    return len(list((ROOT / "boards" / "reserve").glob("QD-*.json"))) + sum(
        1 for f in (ROOT / "boards" / "queue").glob("QD-*.json") if board(f).get("reserve"))


def pick_kinds(n):
    """Which evergreen kinds to write: questions, top lists and true stories, each in proportion to how its Shorts do
    against typical (equal until the data can tell)."""
    w = {k: min(2.0, max(0.5, lift_of("kind", k) or 1.0)) for k in ("evergreen", "top list", "true story")}
    pool = [k for k, x in w.items() for _ in range(round(4 * x))]
    random.Random(f"{NOW.date()}:{n}").shuffle(pool)
    return pool[:n]


def search_terms(n=15):
    """What people typed into YouTube search to find our Shorts (analytics/search_terms.csv), most views first."""
    p = ROOT / "analytics" / "search_terms.csv"
    if not p.exists(): return []
    try: rows = sorted(csv.DictReader(p.open()), key=lambda r: -float(r.get("views") or 0))
    except Exception: return []
    return [r["term"].strip()[:50] for r in rows if r.get("term", "").strip()][:n]


def trend_share():
    """What share of the evergreen ideas ride the day's trending subjects: half until the data can tell (drivers.csv,
    source "Trend-tied" against "Evergreen"), then between a quarter and three quarters."""
    lift = lift_of("source", "Trend-tied")
    return 0.5 if lift is None else min(0.75, max(0.25, 0.5 * lift))


def evergreen_packs(kinds, seen, trending=()):
    """Fact packs for evergreen Shorts of the given kinds in the best categories, each from one Wikipedia article whose
    quotes are checked word for word (factpack.verify), like the news packs. `trending`: the day's trending subjects
    (topic names): a share of the ideas (trend_share) are top 10s and true stories that ride them."""
    up = boosts()
    cats = sorted(CATS, key=lambda c: -up.get(c, 0))
    recent = "; ".join(t for t, _, _ in seen[-60:])[:1500]
    want = {k: kinds.count(k) for k in set(kinds)}
    names = {"evergreen": "question", "top list": "top list", "true story": "true story"}
    ask = ", ".join(f'{v} "{names[k]}"' for k, v in want.items())
    subjects = [re.sub(r"\s+", " ", str(t)).strip()[:60] for t in trending if str(t).strip()][:12]
    tr = TRENDING_ASK.format(subjects="; ".join(subjects), n=max(1, round(trend_share() * len(kinds)))) if subjects else ""
    terms = search_terms()
    if terms: tr += SEARCH_ASK.format(terms="; ".join(terms))
    ans, _ = factpack.gemini(EVERGREEN_PLAN.format(n=len(kinds) + 2, kinds=ask, cats=", ".join(cats), recent=recent, trending=tr), None,
                             timeout=100, temperature=0.8)
    items = ans.get("items") if isinstance(ans, dict) else None
    packs = []
    for it in items or []:
        if not any(v > 0 for v in want.values()) or factpack.STATE.get("spent"): break
        kind = {v: k for k, v in names.items()}.get(str(it.get("kind") or "").lower().strip(), "")
        if want.get(kind, 0) <= 0: continue
        q, title = str(it.get("idea") or it.get("question") or "").strip(), str(it.get("wikipedia") or "").strip()
        if not q or not title: continue
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        try:
            txt, img = factpack.page_text(url, wiki=True)
            if len(txt) < 800: continue
            got, _ = factpack.gemini(EVERGREEN_FACTS.format(q=q, how=HOW[kind], title=title, url=url, text=txt), factpack.SCHEMA,
                                     timeout=100, lite=True)
        except Exception as e:
            print("evergreen:", title, str(e)[:120]); continue
        _, single = factpack.verify((got or {}).get("facts"), {1: factpack.norm(txt)}, {1: "wikipedia"})
        if len(single) < MIN_FACTS[kind]: print(f"evergreen: {q}: only {len(single)} checked facts"); continue
        src = {"outlet": "Wikipedia", "title": title, "url": url, "published": "", "kind": "wikipedia"}
        rides = str(it.get("trending") or "").strip()[:80]
        p = {"topic": q, "kind": kind, "signal": f"evergreen {names[kind]}" + (f" (trending: {rides})" if rides else ""), "category": it.get("category", ""),
             "what_is_new": "", "hooks": [factpack.undash(h) for h in (got or {}).get("hooks") or []][:3],
             "sources": [[title, url, "Wikipedia", ""]], "verified": [], "one_source": single,
             "images": factpack.image_ideas([(src, txt, img)])}
        if not covered(p, seen): packs.append(p); want[kind] -= 1
    return packs


def fiction_pack(seen):
    """A premise for an original short story (the fiction test), as a pack the writer can use: no facts to check, one
    line saying it is fiction, and the channel as its source."""
    try:
        ans, _ = factpack.gemini(FICTION_PLAN.format(recent="; ".join(t for t, _, _ in seen[-30:])[:800]), None, timeout=60,
                                 temperature=1.0, lite=True)
    except Exception as e:
        print("fiction:", str(e)[:120]); return None
    premise = str(ans.get("premise") or "").strip() if isinstance(ans, dict) else ""
    if not premise: return None
    return {"topic": premise, "kind": "fiction", "signal": "fiction test", "category": ans.get("category") or "Entertainment",
            "what_is_new": "", "hooks": [], "verified": [{"claim": "This is an original fictional story.", "sources": [1]}],
            "sources": [["Quickplay Daily original story", "https://www.youtube.com/@quickplaydaily", "Quickplay Daily", ""]],
            "one_source": [], "images": []}


TESTS = {   # what each Short can try; the data (analytics/drivers.csv) decides, and keeps deciding as it grows
    "hook_type": {"question": "Open with a question (ending in a question mark) that the Short then answers.",
                  "number": "Open with the most surprising number in the facts.",
                  "superlative": "Open with a first, biggest, only or record detail from the facts.",
                  "twist": "Open with a twist: what people would expect, then the surprising truth."},
    "length": {"under 25 s": "Keep it short: 60 to 72 words in total.",
               "35 to 44 s": "Take a little longer: 105 to 120 words in total."},
    "ending": {"loop": "End with a line that flows straight back into the first line so the Short loops, and end on the "
                       "same picture as the first shot. No question and no subscribe line at the end.",
               "question": "End with a short question viewers can answer in the comments.",
               "follow line": "End the last beat with one short spoken line asking viewers to subscribe for one of these "
                              "every day."},
    "title_search": {"search phrase": "Open the title with one of the search phrases listed below, word for word, if one "
                                      "fits the story; otherwise with the name people search.",
                     "curiosity": "Open the title with the name, then the most curious detail; don't copy a search phrase."},
    "first_frame": {"cover": "Beat 1 shows a title card from the first frame (\"atWord\": 0): 2 to 4 big words naming the "
                             "subject and the hook, over the subject's photo.",
                    "photo": "Beat 1 has no graphic: the subject's photo alone fills the first frame."},
    "angles": {"shown": "", "hidden": ""},      # whether the writer sees which angles already work on YouTube (angles())
    "series": {"single": "", "two parts": "", "three parts": ""},  # Shorts with a cliffhanger between them (emit_kind()); a rich pack only
}
NOT_FOR = {"breaking": {"series"}, "follow-up": {"series"}, "remake": {"series", "angles"}, "evergreen": {"title_search", "angles", "series"},
           "top list": {"title_search", "angles"}, "true story": {"title_search", "angles"}, "fiction": {"title_search", "angles"}}
RETEST = 5      # 1 in 5 Shorts challenges a winner, so new data can overturn it


def winners():
    """{test: arm} for each test where the data has a clear winner (verdict "push", above typical)."""
    out, p = {}, ROOT / "analytics" / "drivers.csv"
    if not p.exists(): return out
    for r in csv.DictReader(p.open()):
        try: lift = float(r.get("lift") or 0)
        except ValueError: continue
        f, v = r.get("feature"), r.get("value")
        if f in TESTS and v in TESTS[f] and r.get("verdict") == "push" and lift > 1: out.setdefault(f, v)
    return out


def test_plan(k, kind="news"):
    """The style for Short number k: every winner the data has found, plus one test in turn (an open test, or on every
    RETEST-th Short a challenger to a winner), plus the comment-replies test on alternate Shorts.
    Returns (the note for the prompt, {test: arm} recorded on the board for analytics)."""
    dims = [t for t in TESTS if t not in NOT_FOR.get(kind, ())]
    won = {t: a for t, a in winners().items() if t in dims}
    picks, still = dict(won), [t for t in dims if t not in won]
    if won and k % RETEST == 0:
        t = list(won)[(k // RETEST) % len(won)]
        rivals = [a for a in TESTS[t] if a != won[t]]
        picks[t] = rivals[(k // (RETEST * len(won))) % len(rivals)]
    elif still:
        t = still[k % len(still)]
        arms = list(TESTS[t])
        picks[t] = arms[(k // len(still)) % len(arms)]
    picks["replies"] = "on" if k % 2 == 0 else "off"
    return style_note(picks), picks


def style_note(picks):
    note = " ".join(TESTS[t][a] for t, a in picks.items() if t in TESTS and TESTS[t].get(a))
    return f"STYLE FOR THIS SHORT: {note}" if note else ""


TRANSLATE = """Translate this YouTube Short's title and summary for viewers searching in Spanish ("es", Spain), Portuguese
("pt", Brazil) and Hindi ("hi"). Keep the names of people, games, films, shows, teams and songs as they are, keep numbers
and the emoji at the end of the title, keep titles under 70 characters, and use no dashes and no < or > characters.
Title: {title}
Summary: {summary}
Return {{"es": {{"title": "...", "summary": "..."}}, "pt": {{"title": "...", "summary": "..."}}, "hi": {{"title": "...", "summary": "..."}}}}"""


def translations(b):
    """The title and summary in Spanish, Portuguese and Hindi: run_board.py turns them into YouTube localisations, so the
    Short also shows up in searches in those languages (Spanish and Hindi speakers are among our biggest audiences)."""
    m = b.get("meta") or {}
    try:
        ans, _ = factpack.gemini(TRANSLATE.format(title=m.get("title", ""), summary=m.get("summary", "")), None, timeout=60,
                                 temperature=0.2, lite=True)
    except Exception as e:
        print("translations:", str(e)[:120]); return {}
    out = {}
    for lang in ("es", "pt", "hi"):
        t = ans.get(lang) if isinstance(ans, dict) else None
        if isinstance(t, dict) and t.get("title") and t.get("summary"):
            out[lang] = {k: re.sub(r"[<>]", "", clean(str(t[k])))[:100 if k == "title" else 1000] for k in ("title", "summary")}
    return out


def suggestions(topic):
    """What people type into YouTube search about the topic (Google's search suggestions for GB and US)."""
    out = []
    for q in dict.fromkeys([topic, " ".join(topic.split()[:2])]):
        for gl in ("GB", "US"):
            try:
                r = requests.get("https://suggestqueries.google.com/complete/search", timeout=10,
                                 params={"client": "firefox", "ds": "yt", "hl": "en", "gl": gl, "q": q})
                out += [s for s in r.json()[1] if isinstance(s, str)]
            except Exception: pass
        if out: break
    return list(dict.fromkeys(out))[:8]


def angles(topic):
    """What already works on YouTube for this topic: the most-viewed Shorts of the last 3 days (title, views, hours since
    posted), so the writer can find a better angle. About 101 units of the YouTube allowance, so a few a run."""
    try:
        import youtube as Y, quota
        if not quota.allow(101, "angle search"): return []
        yt = Y.client()
        quota.spend(101, "angle search")
        since = (NOW - dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = yt.search().list(part="snippet", q=topic, type="video", videoDuration="short", order="viewCount",
                             publishedAfter=since, maxResults=5, relevanceLanguage="en").execute()
        ids = [it["id"]["videoId"] for it in r.get("items", []) if (it.get("id") or {}).get("videoId")]
        out = []
        for it in (yt.videos().list(part="statistics,snippet", id=",".join(ids)).execute().get("items", []) if ids else []):
            hrs = max(1, (NOW - dt.datetime.fromisoformat(it["snippet"]["publishedAt"].replace("Z", "+00:00"))).total_seconds() / 3600)
            out.append(f'"{it["snippet"]["title"]}" ({int(it["statistics"].get("viewCount", 0)):,} views in {hrs:.0f} hours)')
        return out
    except Exception as e:
        print("angles:", str(e)[:150]); return []


def lift_of(feature, value):
    """The data's lift for one feature value (analytics/drivers.csv), or None while there are too few Shorts to tell."""
    p = ROOT / "analytics" / "drivers.csv"
    if not p.exists(): return None
    for r in csv.DictReader(p.open()):
        if r.get("feature") == feature and r.get("value") == value and r.get("verdict") not in (None, "", "too few to tell"):
            try: return float(r.get("lift") or 0)
            except ValueError: return None
    return None


def share(kind, base, top):
    """How many Shorts of a kind to write: more when the data says that kind beats typical, fewer when it trails (never
    none, so it keeps being measured)."""
    lift = lift_of("kind", kind)
    return base if lift is None else max(1, min(top, round(base * min(2.0, max(0.5, lift)))))


def dropoff_notes():
    """Where viewers swipe away (analytics/dropoff.json from dropoff.py): guidance once enough Shorts are measured, which
    changes as the data does."""
    try: return json.loads((ROOT / "analytics" / "dropoff.json").read_text()).get("guidance") or []
    except Exception: return []


def shape(b, picks):
    """Makes the board follow its first-frame test."""
    beats = b.get("beats") or []
    if not beats: return
    v = beats[0].get("visual") or {"type": "none"}
    if picks.get("first_frame") == "cover":
        if v.get("type", "none") == "none":
            words = re.sub(r"[^\w\s'&:]", " ", str((b.get("meta") or {}).get("title", ""))).split(":")[0].split()[:4]
            if words: beats[0]["visual"] = {"type": "title", "lines": [" ".join(words)], "highlight": [], "atWord": 0}
        else: beats[0]["visual"]["atWord"] = 0
    elif picks.get("first_frame") == "photo":
        beats[0]["visual"] = {"type": "none"}


def writer_name(model):
    return model if ":" in model else f"gemini:{model}"


def choose_writer(sid):
    """The first-choice model for one board, by Thompson sampling over the writers that still have quota, scored by
    analytics/models.json (each Short against Shorts posted around the same time); a writer with under 3 measured Shorts
    gets an early-try boost, so every company's model is tested on real Shorts and the data decides. None: the chain's
    own order."""
    try: stats = json.loads((ROOT / "analytics" / "models.json").read_text()).get("writers") or {}
    except Exception: stats = {}
    spent, slow = factpack.STATE.get("spent_models") or set(), factpack.STATE.get("slow_models") or {}
    try: cands = [writer_name(m) for m in (factpack.STATE.get("models") or [])] + factpack.chain()
    except Exception: cands = []
    cands = [m for m in cands if m.split(":", 1)[-1] not in spent and m not in spent and slow.get(m.split(":", 1)[-1], 0) < 2
             and slow.get(m, 0) < 2 and not m.startswith("claude:")]       # Claude only when every free model is spent
    if len(cands) < 2: return None
    rng, best, top = random.Random(f"writer:{sid}"), None, -1e9
    for m in cands:
        s = stats.get(m) or {}
        n = int(s.get("n") or 0)
        mean = float(s.get("score") or 1.0) if n else 1.0
        if n < 3: mean = max(mean, 1.08)
        v = rng.gauss(mean, 0.35 / math.sqrt(n + 1))
        if v > top: best, top = m, v
    return best


def write_one(p, sid, day, prompt_head, extra="", kind="news"):
    prompt = prompt_head + (f"\n\n{extra}" if extra else "") + "\n\nTHE PACK\n" + pack_text(p)
    pick = choose_writer(sid)
    ans, model = factpack.gemini(prompt, None, timeout=150, temperature=0.6, **({"prefer": pick} if pick else {}))
    if not isinstance(ans, dict) or ans.get("skip"): return None, f"skipped: {ans.get('skip') if isinstance(ans, dict) else 'no board'}"
    best = None             # the first board with no errors, kept in case fixing its warnings breaks it
    for attempt in range(3):
        if isinstance(ans, dict) and isinstance(ans.get("board"), dict): ans = ans["board"]     # a model that wrapped it
        b = clean(ans)
        if not isinstance(b.get("beats"), list) or not b["beats"]: b["beats"] = []
        for k in ("tiktok", "look", "mode", "flag", "bgvideo"): b.pop(k, None)
        b = {"id": sid, "created": str(day), **{k: v for k, v in b.items() if k not in ("id", "created", "writer")}, "writer": writer_name(model)}
        added = BG.fill(b)        # the video behind the Short: the writer's own searches, tidied; the category's when it gave fewer than 2
        if os.environ.get("WRITE_DRY"): b["mode"] = "dry"
        errs, warns = validate.check(b)
        if kind == "fiction": warns = [w for w in warns if "stock" not in w and "real picture" not in w]   # stock is the point
        else: errs = errs + media_problems(b)
        if not errs and kind != "fiction": errs = ["facts: " + x for x in fact_check(b, p)]     # only a clean board is worth a fact check
        note = f"{model}, {len(warns)} warnings" + (f" ({'; '.join(warns)[:200]})" if warns else "") + (f", background: {added} from the category" if added else "")
        if not errs:
            if not warns or best: return b, note     # a warning flags the Short for a person, so it gets one fixing round
            best = (b, note)
        elif best: return best
        if attempt == 2: break
        fix = (prompt_head + (f"\n\n{extra}" if extra else "") + "\n\nTHE PACK\n" + pack_text(p) + "\n\nYOUR BOARD\n" + json.dumps(ans, ensure_ascii=False)
               + "\n\nIt fails these checks. Fix every one and return the whole corrected board as JSON:\n- " + "\n- ".join(errs + warns))
        ans, model = factpack.gemini(fix, None, timeout=150, temperature=0.3)
        if not isinstance(ans, dict): break
    return best or (None, "still failing: " + "; ".join(errs)[:300])


def main():
    facts = factpack.OUT
    if not facts.exists(): print("no fact packs"); return
    d = json.loads(facts.read_text())
    breaking = d.get("mode") == "breaking"          # a check between the main runs: only what is spiking
    run, day, cap = plan(breaking, d.get("run", ""))
    print(f"{run} run for {day}: {cap} to write from {len(d.get('topics') or [])} fact packs")
    if cap <= 0 and (breaking or reserve_count() >= 6): return
    seen, used, follow, up, src_up = recent(), day_formats(day), hot(), boosts(), boosts("source")
    moods, notes = list(CFG.get("music_moods") or []), dropoff_notes()
    head = (RULES % {"moods": moods} + "\n\nFORMATS\n" + formats() + "\n\nWHAT THE DATA SAYS WORKS\n" + recipe()
            + ("\n\nWHERE VIEWERS SWIPE AWAY (from the data)\n- " + "\n- ".join(notes) if notes else "")
            + "\n\nEXAMPLE BOARD (shape only, a different story)\n" + example())
    out, written = ROOT / "boards" / "queue", []
    deadline = time.time() + 60 * float(os.environ.get("WRITE_MINUTES") or 55)   # the job stops at 90: save what is written
    late = lambda: time.time() > deadline
    state = {"n": next_id(), "angles": int(CFG.get("angle_searches_per_run", 2))}
    out.mkdir(parents=True, exist_ok=True)

    def emit(p, note="", kind="news", reserve=False, fol=None, tests=None, series=None):
        sid = f"QD-{state['n']:03d}"
        if tests is None: style, tests = test_plan(state["n"], kind)
        else: style = style_note(tests)
        extra = [(f"Formats already used for this day, oldest first: {', '.join(used)}. Use a different format from the "
                  f"last one ({used[-1]}), and prefer the ones used least.") if used else "", style, note]
        if tests.get("title_search") == "search phrase":
            sug = suggestions(p["topic"])
            if sug: extra.append("WHAT PEOPLE TYPE INTO YOUTUBE SEARCH ABOUT THIS: " + "; ".join(sug))
        if tests.get("angles") == "shown" and state["angles"] > 0 and not breaking:
            state["angles"] -= 1
            ang = angles(p["topic"])
            if ang: extra.append("SHORTS ALREADY GETTING VIEWS ON THIS SUBJECT (learn which angle or question works, then "
                                 "find a fresher or better one; never copy their wording, footage or script): " + "; ".join(ang))
        try:
            b, why = write_one(p, sid, day, head, "\n\n".join(x for x in extra if x), kind)
        except Exception as e:
            b, why = None, f"error: {e}"[:200]
        print(f"{p['topic']}: {why}")
        if not b: return None
        before = json.dumps(b)
        shape(b, tests)
        if validate.check(b)[0]: b = json.loads(before)
        b.update(kind=kind, test=tests, source=source_of(p.get("signal")))
        if fol: b["follows"] = fol["short"]
        if reserve: b["reserve"] = True
        if series: b["series"] = series
        tr = translations(b)
        if tr: b["meta"]["translations"] = tr
        (out / f"{sid}.json").write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")))
        written.append(b); used.append(b.get("format", "")); state["n"] += 1
        return b

    def emit_kind(p, kind, reserve=False, note="", fol=None):
        """A Short of any kind, or two or three parts with a cliffhanger between them when its series test says so and the
        pack has 3 facts or more a part (never from the reserve, which could release them out of order, and never a
        follow-up or breaking news)."""
        style, tests = test_plan(state["n"], kind)
        base = "\n\n".join(x for x in (KIND_NOTE.get(kind, ""), note) if x)
        facts = len(p.get("verified") or []) + len(p.get("one_source") or [])
        parts = min({"two parts": 2, "three parts": 3}.get(tests.get("series") or "", 1), facts // 3)   # 3 facts a part at least
        if parts < 2 or reserve or fol:
            if "series" in tests: tests["series"] = "single"
            return emit(p, base, kind, reserve, fol=fol, tests=tests)
        first, made = f"QD-{state['n']:03d}", []
        for n in range(1, parts + 1):
            prev = made[-1] if made else None
            said = " ".join(x.get("say", "") for x in prev.get("beats") or []) if prev else ""
            b = emit(p, (base + "\n\n" if base else "") + part_note(n, parts, prev["meta"]["title"] if prev else "", said), kind,
                     tests=tests, series={"id": first, "part": n, "of": parts, **({"prev": prev["id"]} if prev else {})})
            if not b: break
            made.append(b)
        if len(made) == parts: return made[0]
        for b in made:                                             # a part missing: no cliffhangers either
            (out / f"{b['id']}.json").unlink(missing_ok=True); written.remove(b); used.pop()
        return emit(p, base, kind, tests={**tests, "series": "single"})

    topics = list(enumerate(d.get("topics") or []))[:4 if breaking else None]   # best first; favoured categories and breakouts move up
    rank = lambda kp: (kp[0] - up.get(kp[1].get("category"), 0) - src_up.get(source_of(kp[1].get("signal")), 0)
                       - (100 if any(covered(kp[1], [r["_about"]]) for r in follow) else 0))
    for _, p in sorted(topics, key=rank):
        if len(written) >= cap or factpack.STATE.get("spent") or late(): break
        if len(p.get("verified") or []) + len(p.get("one_source") or []) < 2:      # one fact makes a thin Short
            print("too few facts:", p["topic"]); continue
        fol = next((r for r in follow if covered(p, [r["_about"]])), None)
        if not fol and covered(p, seen + [about(b) for b in written]): print("covered already:", p["topic"]); continue
        note = (f'FOLLOW-UP: our Short "{fol.get("title")}" is getting {float(fol["times_typical"]):.0f} times our usual '
                "views. Write a follow-up on the same subject: a new angle or the next chapter from this pack, never a "
                "repeat, with a title tied to the original.") if fol else ""
        if fol or breaking: got = emit(p, note, "follow-up" if fol else "breaking", fol=fol)
        else: got = emit_kind(p, "news")
        if got and fol: follow.remove(fol)
    for fol in follow[:1]:                                    # the strongest breakout with no pack today: one from its own pages
        if len(written) >= cap or factpack.STATE.get("spent") or late(): break
        p = followup_pack(fol, seen)
        if not p: print("follow-up: no pack for", fol.get("short")); continue
        note = (f'FOLLOW-UP: our Short "{fol.get("title")}" is getting {float(fol["times_typical"]):.0f} times our usual '
                "views. Write a follow-up on the same subject: a new angle or the next chapter from this pack, never a "
                "repeat, with a title tied to the original.")
        if emit(p, note, "follow-up", fol=fol): follow.remove(fol)
    if run == "morning" and len(written) < cap and not factpack.STATE.get("spent") and not late():   # one remake a day
        for w in weak():
            p = next((p for _, p in sorted(topics, key=rank) if covered(p, [w["_about"]])), None)      # still trending
            if not p or len(p.get("verified") or []) + len(p.get("one_source") or []) < 2: continue
            b = emit(p, REMAKE_NOTE.format(title=w.get("title", "")), "remake")
            if b: b["remakes"] = w["short"]; (out / f"{b['id']}.json").write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")))
            break
    if not breaking and not factpack.STATE.get("spent"):    # evergreen kinds fill spare places and stock the reserve
        spare = max(0, cap - len(written))
        if run == "morning":                                  # the fiction test: a few original stories a day, as the data allows
            for _ in range(min(spare, share("fiction", 1, 3))):
                if late(): break
                fp = fiction_pack(seen + [about(b) for b in written])
                if not fp or factpack.STATE.get("spent"): break
                before = len(written); emit_kind(fp, "fiction"); spare = max(0, spare - (len(written) - before))
        want = min(20, spare + (2 if reserve_count() < 6 else 0))      # every place the news left, so each run writes its full number
        if want and not late():
            try:
                ever = evergreen_packs(pick_kinds(want), seen + [about(b) for b in written], [p["topic"] for _, p in topics[:12]])
            except Exception as e:
                ever = []; print("evergreen:", str(e)[:200])
            for p in ever:
                if factpack.STATE.get("spent") or late(): break
                before = len(written)
                emit_kind(p, p.get("kind", "evergreen"), reserve=spare <= 0)
                if spare > 0: spare = max(0, spare - (len(written) - before))
    print(f"wrote {len(written)} of {cap}: " + "; ".join(f"{b['id']} {b['meta']['title']}" + (" (reserve)" if b.get("reserve") else "")
                                               for b in written))
    print("gemini:", json.dumps({"order": factpack.STATE.get("models", [])[:6], **factpack.gemini_state(), "late": late()}))


if __name__ == "__main__":
    main()
