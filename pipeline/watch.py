"""The watchlist: big events we know are coming, watched every trends run so the channel is ready before the searches
peak (proactive) and leans in hard when they rise (reactive). Charlie, 23 October: GTA 6 (out 19 November 2026).

usage: python pipeline/watch.py          (trends.yml runs it before trends.py; prints and saves the state)

For each item in config.json "watchlist" it measures, from free sources:
- Wikipedia page views a day for the last 30 days (Wikimedia REST, no key): "momentum" is yesterday against the median
  of the 14 days before (1.0 = normal, 2.0 = twice the usual interest);
- how many reputable news articles named it in the last 24 hours (Google News RSS search);
- whether it is in today's Google Trends, Wikipedia top pages or YouTube charts (trends/latest.json);
- how many YouTube search suggestions it has (what people type).
Then a phase from the date (build-up within the item's "lead_days", 45 unless set, launch from 3 days before to 7 after)
and a level: "surging" when momentum is 1.5 or more, it is in Google Trends, or the news jumps: at least twice its usual
articles a day (the median of the last 7 days in analytics/watch.csv) and 15 or more, once there are 3 days of history (a
big film is written about 100 times a day every day; that is its normal, not a surge); else "steady".
A steady item (far from its date and quiet) is only measured: no topics and no places until it builds up or surges, so
four items on the list never take four forced places a day (a trailer drop or a leak turns it surging that run).

What follows from it (each part reads status/watch.json):
- trends.py adds the item's main term and its angles as topics marked "watchlist", which the fact packs keep like
  Charlie's own requests, so news packs about it are built every run;
- writer.py gives it its own places each day (none steady, 2 in the build-up, 3 when surging, 4 in launch week), outside the
  category shares, with the item's own rules in the brief (for GTA 6: the game as news, never its violence or crime);
  the evergreen planner rides it (top lists and true stories from its series);
- the clips scout adds heat to campaigns about it, and the Mac Chrome run looks for its campaigns to join;
- a GitHub issue the first time an item turns surging; the hub's Watchlist table; analytics/watch.csv keeps every day;
- a seasonal playbook (25 October, pipeline/series.py): the first time an item reaches launch or surging, a mini-series plan
  is written once into status/playbooks.json (its first 5 angles, one a day, numbered "<Event> #1 to #5", each Short added to
  a playlist of the event). topics_today() then offers the day's angle instead of the same first angles every day; they are
  watch topics, so the places above and watch_share_max still apply.
- viral topics (27 October, viral_items below): a topic going viral now, in any category, is pushed for a few days with
  several angles, each angle tested as an arm.
"""
import csv, datetime as dt, json, pathlib, re, statistics, unicodedata, urllib.parse
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
STATE = ROOT / "status" / "watch.json"
HIST = ROOT / "analytics" / "watch.csv"
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
PLACES = {"steady": 0, "build-up": 2, "surging": 3, "launch": 4}


def items():
    return [w for w in CFG.get("watchlist") or [] if w.get("name") and w.get("active", True)]


def pageviews(article, days=30):
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=days - 1)
    u = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
         f"{urllib.parse.quote(article.replace(' ', '_'), safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
    try:
        r = requests.get(u, headers=UA, timeout=20)
        return [int(x.get("views", 0)) for x in r.json().get("items", [])] if r.ok else []
    except Exception: return []


def news_24h(term):
    """Articles naming the term in the last 24 hours (Google News RSS search, UK edition)."""
    try:
        r = requests.get("https://news.google.com/rss/search", params={"q": f'"{term}" when:1d', "hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
                         headers=UA, timeout=20)
        return len(re.findall(r"<item>", r.text)) if r.ok else 0
    except Exception: return 0


def suggestions(term):
    try:
        r = requests.get("https://suggestqueries.google.com/complete/search", timeout=10,
                         params={"client": "firefox", "ds": "yt", "hl": "en", "gl": "GB", "q": term})
        return [s for s in r.json()[1] if isinstance(s, str)]
    except Exception: return []


def in_trends(terms):
    try: t = json.loads((ROOT / "trends" / "latest.json").read_text())
    except Exception: return []
    found = []
    gt = json.dumps(t.get("google_trends") or {}).lower()
    wt = json.dumps(t.get("wikipedia_top") or []).lower()
    yc = json.dumps(t.get("youtube_charts") or {}).lower()
    for term in terms:
        low = term.lower()
        if low in gt and "Google Trends" not in found: found.append("Google Trends")
        if low.replace(" ", "_") in wt or low in wt:
            if "Wikipedia top pages" not in found: found.append("Wikipedia top pages")
        if low in yc and "YouTube charts" not in found: found.append("YouTube charts")
    return found


def phase(w, today):
    """(days to go, phase). Launch runs from 3 days before to "after_days" after (7 unless set: 1 suits a one-day moment
    such as Halloween, 2 an awards night or a match); build-up within "lead_days" (45 unless set)."""
    try: d = (dt.date.fromisoformat(str(w.get("date"))) - today).days
    except Exception: return None, "steady"
    if -int(w.get("after_days") or 7) <= d <= 3: return d, "launch"
    if 0 < d <= int(w.get("lead_days") or 45): return d, "build-up"
    return d, "steady"


def measure(w, today=None):
    today = today or dt.date.today()
    terms = [w["name"]] + [t for t in w.get("terms") or [] if t != w["name"]]
    pv = pageviews(w.get("wikipedia") or w["name"])
    base = statistics.median(pv[-15:-1]) if len(pv) >= 8 else None
    momentum = round(pv[-1] / base, 2) if pv and base else None
    news = max([news_24h(t) for t in terms[:2]] or [0])
    sug = suggestions(terms[0])
    where = in_trends(terms)
    days, ph = phase(w, today)
    usual_news = news_usual(w["name"], today)
    # no news jump until the item has 3 days of its own news history: 24 October, Avengers: Doomsday had 100 articles on its
    # first day and was called surging, but that is its normal (Wikipedia momentum and Google Trends have their own baselines)
    news_jump = usual_news is not None and news >= max(15, 2 * usual_news)
    surging = (momentum or 0) >= 1.5 or news_jump or "Google Trends" in where
    level = "launch" if ph == "launch" else "surging" if surging else ph
    places = PLACES.get(level, 1) if w.get("places") is None else min(PLACES.get(level, 1), int(w["places"]))   # "places": an item's own ceiling
    return {"name": w["name"], "days_to": days, "phase": ph, "level": level, "places": places,
            "momentum": momentum, "views_yesterday": pv[-1] if pv else None, "views_usual": round(base) if base else None,
            "views_30d": pv, "news_24h": news, "news_usual": usual_news, "suggestions": sug[:8], "in": where, "category": w.get("category", ""),
            "angles": w.get("angles") or [], "rules": w.get("rules", ""), "terms": terms, "wikipedia": w.get("wikipedia") or ""}


def news_usual(name, today):
    """The item's usual articles a day: the median of its last 7 days before today in analytics/watch.csv; None with under 3."""
    try: rows = [r for r in csv.DictReader(HIST.open()) if r.get("name") == name and r.get("day", "") < str(today)]
    except Exception: return None
    vals = [float(r["news_24h"]) for r in rows[-7:] if str(r.get("news_24h", "")).replace(".", "", 1).isdigit()]
    return statistics.median(vals) if len(vals) >= 3 else None


def state():
    """The last saved measurement (what trends.py, writer.py and the scout read)."""
    try: return json.loads(STATE.read_text())
    except Exception: return {}


def playbooks_path():
    """status/playbooks.json, next to the state file (a test that moves STATE moves it too)."""
    return STATE.with_name("playbooks.json")


def topics_today(today=None):
    """(topic, signal) pairs for trends.py: for each item in the build-up, surging or launching, its main term and as many
    angles as it has places; a steady item adds nothing (it is only measured). An item with a playbook (series.py) offers
    the one angle that is due today instead of the same first angles every day, in order, one a day; its other angles
    (those outside the playbook) keep their places."""
    out = []
    for it in (state().get("items") or []):
        if it.get("level", "steady") == "steady" or not it.get("places"): continue
        d = it.get("days_to")
        sig = f"watchlist: {it['name']} ({it['level']}" + (f", {d} day{'s' if d != 1 else ''} to go" if d is not None and d > 0 else "") + ")"
        out.append((it["name"], sig))
        angles = list(it.get("angles") or [])
        try:
            import series as SER
            if SER.plan_of(it["name"], playbooks_path()):
                due = SER.today_angle(it["name"], today, playbooks_path())
                if due: out.append((due[1], sig))
                mine = {SER.norm(a) for a in SER.playbook_angles(it["name"], playbooks_path())}
                angles = [a for a in angles if SER.norm(a) not in mine]
        except Exception as e: print("playbook:", str(e)[:120])
        if it.get("viral"):                   # a viral item: its due angles (a daily angle once a day, the others once), then its own
            amap = it.get("angle_map") or {}
            due = [(a, sig) for a in angles if norm(a) in amap and norm(a) != norm(it["name"]) and angle_due(it, amap[norm(a)], today)]
            if it.get("mega"):                # a mega trend: the angles with the fewest Shorts today go first
                due.sort(key=lambda x: angle_count(it, amap[norm(x[0])], today))
            own = [(a, sig) for a in angles if norm(a) not in amap]
            out += due[:int(it.get("places", 1)) + 2] + own[:max(0, int(it.get("places", 1)) - len(due))]
            continue
        out += [(a, sig) for a in angles][:it.get("places", 1)]
    return out


# ---------------- viral topics (27 October) ----------------
# Charlie, 27 October: "the balloon dor is going viral so i need this pushed lots with better content overall, ... who won and
# why and overall discussion around the whole topic ... on a rolling basis ... constantly being tested and assessed to analyse
# what the drivers are for views" and "for any viral topics this is just an example".
# A topic is viral when at least min_sources free source families name it today (Wikipedia top pages, Google Trends in the UK,
# Google Trends abroad, the UK news sections, the YouTube charts, Bluesky) and its Wikipedia interest is a jump on its usual
# (yesterday at least "momentum" times the median of the 14 days before; a brand new page counts). A watchlist item that goes
# viral is lifted to surging with the viral places; anything else safe with a category is added as an "auto" item (at most
# max_items at once). Either keeps going while it stays hot (seen yesterday or today) for up to "days" days, with several
# angles (the news, why, reactions, history and records, explained, facts): each a Short of its own, never repeating what was
# made, recorded on the board as test.viral_angle so analytics/drivers.csv rates the angles ("viral" rates the push itself).
# A "push" angle goes first, a "cut back" one last, a paused one is left out. The Shorts are permitted pictures and narration
# as ever: never event or broadcast footage. Politics, deaths, crime and adult pages are never picked up (no category, the
# trends.SKIP words, the GRIM words below); the fact packs, validate.py and the channel rules check every board as usual.
VIRAL_DEFAULTS = {
    "on": True, "min_wiki_views": 150000, "min_sources": 3, "max_items": 2, "days": 7, "places": 4, "momentum": 2.0,
    "extra_share": 0.2,
    "rules": ("A viral topic: family-friendly news about it exactly as the sources state it, a fresh angle each time. No event or "
              "broadcast footage (permitted pictures and narration only); never predictions, odds or leaks as facts; never "
              "negative about a real person; never about views, popularity or why it is trending; UK English."),
    "angles": [
        {"key": "latest", "topic": "{name}", "repeat": "daily", "brief": "the latest news: what happened, who, when and where"},
        {"key": "why", "topic": "{name} analysis", "repeat": "once",
         "brief": "why it turned out as it did, as the sources explain it (for a result: why the winner won and what decided it)"},
        {"key": "reaction", "topic": "{name} reaction", "repeat": "daily",
         "brief": "how the people involved and the fans reacted, quoted as the sources quote them"},
        {"key": "records", "topic": "{name} history and records", "repeat": "once",
         "brief": "the history behind it and the records it set or matched"},
        {"key": "explained", "topic": "{name} explained", "repeat": "once",
         "brief": "what it is and how it works, for someone who has only just heard of it"},
        {"key": "facts", "topic": "{name} facts", "repeat": "daily", "brief": "the most surprising facts in the sources"},
    ],
    # a mega trend (Charlie, 27 October: "the ballon d'or has 92.84 momentum ... there should like 5-10 different shorts about
    # it ... real time adaption to large trends was part of the original goal"): yesterday's Wikipedia views at least 20 times
    # their usual give 5 places a day, 50 times 8, 90 times (or 500,000 views on a jump) 10. Momentum alone qualifies it (no
    # 3 sources needed). The places come on top of the day's number; a fitting channel (its categories) adds 1 to 3 angles of
    # its own; a breaking check that sees one writes up to 4 at once. It follows the current tier while the surge holds,
    # keeps half its peak while momentum is still over end_below, and ends under it or "days" after it began.
    "mega": {"tiers": [[20, 5], [50, 8], [90, 10]], "views": 500000, "end_below": 3, "breaking_writes": 4,
             "channel_angles": 3, "repeat": 2},
    "mega_angles": [
        {"key": "people", "topic": "{name} star", "repeat": "daily",
         "brief": "the person at the centre of it (the winner, the star or the maker): their story as the sources tell it"},
        {"key": "rankings", "topic": "{name} rankings", "repeat": "daily",
         "brief": "the full list or ranking (the top three to five) in order, exactly as the sources give it"},
        {"key": "numbers", "topic": "{name} by the numbers", "repeat": "daily",
         "brief": "the numbers: votes, scores, figures and records, as the sources give them"},
        {"key": "moments", "topic": "{name} best moments", "repeat": "daily",
         "brief": "the standout moments, told from the sources in words and permitted pictures (no footage)"},
        {"key": "next", "topic": "{name} what happens next", "repeat": "daily",
         "brief": "what comes next, the dates and plans the sources state (never predictions)"},
        {"key": "past", "topic": "{name} past winners", "repeat": "once",
         "brief": "the earlier editions or the ones that came before, and how this one compares"},
    ],
}
VIRAL_STATE = None                  # status/viral.json next to STATE (viral_path); a test may set its own
LATEST = ROOT / "trends" / "latest.json"
BOARDS = ROOT / "boards"
UNSAFE = re.compile(r"\b(porn\w*|xxx|adult|sex|sexy|nude\w*|naked|onlyfans|explicit|nsfw|erotic\w*)\b", re.I)
GRIM = re.compile(r"\b(died|dies|death|dead|tribute\w*|funeral|obituar\w*|passed away|tragedy|tragic|mourn\w*|killed|"
                  r"prison|jail|jailed|fraud\w*|sentenced|convicted|charged|lawsuit|sued|guilty|arrested)\b", re.I)
META = re.compile(r"^(deaths in|list of|main page|special|portal|wikipedia|file|xxxx)\b", re.I)
NEWS_CAT = {"sports": "Sport", "entertainment": "Entertainment", "technology": "Tech", "science": "Science"}
CHART_CAT = {"sport": "Sport", "gaming": "Gaming", "music": "Music", "entertainment": "Entertainment", "tech": "Tech"}
PAREN_CAT = [(r"film", "Film"), (r"video game|game", "Gaming"), (r"song|album|singer|band|rapper|musician", "Music"),
             (r"tv series|tv programme|tv program|series|show", "Entertainment"), (r"footballer|football|cricketer|tennis|athlete", "Sport")]


def viral_cfg():
    c = dict(VIRAL_DEFAULTS); c.update(CFG.get("viral") or {})
    c["mega"] = dict(VIRAL_DEFAULTS["mega"], **(c.get("mega") or {}))
    return c


def all_angles(cfg=None):
    """Every angle: the viral ones, then the mega trend ones."""
    cfg = cfg or viral_cfg()
    return list(cfg.get("angles") or []) + list(cfg.get("mega_angles") or [])


def mega_places(momentum, views=None, cfg=None):
    """A mega trend's places a day from yesterday's Wikipedia momentum (its tiers) or views (the top tier, on a jump: a
    momentum of at least the viral one, or a page too new for one); 0 when it is not one."""
    cfg = cfg or viral_cfg()
    mc = cfg["mega"]
    tiers = sorted((float(t), int(n)) for t, n in mc.get("tiers") or [])
    if not tiers: return 0
    best = 0
    for t, n in tiers:
        if momentum is not None and float(momentum) >= t: best = max(best, n)
    try: v = float(views or 0)
    except (TypeError, ValueError): v = 0
    if v >= float(mc.get("views") or 1e12) and (momentum is None or float(momentum) >= float(cfg["momentum"])):
        best = max(best, tiers[-1][1])
    return best


def mega_level(s, momentum, views, today, cfg=None):
    """Today's mega places for a viral topic's state s (updated in place): the current tier while the surge holds, half its
    peak (at least 2) while momentum is still at end_below or more, else 0; never more than "days" after it began."""
    cfg = cfg or viral_cfg()
    mc = cfg["mega"]
    since = s.get("mega_since")
    try: age = (today - dt.date.fromisoformat(since)).days if since else 0
    except ValueError: age, since = 0, None
    if since and age >= int(cfg["days"]): return 0
    tier = mega_places(momentum, views, cfg)
    if tier:
        if not since: s["mega_since"] = str(today)
        s["mega_peak"] = max(int(s.get("mega_peak") or 0), tier)
        return tier
    if since and momentum is not None and float(momentum) >= float(mc.get("end_below") or 3):
        return max(2, -(-int(s.get("mega_peak") or 0) // 2))
    return 0


def norm(s):
    """Lower case without accents or punctuation: "Ballon d’Or" and "BALLON D'OR" are both "ballon d or"."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in s if not unicodedata.combining(c)).lower()))


def bare(s):
    """norm without a leading or trailing year: "2026 Ballon d'Or" and "Ballon d'Or 2026" are both "ballon d or"."""
    return re.sub(r"^(19|20)\d\d\s+|\s+(19|20)\d\d$", "", norm(s)).strip()


def _title(page):
    """("Clayface", "film") from "Clayface (film)"."""
    t = str(page or "").replace("_", " ").strip()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", t)
    return (m.group(1).strip(), m.group(2).strip().lower()) if m else (t, "")


def _rules():
    """trends.SKIP (politics, crime, money, adult, practical searches) and validate.NEGATIVE, with a fallback each."""
    try: from trends import SKIP
    except Exception: SKIP = re.compile(r"\b(election|vote|minister|president|war|police|court|crypto|betting|porn)\b", re.I)
    try: from validate import NEGATIVE
    except Exception: NEGATIVE = re.compile(r"\b(admits?|slam\w*|feud\w*|scandal\w*|backlash|mock\w*)\b", re.I)
    return SKIP, NEGATIVE


def _texts(latest):
    """Every text the free sources gave today: [(family, text, category hint)]."""
    out = []
    for cc, rows in (latest.get("google_trends") or {}).items():
        fam = "Google Trends" if cc == "GB" else "Google Trends abroad"
        for r in rows or []:
            if not isinstance(r, dict): continue
            out.append((fam, r.get("q", ""), ""))
            out += [(fam, h if isinstance(h, str) else (h or {}).get("title", ""), "") for h in r.get("news") or []]
    for sec, heads in (latest.get("google_news_uk") or {}).items():
        out += [("UK news", h if isinstance(h, str) else (h or {}).get("title", ""), NEWS_CAT.get(sec, "")) for h in heads or []]
    for ch, rows in (latest.get("youtube_charts") or {}).items():
        cat = CHART_CAT.get(ch.split("-", 1)[1] if "-" in ch else "", "")
        out += [("YouTube charts", (r or {}).get("title", ""), cat) for r in rows or [] if isinstance(r, dict)]
    out += [("Bluesky", (r or {}).get("topic", ""), "") for r in latest.get("bluesky") or [] if isinstance(r, dict)]
    return [(f, t, c) for f, t, c in out if t]


def _momentum(pv):
    """Yesterday against the median of the 14 days before; a page under 8 days old with its views counts as a jump (None)."""
    if len(pv) < 8: return None
    base = statistics.median(pv[-15:-1])
    return round(pv[-1] / base, 2) if base else None


def _verdicts():
    """analytics/drivers.csv verdicts of the viral angles: {angle: verdict}."""
    try: return {r.get("value"): str(r.get("verdict") or "") for r in csv.DictReader((ROOT / "analytics" / "drivers.csv").open(encoding="utf-8"))
                 if r.get("feature") == "viral_angle"}
    except Exception: return {}


def angle_order(cfg, first_seen, today, mega=False):
    """The angles to offer, best first: a "push" verdict first, a "cut back" one last, a paused one left out (unless all
    are); the rest rotate a step a day so a different angle leads each day. mega: the mega trend angles too."""
    v = _verdicts()
    keys = [a["key"] for a in (all_angles(cfg) if mega else cfg["angles"])]
    if not keys: return []
    k = max(0, (today - first_seen).days) % len(keys)
    keys = keys[k:] + keys[:k]
    live = [x for x in keys if not v.get(x, "").startswith(("pause", "stop"))] or keys
    return sorted(live, key=lambda x: 0 if v.get(x, "").startswith("push") else 2 if v.get(x, "").startswith("cut back") else 1)


def viral_path():
    """status/viral.json, next to the state file (a test that moves STATE moves it too)."""
    return VIRAL_STATE or STATE.with_name("viral.json")


def _viral_state():
    try: return json.loads(viral_path().read_text())
    except Exception: return {}


def viral_items(today, got, latest=None, pv=None):
    """Mark today's viral topics: lifts the matching watch items in got (in place) and returns the auto items to add.
    latest: trends/latest.json (read when None); pv: the page views function (pageviews; a test passes a stub)."""
    cfg = viral_cfg()
    if not cfg.get("on", True): return []
    pv = pv or pageviews
    if latest is None:
        try: latest = json.loads(pathlib.Path(LATEST).read_text())
        except Exception: latest = {}
    SKIP, NEGATIVE = _rules()
    texts = [(f, t, c, f" {norm(t)} ") for f, t, c in _texts(latest)]
    cands = {}                                    # bare name: {title, paren, views, page, trend}
    for r in latest.get("wikipedia_top") or []:
        t, paren = _title(r.get("page"))
        key = bare(t)
        try: views = int(r.get("views") or 0)
        except (TypeError, ValueError): views = 0
        if not key or META.search(t) or views < int(cfg["min_wiki_views"]): continue
        c = cands.setdefault(key, {"title": t, "paren": paren, "views": 0, "page": r.get("page"), "top": 0, "trend": False})
        c["views"] += views
        if views > c["top"]: c.update(top=views, page=r.get("page"), paren=paren or c["paren"])
    for r in (latest.get("google_trends") or {}).get("GB") or []:
        key = bare((r or {}).get("q", ""))
        if key and key not in cands: cands[key] = {"title": r["q"], "paren": "", "views": 0, "page": None, "top": 0, "trend": True}
    st = _viral_state()
    watch = {g["name"]: g for g in got}
    wkeys = {}
    for w in items():
        for t in [w["name"], w.get("wikipedia") or ""] + list(w.get("terms") or []):
            if bare(t): wkeys.setdefault(bare(t), w["name"])
    chosen, autos = [], []                        # (name, term) of the items picked today
    order = sorted(cands.items(), key=lambda kv: (kv[0] not in wkeys, -kv[1]["views"]))
    for key, c in order:
        if len(key.replace(" ", "")) < 5 and " " not in key: continue          # "f1", "ufc": too short to match safely
        wname = wkeys.get(key)
        if SKIP.search(c["title"]) or UNSAFE.search(c["title"]) or UNSAFE.search(c["page"] or "") or META.search(c["title"]): continue
        hits = [x for x in texts if f" {key} " in x[3]]
        fams = sorted({x[0] for x in hits} | ({"Wikipedia top pages"} if c["page"] else set()))
        pm = None                                 # the page's momentum, when read
        if len(fams) < int(cfg["min_sources"]):   # too few sources: only a mega trend (momentum alone) goes on
            if wname: mega = mega_places(watch.get(wname, {}).get("momentum"), watch.get(wname, {}).get("views_yesterday"), cfg)
            elif c["page"]: pm = _momentum(pv(c["page"])); mega = mega_places(pm, c["top"], cfg)
            else: mega = 0
            if not mega: continue
        heads = [x[1] for x in hits]
        bad = sum(1 for h in heads if SKIP.search(h) or (not wname and NEGATIVE.search(h)))
        grim = sum(1 for h in heads if GRIM.search(h))
        if heads and bad * 3 >= len(heads): continue
        if (grim and not wname) or (wname and heads and grim * 3 >= len(heads)) or GRIM.search(c["title"]): continue
        if wname:
            m = watch.get(wname, {}).get("momentum")
            if m is not None and m < float(cfg["momentum"]) and not c["trend"]: continue
            if any(n == wname for n, _ in chosen): continue
            chosen.append((wname, key)); continue
        if any(sum(1 for h in heads if f" {k} " in f" {norm(h)} ") * 2 >= max(1, len(heads)) for _, k in chosen): continue   # part of a story already picked
        cats = [x[2] for x in hits if x[2]] + [cat for pat, cat in PAREN_CAT if c["paren"] and re.search(pat, c["paren"])][:1] * 2
        if not cats: continue                     # no category: politics, world news or a person with no story of ours
        m = None
        if c["page"]:
            m = pm if pm is not None else _momentum(pv(c["page"]))
            if m is not None and m < float(cfg["momentum"]): continue
        if sum(1 for n, _ in chosen if n not in watch) >= int(cfg["max_items"]): continue
        name = re.sub(r"\s+", " ", c["title"]).strip()
        chosen.append((name, key))
        autos.append({"name": name, "category": max(set(cats), key=cats.count), "terms": [name], "wiki": c["page"], "in": fams,
                      "momentum": m, "views": c["top"] or None})
    for g in got:                                 # a watch item surging that hard is a mega trend whatever the sources say
        if not any(n == g["name"] for n, _ in chosen) and mega_places(g.get("momentum"), g.get("views_yesterday"), cfg):
            chosen.append((g["name"], bare(g["name"])))
    # the rolling state: a topic stays while it was hot yesterday or today, for up to "days" days from its first day
    for name, key in chosen:
        s = st.get(name) or {}
        try: gap = (today - dt.date.fromisoformat(s.get("last_hot", ""))).days
        except ValueError: gap = 99
        if gap > 3: s = {"first_seen": str(today)}
        s.update(last_hot=str(today), key=key, watch=name in watch)
        a = next((x for x in autos if x["name"] == name), None)
        if a: s.update(category=a["category"], terms=a["terms"], wiki=a["wiki"], momentum=a["momentum"], views=a["views"], **{"in": a["in"]})
        st[name] = s
    live = {}
    for name, s in st.items():
        try: hot = (today - dt.date.fromisoformat(s["last_hot"])).days; age = (today - dt.date.fromisoformat(s["first_seen"])).days
        except (KeyError, ValueError): continue
        if hot <= 1 and age < int(cfg["days"]): live[name] = s
    st = {n: s for n, s in st.items() if s.get("last_hot", "") >= str(today - dt.timedelta(days=30))}
    out = []
    for name, s in live.items():
        first = dt.date.fromisoformat(s["first_seen"])
        g = watch.get(name)
        if g is None and s.get("watch"): continue            # a watch item taken off the list
        m = g.get("momentum") if g is not None and g.get("momentum") is not None else s.get("momentum")
        mega = mega_level(s, m, (g or {}).get("views_yesterday") or s.get("views"), today, cfg)
        keys = angle_order(cfg, first, today, mega=bool(mega))
        topics = {k: next(a for a in all_angles(cfg) if a["key"] == k)["topic"].format(name=name) for k in keys}
        amap = {norm(t): k for k, t in topics.items()}
        if g is None:
            g = {"name": name, "auto": True, "days_to": None, "phase": "viral", "momentum": m, "views_yesterday": s.get("views"),
                 "views_usual": None, "views_30d": [], "news_24h": None, "news_usual": None, "suggestions": [],
                 "in": s.get("in") or [], "category": s.get("category", ""), "terms": s.get("terms") or [name], "angles": [],
                 "rules": cfg["rules"], "wikipedia": s.get("wiki")}
            out.append(g)
        else:
            g["rules"] = (str(g.get("rules") or "") + " " + cfg["rules"]).strip()
        g.update(viral=True, viral_since=s["first_seen"], angle_map=amap, mega=mega,
                 level=g.get("level") if g.get("level") == "launch" else "surging",
                 places=max(int(g.get("places") or 0), int(cfg["places"]), mega))
        if mega: g.update(mega_since=s.get("mega_since"), mega_peak=s.get("mega_peak"))
        mine = list(topics.values())
        own = [a for a in g.get("angles") or [] if norm(a) not in amap]
        g["angles"] = mine + (own if (g.get("days_to") is None or g["days_to"] > 0) else [])
    try: viral_path().parent.mkdir(exist_ok=True); viral_path().write_text(json.dumps(st, indent=1, ensure_ascii=False))
    except Exception as e: print("viral state:", str(e)[:120])
    return out


def viral_key(p, items=None):
    """The viral angle of a topic (a fact pack or a trends topic: its "topic" and "signal"), or None."""
    s = str(p.get("signal", ""))
    if not s.startswith("watchlist: "): return None
    for it in (items if items is not None else (state().get("items") or [])):
        if it.get("viral") and s.startswith(f"watchlist: {it['name']} "):
            return (it.get("angle_map") or {}).get(norm(p.get("topic", "")))
    return None


def mega_item(p, items=None):
    """The watch item of a mega trend a topic belongs to (its signal names an item with mega places today), or None."""
    s = str(p.get("signal", ""))
    if not s.startswith("watchlist: "): return None
    for it in (items if items is not None else (state().get("items") or [])):
        if it.get("mega") and s.startswith(f"watchlist: {it['name']} ("): return it
    return None


_MADE = {}


def board_title(b):
    """A board's title: boards keep it in meta.title (a top-level "title" only on older or hand-made ones)."""
    return str(b.get("title") or (b.get("meta") or {}).get("title") or "") if isinstance(b, dict) else ""


_MEGA_N = None


def mega_boards(day, channel="main", fresh=False):
    """How many Shorts of a mega trend a channel's day (the boards' "created" date) holds, in every board folder but
    expired: the Shorts written on top of the day's number (writer.py), so plan.py adds a slot for each and quota.py keeps
    room for them, and they go out that day. The folders are read once a process (`fresh` reads them again)."""
    global _MEGA_N
    if _MEGA_N is None or fresh:
        _MEGA_N = {}
        for d in ("queue", "ready", "done", "failed"):
            for f in (BOARDS / d).glob("QD-*.json"):
                try:
                    txt = f.read_text()
                    if '"mega"' not in txt: continue
                    b = json.loads(txt)
                except Exception: continue
                if b.get("mega"):
                    k = (str(b.get("created") or "")[:10], b.get("channel") or "main")
                    _MEGA_N[k] = _MEGA_N.get(k, 0) + 1
    return _MEGA_N.get((str(day)[:10], channel), 0)


def _made_key(name, channel="main"):
    """viral_made's key: the item's name for the main channel, "<channel>:<name>" for another (a fitting channel's own angles
    of a mega trend never use the main channel's)."""
    return name if (channel or "main") == "main" else f"{channel}:{name}"


def viral_made(name, channel="main"):
    """[(created, angle, title)] of the viral Shorts a channel already made about an item (every board folder), oldest first."""
    if not _MADE:
        _MADE[None] = True
        for d in ("queue", "ready", "done", "failed", "expired"):
            for f in (BOARDS / d).glob("*.json"):
                try:
                    txt = f.read_text()
                    if '"viral_angle"' not in txt: continue
                    b = json.loads(txt)
                except Exception: continue
                k = (b.get("test") or {}).get("viral_angle") if isinstance(b.get("test"), dict) else None
                if k and b.get("watch") and not b.get("mirror_of"):      # a Spanish mirror is the same Short
                    _MADE.setdefault(_made_key(b["watch"], b.get("channel")), []).append((str(b.get("created") or ""), k, board_title(b)))
        for v in _MADE.values():
            if isinstance(v, list): v.sort()
    return list(_MADE.get(_made_key(name, channel)) or [])


def angle_count(item, key, today=None, extra=(), channel="main"):
    """How many Shorts an angle already has where it counts: today for a daily angle, since the push began for a once one.
    extra: boards written in this run, not yet in the folders. channel: whose Shorts (each channel has its own count)."""
    today = str(today or dt.date.today())
    rep = next((a.get("repeat", "daily") for a in all_angles() if a["key"] == key), "daily")
    made = [(c, k) for c, k, _ in viral_made(item["name"], channel)]
    made += [(str(b.get("created") or ""), (b.get("test") or {}).get("viral_angle")) for b in extra
             if b.get("watch") == item["name"] and isinstance(b.get("test"), dict) and (b.get("channel") or "main") == channel
             and not b.get("mirror_of")]
    if rep == "once": return sum(1 for c, k in made if k == key and c >= str(item.get("viral_since") or ""))
    return sum(1 for c, k in made if k == key and c == today)


def angle_due(item, key, today=None, extra=()):
    """Whether an angle is due: a daily one when none was made for today, a once one when none since the item went viral.
    A mega trend's daily angle may run mega.repeat times a day (each from different sources: the writer's covered check)."""
    rep = next((a.get("repeat", "daily") for a in all_angles() if a["key"] == key), "daily")
    n = angle_count(item, key, today, extra)
    if rep == "once": return n == 0
    return n < (max(1, int(viral_cfg()["mega"].get("repeat", 1))) if item.get("mega") else 1)


def viral_titles(item, extra=(), n=8):
    """The latest titles already made about a viral item since it went viral, on every channel (the writer's "do not repeat"
    list)."""
    since = str(item.get("viral_since") or "")
    viral_made(item["name"])                                                  # fills _MADE
    keys = [k for k in _MADE if isinstance(k, str) and (k == item["name"] or k.endswith(":" + item["name"]))]
    got = [(c, t) for k in keys for c, _, t in _MADE[k] if c >= since]
    got += [(str(b.get("created") or ""), board_title(b)) for b in extra if b.get("watch") == item["name"]]
    return [t for _, t in sorted(got) if t][-n:]


def run(today=None):
    today = today or dt.date.today()
    prev = {i["name"]: i for i in (state().get("items") or [])}
    got = [measure(w, today) for w in items()]
    try: got += viral_items(today, got)        # viral topics: watch items lifted in place, auto items added
    except Exception as e: print("viral:", str(e)[:160])
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "items": got},
                                indent=1, ensure_ascii=False))
    for g in got:                       # a seasonal playbook is written once, the first time an item reaches launch or surging
        w = next((i for i in items() if i["name"] == g["name"]), None)
        if not w or g["level"] not in ("launch", "surging"): continue
        try:
            import series as SER
            plan = SER.ensure_playbook(w, g["level"], today, playbooks_path())
            if plan: print(f"watch: {g['name']}: playbook of {plan['of']} angles, one a day: " + "; ".join(plan["angles"]))
        except Exception as e: print("playbook:", str(e)[:120])
    rows = list(csv.DictReader(HIST.open())) if HIST.exists() else []
    fields = ["day", "name", "level", "days_to", "momentum", "views_yesterday", "views_usual", "news_24h", "suggestions", "in"]
    for g in got:
        rows = [r for r in rows if not (r["day"] == str(today) and r["name"] == g["name"])]
        rows.append({"day": str(today), "name": g["name"], "level": g["level"], "days_to": g["days_to"], "momentum": g["momentum"],
                     "views_yesterday": g["views_yesterday"], "views_usual": g["views_usual"], "news_24h": g["news_24h"],
                     "suggestions": len(g["suggestions"]), "in": "; ".join(g["in"])})
    with HIST.open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields); wr.writeheader(); wr.writerows(rows[-2000:])
    for g in got:
        if g.get("viral"): print(f"viral: {g['name']} ({'auto, ' if g.get('auto') else ''}{g.get('category')}) since {g.get('viral_since')}: "
                                 f"{g['places']} places" + (f" (MEGA trend, peak {g.get('mega_peak')} since {g.get('mega_since')})" if g.get('mega') else "")
                                 + ", angles " + ", ".join((g.get('angle_map') or {}).values()))
        print(f"watch: {g['name']}: {g['level']}, {g['days_to']} day(s) to go, momentum {g['momentum']}, "
              f"{g['views_yesterday']} Wikipedia views (usual {g['views_usual']}), {g['news_24h']} articles in 24 h, in {g['in'] or 'nothing'}")
        if g["level"] in ("surging", "launch") and (prev.get(g["name"]) or {}).get("level") not in ("surging", "launch") and not g.get("auto"):
            note_surge(g)
    return got


def note_surge(g):
    """One GitHub issue when an item first turns surging (needs the gh CLI and GH_TOKEN, as on GitHub)."""
    import subprocess
    title = f"🔥 {g['name']} is {g['level']}: the channel is leaning in"
    body = (f"{g['name']}: momentum {g['momentum']} (Wikipedia {g['views_yesterday']} views yesterday against {g['views_usual']} usually), "
            f"{g['news_24h']} news articles in 24 hours, in {', '.join(g['in']) or 'no chart yet'}. The writer now gives it "
            f"{g['places']} places a day and the clips scout favours its campaigns. Nothing to do; the hub's Watchlist shows it.")
    try: subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], capture_output=True, timeout=60)
    except Exception: pass


if __name__ == "__main__":
    run()
