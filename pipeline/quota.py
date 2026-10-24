"""The YouTube allowance guard (Charlie, 19 October): uploads come first.

The allowance resets at midnight Pacific time: 08:00 UK most of the year, 07:00 UK in the weeks when only one side has
changed its clocks (25 October to 1 November 2026, and late March). All four channels share it: they sign in through one
Google Cloud project (YT_CLIENT_ID). Each workflow records what it spends in status/quota/<workflow>.json (one file each,
so they never overwrite each other).

Since 1 June 2026 (the YouTube Data API's revision history) uploads (videos.insert) and searches (search.list) each have
their own bucket, 100 calls a day by default, and every other method shares the 10,000 units (comments and title or
privacy changes 50, reads 1). youtube_quota_model "buckets" (the default) counts it that way: a clip upload goes ahead
only while the upload calls made today, plus the main channel's Shorts still to come, plus a margin, stay under the upload
bucket; an optional extra only while the units spent, plus a margin, stay under the 10,000. A quotaExceeded on an upload
stops uploads (and nothing else) until the reset. Until 24 October every upload and search was counted as 100 of the
10,000 units, so on 23 and 24 October clip promotes and comments were held back for room the uploads never used, while
the real limit, 100 uploads a day across the four channels, was not watched at all. "units" restores that old model.
  config.json: youtube_quota_model, youtube_quota_per_day, youtube_uploads_per_day, youtube_searches_per_day,
  youtube_upload_units, youtube_quota_margin, youtube_upload_margin, youtube_search_margin
"""
import datetime as dt, json, os, pathlib, re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = ROOT / "status" / "quota"
CFG = json.loads((ROOT / "config.json").read_text())
PT = ZoneInfo("America/Los_Angeles")
COST = {"upload": int(CFG.get("youtube_upload_units", 100)), "comment": 50, "playlist": 50, "title": 50, "reply": 50,
        "search": 100}
MODE = str(CFG.get("youtube_quota_model", "buckets"))
BUCKETS = {"upload": int(CFG.get("youtube_uploads_per_day", 100)), "search": int(CFG.get("youtube_searches_per_day", 100))}


def bucket(what):
    """The bucket of its own a call draws on ("upload" or "search"), or None for the shared units. Callers name their
    calls ("upload", "clip upload", "competitor search", "angle search") and pass the old unit price (COST), so the part
    above that price (a search's video details, 1 or 2 units) still counts in the shared units."""
    if MODE != "buckets": return None
    w = str(what or "").lower()
    return "upload" if "upload" in w else "search" if "search" in w else None


def today():
    return str(dt.datetime.now(PT).date())


# The upload ceiling (Charlie, 21 October: as many Shorts a day as YouTube allows). YouTube publishes no number, so the
# limit learns: it starts at config daily_limit, rises by upload_limit_step after each day YouTube accepted every upload
# and the day was filled, up to upload_limit_max (what the API allowance leaves room for), and settles where YouTube
# first refuses an upload (uploadLimitExceeded: the limit becomes what it accepted in those 24 hours).
LIMIT_P = ROOT / "status" / "upload_limit.json"


def _limit_state():
    try: return json.loads(LIMIT_P.read_text())
    except Exception: return {}


def daily_limit():
    """Shorts a day: the ceiling learned from YouTube when there is one (status/upload_limit.json), else config daily_limit."""
    base = int(CFG.get("daily_limit", 24))
    try: return max(1, int(_limit_state().get("limit") or base))
    except (TypeError, ValueError): return base


VOLUME_P = ROOT / "status" / "volume.json"


def target():
    """Shorts a day we choose to make (Charlie, 23 October: fewer, better, a week's test): status/volume.json "per_day"
    (set and judged by analytics.volume_test), else config shorts_per_day, never above the learned ceiling (daily_limit)."""
    try: n = int(json.loads(VOLUME_P.read_text()).get("per_day") or 0)
    except Exception: n = 0
    n = n or int(CFG.get("shorts_per_day") or 0)
    return max(1, min(daily_limit(), n)) if n else daily_limit()


def _decide(change, why, evidence):
    p = ROOT / "analytics" / "decisions.csv"
    import csv
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["date", "area", "change", "why", "evidence", "check_on", "by"])
        d = dt.date.today()
        w.writerow([str(d), "Uploads a day", change, why, evidence, str(d + dt.timedelta(days=7)), "quota.py (automatic)"])


def refused(uploads_24h):
    """YouTube refused an upload for its daily limit: the ceiling becomes what it accepted in the last 24 hours."""
    st, now = _limit_state(), dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    new = max(int(CFG.get("upload_limit_min", 10)), int(uploads_24h))
    old = daily_limit()
    st.update(limit=new, refused_at=now, refused_with=int(uploads_24h))
    LIMIT_P.parent.mkdir(parents=True, exist_ok=True); LIMIT_P.write_text(json.dumps(st, indent=1))
    if new != old:
        _decide(f"Upload ceiling {old} to {new}", f"YouTube refused an upload with {uploads_24h} uploads in the last 24 hours",
                "uploadLimitExceeded from the YouTube Data API")
    return new


def learn(uploads_24h):
    """Called every hour by publish.py: a day after the last change, if the day was filled and YouTube refused nothing in
    the last 48 hours, the ceiling rises by upload_limit_step (up to upload_limit_max). Returns the limit."""
    st, now = _limit_state(), dt.datetime.now(dt.timezone.utc)
    limit, top, step = daily_limit(), int(CFG.get("upload_limit_max", 72)), int(CFG.get("upload_limit_step", 6))
    def age(k):
        try: return (now - dt.datetime.fromisoformat(st[k])).total_seconds() / 3600
        except (KeyError, ValueError, TypeError): return 1e9
    if limit >= top or age("refused_at") < 48 or age("raised_at") < 24 or int(uploads_24h) < limit - 1: return limit
    new = min(top, limit + step)
    st.update(limit=new, raised_at=now.isoformat(timespec="minutes"), raised_with=int(uploads_24h))
    LIMIT_P.parent.mkdir(parents=True, exist_ok=True); LIMIT_P.write_text(json.dumps(st, indent=1))
    _decide(f"Upload ceiling {limit} to {new}", f"YouTube accepted every upload with {uploads_24h} in 24 hours and no refusal in 48 hours",
            "status/upload_limit.json")
    return new


def _mine():
    name = re.sub(r"[^a-z0-9]+", "-", os.environ.get("GITHUB_WORKFLOW", "local").lower()).strip("-") or "local"
    return DIR / f"{name}.json"


def _load(p):
    try: d = json.loads(p.read_text())
    except Exception: return {}
    return d if d.get("day") == today() else {}


def _save(d):
    DIR.mkdir(parents=True, exist_ok=True)
    _mine().write_text(json.dumps(d, indent=1))


def _upgrade(d):
    """A record written before the buckets (no "calls"): its uploads and searches move from units to calls, so the day
    of the change counts them once."""
    if MODE != "buckets" or "calls" in d: return d
    d["calls"], by = {}, d.setdefault("by", {})
    for what, u in list(by.items()):
        b = bucket(what)
        if not (b and COST[b]): continue
        n = int(u) // COST[b]
        d["calls"][b] = d["calls"].get(b, 0) + n
        d["units"] = int(d.get("units") or 0) - n * COST[b]
        by[what] = int(u) - n * COST[b]
        if not by[what]: by.pop(what)
    return d


def spend(units, what="other"):
    """Records what this workflow spent today: a call in its own bucket (an upload or a search), and units."""
    d = _upgrade(_load(_mine()) or {"day": today(), "units": 0, "by": {}})
    b, units = bucket(what), int(units)
    if b:
        calls = d.setdefault("calls", {}); calls[b] = calls.get(b, 0) + 1
        units = max(0, units - COST[b])
    d["units"] = int(d.get("units") or 0) + units
    if units or not b: d.setdefault("by", {})[what] = d.get("by", {}).get(what, 0) + units
    _save(d)


def exhausted(kind="upload"):
    """YouTube refused a call for quota (kind "upload", "search" or "units"): what draws on that bucket stops until the
    reset. (The only caller is an upload; with youtube_quota_model "units" every optional extra stops, as before.)"""
    d = _upgrade(_load(_mine()) or {"day": today(), "units": 0, "by": {}})
    ex = d.get("exhausted")
    ex = dict(ex) if isinstance(ex, dict) else ({"upload": ex} if ex else {})
    ex[kind if MODE == "buckets" else "units"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    d["exhausted"] = ex
    _save(d)


def _norm(f):
    """One workflow's record of today as (units, {bucket: calls}, {bucket: refused at}), whichever version wrote it (a
    record from before the buckets refused only uploads, and counted each upload and search as its old price in units)."""
    f = _upgrade(json.loads(json.dumps(f)))
    ex = f.get("exhausted")
    ex = dict(ex) if isinstance(ex, dict) else ({"upload": ex} if ex else {})
    if MODE != "buckets" and ex: ex = {"units": next(iter(ex.values()))}
    return max(0, int(f.get("units") or 0)), dict(f.get("calls") or {}), ex


def _records():
    return [_norm(_load(p)) for p in DIR.glob("*.json")] if DIR.exists() else []


def state():
    """(units spent today across all workflows, whether YouTube refused a call for quota in the shared units today; with
    youtube_quota_model "units", any refusal)."""
    recs = _records()
    return sum(u for u, _, _ in recs), any("units" in ex for _, _, ex in recs)


def calls(b):
    """Calls made today in one of the buckets of their own ("upload", "search"), across all workflows."""
    return sum(c.get(b, 0) for _, c, _ in _records())


def bucket_refused(b):
    return any(b in ex for _, _, ex in _records())


def uploads_left():
    """Uploads still to come before the reset: the day's planned number (target(), and the weekly video) less the uploads
    made since it. (The learned ceiling was used until 24 October: 40 kept places for a 15-a-day plan held back 2,500
    units every day.)"""
    start = dt.datetime.now(PT).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc)
    done = 0
    for p in (ROOT / "status").glob("QD-*.json"):
        try: up = json.loads(p.read_text()).get("uploaded_at")
        except Exception: continue
        try:
            if up and dt.datetime.fromisoformat(up.replace("Z", "+00:00")) >= start: done += 1
        except ValueError: pass
    return max(0, target() + 1 - done)


def allow(units, what="extra"):
    """True when an optional call fits without touching what the day's Shorts need: an upload or a search in its own
    bucket (a clip upload keeps room for the main channel's Shorts still to come), anything else in the shared units."""
    b, units = bucket(what), int(units)
    if b:
        if bucket_refused(b):
            print(f"YouTube allowance: {what} skipped, YouTube refused a {b} for quota today"); return False
        keep = int(CFG.get(f"youtube_{b}_margin", 3)) + (uploads_left() if b == "upload" and what != "upload" else 0)
        made = calls(b)
        if made + keep + 1 > BUCKETS[b]:
            print(f"YouTube allowance: {what} skipped ({made} of {BUCKETS[b]} {b} calls made today, {keep} kept for the Shorts)")
            return False
        units = max(0, units - COST[b])
        if not units: return True
    spent, refused = state()
    if refused:
        print(f"YouTube allowance: {what} skipped, YouTube refused a call for quota today"); return False
    keep = int(CFG.get("youtube_quota_margin", 1000)) + (0 if MODE == "buckets" else uploads_left() * COST["upload"])
    if spent + keep + units <= int(CFG.get("youtube_quota_per_day", 10000)): return True
    print(f"YouTube allowance: {what} skipped ({spent} units spent today, {keep} kept)")
    return False
