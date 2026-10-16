"""Render one Short on a GitHub runner: media, voice, video, checks. No upload here.

usage: python run_board.py boards/queue/<id>.json --slot <ISO UTC or ''> --mode schedule|private|none|reject
       (on GitHub the job comes in the JOB_JSON environment variable instead, so no board text ever reaches a shell)
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

def recent_tracks():
    """Music slugs of the most recent Shorts, newest first, so the same track isn't used twice in a row."""
    rows = []
    for f in (ROOT / "status").glob("*.json"):
        try: st = json.loads(f.read_text())
        except Exception: continue
        if st.get("music"): rows.append((st.get("rendered", ""), st["music"]))
    return [m for _, m in sorted(rows, reverse=True)]

def pick_music(sb):
    """A board names a track ("slug") or a mood from config.json; otherwise the category decides.
    Within the pool, the track used longest ago wins."""
    cat = json.loads((P / "music" / "catalog.json").read_text())
    by = {c["slug"]: c for c in cat}
    m = sb.setdefault("music", {})
    if m.get("slug") not in by:
        mood, category = m.get("mood"), sb.get("category")
        pool = ([c for c in cat if mood and mood in c.get("moods", [])]
                or [c for c in cat if category in c.get("categories", [])] or cat)
        recent = recent_tracks()
        age = lambda c: recent.index(c["slug"]) if c["slug"] in recent else 10 ** 6
        pool.sort(key=lambda c: (-age(c), hashlib.sha1((sb["id"] + c["slug"]).encode()).hexdigest()))
        m["slug"] = pool[0]["slug"]
    m.setdefault("gain_db", -15)
    return by[m["slug"]]

def description(sb, credits, track):
    m = sb.get("meta", {})
    out = [m.get("summary", "").strip(), "", "Sources:"] + [f"{t}: {u}" for t, u in m.get("sources", [])]
    seen, vis = set(), []
    for c in credits:
        cr, src = c.get("credit", ""), c.get("source", "")
        if not cr or cr.startswith("Music:") or (cr, src) in seen: continue
        seen.add((cr, src)); vis.append(f"{cr} ({src})" if src else cr)
    if vis: out += ["", "Visuals:"] + vis
    out += ["", f"Music: {track['title']} by {track['artist']} ({track.get('source', 'YouTube Audio Library')})", "",
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
    ap.add_argument("board", nargs="?"); ap.add_argument("--slot", default=""); ap.add_argument("--mode", default="none")
    a = ap.parse_args()
    job = json.loads(os.environ["JOB_JSON"]) if os.environ.get("JOB_JSON") else {"board": a.board, "slot": a.slot, "mode": a.mode}
    board_path = ROOT / job["board"]
    if not board_path.resolve().is_relative_to((ROOT / "boards").resolve()): sys.exit("board must be under boards/")
    sid = job.get("id") or board_path.stem
    res = ROOT / "result" / sid; res.mkdir(parents=True, exist_ok=True)
    status = {"id": sid, "board": job["board"], "mode": job["mode"], "slot": job.get("slot", ""),
              "rendered": dt.datetime.now(dt.timezone.utc).isoformat()}
    if job["mode"] == "reject":
        status.update(state="failed (board rejected)", error=job.get("errors", "failed validation"))
        (res / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False)); print(json.dumps(status, indent=1))
        return
    sb = json.loads(board_path.read_text()); sid = sb["id"]
    status["title"] = sb.get("meta", {}).get("title")
    try:
        import fetch_media
        sb = fetch_media.resolve(sb)
        track = pick_music(sb); status["music"] = track["slug"]
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
            "category": sb.get("category", "Entertainment"), "slot": job.get("slot", ""), "mode": job["mode"]},
            indent=1, ensure_ascii=False))
        mp4.replace(res / "video.mp4")
        status["state"] = "rendered"
    except Exception as e:
        status["state"] = "failed"; status["error"] = f"{type(e).__name__}: {e}"[:600]
        traceback.print_exc()
    (res / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(json.dumps(status, indent=1))

if __name__ == "__main__":
    main()
