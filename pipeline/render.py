"""Render a Quickplay Daily Short from a storyboard JSON.

usage: python3 -I render.py <storyboard.json> <out_dir> [--preview]
"""
import asyncio, json, math, os, re, subprocess, sys, pathlib, time
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, resample_poly

HERE = pathlib.Path(__file__).resolve().parent
TTS_DIR = HERE.parent / "tts"
SR = 48000
FPS = 25

_kokoro = None
def kokoro():
    global _kokoro
    if _kokoro is None:
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(TTS_DIR / "kokoro-v1.0.onnx"), str(TTS_DIR / "voices-v1.0.bin"))
    return _kokoro

def trim(x, sr, thr=0.008, pad=0.03):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(pad * sr)); b = min(len(x), idx[-1] + int(pad * sr))
    return x[a:b]

def syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1 if re.search(r"\d", word) else 0.5
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith("le"):
        n -= 1
    return max(1, n)

def word_weight(word):
    digits = re.sub(r"[^0-9]", "", word)
    if digits:
        base = 1.6 * len(digits) if len(digits) <= 2 else 3.2 if len(digits) == 4 else 1.2 * len(digits)
    else:
        base = syllables(word)
    return base + 0.6

def pause_after(word):
    if re.search(r"[.!?]$", word): return 2.2
    if re.search(r"[,;:]$", word): return 1.3
    return 0.0

def split_words(text):
    return [w for w in re.split(r"\s+", text.strip()) if w]

def tts(text, voice, speed):
    k = kokoro()
    samples, sr = k.create(text, voice=voice, speed=speed, lang="en-gb")
    samples = trim(np.asarray(samples, dtype=np.float32), sr)
    out = resample_poly(samples, SR, sr).astype(np.float32)
    return out

# ---------------- music and sfx ----------------
NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
def freq(name, octave):
    midi = 12 * (octave + 1) + NOTE[name]
    return 440.0 * 2 ** ((midi - 69) / 12)

def lp(x, cutoff, order=4):
    sos = butter(order, cutoff, btype="low", fs=SR, output="sos"); return sosfilt(sos, x)
def hp(x, cutoff, order=2):
    sos = butter(order, cutoff, btype="high", fs=SR, output="sos"); return sosfilt(sos, x)
def bp(x, lo, hi, order=2):
    sos = butter(order, [lo, hi], btype="band", fs=SR, output="sos"); return sosfilt(sos, x)

def music_bed(duration, seed=1, bpm=96):
    rng = np.random.default_rng(seed)
    n = int(duration * SR) + SR
    out = np.zeros(n, dtype=np.float64)
    beat = 60.0 / bpm; bar = 4 * beat
    progs = [[("A", "C", "E"), ("F", "A", "C"), ("C", "E", "G"), ("G", "B", "D")],
             [("C", "E", "G"), ("G", "B", "D"), ("A", "C", "E"), ("F", "A", "C")],
             [("F", "A", "C"), ("C", "E", "G"), ("G", "B", "D"), ("A", "C", "E")]]
    prog = progs[seed % len(progs)]
    t_bar = 0.0; k = 0
    while t_bar < duration + bar:
        chord = prog[k % 4]
        a = int(t_bar * SR); L = int(bar * SR); tt = np.arange(L) / SR
        env = np.minimum(1, tt / 0.35) * np.minimum(1, (bar - tt) / 0.5)
        pad = np.zeros(L)
        for j, nm in enumerate(chord):
            f = freq(nm, 4 if j else 3) * (2 if j == 2 else 1)
            for det in (-0.12, 0.12):
                ff = f * 2 ** (det / 12)
                for h in range(1, 6):
                    pad += np.sin(2 * np.pi * ff * h * tt + rng.uniform(0, 6.28)) / (h * 1.6)
        pad = lp(pad, 1400) * env * 0.035
        root = freq(chord[0], 2)
        bass = np.zeros(L)
        for bt in (0, 2):
            s = int(bt * beat * SR); m = int(beat * 1.8 * SR)
            seg = np.arange(min(m, L - s)) / SR
            bass[s:s + len(seg)] += np.sin(2 * np.pi * root * seg) * np.exp(-seg * 2.2) * 0.10
        kick = np.zeros(L)
        for bt in (0, 2):
            s = int(bt * beat * SR); seg = np.arange(int(0.18 * SR)) / SR
            f0 = 110 * np.exp(-seg * 18) + 45
            ph = 2 * np.pi * np.cumsum(f0) / SR
            kick[s:s + len(seg)] += np.sin(ph) * np.exp(-seg * 22) * 0.20
        hats = np.zeros(L)
        for e in range(8):
            if e % 2 == 1:
                s = int(e * beat / 2 * SR); seg = int(0.05 * SR)
                nz = rng.standard_normal(seg) * np.exp(-np.arange(seg) / SR * 70)
                hats[s:s + seg] += nz * 0.018
        hats = hp(hats, 7000)
        blk = pad + bass + kick + hats
        if a >= n:
            break
        end = min(n, a + L); out[a:end] += blk[:end - a]
        t_bar += bar; k += 1
    out = out[:int(duration * SR)]
    fade = int(0.8 * SR)
    out[:fade] *= np.linspace(0, 1, fade); out[-fade:] *= np.linspace(1, 0, fade)
    return out.astype(np.float32)

def whoosh(seed=0):
    rng = np.random.default_rng(seed)
    L = int(0.42 * SR); tt = np.arange(L) / SR
    nz = rng.standard_normal(L)
    lo = bp(nz, 300, 1500); hi = bp(nz, 1500, 6000)
    mix = lo * (1 - tt / tt[-1]) + hi * (tt / tt[-1])
    env = np.sin(np.pi * np.clip(tt / tt[-1], 0, 1)) ** 2
    return (mix * env * 0.10).astype(np.float32)

# ---------------- timeline ----------------
def build_timeline(sb):
    voice = sb.get("voice", "bm_george"); speed = sb.get("speed", 1.08)
    t = 0.06; gap = sb.get("gap", 0.20)
    segs = []; words = []; beats = []
    for bi, beat in enumerate(sb["beats"]):
        say = beat["say"]
        audio = tts(say, voice, speed)
        L = len(audio) / SR
        sw = split_words(say)
        cw = split_words(beat.get("cap", say))
        if len(cw) != len(sw):
            print(f"  warning: caption/speech word count differs in beat {bi}; using speech words", file=sys.stderr)
            cw = sw
        weights = [word_weight(w) for w in sw]
        pauses = [pause_after(w) if j < len(sw) - 1 else 0 for j, w in enumerate(sw)]
        total = sum(weights) + sum(pauses)
        cur = t
        for j, w in enumerate(sw):
            d = L * weights[j] / total
            words.append({"w": w, "cap": re.sub(r"[,;:]$", "", cw[j]), "start": round(cur, 3), "end": round(cur + d, 3), "beat": bi})
            cur += d + L * pauses[j] / total
        segs.append((t, audio))
        beats.append({"start": round(t, 3), "speech_end": round(t + L, 3), "visual": beat["visual"]})
        t += L + (beat.get("gap", gap))
    duration = t + sb.get("tail", 0.55)
    for i, b in enumerate(beats):
        b["end"] = round(beats[i + 1]["start"], 3) if i + 1 < len(beats) else round(duration, 3)
    # caption groups: up to 3 words, break on punctuation, never across beats
    groups = []; cur = []
    for i, w in enumerate(words):
        cur.append(i)
        brk = len(cur) >= sb.get("group", 3) or re.search(r"[.,!?;:]$", w["w"]) or i == len(words) - 1 or words[i + 1]["beat"] != w["beat"]
        if len(" ".join(words[k]["cap"] for k in cur)) > 22 and len(cur) > 1 and not brk:
            brk = True
        if brk:
            groups.append({"words": cur, "start": words[cur[0]]["start"], "end": words[cur[-1]]["end"]}); cur = []
    for g, nxt in zip(groups, groups[1:] + [None]):
        if nxt is not None and words[nxt["words"][0]]["beat"] == words[g["words"][0]]["beat"]:
            g["end"] = nxt["start"]
        else:
            g["end"] = round(g["end"] + 0.15, 3)
    return segs, words, beats, groups, duration

def mix_audio(segs, beats, duration, seed, path):
    n = int(duration * SR) + SR
    voice = np.zeros(n, dtype=np.float32)
    for t0, a in segs:
        s = int(t0 * SR); voice[s:s + len(a)] += a[:max(0, n - s)]
    music = music_bed(duration + 1, seed=seed)
    m = np.zeros(n, dtype=np.float32); m[:len(music)] = music[:n]
    # duck music under speech
    env = np.abs(voice); env = np.convolve(env, np.ones(int(0.12 * SR)) / int(0.12 * SR), mode="same")
    duck = 1 - 0.45 * np.clip(env / 0.03, 0, 1)
    sfx = np.zeros(n, dtype=np.float32)
    for i, b in enumerate(beats[1:], start=1):
        w = whoosh(seed + i); s = max(0, int((b["start"] - 0.18) * SR)); sfx[s:s + len(w)] += w[:max(0, n - s)]
    mixed = voice * 1.0 + m * duck * 1.0 + sfx
    mixed = mixed[:int(duration * SR)]
    peak = np.max(np.abs(mixed)) or 1
    mixed = mixed / peak * 0.89
    sf.write(path, np.stack([mixed, mixed], axis=1), SR, subtype="PCM_16")

def icon_svgs(names):
    out = {}
    for nm in names:
        p = HERE / "node_modules/lucide-static/icons" / f"{nm}.svg"
        if p.exists():
            svg = p.read_text()
            svg = re.sub(r'<!--.*?-->', '', svg, flags=re.S).strip()
            out[nm] = svg
    return out

# ---------------- media (photos, stills and stock video behind the graphics) ----------------
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}

def _cover(img, W, H, fx=0.5, fy=0.5):
    from PIL import Image
    w, h = img.size; s = max(W / w, H / h)
    nw, nh = max(W, int(round(w * s))), max(H, int(round(h * s)))
    img = img.resize((nw, nh), Image.LANCZOS)
    x = int(round((nw - W) * fx)); y = int(round((nh - H) * fy))
    return img.crop((x, y, x + W, y + H))

def _blur_fill(img):
    from PIL import ImageFilter, ImageEnhance
    f = _cover(img, 540, 960).filter(ImageFilter.GaussianBlur(18))
    f = ImageEnhance.Brightness(f).enhance(0.6)
    return f.resize((1080, 1920))

def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out); st = j["streams"][0]
    return st["width"], st["height"], float(j["format"].get("duration", 0) or 0)

def prepare_media(sb, beats, sid, out_dir):
    """Turn each beat's `media` (one item or a list) into timed layers for the template."""
    from PIL import Image
    work = out_dir / f"{sid}_media"; work.mkdir(parents=True, exist_ok=True)
    items, credits, k = [], [], 0
    for bi, (beat, b) in enumerate(zip(sb["beats"], beats)):
        med = beat.get("media")
        if not med: continue
        med = med if isinstance(med, list) else [med]
        start = 0.0 if bi == 0 else b["start"]; end = b["end"]; seg = (end - start) / len(med)
        for j, m in enumerate(med):
            src = (HERE / m["src"]).resolve()
            if not src.exists():
                print(f"  warning: missing media {src}", file=sys.stderr); continue
            kind = "video" if src.suffix.lower() in VIDEO_EXT else "image"
            fx, fy = (m.get("focus") or [0.5, 0.4])[:2]
            d = work / f"m{k}"; d.mkdir(exist_ok=True); k += 1
            t0, t1 = start + j * seg, start + (j + 1) * seg
            it = {"kind": kind, "t0": round(t0, 3), "t1": round(t1, 3), "credit": m.get("credit", ""),
                  "kb": m.get("zoom"), "panX": m.get("panX", 0), "panY": m.get("panY", 0)}
            if kind == "image":
                img = Image.open(src).convert("RGB"); w, h = img.size
                layout = m.get("layout") or ("card" if w / h > 0.8 else "cover")
                if layout == "card":
                    ch = min(700 if m.get("label") else 780, int(round(960 * h / w)))  # leave room for a name label above the captions
                    _cover(img, 960, ch, fx, fy).save(d / "card.jpg", quality=90)
                    _blur_fill(img).save(d / "fill.jpg", quality=85)
                    it.update(card=os.path.relpath(d / "card.jpg", HERE), cardH=ch, cardTop=int(370 + (760 - ch) / 2))
                else:
                    _cover(img, 1080, 1920, fx, fy).save(d / "fill.jpg", quality=90)
                it["fill"] = os.path.relpath(d / "fill.jpg", HERE)
            else:
                w, h, dur = _probe(src)
                layout = m.get("layout") or "cover"
                need = (t1 - t0) + 0.6; ss = float(m.get("start", 0))
                loop = ["-stream_loop", "-1"] if dur and dur - ss < need else []
                fr = d / "frames"; fr.mkdir(exist_ok=True)
                if layout == "card":
                    ch = min(780, int(round(960 * h / w)) // 2 * 2)
                    vf = f"scale=960:{ch}:force_original_aspect_ratio=increase,crop=960:{ch}:(in_w-960)*{fx}:(in_h-{ch})*{fy},fps={FPS}"
                    it.update(card=os.path.relpath(fr / "00001.jpg", HERE), cardH=ch, cardTop=int(370 + (760 - ch) / 2))
                else:
                    vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(in_w-1080)*{fx}:(in_h-1920)*{fy},fps={FPS}"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *loop, "-ss", f"{ss:.2f}", "-i", str(src), "-t", f"{need:.2f}",
                                "-vf", vf, "-q:v", "4", str(fr / "%05d.jpg")], check=True)
                frames = sorted(fr.glob("*.jpg"))
                if layout == "card":
                    _blur_fill(Image.open(frames[0]).convert("RGB")).save(d / "fill.jpg", quality=85)
                    it["fill"] = os.path.relpath(d / "fill.jpg", HERE)
                else:
                    it["fill"] = os.path.relpath(frames[0], HERE)
                it.update(frames=os.path.relpath(fr, HERE), count=len(frames), fps=FPS)
            # hero: a photo beat with no graphic; card: a whole landscape still under a graphic (lighter dim); bg: full-bleed behind a graphic
            it["mode"] = m.get("mode") or ("hero" if beat["visual"].get("type") == "media" else "card" if layout == "card" else "bg")
            if m.get("dim") is not None: it["dim"] = float(m["dim"])  # per-clip override for busy footage
            if m.get("label"):
                it["label"] = m["label"]
                it["labelTop"] = (it["cardTop"] + it["cardH"] + 28) if it.get("card") else 1080
            items.append(it)
            if m.get("credit"):
                credits.append({"credit": m["credit"], "source": m.get("source", ""), "license": m.get("license", "")})
    return items, credits

async def capture(html, data, duration, frames_cmd, poster_path, poster_t):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        br = await p.chromium.launch()
        pg = await br.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        await pg.goto(html.as_uri())
        await pg.evaluate("document.fonts.ready")
        await pg.evaluate("(d) => window.build(d)", data)
        await pg.evaluate("document.fonts.ready")
        await pg.wait_for_timeout(150)
        proc = subprocess.Popen(frames_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
        nframes = int(math.ceil(duration * FPS))
        has_video = any(m.get("kind") == "video" for m in data.get("media", [])) or bool(data.get("bg"))   # frames to swap in (prepMedia)
        for i in range(nframes):
            t = i / FPS
            if has_video:
                await pg.evaluate(f"window.prepMedia({t:.4f})")
            await pg.evaluate(f"window.renderAt({t:.4f})")
            buf = await pg.screenshot(type="jpeg", quality=90)
            proc.stdin.write(buf)
            if poster_path and abs(t - poster_t) < 0.5 / FPS:
                pathlib.Path(poster_path).write_bytes(buf)
        proc.stdin.close(); proc.wait()
        await br.close()

def main():
    sb_path = pathlib.Path(sys.argv[1]); out_dir = pathlib.Path(sys.argv[2]); out_dir.mkdir(parents=True, exist_ok=True)
    sb = json.loads(sb_path.read_text())
    sid = sb["id"]; t0 = time.time()
    segs, words, beats, groups, duration = build_timeline(sb)
    wav = out_dir / f"{sid}.wav"
    mix_audio(segs, beats, duration, sb.get("seed", 3), str(wav))
    icons = set([sb.get("chipIcon", "trending-up")])
    for b in sb["beats"]:
        for it in b["visual"].get("items", []):
            if isinstance(it, dict) and it.get("icon"): icons.add(it["icon"])
    data = {"accent": sb.get("accent", "#2EE6C5"), "category": sb["category"], "chipIcon": sb.get("chipIcon", "trending-up"),
            "icons": icon_svgs(icons), "beats": beats, "words": words, "groups": groups, "duration": duration}
    media, credits = prepare_media(sb, beats, sid, out_dir)
    data["media"] = media
    (out_dir / f"{sid}.credits.json").write_text(json.dumps(credits, indent=1, ensure_ascii=False))
    (out_dir / f"{sid}.timeline.json").write_text(json.dumps({"beats": beats, "words": words, "groups": groups, "duration": duration}, indent=1))
    silent = out_dir / f"{sid}.video.mp4"
    # The browser upload tool takes under 10 MB per file, so cap the video rate to fit ~9.4 MB with 128k audio.
    vmax = int(min(8_000_000, 0.95 * (9.4e6 * 8 / duration - 128_000)) / 1000)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(sb.get("crf", 22)), "-maxrate", f"{vmax}k", "-bufsize", f"{2 * vmax}k",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-r", str(FPS), str(silent)]
    asyncio.run(capture(HERE / "template.html", data, duration, cmd, out_dir / f"{sid}.poster.jpg", sb.get("posterT", 0.4)))
    final = out_dir / f"{sid}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav),
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                    "-movflags", "+faststart", "-shortest", str(final)], check=True)
    if final.stat().st_size > 9.6e6:  # rare: two-pass to a fixed bitrate from the capped first encode
        vb = int((9.2e6 * 8 / duration - 128_000) / 1000); tmp = out_dir / f"{sid}.2pass.mp4"; log = str(out_dir / f"{sid}.x264")
        for p, dst in ((1, "/dev/null"), (2, str(tmp))):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-c:v", "libx264", "-preset", "medium", "-b:v", f"{vb}k",
                            "-pass", str(p), "-passlogfile", log, "-pix_fmt", "yuv420p", "-an", "-f", "mp4", dst], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-i", str(wav), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", "-shortest", str(final)], check=True)
        tmp.unlink(missing_ok=True)
        for f in out_dir.glob(f"{sid}.x264*"): f.unlink()
    silent.unlink(missing_ok=True)
    size = final.stat().st_size / 1e6
    print(json.dumps({"id": sid, "duration": round(duration, 2), "size_mb": round(size, 2), "secs": round(time.time() - t0, 1), "file": str(final)}))

if __name__ == "__main__":
    main()
