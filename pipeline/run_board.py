"""Render one Short on a GitHub runner: media, voice, video, checks. No upload here.

usage: python run_board.py boards/queue/<id>.json --slot <ISO UTC or ''> --mode schedule|private|none
Leaves in result/<id>/: the MP4, upload.json (title, description, tags, slot) and status.json, plus review.jpg.
This job never sees the YouTube keys: uploading happens in a separate job with a much smaller set of code.
"""
import argparse, datetime as dt, hashlib, json, os, pathlib, subprocess, sys, traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = ROOT / "pipeline"
sys.path.insert(0, str(P))
PY = sys.executable

def sh(*cmd, cwd=P):
    print("$", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd)

def pick_music(sb):
    cat = json.loads((P / "music" / "catalog.json").read_text())
    slugs = [c["slug"] for c in cat]
    m = sb.setdefault("music", {})
    if m.get("slug") not in slugs:
        m["slug"] = slugs[int(hashlib.sha1(sb["id"].encode()).hexdigest(), 16) % len(slugs)]
    m.setdefault("gain_db", -15)
    return next(c for c in cat if c["slug"] == m["slug"])

def description(sb, credits, track):
    m = sb.get("meta", {})
    out = [m.get("summary", "").strip(), "", "Sources:"] + [f"{t}: {u}" for t, u in m.get("sources", [])]
    seen, vis = set(), []
    for c in credits:
        cr, src = c.get("credit", ""), c.get("source", "")
        if not cr or cr.startswith("Music:") or (cr, src) in seen: continue
        seen.add((cr, src)); vis.append(f"{cr} ({src})" if src else cr)
    if vis: out += ["", "Visuals:"] + vis
    out += ["", f"Music: {track['title']} by {track['artist']} (YouTube Audio Library)", "",
            "Independent channel, not affiliated with the companies or people featured. Facts checked against the sources above.",
            "", " ".join(m.get("hashtags") or ["#Shorts"])]
    return "\n".join(out)

def contact_sheet(mp4, timeline, dest):
    from PIL import Image
    shots = json.loads(timeline.read_text()).get("shots", [])
    tiles = []
    for i, s in enumerate(shots):
        f = dest.with_suffix(f".{i}.jpg")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{(s['t0'] + s['t1']) / 2:.2f}", "-i", str(mp4),
                        "-frames:v", "1", "-vf", "scale=108:192", str(f)], check=True)
        tiles.append(Image.open(f).copy()); f.unlink()
    cols = 10; rows = max(1, (len(tiles) + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * 108, rows * 192), (16, 16, 16))
    for i, t in enumerate(tiles): sheet.paste(t, ((i % cols) * 108, (i // cols) * 192))
    sheet.save(dest, quality=70)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board"); ap.add_argument("--slot", default=""); ap.add_argument("--mode", default="none")
    a = ap.parse_args()
    sb = json.loads((ROOT / a.board).read_text()); sid = sb["id"]
    res = ROOT / "result" / sid; res.mkdir(parents=True, exist_ok=True)
    status = {"id": sid, "board": a.board, "title": sb.get("meta", {}).get("title"), "mode": a.mode, "slot": a.slot,
              "rendered": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        import fetch_media
        sb = fetch_media.resolve(sb)
        track = pick_music(sb)
        sb.update(voice_engine="chatterbox", voice_dir=f"voice/{sid}", voice_tag="cb")
        resolved = P / "out" / f"{sid}.resolved.json"; resolved.parent.mkdir(exist_ok=True)
        resolved.write_text(json.dumps(sb, indent=1, ensure_ascii=False))
        sh(PY, "tts_cb.py", resolved, P / "voice" / sid, "--voice", sb.get("voice", os.environ.get("QP_VOICE", "F2")))
        sh(PY, "render3.py", resolved, P / "out")
        mp4 = P / "out" / f"{sid}.mp4"
        man = json.loads((P / "voice" / sid / "cb_manifest.json").read_text())
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                                   capture_output=True, text=True, check=True).stdout)
        weak = [b["beat"] for b in man["beats"] if b["recall"] < 0.4 and len(sb["beats"][b["beat"]]["say"].split()) >= 4]
        status["qa"] = {"duration": round(dur, 1), "wps": man["wps"], "weak_beats": weak, "size_mb": round(mp4.stat().st_size / 1e6, 1)}
        contact_sheet(mp4, P / "out" / f"{sid}.timeline.json", res / "review.jpg")
        problems = []
        if not 12 <= dur <= 75: problems.append(f"length {dur:.0f}s")
        if weak: problems.append(f"unclear narration in beats {weak}")
        if problems: raise RuntimeError("checks failed: " + "; ".join(problems))
        credits = json.loads((P / "out" / f"{sid}.credits.json").read_text())
        meta = sb.get("meta", {})
        (res / "upload.json").write_text(json.dumps({
            "title": meta["title"], "description": description(sb, credits, track),
            "tags": [h.lstrip("#") for h in meta.get("hashtags", [])] + meta.get("tags", []),
            "category": sb.get("category", "Entertainment"), "slot": a.slot, "mode": a.mode}, indent=1, ensure_ascii=False))
        mp4.replace(res / "video.mp4")
        status["state"] = "rendered"
    except Exception as e:
        status["state"] = "failed"; status["error"] = f"{type(e).__name__}: {e}"[:600]
        traceback.print_exc()
    (res / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(json.dumps(status, indent=1))

if __name__ == "__main__":
    main()
