"""Pick queued boards for this run and give each a posting slot. Prints `boards=<json>` for the GitHub matrix.

Rules (numbers live in config.json)
- At most upload_limit_24h uploads in any 24 hours (default daily_limit), counting every upload on the channel
  (including ones made by hand). YouTube may enforce a lower limit; then the extra boards wait in the queue and the next
  run tries again. daily_limit is how many Shorts a day the writer makes; slots_per_day caps how many go public a day.
- A board whose "created" date is a later day (the 20:50 evening run writes the first part of tomorrow) gets that day's
  slots, never tonight's.
- Slots: slots_per_day a day. Until 30 Shorts have results: from slot_first, every slot_every_minutes (UK time); then the
  times learned from results (analytics/slots.json, see learned_slots). A slot already taken is never reused.
- A Short goes to the first free slot at least lead_hours away (time to render and process).
- A board may fix its slot with "publish_at": "YYYY-MM-DD HH:MM" (UK time), or set "mode": "private"
  (test upload, not scheduled), "mode": "none" (render only) or "mode": "dry" (rendered and held for approval like a real
  Short, but never uploaded: tests the approval path).
- A board that fails pipeline/validate.py is not rendered: it goes to boards/failed with the reasons.
- Approval (config "approval"): "all" = every Short waits for Charlie's OK after rendering; "flagged" = only Shorts with a
  reason to look (the writer's "flag", validator warnings, or render checks) wait; "none" = nothing waits.
  Waiting Shorts are rendered but not uploaded, so they don't use the daily upload limit; pipeline/publish.py uploads
  them once approved.
"""
import datetime as dt, json, os, pathlib, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
CFG = json.loads((ROOT / "config.json").read_text())
LIMIT = int(os.environ.get("DAILY_LIMIT", CFG.get("upload_limit_24h", CFG.get("daily_limit", 10))))
LEAD = dt.timedelta(hours=float(CFG.get("lead_hours", 3)))

def _mins(hm):
    h, m = map(int, hm.split(":")); return h * 60 + m

def learned_slots(n):
    """The day's posting times learned from results (analytics/slots.json, refreshed once a day so a day's times stay
    fixed): each half hour from 07:00 to 22:30 scores by how Shorts posted at or near it did against Shorts posted
    around the same days; the best n are kept at least 75 minutes apart. Times with little data get a small bonus so
    they're still tried. None until 30 Shorts have results."""
    try: stats = json.loads((ROOT / "analytics" / "slots.json").read_text()).get("slots") or {}
    except Exception: return None
    if sum(v.get("n", 0) for v in stats.values()) < 30: return None
    def score(c):
        num = den = 0.0
        for k, v in stats.items():
            d = abs(_mins(k) - _mins(c))
            if d <= 60:
                w = v.get("n", 0) * (1.0 if d == 0 else 0.5 if d <= 30 else 0.25)
                num += w * v.get("score", 1.0); den += w
        sc = (num + 3.0) / (den + 3.0)
        return max(sc, 1.03) if den < 2 else sc
    ranked = sorted((f"{h:02d}:{m:02d}" for h in range(7, 23) for m in (0, 30)), key=lambda c: (-score(c), c))
    for gap in (75, 60, 45, 30):          # 20 a day needs half-hour spacing
        picked = []
        for c in ranked:
            if all(abs(_mins(c) - _mins(q)) >= gap for q in picked): picked.append(c)
            if len(picked) == n: return sorted(picked)
    return None

def day_slots(day):
    n = int(CFG.get("slots_per_day", 10))
    times = learned_slots(n)
    if times:
        return [dt.datetime(day.year, day.month, day.day, *map(int, t.split(":")), tzinfo=UK).astimezone(dt.timezone.utc)
                for t in times]
    h, m = map(int, CFG.get("slot_first", "09:00").split(":"))
    first = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UK)
    step = dt.timedelta(minutes=int(CFG.get("slot_every_minutes", 90)))
    return [(first + step * i).astimezone(dt.timezone.utc) for i in range(n)]

def schedule_state(now, yt=None):
    """(taken slots, uploads in the last 24 hours, YouTube reachable). Our uploads come from status files (exact upload
    time). YouTube only gives a reliable upload time for videos that are still private (once public, the playlist date
    becomes the publish time), so other private uploads are added from the channel; anything else is caught by YouTube's
    own limit error."""
    import youtube as Y
    taken, recent, online = set(), 0, Y.available()
    statuses = []
    for f in (ROOT / "status").glob("*.json"):
        if f.name == "channel.json": continue
        try: statuses.append(json.loads(f.read_text()))
        except Exception: pass
    ours = {st.get("video") for st in statuses if st.get("video")}
    for st in statuses:
        if st.get("publish_at"): taken.add(Y.utc(st["publish_at"]))
        up = Y.utc(st.get("uploaded_at"))
        if up and now - up < dt.timedelta(hours=24): recent += 1
    if online:
        for v in Y.recent_videos(yt or Y.client()):
            if v["publish_at"]: taken.add(Y.utc(v["publish_at"]))
            up = Y.utc(v["uploaded"])
            if v["id"] not in ours and v["privacy"] != "public" and up and now - up < dt.timedelta(hours=24): recent += 1
    return taken, recent, online

def slot_picker(now, taken):
    def next_slot(created=None):
        """The first free slot at least lead_hours away, on or after the board's "created" day (UK)."""
        day = (now + LEAD).astimezone(UK).date()
        try:
            want = dt.date.fromisoformat(str(created)[:10]) if created else None
            if want and want > day: day = want
        except ValueError: pass
        for _ in range(60):
            for t in day_slots(day):
                if t >= now + LEAD and t not in taken:
                    taken.add(t); return t
            day += dt.timedelta(days=1)
        raise RuntimeError("no free slot in the next 60 days")
    return next_slot

def hold_reasons(b, warnings):
    """Why this Short should wait for Charlie's approval (empty list: it can go out on its own)."""
    mode = CFG.get("approval", "flagged")
    if b.get("reserve"):            # evergreen spare: waits in boards/reserve (publish.py), however approval is set
        return ["reserve: approved in advance, posted only on a day nothing new was written"] + \
               ([f"writer: {b['flag']}"] if b.get("flag") else []) + [f"check: {w}" for w in warnings]
    if mode == "none": return []
    out = ["approval is on for every Short (config.json)"] if mode == "all" else []
    if b.get("flag"): out.append(f"writer: {b['flag']}")
    out += [f"check: {w}" for w in warnings]
    return out

def main():
    queue = sorted((ROOT / "boards" / "queue").glob("*.json"))
    if not queue:
        print("boards=[]"); return
    import validate as V
    now = dt.datetime.now(dt.timezone.utc)
    taken, recent, online = schedule_state(now)
    capacity = max(0, LIMIT - recent)
    uk_today = now.astimezone(UK).date()
    if uk_today.weekday() == 6:      # Sunday: keep one upload for the weekly long video (weekly.py) until it's up
        wk = ROOT / "status" / f"weekly-{uk_today}.json"
        try: done_wk = bool(json.loads(wk.read_text()).get("video"))
        except Exception: done_wk = False
        if not done_wk: capacity = max(0, capacity - 1)
    next_slot = slot_picker(now, taken)

    import looks as LK         # each new Short's look: caption style, voice, energy, grade (templates/looks.json)
    stats, seen = LK.load_stats(), []
    for sp in (ROOT / "status").glob("QD-*.json"):
        try: st = json.loads(sp.read_text())
        except Exception: continue
        if st.get("look"): seen.append((st.get("rendered", ""), st["look"]))
    recent_looks = [lk for _, lk in sorted(seen, key=lambda x: x[0])][-5:]

    jobs, uploads = [], 0
    for p in queue:
        try: b = json.loads(p.read_text())
        except Exception: b = {"id": p.stem}
        errs, warns = V.check(b, p) if "beats" in b else (["not a valid board"], [])
        if errs:
            jobs.append({"board": str(p.relative_to(ROOT)), "id": b.get("id", p.stem), "slot": "", "mode": "reject",
                         "errors": "; ".join(errs)[:900]})
            continue
        mode = b.get("mode", "schedule")
        if mode in ("schedule", "private") and not online: mode = "none"
        hold = hold_reasons(b, warns) if mode != "none" else []
        if mode == "dry" and not hold: hold = ["dry run: always waits for approval, never uploaded"]
        if mode != "none" and not hold:
            if uploads >= capacity: continue
            uploads += 1
        slot = ""
        if mode == "schedule" and not hold:
            t = None
            if b.get("publish_at"):
                t = dt.datetime.strptime(b["publish_at"], "%Y-%m-%d %H:%M").replace(tzinfo=UK).astimezone(dt.timezone.utc)
                if t < now + dt.timedelta(minutes=45): t = None
                else: taken.add(t)
            slot = (t or next_slot(b.get("created"))).isoformat().replace("+00:00", "Z")
        look = b.get("look") if isinstance(b.get("look"), dict) else LK.choose(b["id"], recent_looks, stats)
        recent_looks.append(look)
        jobs.append({"board": str(p.relative_to(ROOT)), "id": b["id"], "slot": slot, "mode": mode, "hold": hold, "look": look})
    print(f"online={online} limit={LIMIT} capacity={capacity} recent_uploads={recent} queued={len(queue)} running={len(jobs)}",
          file=sys.stderr)
    print("boards=" + json.dumps(jobs, ensure_ascii=False))

if __name__ == "__main__":
    main()
