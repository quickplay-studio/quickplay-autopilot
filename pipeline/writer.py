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
CATS = ["Gaming", "Film", "Music", "Sport", "Tech", "Science", "Entertainment", "Animals", "Food", "Cars", "History"]   # the last four: new markets on test from 24 October

RULES = """You write one YouTube Short script ("board") as JSON for Quickplay Daily: an anonymous, family-friendly UK channel about
gaming, film and TV, music, sport, celebrities, streamers and creators, tech launches, space, animals and nature, food,
cars and history. Every rule must hold.
- UK English and UK style: "Tuesday 20 October", "20 million pounds", colour, favourite. Never use an en dash or an em dash
  anywhere (use commas, colons or full stops).
- Never politics, crime, health claims, money or investing advice, adult content or gambling. Explore the subject itself;
  never talk about views, virality or why something went viral.
- Never negative about a real person (Charlie, 25 October): no admits, betrays, slams, feuds, backlash, mocked, exposed,
  blamed, fails, flops, quits, splits, rows or drama about anyone real, however the source frames it. Real people appear
  for what they made, won, released, said or achieved; a game show's "betrayal" is a plot point in fiction, not in
  our Shorts. Negative turns are allowed only in a fiction board.
- Facts: use ONLY the facts in the pack below. A "verified" fact can be stated plainly. A "one source" fact must name its
  source in the narration ("Variety says", "according to the BBC"). Anything unconfirmed must be said to be unconfirmed and
  who is saying it. Never invent anything. Copy names, numbers and dates exactly as the pack writes them.
- Your own point (YouTube only pays for and recommends original Shorts, never ones that read out news text or follow a
  template): every Short makes one point its sources don't spell out, built only from the pack's own facts: two facts set
  side by side, one number measured against another, what follows from the facts, or what it means for the viewer. Land
  it in the payoff beat. Tell the story in your own order and your own words around that point: never follow an article's
  order, structure or phrasing, and never add an outside fact to make the point.
- Relatable, for everyone: the Short is for the millions who know the subject from their own life (the game on every
  phone, the film everyone has seen, the song at every party, the team, the gadget in their pocket), never for the fans
  who know the lore. Tell it through what it means for the viewer ("you", "your", "everyone who..."), and skip business
  history, licensing, corporate timelines, dates for their own sake and records only fans care about. If the subject is
  known only to fans, find the angle an ordinary person would care about, or return {"skip": "niche"}. Set "appeal":
  "everyone" when most people in the UK and US know the subject, "fans" when only followers do.
- Beat 1 (the hook): the most surprising true detail in 12 words or fewer, said as a plain statement whose first four
  words name the best-known person, band or team in the pack (the one most viewers know; never a co-star, outlet or date
  first: "Olivia Rodrigo's new video has a surprise host", not "David Byrne turns host in Olivia Rodrigo's video"), or the
  title when no person is in the story, then the result: what just changed, or how it ended (hooks led by a named person
  get about twice the views here). Open with a question or a twist only when the style line below asks for one. Never
  "X is back", never "Discover", "Did you know", "Learn", "Here's how", "Today we", "Let's look" or any slow intro. Put
  "impact": true on the hook and on the payoff beat.
- 5 to 9 beats, 70 to 110 words of narration in total (count them; a length in the style line below sets its own range),
  one or two sentences per beat (a longer Short, when the style note below asks for one, keeps every beat a new surprise
  and saves the wildest for last).
- Ending: land the payoff, then either a line that loops back into the hook or a short question viewers can answer.
- Neat and minimal: at most 3 beats with a graphic ("visual" not {"type": "none"}), few words on each graphic.
- Real footage first: at least 4 in 5 shots show the actual subject, and beat 1's shots always do. In order: the pack's
  real pictures, "commons-search:Full Name" for each person (add "label": {"t": "Full Name", "s": "who they are"} the
  first time each person appears), "nasa:video:words" or "nasa:image:words" for space, "page:https://..." for an official
  page's own picture (a studio, publisher, label, team or agency; never a news site). Stock ("pixabay:video:2 to 4
  concrete words") only when nothing real exists, at most 1 in 5 shots, never on beat 1.
- Shots: 1 to 3 per beat, a new shot every 2 to 3 seconds (about every 6 to 8 words): later shots in a beat take "at"
  (the word number the cut lands on); "move" is one of in, out, left, right, up, down, still. Keep the camera moving
  gently (in, out, left or right; Shorts with a steady, moving camera do about twice as well here as calm, still ones):
  "still" only under a graphic.
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
- meta.title: under 50 characters (count them). The exact name people search comes first (person, game, film, show,
  team), then, as the style line's title answer says, either the news the first line says ("Tate McRae hits number one
  in Australia") or hold the answer back: promise the detail without giving it away, as the Shorts that break out from
  small channels do ("LISA's Tarantino video: the detail you missed", "Avengers: Doomsday teaser: 3 things to spot",
  "iPhone Duo: every big change explained"). Never a question (question titles get about half the views here) and never a
  promise the Short doesn't keep: anything unconfirmed is called a report or a rumour. An emoji only as the style line
  below says: one at the very end when it asks for one, none at all otherwise.
  meta.alt_title: a second title with a different angle, same rules. meta.summary: one or two sentences.
- meta.hashtags: 8 to 15, exact names first, then the franchise or show, the category, then one or two broad ones such as
  #Trending or #Gaming; never #viral or anything unrelated. meta.tags: 5 to 15 phrases people would search.
  meta.comment: one question viewers can answer, under 100 characters, no links.
- meta.sources: the pack's sources as [title, url] in the same order. meta.facts: every claim you used as
  [claim, [source numbers from the pack]].
- "format": one of the format ids below. On this channel "one_detail" does best (about twice the typical views) and
  "three_details" worst (under half): choose one_detail whenever one striking detail carries the story, three_details only
  when the pack holds three details each strong enough to lead, and keep rotating formats as the note below asks.
  "category": one of Gaming, Film, Music, Sport, Tech, Science, Entertainment, Animals, Food, Cars, History.
  "appeal": "everyone" or "fans" (see above). "music": {"mood": one of %(moods)s}.
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
    """What the last 14 days of boards covered (queue, ready, done, reserve and failed); dry-run boards are tests that
    never go out, so they cover nothing."""
    cut, out = str((NOW - dt.timedelta(days=days)).date()), []
    for d in ("queue", "ready", "done", "reserve", "failed"):
        for f in (ROOT / "boards" / d).glob("QD-*.json"):
            b = board(f)
            if str(b.get("created", "")) >= cut and b.get("mode") != "dry": out.append(about(b))
    return out


def covered(p, seen, watch=None):
    """Covered: a recent board cites one of the pack's articles (Wikipedia pages don't count: many stories share one), or
    its title shares two of the topic's longer words. A watchlist topic (watch: True, or a "watchlist" signal) is judged
    more loosely, because a big event's news all cites the same few articles: covered only when one recent board cites at
    least half of its articles (and two or more), or its title shares two of the topic's longer words. (24 October: one GTA
    6 Short made every GTA 6 and Avengers angle "covered", so the watchlist's places a day could never be filled.)"""
    if watch is None: watch = str(p.get("signal", "")).startswith("watchlist")
    words = {w for w in re.findall(r"[a-z0-9]+", p["topic"].lower()) if len(w) > 3}
    urls = {s[1] for s in p.get("sources") or [] if len(s) > 1 and "wikipedia.org" not in str(s[1])}
    need_urls = max(2, -(-len(urls) // 2)) if watch else 1
    need_words = 2 if watch else min(2, len(words))
    for title, _, srcs in seen:
        if urls and len(urls & srcs) >= need_urls: return True
        if words and len(words) >= need_words and len(words & set(re.findall(r"[a-z0-9]+", title.lower()))) >= need_words: return True
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
    # a posting day runs from slot_first to slot_first (all 24 hours), and what this run writes goes out lead_hours from now
    # at the soonest (plan.py's LEAD), so the day is the one that hour falls in. Without the lead, the 06:47 UTC breaking
    # check (started by GitHub at about 07:15, 07:15 UK in winter) counted towards yesterday, which is usually full, and
    # wrote nothing from 25 October, when the clocks go back.
    lead = dt.timedelta(hours=float(CFG.get("lead_hours", 3)))
    base = (uk + lead - dt.timedelta(hours=h, minutes=m)).date()
    day = base + dt.timedelta(days=1 if run == "evening" else 0)
    made = 0
    for d in ("queue", "ready", "done", "failed"):
        for p in (ROOT / "boards" / d).glob("QD-*.json"):
            try: b = json.loads(p.read_text())
            except Exception: continue
            if b.get("created") == str(day) and not b.get("reserve"): made += 1
    import quota
    limit = quota.target() - (1 if day.weekday() == 6 else 0)
    runs = {k: int(v) for k, v in (CFG.get("runs") or {}).items() if str(v).isdigit()}
    per_run = share("breaking", 2, 4) if breaking else max(1, -(-runs.get(run, 6) * quota.target() // max(1, sum(runs.values()))))
    if run == "afternoon": per_run = min(max(30, limit * 3 // 4), max(per_run, limit - made))     # the day's last run makes up anything the morning missed
    cap = min(per_run, max(0, limit - made))
    if os.environ.get("WRITE_COUNT", "").strip().isdigit(): cap = int(os.environ["WRITE_COUNT"])
    return run, day, cap


# Keys the pipeline sets on a board itself. A model shown an example board copied them into new ones (24 October: seven
# news boards claimed to follow QD-037, four carried "watch": their own topic, three a franchise with no number), which
# can count a breakout as followed up or fill a watchlist item's places, so the example never shows them and they are
# stripped from whatever a model writes.
BOOKKEEPING = ("watch", "follows", "remakes", "franchise", "series", "reserve", "kind", "source", "editor", "writer",
               "test", "mode", "appeal_note")


def example():
    """The newest finished board closest to the rules (fewest validator warnings, least stock), as the shape to copy."""
    best, free = None, f"QD-{next_id():03d}"
    done = sorted((ROOT / "boards" / "done").glob("QD-*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0), reverse=True)
    for p in done[:20]:
        try: b = json.loads(p.read_text())
        except Exception: continue
        if b.get("mode") or b.get("reserve"): continue
        for k in ("id", "created", "tiktok", "look", "flag", "bgvideo") + BOOKKEEPING: b.pop(k, None)
        (b.get("meta") or {}).pop("translations", None)         # made separately (translations()), not by the writer
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


# The Recipe lines the writer can act on, the robust verdicts first (content review, 24 October: a blind cut at 900 of the
# Recipe's 3,054 characters ended mid-line in "Format: ...", so the hook, length and title lines never reached the writer).
# RECIPE_FIRST is the writer's own craft choices in the order of their evidence: hook style, length and format are the
# ones the data report found robust (the same direction on every measure), then what is paused, the title, the music
# mood and the rest. Lines on what the pipeline decides itself (posting time and day, the look, comment replies, the
# writer model, the kind, the category mix and follow-ups, which the planner applies) are left out, and so are pictures
# (real pictures first is the channel's rule, and Charlie's) and the progress of the tests (the hub's, not the writer's);
# a test's STYLE line beats any of them. A line is kept whole or left out, never cut, and the lot stays inside RECIPE_BUDGET.
RECIPE_FIRST = ("Hook style", "Length", "Format", "Hook length", "Paused for 14 days", "Title", "Title wording", "Title emoji",
                "Title answer", "Music mood", "Ending", "Follow line", "Appeal")
RECIPE_NOT = ("Posting time", "Day posted", "Captions", "Voice", "Camera energy", "Colour grade", "Opening", "Comment replies",
              "Writer model", "Kind of Short", "Category mix", "Follow up", "Topic source", "Series", "Named series", "Pictures",
              "Exploration", "Posted late", "First frame", "Angle research", "Tests being run")
RECIPE_BUDGET = 1600


def recipe():
    """The Recipe section of analytics/insights.md as the writer is given it: the top-level lines it can act on (not the
    tests' progress, nor what the planner and the render decide), the robust verdicts first, whole lines within the budget."""
    p = ROOT / "analytics" / "insights.md"
    if not p.exists(): return ""
    m = re.search(r"## Recipe.*?(?=\n## )", p.read_text(), re.S)
    if not m: return ""
    lines = [l for l in m.group(0).splitlines()[1:] if l.startswith("- ") and not l.startswith("- - ")]
    # an insights.md written before 24 October evening still carries "a hook of 8 words or fewer" (3 Shorts of evidence, and
    # the hook rule allows 12 words); analytics.audience_recipe now says the name belongs in the hook's first four words
    lines = [re.sub(r" and a hook of \d+ words or fewer", " and the best-known name in the hook's first four words", l) for l in lines]
    label = lambda l: l[2:].split(":", 1)[0].split(" (", 1)[0].strip()
    first = sorted((l for l in lines if label(l) in RECIPE_FIRST), key=lambda l: RECIPE_FIRST.index(label(l)))
    rest = [l for l in lines if label(l) not in RECIPE_FIRST and not label(l).startswith(RECIPE_NOT)]
    out, size = [], 0
    for l in first + rest:
        if size + len(l) > RECIPE_BUDGET: continue
        out.append(l); size += len(l) + 1
    if not out: return ""
    return "\n".join(["(Where a STYLE FOR THIS SHORT line below differs from these, follow the style line: it is a test.)"] + out)


def pack_text(p):
    lines = [f"TOPIC: {p['topic']} (trend signal: {p.get('signal', '')}; category hint: {p.get('category', '')})"]
    if p.get("what_is_new"): lines.append(f"What is new: {p['what_is_new']}")
    lines.append("Sources (number: outlet, title, date, url):")
    for k, s in enumerate(p["sources"], 1):
        ref = " (a reference: state its facts plainly, never name or cite it)" if "wikipedia.org" in str(s[1]) else ""
        lines.append(f"  {k}: {s[2]}, {s[0]}, {s[3]}, {s[1]}{ref}")
    lines.append("Verified facts (two sources):")
    for f in p["verified"]: lines.append(f"  - {f['claim']} {f['sources']}")
    if p.get("one_source"):
        lines.append("One source facts (name the source if used):")
        for f in p["one_source"]: lines.append(f"  - {f['claim']} {f['sources']}")
    if p.get("images"): lines.append("Real pictures to use as shots: " + ", ".join(p["images"]))
    if p.get("hooks"): lines.append("Hook ideas: " + " | ".join(p["hooks"]))
    return "\n".join(lines)


WIKI_SAID = re.compile(r"(,\s*)?\b(according to wikipedia|as wikipedia (puts it|says|notes)|wikipedia (says|shows|states|lists|notes|reports)( that)?)\b(,\s*)?", re.I)


def unwiki(b):
    """Narration never cites Wikipedia (validate.py): the attribution is dropped and the fact stated, so a board isn't
    lost to a habit models keep (two of the 23 October evening boards failed only on this)."""
    for x in b.get("beats") or []:
        s = x.get("say")
        if isinstance(s, str) and WIKI_SAID.search(s):
            s = re.sub(r"\s+([,.!?])", r"\1", re.sub(r"\s{2,}", " ", WIKI_SAID.sub(" ", s))).strip(" ,")
            x["say"] = s[:1].upper() + s[1:]
    return b


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


STOP = -99        # the weight of a paused choice (drivers.py "pause", once "stop"): left out, not just moved down
PAUSED = ("pause", "stop")


def driver_rows():
    p = ROOT / "analytics" / "drivers.csv"
    if not p.exists(): return []
    try: return list(csv.DictReader(p.open()))
    except Exception: return []


def stopped():
    """{feature: {values}} the data has paused (verdict "pause", or the old "stop", in analytics/drivers.csv): left out
    for 14 days, then retested (drivers.py)."""
    out = {}
    for r in driver_rows():
        if r.get("verdict") in PAUSED: out.setdefault(r.get("feature"), set()).add(r.get("value"))
    return out


def boosts(feature="category"):
    """How far the data moves a pack up (or down) the list for one feature (its category, or where the topic came from,
    analytics/drivers.csv): "push" 2 places up, an early sign 1; below typical the same way down ("cut back" 2); a choice
    back from a pause ("retest") 2 down, so it comes back on a small share."""
    out = {}
    for r in driver_rows():
        if r.get("feature") != feature: continue
        try: lift = float(r.get("lift") or 0)
        except ValueError: continue
        v = r.get("verdict")
        if v == "push" and lift > 1: out[r.get("value")] = 2
        elif v in PAUSED: out[r.get("value")] = STOP           # a week on, little to no views: left out for 14 days
        elif v in ("cut back", "retest"): out[r.get("value")] = -2
        elif v == "early sign": out[r.get("value")] = 1 if lift > 1.15 else -1 if lift < 0.85 else 0
    return out


def category_shares():
    """Each category's share of the day's Shorts from the data (drivers.category_mix over analytics/drivers.csv: lift
    squared, every category at least 5% and none over 35%; a paused one none, one being retested 5%). Until 24 October
    the floor was 4% and there was no cap: Music 33%, Film 32%, Sport 20% and 0.6 Shorts a day for each of the rest.
    Empty without data."""
    import drivers
    return drivers.category_mix(driver_rows())


EXPLORE = 0.08       # a category with no measured Shorts yet gets about 1 place in 12 until the data speaks
EXPLORE_SHARE = 0.2  # at least 1 Short in 5 each day is an exploration Short (24 October guardrail, explore_due)
WRITER_CAP, WRITER_PROVEN = 0.35, 20      # no writer model over 35% of the day's boards until it has 20 measured Shorts (data report item 7)
DAY = {"boards": [], "target": 0}         # the target day's boards so far (earlier runs and this one), set by main()


def day_boards(day):
    """The target day's boards so far, from every folder, without the reserve and dry runs."""
    out = []
    for d in ("queue", "ready", "done", "failed"):
        for f in (ROOT / "boards" / d).glob("QD-*.json"):
            b = board(f)
            if b.get("created") == str(day) and not b.get("reserve") and b.get("mode") != "dry": out.append(b)
    return out


def explore_due(boards=None):
    """True while fewer than 1 in 5 of the day's Shorts are exploration Shorts (test "explore": "yes"). An exploration
    Short takes a category drawn evenly from the day's packs, and draws every test arm, look and posting band evenly,
    cut-back choices included and paused ones not, so the data keeps measuring what the recipe has turned away from
    (Charlie, 24 October: an "improvement" must not quietly narrow the channel). analytics compares them with the rest."""
    boards = DAY["boards"] if boards is None else boards
    n, e = len(boards), sum(1 for b in boards if (b.get("test") or {}).get("explore") == "yes")
    return e < EXPLORE_SHARE * (n + 1)


def explore_pick(rest, n):
    """The pack for exploration Short number n: a category drawn evenly from the packs still open (`rest`, best first),
    whatever the recipe's shares, then that category's best pack. None without packs."""
    cats = sorted({q.get("category") for q in rest if q.get("category")})
    if not cats: return None
    cat = random.Random(f"explore-category:{n}").choice(cats)
    return next(q for q in rest if q.get("category") == cat)


def floor_needs(boards=None, target=None):
    """The categories under their floor for the day: at least 1 Short each, or 7% of the day's number when it is 15 or
    more. Paused categories have no floor."""
    boards = DAY["boards"] if boards is None else boards
    target = DAY["target"] if target is None else target
    floor = max(1, round(0.07 * target)) if target >= 15 else 1
    got = {}
    for b in boards: got[b.get("category")] = got.get(b.get("category"), 0) + 1
    paused = stopped().get("category", set())
    return {c for c in CATS if got.get(c, 0) < floor and c not in paused}


def explore_format(k, avoid=""):
    """A format drawn evenly for an exploration Short (paused formats, and the day's last format, left out), as a note
    for its prompt."""
    try: ids = [x["id"] for x in json.loads((ROOT / "templates" / "formats.json").read_text()).get("formats", []) if not x.get("retired")]
    except Exception: return ""
    ids = [i for i in ids if i not in stopped().get("format", set()) and i != avoid] or ids
    if not ids: return ""
    f = random.Random(f"explore-format:{k}").choice(ids)
    return (f"EXPLORATION SHORT (1 in 5 a day, so the data keeps measuring every option): use the {f} format if the pack "
            "suits it at all, whatever the recipe says.")


def over_share(cat, written, cap, shares):
    """True when the day's run already has its category's share of places (rounded up; no data: never)."""
    if not shares or cap <= 0: return False
    share = shares.get(cat, EXPLORE)            # a category with no data yet (a new market) explores at a fixed share
    return sum(1 for b in written if b.get("category") == cat) >= max(1, -(-share * cap // 1))


FRANCHISE = {"Music": "Song Secrets", "Film": "Film Facts", "Sport": "Sport Shocks", "Gaming": "Game Facts",
             "Tech": "Tech Truths", "Science": "Space Facts", "Entertainment": "Star Stories", "Animals": "Animal Facts",
             "Food": "Food Facts", "Cars": "Car Facts", "History": "History Bites"}


def franchise_count(name, written=()):
    """How many Shorts of a named series exist (every board folder, and this run's), so the next gets the next number."""
    n = sum(1 for b in written if str(b.get("franchise", "")).startswith(name + " #"))
    for d in ("queue", "ready", "done", "failed", "reserve"):
        for f in (ROOT / "boards" / d).glob("QD-*.json"):
            b = board(f)
            if str(b.get("franchise", "")).startswith(name + " #") and b.get("mode") != "dry": n += 1
    return n


def source_of(signal):
    """Where a topic came from, from its pack's trend signal, so the data can learn which sources find winners."""
    s = str(signal or "").lower()
    # the free sources added on 24 October (trend_sources.py) come before the families their signals also name ("On this
    # day ... (Wikipedia)", "Apple albums"), and Apple Music before "music" (its chart topics were labelled YouTube music)
    for key, name in (("watchlist", "Watchlist"), ("request", "Requests"), ("trending:", "Trend-tied"), ("follow-up", "Follow-up"), ("evergreen", "Evergreen"),
                      ("on this day", "On this day"), ("in the news", "Wikipedia In the news"), ("tvmaze", "TVmaze"), ("steam", "Steam"),
                      ("app store", "App Store"), ("apple albums", "Apple albums"), ("bluesky", "Bluesky"), ("formula 1", "Formula 1"), ("apify", "Apify"),
                      ("apple", "Apple Music"), ("music", "YouTube music"), ("youtube", "YouTube"),
                      ("wikipedia", "Wikipedia"), ("google trends", "Google Trends"), ("launch", "Rocket launches"),
                      ("rocket", "Rocket launches"), ("football", "Football"), ("fixture", "Football"),
                      ("chart", "Apple Music"), ("news", "News")):
        if key in s: return name
    return "Other"


def hot():
    """Our breakouts (analytics/breakouts.csv: the top fifth at 3 hours, or 2x the usual views for their age) in their first
    3 days, strongest first, with no follow-up yet: a fresh pack on the same subject is written first, as a follow-up.
    Guards (24 October, the data report's act-at-3-hours): no third follow-up on one subject (a breakout that is itself a
    follow-up of a follow-up is left), nothing in a paused category or from a paused topic source (drivers.py), and never
    a dead Short (drivers.dead)."""
    p = ROOT / "analytics" / "breakouts.csv"
    if not p.exists(): return []
    # a dry-run board never goes out, so it is no follow-up (24 October: the dry test's follow-up of QD-135, a 31x
    # breakout, sat in boards/ready and stopped the real one)
    boards = {b.get("id"): b for b in map(board, (ROOT / "boards").glob("*/QD-*.json")) if b.get("mode") != "dry"}
    done = {b.get("follows") for b in boards.values()}
    paused = stopped()
    try:
        import drivers
        sp = ROOT / "analytics" / "shorts.csv"
        dead = {r.get("short") for r in drivers.dead(list(csv.DictReader(sp.open())) if sp.exists() else [])}
    except Exception: dead = set()
    rows = []
    times = float(CFG.get("breakout_times", 2))
    for r in csv.DictReader(p.open()):
        try: x, h = float(r.get("times_typical") or 0), float(r.get("hours_public") or 999)
        except ValueError: continue
        if x < times or h > 72 or r.get("short") in done or r.get("short") in dead: continue
        own = boards.get(r.get("short")) or {}
        if own.get("follows") and (boards.get(own["follows"]) or {}).get("follows"):
            print(f"follow-up: {r.get('short')} is already the second follow-up on its subject"); continue
        if r.get("category") in paused.get("category", set()) or own.get("source") in paused.get("source", set()):
            print(f"follow-up: {r.get('short')}: its category or source is paused"); continue
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
    done = {b.get("remakes") for b in map(board, (ROOT / "boards").glob("*/QD-*.json")) if b.get("mode") != "dry"}
    import drivers
    allrows = list(csv.DictReader(p.open()))
    dead_ids = {r.get("short") for r in drivers.dead(allrows)}
    rows = []
    for r in allrows:
        try:
            x = float(r.get("views_vs_typical") or "")
            age = (NOW - dt.datetime.fromisoformat(r["posted"])).total_seconds() / 3600 if r.get("posted") else 0
        except ValueError: continue
        if x >= 0.5 or age < 48 or age > 14 * 24 or r.get("short") in done or not r.get("short"): continue
        if r.get("short") in dead_ids: continue                   # a week on with little to no views: not posted about again
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
from one English Wikipedia article. Relatable first: subjects most people in the UK and US know from their own lives
(the biggest games, films, songs, shows, teams and gadgets), angles an ordinary person feels ("the thing everyone got
wrong", "what you never noticed", "why it is still everywhere"), never business history, licensing deals or lore only
fans know; give each idea "appeal": 1 to 5 (5: nearly everyone knows and cares) and offer only 4s and 5s.
Never politics, crime, health, money, adult themes, deaths or a person under 18.
{trending}Nothing on these recent Shorts: {recent}.
Return {{"items": [{{"kind": "question, top list or true story", "idea": "the question, list or story in a few words",
"category": "Gaming, Film, Music, Sport, Tech, Science, Entertainment, Animals, Food, Cars or History", "wikipedia": "the exact article title",
"appeal": 5, "trending": "the trending subject it rides, or empty"}}]}}"""
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
  character, at most 40 words}}]. The article's tables come as lines like "1 | Minecraft | 300,000,000 | Multi-platform":
  for a ranking or a figure, quote that whole line.
Leave out opinions, rumours, and anything about politics, crime, health or money advice.
"what_is_new": "". "hooks": up to 3 openings of 12 words or fewer, each built only on facts above.
Reply as JSON: {{"what_is_new": "", "hooks": ["..."], "facts": [{{"claim": "...", "evidence": [{{"source": 1, "quote": "..."}}]}}]}}

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
                  "the question people type, with the searchable name early, but never open with a question: the first line "
                  "is the answer's most surprising fact, said plainly. Its facts come from one encyclopedia article: "
                  "state them plainly and never name the source.")
COUNTDOWN_NOTE = ("COUNTDOWN: count down the ranked list in the pack, from the lowest entry it gives (number 10, or as many as "
                  "there are) to number 1, one or two entries a beat, each with its figure; tease number 1 in the hook, as a "
                  "plain statement of its figure, without "
                  "naming it and save it for the last beat. Use the \"countdown\" format and at most one bars graphic, for the "
                  "top three. Title it as people search the list (\"Top 10 best-selling games ever\"). Its facts come from one "
                  "encyclopedia article: state them plainly and never name the source.")
STORY_NOTE = ("TRUE STORY: open on how it ended, naming who (\"The Beatles recorded their entire debut album in just twelve "
              "hours.\"), never on a date or the set-up; then tell it in order: the set-up, what happened, the turn and "
              "how it ended. Use the \"story\" format. Real photos of the people and places in every beat (commons-search with "
              "full names), never stock for people. Title it as the story (\"The day ...\", \"How ...\"). Its facts come from one "
              "encyclopedia article: state them plainly and never name the source.")
FICTION_NOTE = ("FICTION: this Short is an ORIGINAL short story (the topic is its premise), not news and not about real people, so "
                "the facts rule and the real pictures rule don't apply. Tell it in the \"story\" format with a twist ending, 90 to "
                "120 words, family-friendly. The title says it is a story (\"... | a short story\" at the end, before the emoji if it has one) and the "
                "summary starts \"An original short story.\" Every beat's shots are game footage: write each src as \"gameplay:\" plus 2 to 4 words of "
                "satisfying, game-like motion (our own gameplay recordings play when we have them, otherwise stock video of those "
                "words), the same kind all the way through (\"gameplay:parkour rooftop run\", \"gameplay:racing track onboard\", "
                "\"gameplay:marble run\", \"gameplay:skateboard street ride\"), and \"background\" searches the same kind in plain "
                "words (no prefix). "
                "Copy meta.sources and meta.facts from the pack exactly.")
FICTION_PLAN = """You write premises for original, family-friendly short stories told in 30 seconds on YouTube Shorts:
gripping, a little eerie or funny, with a twist ending, set in worlds our viewers love (games, films, music, sport, space,
the internet). No real people, brands or crimes, nothing too scary for children. Not like these recent ones: {recent}.
Return {{"premise": "one sentence", "category": "Gaming, Film, Music, Sport, Tech, Science, Entertainment, Animals, Food, Cars or History"}}"""
PART_FIRST = ("SERIES: this is Part 1 of {of}. Cover the first part only (for a countdown, the lowest entries of the list; for "
              "a story, up to the first turning point; for news, what happened first) and end on a cliffhanger line that makes "
              "viewers want Part 2, such as \"Number 1 is in Part 2\" or \"What happened next is in Part 2\". End the title "
              "with \"(Part 1)\", before the emoji if it has one.")
PART_MID = ("SERIES: this is Part {n} of {of}, following our Short \"{title}\", whose narration was: {said} Open with a five-word "
            "recap that makes sense on its own, carry on (the middle of the list, or what happened next) without repeating "
            "earlier parts, and end on a cliffhanger for Part {next}. End the title with \"(Part {n})\", before the emoji if it has one.")
PART_LAST = ("SERIES: this is Part {n} of {of}, following our Short \"{title}\", whose narration was: {said} Open with a five-word "
             "recap that makes sense on its own, then finish it (the top of the list, or what happened next) and land the "
             "payoff. Don't repeat the earlier parts. End the title with \"(Part {n})\", before the emoji if it has one.")
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
    cats = [c for c in sorted(CATS, key=lambda c: -up.get(c, 0)) if up.get(c, 0) > STOP] or list(CATS)
    recent = "; ".join(t for t, _, _ in seen[-60:])[:1500]
    want = {k: kinds.count(k) for k in set(kinds)}
    names = {"evergreen": "question", "top list": "top list", "true story": "true story"}
    ask = ", ".join(f'{v} "{names[k]}"' for k, v in want.items())
    subjects = [re.sub(r"\s+", " ", str(t)).strip()[:60] for t in trending if str(t).strip()][:12]
    tr = TRENDING_ASK.format(subjects="; ".join(subjects), n=max(1, round(trend_share() * len(kinds)))) if subjects else ""
    terms = search_terms()
    if terms: tr += SEARCH_ASK.format(terms="; ".join(terms))
    sh = category_shares()
    named = ", ".join(f"{c} (about {round(100 * sh[c])}% of the ideas)" if c in sh else c for c in cats)
    ans, _ = factpack.gemini(EVERGREEN_PLAN.format(n=len(kinds) + 2, kinds=ask, cats=named, recent=recent, trending=tr), None,
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
            got, _, single, _ = factpack.facts_from(EVERGREEN_FACTS.format(q=q, how=HOW[kind], title=title, url=url, text=txt),
                                                    {1: factpack.norm(txt)}, {1: "wikipedia"}, want=MIN_FACTS[kind])
        except Exception as e:
            print("evergreen:", title, str(e)[:120]); continue
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
    "hook_type": {"statement": "Open with a plain statement of the news, naming the best-known person, band or team first (the game or title when there is none).",
                  "question": "Open with a question (ending in a question mark) that the Short then answers.",
                  "number": "Open with the most surprising number in the facts, then the best-known name by the fourth word (\"16 times: Rod Stewart owned MTV's first day\").",
                  "superlative": "Open with a first, biggest, only or record detail from the facts.",
                  "twist": "Open with a twist: what people would expect, then the surprising truth."},
    "length": {"under 25 s": "Keep it short: 60 to 72 words in total.",
               "25 to 34 s": "Keep it tight: 78 to 95 words in total.",
               "35 to 44 s": "Take a little longer: 105 to 120 words in total.",
               "about 60 s": "A full minute: 150 to 180 words over 10 to 14 beats. Every beat lands a new surprise or turn, the "
                             "wildest fact comes last, and the hook promises it ('the last one changes everything').",
               "about 2 min": "Two minutes: 280 to 340 words over 18 to 26 beats. Escalate: each beat tops the last, a fresh "
                              "twist every 10 seconds, a running count or countdown so viewers stay, the wildest fact last, "
                              "and a reason to keep watching said out loud at the hook and at the halfway point."},
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
    # a named recurring series per category ("Song Secrets #12: ..."), to turn viewers into subscribers (Charlie,
    # 23 October: subscribers are the Partner Programme blocker, 9 from 19,500 views); the title prefix is added in emit()
    "franchise": {"named": "", "plain": ""},
    # factors that act after the writing (24 October, data report item 4): the camera energy (looks.choose honours the arm)
    # and the quarter of the UK day the Short goes out (plan.py's slot picker); no prompt text, the arm rides on the
    # board's test field and analytics records what was actually used (look_energy, fx_slot_used)
    "fx_energy": {"steady": "", "lab-energy-1019": ""},   # the two active looks: punchy is retired (Charlie, 19 October: neat, minimal Shorts), calm by the data (23 October)
    "fx_slot": {"06:00 to 12:00": "", "12:00 to 18:00": ""},
}
FX = ("fx_energy", "fx_slot")       # never drawn for an exploration Short, whose look and hour are drawn evenly (plan.py, looks.py)
LONG_NEEDS = {"about 60 s": 9, "about 2 min": 16}      # facts a pack must hold for a long arm (never padding, never invention)
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


def arms(t):
    """The arms of a test still worth making: a "stop" arm (drivers.py) is left out for good."""
    return [a for a in TESTS[t] if a not in stopped().get(t, ())] or list(TESTS[t])


def test_round(today=None):
    """The factorial round in force (config "test_round"): {name, start, factors: {test: [two arms]}, per_arm}, or {}
    before its start. Every Short in the round gets an arm of EVERY factor, each drawn 50/50 on its own (data report,
    24 October: one test in turn gave each arm well under a Short a day, so nothing settled; four independent 50/50
    factors give each arm about 7 a day at 15 Shorts, and a 2x difference shows at about 70 Shorts an arm)."""
    r = CFG.get("test_round") or {}
    today = today or NOW.astimezone(UK).date()
    try:
        if not r.get("factors") or today < dt.date.fromisoformat(str(r.get("start"))): return {}
    except ValueError: return {}
    return {**r, "factors": {f: [a for a in arms_ if a in TESTS.get(f, {})] for f, arms_ in r["factors"].items() if f in TESTS}}


def test_plan(k, kind="news", explore=False, today=None):
    """The style for Short number k: every winner the data has found; the factorial round's factors (test_round), each
    drawn 50/50 on its own for this Short (a winner's factor still challenged on every RETEST-th Short); one other open
    test in turn; and the comment-replies test on alternate Shorts. An exploration Short (explore_due) draws every
    test's arm evenly instead, cut-back arms included, paused ones not, so a verdict can always be overturned. Returns
    (the note for the prompt, {test: arm} recorded on the board for analytics, with "explore" and the round's name)."""
    dims = [t for t in TESTS if t not in NOT_FOR.get(kind, ())]
    if explore:
        rng = random.Random(f"explore-arms:{k}")
        picks = {t: rng.choice(arms(t)) for t in dims if t not in FX}
        picks.update(replies=rng.choice(["on", "off"]), explore="yes")
        return style_note(picks), picks
    won = {t: a for t, a in winners().items() if t in dims}
    rnd = test_round(today)
    factors = {f: [a for a in arms_ if a in arms(f)] for f, arms_ in (rnd.get("factors") or {}).items() if f in dims}
    factors = {f: a for f, a in factors.items() if len(a) >= 2}
    picks = dict(won)
    for f, options in factors.items():               # the round: every factor, 50/50, independent of the others
        if f in won and k % RETEST: continue          # a settled factor keeps its winner, challenged 1 Short in RETEST
        picks[f] = random.Random(f"{rnd.get('name', 'round')}:{f}:{k}").choice(options)
    still = [t for t in dims if t not in won and t not in factors]
    others = [t for t in won if t not in factors]
    if others and k % RETEST == 0:
        t = others[(k // RETEST) % len(others)]
        rivals = [a for a in arms(t) if a != won[t]]
        if rivals: picks[t] = rivals[(k // (RETEST * len(others))) % len(rivals)]
    elif still:
        t = still[k % len(still)]
        options = arms(t)
        picks[t] = options[(k // len(still)) % len(options)]
    picks["replies"] = "on" if k % 2 == 0 else "off"
    picks["explore"] = "no"
    if factors: picks["round"] = rnd.get("name", "round")
    return style_note(picks), picks


# The title emoji (24 October): all 7 vidIQ outlier explainers from small channels carry no emoji, all of ours one, so every
# Short takes an arm, 50/50 by its number and independent of the replies test (which follows k % 2), until drivers.csv
# gives one arm a clear "push" (feature "title_emoji", read from the live title); then that arm, with every RETEST-th Short
# still trying the other so new data can overturn it. Recorded on the board's test field; shape() and validate.py hold it.
# The title answer (content review, 24 October): our own data has 7 of the best 8 titles stating the news and our 5
# held-back titles at a median of 0.12x, while the vidIQ outliers from other channels all hold the answer back. So every
# news Short takes an arm, 50/50 by (k // 4) % 2, independent of the replies (k % 2) and emoji ((k // 2) % 2) tests, and
# drivers.csv decides ("title_answer", as assigned). Evergreen, top list, true story and fiction keep their own title forms.
TITLE_TESTS = {"title_emoji": {"emoji": "Title emoji: end meta.title and meta.alt_title with exactly one emoji that fits the payoff.",
                               "none": "Title emoji: none. No emoji anywhere in meta.title or meta.alt_title."},
               "title_answer": {"stated": "Title answer: after the searched name, say the news the first line says (\"Tate McRae hits number one in Australia\").",
                                "held back": "Title answer: after the searched name, hold the answer back (\"LISA's Tarantino video: the detail you missed\")."}}
TITLE_BITS = {"title_emoji": 2, "title_answer": 4}           # the arm is (k // bit) % 2 until a winner
TITLE_NOT_FOR = {"title_answer": {"evergreen", "top list", "true story", "fiction"}}


def title_arm(k, test="title_emoji"):
    won = None
    try:
        for r in csv.DictReader((ROOT / "analytics" / "drivers.csv").open()):
            if r.get("feature") == test and r.get("verdict") == "push" and float(r.get("lift") or 0) > 1:
                won = r.get("value"); break
    except Exception: pass
    arms_ = list(TITLE_TESTS[test])
    if won in arms_: return won if k % RETEST else next(a for a in arms_ if a != won)
    return arms_[(k // TITLE_BITS.get(test, 2)) % 2]


def with_title_test(tests, k, kind="news"):
    """The tests with this Short's title arms added (each kept when the board already has one, as series parts do)."""
    for t in TITLE_TESTS:
        if not tests.get(t) and kind not in TITLE_NOT_FOR.get(t, ()): tests = {**tests, t: title_arm(k, t)}
    return tests


def style_note(picks):
    note = " ".join(src[t][a] for t, a in picks.items() for src in (TESTS, TITLE_TESTS) if t in src and src[t].get(a))
    return f"STYLE FOR THIS SHORT: {note}" if note else ""


TRANSLATE = """Translate this YouTube Short's title and summary for viewers searching in Spanish ("es", Spain), Portuguese
("pt", Brazil) and Hindi ("hi"). Keep the names of people, games, films, shows, teams and songs as they are, keep numbers
and the emoji at the end of the title when it has one, keep titles under 50 characters, and use no dashes and no < or > characters.
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
    none, so it keeps being measured); none while paused, 1 while it is retested after a pause."""
    if kind in stopped().get("kind", ()): return 0        # a week on, little to no views: left out for 14 days
    if any(r.get("feature") == "kind" and r.get("value") == kind and r.get("verdict") == "retest" for r in driver_rows()): return 1
    lift = lift_of("kind", kind)
    return base if lift is None else max(1, min(top, round(base * min(2.0, max(0.5, lift)))))


def dropoff_notes():
    """Where viewers swipe away (analytics/dropoff.json from dropoff.py): guidance once enough Shorts are measured, which
    changes as the data does."""
    try: return json.loads((ROOT / "analytics" / "dropoff.json").read_text()).get("guidance") or []
    except Exception: return []


def shape(b, picks):
    """Makes the board follow its first-frame test and its title emoji arm (a "none" title loses any emoji it came with)."""
    if picks.get("title_emoji") == "none":
        m = b.get("meta") or {}
        for k in ("title", "alt_title"):
            if m.get(k): m[k] = re.sub(r"\s{2,}", " ", validate.EMOJI.sub("", str(m[k])).replace("️", "").replace("‍", "")).strip()
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


def writer_capped(m, stats=None):
    """No model over 35% of the day's boards (counted by the model that actually wrote them) until it has WRITER_PROVEN
    measured Shorts (24 October: one model wrote 41% of the day's boards on the strength of 2 measured Shorts)."""
    if stats is None:
        try: stats = json.loads((ROOT / "analytics" / "models.json").read_text()).get("writers") or {}
        except Exception: stats = {}
    counts = {}
    for b in DAY["boards"]: counts[b.get("writer")] = counts.get(b.get("writer"), 0) + 1
    total = sum(counts.values())
    if total < 3 or int((stats.get(m) or {}).get("n") or 0) >= WRITER_PROVEN: return False
    return (counts.get(writer_name(m), 0) + 1) / (total + 1) > WRITER_CAP


def choose_writer(sid):
    """The first-choice model for one board, by Thompson sampling over the writers that still have quota, scored by
    analytics/models.json (each Short against Shorts posted around the same time). The prior is the writing order
    (factpack.writing_order: the strongest writers first), so an untested big model starts ahead of a small one and the
    data takes over as Shorts are measured. Never Gemini Lite, the runner's model or Claude (Claude has its own arm).
    None: the chain's own order."""
    try: stats = json.loads((ROOT / "analytics" / "models.json").read_text()).get("writers") or {}
    except Exception: stats = {}
    spent, slow = factpack.STATE.get("spent_models") or set(), factpack.STATE.get("slow_models") or {}
    try: order = factpack.writing_order()
    except Exception: order = []
    cands = [m for m in order if m.split(":", 1)[-1] not in spent and m not in spent and slow.get(m.split(":", 1)[-1], 0) < 2
             and slow.get(m, 0) < 2 and not m.startswith(("claude:", "local:")) and "lite" not in m]
    cands = [m for m in cands if not writer_capped(m, stats)]
    if len(cands) < 2: return cands[0] if cands else None
    rng, best, top = random.Random(f"writer:{sid}"), None, -1e9
    for i, m in enumerate(cands):
        s = stats.get(m) or {}
        n = int(s.get("n") or 0) if s.get("score") is not None else 0
        prior = max(0.95, 1.12 - 0.02 * i)             # the writing order, until the data says otherwise
        mean = (n * float(s.get("score") or 1.0) + 3 * prior) / (n + 3)
        v = rng.gauss(mean, 0.35 / math.sqrt(n + 1))
        if v > top: best, top = m, v
    return best


# Claude, capped: an editor on free models' boards and a test arm writing 1 board in 4 (Charlie, 23 October). Counted per
# UK day in status/claude_usage.json; both shares fall back by themselves when Claude's Shorts don't earn more views.
# 24 October: Charlie's allowance comes first, so 4 edits a day on a random 3 in 10 passing boards (claude_edit_share) and
# no test-arm boards (claude_writes_per_day 0); edited boards keep "editor": "claude", so the editor test still measures.
EDIT = """You are the editor of a family-friendly UK YouTube Shorts channel. A writer's board follows (JSON). Make it more
gripping for an ordinary viewer scrolling past: a sharper hook (first line, the best-known name in its first four
words), a title that makes people tap, a punchier last line, and a pinned comment that invites replies. Rewrite only
these five, nothing else:
- title and alt_title (a different angle on the same Short): each under 50 characters, the exact name people search
  first, then {title_way}, never a question, no clickbait lies, {emoji},
- comment (one question viewers want to answer),
- first (beat 1's narration) and last (the last beat's narration): keep every fact, name and number they hold, use the
  same number of words as first_words and last_words say (two more or fewer at most: count them), keep the first line's
  form (a statement stays a statement, a question stays a question, a number hook still opens on its number: the board
  may be testing it), put the best-known person, band or team within the first four words of the first line (a co-star,
  an outlet or a date never comes first) and then the result (what just changed, or how it ended), never open it on
  "Did you know" or a date, and never add a claim the board doesn't make.
UK English, no dashes of any kind, no emoji in the narration. Reply with JSON only:
{"title": "...", "alt_title": "...", "comment": "...", "first": "...", "last": "..."}"""


def usage():
    return factpack.claude_usage()


def used(what):
    factpack.claude_note(what)


def claude_label():
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip(): return None
    label = "claude:" + CFG.get("claude_model", "sonnet")
    return None if label in (factpack.STATE.get("spent_models") or set()) else label


def claude_shares():
    """(write share, edit share): 1 in 4 boards written by Claude and every passing board edited, until 5 measured Shorts
    each; then scaled by views against the rest (views_vs_typical in analytics/models.json), squared, so a Claude choice
    that doesn't earn more views fades out by itself."""
    try: m = json.loads((ROOT / "analytics" / "models.json").read_text())
    except Exception: m = {}
    def ratio(mine, rest):
        if int(mine.get("n") or 0) < 5 or not mine.get("views_vs_typical") or not rest.get("views_vs_typical"): return None
        return float(mine["views_vs_typical"]) / max(0.05, float(rest["views_vs_typical"]))
    ws = m.get("writers") or {}
    cl = [w for k, w in ws.items() if k.startswith("claude:") and w.get("views_vs_typical")]
    others = [float(w["views_vs_typical"]) for k, w in ws.items() if not k.startswith("claude:") and w.get("views_vs_typical")]
    mine = {"n": sum(int(w.get("n") or 0) for w in cl), "views_vs_typical": max([float(w["views_vs_typical"]) for w in cl] or [0])}
    rw = ratio(mine, {"views_vs_typical": sorted(others)[len(others) // 2] if others else 0})
    ed = m.get("editors") or {}
    re_ = ratio(ed.get("claude") or {}, ed.get("none") or {})
    write = 0.25 if rw is None else min(0.5, max(0.03, 0.25 * rw * rw))
    edit = 1.0 if re_ is None else min(1.0, max(0.05, re_ * re_))
    return write, edit


def claude_arm(sid):
    """"claude:<model>" when this board is one of Claude's test-arm boards and today's cap has room, else None."""
    label = claude_label()
    if not label or usage()["writes"] >= int(CFG.get("claude_writes_per_day", 8)): return None
    return label if random.Random(f"claude-write:{sid}").random() < claude_shares()[0] else None


def words(t): return len(str(t or "").split())


def numbers(t): return sorted(re.findall(r"\d+", factpack.digits(str(t or ""))))


def claude_edit(b, p, kind, note):
    """Claude rewrites the title, alternative title, pinned comment, first and last lines of a free model's passing board;
    the board is validated and fact-checked again and the original kept if anything fails. Returns (board, note)."""
    label = claude_label()
    if (not label or str(b.get("writer", "")).startswith("claude:") or not b.get("beats")
            or usage()["edits"] >= int(CFG.get("claude_edits_per_day", 24))
            or random.Random(f"claude-edit:{b.get('id')}").random() >= min(claude_shares()[1], float(CFG.get("claude_edit_share", 1.0)))):
        return b, note      # claude_edit_share (24 October: 0.3): the day's few edits spread over every run, not the first boards
    m, beats = b.get("meta") or {}, b["beats"]
    show = {"title": m.get("title", ""), "alt_title": m.get("alt_title", ""), "comment": m.get("comment", ""),
            "lines": [x.get("say", "") for x in beats], "facts": m.get("facts") or [],
            "first_words": words(beats[0].get("say")), "last_words": words(beats[-1].get("say"))}
    used("edits")
    emoji = {"none": "with no emoji at all"}.get((b.get("test") or {}).get("title_emoji"), "each ending with exactly one emoji")
    way = {"stated": "the news the first line says (\"Tate McRae hits number one in Australia\")"}.get(
        (b.get("test") or {}).get("title_answer"), "the detail promised but held back (\"LISA's Tarantino video: the detail you missed\")")
    ans, why = factpack.claude_call(label, EDIT.replace("{emoji}", emoji).replace("{title_way}", way)
                                    + "\n\nTHE BOARD\n" + json.dumps(show, ensure_ascii=False), 150)
    if not isinstance(ans, dict): return b, note + f", editor: no answer ({str(why)[:60]})"
    new = json.loads(json.dumps(b))
    nm = new["meta"]
    for k in ("title", "alt_title", "comment"):
        if str(ans.get(k) or "").strip(): nm[k] = str(ans[k]).strip()
    first, last = str(ans.get("first") or "").strip(), str(ans.get("last") or "").strip()
    bad, skipped = [], []
    for i, t in ((0, first), (len(beats) - 1, last)):
        if not t: continue
        old = beats[i].get("say", "")
        if abs(words(t) - words(old)) > 2 or any(n not in numbers(t) for n in numbers(old)) or re.search("[\u2013\u2014]", t):
            skipped.append(f"beat {i + 1}"); continue      # that line stays as written, the rest of the edit still counts
        new["beats"][i]["say"] = t
    if re.search("[\u2013\u2014]", json.dumps([nm.get(k) for k in ("title", "alt_title", "comment")], ensure_ascii=False)):
        bad.append("a dash")
    if not bad:
        errs, warns = validate.check(new)
        _, old_warns = validate.check(b)
        bad = errs + (["more warnings"] if len(warns) > len(old_warns) else [])
    if not bad and kind != "fiction": bad = fact_check(new, p)
    if bad: return b, note + f", editor: kept the original ({'; '.join(bad)[:120]})"
    new["editor"] = "claude"
    return new, note + ", edited by Claude" + (f" ({', '.join(skipped)} kept as written)" if skipped else "")


def write_one(p, sid, day, prompt_head, extra="", kind="news", tests=None):
    """One board, then (when it passed every check) Claude's edit."""
    b, note = write_board(p, sid, day, prompt_head, extra, kind, tests)
    if b and str(b.get("writer", "")).startswith("claude:"): used("writes")
    if b:
        try: b, note = claude_edit(b, p, kind, note)
        except Exception as e: note += f", editor: kept the original ({str(e)[:80]})"     # the board is never lost to the edit
    return b, note


def write_board(p, sid, day, prompt_head, extra="", kind="news", tests=None):
    prompt = prompt_head + (f"\n\n{extra}" if extra else "") + "\n\nTHE PACK\n" + pack_text(p)
    # the writer-model test (factpack.writer_test, data report item 7): the board's arm decides the first model, unless
    # Claude's own arm has it or the 35% cap says no (the arm is still recorded: an intention-to-treat comparison)
    arm, arm_model = factpack.writer_test(int(re.sub(r"\D", "", str(sid)) or 0), day if isinstance(day, dt.date) else None)
    claude = claude_arm(sid)
    test_pick = arm_model if arm_model and not claude and not writer_capped(arm_model) else None
    pick = claude or test_pick or choose_writer(sid)
    ans, model = factpack.gemini(prompt, None, timeout=150, temperature=0.6, writing=True, **({"prefer": pick} if pick else {}))
    if not isinstance(ans, dict) or ans.get("skip"): return None, f"skipped: {ans.get('skip') if isinstance(ans, dict) else 'no board'}"
    best = None             # the first board with no errors, kept in case fixing its warnings breaks it
    for attempt in range(3):
        if isinstance(ans, dict) and isinstance(ans.get("board"), dict): ans = ans["board"]     # a model that wrapped it
        b = clean(ans)
        if not isinstance(b.get("beats"), list) or not b["beats"]: b["beats"] = []
        unwiki(b)
        for k in ("tiktok", "look", "flag", "bgvideo") + BOOKKEEPING: b.pop(k, None)
        b = {"id": sid, "created": str(day), **{k: v for k, v in b.items() if k not in ("id", "created", "writer")}, "writer": writer_name(model)}
        if tests: b["test"] = dict(tests)          # the validator reads the length and title emoji arms from it
        if arm: b.setdefault("test", {}).update(writer_arm=arm, writer_arm_used=factpack.writer_arm_of(model))
        if (tests or {}).get("title_emoji") == "none": shape(b, {"title_emoji": "none"})     # an emoji the model added anyway goes
        added = BG.fill(b)        # the video behind the Short: the writer's own searches, tidied; the category's when it gave fewer than 2
        if os.environ.get("WRITE_DRY"): b["mode"] = "dry"
        errs, warns = validate.check(b)
        if errs and tests and tests.get("length") in LONG_NEEDS and all("(about" in x or x.startswith("beats:") for x in errs):
            print(f"{sid}: a normal length came back instead of {tests['length']}: kept as written")   # a Short is worth more than the arm
            tests = {**tests, "length": "as written"}; b["test"] = dict(tests)
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
        ans, model = factpack.gemini(fix, None, timeout=150, temperature=0.3, writing=True, **({"prefer": test_pick} if test_pick else {}))
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
    DAY["boards"] = day_boards(day)                # the day so far: exploration share, category floors, writer cap
    try:
        import quota
        DAY["target"] = quota.target()
    except Exception: DAY["target"] = len(DAY["boards"]) + cap
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

    def emit(p, note="", kind="news", reserve=False, fol=None, tests=None, series=None, explore=False):
        sid = f"QD-{state['n']:03d}"
        if tests is None: style, tests = test_plan(state["n"], kind, explore) if explore else test_plan(state["n"], kind)
        tests = with_title_test(tests, state["n"], kind)      # the title emoji and title answer tests ride on every Short
        facts = len(p.get("verified") or []) + len(p.get("one_source") or [])
        if tests.get("length") in LONG_NEEDS and facts < LONG_NEEDS[tests["length"]]:      # a long Short needs the facts for it
            print(f"{sid}: {tests['length']} needs {LONG_NEEDS[tests['length']]} facts, the pack has {facts}: 35 to 44 s instead")
            tests = {**tests, "length": "35 to 44 s"}
        style = style_note(tests)
        extra = [(f"Formats already used for this day, oldest first: {', '.join(used)}. Use a different format from the "
                  f"last one ({used[-1]}), and prefer the ones used least.") if used else "", style, note]
        if tests.get("explore") == "yes": extra.append(explore_format(state["n"], used[-1] if used else ""))
        try:                                       # what other channels' Shorts are winning with this week (competitors.py)
            import competitors
            wins = competitors.top_titles(p.get("category") or "")
            if wins: extra.append("WHAT IS WINNING ON SHORTS THIS WEEK IN THIS CATEGORY (other channels, by views an hour; learn "
                                  "what makes people stop and find a fresher angle, never copy their wording): " + "; ".join(wins))
        except Exception: pass
        if tests.get("title_search") == "search phrase":
            sug = suggestions(p["topic"])
            if sug: extra.append("WHAT PEOPLE TYPE INTO YOUTUBE SEARCH ABOUT THIS: " + "; ".join(sug))
        if tests.get("angles") == "shown" and state["angles"] > 0 and not breaking:
            state["angles"] -= 1
            ang = angles(p["topic"])
            if ang: extra.append("SHORTS ALREADY GETTING VIEWS ON THIS SUBJECT (learn which angle or question works, then "
                                 "find a fresher or better one; never copy their wording, footage or script): " + "; ".join(ang))
        try:
            b, why = write_one(p, sid, day, head, "\n\n".join(x for x in extra if x), kind, tests)
        except Exception as e:
            b, why = None, f"error: {e}"[:200]
        print(f"{p['topic']}: {why}")
        if not b: return None
        before = json.dumps(b)
        shape(b, tests)
        if validate.check(b)[0]: b = json.loads(before)
        b.update(kind=kind, test={**tests, **(b.get("test") or {})}, source=source_of(p.get("signal")))
        if tests.get("franchise") == "named":
            name = FRANCHISE.get(b.get("category") or p.get("category") or "", "Quickplay Facts")
            n = 1 + franchise_count(name, written)
            m = b.setdefault("meta", {})
            if not str(m.get("title", "")).startswith(name):
                m["title"] = f"{name} #{n}: {m.get('title', '')}"[:95]
            b["franchise"] = f"{name} #{n}"
        if fol: b["follows"] = fol["short"]
        if reserve: b["reserve"] = True
        if series: b["series"] = series
        tr = translations(b)
        if tr: b["meta"]["translations"] = tr
        (out / f"{sid}.json").write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")))
        written.append(b); used.append(b.get("format", "")); state["n"] += 1
        if not reserve: DAY["boards"].append(b)
        return b

    def emit_kind(p, kind, reserve=False, note="", fol=None, explore=None):
        """A Short of any kind, or two or three parts with a cliffhanger between them when its series test says so and the
        pack has 3 facts or more a part (never from the reserve, which could release them out of order, and never a
        follow-up or breaking news). `explore`: an exploration Short (None: when explore_due says so; never the reserve)."""
        if explore is None: explore = not reserve and explore_due()
        style, tests = test_plan(state["n"], kind, explore) if explore else test_plan(state["n"], kind)
        tests = with_title_test(tests, state["n"], kind)      # one arm for every part of a series
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
    rank = lambda kp: (kp[0] - (200 - 20 * {"launch": 0, "surging": 1, "build-up": 2}.get((WATCH.get(watch_of(kp[1])) or {}).get("level"), 3) if watch_of(kp[1]) else 0)
                       - up.get(kp[1].get("category"), 0) - src_up.get(source_of(kp[1].get("signal")), 0)
                       - (100 if any(covered(kp[1], [r["_about"]]) for r in follow) else 0))
    try:                                                     # the watchlist (pipeline/watch.py): its own places today
        import watch
        WATCH = {i["name"]: i for i in (watch.state().get("items") or [])}
    except Exception: WATCH = {}
    def watch_of(p):
        s = str(p.get("signal", ""))
        return next((n for n in WATCH if s.startswith(f"watchlist: {n} ")), None) if s.startswith("watchlist") else None
    def watch_done(name):
        return sum(1 for d in ("queue", "ready", "done", "failed") for f in (ROOT / "boards" / d).glob("QD-*.json")
                   if (board(f).get("watch") == name and board(f).get("created") == str(day))) + sum(1 for b in written if b.get("watch") == name)
    # one cap across the watchlist (24 October: the calendar of big dates would ask for 22 places a day in GTA 6 week, more
    # than the day's Shorts): at most watch_share_max of the day's target goes to watch items, launch items first, then
    # surging, then build-up, so the day's own news and every category keep their room
    WATCH_CAP = max(1, round(float(CFG.get("watch_share_max", 0.34)) * max(1, int(DAY.get("target") or quota.target()))))
    WATCH_RANK = {"launch": 0, "surging": 1, "build-up": 2}
    def watch_total():
        """Watch boards for the day so far, every item together (one pass over the boards)."""
        return sum(1 for d in ("queue", "ready", "done", "failed") for f in (ROOT / "boards" / d).glob("QD-*.json")
                   if board(f).get("watch") and board(f).get("created") == str(day)) + sum(1 for b in written if b.get("watch"))
    shares, later = category_shares(), []
    if shares: print("category shares:", {c: round(v, 2) for c, v in sorted(shares.items(), key=lambda x: -x[1])})
    def eligible(q):
        """A news pack that could be written now as a plain news Short (for an exploration pick)."""
        if q.get("_done") or watch_of(q): return False
        if up.get(q.get("category"), 0) <= STOP or src_up.get(source_of(q.get("signal")), 0) <= STOP: return False
        if len(q.get("verified") or []) + len(q.get("one_source") or []) < 2: return False
        if any(covered(q, [r["_about"]]) for r in follow): return False            # a follow-up is no exploration
        return not covered(q, seen + [about(b) for b in written])
    order = sorted(topics, key=rank)
    # category floors (24 October): the best pack of each category still under its floor for the day goes first, after
    # the watchlist and the breakouts, so no category drops out of measurement
    need, firsts = floor_needs(), set()
    for _, q in order:
        if q.get("category") in need and eligible(q): firsts.add(id(q)); need.discard(q.get("category"))
    if firsts:
        order = sorted(topics, key=lambda kp: rank(kp) - (150 if id(kp[1]) in firsts else 0))
        print("category floors first:", sorted({q.get("category") for _, q in order if id(q) in firsts}))
    for k, (_, p) in enumerate(order):
        if len(written) >= cap or factpack.STATE.get("spent") or late(): break
        if p.get("_done"): continue                 # written already as an exploration Short
        wn = watch_of(p)
        if wn and watch_done(wn) >= int(WATCH[wn].get("places", 1)): print(f"watchlist {wn}: today's places are filled:", p["topic"]); continue
        if wn and watch_total() >= WATCH_CAP: print(f"watchlist: the day's {WATCH_CAP} watch places are filled:", p["topic"]); continue
        if not wn and p.get("_later") is None and over_share(p.get("category"), written, cap, shares):
            p["_later"] = True; order.append((0, p)); continue     # its category has its share: only if places are left at the end
        if up.get(p.get("category"), 0) <= STOP or src_up.get(source_of(p.get("signal")), 0) <= STOP:
            print("stopped choice, skipped:", p["topic"], p.get("category")); continue
        if len(p.get("verified") or []) + len(p.get("one_source") or []) < 2:      # one fact makes a thin Short
            print("too few facts:", p["topic"]); continue
        fol = next((r for r in follow if covered(p, [r["_about"]])), None)
        if not fol and covered(p, seen + [about(b) for b in written]): print("covered already:", p["topic"]); continue
        note = (f'FOLLOW-UP: our Short "{fol.get("title")}" is getting {float(fol["times_typical"]):.0f} times our usual '
                "views. Write a follow-up on the same subject: a new angle or the next chapter from this pack, never a "
                "repeat, with a title tied to the original.") if fol else ""
        if wn:
            rules = f"WATCHLIST ({wn}, {WATCH[wn].get('level')}): {WATCH[wn].get('rules', '')}".strip()
            got = emit_kind(p, "news", note=(note + "\n\n" + rules).strip(), explore=False)
            if got: got["watch"] = wn; (out / f"{got['id']}.json").write_text(json.dumps(got, ensure_ascii=False, separators=(",", ":")))
        elif fol or breaking: got = emit(p, note, "follow-up" if fol else "breaking", fol=fol)
        elif explore_due():
            # an exploration Short: a category drawn evenly from the packs still open, its best pack; the pack this
            # place was for comes straight after
            q = explore_pick([x for _, x in order[k:] if eligible(x)], state["n"]) or p
            if q is not p: order.insert(k + 1, (0, p))
            q["_done"] = True
            print(f"exploration Short: {q.get('category')}: {q['topic']}")
            got = emit_kind(q, "news", explore=True)
        else: got = emit_kind(p, "news", explore=False)
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
                riding = [n for n, i in WATCH.items() if i.get("level") != "steady"]      # proactive: ideas that ride what is coming
                ever = evergreen_packs(pick_kinds(want), seen + [about(b) for b in written], riding + [p["topic"] for _, p in topics[:12]])
            except Exception as e:
                ever = []; print("evergreen:", str(e)[:200])
            for p in ever:
                if factpack.STATE.get("spent") or late(): break
                before = len(written)
                emit_kind(p, p.get("kind", "evergreen"), reserve=spare <= 0)
                if spare > 0: spare = max(0, spare - (len(written) - before))
    print(f"wrote {len(written)} of {cap}: " + "; ".join(f"{b['id']} {b['meta']['title']}" + (" (reserve)" if b.get("reserve") else "")
                                               for b in written))
    try: order = factpack.writing_order()[:6]
    except Exception: order = factpack.STATE.get("models", [])[:6]
    u = usage()
    u["edits"], u["writes"] = u.get("edits", 0), u.get("writes", 0)
    print("gemini:", json.dumps({"order": order, **factpack.gemini_state(), "late": late(),
                                 "claude today": f"{u['edits']} of {CFG.get('claude_edits_per_day', 24)} edits, "
                                                 f"{u['writes']} of {CFG.get('claude_writes_per_day', 8)} writes"}))


if __name__ == "__main__":
    main()
