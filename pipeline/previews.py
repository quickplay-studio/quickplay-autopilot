"""Download the preview video of every Short waiting in boards/ready, for the lineup message.
Uses GitHub's REST API (GraphQL, which `gh release download` needs for drafts, is blocked in Claude sessions).
usage: python pipeline/previews.py <out dir> [--reserve] [--social]      prints one file path per Short
  --reserve  the evergreen spares in boards/reserve      --social  the TikTok and Instagram version instead
Files over 15 MB are re-encoded smaller for chat (the uploaded video keeps its full quality).
"""
import json, pathlib, shutil, subprocess, sys

def chat_size(path):
    if path.stat().st_size <= 15e6 or not shutil.which("ffmpeg"): return
    tmp = path.with_suffix(".small.mp4")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-maxrate", "3000k", "-bufsize", "6000k", "-c:a", "copy", "-movflags", "+faststart", str(tmp)])
    if r.returncode == 0 and tmp.exists(): tmp.replace(path)

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "quickplay-studio/quickplay-autopilot"

def main(out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    rels = json.loads(subprocess.run(["gh", "api", f"repos/{REPO}/releases?per_page=100"], capture_output=True, text=True, check=True).stdout)
    by_tag = {r["tag_name"]: r for r in rels}
    folder = "reserve" if "--reserve" in sys.argv else "ready"       # --reserve: the evergreen spares awaiting approval
    for p in sorted((ROOT / "boards" / folder).glob("*.json")):
        sid = json.loads(p.read_text())["id"]
        want = "social.mp4" if "--social" in sys.argv else "video.mp4"
        asset = next((a for a in (by_tag.get(f"preview-{sid}") or {}).get("assets", []) if a["name"] == want), None)
        if not asset:
            print(f"{sid}: no preview found"); continue
        dest = out / (f"{sid}.social.mp4" if want == "social.mp4" else f"{sid}.mp4")
        with open(dest, "wb") as f:
            subprocess.run(["gh", "api", "-H", "Accept: application/octet-stream", f"repos/{REPO}/releases/assets/{asset['id']}"], stdout=f, check=True)
        chat_size(dest)
        print(dest)

if __name__ == "__main__":
    main([a for a in sys.argv[1:] if not a.startswith("--")][0])
