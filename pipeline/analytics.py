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
def our_shorts():
    """Status files and boards: what each Short was (category, format, mood, hook, words) keyed by YouTube id."""
    boards = {}
    for d in ("done", "ready", "queue", "failed", "rejected", "reserve", "hold"):
        for p in (ROOT / "boards" / d).glob("*.json"):
            b = load_json(p, {})
            if b.get("id"): boards[b["id"]] = b
    out = {}
    for p in (ROOT / "status").glob("*.json"):
        st = load_json(p, {})
        if not st.get("video"): continue
        b = boards.get(st.get("id"), {})
        beats = b.get("beats") or []
        hook = beats[0].get("say", "") if beats else ""
        out[st["video"]] = {
            "id": st.get("id"), "title": st.get("title") or b.get("meta", {}).get("title", ""),
            "category": b.get("category", ""), "format": b.get("format", ""),
            "mood": (b.get("music") or {}).get("mood", ""), "hook": hook, "hook_words": len(hook.split()),
            "words": sum(len(bt.get("say", "").split()) for bt in beats), "seconds": (st.get("qa") or {}).get("duration"),
            "hashtags": len((b.get("meta") or {}).get("hashtags") or []),
            "instagram_media": (st.get("instagram") or {}).get("media"), "tiktok": bool(st.get("tiktok")),
            "source": st.get("source", "pipeline"), "timeline": st.get("timeline"),
            "real_share": round((st.get("media") or {}).get("real_shots", 0) / max(1, sum(len(bt.get("shots") or []) for bt in beats)), 2)
                          if st.get("media") and beats else ""}
    legacy = load_json(OUT / "legacy.json", {}) or {}       # Shorts from before the pipeline kept boards
    for vid, o in out.items():
        if not o["category"] and o["id"] in (legacy.get("by_id") or {}):
            o.update(category=legacy["by_id"][o["id"]], format=o["format"] or "legacy")
    for vid, cat in (legacy.get("by_video") or {}).items():
        out.setdefault(vid, {"id": "", "title": "", "category": cat, "format": "legacy", "mood": "", "hook": "", "hook_words": "",
                             "words": "", "seconds": "", "hashtags": "", "instagram_media": None, "tiktok": False,
                             "source": "manual", "timeline": None, "real_share": ""})
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
                "retention": {v: {float(k): x for k, x in cv.items()} for v, cv in (c.get("retention") or {}).items()}}
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
    retention = {}
    for vid, v in vids.items():
        posted = utc(v.get("publish_at")) or utc(v.get("uploaded"))
        if v.get("privacy") != "public" or not posted or not (dt.timedelta(days=2) <= NOW - posted <= dt.timedelta(days=30)):
            continue
        try: curve = query("audienceWatchRatio", dimensions="elapsedVideoTimeRatio", filters=f"video=={vid}")
        except Exception: continue
        if curve: retention[vid] = {float(r["elapsedVideoTimeRatio"]): float(r["audienceWatchRatio"]) for r in curve}
    aud = audience(query, vids, ours or {})
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_p.write_text(json.dumps({"at": NOW.isoformat(timespec="minutes"), "analytics": per_video, "daily": daily,
                                   "audience": aud, "retention": {v: {str(k): x for k, x in cv.items()} for v, cv in retention.items()}},
                                  ensure_ascii=False))
    return {"subs": subs, "videos": vids, "stats": stats, "analytics": per_video, "daily": daily, "retention": retention,
            "audience": aud, "cached_at": NOW.isoformat(timespec="minutes")}

def audience(query, vids, ours):
    """Where viewers are, how they found the Shorts, and their age and gender: for the channel, for each category (a
    query filtered to that category's videos), and each Short's share from the channel's top 5 countries. About 30
    queries; any that YouTube refuses (too little data yet, or an unsupported combination) is skipped and noted."""
    out, errs = {"channel": {}, "categories": {}, "short_countries": {}}, []
    def q(label, *a, **kw):
        try: return query(*a, **kw)
        except Exception as e: errs.append(f"{label}: {type(e).__name__}: {str(e)[:120]}"); return []
    out["channel"]["countries"] = q("countries", "views,averageViewPercentage", dimensions="country", sort="-views", maxResults=25)
    out["channel"]["traffic"] = q("traffic", "views", dimensions="insightTrafficSourceType", sort="-views")
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
    for row in out["channel"]["countries"][:5]:
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
    """The retention ratio at a fraction of the video (the first measured point at or after it), as a percentage."""
    if not curve: return ""
    k = min((k for k in curve if k >= frac), default=max(curve))
    return round(100 * curve[k])

# ---------------- Instagram ----------------
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
    keys = ("views", "reach", "shares", "saved", "total_interactions", "ig_reels_avg_watch_time")
    for m in media:
        posted = utc(m.get("timestamp"))
        if FAST and m["id"] in cache and posted and NOW - posted > dt.timedelta(days=3):
            m.update(cache[m["id"]]); continue           # older Reels move slowly: hourly runs reuse the last full run
        r = requests.get(f"{api}/{m['id']}/insights", params={"metric": "views,reach,shares,saved,total_interactions",
                                                              "access_token": tok}, timeout=30).json()
        if "error" in r: insights_error = r["error"].get("message", "")[:200]; continue
        for d in r.get("data", []):
            m[d["name"]] = (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
        if not FAST and m.get("media_product_type") == "REELS":     # average watch time, asked apart so a refusal costs nothing else
            w = requests.get(f"{api}/{m['id']}/insights", params={"metric": "ig_reels_avg_watch_time", "access_token": tok}, timeout=30).json()
            for d in w.get("data", []) if "error" not in w else []:
                m[d["name"]] = (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
        cache[m["id"]] = {**cache.get(m["id"], {}), **{k: m[k] for k in keys if k in m}}
    CACHE.mkdir(parents=True, exist_ok=True); cache_p.write_text(json.dumps(cache))
    return {"followers": me.get("followers_count"), "username": me.get("username"), "media": media, "insights_error": insights_error}

# ---------------- TikTok ----------------
def tiktok():
    if json.loads((ROOT / "config.json").read_text()).get("tiktok_mode") == "off": return None     # dropped 19 Oct 2026
    if len(os.environ.get("SOCIAL_KEY", "")) < 20: return None
    import requests, social
    t = social.load("tiktok")
    if not t.get("access_token"): return None
    h = {"Authorization": f"Bearer {t['access_token']}"}
    u = requests.get(f"{social.TT_API}/user/info/", headers=h, timeout=30,
                     params={"fields": "display_name,follower_count,likes_count,video_count"}).json()
    if (u.get("error") or {}).get("code") not in (None, "ok"): raise RuntimeError(u["error"].get("message", "tiktok error"))
    vids, cursor = [], None
    for _ in range(10):
        body = {"max_count": 20, **({"cursor": cursor} if cursor else {})}
        r = requests.post(f"{social.TT_API}/video/list/", headers=h, json=body, timeout=30,
                          params={"fields": "id,title,video_description,create_time,view_count,like_count,comment_count,share_count,duration"}).json()
        if (r.get("error") or {}).get("code") not in (None, "ok"): raise RuntimeError(r["error"].get("message", "tiktok list error"))
        d = r.get("data") or {}
        vids += d.get("videos") or []
        if not d.get("has_more"): break
        cursor = d.get("cursor")
    return {"followers": ((u.get("data") or {}).get("user") or {}).get("follower_count"), "videos": vids}

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
    TikTok views]]}}. A point every run (hourly) for a Short's first 7 days, then one every 6 hours up to 30 days."""
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
            pts.append([h, r["yt_views"], num(r["ig_views"]), num(r["tt_views"])]); changed.add(day)
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

def breakouts(rows, curves):
    """analytics/breakouts.csv: Shorts 2 to 48 hours old running at 3x or more the views recent Shorts had at the same
    age (from the hourly curves, 5 or more peers, at least 300 views). Views come in lopsided bursts, so the writer
    follows these up while the topic is hot (CLAUDE.md, What gets views)."""
    out, recent = [], [r for r in rows if r["posted"] and (NOW - utc(r["posted"])).total_seconds() <= 7 * 86400]
    for r in recent:
        age = (NOW - utc(r["posted"])).total_seconds() / 3600
        if not 2 <= age <= 48: continue
        peers = [p for p in (views_at(curves.get(rkey(x)), age) for x in recent if x is not r) if p is not None]
        if len(peers) < 5: continue
        typ = max(1.0, statistics.median(peers)); ratio = r["yt_views"] / typ
        if ratio >= 3 and r["yt_views"] >= 300:
            out.append({"short": r["short"], "title": r["title"], "category": r["category"], "hours_public": round(age, 1),
                        "views": r["yt_views"], "typical_at_this_age": round(typ), "times_typical": round(ratio, 1),
                        "youtube_url": r["youtube_url"]})
    out.sort(key=lambda b: -b["times_typical"])
    write_csv(OUT / "breakouts.csv", out, ["short", "title", "category", "hours_public", "views", "typical_at_this_age",
                                            "times_typical", "youtube_url"])
    return out

def relative(rows, field, out_field, min_age_h=24):
    """Each Short's `field` against the median of Shorts posted within 3 days of it (1.0 = typical); needs 3 peers."""
    aged = [r for r in rows if r["posted"] and r.get(field) not in ("", None) and (NOW - utc(r["posted"])).total_seconds() >= min_age_h * 3600]
    for r in rows:
        r[out_field] = ""
        if r not in aged: continue
        t = utc(r["posted"])
        peers = [float(x[field]) for x in aged if abs((utc(x["posted"]) - t).total_seconds()) <= 3 * 86400]
        if len(peers) >= 3 and statistics.median(peers): r[out_field] = round(float(r[field]) / statistics.median(peers), 3)

CATS = ["Gaming", "Film", "Music", "Sport", "Tech", "Science", "Entertainment"]

def update_hourly(rows, ig, tt):
    """analytics/hourly.csv: one row per hour (UTC, with UK day, hour and weekday) with the views gained since the last
    run on each platform and, for YouTube, in each category. 60 days kept."""
    p = OUT / "hourly.csv"
    hist = list(csv.DictReader(io.StringIO(p.read_text()))) if p.exists() else []
    last = load_json(CACHE / "last.json", {}) or {}
    prev_at, prev = utc(last.get("at")), last.get("yt") or {}
    hour = NOW.replace(minute=0, second=0, microsecond=0); ukh = hour.astimezone(UK)
    ig_total = sum(num(r["ig_views"]) or 0 for r in rows); tt_total = sum(int(v.get("view_count") or 0) for v in (tt or {}).get("videos", []))
    row = {"hour_utc": hour.strftime("%Y-%m-%dT%H:00Z"), "uk_day": ukh.strftime("%Y-%m-%d"), "uk_hour": ukh.strftime("%H"),
           "uk_weekday": ukh.strftime("%a"), "yt_total": sum(r["yt_views"] for r in rows),
           "ig_total": ig_total if ig else "", "tt_total": tt_total if tt else ""}
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
        row["tt_gained"] = max(0, tt_total - last["tt_total"]) if tt and last.get("tt_total") is not None else ""
    if hist and hist[-1]["hour_utc"] == row["hour_utc"] and "hours" in row:     # a second run within the same hour adds to it
        old = hist.pop()
        for k in ["hours", "yt_gained", "ig_gained", "tt_gained"] + [f"yt_{c.lower()}" for c in CATS + ["Other"]]:
            a, b = old.get(k), row.get(k)
            if a not in ("", None) and b not in ("", None): row[k] = round(float(a) + float(b), 2) if k == "hours" else int(float(a)) + int(b)
    hist.append(row)
    cutoff = (NOW - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H")
    hist = [h for h in hist if h["hour_utc"] >= cutoff]
    write_csv(p, hist, ["hour_utc", "uk_day", "uk_hour", "uk_weekday", "hours", "yt_total", "yt_gained", "ig_total", "ig_gained",
                        "tt_total", "tt_gained"] + [f"yt_{c.lower()}" for c in CATS + ["Other"]])
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "last.json").write_text(json.dumps({"at": NOW.isoformat(timespec="seconds"), "yt": {rkey(r): r["yt_views"] for r in rows},
                                                 "ig_total": ig_total if ig else None, "tt_total": tt_total if tt else None}))
    return hist

# ---------------- where, how found, who: from the full run's YouTube Analytics ----------------
TRAFFIC = {"SHORTS": "Shorts feed", "YT_SEARCH": "YouTube search", "SUBSCRIBER": "Subscribers", "EXT_URL": "Outside YouTube",
           "RELATED_VIDEO": "Suggested videos", "YT_CHANNEL": "Channel page", "NO_LINK_OTHER": "Direct or unknown",
           "PLAYLIST": "Playlists", "NOTIFICATION": "Notifications", "YT_OTHER_PAGE": "Other YouTube pages",
           "BROWSE": "Browse features", "HASHTAGS": "Hashtag pages", "SOUND_PAGE": "Sound pages", "END_SCREEN": "End screens"}

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
    write_csv(OUT / "audience.csv", demo, ["scope", "age", "gender", "viewer_pct"])

# ---------------- decisions: every change made from the data, with its reason ----------------
DEC_FIELDS = ["date", "area", "change", "why", "evidence", "check_on", "by"]

def log_decisions(table):
    """When a driver's verdict turns to "push" or "cut back" (or back to typical), add a line to decisions.csv: the
    writer's recipe changes with it, so Charlie can see what changed and why. Reviews add their own lines."""
    p, vp = OUT / "decisions.csv", CACHE / "verdicts.json"
    prev = load_json(vp, {}) or {}
    cur = {f"{t['feature']}|{t['value']}": t for t in table if t["n"] >= 5}
    rows = list(csv.DictReader(io.StringIO(p.read_text()))) if p.exists() else []
    today = str(NOW.astimezone(UK).date()); check = str(NOW.astimezone(UK).date() + dt.timedelta(days=7))
    for k, t in cur.items():
        was = (prev.get(k) or {}).get("verdict")
        if t["verdict"] == was or (was is None and t["verdict"] == "about typical"): continue
        if t["verdict"] == "push": change = f"Lean towards {t['feature_label'].lower()} \"{t['value']}\""
        elif t["verdict"] == "cut back": change = f"Use less {t['feature_label'].lower()} \"{t['value']}\""
        else: change = f"Back to normal for {t['feature_label'].lower()} \"{t['value']}\""
        why = f"{t['lift']}x typical views over {t['n']} Shorts" + (f" ({t['why']})" if t.get("why") else "")
        rows.append({"date": today, "area": t["feature_label"], "change": change, "why": why,
                     "evidence": f"drivers.csv: {t['feature']} = {t['value']}, n {t['n']}, lift {t['lift']}, median {t['median_rel']}",
                     "check_on": check, "by": "analytics (automatic)"})
    vp.write_text(json.dumps({k: {"verdict": t["verdict"], "lift": t["lift"], "n": t["n"]} for k, t in cur.items()}))
    rows.sort(key=lambda r: r["date"], reverse=True)
    write_csv(p, rows, DEC_FIELDS)

# ---------------- put it together ----------------
def main():
    import drivers as DRV
    OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
    errors, ours = {}, our_shorts()
    yt = ig = tt = None
    try: yt = youtube(ours)
    except Exception as e: errors["youtube"] = f"{type(e).__name__}: {e}"[:300]
    try: ig = instagram()
    except Exception as e: errors["instagram"] = f"{type(e).__name__}: {e}"[:300]
    try: tt = tiktok()
    except Exception as e: errors["tiktok"] = f"{type(e).__name__}: {e}"[:300]
    if not yt and FAST:
        print(json.dumps({"errors": errors})); return          # nothing fresh to write: keep the last good files

    rows = []
    aud = (yt or {}).get("audience") or {}
    short_cc = aud.get("short_countries") or {}
    ig_by_id = {m["id"]: m for m in (ig or {}).get("media", [])}
    ig_by_title = {norm((m.get("caption") or "").split("\n")[0]): m for m in (ig or {}).get("media", [])}
    tt_by_title = {norm((v.get("video_description") or v.get("title") or "").split("\n")[0]): v for v in (tt or {}).get("videos", [])}
    for vid, v in ((yt or {}).get("videos") or {}).items():
        if v.get("privacy") != "public": continue
        o = ours.get(vid, {})
        posted = utc(v.get("publish_at")) or utc(v.get("uploaded"))
        hours = max(1.0, (NOW - posted).total_seconds() / 3600) if posted else None
        s, a = yt["stats"].get(vid, {}), yt["analytics"].get(vid, {})
        key = norm(v["title"])
        im = ig_by_id.get(o.get("instagram_media")) or ig_by_title.get(key) or {}
        tv = tt_by_title.get(key) or {}
        uk = posted.astimezone(UK) if posted else None
        row = {
            "short": o.get("id", ""), "title": v["title"], "posted": posted.isoformat(timespec="minutes") if posted else "",
            "posted_day": posted.strftime("%Y-%m-%d") if posted else "", "slot_uk": uk.strftime("%H:%M") if uk else "",
            "category": o.get("category", ""), "format": o.get("format", ""), "mood": o.get("mood", ""),
            "hook": o.get("hook", ""), "hook_words": o.get("hook_words", ""), "seconds": o.get("seconds", ""),
            "yt_views": s.get("views", 0), "yt_likes": s.get("likes", 0), "yt_comments": s.get("comments", 0),
            "yt_engaged_views": a.get("engagedViews", ""), "yt_avg_viewed_pct": round(a["averageViewPercentage"], 1) if a.get("averageViewPercentage") is not None else "",
            "yt_shares": a.get("shares", ""), "yt_subs_gained": a.get("subscribersGained", ""),
            "ig_views": im.get("views", ""), "ig_reach": im.get("reach", ""), "ig_likes": im.get("like_count", ""),
            "ig_comments": im.get("comments_count", ""), "ig_shares": im.get("shares", ""), "ig_saves": im.get("saved", ""),
            "tt_views": tv.get("view_count", ""), "tt_likes": tv.get("like_count", ""), "tt_comments": tv.get("comment_count", ""),
            "tt_shares": tv.get("share_count", ""),
            "youtube_url": f"https://youtube.com/shorts/{vid}", "instagram_url": im.get("permalink", "")}
        curve = (yt.get("retention") or {}).get(vid)
        secs = o.get("seconds") or 0
        row["yt_held_3s_pct"] = at_point(curve, min(1.0, 3 / secs)) if curve and secs else ""      # still watching 3 seconds in
        row["yt_held_end_pct"] = at_point(curve, 0.95) if curve else ""                            # still watching at the end
        row["real_share"] = o.get("real_share", "")            # share of shots that are real images of the subject
        dr = drops(curve, o.get("timeline"), secs) if curve and secs else []
        row["yt_worst_beat"] = (lambda w: f"beat {w[1] + 1} ({w[2]}), -{w[0]} pts/s")(max(dr)) if dr else ""
        row["_drops"] = dr
        av, ev = a.get("views"), a.get("engagedViews")
        row["yt_engaged_pct"] = round(100 * ev / av) if av and ev is not None else ""             # stayed past the first seconds
        total = sum(int(row[k]) for k in ("yt_views", "ig_views", "tt_views") if str(row[k]).strip() not in ("", "None"))
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
        r["rel"] = r["views_vs_typical"]
    looks_out = look_scores(rows)
    hourly = update_hourly(rows, ig, tt)

    # per-day history: today's totals are appended to analytics/history.csv, so growth shows over time
    hist_p = OUT / "daily.csv"
    hist = list(csv.DictReader(io.StringIO(hist_p.read_text()))) if hist_p.exists() else []
    hist = [h for h in hist if not (h["day"] == str(TODAY) and h["source"] == "snapshot")]
    snap = {"day": str(TODAY), "source": "snapshot"}
    snap["yt_followers"] = (yt or {}).get("subs", "")
    snap["yt_views_total"] = sum(r["yt_views"] for r in rows)
    snap["ig_followers"] = (ig or {}).get("followers", "")
    snap["ig_views_total"] = sum(int(r["ig_views"]) for r in rows if str(r["ig_views"]).strip() not in ("", "None"))
    snap["tt_followers"] = (tt or {}).get("followers", "")
    snap["tt_views_total"] = sum(int(v.get("view_count") or 0) for v in (tt or {}).get("videos", []))
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
    fields = ["day", "source", "yt_followers", "yt_views_total", "ig_followers", "ig_views_total", "tt_followers",
              "tt_views_total", "yt_views_day", "yt_engaged_views_day", "yt_subs_gained_day"]
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
        "tiktok": {"followers": (tt or {}).get("followers"), "videos": len((tt or {}).get("videos", []))} if tt else None,
        "ypp": {"subscribers_needed": 1000, "shorts_views_needed_90_days": 10_000_000, "apply_before": str(YPP_DEADLINE),
                "days_left": (YPP_DEADLINE - TODAY).days,
                "subscribers_pct": round(100 * ((yt or {}).get("subs") or 0) / 1000, 1),
                "views_pct": round(100 * est / 10_000_000, 2),
                "views_needed_per_day": round(max(0, 10_000_000 - est) / max(1, min(90, (YPP_DEADLINE - TODAY).days))),
                "note": "Engaged views: YouTube's Analytics through its last day, plus live views since then at the recent "
                        "engaged share (YouTube's own figure lags a day or two)."},
        "tiktok_rewards": {"followers_needed": 10000, "views_needed_30_days": 100000, "min_video_seconds": 61},
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
        "tt_followers": summary["tiktok"]["followers"] if summary.get("tiktok") else ""}],
        ["as_of", "as_of_uk", "full_as_of_uk", "subscribers", "engaged_views_90d", "engaged_views_90d_youtube", "youtube_last_day",
         "views_all_time", "public_shorts", "needed_per_day", "days_left", "views_last_hour", "views_last_24h", "ig_followers", "tt_followers"])
    if not FAST:            # the slower reads: looks, posting times, audience, drivers and the writer's notes
        (OUT / "looks.json").write_text(json.dumps(looks_out, indent=1, ensure_ascii=False))
        slot_scores(rows)
        write_audience(aud)
        table, _base = DRV.analyse(rows)
        write_csv(OUT / "drivers.csv", table, ["feature", "feature_label", "value", "n", "lift", "median_rel", "verdict",
                                               "held_3s_pct", "avg_viewed_pct", "subs_per_1k", "shares_per_1k", "why"])
        log_decisions(table)
        follow = [f"Follow up {b['short'] or b['title']} (\"{b['title']}\"): {b['times_typical']}x the views recent Shorts had "
                  f"{b['hours_public']} hours in. Write one follow-up in the next run (a new angle, the next chapter, or the answer "
                  "to its top comment), title tied to it." for b in hot[:2]]
        (OUT / "insights.md").write_text(insights(rows, summary, table, follow + DRV.recipe(table, rows) + audience_recipe(aud), aud))
    print(json.dumps({"mode": summary["mode"], "shorts": len(rows), "errors": errors}, indent=1))

def look_scores(rows):
    """How each look option (templates/looks.json) does. Every Short public for 24 hours gets a score against Shorts posted
    within 3 days of it (1.0 = typical): 40% the share still watching 3 seconds in, 40% the average % viewed, 20% views an
    hour, using whichever are available. Each option's score is the median over the Shorts that used it."""
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
    def rel(r, field):
        v = r.get(field)
        if v in ("", None): return None
        t = utc(r["posted"])
        peers = [float(x[field]) for x in aged if x.get(field) not in ("", None) and abs((utc(x["posted"]) - t).total_seconds()) <= 3 * 86400]
        if len(peers) < 3: return None
        med = statistics.median(peers)
        return float(v) / med if med else None
    for r in aged:
        parts = [(w, x) for w, x in ((0.4, rel(r, "yt_held_3s_pct")), (0.4, rel(r, "yt_avg_viewed_pct")), (0.2, rel(r, "views_per_hour")))
                 if x is not None]
        if parts: r["look_score"] = round(sum(w * x for w, x in parts) / sum(w for w, _ in parts), 3)
    out = {"updated": NOW.isoformat(timespec="minutes"), "dimensions": {},
           "how": "Each Short against Shorts posted within 3 days of it (1.0 = typical): 40% still watching at 3 seconds, "
                  "40% average % viewed, 20% views an hour. An option's score is the median of its Shorts."}
    try: cat = LK.catalogue()
    except Exception: return out
    for dim, spec in cat["dimensions"].items():
        for opt in spec["options"]:
            used = [r for r in aged if r.get(f"look_{dim}") == opt and r.get("look_score") != ""]
            e = {"n": len(used)}
            if used:
                e["score"] = round(statistics.median(r["look_score"] for r in used), 3)
                for k, f in (("held_3s_pct", "yt_held_3s_pct"), ("avg_viewed_pct", "yt_avg_viewed_pct")):
                    vals = [float(r[f]) for r in used if r.get(f) not in ("", None)]
                    if vals: e[k] = round(statistics.median(vals), 1)
            out["dimensions"].setdefault(dim, {})[opt] = e
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
    p.write_text(json.dumps({"day": today, "updated": NOW.isoformat(timespec="minutes"),
                             "slots": {k: {"n": len(v), "score": round(statistics.median(v), 3)} for k, v in sorted(by.items())}}, indent=1))

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
            if got: lines.append(f"- {dim}: " + ", ".join(f"{k} {v['score']:.2f} ({v['n']})" for k, v in got))
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
