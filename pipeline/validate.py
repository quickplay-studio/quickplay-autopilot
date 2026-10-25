"""Check boards before they are queued. The morning session runs it before pushing; GitHub runs it again before rendering
and rejects any board with errors (it goes to boards/failed with the reasons).

usage: python pipeline/validate.py boards/queue/QD-101.json [more.json ...]     exit code 1 if any board has errors
Standard library only.
"""
import datetime as dt, json, pathlib, re, sys, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import background as BG        # the search format for the video behind a Short (standard library at import)

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATS = {"Gaming", "Film", "Music", "Sport", "Tech", "Science", "Entertainment", "Animals", "Food", "Cars", "History"}
VISUALS = {"none", "title", "stat", "cards", "quote", "date", "versus", "timeline", "bars"}
MODES = {"schedule", "private", "none", "dry"}
SRC = re.compile(r"^(commons:File:.+|commons-search:.+|pixabay:(video|image):.+|url:https://.+|page:https://.+|openverse:.+|nasa:(video|image):.+|gameplay:.*)$")
DASH = re.compile("[—–]")
# Clear signs of an excluded topic: the board is rejected.
BANNED = re.compile(r"\b(elections?|parliament\w*|politicians?|political|murder\w*|terroris\w*|porn\w*|onlyfans|nsfw|casinos?|"
                    r"gambl\w*|betting|bookmakers?|lottery|crypto\w*|bitcoin|forex|went viral|goes viral|gone viral|viral video|"
                    r"million views|billion views)\b", re.I)
# Negative framing of a real person (Charlie, 25 October: "no negative media unless it's fictional"; a Short read "Richard E
# Grant admits betrayal to Joe Lycett"): rejected unless the board's kind is fiction. The subject itself is fine (a result, a
# record, a release); what is not fine is a real person admitting, failing, feuding, being mocked, exposed or blamed.
NEGATIVE = re.compile(r"\b(betray\w*|admits?|admitted|confess\w*|slam\w*|savage[ds]?|roast\w*|mock\w*|humiliat\w*|expos\w*|"
                      r"feud\w*|backlash|scandal\w*|cheat\w*|lie[sd]?|lying|liar|axed|sacked|fired|snub\w*|accus\w*|blame[sd]?|"
                      r"rant\w*|meltdown|furious|fury|outrage\w*|controvers\w*|calls? out|hits? back|clap\w* back|"
                      r"shock exit|storm\w* off|disgrace\w*|shame\w*|embarrass\w*|flop\w*|divorce\w*|split\w* up|break ?up|breakup|"
                      r"dump\w*|bust-up|spat|trolled|booed)\b", re.I)
# The same two rules for a Spanish board (language "es", the mirror of a main Short: pipeline/mirror.py). The English patterns
# are not run on Spanish text ("exposición" would match expos\w*); these stand in for them. Accents are optional.
BANNED_ES = re.compile(r"\b(elecci[oó]n(es)?|parlament\w*|pol[ií]tic[oa]s?|asesin\w*|terroris\w*|porno\w*|onlyfans|nsfw|casinos?|"
                       r"apuest\w*|apostar|apostadores?|loter[ií]a|cripto\w*|bitcoin|forex|se hizo viral|se vuelve viral|vuelto viral|"
                       r"v[ií]deo viral|millones de visualizaciones|mil millones de visualizaciones)\b", re.I)
NEGATIVE_ES = re.compile(r"\b(traici[oó]n|traicion\w*|admite[ns]?|admiti[oó]|admitieron|confes\w*|arremet\w*|destroz\w*|humill\w*|"
                         r"burl\w*|ridiculiz\w*|expone[ns]?|expuso|expusieron|desenmascar\w*|en evidencia|pelea\w*|peleado|"
                         r"enfrentamiento\w*|ri[ñn]a|polémic\w*|polemic\w*|controvers\w*|esc[aá]ndalo\w*|"
                         r"trampa\w*|tramposo\w*|enga[ñn]\w*|mient[ea]\w*|mentir\w*|mentiros\w*|mentira\w*|despedid\w*|despide[ns]?|"
                         r"despidi[oó]|echad\w+|acus\w*|culpa\w*|culpan|rabieta\w*|enojad\w*|furios\w*|furia|indignaci\w*|"
                         r"abuche\w*|desaire\w*|trolle\w*|fracas\w*|divorci\w*|separaci[oó]n|se separa\w*|ruptura\w*|"
                         r"verg[üu]enza|vergonzos\w*|bochorn\w*|contraataca\w*|responde con dureza|desprecia\w*|critic(a|an|aron|[oó]) a)\b",
                         re.I)
SLOW_ES = re.compile(r"(descubre|aprende|as[ií] es como|hoy vamos|vamos a ver|bienvenid\w+|en este (short|v[ií]deo))\b", re.I)
# Words that are often fine but worth a second look: printed as warnings only.
WATCH = re.compile(r"\b(vote|voting|police|shooting|shot dead|killed|arrest\w*|court|cure[sd]?|vaccine\w*|president|minister|"
                   r"stocks?|shares|invest\w*|viral|views)\b", re.I)
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
US_DATE = re.compile(rf"\b({MONTHS}) \d{{1,2}}(st|nd|rd|th)?\b")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")
# a first line that opens on a date ("On 11 April 1970", "Tuesday 20 October", "In 1999", "October 1976"): the lead is the person
# and the result, not the day (content review, 24 October: the 2 date-first hooks got 0.27x the views of the rest); drivers.py
# keeps the same pattern (DATE_FIRST) so a date is never taken for the number arm
DATE_FIRST = re.compile(rf"(on |in |back in )?((monday|tuesday|wednesday|thursday|friday|saturday|sunday) )?(\d{{1,2}}(st|nd|rd|th)? )?"
                        rf"(({MONTHS.lower()})\b|(1[89]\d\d|20\d\d)\b)")


def _toks(t):
    """Lower case words, a trailing 's dropped and punctuation trimmed: "Olivia Rodrigo's new video:" -> olivia, rodrigo, new, video."""
    return [re.sub(r"['’]s$", "", x).strip(".,:;!?") for x in re.findall(r"[\w'’.&-]+", str(t).lower())]


def hook_lead(b):
    """The lead name of a board: a name it labels on screen (shots' label.t, which the prompt asks for on each person) that
    its title opens with (one of the title's first six words), or "" when there is none."""
    title = str((b.get("meta") or {}).get("title") or "")
    head = _toks(title)[:6]
    for bt in b.get("beats") or []:
        for s in (bt.get("shots") or []) if isinstance(bt, dict) else []:
            n = str(s["label"].get("t") or "") if isinstance(s, dict) and isinstance(s.get("label"), dict) else ""
            if n and any(x in head for x in _toks(n) if len(x) > 2): return n
    return ""


def lead_named(lead, hook):
    """The lead is named in the hook's first five words (any of its words of 3 letters or more)."""
    first = _toks(hook)[:5]
    return any(x in first for x in _toks(lead) if len(x) > 2)

def _formats():
    return {f["id"] for f in json.loads((ROOT / "templates" / "formats.json").read_text())["formats"]}

def _config():
    return json.loads((ROOT / "config.json").read_text())

def _catalog():
    return {c["slug"] for c in json.loads((ROOT / "pipeline" / "music" / "catalog.json").read_text())}

def _ids_elsewhere(path):
    out = {}
    for d in ("queue", "ready", "done", "failed", "hold", "rejected", "reserve", "expired"):
        for p in (ROOT / "boards" / d).glob("*.json"):
            if path and p.resolve() == pathlib.Path(path).resolve(): continue
            try: out[json.loads(p.read_text()).get("id")] = p
            except Exception: pass
    return out

def check(b, path=None):
    """Returns (errors, warnings) for one board dict. Never raises: a board the checks cannot even read (a beat that is a
    string, a title that is a number) is an error like any other. Until 24 October such a board raised here, and since
    plan.py checks every queued board before the render matrix, one bad board stopped every Short from rendering."""
    if not isinstance(b, dict): return ["not a board: a JSON object is expected"], []
    try: return _check(b, path)
    except Exception as ex:
        return [f"malformed board ({type(ex).__name__}: {str(ex)[:120]}): every field must have the shape the example board has"], []


def _check(b, path=None):
    e, w = [], []
    sid = b.get("id", "")
    es = b.get("language") == "es"          # the Spanish mirror of a main Short (pipeline/mirror.py): id QD-###-es
    if not re.fullmatch(r"QD-\d{3,}(-es)?|TEST-[A-Z0-9-]+", sid): e.append("id: QD-### (next free number)")
    elif sid in _ids_elsewhere(path): e.append(f"id: {sid} is already used, take the next free number")
    elif sid.startswith("QD-") and int(re.match(r"QD-(\d+)", sid).group(1)) < int(_config().get("first_id", 1)): e.append(f"id: numbers start at QD-{int(_config()['first_id']):03d}")
    if sid.endswith("-es") != (es and bool(b.get("mirror_of"))) or (sid.endswith("-es") and b.get("mirror_of") != sid[:-3]):
        e.append("id: a Spanish mirror is QD-###-es with language es and mirror_of (the main Short's id, QD-###), and nothing else is")
    if es and b.get("channel") != "es": e.append("channel: a Spanish board is for the es channel")
    if b.get("format") not in _formats(): e.append(f"format: one of {sorted(_formats())}")
    if b.get("category") not in CATS: e.append(f"category: one of {sorted(CATS)}")
    if b.get("mode", "schedule") not in MODES: e.append(f"mode: one of {sorted(MODES)}")
    chans = sorted((_config().get("shorts_channels") or {}))       # the Daily line's other channels (config shorts_channels)
    if b.get("channel") not in (None, "main") and b.get("channel") not in chans:
        e.append(f"channel: main (leave it out) or one of {chans}")
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
    arm = str((b.get("test") or {}).get("length") or "")           # the length test (writer.py): a minute or two minutes allowed
    # each length arm is held to its own range (content review, 24 October: 22 of 96 boards ran under 70 words and 4 of 8
    # "35 to 44 s" boards missed theirs, so round 1's length factor would compare arms that were never written to length)
    lo, hi, best, top = {"about 60 s": (130, 200, (150, 180), 16), "about 2 min": (250, 370, (280, 340), 30),
                         "under 25 s": (50, 135, (58, 80), 14), "25 to 34 s": (50, 135, (75, 100), 14),
                         "35 to 44 s": (50, 135, (100, 125), 14)}.get(arm, (50, 135, (70, 125), 14))
    if es: lo, hi, best = int(lo * 0.85), int(hi * 1.3), (int(best[0] * 0.9), int(best[1] * 1.25))      # Spanish runs about a fifth longer
    if not 3 <= len(beats) <= top: e.append(f"beats: 3 to {top}")
    hook0 = ((beats[0].get("say") if beats else "") or "").strip().lower()
    if re.match(r"(discover|learn|here'?s how|here is how|today we|let'?s look|let'?s talk|welcome|in this short|in this video)\b", hook0):
        e.append("beat 0: a slow intro (Discover, Learn, Here's how, Today we, Let's look): open on the most surprising detail instead")
    if es and SLOW_ES.match(hook0):
        e.append("beat 0: a slow intro (Descubre, Aprende, Hoy vamos a...): open on the most surprising detail instead")
    # content review (24 October), warnings that get one fixing round: question and "Did you know" openings got 0.47x the
    # views of the rest (7 of the 11 were asked for by no arm), and the 2 date-first openings 0.27x
    hook_arm = str((b.get("test") or {}).get("hook_type") or "") if isinstance(b.get("test"), dict) else ""
    if hook_arm != "question" and (hook0.endswith("?") or "?" in " ".join(hook0.split()[:10])
                                   or re.match(r"(did you know|have you ever|ever wondered|can you guess|guess what)\b", hook0)):
        w.append("beat 0: open with a plain statement that names the star, not a question or 'Did you know'")
    if DATE_FIRST.match(hook0):
        w.append("beat 0: lead with the person and the result, not the date")
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
    allshots = [str(s.get("src", "")) for bt in beats for s in bt.get("shots") or []]
    stock = [x for x in allshots if x.startswith(("pixabay:", "gameplay:"))]
    if allshots and len(stock) > max(1, len(allshots) // 5):
        w.append(f"shots: {len(stock)} of {len(allshots)} are stock; real pictures of the subject first (stock at most 1 in 5)")
    if beats and any(str(s.get("src", "")).startswith(("pixabay:", "gameplay:")) for s in (beats[0].get("shots") or [])):
        w.append("beat 0: the hook needs a real picture of the subject, not stock")
    if not lo <= total <= hi: e.append(f"narration: {total} words, needs {best[0]} to {best[1]}" + (f" ({arm})" if arm in ("about 60 s", "about 2 min") else " (20 to 45 seconds)"))
    elif not best[0] <= total <= best[1]: w.append(f"narration: {total} words, best between {best[0]} and {best[1]}")

    # the video behind the Short (pipeline/background.py): 2 to 4 stock searches, not shots, so never counted as stock above
    bgq = b.get("background")
    if bgq is None: w.append("background: add 2 to 4 stock video searches (2 to 4 concrete words each) for the video behind the Short")
    elif not isinstance(bgq, list) or not 2 <= len(bgq) <= 4: e.append("background: a list of 2 to 4 stock video searches")
    else:
        seen = set()
        for q in bgq:
            if not isinstance(q, str) or not BG.SEARCH.fullmatch(q):
                e.append(f"background: {str(q)[:40]!r} must be 2 to 4 plain words, single spaces, no punctuation (nasa: first for NASA footage)")
                continue
            key = q.lower().removeprefix("nasa:")
            if key in seen: e.append(f"background: {q!r} is listed twice")
            seen.add(key)
    if "bgvideo" in b and not isinstance(b["bgvideo"], bool): e.append("bgvideo: true or false, or leave it out (config.json background.enabled decides)")

    m = b.get("meta") or {}
    title = m.get("title") or ""
    # the title emoji test (writer.py TITLE_TESTS, 24 October): a "none" title carries no emoji, the rest end with one
    arm = str((b.get("test") or {}).get("title_emoji") or "") if isinstance(b.get("test"), dict) else ""
    if not 1 <= len(title) <= 70: e.append("meta.title: 1 to 70 characters")
    elif len(title) > 50 and not b.get("franchise"):      # one limit, 50 (the series prefix is added after the writer)
        w.append(f"meta.title: {len(title)} characters: under 50, the searched name still first")
    if arm == "none":
        if EMOJI.search(title): e.append("meta.title: no emoji (this Short tests a title without one)")
    elif not EMOJI.search(title[-2:]): e.append("meta.title: end with one emoji")
    # the hook names the lead the title names (content review, 24 October: hooks whose first four words name the best-known
    # person got 2.24x the views; Olivia Rodrigo first 5.42x, David Byrne first 0.27x): the lead is a name the board labels
    # on screen that the title opens with, and it belongs in the hook's first five words (question and twist arms aside)
    lead = hook_lead(b)
    if hook_arm not in ("question", "twist") and lead and not lead_named(lead, hook0):
        w.append(f"beat 0: name {lead} in the first five words, as the title does")
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
                    elif v not in cat[d]["options"] or (cat[d]["options"][v].get("retired") and b.get("mode") != "none"):
                        # a render-only test board may try an option that is held back until its test passes
                        e.append(f"look.{d}: one of {sorted(k for k, o in cat[d]['options'].items() if not o.get('retired'))}")
        except (OSError, ValueError, KeyError): pass
    if m.get("comment") and (len(str(m["comment"])) > 100 or "http" in str(m["comment"])): e.append("meta.comment: under 100 characters, no links")
    alt = str(m.get("alt_title") or "")
    if alt and (len(alt) > 70 or (bool(EMOJI.search(alt)) if arm == "none" else not EMOJI.search(alt[-2:]))):
        e.append("meta.alt_title: under 70 characters, " + ("no emoji" if arm == "none" else "one emoji at the end"))
    if not m.get("comment") or not alt: w.append("meta.comment and meta.alt_title: add both (comment question, backup title)")
    srcs = m.get("sources") or []
    bad = [s for s in srcs if not (isinstance(s, list) and len(s) == 2 and str(s[1]).startswith("https://"))]
    if bad: e.append("meta.sources: each one [title, https url]")
    sites = {urllib.parse.urlparse(s[1]).netloc.lower().removeprefix("www.") for s in srcs if s not in bad}
    if len(srcs) < 1: e.append("meta.sources: at least 1 source (the exact page)")
    elif len(sites) < 2: w.append("meta.sources: one site only; name it in the narration for breaking news")
    facts = m.get("facts") or []
    if not facts: e.append("meta.facts: list every factual claim as [claim, [source numbers]]")
    for f in facts:
        if not (isinstance(f, list) and len(f) == 2 and isinstance(f[1], list)):
            e.append("meta.facts: each one [claim, [source numbers]]"); continue
        nums = set(f[1])
        if any(not isinstance(k, int) or not 1 <= k <= len(srcs) for k in nums):
            e.append(f"meta.facts: source numbers run from 1 to {len(srcs)} ({str(f[0])[:40]})")
        elif not nums:
            e.append(f"meta.facts: needs a source: {str(f[0])[:60]}")

    blob = json.dumps(b, ensure_ascii=False)
    if DASH.search(blob): e.append("no em dashes or en dashes anywhere")
    said = " ".join(bt.get("say", "") for bt in beats) + " " + title
    if re.search(r"according to wikipedia|wikipedia (says|shows|states|lists|notes|reports)", said, re.I):
        e.append("say: never cite Wikipedia; state the fact, or name the outlet that reported it")
    text = " ".join([bt.get("say", "") for bt in beats] + [title, m.get("summary", "")])
    us = sorted({m.group(0) for m in US_DATE.finditer(text)})
    if us: e.append(f"UK date style: write '20 October', not {us}")
    hits = sorted({h.lower() for h in BANNED.findall(text)} | ({m.group(0).lower() for m in BANNED_ES.finditer(text)} if es else set()))
    if hits: e.append(f"excluded topic or virality words: {hits}")
    if str(b.get("kind", "")).lower() != "fiction":
        early = " ".join([title, m.get("summary", "")] + [bt.get("say", "") for bt in beats[:2]])
        neg = sorted({m.group(0).lower() for m in NEGATIVE_ES.finditer(early)} if es else {h.lower() for h in NEGATIVE.findall(early)})
        if neg: e.append(f"negative framing of a real person (only in fiction): {neg}")
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
