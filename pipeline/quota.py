"""The YouTube allowance guard (Charlie, 19 October): uploads come first.

Uploads, creator comments, playlists, title swaps, comment replies and the writer's angle searches all draw on one daily
YouTube API allowance, which resets at midnight Pacific time (08:00 UK, 07:00 in winter). Each workflow records what it
spends in status/quota/<workflow>.json (one file each, so they never overwrite each other). allow() lets an optional
extra go ahead only while what is spent today, plus what the rest of the day's uploads will need, plus a margin, plus
the extra, stays under the allowance. Once YouTube refuses an upload for quota, every extra stops until the reset.
  config.json: youtube_quota_per_day, youtube_upload_units, youtube_quota_margin
"""
import datetime as dt, json, os, pathlib, re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = ROOT / "status" / "quota"
CFG = json.loads((ROOT / "config.json").read_text())
PT = ZoneInfo("America/Los_Angeles")
COST = {"upload": int(CFG.get("youtube_upload_units", 100)), "comment": 50, "playlist": 50, "title": 50, "reply": 50,
        "search": 100}


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


def spend(units, what="other"):
    """Records units this workflow spent today."""
    d = _load(_mine()) or {"day": today(), "units": 0, "by": {}}
    d["units"] += int(units); d["by"][what] = d["by"].get(what, 0) + int(units)
    _save(d)


def exhausted():
    """YouTube refused an upload for quota: every optional extra stops until the reset."""
    d = _load(_mine()) or {"day": today(), "units": 0, "by": {}}
    d["exhausted"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    _save(d)


def state():
    """(units spent today across all workflows, whether YouTube refused an upload for quota today)."""
    files = [_load(p) for p in DIR.glob("*.json")] if DIR.exists() else []
    return sum(int(f.get("units") or 0) for f in files), any(f.get("exhausted") for f in files)


def uploads_left():
    """Uploads still to come before the reset: the day's limit (and the weekly video) less the uploads made since it."""
    start = dt.datetime.now(PT).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt.timezone.utc)
    done = 0
    for p in (ROOT / "status").glob("QD-*.json"):
        try: up = json.loads(p.read_text()).get("uploaded_at")
        except Exception: continue
        try:
            if up and dt.datetime.fromisoformat(up.replace("Z", "+00:00")) >= start: done += 1
        except ValueError: pass
    return max(0, daily_limit() + 1 - done)


def allow(units, what="extra"):
    """True when an optional extra of `units` fits without touching what the day's uploads need."""
    spent, refused = state()
    if refused:
        print(f"YouTube allowance: {what} skipped, YouTube refused an upload for quota today"); return False
    keep = uploads_left() * COST["upload"] + int(CFG.get("youtube_quota_margin", 1000))
    if spent + keep + int(units) <= int(CFG.get("youtube_quota_per_day", 10000)): return True
    print(f"YouTube allowance: {what} skipped ({spent} units spent today, {keep} kept for the uploads still to come)")
    return False
