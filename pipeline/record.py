"""Write results back to the repository: status/<id>.json, review/<id>.jpg, and move each board.
Rendered or uploaded -> boards/done. Failed -> boards/failed. Expired (freshness.py) -> boards/expired.
Waiting for Charlie's approval -> boards/ready, with the render kept as a draft release preview-<id>.
Held by upload.py (YouTube's daily limit, or the keys missing) -> boards/ready, approved, with the same draft release, so
publish.py uploads it without a new render; only if the draft can't be kept does it stay queued and render again.
usage: python record.py <results dir>"""
import json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def preview(res, sid, prev, notes="Waiting for approval. Uploaded to YouTube, TikTok and Instagram once approved."):
    """Keep a Short that waits (for approval, for YouTube's daily limit, or for the YouTube keys) as a draft release (only
    the repo's owners can see drafts): video.mp4 (YouTube version), social.mp4 (TikTok and Instagram version) and
    upload.json. publish.py uploads from it."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp); files = []
        for src, name in ((prev, "video.mp4"), (res / "social.mp4", "social.mp4"), (res / "upload.json", "upload.json")):
            if src.exists(): shutil.copy(src, tmp / name); files.append(str(tmp / name))
        tag = f"preview-{sid}"
        subprocess.run(["gh", "release", "delete", tag, "-y"], capture_output=True)    # a re-render replaces its old preview
        r = subprocess.run(["gh", "release", "create", tag, *files, "--draft", "--title", f"{sid} preview", "--notes", notes],
                           capture_output=True, text=True)
    if r.returncode == 0: return {"preview_release": tag, "preview_url": r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""}
    return {"preview_error": r.stderr.strip()[:200]}


HELD = "approved, waiting"          # upload.py held a rendered Short (YouTube's daily limit, or the keys missing): see hold()
KEYS_TITLE = "🔑 The YouTube keys are missing: Shorts wait as previews"


def keys_alert(statuses):
    """One issue while Shorts wait for the YouTube keys (needs Charlie: only he can put a secret back), closed by the
    first batch that uploads again."""
    try:
        import alerts as A
        waiting = [s["id"] for s in statuses if str(s.get("state", "")).startswith(HELD + " for the YouTube keys")]
        if waiting:
            A.raise_issue(KEYS_TITLE, f"{len(waiting)} rendered Short(s) wait as previews because the render workflow has no YouTube "
                          f"keys ({', '.join(waiting[:12])}). Put YT_CLIENT_ID, YT_CLIENT_SECRET and YT_REFRESH_TOKEN back at "
                          "https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions (or ask Claude). "
                          "Nothing is lost: the hourly publish run uploads them once the keys work, if their story is still current.",
                          labels=["needs-charlie"])
        elif any(s.get("video") for s in statuses): A.clear(KEYS_TITLE, "Shorts upload again.")
    except Exception as e: print("keys alert:", str(e)[:160])


def main(root):
    seen = []
    for res in sorted(pathlib.Path(root).iterdir()):
        sp = res / "status.json"
        if not sp.exists(): continue
        st = json.loads(sp.read_text()); sid = st["id"]; seen.append(st)
        (ROOT / "status").mkdir(exist_ok=True); (ROOT / "review").mkdir(exist_ok=True)
        (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        if (res / "review.jpg").exists(): shutil.copy(res / "review.jpg", ROOT / "review" / f"{sid}.jpg")
        if (res / "review_social.jpg").exists(): shutil.copy(res / "review_social.jpg", ROOT / "review" / f"{sid}.social.jpg")
        soc = res / "social.mp4"
        if soc.exists() and st.get("video") and not st.get("social_release"):
            tag = f"social-{sid}"
            r = subprocess.run(["gh", "release", "create", tag, str(soc), "--draft", "--title", tag,
                                "--notes", "TikTok and Instagram version, removed once posted."], capture_output=True, text=True)
            if r.returncode == 0: st["social_release"] = tag
            else: st.setdefault("social_errors", []).append(f"release: {r.stderr.strip()[:200]}")
            (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        prev = res / "preview.mp4"
        if st.get("state") == "awaiting approval" and prev.exists() and not st.get("preview_release"):
            st.update(preview(res, sid, prev))
            (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        held = str(st.get("state", "")).startswith(HELD)
        if held and not st.get("preview_release"):
            got = preview(res, sid, prev, "Rendered and approved; waiting for room on YouTube (its daily limit, or the keys). "
                          "publish.py uploads it from here, then posts the social version.") if prev.exists() else {"preview_error": "no preview.mp4"}
            st.update(got)
            if not st.get("preview_release"):        # the draft could not be kept: wait in the queue and render again, as before
                st["state"] = "waiting for YouTube's daily upload limit"; st.pop("approved", None); held = False
            (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        board = ROOT / st["board"]
        if not board.exists() or st["state"].startswith("waiting"): continue
        if st.get("late"):           # freshness.py's decision on a late Short, kept now the job can commit (plan.py cannot)
            try:
                import freshness as FR
                FR.log({**json.loads(board.read_text()), "id": sid}, st["late"], "render")
            except Exception as e: print(sid, "late log:", str(e)[:120])
        folder = "ready" if st["state"] == "awaiting approval" else ("failed" if "fail" in st["state"] else "done")
        if st["state"].startswith("expired"): folder = "expired"                # freshness.py: missed its day, story moved on
        if held: folder = "ready"                                              # approved: publish.py uploads it from its preview
        try: is_reserve = bool(json.loads(board.read_text()).get("reserve"))
        except Exception: is_reserve = False
        if is_reserve and folder == "ready": folder = "reserve"                 # evergreen spares wait apart (publish.py)
        if sid.startswith("TEST-") and folder != "ready": folder = "test"     # test boards never mix with real ones
        dest = ROOT / "boards" / folder; dest.mkdir(exist_ok=True)
        shutil.move(str(board), str(dest / board.name))
        print(sid, "->", dest.name, "|", st["state"])
    keys_alert(seen)

if __name__ == "__main__":
    main(sys.argv[1])
