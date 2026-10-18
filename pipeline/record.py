"""Write results back to the repository: status/<id>.json, review/<id>.jpg, and move each board.
Rendered or uploaded -> boards/done. Failed -> boards/failed. Waiting for the upload limit -> stays queued.
Waiting for Charlie's approval -> boards/ready, with the render kept as a draft release preview-<id>.
usage: python record.py <results dir>"""
import json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def preview(res, sid, prev):
    """Keep a Short that waits for approval as a draft release (only the repo's owners can see drafts):
    video.mp4 (YouTube version), social.mp4 (TikTok and Instagram version) and upload.json. publish.py uploads from it."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp); files = []
        for src, name in ((prev, "video.mp4"), (res / "social.mp4", "social.mp4"), (res / "upload.json", "upload.json")):
            if src.exists(): shutil.copy(src, tmp / name); files.append(str(tmp / name))
        tag = f"preview-{sid}"
        subprocess.run(["gh", "release", "delete", tag, "-y"], capture_output=True)    # a re-render replaces its old preview
        r = subprocess.run(["gh", "release", "create", tag, *files, "--draft", "--title", f"{sid} preview",
                            "--notes", "Waiting for approval. Uploaded to YouTube, TikTok and Instagram once approved."],
                           capture_output=True, text=True)
    if r.returncode == 0: return {"preview_release": tag, "preview_url": r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""}
    return {"preview_error": r.stderr.strip()[:200]}

def main(root):
    for res in sorted(pathlib.Path(root).iterdir()):
        sp = res / "status.json"
        if not sp.exists(): continue
        st = json.loads(sp.read_text()); sid = st["id"]
        (ROOT / "status").mkdir(exist_ok=True); (ROOT / "review").mkdir(exist_ok=True)
        (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        if (res / "review.jpg").exists(): shutil.copy(res / "review.jpg", ROOT / "review" / f"{sid}.jpg")
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
        board = ROOT / st["board"]
        if not board.exists() or st["state"].startswith("waiting"): continue
        folder = "ready" if st["state"] == "awaiting approval" else ("failed" if "fail" in st["state"] else "done")
        try: is_reserve = bool(json.loads(board.read_text()).get("reserve"))
        except Exception: is_reserve = False
        if is_reserve and folder == "ready": folder = "reserve"                 # evergreen spares wait apart (publish.py)
        if sid.startswith("TEST-") and folder != "ready": folder = "test"     # test boards never mix with real ones
        dest = ROOT / "boards" / folder; dest.mkdir(exist_ok=True)
        shutil.move(str(board), str(dest / board.name))
        print(sid, "->", dest.name, "|", st["state"])

if __name__ == "__main__":
    main(sys.argv[1])
