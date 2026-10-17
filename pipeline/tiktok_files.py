"""Today's TikTok package for Charlie to upload on desktop (TikTok Studio): the 5 TikTok picks' videos (the version with
platform-safe music), their captions and the time each goes public on YouTube, so he can schedule TikTok to match.
Uses GitHub's REST API (GraphQL is blocked in Claude sessions).
usage: python pipeline/tiktok_files.py <out dir> [YYYY-MM-DD]     prints one block per Short
"""
import datetime as dt, json, pathlib, subprocess, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "quickplay-studio/quickplay-autopilot"
sys.path.insert(0, str(ROOT / "pipeline"))
from social import caption

def main(out, day=None):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    day = day or dt.date.today().isoformat()
    rels = json.loads(subprocess.run(["gh", "api", f"repos/{REPO}/releases?per_page=100"], capture_output=True, text=True, check=True).stdout)
    by_tag = {r["tag_name"]: r for r in rels}
    for folder in ("ready", "done"):
        for p in sorted((ROOT / "boards" / folder).glob("QD-*.json")):
            b = json.loads(p.read_text())
            if b.get("created") != day or not b.get("tiktok"): continue
            sid = b["id"]; stp = ROOT / "status" / f"{sid}.json"
            st = json.loads(stp.read_text()) if stp.exists() else {}
            rel = by_tag.get(st.get("social_release") or "") or by_tag.get(f"preview-{sid}") or by_tag.get(f"social-{sid}")
            asset = next((a for a in (rel or {}).get("assets", []) if a["name"] == "social.mp4"), None)
            when = st.get("publish_at")
            when = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/London")).strftime("%a %d %b %H:%M") if when else "not scheduled yet"
            path = "no video found"
            if asset:
                dest = out / f"{sid}-tiktok.mp4"
                with open(dest, "wb") as f:
                    subprocess.run(["gh", "api", "-H", "Accept: application/octet-stream", f"repos/{REPO}/releases/assets/{asset['id']}"], stdout=f, check=True)
                path = str(dest)
            print(f"=== {sid} · YouTube public {when}\nfile: {path}\ncaption:\n{caption(st, b, 'tiktok')}\n")

if __name__ == "__main__":
    main(*sys.argv[1:3])
