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
"""
import csv, datetime as dt, json, pathlib, re, statistics, sys, urllib.parse
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
            "angles": w.get("angles") or [], "rules": w.get("rules", ""), "terms": terms}


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
        out += [(a, sig) for a in angles][:it.get("places", 1)]
    return out


def run(today=None):
    today = today or dt.date.today()
    prev = {i["name"]: i for i in (state().get("items") or [])}
    got = [measure(w, today) for w in items()]
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
        print(f"watch: {g['name']}: {g['level']}, {g['days_to']} day(s) to go, momentum {g['momentum']}, "
              f"{g['views_yesterday']} Wikipedia views (usual {g['views_usual']}), {g['news_24h']} articles in 24 h, in {g['in'] or 'nothing'}")
        if g["level"] in ("surging", "launch") and (prev.get(g["name"]) or {}).get("level") not in ("surging", "launch"):
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
