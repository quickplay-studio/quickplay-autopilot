"""How every Short is doing on YouTube, Instagram and TikTok, in one place.

Writes analytics/ (read by the daily writer, and uploaded to the stats dashboard each morning):
  shorts.csv     one row per Short: when, topic, format, and views, likes, comments, shares on each platform,
                 YouTube average % viewed, engaged views and subscribers gained, views per hour since posting,
                 retention (share still watching 3 seconds in and at the end)
  daily.csv      one row per day and platform: views, followers, followers gained
  summary.json   totals, monetisation progress (YouTube Partner Program, TikTok Creator Rewards) and the latest numbers
  insights.md    what's working: best and worst Shorts, averages by category, format, hook length, posting slot
Only the channel's own numbers are read; tokens are never written out. Each platform is optional: one that isn't
connected (or fails) is noted in summary.json and the rest still run.
usage: python pipeline/analytics.py
"""
import csv, datetime as dt, io, json, os, pathlib, statistics, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
OUT = ROOT / "analytics"
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
    for d in ("done", "ready", "queue", "failed", "rejected"):
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
    return out

# ---------------- YouTube ----------------
def youtube():
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
    ya = build("youtubeAnalytics", "v2", credentials=Y.creds(), cache_discovery=False)
    start = str(TODAY - dt.timedelta(days=120))

    def query(metrics, **kw):
        """Run an Analytics query; drop engagedViews if this API version doesn't know it."""
        try:
            r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=str(TODAY), metrics=metrics, **kw).execute()
        except HttpError as e:
            if "engagedViews" in metrics:
                return query(metrics.replace("engagedViews,", "").replace(",engagedViews", ""), **kw)
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
    return {"subs": subs, "videos": vids, "stats": stats, "analytics": per_video, "daily": daily, "retention": retention}

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
    for m in media:
        r = requests.get(f"{api}/{m['id']}/insights", params={"metric": "views,reach,shares,saved,total_interactions",
                                                              "access_token": tok}, timeout=30).json()
        if "error" in r: insights_error = r["error"].get("message", "")[:200]; continue
        for d in r.get("data", []):
            m[d["name"]] = (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value"))
    return {"followers": me.get("followers_count"), "username": me.get("username"), "media": media, "insights_error": insights_error}

# ---------------- TikTok ----------------
def tiktok():
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

def main():
    OUT.mkdir(exist_ok=True)
    errors, ours = {}, our_shorts()
    yt = ig = tt = None
    try: yt = youtube()
    except Exception as e: errors["youtube"] = f"{type(e).__name__}: {e}"[:300]
    try: ig = instagram()
    except Exception as e: errors["instagram"] = f"{type(e).__name__}: {e}"[:300]
    try: tt = tiktok()
    except Exception as e: errors["tiktok"] = f"{type(e).__name__}: {e}"[:300]

    rows = []
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
        uk = posted.astimezone(ZoneInfo("Europe/London")) if posted else None
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
        rows.append(row)
    rows.sort(key=lambda r: r["posted"], reverse=True)
    looks_out = look_scores(rows)
    (OUT / "looks.json").write_text(json.dumps(looks_out, indent=1, ensure_ascii=False))
    slot_scores(rows)

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
    write_csv(OUT / "shorts.csv", rows, [k for k in rows[0] if not k.startswith("_")] if rows else ["short", "title"])

    # monetisation progress
    d90 = [d for d in (yt or {}).get("daily", []) if d["day"] >= str(TODAY - dt.timedelta(days=90))]
    v90 = sum(int(d.get("engagedViews") or d.get("views") or 0) for d in d90)
    summary = {
        "updated": NOW.isoformat(timespec="minutes"), "errors": errors,
        "youtube": {"subscribers": (yt or {}).get("subs"), "public_shorts": len(rows),
                    "views_all_time": sum(r["yt_views"] for r in rows),
                    "views_last_90_days": v90, "views_measure": "engaged views" if any("engagedViews" in d for d in d90) else "views"},
        "instagram": {"followers": (ig or {}).get("followers"), "posts": len((ig or {}).get("media", [])),
                      "insights_error": (ig or {}).get("insights_error")} if ig else None,
        "tiktok": {"followers": (tt or {}).get("followers"), "videos": len((tt or {}).get("videos", []))} if tt else None,
        "ypp": {"subscribers_needed": 1000, "shorts_views_needed_90_days": 10_000_000, "apply_before": str(YPP_DEADLINE),
                "days_left": (YPP_DEADLINE - TODAY).days,
                "subscribers_pct": round(100 * ((yt or {}).get("subs") or 0) / 1000, 1),
                "views_pct": round(100 * v90 / 10_000_000, 2),
                "views_needed_per_day": round(max(0, 10_000_000 - v90) / max(1, min(90, (YPP_DEADLINE - TODAY).days)))},
        "tiktok_rewards": {"followers_needed": 10000, "views_needed_30_days": 100000, "min_video_seconds": 61},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    (OUT / "insights.md").write_text(insights(rows, summary))
    print(json.dumps({"shorts": len(rows), "errors": errors}, indent=1))

def look_scores(rows):
    """How each look option (templates/looks.json) does. Every Short public for 24 hours gets a score against Shorts posted
    within 3 days of it (1.0 = typical): 40% the share still watching 3 seconds in, 40% the average % viewed, 20% views an
    hour, using whichever are available. Each option's score is the median over the Shorts that used it."""
    import looks as LK
    look_by_id = {}
    for p in (ROOT / "status").glob("QD-*.json"):
        st = load_json(p, {})
        if st.get("look"): look_by_id[st.get("id")] = st["look"]
    for r in rows:
        lk = look_by_id.get(r["short"]) or {}
        for d in ("captions", "voice", "energy", "grade"): r[f"look_{d}"] = lk.get(d, "")
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

def insights(rows, s):
    """A short read for the daily writer: what to repeat and what to drop."""
    L = [f"# What's working (updated {s['updated'][:16].replace('T', ' ')} UTC)", ""]
    y, p = s["youtube"], s["ypp"]
    L += [f"YouTube Partner Program: {y['subscribers'] or 0:,} of 1,000 subscribers, {y['views_last_90_days']:,} of 10,000,000 "
          f"Shorts {y['views_measure']} in the last 90 days. Apply before {p['apply_before']} ({p['days_left']} days): "
          f"after that new channels need 20M. Needed from now: about {p['views_needed_per_day']:,} views a day.", ""]
    if s["errors"]: L += ["Not available this time: " + "; ".join(f"{k} ({v[:80]})" for k, v in s["errors"].items()), ""]
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
