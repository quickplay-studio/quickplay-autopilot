"""The Spanish mirror (Charlie, 25 October: "40% of views are US, boards already carry translations"): Quickplay Diario, the
Spanish channel for the Americas, posts a Spanish version of the main channel's Shorts.

For each main board that has been written (boards/queue) or has gone public (boards/done) and has no mirror yet, one model call
(factpack.gemini, JSON in and out) translates every word the viewer hears or reads into neutral Latin American Spanish: each
beat's `say`, the graphics' texts, the roles under the name tags, the title (under 50 characters), summary, tags, hashtags and
comment. The mirror keeps the same fact pack: sources, facts, pictures, shots, music and background are the original's, and
nothing is added; a numbers check (every number in the English is in the Spanish and no other), a names check and the board
rules (validate.py, with its Spanish banned and negative-framing lists) must pass, and a translation that fails them is asked
for again once with what was wrong, then dropped. The result is boards/queue/<id>-es.json: "language": "es", "channel": "es",
"mirror_of": <id>, so plan.py gives it the es channel's sign-in, its American-evening slots (23:00 UTC, then 00:00 to 03:00 UTC)
and its own room per day, run_board.py reads it in the Spanish voice (Chatterbox Multilingual) with Spanish labels, and
upload.py sends Spanish metadata with defaultLanguage es.

Dormant until the channel's sign-in exists (youtube.connected("es"): tokens/youtube_es.enc), like every extra channel. The main
channel is never touched: the mirror reads its boards and writes new ones. A time-sensitive board more than a day old is left
alone; freshness.py judges a Spanish Short's day in New York time and with Spanish day words. Every attempt is one row of
analytics/mirror_log.csv (made, failed, skipped), and a board that failed twice is not tried again.

usage: python pipeline/mirror.py [--day YYYY-MM-DD] [--run morning|afternoon|evening] [--dry]    (writer.py calls mirror_boards)
"""
import collections, copy, csv, datetime as dt, json, math, pathlib, re, sys
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import factpack, freshness, validate

UK = ZoneInfo("Europe/London")
CFG = json.loads((ROOT / "config.json").read_text())
LOG = ROOT / "analytics" / "mirror_log.csv"
LOG_FIELDS = ["at", "id", "result", "why", "model"]
CATEGORY_ES = {"Gaming": "Videojuegos", "Film": "Cine", "Music": "Música", "Sport": "Deportes", "Tech": "Tecnología", "Science": "Ciencia",
               "Entertainment": "Famosos", "Animals": "Animales", "Food": "Comida", "Cars": "Autos", "History": "Historia"}
FOLDERS = ("queue", "ready", "done", "failed", "reserve", "rejected", "expired", "hold")
# what the mirror does not carry over: the English look, the series names, the schedule and the cross-posting picks
DROP = ("look", "publish_at", "flag", "tiktok", "franchise", "series", "follows", "editor", "reserve", "social", "channel_series",
        "control", "sameness", "sameness_with", "sameness_recipe_share")      # a mirror is never a control Short (control.py) and has its own sameness
KEEP_TEST = ("length", "title_emoji", "hook_type", "viral_angle")             # the arms the Spanish board is written (and validated) to
VISUAL_TEXT = ("kicker", "label", "sub", "caption", "text", "by", "mid", "month", "weekday", "stamp", "t", "s", "value", "prefix", "suffix")
SKIP_NAMES = set("""january february march april may june july august september october november december monday tuesday wednesday thursday
friday saturday sunday british english american spanish french german italian japanese korean mexican canadian christmas easter
the this that these those there then they when what where which while with from after before also but and""".split())
MAX_GROWTH = 1.35          # the Spanish narration runs at most this many times the English word count
MAX_TRIES = 2              # attempts per board, across runs: a board that failed twice is left
MIN_REL = 0.35             # a Short the main channel's audience clearly passed over (views against typical, 3 days on) is not mirrored: a dead Short is never remade


# ---------------------------------------------------------------- the line
def signed_in(ch):
    """The channel has its own sign-in (youtube.connected: tokens/youtube_<ch>.enc)."""
    try:
        import youtube as Y
        return bool(Y.connected(ch))
    except Exception:           # no Google libraries here: the file is all connected() looks for anyway
        f = ROOT / "tokens" / f"youtube_{ch}.enc"
        return f.is_file() and f.stat().st_size > 0


def mirror_channels():
    """{name: config} of the channels that mirror the main channel and are signed in."""
    return {ch: c for ch, c in (CFG.get("shorts_channels") or {}).items()
            if isinstance(c, dict) and c.get("mirror_of") == "main" and c.get("language") == "es" and signed_in(ch)}


def read(path):
    try: return json.loads(pathlib.Path(path).read_text())
    except Exception: return {}


def mirror_files():
    """{mirror id: (board, folder)} for every Spanish board in any folder."""
    out = {}
    for d in FOLDERS:
        for f in (ROOT / "boards" / d).glob("QD-*-es.json"):
            b = read(f)
            if isinstance(b, dict) and b.get("id"): out[b["id"]] = (b, d)
    return out


def log_rows():
    if not LOG.exists(): return []
    try: return list(csv.DictReader(LOG.open()))
    except Exception: return []


def log(sid, result, why="", model=""):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists() or not LOG.stat().st_size
    with LOG.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new: w.writeheader()
        w.writerow({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "id": sid, "result": result,
                    "why": str(why)[:300].replace("\n", " "), "model": model})


def candidates(day):
    """The main boards worth a mirror, best first: written (queue) or public (done), a normal scheduled Short on the main
    channel, at most a week old and, when it is time-sensitive, at most a day old, with no mirror yet (in any folder) and fewer
    than MAX_TRIES failed attempts, and not one the main channel's audience clearly passed over (MIN_REL). Order: today's time-sensitive Shorts first (the American evening is the same news day),
    then the ones the main channel's audience took best (views against typical), newest first."""
    have = set(mirror_files())
    failed = collections.Counter(r.get("id") for r in log_rows() if r.get("result") == "failed")
    rel = {}
    try:
        for r in csv.DictReader((ROOT / "analytics" / "shorts.csv").open()):
            try:
                if float(r.get("views_vs_typical") or 0) > 0: rel[r["short"]] = float(r["views_vs_typical"])
            except (ValueError, KeyError): pass
    except OSError: pass
    out = []
    for d in ("queue", "done"):
        for f in sorted((ROOT / "boards" / d).glob("QD-*.json"))[-80:]:       # the newest 80: nothing older is a week old
            b = read(f)
            if not isinstance(b, dict) or not re.fullmatch(r"QD-\d{3,}", str(b.get("id", ""))): continue
            if b.get("channel") not in (None, "main") or b.get("language") or b.get("mode", "schedule") != "schedule": continue
            if b["id"] + "-es" in have or failed[b["id"] + "-es"] >= MAX_TRIES: continue
            try: age = (day - dt.date.fromisoformat(str(b.get("created"))[:10])).days
            except ValueError: continue
            timely = freshness.kind_of(b) in freshness.TIMELY
            if age > 7 or age < 0 or (timely and age > 1) or (age >= 3 and rel.get(b["id"], 1.0) < MIN_REL): continue
            out.append((not (timely and age == 0), -rel.get(b["id"], 1.0), age, b["id"], b))
    out.sort(key=lambda x: x[:4])
    return [x[4] for x in out]


def room(ch, c, day, run):
    """How many mirrors this run may make: the channel's per_day spread over the day's runs like the main channel's (config
    runs), a run making up what an earlier one could not, less the mirrors already made for `day`."""
    per_day = int(c.get("per_day") or 6)
    runs = {k: int(v) for k, v in (CFG.get("runs") or {}).items() if str(v).isdigit()}
    order = [k for k in ("morning", "afternoon", "evening") if k in runs]
    if run in order and runs:
        share = sum(runs[k] for k in order[:order.index(run) + 1]) / max(1, sum(runs.values()))
        so_far = min(per_day, max(1, math.ceil(per_day * share)))
    else: so_far = per_day
    made = sum(1 for b, d in mirror_files().values() if b.get("channel") == ch and b.get("mirrored") == str(day) and d != "failed")
    return max(0, so_far - made)


# ---------------------------------------------------------------- the words of a board
def has_words(s):
    return isinstance(s, str) and bool(re.search(r"[^\W\d_]{3,}", s))


def collect(b):
    """({key: text}, {key: (container, index)}) for every text of the board that is read or heard: the keys name where the text
    is, and the second dict says where to put the translation back."""
    fields, slots = {}, {}
    def add(key, cont, idx):
        v = cont[idx]
        if isinstance(v, str) and v.strip(): fields[key] = v; slots[key] = (cont, idx)
    def walk(key, v):
        if not isinstance(v, dict): return
        for k, x in v.items():
            if k in VISUAL_TEXT and isinstance(x, str) and (has_words(x) or k not in ("value", "prefix", "suffix")): add(f"{key}.{k}", v, k)
            elif k == "lines" and isinstance(x, list):
                for j, ln in enumerate(x):
                    if isinstance(ln, str): add(f"{key}.lines.{j}", x, j)
            elif k == "items" and isinstance(x, list):
                for j, it in enumerate(x): walk(f"{key}.items.{j}", it)
    for i, bt in enumerate(b.get("beats") or []):
        add(f"b{i}.say", bt, "say")
        walk(f"b{i}.v", bt.get("visual"))
        for j, sh in enumerate(bt.get("shots") or []):
            lab = sh.get("label") if isinstance(sh, dict) else None
            if isinstance(lab, dict) and lab.get("s"): add(f"b{i}.s{j}.role", lab, "s")        # the name stays, the role is translated
    m = b.setdefault("meta", {})
    for k in ("title", "summary", "comment", "alt_title"):
        if m.get(k): add(f"meta.{k}", m, k)
    for j, t in enumerate(m.get("tags") or []):
        if j and isinstance(t, str): add(f"meta.tags.{j}", m["tags"], j)               # the first tag is the story's own name: kept
    for j, h in enumerate(m.get("hashtags") or []):
        if isinstance(h, str): add(f"meta.hashtags.{j}", m["hashtags"], j)
    return fields, slots


def numbers(text):
    """The numbers in a text as bare digits (1,200 and 1.200 are the same number, 1.5 and 1,5 too)."""
    return collections.Counter(re.sub(r"\D", "", n) for n in re.findall(r"\d[\d., ]*\d|\d", str(text)))


def names(text):
    """Capitalised words in the middle of a sentence: people, bands, songs, places and brands, which stay as they are."""
    out = set()
    for sentence in re.split(r"(?<=[.!?])\s+", str(text)):
        words = [re.sub(r"['’]s$", "", w) for w in re.findall(r"[\w'’-]+", sentence)]
        for w in words[1:]:
            if w[0].isupper() and len(w) >= 3 and w.lower() not in SKIP_NAMES and not w.isupper(): out.add(w.lower())
    return out


def fold(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(s).lower()) if unicodedata.category(c) != "Mn")


def problems_with(fields, es, es_board=None):
    """What is wrong with a translation (a list of plain sentences), judged against the English fields."""
    if not isinstance(es, dict): return ["the answer must be one JSON object"]
    out = []
    missing = [k for k in fields if k not in es or not isinstance(es[k], str) or not es[k].strip()]
    if missing: out.append(f"these keys are missing or empty: {missing[:8]}")
    extra = [k for k in es if k not in fields]
    if extra: out.append(f"these keys are not in the English: {extra[:8]}")
    if missing: return out
    for k, v in es.items():
        if k in fields and re.search("[\u2014\u2013]", v): out.append(f"{k} has a dash: use a comma or a full stop")
    for i in sorted({int(m.group(1)) for k in fields for m in [re.match(r"b(\d+)\.say$", k)] if m}):
        a, z = numbers(fields[f"b{i}.say"]), numbers(es[f"b{i}.say"])
        if a != z:
            lost, new = sorted((a - z).elements()), sorted((z - a).elements())
            out.append(f"b{i}.say: the numbers must be the same as the English (digits kept as digits); missing {lost}, not in the English {new}")
    en_say = " ".join(v for k, v in fields.items() if k.endswith(".say")); es_say = " ".join(v for k, v in es.items() if k.endswith(".say"))
    if len(es_say.split()) > MAX_GROWTH * len(en_say.split()):
        out.append(f"the narration is {len(es_say.split())} words against {len(en_say.split())} in English: at most {int(MAX_GROWTH * 100 - 100)}% more, say it shorter")
    want = names(en_say); body = fold(" ".join(es.values()))
    lost = sorted(n for n in want if fold(n) not in body)
    if want and len(lost) > 0.4 * len(want): out.append(f"names must stay as they are in English; not found: {lost[:8]}")
    t = es.get("meta.title", "")
    if len(t) > 50: out.append(f"meta.title is {len(t)} characters: under 50")
    return out


PROMPT = """You translate a finished YouTube Short from English into neutral Latin American Spanish for viewers across the Americas (Mexico to Argentina, and Spanish speakers in the United States). The English Short is below as JSON: each key says where the text is (b3.say is the narration of beat 3, b3.v.* the words of a graphic on screen, b3.s0.role a label under a name tag, meta.* the title, summary, tags and hashtags).

RETURN one JSON object with exactly the same keys and nothing else, every value translated.

RULES
- Same facts, nothing invented, nothing left out that changes the meaning. Keep every number as digits exactly as it is (12, 2.5, 1,200), keep currency symbols, and never turn a number into words. Do not add a source, a claim or an opinion.
- Names of people, bands, songs, albums, films, games, teams, places and brands stay exactly as in English (a work is translated only when it has an established Spanish title).
- Write for the ear: short spoken sentences, natural Spanish, not word for word. The first line is a hook that names the star early, as the English does. Same energy, same tone, family friendly. Never add anything negative, mocking or critical about a real person that the English does not say.
- If a beat's narration asks viewers to subscribe (an English series is named, "Song Secrets is here every day; subscribe so you don't miss the next one"), say it as one short line inviting them to subscribe to this channel for more Shorts like it, without naming the English series (the Spanish channel has none).
- Neutral Latin American Spanish: tu or ustedes, no vosotros, no voseo, no Spain-only words (ordenador, movil, coger, vale). Months and weekdays in lower case ("25 de octubre", "martes"); a three-letter month or weekday on a graphic stays three letters (OCT, MAR).
- Keep the narration (every b*.say) to at most 20% more words than the English. Graphics and labels must stay as short as the English (at most 25% longer) so they fit the screen.
- No em dashes and no en dashes anywhere: use a comma or a full stop. Use the opening marks of Spanish questions and exclamations.
- meta.title: under 50 characters, the searched name first, and if the English title ends with an emoji end with that same emoji. meta.alt_title: the same, a different wording. meta.comment: one short question for viewers, under 100 characters, no links.
- meta.hashtags: the same number as the English, each starting with # followed by letters and digits only (no spaces), names unchanged, most relevant first. meta.tags: search phrases Spanish speakers type.
- UK English spelling does not apply: write Spanish only, no English words except names.

CATEGORY: {category}

ENGLISH SHORT (JSON)
{fields}
{retry}"""


def ask_model(fields, category, problems=None, ask=None):
    """(translation dict, model name) from one model call."""
    retry = ("\nYOUR LAST ANSWER WAS REFUSED FOR THESE REASONS, FIX THEM AND KEEP THE REST:\n- " + "\n- ".join(problems)) if problems else ""
    ans, model = (ask or factpack.gemini)(PROMPT.format(category=category, fields=json.dumps(fields, ensure_ascii=False, indent=1), retry=retry),
                                          None, timeout=100, temperature=0.2, lite=True)
    return ans, model


def build(b, es_fields, slots, model, day, ch, c):
    """The Spanish board: `b` (a copy of the English one, `slots` from collect(b)) with every text replaced."""
    orig = b["id"]
    for bt in b.get("beats") or []:
        if bt.get("say"): bt["say_en"] = bt["say"]          # the English line stays for the picture match (fetch_media.py): same pictures as the original
    for k, (cont, idx) in slots.items():
        cont[idx] = re.sub(r"[<>]", "", re.sub(r"\s+", " ", es_fields[k]).strip())
    b.update(id=orig + "-es", language="es", channel=ch, mirror_of=orig, mirrored=str(day), writer=f"mirror:{model}")
    for k in DROP: b.pop(k, None)
    b["test"] = {**{k: v for k, v in (b.get("test") or {}).items() if k in KEEP_TEST}, "mirror": "yes"}
    for bt in b.get("beats") or []:
        bt.pop("say_cb", None); bt.pop("cap", None)
    m = b["meta"]
    m.pop("translations", None)
    m["hashtags"] = [h if str(h).startswith("#") else "#" + str(h) for h in m.get("hashtags") or []]
    b["chip_label"] = CATEGORY_ES.get(b.get("category"), b.get("category"))
    b["cta_lines"] = ["Sigue para", "la tendencia", "de mañana"]           # the call to action of a closing card (template3.html)
    if c.get("handle"): b["handle"] = c["handle"]
    return b


def fix_emoji(en_title, es_title):
    """The Spanish title ends with the emoji the English one does (the title emoji test), when the model dropped it."""
    tail = en_title.strip()[-2:]
    emoji = tail.strip() if validate.EMOJI.search(tail) else ""
    if emoji and not validate.EMOJI.search(es_title.strip()[-2:]): return es_title.rstrip() + " " + emoji
    return es_title


def clean_answer(ans, en):
    """The model's answer with dashes turned into commas and the title's emoji kept (the board rules refuse a dash)."""
    if not isinstance(ans, dict): return ans
    ans = {k: re.sub("\\s*[\u2014\u2013]\\s*", ", ", v) if isinstance(v, str) else v for k, v in ans.items()}
    if isinstance(ans.get("meta.title"), str) and en.get("meta.title"): ans["meta.title"] = fix_emoji(en["meta.title"], ans["meta.title"])
    return ans


def translate(src, ch, c, day, ask=None):
    """(Spanish board, model, "") for one main board, or (None, model, why): one model call, and a second with what was wrong
    when the first answer is refused by the checks."""
    en, _ = collect(copy.deepcopy(src))
    if not any(k.endswith(".say") for k in en): return None, "", "no narration to translate"
    problems, model = None, ""
    for attempt in range(2):
        try: ans, model = ask_model(en, src.get("category", ""), problems, ask)
        except Exception as e: return None, model, f"no model answered: {str(e)[:160]}"
        ans = clean_answer(ans, en)
        problems = problems_with(en, ans)
        if not problems:
            b = copy.deepcopy(src); _, slots = collect(b)
            es = build(b, ans, slots, model, day, ch, c)
            errs = [x for x in validate.check(es)[0] if "already used" not in x]
            if not errs: return es, model, ""
            problems = [f"board rules: {x}" for x in errs]
        if factpack.STATE.get("spent"): break
    return None, model, "; ".join(problems)[:300]


# ---------------------------------------------------------------- the run
def mirror_boards(day, run="", late=lambda: False, ask=None):
    """Make this run's Spanish mirrors (called by writer.py after the main boards, and by main below). `day`: the UK date the
    run writes for. Returns the boards written; nothing at all while no mirror channel is signed in."""
    wrote = []
    for ch, c in mirror_channels().items():
        want = room(ch, c, day, run)
        if want <= 0: print(f"mirror {ch}: the day's share is made"); continue
        todo = candidates(day)
        if not todo: print(f"mirror {ch}: no main board to mirror"); continue
        made = 0
        for src in todo:
            if made >= want or factpack.STATE.get("spent") or late(): break
            es, model, why = translate(src, ch, c, day, ask)
            if not es:
                log(src["id"] + "-es", "failed", why, model); print(f"mirror {ch}: {src['id']}: {why}"); continue
            out = ROOT / "boards" / "queue" / f"{es['id']}.json"
            out.write_text(json.dumps(es, ensure_ascii=False, separators=(",", ":")))
            log(es["id"], "made", es["meta"]["title"], model); made += 1; wrote.append(es)
            print(f"mirror {ch}: {es['id']} {es['meta']['title']} ({model})")
        print(f"mirror {ch}: made {made} of {want}")
    return wrote


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=""); ap.add_argument("--run", default="")
    ap.add_argument("--dry", action="store_true", help="list what would be mirrored, call no model")
    a = ap.parse_args(argv)
    day = dt.date.fromisoformat(a.day) if a.day else dt.datetime.now(UK).date()
    if a.dry:
        for ch, c in mirror_channels().items():
            print(f"{ch}: room {room(ch, c, day, a.run)}; next: " + ", ".join(b["id"] for b in candidates(day)[:12]))
        return 0
    mirror_boards(day, a.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
