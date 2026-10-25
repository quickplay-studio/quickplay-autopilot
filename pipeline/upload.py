"""Upload rendered Shorts. Runs in its own job with only the Google client libraries installed.

usage: python upload.py <results dir>   (each subfolder: video.mp4, upload.json, status.json)

Each Short goes to the channel in its status ("channel", main when it has none; 25 October: the Daily line's other channels,
config shorts_channels), through that channel's own sign-in.
"""
import datetime as dt, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import youtube as Y

KEYS_MISSING = "approved, waiting for the YouTube keys (YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN)"
LIMIT_WAIT = "approved, waiting for YouTube's daily upload limit"


def signin_missing(channel):
    """Held for a channel whose sign-in cannot be used (it is looked for again by publish.py every hour)."""
    return f"approved, waiting for the {channel} channel's sign-in"


def hold(res, st, state):
    """A rendered Short YouTube can't take now (its daily limit, or the keys are missing) is kept as it is: the video
    becomes preview.mp4, record.py stores it as the draft release preview-<id> and moves the board to boards/ready, already
    approved, and publish.py (hourly) uploads it from there once there is room. Until 24 October such a Short stayed in
    the queue and was rendered again from scratch by the next run, 7 to 15 minutes each (audit M5), or, without the keys,
    was filed as done and never uploaded (audit M9)."""
    v = res / "video.mp4"
    if v.exists(): v.replace(res / "preview.mp4")
    st.update(state=state, approved=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              approved_by="automatic: nothing needed approval; YouTube could not take it yet")


def main(root):
    yt = Y.client() if Y.available() else None
    on_channel = {}
    if yt is not None:      # never upload the same Short twice (e.g. a re-run of an old commit)
        try: on_channel = {v["title"].strip().lower(): v["id"] for v in Y.recent_videos(yt, limit=100)}
        except Exception as e: print("could not list channel videos:", e)
    clients = {"main": (yt, on_channel)}

    def client_of(ch):
        """(client, the titles already on the channel) for one channel, built when its first Short comes; (None, {}) when
        its sign-in is missing or does not work."""
        if ch not in clients:
            c, on = None, {}
            if Y.connected(ch):
                try: c = Y.client_for(ch)
                except (Exception, SystemExit) as e: print(f"{ch}: the channel's sign-in did not work:", f"{type(e).__name__}: {e}"[:160])
            if c is not None:
                try: on = {v["title"].strip().lower(): v["id"] for v in Y.recent_videos(c, limit=100)}
                except Exception as e: print(f"could not list the {ch} channel's videos:", e)
            clients[ch] = (c, on)
        return clients[ch]

    limited = set()         # channels YouTube refused one for its daily limit ("*": for the shared quota): their rest wait
    for res in sorted(pathlib.Path(root).iterdir()):
        st_path = res / "status.json"
        if not st_path.exists(): continue
        st = json.loads(st_path.read_text())
        up = res / "upload.json"
        if st.get("state") != "rendered" or not up.exists() or st.get("mode") not in ("schedule", "private", "dry"):
            if st.get("state") == "rendered": st["state"] = "rendered (no upload)"
            st_path.write_text(json.dumps(st, indent=1, ensure_ascii=False)); continue
        u = json.loads(up.read_text())
        ch = st.get("channel") or u.get("channel") or "main"
        yt, on_channel = client_of(ch)
        dup = on_channel.get(u["title"].strip().lower())
        if u.get("flags") and not dup:
            # Waits for Charlie: kept as a preview (record.py stores it as a draft release), uploaded by publish.py once approved.
            (res / "video.mp4").replace(res / "preview.mp4")
            st["state"] = "awaiting approval"
            st_path.write_text(json.dumps(st, indent=1, ensure_ascii=False))
            print(st["id"], "awaiting approval:", "; ".join(u["flags"])); continue
        if yt is None:
            hold(res, st, KEYS_MISSING if ch == "main" else signin_missing(ch))
        elif dup:
            st.update(state="already on YouTube (not uploaded again)", video=dup, url=f"https://youtube.com/shorts/{dup}")
        elif ch in limited or "*" in limited:
            hold(res, st, LIMIT_WAIT)
        else:
            try:
                vid = Y.upload(yt, res / "video.mp4", u["title"], u["description"], u["tags"], u["category"],
                               u["slot"] if u["mode"] == "schedule" else None, localizations=u.get("localizations"),
                               **({"language": u["language"]} if u.get("language") else {}))
                st["uploaded_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
                st.update(state="scheduled" if u["mode"] == "schedule" else "uploaded (private)", video=vid,
                          url=f"https://youtube.com/shorts/{vid}", publish_at=u["slot"] or None)
                try:
                    kept = Y.video_status(yt, vid); st["youtube"] = kept
                    if u["mode"] == "schedule" and not kept.get("publish_at"):
                        st["state"] = "uploaded but not scheduled (check Studio)"
                except Exception as e:
                    st["youtube"] = {"error": str(e)[:200]}
            except Y.LimitReached as e:
                hold(res, st, LIMIT_WAIT); limited.add("*" if "quotaExceeded" in str(e) else ch)
            except Exception as e:
                st.update(state="upload failed", error=f"{type(e).__name__}: {e}"[:600])
        st_path.write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(st["id"], st["state"], st.get("url", ""))

if __name__ == "__main__":
    main(sys.argv[1])
