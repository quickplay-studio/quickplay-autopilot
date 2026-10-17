"""Download the preview video of every Short waiting in boards/ready, for the lineup message.
Uses GitHub's REST API (GraphQL, which `gh release download` needs for drafts, is blocked in Claude sessions).
usage: python pipeline/previews.py <out dir>      prints one file path per Short
"""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "quickplay-studio/quickplay-autopilot"

def main(out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    rels = json.loads(subprocess.run(["gh", "api", f"repos/{REPO}/releases?per_page=100"], capture_output=True, text=True, check=True).stdout)
    by_tag = {r["tag_name"]: r for r in rels}
    for p in sorted((ROOT / "boards" / "ready").glob("*.json")):
        sid = json.loads(p.read_text())["id"]
        asset = next((a for a in (by_tag.get(f"preview-{sid}") or {}).get("assets", []) if a["name"] == "video.mp4"), None)
        if not asset:
            print(f"{sid}: no preview found"); continue
        dest = out / f"{sid}.mp4"
        with open(dest, "wb") as f:
            subprocess.run(["gh", "api", "-H", "Accept: application/octet-stream", f"repos/{REPO}/releases/assets/{asset['id']}"], stdout=f, check=True)
        print(dest)

if __name__ == "__main__":
    main(sys.argv[1])
