"""Render a v3 ("polished") Quickplay Daily Short: fast cuts, Ken Burns stills, trailer clips,
whip / zoom / flash transitions, a real music track cut to the beat, and synthesised SFX.

usage: python3 -I render3.py <storyboard.json> <out_dir>

Storyboard additions over v2:
  "music": {"slug": "ten", "start": <sec, optional>, "gain_db": -16}
  beat["shots"]: [{"src", "w", "start" (video in-point), "focus": [x, y], "move": in|out|left|right|up|down|still,
                   "label": {"t", "s"}, "credit", "tin": cut|whip|zoom|flash}]
  beat["impact"]: true  -> boom + punch-in at the beat start
  beat["riser"]: true   -> riser leading into the beat
"""
import asyncio, json, math, os, subprocess, sys, pathlib, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import numpy as np
import soundfile as sf
import render as R  # v2 renderer: TTS, timeline, captions, capture loop

SR, FPS = R.SR, R.FPS
GRAPHIC = {"title", "stat", "cards", "quote", "date", "versus", "timeline", "bars", "cta"}

# ---------------- sound design (synthesised, so every effect is ours) ----------------
def _env(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-3)) * np.exp(-np.maximum(0, t - a) / max(d, 1e-3))

def sfx_whoosh(seed, dur=0.42):
    rng = np.random.default_rng(seed); n = int(dur * SR); t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    lo, mid, hi = R.bp(nz, 250, 900), R.bp(nz, 900, 3000), R.bp(nz, 3000, 9000)
    x = t / t[-1]
    mix = lo * (1 - x) ** 1.5 + mid * np.sin(np.pi * x) + hi * x ** 2 * 0.6
    env = np.sin(np.pi * np.clip(x, 0, 1)) ** 1.6
    return (mix * env * 0.16).astype(np.float32)

def sfx_impact(seed, dur=1.1, strength=1.0):
    rng = np.random.default_rng(seed); n = int(dur * SR); t = np.arange(n) / SR
    f = 34 + 46 * np.exp(-t * 9)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.4)
    crack = R.lp(rng.standard_normal(n), 2600) * np.exp(-t * 40)
    tail = R.bp(rng.standard_normal(n), 150, 900) * np.exp(-t * 6) * 0.25
    return ((sub * 0.55 + crack * 0.35 + tail) * strength * 0.5).astype(np.float32)

def sfx_riser(seed, dur=1.6):
    rng = np.random.default_rng(seed); n = int(dur * SR); t = np.arange(n) / SR; x = t / t[-1]
    nz = rng.standard_normal(n)
    noise = R.hp(nz, 1200) * x ** 2.2 * 0.5 + R.bp(nz, 400, 1600) * x * 0.3
    f = 220 * 2 ** (x * 2.6)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * x ** 2 * 0.22
    return ((noise + tone) * 0.22).astype(np.float32)

def sfx_tick(seed):
    rng = np.random.default_rng(seed); n = int(0.05 * SR); t = np.arange(n) / SR
    return (R.bp(rng.standard_normal(n), 1800, 6000) * np.exp(-t * 120) * 0.22).astype(np.float32)

def load_music(slug, start, dur):
    cat = {c["slug"]: c for c in json.loads((HERE / "music" / "catalog.json").read_text())}
    c = cat[slug]; st = c["start"] if start is None else start
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{st:.3f}", "-t", f"{dur + 1:.3f}", "-i", str(HERE / "music" / f"{slug}.mp3"),
                          "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    m = np.frombuffer(raw, np.float32).copy()
    beats = [b - st for b in c["beats"] if st <= b <= st + dur + 1]
    return m, beats, c

def mix_audio3(segs, duration, music, events, path, gain_db=-16):
    n = int(duration * SR) + SR
    voice = np.zeros(n, np.float32)
    for t0, a in segs:
        s = int(t0 * SR); voice[s:s + len(a)] += a[:max(0, n - s)]
    m = np.zeros(n, np.float32); m[:min(n, len(music))] = music[:n]
    fi, fo = int(0.25 * SR), int(1.4 * SR); end = int(duration * SR)
    m[:fi] *= np.linspace(0, 1, fi); m[end - fo:end] *= np.linspace(1, 0, fo); m[end:] = 0
    env = np.abs(voice); k = int(0.1 * SR); env = np.convolve(env, np.ones(k) / k, mode="same")
    duck = 1 - 0.5 * np.clip(env / 0.025, 0, 1)
    vr = np.sqrt(np.mean(voice[voice != 0] ** 2)) if np.any(voice) else 0.05
    mr = np.sqrt(np.mean(m[:end] ** 2)) or 1
    m = m / mr * vr * 10 ** (gain_db / 20)
    fx = np.zeros(n, np.float32)
    for t, a in events:
        s = max(0, int(t * SR)); fx[s:s + len(a)] += a[:max(0, n - s)]
    mixed = (voice + m * duck + fx)[:end]
    mixed = mixed / (np.max(np.abs(mixed)) or 1) * 0.89
    sf.write(path, np.stack([mixed, mixed], axis=1), SR, subtype="PCM_16")

# ---------------- shots ----------------
def _luma(img):
    g = np.asarray(img.convert("L").resize((54, 96)), np.float32) / 255
    return float(g[25:75, 5:49].mean())

def scene_fit(src, start, vis, slow):
    """Keep a clip inside one scene of its source (cut list in <stem>.cuts.json): move the in-point, or slow it a little."""
    cf = src.with_suffix(".cuts.json")
    if not cf.exists(): return start, slow, ""
    dur = R._probe(src)[2]
    edges = [0.0] + sorted(json.loads(cf.read_text())) + [dur]
    a = max(e for e in edges if e <= start + 0.02); b = min(e for e in edges if e > start + 0.02)
    a2, b2 = a + 0.04, b - 0.05
    st = max(start, a2)
    if st + vis / slow > b2:
        st = max(a2, b2 - vis / slow)
        if st + vis / slow > b2:
            slow, st = min(1.5, vis / max(0.2, b2 - a2)), a2
    note = "" if st + vis / slow <= b2 + 0.01 else f"still crosses the cut at {b:.2f}s"
    return round(st, 3), round(slow, 3), note

def prepare_shots(sb, beats, words, duration, mbeats, sid, out_dir):
    from PIL import Image
    work = out_dir / f"{sid}_shots"; work.mkdir(parents=True, exist_ok=True)
    items, credits, punches, k, dirn = [], [], [], 0, 1
    for bi, (beat, b) in enumerate(zip(sb["beats"], beats)):
        shots = beat.get("shots") or []
        if not shots: continue
        start = 0.0 if bi == 0 else b["start"]; end = b["end"]
        ws = [s.get("w", 1.0) for s in shots]; n = len(shots)
        bw = [w for w in words if w["beat"] == bi]
        fixed = {0: start, n: end}
        for j, s in enumerate(shots):                                      # "at": cut to this shot on a spoken word
            if j and s.get("at") is not None and bw:
                fixed[j] = min(end - 0.3, max(start + 0.4, bw[min(int(s["at"]), len(bw) - 1)]["start"] - 0.06))
        keys = sorted(fixed); cuts = [start]
        for p, q in zip(keys, keys[1:]):
            tot = sum(ws[p:q])
            for j in range(p + 1, q):
                c = cuts[-1] + (fixed[q] - fixed[p]) * ws[j - 1] / tot
                near = [mb for mb in mbeats if abs(mb - c) <= 0.16]      # land cuts on the music's beat
                if near: c = min(near, key=lambda mb: abs(mb - c))
                cuts.append(max(cuts[-1] + 0.5, c))
            if q < n: cuts.append(max(cuts[-1] + 0.35, fixed[q]))
        cuts.append(end)
        has_graphic = beat["visual"].get("type") in GRAPHIC
        if beat.get("impact"): punches.append(round(start + 0.02, 3))
        for j, shot in enumerate(shots):
            t0, t1 = cuts[j], cuts[j + 1]
            src = (HERE / shot["src"]).resolve()
            if not src.exists():
                print(f"  warning: missing {src}", file=sys.stderr); continue
            fx, fy = (shot.get("focus") or [0.5, 0.45])[:2]
            move = shot.get("move", "in")
            tin = shot.get("tin") or ("cut" if j else ("zoom" if bi == 0 else "whip"))
            if tin == "whip": dirn = -dirn
            d = work / f"s{k:02d}"; d.mkdir(exist_ok=True); k += 1
            it = {"t0": round(t0, 3), "t1": round(t1, 3), "tin": tin, "dir": dirn, "credit": shot.get("credit", sb.get("credit", "")),
                  "src": pathlib.Path(shot["src"]).stem}
            if src.suffix.lower() in R.VIDEO_EXT:
                w, h, dur = R._probe(src)
                zoom = shot.get("zoom", 1.08); H2 = int(1920 * zoom) // 2 * 2; W2 = int(round(w * H2 / h)) // 2 * 2
                x = int(min(max(0, fx * W2 - 540), W2 - 1080)); y = int((H2 - 1920) * fy)
                need = (t1 - t0) + 0.4
                st, slow, note = scene_fit(src, float(shot.get("start", 0)), (t1 - t0) + 0.12, float(shot.get("slow") or 1.0))
                if note: print(f"  warning: {sid} shot {k - 1} ({shot['src']} @{st}) {note}", file=sys.stderr)
                vf = f"scale={W2}:{H2},crop=1080:1920:{x}:{y},fps={FPS}"
                if slow > 1.001: vf = f"setpts={slow}*PTS," + vf
                if shot.get("eq"): vf += f",eq={shot['eq']}"                 # lift dark footage, e.g. "gamma=1.5:contrast=1.08"
                fr = d / "frames"; fr.mkdir(exist_ok=True)
                for old in fr.glob("*.jpg"): old.unlink()
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{st:.3f}", "-i", str(src), "-t", f"{need:.3f}",
                                "-vf", vf, "-q:v", "3", str(fr / "%05d.jpg")], check=True)
                it["vsrc"] = [st, slow]
                frames = sorted(fr.glob("*.jpg"))
                it.update(kind="video", fill=os.path.relpath(frames[0], HERE), frames=os.path.relpath(fr, HERE), count=len(frames), fps=FPS,
                          s0=1.0, s1=1.0 + (0.05 if move != "still" else 0.0))
                lum = _luma(Image.open(frames[min(len(frames) - 1, len(frames) // 2)]))
            else:
                img = Image.open(src).convert("RGB"); w, h = img.size
                m = 1.14 if move in ("left", "right", "up", "down") else 1.04
                sc = max(1080 * m / w, 1920 * m / h); W, H = int(round(w * sc)), int(round(h * sc))
                img.resize((W, H), Image.LANCZOS).save(d / "img.jpg", quality=88)
                cx, cy = fx * W, fy * H
                def clampc(cx, cy, s):
                    return min(max(cx, 540 / s + 2), W - 540 / s - 2), min(max(cy, 960 / s + 2), H - 960 / s - 2)
                if move == "out": s0, s1 = 1.12, 1.0
                elif move == "still": s0 = s1 = 1.02
                elif move in ("left", "right", "up", "down"): s0 = s1 = 1.02
                else: s0, s1 = 1.0, 1.11
                dx = min(170, (W - 1080 / s0) / 2 - 4); dy = min(150, (H - 1920 / s0) / 2 - 4)
                c0, c1 = (cx, cy), (cx, cy)
                if move == "left": c0, c1 = (cx + dx, cy), (cx - dx, cy)
                if move == "right": c0, c1 = (cx - dx, cy), (cx + dx, cy)
                if move == "up": c0, c1 = (cx, cy + dy), (cx, cy - dy)
                if move == "down": c0, c1 = (cx, cy - dy), (cx, cy + dy)
                (cx0, cy0), (cx1, cy1) = clampc(*c0, s0), clampc(*c1, s1)
                it.update(kind="image", fill=os.path.relpath(d / "img.jpg", HERE), W=W, H=H, s0=s0, s1=s1,
                          cx0=round(cx0, 1), cy0=round(cy0, 1), cx1=round(cx1, 1), cy1=round(cy1, 1))
                lum = _luma(img.crop((int(cx0 - 540 / s0), int(cy0 - 960 / s0), int(cx0 + 540 / s0), int(cy0 + 960 / s0))))
            # legibility: darken more behind graphics, and more on bright footage
            it["dim"] = round(min(0.72, max(0.30, 0.34 + (lum - 0.35) * 0.9)), 2) if has_graphic else round(min(0.3, max(0.06, (lum - 0.45) * 0.8)), 2)
            if shot.get("label"):
                it["label"] = shot["label"]; it["labelTop"] = shot.get("labelTop", 1020)
            items.append(it)
            if it["credit"]:
                credits.append({"credit": it["credit"], "source": shot.get("source", sb.get("source", "")), "license": shot.get("license", "")})
    return items, credits, punches

def sfx_events(sb, beats, items):
    ev = []
    for i, it in enumerate(items):
        if it["tin"] == "whip" and it["t0"] > 0.1: ev.append((it["t0"] - 0.17, sfx_whoosh(i)))
        elif it["tin"] == "zoom" and it["t0"] > 0.1: ev.append((it["t0"] - 0.12, sfx_whoosh(100 + i, 0.3) * 0.7))
        elif it["tin"] == "flash": ev.append((it["t0"], sfx_impact(200 + i, 0.6, 0.45)))
    for bi, (beat, b) in enumerate(zip(sb["beats"], beats)):
        st = 0.0 if bi == 0 else b["start"]
        if beat.get("impact"): ev.append((max(0, st - 0.01), sfx_impact(300 + bi)))
        if beat.get("riser"): ev.append((max(0, st - 1.6), sfx_riser(400 + bi)))
        v = beat["visual"]
        if v.get("type") in ("cards", "quote", "date", "versus"): ev.append((st + 0.12, sfx_tick(500 + bi)))
    return ev

def main():
    sb_path = pathlib.Path(sys.argv[1]); out_dir = pathlib.Path(sys.argv[2]); out_dir.mkdir(parents=True, exist_ok=True)
    sb = json.loads(sb_path.read_text())
    sid = sb["id"]; t0 = time.time()
    if sb.get("voice_engine") == "chatterbox":       # narration pre-rendered by tts_cb.py (one WAV per beat)
        import voice as V
        segs, words, beats, groups, duration = V.build_timeline_cb(
            sb, HERE / sb.get("voice_dir", f"voice/{sid}"), sb.get("voice_tag", "cb"), sb.get("voice_tempo", 1.0))
    else:
        segs, words, beats, groups, duration = R.build_timeline(sb)
    for bi, (beat, b) in enumerate(zip(sb["beats"], beats)):   # reveal a graphic on a given spoken word
        aw = beat["visual"].get("atWord")
        if aw is not None:
            ws = [w for w in words if w["beat"] == bi]
            rel = round(ws[min(aw, len(ws) - 1)]["start"] - (0.0 if bi == 0 else b["start"]), 2)
            b["visual"] = dict(b["visual"], at=[rel, rel + 0.05, rel + 0.15, rel + 0.2])
    mus = sb.get("music", {})
    music, mbeats, mcat = load_music(mus.get("slug", "ten"), mus.get("start"), duration)
    items, credits, punches = prepare_shots(sb, beats, words, duration, mbeats, sid, out_dir)
    wav = out_dir / f"{sid}.wav"
    mix_audio3(segs, duration, music, sfx_events(sb, beats, items), str(wav), mus.get("gain_db", -16))
    credits.append({"credit": f"Music: {mcat['title']} by {mcat['artist']} (YouTube Audio Library)", "source": "", "license": ""})
    icons = set([sb.get("chipIcon", "trending-up")])
    for b in sb["beats"]:
        for it in b["visual"].get("items", []):
            if isinstance(it, dict) and it.get("icon"): icons.add(it["icon"])
    data = {"accent": sb.get("accent", "#2EE6C5"), "category": sb["category"], "chipIcon": sb.get("chipIcon", "trending-up"),
            "icons": R.icon_svgs(icons), "beats": beats, "words": words, "groups": groups, "duration": duration,
            "media": items, "punches": punches}
    (out_dir / f"{sid}.credits.json").write_text(json.dumps(credits, indent=1, ensure_ascii=False))
    (out_dir / f"{sid}.timeline.json").write_text(json.dumps({"beats": beats, "words": words, "groups": groups, "duration": duration,
                                                              "shots": [{k: v for k, v in it.items() if k in ('t0', 't1', 'tin', 'kind', 'fill', 'dim', 'src', 'vsrc')} for it in items]}, indent=1))
    silent = out_dir / f"{sid}.video.mp4"
    vmax = int(min(8_000_000, 0.95 * (9.4e6 * 8 / duration - 128_000)) / 1000)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(sb.get("crf", 21)), "-maxrate", f"{vmax}k", "-bufsize", f"{2 * vmax}k",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-r", str(FPS), str(silent)]
    asyncio.run(R.capture(HERE / "template3.html", data, duration, cmd, out_dir / f"{sid}.poster.jpg", sb.get("posterT", 0.6)))
    final = out_dir / f"{sid}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav),
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                    "-movflags", "+faststart", "-shortest", str(final)], check=True)
    silent.unlink(missing_ok=True)
    print(json.dumps({"id": sid, "duration": round(duration, 2), "size_mb": round(final.stat().st_size / 1e6, 2),
                      "shots": len(items), "secs": round(time.time() - t0, 1), "file": str(final)}))

if __name__ == "__main__":
    main()
