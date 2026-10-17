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

def pick_social_music(sb):
    """Same mood as the YouTube track, from the library licensed for every platform (pipeline/music_social). None if empty."""
    cp = P / "music_social" / "catalog.json"
    if not cp.exists(): return None
    cat = [c for c in json.loads(cp.read_text()) if (P / "music_social" / f"{c['slug']}.mp3").exists()]
    if not cat: return None
    mood, category = (sb.get("music") or {}).get("mood"), sb.get("category")
    pool = ([c for c in cat if mood and mood in c.get("moods", [])] or [c for c in cat if category in c.get("categories", [])] or cat)
    rows = []
    for f in (ROOT / "status").glob("*.json"):
        try: st = json.loads(f.read_text())
        except Exception: continue
        if st.get("social_music"): rows.append((st.get("rendered", ""), st["social_music"]))
    recent = [m for _, m in sorted(rows, reverse=True)]
    age = lambda c: recent.index(c["slug"]) if c["slug"] in recent else 10 ** 6
    pool.sort(key=lambda c: (-age(c), hashlib.sha1((sb["id"] + c["slug"]).encode()).hexdigest()))
    sb["social_music"] = {"slug": pool[0]["slug"], "gain_db": (sb.get("music") or {}).get("gain_db", -15)}
    return pool[0]

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
            "", " ".join(hashtags_for(m, "youtube"))]
    return "\n".join(out)

def hashtags_for(meta, platform):
    """YouTube: up to 15 (it shows 3 above the title and ignores every hashtag past 60) plus #Shorts.
    Instagram allows 5 per Reel. TikTok: 7 plus #fyp. The board lists them most relevant first."""
    tags, seen = [], set()
    for h in meta.get("hashtags") or []:
        k = h.lower()
        if k in seen or k == "#shorts": continue
        seen.add(k); tags.append(h)
    if platform == "youtube": return tags[:15] + ["#Shorts"]
    if platform == "instagram": return tags[:5]
    return tags[:7] + ["#fyp"]

def youtube_tags(meta):
    """Keyword tags for YouTube's tags field: hashtags without # first, then meta.tags, within YouTube's 500 characters."""
    out, seen, used = [], set(), 0
    for t in [h.lstrip("#") for h in hashtags_for(meta, "youtube")] + list(meta.get("tags") or []):
        t = str(t).strip(); k = t.lower()
        if not t or k in seen: continue
        cost = len(t) + (2 if " " in t else 0) + (1 if out else 0)
        if used + cost > 480: break
        seen.add(k); out.append(t); used += cost
    return out

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
        planned_real = sum(1 for bt in sb["beats"] for sh in bt.get("shots") or [] if not str(sh.get("src", "")).startswith("pixabay:"))
        sb = fetch_media.resolve(sb)
        real = sum(1 for bt in sb["beats"] for sh in bt.get("shots") or []
                   if "pixabay" not in (str(sh.get("source", "")) + str(sh.get("credit", ""))).lower())
        flags = list(job.get("hold") or [])
        if job["mode"] != "none" and json.loads((ROOT / "config.json").read_text()).get("approval", "flagged") != "none":
            if real == 0: flags.append("render: no real images of the subject (all stock footage)"
                                       + (f"; {planned_real} planned real shots could not be fetched" if planned_real else ""))
        status["media"] = {"real_shots": real, "planned_real": planned_real}
        track = pick_music(sb); status["music"] = track["slug"]
        social = pick_social_music(sb)
        if social: status["social_music"] = social["slug"]
        # the look (caption style, voice and pace, camera energy, colour grade): chosen by plan.py, see templates/looks.json
        import looks as LK
        look = LK.resolve(job.get("look") or sb.get("look"))
        sb.update(look=look["ids"], look_render=look["render"], group=look["render"]["group"])
        status["look"] = dict(look["ids"])
        voice = sb.get("voice", "F2") if sb.get("voice_fixed") else look["voice"]["voice"]
        sb.update(voice_engine="chatterbox", voice_dir=f"voice/{sid}", voice_tag="cb")
        resolved = P / "out" / f"{sid}.resolved.json"; resolved.parent.mkdir(exist_ok=True)
        resolved.write_text(json.dumps(sb, indent=1, ensure_ascii=False))
        for v in [voice] + (["F2"] if voice != "F2" else []):      # an unclear read in a new voice falls back to the house voice
            sh(PY, "tts_cb.py", resolved, P / "voice" / sid, "--voice", v, "--target-wps", str(look["voice"]["wps"]))
            man = json.loads((P / "voice" / sid / "cb_manifest.json").read_text())
            weak = [b["beat"] for b in man["beats"] if b["recall"] < 0.4 and len(sb["beats"][b["beat"]]["say"].split()) >= 4]
            if not weak or v == "F2": break
            print(f"voice {v}: unclear in beats {weak}, retrying with F2", flush=True)
            status["look"]["voice"] = "george"; status["look_note"] = f"voice {v} was unclear, used george"
        sh(PY, "render3.py", resolved, P / "out")
        mp4 = P / "out" / f"{sid}.mp4"
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                                   capture_output=True, text=True, check=True).stdout)
        status["qa"] = {"duration": round(dur, 1), "wps": man["wps"], "weak_beats": weak, "size_mb": round(mp4.stat().st_size / 1e6, 1)}
        try:       # when each beat starts and what's on screen, so analytics can map where viewers leave
            tl = json.loads((P / "out" / f"{sid}.timeline.json").read_text())
            status["timeline"] = [[round(b["start"], 2), round(b["end"], 2), (b.get("visual") or {}).get("type", "none"),
                                   sum(1 for s in tl.get("shots", []) if b["start"] - 0.01 <= s["t0"] < b["end"])] for b in tl["beats"]]
        except Exception as e: print("timeline not recorded:", e)
        contact_sheet(mp4, P / "out" / f"{sid}.timeline.json", res / "review.jpg")
        problems = []
        if not 12 <= dur <= 75: problems.append(f"length {dur:.0f}s")
        if weak: problems.append(f"unclear narration in beats {weak}")
        if problems: raise RuntimeError("checks failed: " + "; ".join(problems))
        credits = json.loads((P / "out" / f"{sid}.credits.json").read_text())
        meta = sb.get("meta", {})
        (res / "upload.json").write_text(json.dumps({
            "title": meta["title"], "description": description(sb, credits, track),
            "tags": youtube_tags(meta),
            "category": sb.get("category", "Entertainment"), "slot": job.get("slot", ""), "mode": job["mode"], "flags": flags},
            indent=1, ensure_ascii=False))
        mp4.replace(res / "video.mp4")
        smp4 = P / "out" / f"{sid}.social.mp4"
        if smp4.exists(): smp4.replace(res / "social.mp4")
        status["state"] = "rendered"
        if flags: status["flags"] = flags
    except Exception as e:
        status["state"] = "failed"; status["error"] = f"{type(e).__name__}: {e}"[:600]
        traceback.print_exc()
    (res / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(json.dumps(status, indent=1))

if __name__ == "__main__":
    main()
