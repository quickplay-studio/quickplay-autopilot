"""One line on how the whole pipeline is doing, for the top of the lineup message.
usage: python pipeline/health.py
"""
import datetime as dt, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import quota
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = dt.datetime.now(dt.timezone.utc)

def load(p, default=None):
    try: return json.loads((ROOT / p).read_text())
    except Exception: return default

def when(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception: return None

def main():
    cfg = load("config.json", {}); problems = []
    uploads = 0
    for p in (ROOT / "status").glob("QD-*.json"):
        st = load(p.relative_to(ROOT), {}) or {}
        t = when(st.get("uploaded_at"))
        if t and NOW - t <= dt.timedelta(hours=24): uploads += 1
        for k, label in (("instagram_error", "Instagram post"), ("facebook_error", "Facebook post"), ("social_error", "cross-post")):
            v = str(st.get(k) or "")
            t = when(v[:16].replace(" ", "T") + ":00+00:00") if v else None
            if v and t and NOW - t <= dt.timedelta(hours=48): problems.append(f"{st['id']} {label} failed")
    failed = sorted(p.stem for p in (ROOT / "boards" / "failed").glob("*.json"))
    if failed: problems.append(f"{len(failed)} in failed ({', '.join(failed[:3])})")
    soc = load("status/social.json", {}) or {}
    for k, label in (("instagram", "Instagram"), ("facebook", "Facebook")):
        v = soc.get(k) or {}
        if k == "facebook" and (not v or "not connected" in str(v.get("error", ""))): continue    # not set up yet
        if soc and not v.get("ok"): problems.append(f"{label} sign-in not working")
        if k == "facebook" and v.get("data_access_expires"):       # Meta wants the key renewed every 90 days or so
            left = (dt.datetime.fromtimestamp(int(v["data_access_expires"]), dt.timezone.utc) - NOW).days
            if left <= 14: problems.append(f"Facebook key needs renewing within {max(0, left)} days (redo the Facebook key steps)")
    if not (load("status/youtube_connect.json", {}) or {}).get("connected"): problems.append("YouTube engagement sign-in missing")
    ks, kp = load("status/keys.json", {}) or {}, []          # pipeline/keys.py, every 3 hours: a key that fails or ends within 14 days
    t = when(ks.get("checked"))
    if ks and t and NOW - t > dt.timedelta(hours=12): kp.append(f"key check last ran {int((NOW - t).total_seconds() // 3600)} hours ago")
    for r in ks.get("keys") or []:
        if r.get("id") == "FB_PAGE_TOKEN": continue         # the Facebook line above says it
        if r.get("status") in ("failing", "expiring") or (r.get("status") == "missing" and r.get("needed")):
            kp.append(f"key {r.get('what')} is {r.get('status')}" + (f" (ends {r['expires']})" if r.get("status") == "expiring" and r.get("expires") else ""))
    problems[:0] = kp               # first: an expired key stops the project quietly, and the line shows only the first four
    tr = load("trends/latest.json", {}) or {}
    if tr.get("date") != str(dt.datetime.now(ZoneInfo("Europe/London")).date()): problems.append(f"trends last refreshed {tr.get('date', 'never')}")
    s = load("analytics/summary.json", {}) or {}
    if s.get("errors"): problems.append("stats: " + ", ".join(s["errors"]) + " not read")
    y, p = s.get("youtube") or {}, s.get("ypp") or {}
    ypp = (f"YPP {y.get('subscribers') or 0:,}/1,000 subs, {y.get('views_last_90_days') or 0:,}/10M views"
           f" (about {p.get('views_needed_per_day', 0):,} a day needed)") if y else "YPP numbers not in yet"
    head = "Health: all good" if not problems else f"Health: {len(problems)} to look at: " + "; ".join(problems[:4])
    print(f"{head} · {uploads}/{quota.daily_limit()} YouTube uploads in 24h · {ypp}")

if __name__ == "__main__":
    main()
