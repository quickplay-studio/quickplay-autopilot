"""Named, numbered series, search-led evergreen subjects and seasonal playbooks (Charlie, 25 October 2026: search-led
evergreen Shorts as named, numbered series in playlists, and seasonal playbooks run as mini-series).

Why: YouTube search brings 24% of our views and the feed 74%, and 11 people have subscribed after 141 Shorts, because a
viewer who likes one Short has no reason to follow. So each category's evergreen Shorts become a numbered series ("Science
Explained #12: ...") that sits in a playlist, and a big event's launch week becomes a five-part mini-series ("Ballon d'Or
#1 to #5"). People who search find the series; the playlist and the numbers give a viewer a next Short to watch.

This module is the logic that needs no network and no model, so the tests run offline:
- the registry (config.json "series", one entry per category) and the next number of a series, counted over boards/*;
- decorate(): the title and the alternative title with the series name and number, inside validate.py's 70 characters;
- description_lines() and comment_text(): the series line and the playlist link in the description (run_board.py) and in
  the creator comment (engage.py);
- candidates(): what people search, for writer.search_led_packs to turn into evergreen Shorts with checked facts: our own
  search terms (analytics/search_terms.csv), YouTube's search suggestions for "why does", "what is", "how did" and
  "explained" after a rotating handful of each category's seeds, Google Trends related queries when trends/latest.json
  carries them (it carries none yet), and Wikipedia's On this day;
- the playbooks (status/playbooks.json, written once by watch.py when an item first reaches launch or surging): the
  item's first five angles, one a day, found again from the boards (series_key, series_no) so no extra state can go stale.
playlists.py (the YouTube side) and writer.py (the models) import this; it imports neither.

Board fields set here (the writer's BOOKKEEPING strips them from anything a model writes): series_name, series_no,
series_kind ("evergreen" or "playbook"), series_key (the playlist's key: the series name, or the event's full name) and,
for a playbook, series_of. The board's "series" is not used: it is already the two- or three-part cliffhanger
({id, part, of, prev}, engage.series_links reads it) and the test field "series" is that test's arm.
"""
import csv, datetime as dt, json, pathlib, re, time
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
UK = ZoneInfo("Europe/London")
PLAYBOOKS = ROOT / "status" / "playbooks.json"
PLAYLISTS = ROOT / "status" / "playlists.json"
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
FOLDERS = ("queue", "ready", "done", "failed", "reserve", "hold")     # boards that hold a number (not rejected or expired ones)
DEFAULT_TITLE = "{name} #{n}: {subject}"
TITLE_LIMIT = 70                                                       # validate.py: meta.title is 1 to 70 characters
NOTE_TITLE = "Write the title for the question people search, under 45 characters, with no series name or number in it"
GENERIC_ANGLES = ("{name} explained", "{name} everything to know", "{name} facts you may have missed", "{name} records and firsts",
                  "{name} what happens next")


def _cfg(cfg): return CFG if cfg is None else cfg


def _q(s):
    """Curly quotes as plain ones (same length, so positions line up) for comparing names."""
    return str(s).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def norm(s): return " ".join(re.findall(r"[a-z0-9]+", _q(s).lower()))


# ---------------- the registry and the numbers ----------------
def registry(cfg=None):
    """{category: spec} from config.json "series": name, category, title pattern, about (the description line), seeds
    (what the search suggestions start from), playlist (an id set by hand, optional). The first entry of a category wins."""
    out = {}
    for s in _cfg(cfg).get("series") or []:
        if not isinstance(s, dict) or not s.get("name") or not s.get("category"): continue
        spec = {"title": DEFAULT_TITLE, "about": "", "seeds": [], "playlist": "", **s}
        if "{subject}" not in str(spec["title"]): spec["title"] = DEFAULT_TITLE
        out.setdefault(s["category"], spec)
    return out


def boards(root=None, folders=FOLDERS):
    """Every real board (dry runs never go out, so they hold no number) in the folders that count."""
    root = pathlib.Path(root or ROOT)
    for d in folders:
        for f in sorted((root / "boards" / d).glob("QD-*.json")):
            try: b = json.loads(f.read_text())
            except Exception: continue
            if isinstance(b, dict) and b.get("mode") != "dry": yield b


def next_number(name, written=(), root=None):
    """The next number of a series: one more than the boards of that name that exist (every folder that counts, and this
    run's `written`, a dry run's too so its own Shorts count on from each other) and than the highest number any of them
    carries, so a board lost from a folder never repeats one."""
    count = top = 0
    seen = {}
    for i, b in enumerate(list(boards(root)) + list(written)):
        seen[b.get("id") or f"?{i}"] = b          # a board written this run is also in boards/queue by now: counted once
    for b in seen.values():
        if b.get("series_name") != name: continue
        count += 1
        try: top = max(top, int(b.get("series_no") or 0))
        except (TypeError, ValueError): pass
    return max(count, top) + 1


# ---------------- titles, descriptions, comments ----------------
EMOJI_TAIL = re.compile(r"\s*((?:[\U0001F000-\U0001FAFF☀-➿⬀-⯿][️‍]*)+)\s*$")
STOPS = {"a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "with", "at", "by", "is", "are", "was", "were", "its", "it", "as",
         "near", "than", "that", "from", "into", "about", "when", "which", "while", "after", "before", "but", "so", "if", "this", "these",
         "those", "his", "her", "their", "our", "your", "my", "be", "been", "has", "have", "had", "do", "does", "did", "over", "under",
         "between", "during", "through", "via", "per", "not", "no", "can", "could", "would", "will", "who", "whose", "what", "why", "how"}


def strip_name(title, names):
    """The title without a leading series name (or event name) the model wrote anyway, and any number or separator after it."""
    t = str(title or "").strip()
    for nm in sorted({str(x) for x in names if x}, key=len, reverse=True):
        m = re.match(r"\s*" + re.escape(_q(nm)).replace(r"\ ", r"\s+") + r"\s*(?:#\s*\d+)?\s*[:|]?\s*", _q(t), re.I)
        if m and m.end() < len(t): t = t[m.end():]
    return t


def decorate(title, name, n, pattern=DEFAULT_TITLE, limit=TITLE_LIMIT, also=()):
    """The title with its series name and number, e.g. "Science Explained #12: Why is the sky blue? 🔭", within `limit`
    characters. The emoji stays last (validate.py wants it there); a title too long loses words from its end, never the
    series. `also`: other names the model may have led with (an event's full name)."""
    t = strip_name(title, [name, *also])
    m = EMOJI_TAIL.search(t)
    tail, core = (m.group(1), t[:m.start()].strip()) if m else ("", t.strip())
    first = core.split()[0] if core.split() else ""
    if first.islower(): core = core[:1].upper() + core[1:]       # "why is" becomes "Why is"; "iPhone" and "eBay" stay as written
    pat = pattern if "{subject}" in str(pattern) else DEFAULT_TITLE
    def fmt(c):
        try: return pat.format(name=name, n=n, subject=c)
        except (KeyError, IndexError, ValueError): return DEFAULT_TITLE.format(name=name, n=n, subject=c)
    build = lambda c: (fmt(c) + (" " + tail if tail else "")).strip()
    words = core.split()
    out = build(" ".join(words))
    while len(out) > limit and len(words) > 2:
        words.pop()
        while len(words) > 2 and (words[-1].lower().strip(",.:;!?-") in STOPS or not words[-1].strip(",.:;!?-")): words.pop()
        out = build(" ".join(words).rstrip(",:;- "))
    if len(out) > limit: out = (f"{name} #{n}" + (" " + tail if tail else ""))[:limit].strip()
    return out


def playlist_title(spec):
    return str(spec.get("playlist_title") or f"{spec['name']} | Quickplay Daily")[:150]


def playlist_id(key, cfg=None, path=None):
    """The playlist of a series: an id set by hand in the registry, else the one engage.py created (status/playlists.json)."""
    for spec in registry(cfg).values():
        if spec["name"] == key and str(spec.get("playlist") or "").strip(): return str(spec["playlist"]).strip()
    try: return str(((json.loads(pathlib.Path(path or PLAYLISTS).read_text()).get("playlists") or {}).get(key) or {}).get("id") or "")
    except Exception: return ""


def playlist_url(key, cfg=None, path=None):
    pid = playlist_id(key, cfg, path)
    return f"https://www.youtube.com/playlist?list={pid}" if pid else ""


def label(b):
    """"Science Explained #12" or "Ballon d'Or #2 of 5"."""
    of = f" of {b['series_of']}" if b.get("series_of") else ""
    return f"{b['series_name']} #{b['series_no']}{of}"


def about_of(b, cfg=None, path=None):
    """The series' description line (the registry's, or the playbook's)."""
    if b.get("series_kind") == "playbook":
        plan = plan_of(b.get("series_key") or "", path)
        return str((plan or {}).get("about") or "")
    return str((registry(cfg).get(b.get("category")) or {}).get("about") or "")


def description_lines(b, url=None, cfg=None):
    """Lines for the YouTube description, after the summary: the series, its number and the line about it, then the
    playlist link when there is one, then a blank line. [] for a Short in no series."""
    if not (isinstance(b, dict) and b.get("series_name") and b.get("series_no")): return []
    url = playlist_url(b.get("series_key") or b["series_name"], cfg) if url is None else url
    about = about_of(b, cfg)
    return [f"{label(b)}" + (f": {about}" if about else "."), *([f"More in the series: {url}"] if url else []), ""]


def comment_text(comment, b, url=""):
    """The creator comment (500 characters at most). Its first line names the series (a Short in none: its category) and asks
    to subscribe, with the series' playlist link (else the channel's one-tap subscribe link); the board's question follows
    (subscriber push, 25 October: subscribe.comment_first_line; until then the question came first and a series' name, number
    and playlist link last). Never fails: without the subscriber module it is the old form."""
    base = str(comment or "").strip()
    try:
        import subscribe
        first = subscribe.comment_first_line(b if isinstance(b, dict) else {}, url)
    except Exception: first = ""
    if first:
        room = 500 - len(first) - 2
        return (first + ("\n\n" + base[:room] if base and room > 0 else ""))[:500]
    if not (isinstance(b, dict) and b.get("series_name") and b.get("series_no")): return base[:500]
    tail = f"{label(b)}." + (f" The whole series: {url}" if url else "")
    return (base[:300] + ("\n\n" if base else "") + tail)[:500]


# ---------------- which series a pack belongs to ----------------
def series_for(p, kind, category=None, reserve=False, cfg=None, path=None):
    """The series a pack's Short would join: a playbook angle of its event (the signal names the event, the topic is one of
    its angles), else an evergreen Short of its category's registry entry. The reserve is released in any order, so it is
    left out. {"kind", "key", "name", "pattern", "also", "no" and "of" for a playbook} or None."""
    hit = playbook_match(p, path)
    if hit:
        plan, no = hit
        return {"kind": "playbook", "key": plan["event"], "name": plan["short"], "pattern": DEFAULT_TITLE, "also": [plan["event"]],
                "no": no, "of": plan["of"]}
    if kind == "evergreen" and not reserve:
        spec = registry(cfg).get(category or (p or {}).get("category") or "")
        if spec: return {"kind": "evergreen", "key": spec["name"], "name": spec["name"], "pattern": spec["title"], "also": []}
    return None


def prepare(p, kind, tests, note="", reserve=False, cfg=None, path=None):
    """Before a board is written: a Short that joins a series leaves the franchise test (the series is its named series:
    test franchise "series", so the franchise arms stay a news-only comparison and the title is not given two prefixes),
    and the model is told the pipeline adds the name and number. -> (tests, note)."""
    s = series_for(p, kind, None, reserve, cfg, path)
    if not s: return tests, note
    tests = {**(tests or {}), "franchise": "series"}
    if s["kind"] == "playbook":
        said = (f'MINI-SERIES: this is number {s["no"]} of {s["of"]} in our "{s["name"]}" mini-series on {s["also"][0]}, one a day. '
                f'Cover this angle only: "{p.get("topic", "")}" (the other angles get their own Short). The pipeline puts '
                f'"{s["name"]} #{s["no"]}: " in front of the title. {NOTE_TITLE}.')
    else:
        said = (f'NUMBERED SERIES: this Short joins our numbered series "{s["name"]}" (one Short, no parts). The pipeline puts '
                f'"{s["name"]} #<number>: " in front of the title. {NOTE_TITLE}.')
    return tests, (note + "\n\n" if note else "") + said


def name_board(b, p, written=(), reserve=False, root=None, cfg=None, path=None):
    """After a board is written: its series, number and decorated titles, in place. Returns the series fields or None."""
    s = series_for(p, b.get("kind", ""), b.get("category") or None, reserve or bool(b.get("reserve")), cfg, path)
    if not s and b.get("kind") == "evergreen" and not (reserve or b.get("reserve")):
        s = series_for(p, "evergreen", (p or {}).get("category"), False, cfg, path)        # the pack's category when the model's has none
    if not s: return None
    no = s["no"] if s["kind"] == "playbook" else next_number(s["name"], written, root)
    m = b.get("meta") if isinstance(b.get("meta"), dict) else {}
    titles = {k: decorate(m[k], s["name"], no, s["pattern"], also=s["also"]) for k in ("title", "alt_title") if m.get(k)}
    fields = {"series_name": s["name"], "series_no": no, "series_kind": s["kind"], "series_key": s["key"]}
    if s["kind"] == "playbook": fields["series_of"] = s["of"]
    m.update(titles)                         # all or nothing: nothing above changed the board
    b.setdefault("meta", m)
    b.update(fields)
    return fields


def search_due(day, run, cap, per_day=None, root=None, cfg=None):
    """How many search-led Shorts this run writes: the evening and morning runs one each, the afternoon run whatever the day
    is still short of config evergreen_search_per_day, never more than the run's places. The day's count is read from the
    boards (source "Search-led" created for that day), so a rerun never doubles it."""
    per_day = int(_cfg(cfg).get("evergreen_search_per_day") or 0) if per_day is None else per_day
    if per_day <= 0 or cap <= 0: return 0
    made = sum(1 for b in boards(root, ("queue", "ready", "done", "failed")) if b.get("created") == str(day) and b.get("source") == "Search-led")
    left = per_day - made
    return max(0, min(left if run == "afternoon" else min(1, left), cap))


# ---------------- what people search ----------------
def _skip():
    try:
        import trends
        return trends.SKIP
    except Exception:
        return re.compile(r"\b(election|vote|minister|president|war|shooting|murder|killed|police|court|trial|arrest|cancer|vaccine|"
                          r"crypto|bitcoin|stock|shares|betting|odds|casino|lottery|porn|onlyfans|near me|login|weather)\b", re.I)


def own_terms(root=None, n=12):
    """What people typed into YouTube to find our Shorts (analytics/search_terms.csv), most views first."""
    p = pathlib.Path(root or ROOT) / "analytics" / "search_terms.csv"
    if not p.exists(): return []
    try: rows = sorted(csv.DictReader(p.open()), key=lambda r: -float(r.get("views") or 0))
    except Exception: return []
    return [{"text": r["term"].strip()[:60], "source": "our search traffic", "detail": f"{int(float(r.get('views') or 0))} views"}
            for r in rows if (r.get("term") or "").strip()][:n]


def suggest(q, gl="GB", get=None, timeout=6):
    """YouTube's search suggestions for q (Google's suggest endpoint, free, no key), as writer.suggestions and clips do."""
    import requests
    try:
        r = (get or requests.get)("https://suggestqueries.google.com/complete/search", timeout=timeout, headers=UA,
                                  params={"client": "firefox", "ds": "yt", "hl": "en", "gl": gl, "q": q})
        return [s for s in r.json()[1] if isinstance(s, str)]
    except Exception: return []


def suggestion_queries(turn=0, cfg=None):
    """[(category, query)]: for a rotating handful of categories (categories_per_run), one of its seeds (rotating by turn)
    after each prefix and before "explained": "why does minecraft", "what is minecraft", "how did minecraft", "minecraft
    explained". Different runs ask about different subjects, so the pool keeps changing."""
    c = _cfg(cfg)
    conf = c.get("evergreen_search") or {}
    reg = registry(c)
    cats = sorted(k for k, v in reg.items() if v.get("seeds"))
    if not cats: return []
    per = max(1, min(len(cats), int(conf.get("categories_per_run") or 5)))
    out = []
    for i in range(per):
        cat = cats[(turn * per + i) % len(cats)]
        seeds = reg[cat]["seeds"]
        seed = str(seeds[(turn + i) % len(seeds)]).strip()
        for pre in conf.get("prefixes") or ("why does", "what is", "how did", "explained"):
            out.append((cat, f"{seed} {pre}" if pre == "explained" else f"{pre} {seed}"))
    return out


def suggestions(turn=0, cfg=None, get=None, seconds=None, geos=("GB", "US")):
    """Candidates from YouTube's suggestions for suggestion_queries(), within `seconds` (config evergreen_search.seconds)."""
    c = _cfg(cfg)
    limit = time.monotonic() + float(seconds if seconds is not None else (c.get("evergreen_search") or {}).get("seconds") or 20)
    skip, out = _skip(), []
    for cat, q in suggestion_queries(turn, c):
        for gl in geos:
            if time.monotonic() > limit: return out
            for s in suggest(q, gl, get)[:5]:
                if norm(s) != norm(q) and not skip.search(s): out.append({"text": s.strip(), "source": "YouTube search suggestions", "detail": cat})
    return out


def trends_related(latest):
    """Google Trends related queries, if trends/latest.json carries them (today it holds each trend's query, traffic and two
    headlines only): a list under "related", "related_queries" or "rising" on a trend, of strings or {"query": ...}."""
    out, gt = [], (latest or {}).get("google_trends") or {}
    for geo, rows in (gt.items() if isinstance(gt, dict) else []):
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict): continue
            for key in ("related", "related_queries", "rising"):
                for x in r.get(key) or []:
                    text = x.get("query") if isinstance(x, dict) else x
                    if isinstance(text, str) and text.strip(): out.append({"text": text.strip(), "source": "Google Trends related queries", "detail": geo})
    return out


def on_this_day(latest):
    """Wikipedia's On this day (trend_sources.py marks these kind evergreen): the subject's page and what happened."""
    wf = (latest or {}).get("wikipedia_feed") or {}
    return [{"text": e["page"], "source": "Wikipedia On this day", "detail": str(e.get("text") or "")[:120], "wiki": e.get("url", "")}
            for e in (wf.get("on_this_day") if isinstance(wf, dict) else None) or [] if isinstance(e, dict) and e.get("page")]


def candidates(latest=None, turn=0, cfg=None, root=None, get=None, seconds=None):
    """Everything people search that an evergreen Short could answer, deduplicated, our own search traffic first:
    [{"text", "source", "detail"}]. Each source is optional; one that fails leaves the rest."""
    c = _cfg(cfg)
    skip, seen, out = _skip(), set(), []
    for src in (lambda: own_terms(root, int((c.get("evergreen_search") or {}).get("own_terms") or 12)), lambda: trends_related(latest),
                lambda: suggestions(turn, c, get, seconds), lambda: on_this_day(latest)):
        try: got = src()
        except Exception as e:
            print("search-led source:", str(e)[:100]); continue
        for x in got:
            k = norm(x["text"])
            if not k or k in seen or skip.search(x["text"]): continue
            seen.add(k); out.append(x)
    return out


def lines_of(cands):
    """The candidates as the numbered lines the planner reads."""
    return "\n".join(f"{i}. [{x['source']}" + (f", {x['detail']}" if x.get("detail") else "") + f"] {x['text']}" for i, x in enumerate(cands, 1))


# ---------------- seasonal playbooks ----------------
def load_playbooks(path=None):
    try: d = json.loads(pathlib.Path(path or PLAYBOOKS).read_text())
    except Exception: d = {}
    return d if isinstance(d, dict) and isinstance(d.get("playbooks"), dict) else {"playbooks": {}}


def plan_of(event, path=None):
    return load_playbooks(path)["playbooks"].get(event)


def short_name(event):
    """The event's name for a title: no year, no leading "The", at most 20 characters ("The Hunger Games: Sunrise on the
    Reaping 2026" is "Hunger Games", "Avengers: Doomsday" stays whole)."""
    s = re.sub(r"\s+(19|20)\d\d$", "", str(event).strip())
    s = re.sub(r"^The\s+", "", s)
    if len(s) > 20 and ":" in s and len(s.split(":")[0]) >= 4: s = s.split(":")[0].strip()
    if len(s) > 20: s = s[:20] if s[20] == " " or " " not in s[:20] else s[:20].rsplit(" ", 1)[0]
    return s.strip(" :-") or str(event)[:20]


def playbook_plan(item, level, today, cfg=None):
    """The five-angle plan for one watchlist item: its own angles first, padded with generic ones ("<name> explained"...),
    one a day. {"event", "short", "date", "category", "created", "level", "angles", "of", "playlist_title", "about"}."""
    want = int((_cfg(cfg).get("playbook") or {}).get("angles") or 5)
    event = item["name"]
    angles = []
    for a in list(item.get("angles") or []) + [g.format(name=event) for g in GENERIC_ANGLES]:
        a = str(a).strip()
        if a and norm(a) not in {norm(x) for x in angles}: angles.append(a)
        if len(angles) == want: break
    short = str(item.get("short") or short_name(event))[:30]
    return {"event": event, "short": short, "date": str(item.get("date") or ""), "category": item.get("category", ""),
            "created": str(today), "level": level, "angles": angles, "of": len(angles),
            "playlist_title": f"{event} in {len(angles)} Shorts | Quickplay Daily"[:150],
            "about": f"{len(angles)} Shorts on {event}, one a day."}


def ensure_playbook(item, level, today, path=None, cfg=None):
    """Writes the item's playbook once, when it first reaches launch or surging (watch.run). Returns the plan when it was
    written now, else None."""
    if level not in ("launch", "surging") or not item.get("angles"): return None
    p = pathlib.Path(path or PLAYBOOKS)
    d = load_playbooks(p)
    if item["name"] in d["playbooks"]: return None
    plan = playbook_plan(item, level, today, cfg)
    d["playbooks"][item["name"]] = plan
    d["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    return plan


def progress(event, root=None):
    """{number: created day} of the playbook Shorts written for an event (boards, any folder that counts)."""
    out = {}
    for b in boards(root):
        if b.get("series_kind") == "playbook" and b.get("series_key") == event:
            try: out[int(b.get("series_no"))] = str(b.get("created") or "")
            except (TypeError, ValueError): pass
    return out


def today_angle(event, today=None, path=None, root=None, cfg=None):
    """(number, angle) the playbook offers today, or None. One a day: none once a numbered angle has been written for today's
    posting day. The first angle not yet written whose turn has come (angle k from k-1 days after the plan) and whose
    grace has not run out (grace_days more days; then the series moves on)."""
    plan = plan_of(event, path)
    if not plan: return None
    today = today or dt.datetime.now(UK).date()
    done = progress(event, root)
    if str(today) in done.values(): return None
    try: age = (today - dt.date.fromisoformat(plan["created"])).days
    except (KeyError, ValueError): return None
    grace = int((_cfg(cfg).get("playbook") or {}).get("grace_days", 2))
    for no, angle in enumerate(plan["angles"], 1):
        if no in done or age < no - 1: continue
        if age > no - 1 + grace: continue
        return no, angle
    return None


def playbook_angles(event, path=None):
    plan = plan_of(event, path)
    return list(plan["angles"]) if plan else []


def playbook_match(p, path=None):
    """(plan, number) when a pack is one of a playbook's angles: its signal names the event ("watchlist: <event> (...") and
    its topic is the angle. None otherwise (the event's main topic is not an angle)."""
    sig = str((p or {}).get("signal") or "")
    if not sig.startswith("watchlist: "): return None
    for event, plan in load_playbooks(path)["playbooks"].items():
        if sig.startswith(f"watchlist: {event} "):
            for no, a in enumerate(plan.get("angles") or [], 1):
                if norm(a) == norm(p.get("topic", "")): return plan, no
    return None
