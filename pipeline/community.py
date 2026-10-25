"""The daily community poll (Charlie, 25 October): a reason for viewers to subscribe. Once a day, from config community_hour_utc
(12), the hourly engage run (engage.yml) takes the day's best Short so far, by YouTube views at 3 hours, and writes
status/community.json:
  poll   the Short's engage question (the board's meta.comment) with 2 to 4 short options: "A or B" questions give their A and B,
         "Will you ..." style questions give Yes, No and Not sure, an open question ("Which song ...?") gets a reaction poll
         (Loved it, Liked it, Not for me), because there is no model call here: this is cheap and uses no API
  post   one text line with the Short's link
YouTube has no API for the Community tab, so the Mac posts it (docs/CHROME_JOBS.md, `python3 pipeline/mac_rows.py` lists it while it
is dated today and not posted) and marks it:
  python pipeline/community.py               hourly (engage.yml): make today's poll once, when it is the hour and a Short qualifies
  python pipeline/community.py show          today's poll, as the Mac posts it
  python pipeline/community.py posted        the Mac posted it
  python pipeline/community.py unavailable [why]   the channel has no Community tab yet: no poll for 7 days, then it asks again
Not chosen: a Short that carries a campaign (it is an advert), a sad or serious story, politics, crime, health, money, adult or
gambling words, and a Short that already had a poll in the last 14 days.
Standard library only, so it runs on the Mac as it is.
"""
import csv, datetime as dt, json, pathlib, re, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
PAUSE_DAYS = 7
REPEAT_DAYS = 14
REACTION = {"question": "How did you find today's most watched Short?", "options": ["Loved it", "Liked it", "Not for me"], "kind": "reaction"}
YES_NO = ["Yes", "No", "Not sure"]
KNEW = ["I knew that", "News to me"]
AUX = r"(?:will|would|did|do|does|have|has|had|can|could|is|are|was|were|should|shall|may|might|must)"
WH = r"(?:which|who|whose|whom|what|when|where|why|how)"
KNOW = re.compile(r"^\s*(?:did|do|does) you (?:already )?know\b", re.I)
RATHER = re.compile(r"^\s*would you rather\s+(.+)$", re.I)
SENSITIVE = re.compile(r"\b(sex\w*|porn\w*|gambl\w*|betting|casino\w*|drugs?|cocaine|heroin|drunk|alcohol\w*|murder\w*|rape\w*|terror\w*|"
                       r"politic\w*|election\w*|brexit|trump|biden|crime\w*|arrest\w*|prison\w*|police|lawsuit|invest\w*|crypto\w*|bitcoin|"
                       r"stocks?|diet|cancer|covid|vaccine\w*)\b", re.I)
DASHES = re.compile(r"\s*[" + chr(0x2013) + chr(0x2014) + r"]\s*")


def load(path, default):
    try: return json.loads(pathlib.Path(path).read_text())
    except Exception: return default


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def uk_day(now):
    return now.astimezone(UK).date().isoformat()


def utc(s):
    try: t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError: return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def clean(s):
    """One line, single spaces, no em or en dashes."""
    return re.sub(r"\s+", " ", DASHES.sub(", ", str(s or ""))).strip()


# ---------- the options ----------
def tidy(s):
    s = re.sub(r"\s+", " ", clean(s)).strip(" ,;:.!?\"'")
    return s[:1].upper() + s[1:] if s else ""


def split_or(seg):
    return [o for o in (tidy(p) for p in re.split(r",\s*(?:or\s+)?|\s+or\s+", seg)) if o]


def options(question):
    """2 to 4 short options read off an engage question, or None for an open question."""
    q = clean(question).rstrip("?").strip()
    if not q: return None
    m = RATHER.match(q)
    seg = None
    if m: seg = m.group(1)
    else:
        head, _, tail = q.partition(":")
        has_or = lambda s: re.search(r"\bor\b", s, re.I)
        opens = lambda s, pat: re.match(r"\s*" + pat + r"\b", s, re.I)
        if tail:                                       # "Whose verse wins: A or B"  /  "A, B or C: which surprised you most"
            if has_or(tail) and not opens(tail, WH): seg = tail
            elif has_or(head) and not opens(head, WH) and not opens(head, AUX): seg = head
        elif has_or(q) and not opens(q, WH) and not opens(q, AUX): seg = q                   # "Too long for radio, or perfect as it is"
    if seg is not None:
        opts = split_or(seg)
        ok = 2 <= len(opts) <= 4 and all(len(o) <= 40 for o in opts) and len({o.lower() for o in opts}) == len(opts)
        return opts if ok else None
    if re.match(r"\s*" + AUX + r"\b", q, re.I) and not re.search(r"\bor\b", q, re.I):
        return list(KNEW if KNOW.match(q) else YES_NO)
    return None


def poll_for(question):
    """{question, options, kind}: the engage question itself when options can be read off it, else the reaction poll."""
    q = clean(question)
    opts = options(q)
    if opts and len(q) <= 150: return {"question": q if q.endswith("?") else q + "?", "options": opts, "kind": "question"}
    return dict(REACTION, options=list(REACTION["options"]))


def post_line(title, url):
    t = clean(title)
    t = (t[:97] + "...") if len(t) > 100 else t
    return f"Most watched Short today: {t} {url}"


# ---------- which Short ----------
def board(root, sid):
    for d in ("done", "ready", "queue", "hold"):
        p = root / "boards" / d / f"{sid}.json"
        if p.exists(): return load(p, None)
    return None


def pick(now, root, used=()):
    """The day's best Short so far by views at 3 hours, with its board and question, or None. Today's Shorts (since UK midnight),
    else the last 24 hours; the first with an engage question that is fit for a poll."""
    try: rows = list(csv.DictReader((root / "analytics" / "shorts.csv").open()))
    except OSError: return None
    u = now.astimezone(UK)
    start = dt.datetime(u.year, u.month, u.day, tzinfo=UK).astimezone(dt.timezone.utc)
    seen = []
    for r in rows:
        t, v3 = utc(r.get("posted")), num(r.get("views_3h"))
        if not (str(r.get("short") or "").startswith("QD-") and str(r.get("youtube_url") or "").startswith("http")) or t is None or v3 is None: continue
        if t <= now: seen.append((t, v3, r))
    pool = [x for x in seen if x[0] >= start] or [x for x in seen if x[0] >= now - dt.timedelta(hours=24)]
    pool.sort(key=lambda x: (-x[1], -(num(x[2].get("yt_views")) or 0.0), -x[0].timestamp()))
    try: import sponsor
    except ImportError: sponsor = None
    for t, v3, r in pool:
        sid = r["short"]
        if sid in used: continue
        b = board(root, sid)
        q = clean(((b or {}).get("meta") or {}).get("comment"))
        if not q or SENSITIVE.search(q + " " + str(r.get("title") or "")): continue
        if sponsor and sponsor.sombre(b): continue
        st = load(root / "status" / f"{sid}.json", {})
        if isinstance(st, dict) and isinstance(st.get("sponsor"), dict) and st["sponsor"].get("applied"): continue      # an advert is not promoted here
        return {"short": sid, "title": clean(r.get("title")), "url": r["youtube_url"], "views_3h": int(v3), "question": q}
    return None


# ---------- the file ----------
def fresh(cur, today):
    """The file carried into a new day: the pause and the history, nothing of yesterday's poll."""
    keep = {"history": list(cur.get("history") or [])[-30:], "paused_until": cur.get("paused_until") or ""}
    if cur.get("date") and cur.get("date") != today and cur.get("poll"):
        keep["history"].append({"date": cur["date"], "short": cur.get("short", ""), "kind": (cur.get("poll") or {}).get("kind", ""),
                                "posted": cur.get("posted", ""), "unavailable": cur.get("unavailable", "")})
        keep["history"] = keep["history"][-30:]
    return keep


def refresh(now=None, root=None, write=True):
    """Makes today's poll once: from config community_hour_utc, when no poll is made for today and a Short qualifies. Returns the
    file's state (a dict, possibly yesterday's or empty)."""
    now = now or utcnow(); root = pathlib.Path(root or ROOT)
    out = root / "status" / "community.json"
    cur = load(out, {}) or {}
    today = uk_day(now)
    paused = bool(cur.get("paused_until")) and str(cur["paused_until"]) >= today
    if cur.get("date") == today and (cur.get("poll") or paused): return cur                  # made (or paused) for today: final
    try: hour = int((load(root / "config.json", {}) or {}).get("community_hour_utc", 12))
    except (TypeError, ValueError): hour = 12
    if now.astimezone(dt.timezone.utc).hour < hour: return cur
    state = fresh(cur, today)
    if paused:                                                                                   # the Community tab was not offered: wait
        state.update(date=today)
    else:
        state["paused_until"] = ""
        cutoff = (now - dt.timedelta(days=REPEAT_DAYS)).astimezone(UK).date().isoformat()
        used = {h.get("short") for h in state["history"] if str(h.get("date") or "") >= cutoff}
        p = pick(now, root, used)
        if p is None: return cur                                                                  # nothing fit yet: try again next hour
        poll = poll_for(p["question"])
        state.update(date=today, made=now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), short=p["short"], title=p["title"],
                     url=p["url"], views_3h=p["views_3h"], poll=poll, post=post_line(p["title"], p["url"]), posted="", unavailable="")
    if write:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    return state


def due(now=None, root=None):
    """Lines for the Mac run: today's poll while it is made and not posted (empty otherwise)."""
    now = now or utcnow(); root = pathlib.Path(root or ROOT)
    s = load(root / "status" / "community.json", {})
    if not isinstance(s, dict) or s.get("date") != uk_day(now) or not s.get("poll") or s.get("posted") or s.get("unavailable"): return []
    p = s["poll"]
    return [f"- Text post: {s.get('post')}", f"- Poll: {p.get('question')} Options: " + " | ".join(p.get("options") or [])]


def mark(what, why="", now=None, root=None):
    """The Mac's answer: "posted" or "unavailable". Returns a line to print."""
    now = now or utcnow(); root = pathlib.Path(root or ROOT)
    out = root / "status" / "community.json"
    s = load(out, {})
    today = uk_day(now)
    if not isinstance(s, dict) or s.get("date") != today or not s.get("poll"): return "community: no poll is dated today, nothing marked"
    if what == "posted":
        s["posted"] = f"{now.astimezone(UK):%Y-%m-%d %H:%M}"; s["unavailable"] = ""
        msg = f"community: marked posted ({s.get('short')})"
    else:
        s["unavailable"] = clean(why) or "no Community tab on the channel"
        s["paused_until"] = (now.astimezone(UK).date() + dt.timedelta(days=PAUSE_DAYS)).isoformat()
        msg = f"community: no Community tab ({s['unavailable']}); no poll until after {s['paused_until']}"
    out.write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
    return msg


def main(argv):
    cmd = argv[0] if argv else "refresh"
    if cmd == "posted": print(mark("posted"))
    elif cmd == "unavailable": print(mark("unavailable", " ".join(argv[1:])))
    elif cmd == "show": print("\n".join(due()) or "community: no poll to post today")
    else:
        s = refresh()
        if s.get("date") == uk_day(utcnow()) and s.get("poll"):
            print(f"community: {s.get('short')} ({s.get('views_3h')} views at 3 hours), {s['poll'].get('kind')} poll, " + ("posted " + s["posted"] if s.get("posted") else "waiting for the Mac"))
        else: print("community: no poll yet today")


if __name__ == "__main__":
    main(sys.argv[1:])
