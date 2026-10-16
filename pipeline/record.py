"""Write results back to the repository: status/<id>.json, review/<id>.jpg, and move each board.
Rendered or uploaded -> boards/done. Failed -> boards/failed. Waiting for the upload limit -> stays queued.
usage: python record.py <results dir>"""
import json, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

def main(root):
    for res in sorted(pathlib.Path(root).iterdir()):
        sp = res / "status.json"
        if not sp.exists(): continue
        st = json.loads(sp.read_text()); sid = st["id"]
        (ROOT / "status").mkdir(exist_ok=True); (ROOT / "review").mkdir(exist_ok=True)
        (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        if (res / "review.jpg").exists(): shutil.copy(res / "review.jpg", ROOT / "review" / f"{sid}.jpg")
        board = ROOT / st["board"]
        if not board.exists() or st["state"].startswith("waiting"): continue
        dest = ROOT / "boards" / ("failed" if "fail" in st["state"] else "done"); dest.mkdir(exist_ok=True)
        shutil.move(str(board), str(dest / board.name))
        print(sid, "->", dest.name, "|", st["state"])

if __name__ == "__main__":
    main(sys.argv[1])
