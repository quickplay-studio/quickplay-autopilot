"""The script writer, on GitHub with Google's Gemini, so no Claude run is needed (Charlie, 19 October).

usage: python pipeline/writer.py            (write.yml runs it after each trends run; WRITE_COUNT and WRITE_DRY optional)

For the run's capacity (config runs: morning before 09:00 UTC and afternoon write for today, evening for tomorrow, never
past daily_limit), it takes the day's fact packs (trends/facts.json) in their best-first order, skips topics covered in
the last 14 days and anything Gemini would flag, and has Gemini write a board from the pack alone, shaped like a good
past board. pipeline/validate.py checks it; Gemini fixes what fails (twice at most); a board that still fails is dropped.
Boards go to boards/queue for render.yml.
"""
import csv, datetime as dt, json, os, pathlib, re, sys, urllib.parse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import factpack, validate

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


def plan(breaking=False):
    """Target day and how many to write (a breaking-news check: today, at most 2)."""
    uk = NOW.astimezone(UK)
    run = "breaking" if breaking else "morning" if NOW.hour < 9 else "afternoon" if NOW.hour < 16 else "evening"
    day = uk.date() + dt.timedelta(days=1 if run == "evening" else 0)
    made = 0
    for d in ("queue", "ready", "done", "failed"):
        for p in (ROOT / "boards" / d).glob("QD-*.json"):
            try: b = json.loads(p.read_text())
            except Exception: continue
            if b.get("created") == str(day) and not b.get("reserve"): made += 1
    limit = int(CFG.get("daily_limit", 24)) - (1 if day.weekday() == 6 else 0)
    cap = min(2 if breaking else int((CFG.get("runs") or {}).get(run, 6)), max(0, limit - made))
    if os.environ.get("WRITE_COUNT", "").strip().isdigit(): cap = int(os.environ["WRITE_COUNT"])
    return run, day, cap


def example():
    """The newest finished board closest to the rules (fewest validator warnings, least stock), as the shape to copy."""
    best, free = None, f"QD-{next_id():03d}"
    done = sorted((ROOT / "boards" / "done").glob("QD-*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0), reverse=True)
    for p in done[:20]:
        try: b = json.loads(p.read_text())
        except Exception: continue
        for k in ("id", "created", "tiktok", "look", "flag"): b.pop(k, None)
        if b.get("mode") or b.get("reserve"): continue
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


CHECK = """You check a YouTube Short script against its fact pack before it is published. For the title and each beat,
decide whether everything it states is in the pack's facts: the same meaning, with every number, date and record attached
to the same person or thing, and nothing added (no extra details, motives, quotes or loaded words such as "clashed").
Questions, the hook's framing and claims clearly marked as unconfirmed are fine. Return {"ok": true} when everything is
supported, otherwise {"ok": false, "problems": [{"beat": <number from 1, or 0 for the title>, "issue": "<what is wrong,
and what the pack says>"}]}."""


def fact_check(b, p):
    """Gemini reads the title and narration against the pack: the problems it finds (none when all is supported)."""
    beats = "\n".join(f"{k}. {x.get('say', '')}" for k, x in enumerate(b.get("beats") or [], 1))
    ans, _ = factpack.gemini(CHECK + "\n\nTHE PACK\n" + pack_text(p) + f"\n\nTHE SCRIPT\n0. {(b.get('meta') or {}).get('title', '')}\n"
                             + beats, None, timeout=100, temperature=0.0)
    if not isinstance(ans, dict) or ans.get("ok") is not False: return []
    return [f"beat {x.get('beat')}: {x.get('issue')}" for x in ans.get("problems") or [] if isinstance(x, dict)][:6]


def media_problems(b):
    """page: pictures are often refused, so at least half the beats need a shot that reliably resolves."""
    beats = b.get("beats") or []
    sure = sum(any(str(s.get("src", "")).startswith(("commons", "nasa:", "openverse:")) for s in x.get("shots") or []) for x in beats)
    if sure * 2 >= len(beats): return []
    return [f"media: only {sure} of {len(beats)} beats have a commons-search:, commons:, openverse: or nasa: shot; add "
            "commons-search shots of the people, teams, venues or events to at least half the beats (page: pictures often fail)"]


def boosts():
    """Categories the data says beat typical (analytics/drivers.csv): "push" moves their packs up 2 places, "early sign" 1."""
    p, out = ROOT / "analytics" / "drivers.csv", {}
    if not p.exists(): return out
    for r in csv.DictReader(p.open()):
        try: lift = float(r.get("lift") or 0)
        except ValueError: continue
        if r.get("feature") == "category" and lift > 1 and r.get("verdict") in ("push", "early sign"):
            out[r.get("value")] = 2 if r["verdict"] == "push" else 1
    return out


def hot():
    """Our Shorts at 3x or more the usual views for their age in their first 3 days (analytics/breakouts.csv), strongest
    first, with no follow-up yet: a fresh pack on the same subject is written first, as a follow-up."""
    p = ROOT / "analytics" / "breakouts.csv"
    if not p.exists(): return []
    done = {board(f).get("follows") for f in (ROOT / "boards").glob("*/QD-*.json")}
    rows = []
    for r in csv.DictReader(p.open()):
        try: x, h = float(r.get("times_typical") or 0), float(r.get("hours_public") or 999)
        except ValueError: continue
        if x < 3 or h > 72 or r.get("short") in done: continue
        f = next((ROOT / "boards").glob(f"*/{r.get('short')}.json"), None)
        r["_about"] = about(board(f)) if f else (r.get("title", ""), r.get("title", ""), set())
        rows.append((x, r))
    return [r for _, r in sorted(rows, key=lambda t: -t[0])]


EVERGREEN_PLAN = """You plan evergreen YouTube Shorts for Quickplay Daily (family-friendly, UK English): questions people
type into YouTube search all year, not news. Suggest {n} questions, best first, in these categories (strongest first):
{cats}. Each starts with Why, How, What, Who or Which, or asks for the first or the biggest; is about something famous (a
game, film, show, song, artist, band, team, player, record or space mission); and is answered by one English Wikipedia
article. Never politics, crime, health, money, adult themes or a person under 18. Nothing on these recent Shorts: {recent}.
Return {{"items": [{{"question": "...", "category": "Gaming, Film, Music, Sport, Tech, Science or Entertainment",
"wikipedia": "the exact article title"}}]}}"""

EVERGREEN_FACTS = """You check facts for a family-friendly Shorts channel. The Short answers a question people search on
YouTube: "{q}". Below is one encyclopedia article. Using ONLY this article, list up to 10 facts that answer the question
or make the answer more surprising: names, dates, numbers, records, firsts. For each fact:
- "claim": one plain sentence in UK English. Copy names, numbers and dates exactly as the article writes them. No dashes.
- "evidence": [{{"source": 1, "quote": the exact sentence from the article that states it, copied character for
  character, at most 40 words}}].
Leave out opinions, rumours, and anything about politics, crime, health or money advice.
"what_is_new": "". "hooks": up to 3 openings of 12 words or fewer, each built only on facts above.

[1] Wikipedia · {title} · {url}
{text}"""

EVERGREEN_NOTE = ("EVERGREEN: this Short answers the question in the topic for people searching it at any time of year. It "
                  "is not news: ignore the rule about what is new, and never say today, this week or recently. Title it as "
                  "the question people type, with the searchable name early. Its facts come from one encyclopedia article: "
                  "state them plainly and never name the source.")


def reserve_count():
    """Evergreen Shorts waiting in the reserve, or on their way there."""
    return len(list((ROOT / "boards" / "reserve").glob("QD-*.json"))) + sum(
        1 for f in (ROOT / "boards" / "queue").glob("QD-*.json") if board(f).get("reserve"))


def evergreen_packs(n, seen):
    """Up to n evergreen questions in the best categories, each as a fact pack from one Wikipedia article whose quotes
    are checked word for word (factpack.verify), like the news packs."""
    up = boosts()
    cats = sorted(CATS, key=lambda c: -up.get(c, 0))
    recent = "; ".join(t for t, _, _ in seen[-60:])[:1500]
    ans, _ = factpack.gemini(EVERGREEN_PLAN.format(n=n + 2, cats=", ".join(cats), recent=recent), None, timeout=100,
                             temperature=0.8)
    items = ans.get("items") if isinstance(ans, dict) else None
    packs = []
    for it in items or []:
        if len(packs) >= n or factpack.STATE.get("spent"): break
        q, title = str(it.get("question") or "").strip(), str(it.get("wikipedia") or "").strip()
        if not q or not title: continue
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        try:
            txt, img = factpack.page_text(url, wiki=True)
            if len(txt) < 800: continue
            got, _ = factpack.gemini(EVERGREEN_FACTS.format(q=q, title=title, url=url, text=txt), factpack.SCHEMA, timeout=100)
        except Exception as e:
            print("evergreen:", title, str(e)[:120]); continue
        _, single = factpack.verify((got or {}).get("facts"), {1: factpack.norm(txt)}, {1: "wikipedia"})
        if len(single) < 3: continue
        src = {"outlet": "Wikipedia", "title": title, "url": url, "published": "", "kind": "wikipedia"}
        p = {"topic": q, "signal": "evergreen search question", "category": it.get("category", ""), "what_is_new": "",
             "hooks": [factpack.undash(h) for h in (got or {}).get("hooks") or []][:3],
             "sources": [[title, url, "Wikipedia", ""]], "verified": [], "one_source": single,
             "images": factpack.image_ideas([(src, txt, img)])}
        if not covered(p, seen): packs.append(p)
    return packs


TESTS = {   # each Short tries one of these in turn, until the data names a winner (analytics/drivers.csv, verdict "push")
    "hook_type": {"question": "Open with a question (ending in a question mark) that the Short then answers.",
                  "number": "Open with the most surprising number in the facts.",
                  "superlative": "Open with a first, biggest, only or record detail from the facts.",
                  "twist": "Open with a twist: what people would expect, then the surprising truth."},
    "length": {"under 25 s": "Keep it short: 60 to 72 words in total.",
               "35 to 44 s": "Take a little longer: 105 to 120 words in total."},
    "follow_line": {"with follow line": "End the last beat with one short spoken line asking viewers to subscribe for one "
                                        "of these every day.",
                    "no follow line": "No subscribe or follow line."},
}


def test_plan(k):
    """The style notes for Short number k: every winner the data has found, plus one open test in turn.
    Returns (the note for the prompt, {test: arm} to record on the board)."""
    picks, p = {}, ROOT / "analytics" / "drivers.csv"
    if p.exists():
        for r in csv.DictReader(p.open()):
            try: lift = float(r.get("lift") or 0)
            except ValueError: continue
            f, v = r.get("feature"), r.get("value")
            if f in TESTS and v in TESTS[f] and r.get("verdict") == "push" and lift > 1: picks.setdefault(f, v)
    still = [t for t in TESTS if t not in picks]
    if still:
        t = still[k % len(still)]
        arms = list(TESTS[t])
        picks[t] = arms[(k // len(still)) % len(arms)]
    note = " ".join(TESTS[t][a] for t, a in picks.items())
    return (f"STYLE FOR THIS SHORT: {note}" if note else ""), picks


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
                                 temperature=0.2)
    except Exception as e:
        print("translations:", str(e)[:120]); return {}
    out = {}
    for lang in ("es", "pt", "hi"):
        t = ans.get(lang) if isinstance(ans, dict) else None
        if isinstance(t, dict) and t.get("title") and t.get("summary"):
            out[lang] = {k: re.sub(r"[<>]", "", clean(str(t[k])))[:100 if k == "title" else 1000] for k in ("title", "summary")}
    return out


def write_one(p, sid, day, prompt_head, extra=""):
    prompt = prompt_head + (f"\n\n{extra}" if extra else "") + "\n\nTHE PACK\n" + pack_text(p)
    ans, model = factpack.gemini(prompt, None, timeout=150, temperature=0.6)
    if not isinstance(ans, dict) or ans.get("skip"): return None, f"skipped: {ans.get('skip') if isinstance(ans, dict) else 'no board'}"
    best = None             # the first board with no errors, kept in case fixing its warnings breaks it
    for attempt in range(3):
        b = clean(ans)
        for k in ("tiktok", "look", "mode", "flag"): b.pop(k, None)
        b = {"id": sid, "created": str(day), **{k: v for k, v in b.items() if k not in ("id", "created")}}
        if os.environ.get("WRITE_DRY"): b["mode"] = "dry"
        errs, warns = validate.check(b)
        errs = errs + media_problems(b)
        if not errs: errs = ["facts: " + x for x in fact_check(b, p)]     # only a clean board is worth a fact check
        note = f"{model}, {len(warns)} warnings" + (f" ({'; '.join(warns)[:200]})" if warns else "")
        if not errs:
            if not warns or best: return b, note     # a warning flags the Short for a person, so it gets one fixing round
            best = (b, note)
        elif best: return best
        if attempt == 2: break
        fix = (prompt_head + "\n\nTHE PACK\n" + pack_text(p) + "\n\nYOUR BOARD\n" + json.dumps(ans, ensure_ascii=False)
               + "\n\nIt fails these checks. Fix every one and return the whole corrected board as JSON:\n- " + "\n- ".join(errs + warns))
        ans, model = factpack.gemini(fix, None, timeout=150, temperature=0.3)
        if not isinstance(ans, dict): break
    return best or (None, "still failing: " + "; ".join(errs)[:300])


def main():
    facts = factpack.OUT
    if not facts.exists(): print("no fact packs"); return
    d = json.loads(facts.read_text())
    breaking = d.get("mode") == "breaking"          # a check between the main runs: only what is spiking, at most 2
    run, day, cap = plan(breaking)
    print(f"{run} run for {day}: {cap} to write")
    if cap <= 0 and (breaking or reserve_count() >= 6): return
    seen, used, follow, up = recent(), day_formats(day), hot(), boosts()
    moods = list(CFG.get("music_moods") or [])
    head = (RULES % {"moods": moods} + "\n\nFORMATS\n" + formats() + "\n\nWHAT THE DATA SAYS WORKS\n" + recipe()
            + "\n\nEXAMPLE BOARD (shape only, a different story)\n" + example())
    out, written, state = ROOT / "boards" / "queue", [], {"n": next_id()}
    out.mkdir(parents=True, exist_ok=True)

    def emit(p, note="", reserve=False, fol=None):
        sid = f"QD-{state['n']:03d}"
        style, tests = test_plan(state["n"])
        extra = "\n\n".join(x for x in (
            (f"Formats already used for this day, oldest first: {', '.join(used)}. Use a different format from the last "
             f"one ({used[-1]}), and prefer the ones used least.") if used else "", style, note) if x)
        try:
            b, why = write_one(p, sid, day, head, extra)
        except Exception as e:
            b, why = None, f"error: {e}"[:200]
        print(f"{p['topic']}: {why}")
        if not b: return None
        if fol: b["follows"] = fol["short"]
        if reserve: b["reserve"] = True
        if tests: b["test"] = tests
        tr = translations(b)
        if tr: b["meta"]["translations"] = tr
        (out / f"{sid}.json").write_text(json.dumps(b, ensure_ascii=False, separators=(",", ":")))
        written.append(b); used.append(b.get("format", "")); state["n"] += 1
        return b

    topics = list(enumerate(d.get("topics") or []))[:4 if breaking else None]   # best first; favoured categories and breakouts move up
    rank = lambda kp: kp[0] - up.get(kp[1].get("category"), 0) - (100 if any(covered(kp[1], [r["_about"]]) for r in follow) else 0)
    for _, p in sorted(topics, key=rank):
        if len(written) >= cap or factpack.STATE.get("spent"): break
        if not p.get("verified") and not p.get("one_source"): continue
        fol = next((r for r in follow if covered(p, [r["_about"]])), None)
        if not fol and covered(p, seen + [about(b) for b in written]): print("covered already:", p["topic"]); continue
        note = (f'FOLLOW-UP: our Short "{fol.get("title")}" is getting {float(fol["times_typical"]):.0f} times our usual '
                "views. Write a follow-up on the same subject: a new angle or the next chapter from this pack, never a "
                "repeat, with a title tied to the original.") if fol else ""
        if emit(p, note, fol=fol) and fol: follow.remove(fol)
    if not breaking and not factpack.STATE.get("spent"):    # evergreen search Shorts fill spare places and stock the reserve
        spare = max(0, cap - len(written))
        want = min(3, spare + min(2, max(0, 6 - reserve_count())))
        if want:
            try:
                ever = evergreen_packs(want, seen + [about(b) for b in written])
            except Exception as e:
                ever = []; print("evergreen:", str(e)[:200])
            for p in ever:
                if factpack.STATE.get("spent"): break
                if emit(p, EVERGREEN_NOTE, reserve=spare <= 0) and spare > 0: spare -= 1
    print(f"wrote {len(written)}: " + "; ".join(f"{b['id']} {b['meta']['title']}" + (" (reserve)" if b.get("reserve") else "")
                                         for b in written))


if __name__ == "__main__":
    main()
