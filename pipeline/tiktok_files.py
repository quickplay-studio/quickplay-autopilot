"""The day's TikTok picks (the 5 boards with "tiktok": true), in YouTube-time order, for Charlie to post.

  python pipeline/tiktok_files.py <out dir> [YYYY-MM-DD] --db              one JSON file per Short in <out dir>/tiktok-db/,
        ready for ArtifactData (collection "tiktok" on the TikTok queue page); prints one short line per Short, no captions
  python pipeline/tiktok_files.py <out dir> [YYYY-MM-DD] --captions-only   prints each caption and YouTube time
  python pipeline/tiktok_files.py <out dir> [YYYY-MM-DD]                   also downloads each video (social.mp4), for
        uploading by hand (tiktok_mode "manual", or a draft TikTok refused)
Uses GitHub's REST API (GraphQL is blocked in Claude sessions).
"""
import datetime as dt, json, pathlib, subprocess, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "quickplay-studio/quickplay-autopilot"
sys.path.insert(0, str(ROOT / "pipeline"))
from social import caption

def picks(day):
    out = []
    for folder in ("ready", "done"):
        for p in sorted((ROOT / "boards" / folder).glob("QD-*.json")):
            b = json.loads(p.read_text())
            if b.get("created") != day or not b.get("tiktok"): continue
            stp = ROOT / "status" / f"{b['id']}.json"
            out.append((b, json.loads(stp.read_text()) if stp.exists() else {}))
    return sorted(out, key=lambda x: (x[1].get("publish_at") or "9999", x[0]["id"]))

def draft_state(st):
    if st.get("tiktok"): return "sent"
    if st.get("tiktok_error"): return "failed: " + st["tiktok_error"].split(" ", 2)[-1][:160]
    if st.get("tiktok_skipped"): return "skipped: " + st["tiktok_skipped"][:160]
    return "on its way"

def uk(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/London")).strftime("%a %d %b %H:%M") if iso else "not scheduled yet"

def main(out, day=None, videos=True, db=False):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    day = day or dt.datetime.now(ZoneInfo("Europe/London")).date().isoformat()
    by_tag = None
    for n, (b, st) in enumerate(picks(day), 1):
        sid = b["id"]
        if db:
            d = out / "tiktok-db"; d.mkdir(exist_ok=True)
            when = st.get("publish_at")
            (d / f"{sid}.json").write_text(json.dumps({
                "day": day, "order": n, "title": st.get("title") or b["meta"]["title"], "caption": caption(st, b, "tiktok"),
                "post_at": when.replace("Z", "+00:00") if when else None, "video": st.get("video") or "",
                "draft": draft_state(st), "posted": False,
                "added": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, ensure_ascii=False, indent=1))
            print(f"{sid} · {uk(st.get('publish_at'))} · draft {draft_state(st)} · {d / (sid + '.json')}")
            continue
        path = "in your TikTok inbox"
        if videos:
            if by_tag is None:
                rels = json.loads(subprocess.run(["gh", "api", f"repos/{REPO}/releases?per_page=100"], capture_output=True,
                                                 text=True, check=True).stdout)
                by_tag = {r["tag_name"]: r for r in rels}
            rel = by_tag.get(st.get("social_release") or "") or by_tag.get(f"preview-{sid}") or by_tag.get(f"social-{sid}")
            asset = next((a for a in (rel or {}).get("assets", []) if a["name"] == "social.mp4"), None)
            path = "no video found"
            if asset:
                dest = out / f"{sid}-tiktok.mp4"
                with open(dest, "wb") as f:
                    subprocess.run(["gh", "api", "-H", "Accept: application/octet-stream", f"repos/{REPO}/releases/assets/{asset['id']}"],
                                   stdout=f, check=True)
                path = str(dest)
        print(f"=== {sid} · YouTube public {uk(st.get('publish_at'))}\nfile: {path}\ncaption:\n{caption(st, b, 'tiktok')}\n")

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], args[1] if len(args) > 1 else None, videos="--captions-only" not in sys.argv and "--db" not in sys.argv,
         db="--db" in sys.argv)
