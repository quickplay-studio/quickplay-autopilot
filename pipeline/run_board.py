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

def halves(text):
    """A beat's line split in two near the middle, at a comma or clause word when there is one, else at a word boundary:
    Chatterbox garbles a long sentence far more often than two short ones (24 October: 5 of the 6 boards ever lost were
    lost to one unclear beat). ("", "") when the line is too short to split."""
    words = str(text or "").split()
    if len(words) < 8: return "", ""
    mid, lo, hi = len(words) / 2, max(3, int(len(words) * 0.25)), min(len(words) - 3, int(len(words) * 0.75))
    joins = ("and", "but", "so", "because", "which", "while", "when", "after", "before", "then", "in", "on", "to",
             "with", "for", "from", "as", "at", "by")
    best = None
    for i in range(lo, hi + 1):                     # cut after a comma, else before a joining word; never mid-phrase
        prev, nxt = words[i - 1], words[i].lower().strip(",.")
        if prev.endswith(","): score = abs(i - mid)
        elif nxt in joins: score = abs(i - mid) + 1
        else: continue
        if best is None or score < best[0]: best = (score, i)
    if best is None: return "", ""                  # no natural place to cut: left as it is
    a, b = " ".join(words[:best[1]]), " ".join(words[best[1]:])
    a = a.rstrip(",;: ") + ("" if a.rstrip()[-1:] in ".?!" else ".")
    return a, b[0].upper() + b[1:] if b else ""


def split_read(sb, bi, vdir, voice, wps, out_root, was):
    """Reads one stubborn beat as two short sentences and joins them with a short pause. The two halves are each checked by
    the same ear proxy as any beat (their own cb_manifest), so nothing is measured twice; when the worse half beats `was`
    (the recall of the read we have) and is clear enough, the joined audio replaces cb_b<bi>.wav in `vdir` and
    (recall, seconds) comes back. None when it is no better, and the beat keeps the audio it had."""
    import shutil
    a, b = halves(sb["beats"][bi].get("say_cb") or sb["beats"][bi]["say"])
    if not a or not b: print(f"beat {bi}: no natural place to split", flush=True); return None
    d = out_root / f"{vdir}-split{bi}"
    two = d / "two.json"; d.mkdir(parents=True, exist_ok=True)
    two.write_text(json.dumps({"id": sb["id"], "beats": [{"say": a}, {"say": b}]}))
    sh(PY, "tts_cb.py", two, d, "--voice", voice, "--target-wps", str(wps))
    w0, w1 = d / "cb_b00.wav", d / "cb_b01.wav"
    if not (w0.exists() and w1.exists()): return None
    halves_recall = [x.get("recall", 0) for x in json.loads((d / "cb_manifest.json").read_text()).get("beats") or []]
    recall = min(halves_recall) if len(halves_recall) == 2 else 0
    print(f"beat {bi}: as two sentences, {', '.join(f'{r:.0%}' for r in halves_recall)} of words heard (was {was:.0%})", flush=True)
    if recall < 0.5 or recall <= was: return None
    joined = d / "joined.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(w0), "-i", str(w1), "-filter_complex",
                    "[0:a]apad=pad_dur=0.12[a0];[a0][1:a]concat=n=2:v=0:a=1[a]", "-map", "[a]", str(joined)], check=True)
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(joined)],
                                capture_output=True, text=True, check=True).stdout or 0)
    shutil.copy(joined, out_root / vdir / f"cb_b{bi:02d}.wav")
    return recall, round(secs, 3)


def recent_tracks():
    """Music slugs of the most recent Shorts, newest first, so the same track isn't used twice in a row."""
    rows = []
    for f in (ROOT / "status").glob("*.json"):
        try: st = json.loads(f.read_text())
        except Exception: continue
        if isinstance(st, dict) and st.get("music"): rows.append((st.get("rendered", ""), st["music"]))
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
        if isinstance(st, dict) and st.get("social_music"): rows.append((st.get("rendered", ""), st["social_music"]))
    recent = [m for _, m in sorted(rows, reverse=True)]
    age = lambda c: recent.index(c["slug"]) if c["slug"] in recent else 10 ** 6
    pool.sort(key=lambda c: (-age(c), hashlib.sha1((sb["id"] + c["slug"]).encode()).hexdigest()))
    sb["social_music"] = {"slug": pool[0]["slug"], "gain_db": (sb.get("music") or {}).get("gain_db", -15)}
    return pool[0]

def localize(meta, desc):
    """YouTube localisations from the writer's translations: the translated title, and the translated summary above the
    English description."""
    out = {}
    for lang, t in ((meta or {}).get("translations") or {}).items():
        if isinstance(t, dict) and t.get("title"):
            out[lang] = {"title": str(t["title"])[:100], "description": (str(t.get("summary") or "") + "\n\n" + desc)[:4900]}
    return out


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

CATEGORY_LOOK = {"Gaming": ("#8B5CF6", "gamepad-2"), "Film": ("#EF4444", "clapperboard"), "Music": ("#C084FC", "music"),
                 "Sport": ("#FFB23F", "trophy"), "Tech": ("#34D399", "cpu"), "Science": ("#7DD3FC", "atom"),
                 "Entertainment": ("#F59E0B", "tv")}

def fill_defaults(sb):
    """The routine fields a writer may leave out (CLAUDE.md, Board schema): beat gap and tail, music level, and a colour
    and icon for the category. Anything the board sets wins."""
    accent, icon = CATEGORY_LOOK.get(sb.get("category"), ("#2EE6C5", "trending-up"))
    sb.setdefault("gap", 0.1); sb.setdefault("tail", 0.6); sb.setdefault("accent", accent); sb.setdefault("chipIcon", icon)
    (sb.setdefault("music", {})).setdefault("gain_db", -15)
    return sb

def contact_sheet(mp4, timeline, dest, big=False):
    """One frame from the middle of every shot. A test board (big) gets larger tiles, then a second block with a frame
    every 3 seconds, so the video behind the shots can be judged as it changes."""
    from PIL import Image
    tl = json.loads(timeline.read_text())
    tw, th, cols = (216, 384, 6) if big else (108, 192, 10)
    times = [(s["t0"] + s["t1"]) / 2 for s in tl.get("shots", [])]
    blocks = [times]
    if big: blocks.append([x for x in (1.5 + 3.0 * k for k in range(40)) if x < tl.get("duration", 0) - 0.2])
    rows = sum(max(0, (len(b) + cols - 1) // cols) for b in blocks) or 1
    sheet, y = Image.new("RGB", (cols * tw, rows * th), (16, 16, 16)), 0
    for block in blocks:
        for i, t in enumerate(block):
            f = dest.with_suffix(f".{i}.jpg")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={tw}:{th}", str(f)], check=True)
            sheet.paste(Image.open(f), ((i % cols) * tw, y + (i // cols) * th)); f.unlink()
        y += ((len(block) + cols - 1) // cols) * th
    sheet.save(dest, quality=75 if big else 70)

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
    if job.get("late"): status["late"] = job["late"]          # freshness.py: how late, and the evidence it went out on (or not)
    if job.get("fx"): status["fx"] = job["fx"]                # the factorial round's arms: assigned, and what plan.py gave them
    if job["mode"] == "reject" and job.get("expired"):          # missed its day and the data says the story has moved on
        status.update(state=f"expired: {job.get('errors', '')}"[:300])
        (res / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False)); print(json.dumps(status, indent=1))
        return
    if job["mode"] == "reject":
        status.update(state="failed (board rejected)", error=job.get("errors", "failed validation"))
        (res / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False)); print(json.dumps(status, indent=1))
        return
    sb = fill_defaults(json.loads(board_path.read_text())); sid = sb["id"]
    status["title"] = sb.get("meta", {}).get("title")
    try:
        import fetch_media, background as BG
        planned_real = sum(1 for bt in sb["beats"] for sh in bt.get("shots") or [] if not str(sh.get("src", "")).startswith(("pixabay:", "gameplay:")))
        sb = fetch_media.resolve(sb)
        # the video behind the Short: clips picked by plan.py (background.py), downloaded here. With none, the Short renders as before.
        cfg = json.loads((ROOT / "config.json").read_text())
        bnotes = []
        if job.get("bg"):
            clips, bnotes = BG.fetch(job["bg"], sid, cfg)
            if clips: sb["bg_clips"], sb["bg_cfg"] = clips, BG.settings(cfg)
        if job.get("bg_notes") or bnotes:       # why a provider was skipped or a clip refused (plan.py's notes, then the downloads')
            status["background_notes"] = (list(job.get("bg_notes") or []) + bnotes)[:24]
        if BG.wanted(sb, cfg) and not sb.get("bg_clips"):
            status["background_note"] = "no background video (no clip found or downloaded): rendered with full-screen pictures"
        real = sum(1 for bt in sb["beats"] for sh in bt.get("shots") or []
                   if not any(w in (str(sh.get("source", "")) + str(sh.get("credit", ""))).lower() for w in ("pixabay", "gameplay")))
        flags = list(job.get("hold") or [])
        notes = sb.pop("_media_notes", [])
        if notes: status["media_notes"] = notes
        if job["mode"] != "none" and json.loads((ROOT / "config.json").read_text()).get("approval", "flagged") != "none":
            if real == 0: flags.append("render: no real images of the subject (all stock footage)"
                                       + (f"; {planned_real} planned real shots could not be fetched" if planned_real else ""))
            flags += [f"render: {n}" for n in notes]
        status["media"] = {"real_shots": real, "planned_real": planned_real}
        track = pick_music(sb); status["music"] = track["slug"]
        social = pick_social_music(sb)
        if social: status["social_music"] = social["slug"]
        # the look (caption style, voice and pace, camera energy, colour grade): chosen by plan.py, see templates/looks.json
        import looks as LK
        look = LK.resolve(job.get("look") or sb.get("look"))
        sb.update(look=look["ids"], look_render=look["render"], group=look["render"]["group"])
        rw, b0 = look["render"].get("reveal_word", 0), (sb["beats"] or [{}])[0]
        if rw and (b0.get("visual") or {}).get("type", "none") != "none" and "atWord" not in b0["visual"]:
            n0 = len((b0.get("say") or "").split())          # image first: the hook's card waits for the fourth word
            if n0 > rw: b0["visual"] = dict(b0["visual"], atWord=rw)
        status["look"] = dict(look["ids"])           # includes the style (minimal or standard): analytics reads look_style from here
        if look["render"].get("pace") == "fast":     # the minimal style cuts to a new picture every 1.2 to 1.8 seconds: more photos of the same subject
            try:
                got = fetch_media.extras(sb)
                if got: status["media"]["extra_photos"] = got
            except Exception as e: print(f"extra photos skipped: {str(e)[:160]}", flush=True)
        try:        # how well the pictures fit their beats (pictures.py): media.pic_* in status, shorts.csv by analytics.py
            status["media"].update(fetch_media.pictures_summary(sb))
            fetch_media.PX.unload()     # the picture model's 1.5 GB is not needed again; the voice model loads next
        except Exception as e: print(f"picture summary skipped: {str(e)[:160]}", flush=True)
        voice = sb.get("voice", "F2") if sb.get("voice_fixed") else look["voice"]["voice"]
        sb.update(voice_engine="chatterbox", voice_tag="cb")
        resolved = P / "out" / f"{sid}.resolved.json"; resolved.parent.mkdir(exist_ok=True)
        tried = []      # an unclear read in a new voice is tried again in the house voice, then the house voice 15% slower
        wps0 = float(look["voice"]["wps"])  # (unclear Shorts were lost outright before 23 October); the clearest read wins
        for k, (v, wps) in enumerate([(voice, wps0)] + ([("F2", wps0)] if voice != "F2" else []) + [("F2", round(wps0 * 0.85, 2))]):
            vdir = f"voice/{sid}-{v}-{k}"
            sb["voice_dir"] = vdir; resolved.write_text(json.dumps(sb, indent=1, ensure_ascii=False))
            sh(PY, "tts_cb.py", resolved, P / vdir, "--voice", v, "--target-wps", str(wps))
            man = json.loads((P / vdir / "cb_manifest.json").read_text())
            low = {b["beat"]: b["recall"] for b in man["beats"] if b["recall"] < 0.4 and len(sb["beats"][b["beat"]]["say"].split()) >= 4}
            weak = sorted(low)
            tried.append((len(weak), -min(low.values(), default=1.0), k, v, vdir, man, weak))
            if not weak: break
            print(f"voice {v} at {wps} words a second: unclear in beats {weak}", flush=True)
        _, worst, _, v, vdir, man, weak = min(tried, key=lambda x: x[:3])
        if weak:                       # still unclear after three reads: each stubborn beat read again as two short sentences
            fixed, mbeats = [], {b["beat"]: b for b in man["beats"]}
            for bi in list(weak):
                try: got = split_read(sb, bi, vdir, v, wps0 * 0.9, P, mbeats[bi]["recall"])
                except Exception as e: print(f"split read of beat {bi} failed: {str(e)[:160]}", flush=True); got = None
                if not got: continue
                mbeats[bi].update(recall=round(got[0], 3), dur=got[1], split=True); fixed.append(bi)
            if fixed:
                weak = [b for b in weak if b not in fixed]
                worst = -min([mbeats[b]["recall"] for b in weak], default=1.0)
                (P / vdir / "cb_manifest.json").write_text(json.dumps(man, indent=1))
                status["voice_note"] = f"beat{'s' if len(fixed) > 1 else ''} {', '.join(map(str, fixed))} read as two sentences"
        if weak and len(weak) == 1 and weak[0] != 0 and -worst >= 0.25:     # one middle beat, mostly heard: the captions carry it
            status["qa_note"] = f"narration a little unclear in beat {weak[0]} (captions carry it)"; weak = []    # a note, not a flag: flags hold a Short for approval
        if v != voice:
            status["look"]["voice"] = "george"; status["look_note"] = f"voice {voice} was less clear, used george"
        sb["voice_dir"] = vdir; resolved.write_text(json.dumps(sb, indent=1, ensure_ascii=False))
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
        try:       # the background clips this Short really used (status/*.json): plan.py never reuses them within reuse_days
            status["background"] = [{k: u.get(k) for k in ("p", "id", "q", "t0", "t1")} for u in json.loads((P / "out" / f"{sid}.bg.json").read_text())]
            if sb.get("bg_clips") and not status["background"]: status["background_note"] = "the background video could not be built: rendered without"
        except Exception as e: print("background not recorded:", e)
        big = sid.startswith("TEST-")      # a test board gets a bigger sheet
        contact_sheet(mp4, P / "out" / f"{sid}.timeline.json", res / "review.jpg", big=big)
        if big and (P / "out" / f"{sid}.social.mp4").exists():      # template tests show both layouts
            contact_sheet(P / "out" / f"{sid}.social.mp4", P / "out" / f"{sid}.timeline.json", res / "review_social.jpg", big=True)
        problems = []
        top = 180 if (sb.get("test") or {}).get("length") == "about 2 min" else 75     # the 2-minute arm (YouTube allows 3)
        if not 12 <= dur <= top: problems.append(f"length {dur:.0f}s")
        if weak: problems.append(f"unclear narration in beats {weak}")
        if problems: raise RuntimeError("checks failed: " + "; ".join(problems))
        credits = json.loads((P / "out" / f"{sid}.credits.json").read_text())
        meta = sb.get("meta", {})
        (res / "upload.json").write_text(json.dumps({
            "title": meta["title"], "description": (desc := description(sb, credits, track)), "localizations": localize(meta, desc),
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
