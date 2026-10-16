"""Channel report: status/channel.json, read straight from YouTube (read-only keys).
Lists recent uploads with privacy, scheduled time and views, and flags anything that should be public by now but isn't.
usage: python pipeline/report.py
"""
import datetime as dt, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import youtube as Y

def main():
    if not Y.available():
        print("report: no YouTube keys"); return
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for v in Y.recent_videos(Y.client(), limit=150):
        pa, up = Y.utc(v["publish_at"]), Y.utc(v["uploaded"])
        flag = ""
        if v["privacy"] == "private" and pa and pa < now - dt.timedelta(minutes=20): flag = "should be public by now"
        elif v["privacy"] == "private" and not pa: flag = "private and not scheduled"
        rows.append({"video": v["id"], "title": v["title"], "privacy": v["privacy"], "publish_at": v["publish_at"],
                     "uploaded": v["uploaded"], "views": v.get("views"), "flag": flag})
    out = {"checked": now.isoformat(timespec="minutes").replace("+00:00", "Z"),
           "uploads_last_24h": sum(1 for r in rows if r["uploaded"] and now - Y.utc(r["uploaded"]) < dt.timedelta(hours=24)),
           "scheduled": sum(1 for r in rows if r["privacy"] == "private" and r["publish_at"] and Y.utc(r["publish_at"]) > now),
           "public": sum(1 for r in rows if r["privacy"] == "public"),
           "flagged": [r for r in rows if r["flag"]],
           "videos": rows}
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / "channel.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"report: {len(rows)} videos, {out['scheduled']} scheduled, {out['public']} public, {len(out['flagged'])} flagged, "
          f"{out['uploads_last_24h']} uploads in the last 24 hours")

if __name__ == "__main__":
    main()
