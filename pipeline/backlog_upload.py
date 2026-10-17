"""Upload Shorts that were rendered before the GitHub pipeline existed (the "backlog" branch holds them encrypted).
Each keeps its planned slot unless that slot has passed or is taken; then it gets the next free slot on today's grid.
Stops at YouTube's daily upload limit; the next scheduled run carries on. Never uploads a title that's already on the channel.

usage: python pipeline/backlog_upload.py <backlog dir with manifest.json> <results dir>     (needs MUSIC_KEY to decrypt)
"""
import datetime as dt, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import youtube as Y
import plan as PL

def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def main(src, out):
    src, out = pathlib.Path(src), pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    # Today's Shorts come first: while any are queued or waiting on main, the backlog waits (they share the upload limits).
    if subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "main"], capture_output=True).returncode == 0:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", "FETCH_HEAD", "boards/queue", "boards/ready"],
                               capture_output=True, text=True).stdout.split()
        daily = [n for n in names if n.endswith(".json") and "/TEST-" not in n]
        if daily:
            print("today's Shorts first:", len(daily), "queued or waiting on main; the backlog waits"); return
    man = json.loads((src / "manifest.json").read_text())
    items, gate = man["items"], man.get("gate")
    yt = Y.client()
    chan = Y.recent_videos(yt, limit=150)
    on = {v["title"].strip().lower(): v for v in chan}
    taken = {Y.utc(v["publish_at"]) for v in chan if v["publish_at"]}
    now = dt.datetime.now(dt.timezone.utc)

    # The first item is a test: nothing else is uploaded until it has gone public at its scheduled time.
    if gate:
        g = next(i for i in items if i["id"] == gate)
        v = on.get(g["title"].strip().lower())
        if v is None:
            items = [g]
        elif v["privacy"] != "public":
            pa = Y.utc(v["publish_at"])
            if pa and pa < now - dt.timedelta(minutes=25):
                d = out / gate; d.mkdir(exist_ok=True)
                (d / "status.json").write_text(json.dumps({"id": gate, "title": g["title"], "board": f"backlog/{gate}", "video": v["id"],
                    "state": "upload failed: scheduled time passed but it is still private (API uploads may be locked)",
                    "publish_at": v["publish_at"], "source": "backlog"}, indent=1, ensure_ascii=False))
                print("gate failed:", gate, "is still private after its publish time"); return
            print("waiting for", gate, "to go public at", v["publish_at"]); items = [g]

    def free_slot():
        day = (now + dt.timedelta(hours=1)).astimezone(PL.UK).date()
        for _ in range(30):
            for t in PL.day_slots(day):
                if t >= now + dt.timedelta(hours=1) and t not in taken:
                    taken.add(t); return t
            day += dt.timedelta(days=1)

    for it in items:
        st = {"id": it["id"], "title": it["title"], "board": f"backlog/{it['id']}", "mode": "schedule", "source": "backlog"}
        d = out / it["id"]; d.mkdir(exist_ok=True)
        hit = on.get(it["title"].strip().lower())
        if hit:
            st.update(state="already on YouTube (not uploaded again)", video=hit["id"], url=f"https://youtube.com/shorts/{hit['id']}",
                      publish_at=hit["publish_at"])
            (d / "status.json").write_text(json.dumps(st, indent=1, ensure_ascii=False)); print(it["id"], st["state"]); continue
        slot = Y.utc(it["publish_at"])
        if slot < now + dt.timedelta(minutes=50) or slot in taken:
            slot = free_slot(); st["note"] = f"planned slot {it['publish_at']} had passed or was taken"
        else:
            taken.add(slot)
        mp4 = d / "video.mp4"
        subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", str(src / it["file"]), "-out", str(mp4),
                        "-pass", "env:MUSIC_KEY"], check=True)
        try:
            vid = Y.upload(yt, mp4, it["title"], it["description"], it["tags"], it["category"], iso(slot))
            st.update(state="scheduled", video=vid, url=f"https://youtube.com/shorts/{vid}", publish_at=iso(slot),
                      uploaded_at=iso(dt.datetime.now(dt.timezone.utc)))
            try: st["youtube"] = Y.video_status(yt, vid)
            except Exception as e: st["youtube"] = {"error": str(e)[:200]}
        except Y.LimitReached:
            st["state"] = "waiting for YouTube's daily upload limit"
            (d / "status.json").write_text(json.dumps(st, indent=1, ensure_ascii=False)); mp4.unlink(missing_ok=True)
            print(it["id"], st["state"]); break
        except Exception as e:
            st.update(state="upload failed", error=f"{type(e).__name__}: {e}"[:600])
        mp4.unlink(missing_ok=True)
        (d / "status.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(it["id"], st["state"], st.get("publish_at", ""))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
