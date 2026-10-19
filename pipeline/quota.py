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
    return max(0, int(CFG.get("daily_limit", 24)) + 1 - done)


def allow(units, what="extra"):
    """True when an optional extra of `units` fits without touching what the day's uploads need."""
    spent, refused = state()
    if refused:
        print(f"YouTube allowance: {what} skipped, YouTube refused an upload for quota today"); return False
    keep = uploads_left() * COST["upload"] + int(CFG.get("youtube_quota_margin", 1000))
    if spent + keep + int(units) <= int(CFG.get("youtube_quota_per_day", 10000)): return True
    print(f"YouTube allowance: {what} skipped ({spent} units spent today, {keep} kept for the uploads still to come)")
    return False
