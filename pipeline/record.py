"""Write results back to the repository: status/<id>.json, review/<id>.jpg, and move each board.
Rendered or uploaded -> boards/done. Failed -> boards/failed. Waiting for the upload limit -> stays queued.
usage: python record.py <results dir>"""
import json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

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
        board = ROOT / st["board"]
        if not board.exists() or st["state"].startswith("waiting"): continue
        dest = ROOT / "boards" / ("failed" if "fail" in st["state"] else "done"); dest.mkdir(exist_ok=True)
        shutil.move(str(board), str(dest / board.name))
        print(sid, "->", dest.name, "|", st["state"])

if __name__ == "__main__":
    main(sys.argv[1])
