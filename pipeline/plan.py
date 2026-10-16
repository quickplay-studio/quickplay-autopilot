"""Pick queued boards for this run and give each a posting slot. Prints `boards=<json>` for the GitHub matrix.

Rules
- At most DAILY_LIMIT uploads in any 24 hours, counting every upload on the channel (including ones made by hand).
- Slots: 09:00 to 22:30 UK every 90 minutes. A slot already taken on YouTube is never reused.
- A Short goes to the first free slot at least 3 hours away (time to render and process).
- A board may fix its slot with "publish_at": "YYYY-MM-DD HH:MM" (UK time), or set "mode": "private"
  (test upload, not scheduled) or "mode": "none" (render only).
"""
import datetime as dt, json, os, pathlib, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
SLOTS = [(9, 0), (10, 30), (12, 0), (13, 30), (15, 0), (16, 30), (18, 0), (19, 30), (21, 0), (22, 30)]
LIMIT = int(os.environ.get("DAILY_LIMIT", "10"))
LEAD = dt.timedelta(hours=3)

def main():
    queue = sorted((ROOT / "boards" / "queue").glob("*.json"))
    if not queue:
        print("boards=[]"); return
    import youtube as Y
    now = dt.datetime.now(dt.timezone.utc)
    taken, recent, online = set(), 0, Y.available()
    if online:
        for v in Y.recent_videos(Y.client()):
            if v["publish_at"]: taken.add(Y.utc(v["publish_at"]))
            up = Y.utc(v["uploaded"])
            if up and now - up < dt.timedelta(hours=24): recent += 1
    for s in (ROOT / "status").glob("*.json"):
        st = json.loads(s.read_text())
        if st.get("publish_at"): taken.add(Y.utc(st["publish_at"]))
    capacity = max(0, LIMIT - recent)

    def next_slot():
        day = (now + LEAD).astimezone(UK).date()
        while True:
            for h, m in SLOTS:
                t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UK).astimezone(dt.timezone.utc)
                if t >= now + LEAD and t not in taken:
                    taken.add(t); return t
            day += dt.timedelta(days=1)

    jobs = []
    for p in queue:
        b = json.loads(p.read_text())
        mode = b.get("mode", "schedule")
        if mode in ("schedule", "private") and not online: mode = "none"
        if mode != "none" and len([j for j in jobs if j["mode"] != "none"]) >= capacity: continue
        slot = ""
        if mode == "schedule":
            t = None
            if b.get("publish_at"):
                t = dt.datetime.strptime(b["publish_at"], "%Y-%m-%d %H:%M").replace(tzinfo=UK).astimezone(dt.timezone.utc)
                if t < now + dt.timedelta(minutes=45): t = None
                else: taken.add(t)
            slot = (t or next_slot()).isoformat().replace("+00:00", "Z")
        jobs.append({"board": str(p.relative_to(ROOT)), "id": b["id"], "slot": slot, "mode": mode})
    print(f"online={online} capacity={capacity} recent_uploads={recent} queued={len(queue)} running={len(jobs)}", file=sys.stderr)
    print("boards=" + json.dumps(jobs))

if __name__ == "__main__":
    main()
