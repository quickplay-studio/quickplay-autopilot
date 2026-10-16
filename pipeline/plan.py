"""Pick queued boards for this run and give each a posting slot. Prints `boards=<json>` for the GitHub matrix.

Rules (numbers live in config.json)
- At most daily_limit uploads in any 24 hours, counting every upload on the channel (including ones made by hand).
  YouTube may enforce a lower limit; then the extra boards wait in the queue and the next run tries again.
- Slots: slots_per_day a day, from slot_first, every slot_every_minutes (UK time). A slot already taken is never reused.
- A Short goes to the first free slot at least lead_hours away (time to render and process).
- A board may fix its slot with "publish_at": "YYYY-MM-DD HH:MM" (UK time), or set "mode": "private"
  (test upload, not scheduled) or "mode": "none" (render only).
- A board that fails pipeline/validate.py is not rendered: it goes to boards/failed with the reasons.
"""
import datetime as dt, json, os, pathlib, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
CFG = json.loads((ROOT / "config.json").read_text())
LIMIT = int(os.environ.get("DAILY_LIMIT", CFG.get("daily_limit", 10)))
LEAD = dt.timedelta(hours=float(CFG.get("lead_hours", 3)))

def day_slots(day):
    h, m = map(int, CFG.get("slot_first", "09:00").split(":"))
    first = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UK)
    step = dt.timedelta(minutes=int(CFG.get("slot_every_minutes", 90)))
    return [(first + step * i).astimezone(dt.timezone.utc) for i in range(int(CFG.get("slots_per_day", 10)))]

def main():
    queue = sorted((ROOT / "boards" / "queue").glob("*.json"))
    if not queue:
        print("boards=[]"); return
    import youtube as Y, validate as V
    now = dt.datetime.now(dt.timezone.utc)
    # Uploads in the last 24 hours: ours come from status files (exact upload time). YouTube only gives a reliable upload
    # time for videos that are still private (once public, the playlist date becomes the publish time), so other
    # private uploads are added from the channel; anything else is caught by YouTube's own limit error.
    taken, recent, online = set(), 0, Y.available()
    statuses = [json.loads(s.read_text()) for s in (ROOT / "status").glob("*.json") if s.name != "channel.json"]
    ours = {st.get("video") for st in statuses if st.get("video")}
    for st in statuses:
        if st.get("publish_at"): taken.add(Y.utc(st["publish_at"]))
        up = Y.utc(st.get("uploaded_at"))
        if up and now - up < dt.timedelta(hours=24): recent += 1
    if online:
        for v in Y.recent_videos(Y.client()):
            if v["publish_at"]: taken.add(Y.utc(v["publish_at"]))
            up = Y.utc(v["uploaded"])
            if v["id"] not in ours and v["privacy"] != "public" and up and now - up < dt.timedelta(hours=24): recent += 1
    capacity = max(0, LIMIT - recent)

    def next_slot():
        day = (now + LEAD).astimezone(UK).date()
        for _ in range(60):
            for t in day_slots(day):
                if t >= now + LEAD and t not in taken:
                    taken.add(t); return t
            day += dt.timedelta(days=1)
        raise RuntimeError("no free slot in the next 60 days")

    jobs, uploads = [], 0
    for p in queue:
        try: b = json.loads(p.read_text())
        except Exception: b = {"id": p.stem}
        errs = V.check(b, p)[0] if "beats" in b else ["not a valid board"]
        if errs:
            jobs.append({"board": str(p.relative_to(ROOT)), "id": b.get("id", p.stem), "slot": "", "mode": "reject",
                         "errors": "; ".join(errs)[:900]})
            continue
        mode = b.get("mode", "schedule")
        if mode in ("schedule", "private") and not online: mode = "none"
        if mode != "none":
            if uploads >= capacity: continue
            uploads += 1
        slot = ""
        if mode == "schedule":
            t = None
            if b.get("publish_at"):
                t = dt.datetime.strptime(b["publish_at"], "%Y-%m-%d %H:%M").replace(tzinfo=UK).astimezone(dt.timezone.utc)
                if t < now + dt.timedelta(minutes=45): t = None
                else: taken.add(t)
            slot = (t or next_slot()).isoformat().replace("+00:00", "Z")
        jobs.append({"board": str(p.relative_to(ROOT)), "id": b["id"], "slot": slot, "mode": mode})
    print(f"online={online} limit={LIMIT} capacity={capacity} recent_uploads={recent} queued={len(queue)} running={len(jobs)}",
          file=sys.stderr)
    print("boards=" + json.dumps(jobs, ensure_ascii=False))

if __name__ == "__main__":
    main()
