"""How every Short is doing on YouTube, Instagram and TikTok, in one place.

Writes analytics/ (read by the daily writer and the reviews, and uploaded to the stats dashboard):
  shorts.csv     one row per Short: when, topic, format, and views, likes, comments, shares on each platform,
                 YouTube average % viewed, engaged views and subscribers gained, views per hour since posting,
                 retention (share still watching 3 seconds in and at the end), views 1 to 72 hours after posting,
                 views against Shorts posted around the same time, top countries
  daily.csv      one row per day and platform: views, followers, followers gained
  hourly.csv     views gained each hour (UK time), by platform and by category: when the audience watches
  curves/        each Short's views hour by hour for its first week (then every few hours to 30 days)
  geo.csv, traffic.csv, audience.csv   where viewers are, how they found us, age and gender (channel and category)
  search_terms.csv  what people typed into YouTube search to find our Shorts (the writer plans more of these)
  drivers.csv    what drives views: every choice (category, format, hook, length, time, look) against typical
  decisions.csv  every change made from the data, with the reason (written here when a result turns, and by reviews)
  summary.json   totals, monetisation progress (YouTube Partner Program, TikTok Creator Rewards) and the latest numbers
  insights.md    what's working, what drives views, and the recipe the writer follows
Only the channel's own numbers are read; tokens are never written out. Each platform is optional: one that isn't
connected (or fails) is noted in summary.json and the rest still run.
usage: python pipeline/analytics.py [--fast]
  --fast  hourly: fresh view counts, hourly and curve snapshots; YouTube Analytics (retention, countries, traffic),
          Instagram insights older than 3 days, insights.md and drivers come from the last full run (3 a day)
"""
import csv, datetime as dt, io, json, math, os, pathlib, statistics, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
OUT = ROOT / "analytics"
CFG = json.loads((ROOT / "config.json").read_text())
CACHE = OUT / "cache"          # the last full run's YouTube Analytics and Instagram insights, reused by fast runs
FAST = "--fast" in sys.argv
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.date()
YPP_DEADLINE = dt.date(2027, 2, 1)     # after this, new applicants need 20M Shorts views in 90 days instead of 10M

def utc(s):
    if not s: return None
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError: return None

def load_json(p, default=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return default

# ---------------- our own records ----------------
IG_TESTS = ("ig_trial", "ig_caption", "ig_hour", "ig_pick", "ig_posted", "ig_hour_uk")


def ig_tests(st):
    """The Instagram post's own tests (social.py, 24 October) for shorts.csv: trial reel (yes, no, refused), caption arm
    (full, short), posting hour arm (morning, any), how it was picked (category, explore, order) and when it went to
    Instagram (UTC time and UK hour). Blank for a Short not on Instagram or posted before the tests."""
    ig = st.get("instagram") if isinstance(st.get("instagram"), dict) else {}
    return {"ig_trial": ig.get("trial", ""), "ig_caption": ig.get("caption", ""), "ig_hour": ig.get("hour", ""),
            "ig_pick": ig.get("pick", ""), "ig_posted": ig.get("at", ""), "ig_hour_uk": ig.get("hour_uk", "")}


def late_label(st, b):
    """"late" or "on time" for a time-sensitive Short (freshness.py: late means public after the day it was written for),
    "" for evergreen kinds, so drivers.csv compares late news with news on time and the late-upload rule follows the data."""
    import freshness as FR
    if FR.kind_of(b) not in FR.TIMELY or b.get("reserve"): return ""
    return "late" if st.get("late") else "on time"

def our_shorts():
    """Status files and boards: what each Short was (category, format, mood, hook, words) keyed by YouTube id."""
    boards = {}
    for d in ("done", "ready", "queue", "failed", "rejected", "reserve", "hold", "expired"):
        for p in (ROOT / "boards" / d).glob("*.json"):
            b = load_json(p, {})
            if b.get("id"): boards[b["id"]] = b
    out = {}
    for p in (ROOT / "status").glob("*.json"):
        st = load_json(p, {})
        if not isinstance(st, dict) or not st.get("video"): continue      # only Short status files (a list file broke this, 23 October)
        b = boards.get(st.get("id"), {})
        beats = b.get("beats") or []
        hook = beats[0].get("say", "") if beats else ""
        out[st["video"]] = {
            "id": st.get("id"), "title": st.get("title") or b.get("meta", {}).get("title", ""),
            "category": b.get("category", ""), "format": b.get("format", ""),
            "mood": (b.get("music") or {}).get("mood", ""), "hook": hook, "hook_words": len(hook.split()), "follow_line": (b.get("test") or {}).get("follow_line", ""), **{k: (b.get(k, "") if k in ("kind", "source", "appeal") else (b.get("test") or {}).get(k, "")) for k in ("ending", "title_search", "first_frame", "angles", "replies", "kind", "source", "series", "franchise", "appeal", "explore", "title_emoji")}, "writer": b.get("writer", ""), "editor": b.get("editor", ""),
            "late": late_label(st, b),
            "words": sum(len(bt.get("say", "").split()) for bt in beats), "seconds": (st.get("qa") or {}).get("duration"),
            "hashtags": len((b.get("meta") or {}).get("hashtags") or []),
            "instagram_media": (st.get("instagram") or {}).get("media"), "tiktok": bool(st.get("tiktok")), **ig_tests(st),
            # where the Short came from (pipeline, backlog, manual). Until 24 October this was "source", which overwrote the
            # board's topic source above, so the "Topic source" driver was never scored.
            "origin": st.get("source", "pipeline"), "timeline": st.get("timeline"),
            "real_share": round((st.get("media") or {}).get("real_shots", 0) / max(1, sum(len(bt.get("shots") or []) for bt in beats)), 2)
                          if st.get("media") and beats else ""}
    legacy = load_json(OUT / "legacy.json", {}) or {}       # Shorts from before the pipeline kept boards
    for vid, o in out.items():
        if not o["category"] and o["id"] in (legacy.get("by_id") or {}):
            o.update(category=legacy["by_id"][o["id"]], format=o["format"] or "legacy")
    for vid, cat in (legacy.get("by_video") or {}).items():
        out.setdefault(vid, {"id": "", "title": "", "category": cat, "format": "legacy", "mood": "", "hook": "", "hook_words": "",
                             "words": "", "seconds": "", "hashtags": "", "instagram_media": None, "tiktok": False,
                             "origin": "manual", "timeline": None, "real_share": ""})
    return out

# ---------------- YouTube ----------------
def youtube(ours=None):
    import youtube as Y
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    yt = Y.client()
    ch = yt.channels().list(part="statistics,snippet", mine=True).execute()["items"][0]
    subs = int(ch["statistics"].get("subscriberCount", 0))
    vids = {v["id"]: v for v in Y.recent_videos(yt, limit=500)}
    # fresher totals than Analytics (which lags a day or two)
    stats = {}
    ids = list(vids)
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()["items"]:
            s = v.get("statistics", {})
            stats[v["id"]] = {"views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                              "comments": int(s.get("commentCount", 0))}
    cache_p = CACHE / "youtube.json"
    if FAST:        # YouTube Analytics only moves once or twice a day: reuse the last full run's answers
        c = load_json(cache_p, {}) or {}
        return {"subs": subs, "videos": vids, "stats": stats, "analytics": c.get("analytics") or {},
                "daily": c.get("daily") or [], "audience": c.get("audience") or {}, "cached_at": c.get("at"),
                "retention": {v: {float(k): x for k, x in cv.items()} for v, cv in (c.get("retention") or {}).items()},
                "sources": c.get("sources") or {}}
    ya = build("youtubeAnalytics", "v2", credentials=Y.creds(), cache_discovery=False)
    start = str(TODAY - dt.timedelta(days=120))

    def query(metrics, since=None, **kw):
        """Run an Analytics query; drop engagedViews if this API version doesn't know it."""
        try:
            r = ya.reports().query(ids="channel==MINE", startDate=since or start, endDate=str(TODAY), metrics=metrics, **kw).execute()
        except HttpError as e:
            if "engagedViews" in metrics:
                return query(metrics.replace("engagedViews,", "").replace(",engagedViews", ""), since, **kw)
            raise
        cols = [c["name"] for c in r.get("columnHeaders", [])]
        return [dict(zip(cols, row)) for row in r.get("rows", []) or []]

    per_video = {r["video"]: r for r in query(
        "views,engagedViews,averageViewPercentage,averageViewDuration,likes,comments,shares,subscribersGained",
        dimensions="video", sort="-views", maxResults=200)}
    daily = query("views,engagedViews,subscribersGained,subscribersLost", dimensions="day", sort="day")
    # retention curve per Short (2 to 30 days old; YouTube Analytics lags a day or two): share of viewers still watching
    # at each point, as {fraction of the video: ratio}. Ratios above 1 mean people rewatched that part (loops).
    retention, sources = {}, {}
    for vid, v in vids.items():
        posted = utc(v.get("publish_at")) or utc(v.get("uploaded"))
        if v.get("privacy") != "public" or not posted or not (dt.timedelta(days=2) <= NOW - posted <= dt.timedelta(days=30)):
            continue
        try: curve = query("audienceWatchRatio", dimensions="elapsedVideoTimeRatio", filters=f"video=={vid}")
        except Exception: continue
        if curve: retention[vid] = {float(r["elapsedVideoTimeRatio"]): float(r["audienceWatchRatio"]) for r in curve}
        try:            # where this Short's views came from (Shorts feed, search, channel page...): did the feed pick it up?
            src = query("views", dimensions="insightTrafficSourceType", filters=f"video=={vid}")
            if src: sources[vid] = {r["insightTrafficSourceType"]: int(r.get("views") or 0) for r in src}
        except Exception: pass
    aud = audience(query, vids, ours or {})
    # the long-form route to the Partner Programme (8,000 watch hours in 365 days from 1 February 2027; 4,000 before):
    # watch time on long videos only (the weekly video), as YouTube counts it
    try:
        lf = query("estimatedMinutesWatched", since=str(TODAY - dt.timedelta(days=365)), filters="creatorContentType==VIDEO_ON_DEMAND")
        aud["longform_watch_hours_365d"] = round(sum(float(r.get("estimatedMinutesWatched") or 0) for r in lf) / 60, 1)
    except Exception as e:
        aud["longform_watch_hours_365d"] = None; print("long-form watch hours:", str(e)[:120])
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_p.write_text(json.dumps({"at": NOW.isoformat(timespec="minutes"), "analytics": per_video, "daily": daily,
                                   "audience": aud, "retention": {v: {str(k): x for k, x in cv.items()} for v, cv in retention.items()},
                                   "sources": sources}, ensure_ascii=False))
    return {"subs": subs, "videos": vids, "stats": stats, "analytics": per_video, "daily": daily, "retention": retention,
            "audience": aud, "cached_at": NOW.isoformat(timespec="minutes"), "sources": sources}

def audience(query, vids, ours):
    """Where viewers are, how they found the Shorts, and their age and gender: for the channel, for each category (a
    query filtered to that category's videos), and each Short's share from the channel's top 5 countries. About 30
    queries; any that YouTube refuses (too little data yet, or an unsupported combination) is skipped and noted."""
    out, errs = {"channel": {}, "categories": {}, "short_countries": {}}, []
    def q(label, *a, **kw):
        try: return query(*a, **kw)
        except Exception as e: errs.append(f"{label}: {type(e).__name__}: {str(e)[:120]}"); return []
    out["channel"]["countries"] = q("countries", "views,averageViewPercentage", dimensions="country", sort="-views", maxResults=25)
    out["channel"]["country_subs"] = q("country subscribers", "subscribersGained", dimensions="country", sort="-subscribersGained", maxResults=25)
    out["channel"]["traffic"] = q("traffic", "views", dimensions="insightTrafficSourceType", sort="-views")
    out["channel"]["search_terms"] = q("search terms", "views", dimensions="insightTrafficSourceDetail",
                                       filters="insightTrafficSourceType==YT_SEARCH", sort="-views", maxResults=25)
    out["channel"]["demographics"] = q("demographics", "viewerPercentage", dimensions="ageGroup,gender")
    cats = {}
    for vid, o in ours.items():
        if vid in vids and vids[vid].get("privacy") == "public" and o.get("category"): cats.setdefault(o["category"], []).append(vid)
    for cat, ids in sorted(cats.items()):
        f = "video==" + ",".join(ids[:200])
        out["categories"][cat] = {
            "shorts": len(ids),
            "countries": q(f"{cat} countries", "views", dimensions="country", filters=f, sort="-views", maxResults=10),
            "traffic": q(f"{cat} traffic", "views", dimensions="insightTrafficSourceType", filters=f, sort="-views"),
            "demographics": q(f"{cat} demographics", "viewerPercentage", dimensions="ageGroup,gender", filters=f)}
    for row in out["channel"]["countries"][:8]:
        cc = row.get("country")
        for r in q(f"videos in {cc}", "views", dimensions="video", filters=f"country=={cc}", sort="-views", maxResults=200):
            out["short_countries"].setdefault(r["video"], {})[cc] = r.get("views", 0)
    out["errors"] = errs
    return out

def ratio_at(curve, frac):
    return curve[min((k for k in curve if k >= frac), default=max(curve))]

def drops(curve, timeline, secs):
    """Viewers lost per second during each beat (percentage points), skipping the first 3 seconds (swipe-aways are
    the hook's job) and beats under a second: [(loss per second, beat index, what was on screen)]."""
    out = []
    for i, (b0, b1, vis, _shots) in enumerate(timeline or []):
        b0 = max(b0, 3.0)
        if b1 - b0 < 1.0 or not secs: continue
        r0, r1 = ratio_at(curve, b0 / secs), ratio_at(curve, min(1.0, b1 / secs))
        out.append((round(100 * (r0 - r1) / (b1 - b0), 2), i, vis if vis and vis != "none" else "footage"))
    return out

def at_point(curve, frac):
    """The retention ratio at a fraction of the video (the first measured point at or after it), as a percentage, at most
    100. YouTube's audienceWatchRatio counts replays, so on 24 October 31 of 35 Shorts read over 100% at 3 seconds (up to
    319%): a loop is not a viewer who stayed, so the share is capped."""
    if not curve: return ""
    k = min((k for k in curve if k >= frac), default=max(curve))
    return round(100 * min(1.0, curve[k]))

# ---------------- Instagram ----------------
REEL_METRICS = ("ig_reels_avg_watch_time", "reels_skip_rate", "reposts", "facebook_views")

def instagram():
    if len(os.environ.get("SOCIAL_KEY", "")) < 20: return None
    import requests, social
    t = social.load("instagram") or ({"token": os.environ["IG_TOKEN"], "user": os.environ.get("IG_USER_ID", "")}
                                     if os.environ.get("IG_TOKEN") else None)
    if not t: return None
    tok = t["token"]; api = social.IG_API
    me = requests.get(f"{api}/me", params={"fields": "user_id,username,followers_count,media_count", "access_token": tok}, timeout=30).json()
    if "error" in me: raise RuntimeError(me["error"].get("message", "instagram error"))
    user = t.get("user") or me.get("user_id")
    media, url = [], f"{api}/{user}/media"
    params = {"fields": "id,caption,media_product_type,timestamp,permalink,like_count,comments_count", "limit": 50, "access_token": tok}
    while url and len(media) < 300:
        r = requests.get(url, params=params, timeout=30).json()
        media += r.get("data", []); url = (r.get("paging") or {}).get("next"); params = None
    insights_error = None
    cache_p = CACHE / "instagram.json"; cache = load_json(cache_p, {}) or {}
    keys = ("views", "reach", "shares", "saved", "total_interactions") + REEL_METRICS
    if str(cache.get("_reel_metrics_at", "")) < str(TODAY - dt.timedelta(days=7)): cache.pop("_reel_metrics", None)   # relearn weekly
    reel_ok = list(cache.get("_reel_metrics") or REEL_METRICS)      # the Reels metrics the API still answers
    def value(d): return (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
    for m in media:
        posted = utc(m.get("timestamp"))
        if FAST and m["id"] in cache and posted and NOW - posted > dt.timedelta(days=3):
            m.update(cache[m["id"]]); continue           # older Reels move slowly: hourly runs reuse the last full run
        r = requests.get(f"{api}/{m['id']}/insights", params={"metric": "views,reach,shares,saved,total_interactions",
                                                              "access_token": tok}, timeout=30).json()
        if "error" in r: insights_error = r["error"].get("message", "")[:200]; continue
        for d in r.get("data", []): m[d["name"]] = value(d)
        # Reels-only metrics, asked apart so a refusal costs nothing else: average watch time, and (24 October) the share
        # of views skipped inside 3 seconds (reels_skip_rate, the only direct hook measure any platform's API gives),
        # reposts, and the plays of the Reel on Facebook when it is crossposted (facebook_views)
        if not FAST and m.get("media_product_type") == "REELS" and reel_ok:
            w = requests.get(f"{api}/{m['id']}/insights", params={"metric": ",".join(reel_ok), "access_token": tok}, timeout=30).json()
            if "error" in w and not cache.get("_reel_metrics"):         # one retired or unknown metric fails the ask: find the rest, once
                ok, w = [], {"data": []}
                for name in REEL_METRICS:
                    q = requests.get(f"{api}/{m['id']}/insights", params={"metric": name, "access_token": tok}, timeout=30).json()
                    if "error" not in q: ok.append(name); w["data"] += q.get("data", [])
                reel_ok = ok
                if ok: cache["_reel_metrics"], cache["_reel_metrics_at"] = ok, str(TODAY)     # none answering may be a passing fault
            for d in w.get("data", []) if "error" not in w else []: m[d["name"]] = value(d)
        cache[m["id"]] = {**cache.get(m["id"], {}), **{k: m[k] for k in keys if k in m}}
    CACHE.mkdir(parents=True, exist_ok=True); cache_p.write_text(json.dumps(cache))
    return {"followers": me.get("followers_count"), "username": me.get("username"), "media": media, "insights_error": insights_error}

# ---------------- Facebook ----------------
FB_METRICS = ("fb_reels_total_plays", "blue_reels_play_count", "post_video_avg_time_watched")

def facebook():
    """The Page's followers and each of our Reels' plays and average watch time, read with the Page key used for posting
    (GitHub secrets FB_PAGE_TOKEN and FB_PAGE_ID); None until those exist. Hourly runs refresh a Reel at most every 3 hours
    in its first 3 days, full runs every Reel up to 30 days old, so a new Page stays well inside Meta's call limits."""
    import requests, social
    fb = social.fb_tokens()
    if not fb: return None
    api, tok = social.FB_API, fb["token"]
    page = requests.get(f"{api}/{fb['page']}", params={"fields": "name,followers_count,fan_count", "access_token": tok}, timeout=30).json()
    if "error" in page: raise RuntimeError(page["error"].get("message", "facebook error"))
    cache_p = CACHE / "facebook.json"; cache = load_json(cache_p, {}) or {}
    metrics, reels, insights_error, blocked = cache.get("_metrics") or list(FB_METRICS), {}, None, False
    def ask(vid, names):
        return requests.get(f"{api}/{vid}/video_insights", params={"metric": ",".join(names), "access_token": tok}, timeout=30).json()
    for sp in sorted((ROOT / "status").glob("QD-*.json")):
        st = load_json(sp, {}) or {}
        f = st.get("facebook") or {}
        vid = f.get("video")
        if not vid: continue
        seen, posted = cache.get(vid) or {}, utc(f.get("at"))
        age = NOW - posted if posted else dt.timedelta(0)
        recent = bool(seen.get("at")) and NOW - utc(seen["at"]) < dt.timedelta(hours=3)
        if seen and (blocked or age > dt.timedelta(days=30) or (FAST and (age > dt.timedelta(days=3) or recent))):
            reels[st["id"]] = seen; continue
        if blocked: continue
        r = ask(vid, metrics)
        if "error" in r:            # one retired metric fails the whole ask: find the ones that still work, once
            r, ok = {"data": []}, []
            for m in FB_METRICS:
                q = ask(vid, [m])
                if "error" in q: insights_error = q["error"].get("message", "")[:200]; continue
                ok.append(m); r["data"] += q.get("data", [])
            if not ok: blocked = True; continue          # no insights at all (e.g. read_insights not granted): stop asking
            cache["_metrics"] = metrics = ok
        got = {d["name"]: (d.get("values") or [{}])[0].get("value") for d in r.get("data", [])}
        plays, w = got.get("fb_reels_total_plays", got.get("blue_reels_play_count")), got.get("post_video_avg_time_watched")
        reels[st["id"]] = cache[vid] = {"views": plays if plays is not None else "",
                                        "avg_watch_s": round(w / 1000, 1) if isinstance(w, (int, float)) else "",
                                        "at": NOW.isoformat(timespec="minutes")}
    CACHE.mkdir(parents=True, exist_ok=True); cache_p.write_text(json.dumps(cache))
    return {"followers": page.get("followers_count", page.get("fan_count")), "name": page.get("name"), "reels": reels,
            "insights_error": insights_error}

# ---------------- put it together ----------------
def norm(s):
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (s or "")).split())

def num(x):
    try: return int(float(x))
    except (TypeError, ValueError): return None

def rkey(r):
    """A Short's key in curves and caches: our id, or the YouTube id for Shorts uploaded outside the pipeline."""
    return r["short"] or r["youtube_url"].rsplit("/", 1)[-1]

# ---------------- timing: each Short's views hour by hour, and the channel's views each hour ----------------
VEL_HOURS = (1, 3, 6, 12, 24, 48, 72)

def update_curves(rows):
    """analytics/curves/<day posted>.json: {short: {video, posted, points: [[hours since posting, YouTube, Instagram,
    Facebook views]]}}. A point every run (hourly) for a Short's first 7 days, then one every 6 hours up to 30 days."""
    d = OUT / "curves"; d.mkdir(exist_ok=True)
    files = {f.stem: load_json(f, {}) or {} for f in d.glob("*.json")}
    changed = set()
    for r in rows:
        posted = utc(r["posted"])
        if not posted: continue
        age = (NOW - posted).total_seconds() / 3600
        day = posted.strftime("%Y-%m-%d")
        c = files.setdefault(day, {}).setdefault(rkey(r), {"video": r["youtube_url"].rsplit("/", 1)[-1], "posted": r["posted"], "points": []})
        if age > 30 * 24 or (FAST and age > 7 * 24): continue
        pts, h = c["points"], round(age, 1)
        if not pts or h - pts[-1][0] >= (0.5 if age <= 7 * 24 else 6):
            pts.append([h, r["yt_views"], num(r["ig_views"]), num(r["fb_views"])]); changed.add(day)
    for day in changed:
        (d / f"{day}.json").write_text(json.dumps(files[day], separators=(",", ":")))
    return {k: c for f in files.values() for k, c in f.items()}

def views_at(curve, hours):
    """YouTube views `hours` after posting, read off the curve (0 at posting); None if the curve doesn't cover it."""
    pts = (curve or {}).get("points") or []
    if not pts or pts[0][0] > hours + 0.75 or pts[-1][0] < hours: return None
    prev = (0.0, 0)
    for h, v, *_ in pts:
        if h >= hours:
            h0, v0 = prev
            return round(v0 + (v - v0) * (hours - h0) / (h - h0)) if h > h0 else v
        prev = (h, v)
    return None

BREAKOUT_FIELDS = ["short", "title", "category", "hours_public", "views", "typical_at_this_age", "times_typical", "youtube_url",
                   "trigger", "views_3h", "typical_3h"]


def early_break(r, recent, curves):
    """(views at 3 hours, typical at 3 hours) when a Short's first 3 hours put it in the top fifth of the last 7 days'
    Shorts at the same age, at 2 times their median or more and at least breakout_3h_min_views (20); else None. 24 October,
    on our own curves: of 89 Shorts this flagged 13 (15%), 10 of them in the top fifth by 24 hours and the other 3 at
    3 to 4 times the median Short, hours before the 24-hour numbers exist (the data report: views at 3 hours pick the top
    fifth with 92% accuracy; breakouts were being flagged 9 to 28 hours in)."""
    v3 = views_at(curves.get(rkey(r)), 3)
    if v3 is None: return None
    t = utc(r["posted"])
    peers = [p for p in (views_at(curves.get(rkey(x)), 3) for x in recent if x is not r and utc(x["posted"]) and utc(x["posted"]) < t)
             if p is not None]
    if len(peers) < 10: return None
    q80 = sorted(peers)[int(0.8 * len(peers))]; med = max(1.0, statistics.median(peers))
    if v3 >= max(q80 + 1, float(CFG.get("breakout_times", 2)) * med, int(CFG.get("breakout_3h_min_views", 20))): return v3, med
    return None


def breakouts(rows, curves):
    """analytics/breakouts.csv: the Shorts to follow up while their topic is hot (the writer's hot(), CLAUDE.md What gets
    views), 2 to 48 hours old, by either trigger:
      - "3 hours" (24 October, the data report's act-at-3-hours): early_break, the top fifth at 3 hours;
      - "views for age": breakout_times (config, 2) or more the views recent Shorts had at the same age (the hourly
        curves, 5 or more peers), with at least breakout_min_views (150).
    times_typical is the ratio of the trigger that fired (the stronger when both)."""
    out, recent = [], [r for r in rows if r["posted"] and (NOW - utc(r["posted"])).total_seconds() <= 7 * 86400]
    for r in recent:
        age = (NOW - utc(r["posted"])).total_seconds() / 3600
        if not 2 <= age <= 48: continue
        hit = None
        peers = [p for p in (views_at(curves.get(rkey(x)), age) for x in recent if x is not r) if p is not None]
        if len(peers) >= 5:
            typ = max(1.0, statistics.median(peers)); ratio = r["yt_views"] / typ
            if ratio >= float(CFG.get("breakout_times", 2)) and r["yt_views"] >= int(CFG.get("breakout_min_views", 150)):
                hit = {"trigger": "views for age", "typical_at_this_age": round(typ), "times_typical": round(ratio, 1)}
        early = early_break(r, recent, curves) if age >= 3 else None
        if early and (hit is None or early[0] / early[1] > hit["times_typical"]):
            hit = {"trigger": "3 hours", "typical_at_this_age": round(early[1]), "times_typical": round(early[0] / early[1], 1)}
        if hit:
            out.append({"short": r["short"], "title": r["title"], "category": r["category"], "hours_public": round(age, 1),
                        "views": r["yt_views"], "youtube_url": r["youtube_url"], **hit,
                        "views_3h": early[0] if early else (views_at(curves.get(rkey(r)), 3) or ""),
                        "typical_3h": round(early[1]) if early else ""})
    out.sort(key=lambda b: -b["times_typical"])
    write_csv(OUT / "breakouts.csv", out, BREAKOUT_FIELDS)
    return out

def peers_of(r, pool, field):
    """`field` for the Shorts posted the same UK day as r (r included), widening to ±36 hours, then ±3 days, while there
    are fewer than 3. Same-day peers take out the day's luck (24 October: with ±3 days 21% of the variance in views
    against peers sat between posting days, with the same UK day 2%)."""
    t = utc(r["posted"]); day = t.astimezone(UK).date()
    for near in (lambda x: utc(x["posted"]).astimezone(UK).date() == day,
                 lambda x: abs((utc(x["posted"]) - t).total_seconds()) <= 36 * 3600,
                 lambda x: abs((utc(x["posted"]) - t).total_seconds()) <= 3 * 86400):
        peers = [float(x[field]) for x in pool if x.get(field) not in ("", None) and near(x)]
        if len(peers) >= 3: return peers
    return []

def relative(rows, field, out_field, min_age_h=24):
    """Each Short's `field` against the median of the Shorts posted the same UK day (peers_of; 1.0 = typical)."""
    aged = [r for r in rows if r["posted"] and r.get(field) not in ("", None) and (NOW - utc(r["posted"])).total_seconds() >= min_age_h * 3600]
    for r in rows:
        r[out_field] = ""
        if r not in aged: continue
        peers = peers_of(r, aged, field)
        if peers and statistics.median(peers): r[out_field] = round(float(r[field]) / statistics.median(peers), 3)

CATS = ["Gaming", "Film", "Music", "Sport", "Tech", "Science", "Entertainment", "Animals", "Food", "Cars", "History"]

def update_hourly(rows, ig, fb):
    """analytics/hourly.csv: one row per hour (UTC, with UK day, hour and weekday) with the views gained since the last
    run on each platform and, for YouTube, in each category. 60 days kept."""
    p = OUT / "hourly.csv"
    hist = list(csv.DictReader(io.StringIO(p.read_text()))) if p.exists() else []
    last = load_json(CACHE / "last.json", {}) or {}
    prev_at, prev = utc(last.get("at")), last.get("yt") or {}
    hour = NOW.replace(minute=0, second=0, microsecond=0); ukh = hour.astimezone(UK)
    ig_total = sum(num(r["ig_views"]) or 0 for r in rows); fb_total = sum(num(r["fb_views"]) or 0 for r in rows)
    row = {"hour_utc": hour.strftime("%Y-%m-%dT%H:00Z"), "uk_day": ukh.strftime("%Y-%m-%d"), "uk_hour": ukh.strftime("%H"),
           "uk_weekday": ukh.strftime("%a"), "yt_total": sum(r["yt_views"] for r in rows),
           "ig_total": ig_total if ig else "", "fb_total": fb_total if fb else ""}
    if prev_at:
        row["hours"] = round((NOW - prev_at).total_seconds() / 3600, 2)
        gained = {c: 0 for c in CATS + ["Other"]}
        for r in rows:
            k = rkey(r); posted = utc(r["posted"])
            base = prev.get(k, 0 if posted and posted > prev_at - dt.timedelta(minutes=5) else None)
            if base is None: continue                           # public before the last run but not counted then: skip
            gained[r["category"] if r["category"] in CATS else "Other"] += max(0, r["yt_views"] - base)
        row["yt_gained"] = sum(gained.values())
        for c, g in gained.items(): row[f"yt_{c.lower()}"] = g
        row["ig_gained"] = max(0, ig_total - last["ig_total"]) if ig and last.get("ig_total") is not None else ""
        row["fb_gained"] = max(0, fb_total - last["fb_total"]) if fb and last.get("fb_total") is not None else ""
    if hist and hist[-1]["hour_utc"] == row["hour_utc"] and "hours" in row:     # a second run within the same hour adds to it
        old = hist.pop()
        for k in ["hours", "yt_gained", "ig_gained", "fb_gained"] + [f"yt_{c.lower()}" for c in CATS + ["Other"]]:
            a, b = old.get(k), row.get(k)
            if a not in ("", None) and b not in ("", None): row[k] = round(float(a) + float(b), 2) if k == "hours" else int(float(a)) + int(b)
    hist.append(row)
    cutoff = (NOW - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H")
    hist = [h for h in hist if h["hour_utc"] >= cutoff]
    write_csv(p, hist, ["hour_utc", "uk_day", "uk_hour", "uk_weekday", "hours", "yt_total", "yt_gained", "ig_total", "ig_gained",
                        "fb_total", "fb_gained"] + [f"yt_{c.lower()}" for c in CATS + ["Other"]])
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "last.json").write_text(json.dumps({"at": NOW.isoformat(timespec="seconds"), "yt": {rkey(r): r["yt_views"] for r in rows},
                                                 "ig_total": ig_total if ig else None, "fb_total": fb_total if fb else None}))
    return hist

# ---------------- where, how found, who: from the full run's YouTube Analytics ----------------
TRAFFIC = {"SHORTS": "Shorts feed", "YT_SEARCH": "YouTube search", "SUBSCRIBER": "Subscribers", "EXT_URL": "Outside YouTube",
           "RELATED_VIDEO": "Suggested videos", "YT_CHANNEL": "Channel page", "NO_LINK_OTHER": "Direct or unknown",
           "PLAYLIST": "Playlists", "NOTIFICATION": "Notifications", "YT_OTHER_PAGE": "Other YouTube pages",
           "BROWSE": "Browse features", "HASHTAGS": "Hashtag pages", "SOUND_PAGE": "Sound pages", "END_SCREEN": "End screens"}

REGION_DIMS = [("category", "Category"), ("format", "Format"), ("hook_type", "Hook"), ("length", "Length")]
EARLY_REGION_VIEWS = 1000

def regions(rows, aud):
    """What works where: for each of our 8 biggest countries, its share of views, how much of each Short its viewers watch,
    the subscribers it brought, and the category, format, hook style and length that get it the most views per Short
    against that country's own average (shrunk towards 1x for small samples, so one lucky Short can't decide it).
    From each Short's views per country (YouTube lists the top 8 countries' Shorts). Returns csv rows and insight lines."""
    ch = (aud or {}).get("channel") or {}
    countries = ch.get("countries") or []
    if not countries: return [], []
    tot = sum(float(r.get("views") or 0) for r in countries) or 1
    subs = {r.get("country"): int(float(r.get("subscribersGained") or 0)) for r in ch.get("country_subs") or []}
    per = (aud or {}).get("short_countries") or {}
    measured = [r for r in rows if utc(r.get("posted")) and (NOW - utc(r["posted"])).total_seconds() >= 24 * 3600]
    def length(r):
        x = num(r.get("seconds"))
        return "" if x is None else ("under 30 s" if x < 30 else "30 to 40 s" if x <= 40 else "over 40 s")
    out, lines = [], []
    for c in countries[:8]:
        cc, views = c.get("country"), float(c.get("views") or 0)
        vals = [(r, float((per.get(r["youtube_url"].rsplit("/", 1)[-1]) or {}).get(cc, 0))) for r in measured]
        base = sum(v for _, v in vals) / len(vals) if vals else 0
        best = {}
        for dim, label in REGION_DIMS:
            groups = {}
            for r, v in vals:
                key = length(r) if dim == "length" else str(r.get(dim) or "")
                if key and key != "legacy": groups.setdefault(key, []).append(v)
            scored = []
            for key, vs in sorted(groups.items()):
                lift = round(((sum(vs) + 3 * base) / (len(vs) + 3)) / base, 2) if base else 1.0
                out.append({"kind": "fit", "country": cc, "dimension": label, "value": key, "shorts": len(vs),
                            "views": int(sum(vs)), "views_per_short": round(sum(vs) / len(vs), 1), "lift": lift})
                scored.append((lift, len(vs), key))
            top = max((x for x in scored if x[1] >= 2), default=None)
            best[dim] = f"{top[2]} ({top[0]:.1f}x, {top[1]} Shorts)" if top and top[0] >= 1.1 else ""
        r_top, v_top = max(vals, key=lambda x: x[1], default=(None, 0))
        avg = c.get("averageViewPercentage")
        row = {"kind": "country", "country": cc, "views": int(views), "share_pct": round(100 * views / tot, 1),
               "avg_viewed_pct": round(float(avg), 1) if avg is not None else "", "subs_gained": subs.get(cc, ""),
               "shorts_seen": sum(1 for _, v in vals if v > 0), "best_category": best["category"], "best_format": best["format"],
               "best_hook": best["hook_type"], "best_length": best["length"],
               "top_short": f"{r_top['title']} ({int(v_top)} views)" if r_top and v_top > 0 else ""}
        out.append(row)
        bits = [b for b in (f"category {best['category']}" if best["category"] else "", f"format {best['format']}" if best["format"] else "",
                            f"hook {best['hook_type']}" if best["hook_type"] else "") if b]
        lines.append(f"- {cc}: {row['share_pct']:g}% of views" + (f", {row['avg_viewed_pct']:g}% watched on average" if avg is not None else "")
                     + (f", {row['subs_gained']} subscribers" if row["subs_gained"] != "" else "")
                     + (". Does best with " + "; ".join(bits) if bits else ". No clear winner yet")
                     + (f". Top Short: {row['top_short']}." if row["top_short"] else "."))
    head = [f"## Regions: who watches and what works for them ({int(tot):,} views with a country; YouTube only names countries with enough viewers)"]
    if tot < EARLY_REGION_VIEWS:
        head.append(f"Early: under {EARLY_REGION_VIEWS:,} views with a country, so these are hints, not rules. A country's viewers "
                    "often come for one Short about their own star; check the top Short before reading it as a taste.")
    return out, head + lines + [""]

def write_audience(aud):
    if not aud: return
    def shares(rows, key, val):
        tot = sum(float(r.get(val) or 0) for r in rows) or 1
        return [(r.get(key), float(r.get(val) or 0), round(100 * float(r.get(val) or 0) / tot, 1)) for r in rows]
    scopes = [("channel", aud.get("channel") or {})] + [(f"category: {c}", v) for c, v in sorted((aud.get("categories") or {}).items())]
    geo, trf, demo = [], [], []
    for scope, a in scopes:
        geo += [{"scope": scope, "country": k, "views": int(v), "share_pct": p} for k, v, p in shares(a.get("countries") or [], "country", "views")]
        trf += [{"scope": scope, "source": TRAFFIC.get(k, (k or "").replace("_", " ").title()), "views": int(v), "share_pct": p}
                for k, v, p in shares(a.get("traffic") or [], "insightTrafficSourceType", "views")]
        demo += [{"scope": scope, "age": (r.get("ageGroup") or "").replace("age", "").replace("-", " to "),
                  "gender": r.get("gender", ""), "viewer_pct": round(float(r.get("viewerPercentage") or 0), 1)}
                 for r in a.get("demographics") or []]
    write_csv(OUT / "geo.csv", geo, ["scope", "country", "views", "share_pct"])
    write_csv(OUT / "traffic.csv", trf, ["scope", "source", "views", "share_pct"])
    terms = [{"term": r.get("insightTrafficSourceDetail", ""), "views": int(float(r.get("views") or 0))}
             for r in (aud.get("channel") or {}).get("search_terms") or [] if r.get("insightTrafficSourceDetail")]
    if terms: write_csv(OUT / "search_terms.csv", terms, ["term", "views"])     # what people typed into YouTube to find us
    write_csv(OUT / "audience.csv", demo, ["scope", "age", "gender", "viewer_pct"])

# ---------------- decisions: every change made from the data, with its reason ----------------
DEC_FIELDS = ["date", "area", "change", "why", "evidence", "check_on", "by"]

ACTING = ("push", "cut back", "pause", "retest", "stop")      # the verdicts that change what the writer does

def log_decisions(table, method=""):
    """When a driver's verdict turns to or from one the writer acts on ("push", "cut back", "pause", "retest"), add a line
    to decisions.csv: the writer's recipe changes with it, so Charlie can see what changed and why. Moves between "early
    sign" and "about typical" change nothing the writer does and are not logged (24 October: 180 automatic decisions in 7
    days, most of them noise). A new judging method (`method`, drivers.METHOD) is one line, not one per verdict it moves.
    Reviews add their own lines."""
    p, vp = OUT / "decisions.csv", CACHE / "verdicts.json"
    prev = load_json(vp, {}) or {}
    cur = {f"{t['feature']}|{t['value']}": t for t in table if t["n"] >= 5}
    rows = list(csv.DictReader(io.StringIO(p.read_text()))) if p.exists() else []
    today = str(NOW.astimezone(UK).date()); check = str(NOW.astimezone(UK).date() + dt.timedelta(days=7))
    state = lambda: {**{k: {"verdict": t["verdict"], "lift": t["lift"], "n": t["n"]} for k, t in cur.items()},
                     **({"_method": method} if method else {})}
    if method and prev.get("_method") != method:
        acting = [t for t in cur.values() if t["verdict"] in ACTING]
        was = sum(1 for k, v in prev.items() if not k.startswith("_") and (v or {}).get("verdict") in ACTING)
        rows.append({"date": today, "area": "How the data is judged", "change": f"New judging rule: {method}",
                     "why": f"{len(acting)} verdicts the writer acts on now, against {was} before (the old rule's were mostly noise)",
                     "evidence": ("drivers.py docstring and SHRINK_NOTE; now " +
                                  ", ".join(f"{t['verdict']} {t['feature']} {t['value']}" for t in acting))[:400],
                     "check_on": check, "by": "analytics (automatic)"})
        vp.write_text(json.dumps(state()))
        rows.sort(key=lambda r: r["date"], reverse=True)
        write_csv(p, rows, DEC_FIELDS); return
    for k, t in cur.items():
        was = (prev.get(k) or {}).get("verdict")
        if t["verdict"] == was or (t["verdict"] not in ACTING and was not in ACTING): continue
        if t["verdict"] == "push": change = f"Lean towards {t['feature_label'].lower()} \"{t['value']}\""
        elif t["verdict"] == "cut back": change = f"Use less {t['feature_label'].lower()} \"{t['value']}\""
        elif t["verdict"] == "pause": change = f"Pause {t['feature_label'].lower()} \"{t['value']}\" for 14 days, then retest it"
        elif t["verdict"] == "retest": change = f"Retest {t['feature_label'].lower()} \"{t['value']}\" on a small share"
        else: change = f"Back to normal for {t['feature_label'].lower()} \"{t['value']}\""
        why = f"{t['lift']}x typical views over {t['n']} Shorts" + (f" ({t['why']})" if t.get("why") else "")
        rows.append({"date": today, "area": t["feature_label"], "change": change, "why": why,
                     "evidence": f"drivers.csv: {t['feature']} = {t['value']}, n {t['n']}, lift {t['lift']}, median {t['median_rel']}",
                     "check_on": check, "by": "analytics (automatic)"})
    vp.write_text(json.dumps(state()))
    rows.sort(key=lambda r: r["date"], reverse=True)
    write_csv(p, rows, DEC_FIELDS)

# ---------------- put it together ----------------
def main():
    import drivers as DRV
    OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
    errors, ours = {}, our_shorts()
    yt = ig = fb = None
    try: yt = youtube(ours)
    except Exception as e: errors["youtube"] = f"{type(e).__name__}: {e}"[:300]
    try: ig = instagram()
    except Exception as e: errors["instagram"] = f"{type(e).__name__}: {e}"[:300]
    try: fb = facebook()
    except Exception as e: errors["facebook"] = f"{type(e).__name__}: {e}"[:300]
    if not yt and FAST:
        print(json.dumps({"errors": errors})); return          # nothing fresh to write: keep the last good files

    rows = []
    aud = (yt or {}).get("audience") or {}
    short_cc = aud.get("short_countries") or {}
    ig_by_id = {m["id"]: m for m in (ig or {}).get("media", [])}
    ig_by_title = {norm((m.get("caption") or "").split("\n")[0]): m for m in (ig or {}).get("media", [])}
    fb_reels = (fb or {}).get("reels") or {}
    for vid, v in ((yt or {}).get("videos") or {}).items():
        if v.get("privacy") != "public": continue
        o = ours.get(vid, {})
        posted = utc(v.get("publish_at")) or utc(v.get("uploaded"))
        hours = max(1.0, (NOW - posted).total_seconds() / 3600) if posted else None
        s, a = yt["stats"].get(vid, {}), yt["analytics"].get(vid, {})
        key = norm(v["title"])
        im = ig_by_id.get(o.get("instagram_media")) or ig_by_title.get(key) or {}
        fv = fb_reels.get(o.get("id")) or {}
        uk = posted.astimezone(UK) if posted else None
        row = {
            "short": o.get("id", ""), "title": v["title"], "posted": posted.isoformat(timespec="minutes") if posted else "",
            "posted_day": posted.strftime("%Y-%m-%d") if posted else "", "slot_uk": uk.strftime("%H:%M") if uk else "",
            "category": o.get("category", ""), "format": o.get("format", ""), "mood": o.get("mood", ""),
            "hook": o.get("hook", ""), "hook_words": o.get("hook_words", ""), "seconds": o.get("seconds", ""), "follow_line": o.get("follow_line", ""), **{k: o.get(k, "") for k in ("ending", "title_search", "first_frame", "angles", "replies", "kind", "source", "series", "franchise", "writer", "editor", "appeal", "late", "explore", "title_emoji")},
            "yt_views": s.get("views", 0), "yt_likes": s.get("likes", 0), "yt_comments": s.get("comments", 0),
            "yt_engaged_views": a.get("engagedViews", ""), "yt_avg_viewed_pct": round(a["averageViewPercentage"], 1) if a.get("averageViewPercentage") is not None else "",
            "yt_shares": a.get("shares", ""), "yt_subs_gained": a.get("subscribersGained", ""),
            "ig_views": im.get("views", ""), "ig_reach": im.get("reach", ""), "ig_likes": im.get("like_count", ""),
            "ig_comments": im.get("comments_count", ""), "ig_shares": im.get("shares", ""), "ig_saves": im.get("saved", ""),
            "ig_skip_rate": im.get("reels_skip_rate", ""), "ig_reposts": im.get("reposts", ""), "ig_fb_views": im.get("facebook_views", ""),
            **{k: o.get(k, "") for k in IG_TESTS},
            "fb_views": fv.get("views", ""), "fb_avg_watch_s": fv.get("avg_watch_s", ""),
            "youtube_url": f"https://youtube.com/shorts/{vid}", "instagram_url": im.get("permalink", "")}
        curve = (yt.get("retention") or {}).get(vid)
        secs = o.get("seconds") or 0
        row["yt_held_3s_pct"] = at_point(curve, min(1.0, 3 / secs)) if curve and secs else ""      # still watching 3 seconds in
        row["yt_held_end_pct"] = at_point(curve, 0.95) if curve else ""                            # still watching at the end
        src = (yt.get("sources") or {}).get(vid) or {}
        tot = sum(src.values())
        row["yt_feed_pct"] = round(100 * src.get("SHORTS", 0) / tot) if tot else ""          # views from the Shorts feed (the algorithm)
        row["yt_search_pct"] = round(100 * src.get("YT_SEARCH", 0) / tot) if tot else ""     # views from YouTube search
        row["real_share"] = o.get("real_share", "")            # share of shots that are real images of the subject
        dr = drops(curve, o.get("timeline"), secs) if curve and secs else []
        row["yt_worst_beat"] = (lambda w: f"beat {w[1] + 1} ({w[2]}), -{w[0]} pts/s")(max(dr)) if dr else ""
        row["_drops"] = dr
        av, ev = a.get("views"), a.get("engagedViews")
        row["yt_engaged_pct"] = round(100 * ev / av) if av and ev is not None else ""             # stayed past the first seconds
        total = sum(int(row[k]) for k in ("yt_views", "ig_views", "fb_views") if str(row[k]).strip() not in ("", "None"))
        row["all_views"] = total
        row["views_per_hour"] = round(row["yt_views"] / hours, 1) if hours else ""
        row["hook_type"] = DRV.hook_type(row["hook"])
        cc = short_cc.get(vid) or {}
        if cc and av:
            top = max(cc, key=cc.get)
            row.update(top_country=top, top_country_pct=round(100 * cc[top] / av), gb_pct=round(100 * cc.get("GB", 0) / av),
                       us_pct=round(100 * cc.get("US", 0) / av))
        else: row.update(top_country="", top_country_pct="", gb_pct="", us_pct="")
        rows.append(row)
    rows.sort(key=lambda r: r["posted"], reverse=True)
    curves = update_curves(rows)
    hot = breakouts(rows, curves)
    for r in rows:
        c = curves.get(rkey(r))
        for h in VEL_HOURS:
            v = views_at(c, h); r[f"views_{h}h"] = "" if v is None else v
    relative(rows, "views_24h", "_rel24")
    relative(rows, "views_per_hour", "_relvph")
    for r in rows:      # views against Shorts posted around the same time: at 24 hours where measured, else views an hour
        r["views_vs_typical"] = r["_rel24"] if r["_rel24"] != "" else r["_relvph"]
        # what drives views is judged at 24 hours only: the views-an-hour stand-in for younger Shorts ran 2 to 6x high
        r["rel"] = r["_rel24"]
    looks_out = look_scores(rows)
    hourly = update_hourly(rows, ig, fb)

    # per-day history: today's totals are appended to analytics/history.csv, so growth shows over time
    hist_p = OUT / "daily.csv"
    hist = list(csv.DictReader(io.StringIO(hist_p.read_text()))) if hist_p.exists() else []
    hist = [h for h in hist if not (h["day"] == str(TODAY) and h["source"] == "snapshot")]
    snap = {"day": str(TODAY), "source": "snapshot"}
    snap["yt_followers"] = (yt or {}).get("subs", "")
    snap["yt_views_total"] = sum(r["yt_views"] for r in rows)
    snap["ig_followers"] = (ig or {}).get("followers", "")
    snap["ig_views_total"] = sum(int(r["ig_views"]) for r in rows if str(r["ig_views"]).strip() not in ("", "None"))
    snap["fb_followers"] = (fb or {}).get("followers", "")
    snap["fb_views_total"] = sum(int(r["fb_views"]) for r in rows if str(r["fb_views"]).strip() not in ("", "None")) if fb else ""
    hist.append(snap)
    # YouTube's own daily numbers (views and subscribers gained each day) replace earlier copies of the same days
    first = min((r["posted_day"] for r in rows if r["posted_day"]), default=str(TODAY))   # the channel's first Short
    yt_days = {d["day"]: d for d in (yt or {}).get("daily", []) if d["day"] >= first}
    hist = [h for h in hist if h["day"] >= first or h["source"] == "snapshot"]
    hist = [h for h in hist if not (h["source"] == "youtube_daily" and h["day"] in yt_days)]
    for d in yt_days.values():
        hist.append({"day": d["day"], "source": "youtube_daily", "yt_views_day": d.get("views", ""),
                     "yt_engaged_views_day": d.get("engagedViews", ""),
                     "yt_subs_gained_day": (d.get("subscribersGained") or 0) - (d.get("subscribersLost") or 0)})
    hist.sort(key=lambda h: (h["day"], h["source"]))
    fields = ["day", "source", "yt_followers", "yt_views_total", "ig_followers", "ig_views_total", "fb_followers",
              "fb_views_total", "yt_views_day", "yt_engaged_views_day", "yt_subs_gained_day"]
    write_csv(hist_p, hist, fields)
    write_csv(OUT / "shorts.csv", rows, [k for k in rows[0] if not k.startswith("_") and k != "rel"] if rows else ["short", "title"])

    # monetisation progress. YouTube counts engaged views for the Partner Program; its Analytics run a day or two behind,
    # so the estimate adds views since its last day (live counts) at the recent engaged share.
    daily = (yt or {}).get("daily", [])
    d90 = [d for d in daily if d["day"] >= str(TODAY - dt.timedelta(days=90))]
    v90 = sum(int(d.get("engagedViews") or d.get("views") or 0) for d in d90)
    est, last_day = v90, max((d["day"] for d in daily if d.get("views") is not None), default=None)
    if daily and first >= min(d["day"] for d in daily):          # the whole channel sits inside Analytics' window
        an_views = sum(int(d.get("views") or 0) for d in daily)
        recent = [d for d in daily if d["day"] >= str(TODAY - dt.timedelta(days=7))]
        rv, re_ = sum(int(d.get("views") or 0) for d in recent), sum(int(d.get("engagedViews") or 0) for d in recent)
        ratio = re_ / rv if rv and re_ else 0.5
        est = v90 + round(max(0, sum(r["yt_views"] for r in rows) - an_views) * ratio)
    summary = {
        "updated": NOW.isoformat(timespec="minutes"), "mode": "hourly" if FAST else "full", "errors": errors,
        "full_updated": (yt or {}).get("cached_at"),
        "youtube": {"subscribers": (yt or {}).get("subs"), "public_shorts": len(rows),
                    "views_all_time": sum(r["yt_views"] for r in rows),
                    "views_last_90_days": v90, "views_measure": "engaged views" if any("engagedViews" in d for d in d90) else "views",
                    "views_last_90_days_estimate": est, "analytics_last_day": last_day},
        "instagram": {"followers": (ig or {}).get("followers"), "posts": len((ig or {}).get("media", [])),
                      "insights_error": (ig or {}).get("insights_error")} if ig else None,
        "facebook": {"followers": (fb or {}).get("followers"), "page": (fb or {}).get("name"), "reels": len((fb or {}).get("reels") or {}),
                     "insights_error": (fb or {}).get("insights_error")} if fb else None,
        "ypp": {"subscribers_needed": 1000, "shorts_views_needed_90_days": 10_000_000, "apply_before": str(YPP_DEADLINE),
                "days_left": (YPP_DEADLINE - TODAY).days,
                "subscribers_pct": round(100 * ((yt or {}).get("subs") or 0) / 1000, 1),
                "views_pct": round(100 * est / 10_000_000, 2),
                "views_needed_per_day": round(max(0, 10_000_000 - est) / max(1, min(90, (YPP_DEADLINE - TODAY).days))),
                "note": "Engaged views: YouTube's Analytics through its last day, plus live views since then at the recent "
                        "engaged share (YouTube's own figure lags a day or two).",
                # from 1 February 2027 (announced 10 August 2026): 20M Shorts views in 90 days, or 8,000 long-form watch hours
                # in 365 days, with 1,000 subscribers either way
                "from_2027": {"shorts_views_needed_90_days": 20_000_000, "views_pct": round(100 * est / 20_000_000, 2),
                              "views_needed_per_day": round(max(0, 20_000_000 - est) / 90),
                              "watch_hours_needed_365_days": 8000,
                              "watch_hours_365d": ((yt or {}).get("audience") or {}).get("longform_watch_hours_365d")}},
    }
    if aud.get("errors"): summary["audience_errors"] = aud["errors"]
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    # one row for the dashboard's headline cards (a file of rows is what it reads)
    write_csv(OUT / "progress.csv", [{
        "as_of": NOW.isoformat(timespec="minutes"), "as_of_uk": NOW.astimezone(UK).strftime("%a %-d %b, %H:%M"),
        "full_as_of_uk": utc(summary["full_updated"]).astimezone(UK).strftime("%a %-d %b, %H:%M") if summary["full_updated"] else "",
        "subscribers": summary["youtube"]["subscribers"] if summary["youtube"]["subscribers"] is not None else "",
        "engaged_views_90d": est, "engaged_views_90d_youtube": v90, "youtube_last_day": last_day or "",
        "views_all_time": summary["youtube"]["views_all_time"], "public_shorts": len(rows),
        "needed_per_day": summary["ypp"]["views_needed_per_day"], "days_left": summary["ypp"]["days_left"],
        "views_last_hour": next((h.get("yt_gained") for h in reversed(hourly) if h.get("yt_gained") not in ("", None)), ""),
        "views_last_24h": sum(int(float(h["yt_gained"])) for h in hourly if h.get("yt_gained") not in ("", None)
                              and h["hour_utc"] >= (NOW - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H")),
        "ig_followers": summary["instagram"]["followers"] if summary.get("instagram") else "",
        "fb_followers": summary["facebook"]["followers"] if summary.get("facebook") else ""}],
        ["as_of", "as_of_uk", "full_as_of_uk", "subscribers", "engaged_views_90d", "engaged_views_90d_youtube", "youtube_last_day",
         "views_all_time", "public_shorts", "needed_per_day", "days_left", "views_last_hour", "views_last_24h", "ig_followers", "fb_followers"])
    if not FAST:            # the slower reads: looks, posting times, audience, drivers and the writer's notes
        (OUT / "looks.json").write_text(json.dumps(looks_out, indent=1, ensure_ascii=False))
        (OUT / "models.json").write_text(json.dumps(writer_scores(rows), indent=1, ensure_ascii=False))
        slot_scores(rows)
        try: volume_test()
        except Exception as e: print("volume test:", str(e)[:150])
        write_audience(aud)
        reg_rows, aud["_regions"] = regions(rows, aud)
        write_csv(OUT / "regions.csv", reg_rows, ["kind", "country", "views", "share_pct", "avg_viewed_pct", "subs_gained", "shorts_seen",
                                                  "best_category", "best_format", "best_hook", "best_length", "top_short",
                                                  "dimension", "value", "shorts", "views_per_short", "lift"])
        pauses = DRV.load_pauses()          # choices left out for 14 days, then retested (drivers.py)
        table, _base = DRV.analyse(rows, pauses)
        DRV.save_pauses(pauses)
        try: table += DRV.analyse_instagram(rows)        # Instagram's own tests and categories, against Instagram views
        except Exception as e: print("instagram drivers:", str(e)[:150])
        write_csv(OUT / "drivers.csv", table, ["feature", "feature_label", "value", "n", "lift", "median_rel", "verdict",
                                               "held_3s_pct", "avg_viewed_pct", "subs_per_1k", "shares_per_1k", "why"])
        log_decisions(table, DRV.METHOD)
        follow = [f"Follow up {b['short'] or b['title']} (\"{b['title']}\"): " +
                  (f"{b['views_3h']} views in its first 3 hours, {b['times_typical']}x the median Short at 3 hours (the top fifth)"
                   if b.get("trigger") == "3 hours" else f"{b['times_typical']}x the views recent Shorts had {b['hours_public']} hours in") +
                  ". Write one follow-up in the next run (a new angle, the next chapter, or the answer to its top comment), title "
                  "tied to it." for b in hot[:2]]
        try: tests_lines = test_progress(rows, table)
        except Exception as e: tests_lines = []; print("test progress:", str(e)[:150])
        (OUT / "insights.md").write_text(insights(rows, summary, table, follow + DRV.recipe(table, rows) + tests_lines + audience_recipe(aud), aud))
    print(json.dumps({"mode": summary["mode"], "shorts": len(rows), "errors": errors}, indent=1))

STAY_DIMS = ("voice",)     # Charlie, 20 October: narrators are judged on viewers not swiping away
WRITER_SHRINK = 5          # a writer model's score is shrunk towards typical by 5 Shorts' worth (writer_scores)

def look_scores(rows):
    """How each look option (templates/looks.json) does. Every Short public for 24 hours gets a score against the Shorts
    posted the same UK day (peers_of; 1.0 = typical): 40% engaged views as a share of views (viewers who didn't swipe
    away), 40% the average % viewed, 20% views an hour, using whichever are available. Until 24 October the first 40% was
    "still watching at 3 seconds", which counts replays (31 of 35 Shorts over 100%) and tracked views at 0.11. Voices
    (STAY_DIMS) are scored on viewers not swiping away alone, among Shorts with 30 or more views. Each option's score is
    the median over the Shorts that used it."""
    import looks as LK
    look_by_id = {}
    for p in (ROOT / "status").glob("QD-*.json"):
        st = load_json(p, {})
        if st.get("look"): look_by_id[st.get("id")] = st["look"]
    try: dims = list(LK.catalogue()["dimensions"])
    except Exception: dims = ["captions", "voice", "energy", "grade"]
    for r in rows:
        lk = look_by_id.get(r["short"]) or {}
        for d in dims: r[f"look_{d}"] = lk.get(d, "")
        r["look_score"] = ""
    aged = [r for r in rows if r["posted"] and (NOW - utc(r["posted"])).total_seconds() >= 24 * 3600]
    def rel(r, field, min_views=0):
        v = r.get(field)
        if v in ("", None) or float(r.get("yt_views") or 0) < min_views: return None
        peers = peers_of(r, [x for x in aged if float(x.get("yt_views") or 0) >= min_views], field)
        if len(peers) < 3: return None
        med = statistics.median(peers)
        return float(v) / med if med else None
    for r in aged:
        parts = [(w, x) for w, x in ((0.4, rel(r, "yt_engaged_pct")), (0.4, rel(r, "yt_avg_viewed_pct")), (0.2, rel(r, "views_per_hour")))
                 if x is not None]
        if parts: r["look_score"] = round(sum(w * x for w, x in parts) / sum(w for w, _ in parts), 3)
        stay = rel(r, "yt_engaged_pct", 30)
        r["stay_score"] = round(stay, 3) if stay is not None else ""
    out = {"updated": NOW.isoformat(timespec="minutes"), "dimensions": {},
           "how": "Each Short against the Shorts posted the same UK day (1.0 = typical): 40% engaged views as a share of views "
                  "(not swiping away), 40% average % viewed, 20% views an hour. Voices: not swiping away alone (Shorts with 30 or "
                  "more views). An option's score is the median of its Shorts.",
           "measure": {d: "not swiping away" for d in STAY_DIMS}}
    try: cat = LK.catalogue()
    except Exception: return out
    for dim, spec in cat["dimensions"].items():
        field = "stay_score" if dim in STAY_DIMS else "look_score"
        for opt in spec["options"]:
            used = [r for r in aged if r.get(f"look_{dim}") == opt and r.get(field) not in ("", None)]
            e = {"n": len(used)}
            if used:
                e["score"] = round(statistics.median(r[field] for r in used), 3)
                for k, f in (("held_3s_pct", "yt_held_3s_pct"), ("avg_viewed_pct", "yt_avg_viewed_pct"), ("stayed_pct", "yt_engaged_pct")):
                    vals = [float(r[f]) for r in used if r.get(f) not in ("", None)]
                    if vals: e[k] = round(statistics.median(vals), 1)
            out["dimensions"].setdefault(dim, {})[opt] = e
    return out

def writer_scores(rows):
    """How each writer model (board "writer", provider:model) does: the same score as look_scores (each Short against
    Shorts posted within 3 days of it, 1.0 = typical), the median over its Shorts. writer.py picks the next board's
    first-choice model from this (analytics/models.json)."""
    aged = [r for r in rows if r.get("writer") and r.get("look_score") not in ("", None)]
    out = {"updated": NOW.isoformat(timespec="minutes"), "writers": {},
           "how": "Each Short against the Shorts posted the same UK day (1.0 = typical): 40% engaged views as a share of views, "
                  "40% average % viewed, 20% views an hour. A writer's score is exp(sum of log scores / (n + 5)): shrunk towards "
                  "typical, so one breakout can't crown a model (24 October: 20.9 from 2 Shorts, one at 27.7x, gave a model 41% "
                  "of the day's boards)."}
    def score(key):
        out_ = {}
        for w in sorted({key(r) for r in rows if r.get("writer")} - {None}):
            used = [r for r in aged if key(r) == w]
            e = {"n": len(used), "shorts": sum(1 for r in rows if r.get("writer") and key(r) == w)}
            if used:
                logs = [math.log(min(20.0, max(0.05, float(r["look_score"])))) for r in used]
                e["score"] = round(math.exp(sum(logs) / (len(logs) + WRITER_SHRINK)), 3)
                vals = [float(r["views_vs_typical"]) for r in used if r.get("views_vs_typical") not in ("", None)]
                if vals: e["views_vs_typical"] = round(statistics.median(vals), 2)
            out_[w] = e
        return out_
    out["writers"] = score(lambda r: r["writer"])
    # Claude as editor (23 October): edited free-model Shorts against unedited ones, and every writer and editor pair.
    # Claude-written Shorts are left out of "editors": the editor only edits other models' boards.
    out["editors"] = score(lambda r: None if r["writer"].startswith("claude:") else r.get("editor") or "none")
    out["combos"] = score(lambda r: r["writer"] + " + " + (r.get("editor") or "no edit"))
    return out

def slot_scores(rows):
    """Posting times (UK, to the half hour) scored by views an hour against Shorts posted within 3 days (1.0 = typical).
    plan.py picks each day's slots from this. Written once per UK day so a day's slots stay fixed."""
    p = OUT / "slots.json"
    today = str(NOW.astimezone(ZoneInfo("Europe/London")).date())
    try:
        if json.loads(p.read_text()).get("day") == today: return
    except Exception: pass
    aged = [r for r in rows if r["posted"] and r.get("slot_uk") and (NOW - utc(r["posted"])).total_seconds() >= 24 * 3600]
    by = {}
    for r in aged:
        t = utc(r["posted"])
        peers = [x["views_per_hour"] for x in aged if x["views_per_hour"] not in ("", None) and abs((utc(x["posted"]) - t).total_seconds()) <= 3 * 86400]
        if len(peers) < 3 or r["views_per_hour"] in ("", None): continue
        med = statistics.median(peers)
        if not med: continue
        h, m = map(int, r["slot_uk"].split(":"))
        q = int(round((h * 60 + m) / 30)) * 30 % 1440          # to the nearest half hour
        key = f"{q // 60:02d}:{q % 60:02d}"
        by.setdefault(key, []).append(float(r["views_per_hour"]) / med)
    # Quarters of the UK day by category (plan.band_scores: post a category when its audience watches; 23 October)
    bands = {}
    for r in aged:
        if r.get("views_vs_typical") in ("", None): continue
        b = ("00-06", "06-12", "12-18", "18-24")[int(r["slot_uk"][:2]) // 6]
        for cat in ("_all", r.get("category") or ""):
            if cat: bands.setdefault(cat, {}).setdefault(b, []).append(float(r["views_vs_typical"]))
    p.write_text(json.dumps({"day": today, "updated": NOW.isoformat(timespec="minutes"),
                             "slots": {k: {"n": len(v), "score": round(statistics.median(v), 3)} for k, v in sorted(by.items())},
                             "bands": {c: {b: {"n": len(v), "score": round(statistics.median(v), 3)} for b, v in sorted(bs.items())}
                                       for c, bs in sorted(bands.items())}}, indent=1))


def test_progress(rows, table, today=None):
    """The factorial round's progress (config test_round, writer.test_plan): for each factor and arm, the Shorts measured
    so far (posted since the round began, 24-hour views in), how many more it needs to show a 2x difference (per_arm, 70;
    data report, 24 October), the days that takes at today's rate, and drivers.csv's verdict once the proof rule is met.
    Writes analytics/tests.json for the hub; returns lines for insights.md."""
    rnd = CFG.get("test_round") or {}
    p = OUT / "tests.json"
    if not rnd.get("factors") or not rnd.get("start"):
        p.unlink(missing_ok=True); return []
    import drivers as DRV
    start, per = str(rnd["start"]), int(rnd.get("per_arm", 70))
    today = today or NOW.astimezone(UK).date()
    verdict = {(t.get("feature"), t.get("value")): t.get("verdict", "") for t in table or []}
    counts = {f: {a: 0 for a in arms} for f, arms in rnd["factors"].items()}
    posted_days = set()
    for r in rows:
        t = utc(r.get("posted"))
        if not t or str(t.astimezone(UK).date()) < start: continue
        posted_days.add(str(t.astimezone(UK).date()))
        if r.get("views_24h") in ("", None): continue
        feats = DRV.features(r)
        for f, arms in counts.items():
            if feats.get(f) in arms: arms[feats[f]] += 1
    try:
        import quota
        rate = max(1.0, 0.8 * quota.target() / 2)      # Shorts an arm a day: 4 in 5 Shorts are in the round, half to each arm
    except Exception: rate = 6.0
    out = {"round": rnd.get("name", "round"), "start": start, "per_arm": per, "as_of": NOW.isoformat(timespec="minutes"), "factors": {}}
    lines = []
    for f, arms in counts.items():
        need = max(0, max(per - n for n in arms.values()))
        settled = any(verdict.get((f, a)) in ("push", "cut back") for a in arms) or need == 0
        out["factors"][f] = {"arms": {a: {"n": n, "needs": max(0, per - n), "verdict": verdict.get((f, a), "")} for a, n in arms.items()},
                             "settled": settled, "days_left": 0 if settled else math.ceil(need / rate)}
        lines.append(f"- {f.replace('_', ' ')}: " + ", ".join(f"{a} {n}" + (f" (needs {per - n} more)" if n < per else "") for a, n in arms.items())
                     + ("; settled" if settled else f"; about {math.ceil(need / rate)} more days at today's rate"))
    p.write_text(json.dumps(out, indent=1))
    if today < dt.date.fromisoformat(start): return []
    return [f"Tests being run ({out['round']}, from {start}: every Short takes an arm of each, 50/50; an arm settles at {per} "
            "measured Shorts, or sooner on a clear result). Shorts measured so far:"] + lines


def volume_days(today=None):
    """Per UK day: Shorts posted, YouTube views gained (hourly.csv, only days the hourly rows cover for 20 hours or more),
    the day's cohort (the 24-hour views of the Shorts posted that day, summed; scaled up when 80% or more of them are
    measured) and their 24-hour views one by one. {day: {...}} from analytics/shorts.csv and hourly.csv."""
    days = {}
    new_day = lambda: {"views": 0.0, "hours": 0.0, "n": 0, "v24": [], "measured": 0}
    p = OUT / "hourly.csv"
    for r in (csv.DictReader(io.StringIO(p.read_text())) if p.exists() else []):
        if r.get("yt_gained") in ("", None) or not r.get("uk_day"): continue
        d = days.setdefault(r["uk_day"], new_day())
        d["views"] += float(r["yt_gained"]); d["hours"] += float(r.get("hours") or 1)
    p = OUT / "shorts.csv"
    for r in (csv.DictReader(io.StringIO(p.read_text())) if p.exists() else []):
        t = utc(r.get("posted"))
        if not t: continue
        d = days.setdefault(str(t.astimezone(UK).date()), new_day())
        d["n"] += 1
        try: v = float(r.get("views_24h"))
        except (TypeError, ValueError): continue
        d["v24"].append(v); d["measured"] += 1
    for d in days.values():
        d["daily"] = d["views"] if d["hours"] >= 20 else None
        d["cohort"] = sum(d["v24"]) * d["n"] / d["measured"] if d["n"] and d["measured"] >= 0.8 * d["n"] else None
    return days


def ratio_ci(during, before, reps=2000, seed=11):
    """Mean of `during` over mean of `before`, with a 90% bootstrap interval over days (each group resampled on its own).
    None when either side is empty or before sums to 0."""
    import random
    if not during or not before or not sum(before): return None
    rng, out = random.Random(seed), []
    for _ in range(reps):
        a = [rng.choice(during) for _ in during]; b = [rng.choice(before) for _ in before]
        if sum(b): out.append((sum(a) / len(a)) / (sum(b) / len(b)))
    out.sort()
    point = (sum(during) / len(during)) / (sum(before) / len(before))
    return {"during": round(sum(during) / len(during)), "before": round(sum(before) / len(before)), "ratio": round(point, 2),
            "lo": round(out[int(0.05 * len(out))], 2), "hi": round(out[min(len(out) - 1, int(0.95 * len(out)))], 2),
            "days": [len(during), len(before)]}


def volume_test(today=None):
    """Charlie's fewer-better test (config volume_test: 15 Shorts a day from 24 October, against the 24 to 40 a day before).
    Judged on each UK day, not on a 7-day snapshot ratio (data report, 24 October: that ratio's standard error is about
    19%, so it can't tell 0.9x from 1.1x):
      - daily YouTube views (views gained per UK day, analytics/hourly.csv),
      - the day's cohort: the 24-hour views of the Shorts posted that day, summed (what the day's work brought in),
      - the median 24-hour views of one Short (a guardrail: fewer Shorts should each do better),
    over the test's days (14) against the days in the two weeks before it that posted 1.25 times the test number or more,
    each ratio with a 90% bootstrap interval over days. The test number stays unless daily views AND the cohort are both
    clearly lower (each interval's top under 0.9); then back to the median number of those days before. While it runs,
    status/volume.json holds the reading so far (quota.target keeps the test number) and the ledger row (volume_test
    "ledger", CH-011) waits for this verdict rather than a 7-day comparison. Returns the reading or the verdict."""
    p = ROOT / "status" / "volume.json"
    try: st = json.loads(p.read_text())
    except Exception: st = {}
    test = CFG.get("volume_test") or {}
    if st.get("verdict") or not test.get("start"): return None
    start = dt.date.fromisoformat(test["start"]); n_days = int(test.get("days", 14)); per = int(test.get("per_day", 15))
    today = today or NOW.astimezone(UK).date()
    if today <= start: return None
    days = volume_days(today)
    judge_on = start + dt.timedelta(days=n_days + 1)          # the last test day's Shorts need their 24 hours
    test_days = [str(start + dt.timedelta(days=i)) for i in range(n_days) if start + dt.timedelta(days=i) < today]
    before_days = [str(start - dt.timedelta(days=i)) for i in range(1, 15)
                   if days.get(str(start - dt.timedelta(days=i)), {}).get("n", 0) >= math.ceil(1.25 * per)]
    pick = lambda ks, f: [days[k][f] for k in ks if k in days and days[k].get(f) is not None]
    daily = ratio_ci(pick(test_days, "daily"), pick(before_days, "daily"))
    cohort = ratio_ci(pick(test_days, "cohort"), pick(before_days, "cohort"))
    def med(ks):
        vals = [v for k in ks if k in days for v in days[k]["v24"]]
        return statistics.median(vals) if vals else None
    before_n = sorted(days[k]["n"] for k in before_days)
    reading = {"test_days_in": len(test_days), "test_days": n_days, "judge_on": str(judge_on), "before_days": sorted(before_days),
               "shorts_a_day": {"during": round(statistics.mean([days[k]["n"] for k in test_days if k in days] or [0]), 1),
                                "before": round(statistics.mean(before_n), 1) if before_n else None},
               "daily_views": daily, "cohort_24h": cohort,
               "median_24h_per_short": {"during": med(test_days), "before": med(before_days)}}
    clearly_lower = lambda x: bool(x) and x["hi"] < 0.9
    enough = bool(daily and cohort and min(daily["days"][0], cohort["days"][0]) >= 10 and min(daily["days"][1], cohort["days"][1]) >= 3)
    ledger_sync(test, judge_on)
    if today < judge_on or not enough:
        why = (f"collecting: day {len(test_days)} of {n_days}, judged from {judge_on:%A %d %B}" if today < judge_on else
               f"extended: too few measured days to judge (daily {(daily or {}).get('days')}, cohort {(cohort or {}).get('days')}; "
               "needs 10 test days and 3 days before)")
        st = {"per_day": per, "verdict": None, "why": why, "reading": reading, "as_of": NOW.isoformat(timespec="minutes")}
        p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(st, indent=1))
        return st
    back = clearly_lower(daily) and clearly_lower(cohort)
    back_to = max(per + 1, min(int(test.get("before", 40)), round(statistics.median(before_n)))) if before_n else int(test.get("before", 40))
    before_a_day = reading["shorts_a_day"]["before"]
    st = {"per_day": back_to if back else per, "verdict": "back" if back else "kept", "judged": str(today), "reading": reading,
          "why": (f"{per} a day brought clearly fewer views: daily views {daily['ratio']}x [{daily['lo']}, {daily['hi']}] and the day's "
                  f"Shorts {cohort['ratio']}x [{cohort['lo']}, {cohort['hi']}] of the days at {before_a_day} a day") if back else
                 (f"{per} a day kept the views: daily views {daily['ratio']}x [{daily['lo']}, {daily['hi']}], the day's Shorts "
                  f"{cohort['ratio']}x [{cohort['lo']}, {cohort['hi']}] of the days at {before_a_day} a day, for less work and "
                  "YouTube allowance")}
    p.write_text(json.dumps(st, indent=1))
    _decision("Shorts a day", f"{'Back to' if back else 'Keep'} {st['per_day']} Shorts a day", st["why"],
              "analytics.volume_test: daily views (hourly.csv) and day cohorts (shorts.csv views_24h), 90% bootstrap intervals over days",
              today + dt.timedelta(days=14))
    ledger_sync(test, judge_on, st)
    return st


def ledger_sync(test, judge_on, verdict=None):
    """Keeps the volume test's ledger row (volume_test "ledger", CH-011) on this test: checked on the judging day rather than
    after the 7 days it was added with, and, once judged, the verdict and the numbers (changes.py leaves a checked row)."""
    cid = test.get("ledger")
    if not cid: return
    try:
        import changes
        rows = changes.load()
        r = next((x for x in rows if x.get("id") == cid), None)
        if r is None or r.get("status") in ("kept", "reverted") or (r.get("status") == "checked" and r.get("verdict") and not verdict): return
        r["after_days"] = str(int(test.get("days", 14))); r["check_on"] = str(judge_on)
        if verdict:
            d, c = verdict["reading"]["daily_views"], verdict["reading"]["cohort_24h"]
            m = verdict["reading"]["median_24h_per_short"]
            r.update(status="checked", verdict="worse" if verdict["verdict"] == "back" else ("better" if d["lo"] > 1.1 else "no change"),
                     result=f"volume test {verdict['verdict']}: daily views {d['before']} -> {d['during']} ({d['ratio']}x, 90% "
                            f"{d['lo']} to {d['hi']}, days {d['days'][0]}/{d['days'][1]}); the day's Shorts at 24 h {c['before']} -> "
                            f"{c['during']} ({c['ratio']}x, {c['lo']} to {c['hi']}); median a Short {m['before']} -> {m['during']}; "
                            f"now {verdict['per_day']} a day")
        changes.save(rows)
    except Exception as e: print("volume test ledger:", str(e)[:150])


def _decision(area, change, why, evidence, check_on):
    p = OUT / "decisions.csv"
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=DEC_FIELDS)
        if new: w.writeheader()
        w.writerow({"date": str(NOW.date()), "area": area, "change": change, "why": why, "evidence": evidence,
                    "check_on": str(check_on), "by": "analytics (automatic)"})


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow(r)

def timing_lines():
    """When the audience watches: YouTube views gained by UK hour and weekday over the last 14 days (analytics/hourly.csv)."""
    p = OUT / "hourly.csv"
    rows = [r for r in (csv.DictReader(io.StringIO(p.read_text())) if p.exists() else [])
            if r.get("yt_gained") not in ("", None) and r["hour_utc"] >= (NOW - dt.timedelta(days=14)).strftime("%Y-%m-%dT%H")]
    days = len({r["uk_day"] for r in rows})
    if days < 3: return [f"Collecting hourly views ({days} of 3 days so far): times of day show here once there are 3."]
    by_h, by_d = {}, {}
    for r in rows:
        g, hrs = float(r["yt_gained"]), max(0.25, float(r.get("hours") or 1))
        by_h.setdefault(r["uk_hour"], []).append(g / hrs); by_d[r["uk_weekday"]] = by_d.get(r["uk_weekday"], 0) + g
    avg = {h: statistics.mean(v) for h, v in by_h.items()}
    best = sorted(avg, key=avg.get, reverse=True)[:4]; worst = sorted(avg, key=avg.get)[:3]
    out = [f"Most views an hour (UK, last {days} days): " + ", ".join(f"{h}:00 ({avg[h]:,.0f}/h)" for h in best) +
           ". Quietest: " + ", ".join(f"{h}:00 ({avg[h]:,.0f}/h)" for h in worst) + "."]
    if len(by_d) >= 5:
        out.append("By weekday (views gained): " + ", ".join(f"{d} {v:,.0f}" for d, v in sorted(by_d.items(), key=lambda kv: -kv[1])) + ".")
    return out

def audience_lines(aud):
    if not aud or not (aud.get("channel") or {}).get("countries"): return ["No country data from YouTube yet (it starts once a few Shorts have views)."]
    out = []
    def top(rows, key, n=4):
        tot = sum(float(r.get("views") or 0) for r in rows) or 1
        return ", ".join(f"{r.get(key)} {round(100 * float(r.get('views') or 0) / tot)}%" for r in rows[:n])
    ch = aud["channel"]
    out.append("Countries (YouTube views): " + top(ch["countries"], "country", 6) + ".")
    for c, v in sorted((aud.get("categories") or {}).items()):
        if v.get("countries"): out.append(f"- {c} ({v.get('shorts', '?')} Shorts): " + top(v["countries"], "country") + ".")
    if ch.get("traffic"):
        out.append("How viewers found us: " + ", ".join(f"{TRAFFIC.get(k, k)} {p}%" for k, p in
                   [(r.get("insightTrafficSourceType"), round(100 * float(r.get("views") or 0) / (sum(float(x.get("views") or 0) for x in ch["traffic"]) or 1)))
                    for r in ch["traffic"][:4]]) + ".")
    if ch.get("demographics"):
        d = sorted(ch["demographics"], key=lambda r: -float(r.get("viewerPercentage") or 0))[:3]
        out.append("Biggest groups: " + ", ".join(f"{(r.get('ageGroup') or '').replace('age', '')} {r.get('gender')} {float(r.get('viewerPercentage') or 0):.0f}%" for r in d) + ".")
    return out

def audience_recipe(aud):
    """Writer guidance from how viewers find us and where they are (needs 300 or more views to say anything)."""
    ch = (aud or {}).get("channel") or {}
    tr = {r.get("insightTrafficSourceType"): float(r.get("views") or 0) for r in ch.get("traffic") or []}
    tot = sum(tr.values())
    if tot < 300: return []
    out, search, feed = [], tr.get("YT_SEARCH", 0) / tot, tr.get("SHORTS", 0) / tot
    if search >= 0.35:
        out.append(f"YouTube search brings {round(100 * search)}% of views (the Shorts feed {round(100 * feed)}%): titles must open "
                   "with the exact name people type (person, game, film, team), the first hashtag and first tag repeat it, and topics "
                   "people are actively searching today beat clever angles on quiet ones.")
    elif feed >= 0.7:
        out.append(f"The Shorts feed brings {round(100 * feed)}% of views: the first second decides everything, so lead with the "
                   "strongest real image and a hook of 8 words or fewer.")
    cc = {r.get("country"): float(r.get("views") or 0) for r in ch.get("countries") or []}
    ctot = sum(cc.values()) or 1
    us, gb = cc.get("US", 0) / ctot, cc.get("GB", 0) / ctot
    if us >= gb + 0.15:
        out.append(f"US viewers are {round(100 * us)}% (UK {round(100 * gb)}%): pick stories that matter in both, explain UK-only "
                   "references in a few words, and keep UK spelling.")
    return out

def insights(rows, s, table=None, recipe=None, aud=None):
    """A short read for the daily writer and the reviews: the recipe from the data, what drives views, when and where
    people watch, then the best and worst Shorts and the finer detail."""
    L = [f"# What's working (updated {s['updated'][:16].replace('T', ' ')} UTC)", ""]
    y, p = s["youtube"], s["ypp"]
    L += [f"YouTube Partner Program: {y['subscribers'] or 0:,} of 1,000 subscribers, about {y.get('views_last_90_days_estimate', y['views_last_90_days']):,} "
          f"of 10,000,000 Shorts {y['views_measure']} in the last 90 days. Apply before {p['apply_before']} ({p['days_left']} days): "
          f"after that new channels need 20M. Needed from now: about {p['views_needed_per_day']:,} views a day.", ""]
    if s["errors"]: L += ["Not available this time: " + "; ".join(f"{k} ({v[:80]})" for k, v in s["errors"].items()), ""]
    L += ["## Recipe from the data (the writer follows this; Charlie's requests and breaking news still come first)"] + \
         [f"- {x}" for x in (recipe or [])] + [""]
    strong = [t for t in (table or []) if t["verdict"] in ("push", "cut back")]
    early = [t for t in (table or []) if t["verdict"] == "early sign" and (t["lift"] >= 1.25 or t["lift"] <= 0.8)]
    if strong or early:
        L += ["## What drives views (each Short against Shorts posted around the same time; 1.0x = typical)"]
        L += [f"- {t['verdict'].capitalize()}: {t['feature_label'].lower()} \"{t['value']}\" {t['lift']}x over {t['n']} Shorts"
              + (f" ({t['why']})" if t["why"] else "") for t in sorted(strong, key=lambda t: -abs(math.log(t["lift"])))]
        L += [f"- Early sign: {t['feature_label'].lower()} \"{t['value']}\" {t['lift']}x over {t['n']} Shorts" for t in early[:6]]
        L += [""]
    L += ["## When people watch"] + timing_lines() + [""]
    L += ["## Where viewers are and how they find us"] + audience_lines(aud) + [""]
    L += (aud or {}).get("_regions") or []
    aged = [r for r in rows if r["posted"] and (NOW - utc(r["posted"])).total_seconds() > 24 * 3600]
    if not aged:
        L += ["Not enough history yet: no Short has been public for 24 hours."]
        return "\n".join(L) + "\n"
    key = lambda r: r["yt_views"]
    top, bottom = sorted(aged, key=key, reverse=True)[:8], sorted(aged, key=key)[:5]
    fmt = lambda r: (f"- {r['yt_views']:,} views ({r['views_per_hour']}/h)"
                     + (f", {r['yt_avg_viewed_pct']}% viewed" if r['yt_avg_viewed_pct'] != "" else "")
                     + (f", +{r['yt_subs_gained']} subs" if r['yt_subs_gained'] not in ("", 0) else "")
                     + f" · {r['title']} [{r['category'] or '?'}, {r['format'] or '?'}, {r['slot_uk']}]"
                     + (f" · hook: \"{r['hook']}\"" if r['hook'] else ""))
    L += ["## Best Shorts (public 24 hours or more)"] + [fmt(r) for r in top] + ["", "## Weakest"] + [fmt(r) for r in bottom] + [""]
    med = statistics.median(r["yt_views"] for r in aged)
    def table(label, field):
        groups = {}
        for r in aged: groups.setdefault(r[field] or "unknown", []).append(r["yt_views"])
        out = [f"## By {label} (median views; overall median {med:,.0f})"]
        for g, v in sorted(groups.items(), key=lambda kv: -statistics.median(kv[1])):
            out.append(f"- {g}: {statistics.median(v):,.0f} median, {len(v)} Shorts")
        return out + [""]
    L += table("category", "category") + table("format", "format") + table("posting slot (UK)", "slot_uk")
    held = [r for r in aged if r.get("yt_held_3s_pct") not in ("", None) and r.get("hook")]
    if held:
        by = sorted(held, key=lambda r: r["yt_held_3s_pct"], reverse=True)
        line = lambda r: f"- {r['yt_held_3s_pct']}% still watching at 3s, {r.get('yt_held_end_pct', '?')}% at the end · \"{r['hook']}\" ({r['title']})"
        if len(by) >= 7:
            L += ["## Hooks that held viewers (share still watching 3 seconds in)"] + [line(r) for r in by[:4]]
            L += ["## Hooks that lost them"] + [line(r) for r in by[-3:]] + [""]
        else:
            L += ["## Hooks, by share still watching 3 seconds in"] + [line(r) for r in by] + [""]
    def med(rs, f):
        v = [float(r[f]) for r in rs if r.get(f) not in ("", None)]
        return f"{statistics.median(v):.0f}" if v else "?"
    real = [r for r in aged if r.get("real_share") not in ("", None) and float(r["real_share"]) >= 0.5]
    stock = [r for r in aged if r.get("real_share") not in ("", None) and float(r["real_share"]) < 0.5]
    if len(real) >= 3 and len(stock) >= 3:
        L += [f"Mostly real images of the subject ({len(real)} Shorts): {med(real, 'yt_held_3s_pct')}% still watching at 3s, "
              f"{med(real, 'yt_avg_viewed_pct')}% viewed, {med(real, 'yt_views')} views. Mostly stock ({len(stock)}): "
              f"{med(stock, 'yt_held_3s_pct')}%, {med(stock, 'yt_avg_viewed_pct')}%, {med(stock, 'yt_views')} views.", ""]
    by_vis = {}
    for r in aged:
        for loss, _i, vis in r.get("_drops") or []: by_vis.setdefault(vis, []).append(loss)
    if by_vis:
        L += ["## Where viewers leave (points of audience lost per second while each kind of beat is on screen; lower is better)"]
        L += [f"- {vis}: {statistics.median(v):.2f} ({len(v)} beats)" for vis, v in sorted(by_vis.items(), key=lambda kv: statistics.median(kv[1]))]
        L += [""]
    try:
        lk = json.loads((OUT / "looks.json").read_text()).get("dimensions", {})
        lines = []
        for dim, opts in lk.items():
            got = sorted(((k, v) for k, v in opts.items() if v.get("n")), key=lambda kv: -kv[1].get("score", 0))
            if got: lines.append(f"- {dim}" + (" (on viewers not swiping away)" if dim in STAY_DIMS else "") + ": "
                                 + ", ".join(f"{k} {v['score']:.2f} ({v['n']})" for k, v in got))
        if lines:
            L += ["## Looks (1.00 = typical for Shorts posted around the same time; Shorts measured in brackets)",
                  "GitHub picks each Short's look and leans towards the winners by itself."] + lines + [""]
    except Exception: pass
    eng = [r["yt_engaged_pct"] for r in aged if r.get("yt_engaged_pct") not in ("", None)]
    if eng: L += [f"Engaged views (stayed past the first seconds): median {statistics.median(eng):.0f}% of views.", ""]
    hooks = [r for r in aged if str(r["hook_words"]).isdigit()]
    if hooks:
        short_h = [r["yt_views"] for r in hooks if int(r["hook_words"]) <= 10]
        long_h = [r["yt_views"] for r in hooks if int(r["hook_words"]) > 10]
        if short_h and long_h:
            L += [f"Hooks of 10 words or fewer: {statistics.median(short_h):,.0f} median views ({len(short_h)}); "
                  f"longer hooks: {statistics.median(long_h):,.0f} ({len(long_h)}).", ""]
    return "\n".join(L) + "\n"

if __name__ == "__main__":
    main()
