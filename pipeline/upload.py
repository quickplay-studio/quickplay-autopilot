"""Upload rendered Shorts. Runs in its own job with only the Google client libraries installed.

usage: python upload.py <results dir>   (each subfolder: video.mp4, upload.json, status.json)
"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import youtube as Y

def main(root):
    yt = Y.client() if Y.available() else None
    for res in sorted(pathlib.Path(root).iterdir()):
        st_path = res / "status.json"
        if not st_path.exists(): continue
        st = json.loads(st_path.read_text())
        up = res / "upload.json"
        if st.get("state") != "rendered" or not up.exists() or st.get("mode") not in ("schedule", "private"):
            if st.get("state") == "rendered": st["state"] = "rendered (no upload)"
            st_path.write_text(json.dumps(st, indent=1, ensure_ascii=False)); continue
        u = json.loads(up.read_text())
        if yt is None:
            st["state"] = "rendered (YouTube keys missing)"
        else:
            try:
                vid = Y.upload(yt, res / "video.mp4", u["title"], u["description"], u["tags"], u["category"],
                               u["slot"] if u["mode"] == "schedule" else None)
                st.update(state="scheduled" if u["mode"] == "schedule" else "uploaded (private)", video=vid,
                          url=f"https://youtube.com/shorts/{vid}", publish_at=u["slot"] or None)
                try:
                    kept = Y.video_status(yt, vid); st["youtube"] = kept
                    if u["mode"] == "schedule" and not kept.get("publish_at"):
                        st["state"] = "uploaded but not scheduled (check Studio)"
                except Exception as e:
                    st["youtube"] = {"error": str(e)[:200]}
            except Y.LimitReached:
                st["state"] = "waiting for YouTube's daily upload limit"
            except Exception as e:
                st.update(state="upload failed", error=f"{type(e).__name__}: {e}"[:600])
        st_path.write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(st["id"], st["state"], st.get("url", ""))

if __name__ == "__main__":
    main(sys.argv[1])
