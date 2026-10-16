"""Builds the platform-safe music library used for the TikTok and Instagram versions (pipeline/music_social).

usage: python pipeline/music_social_build.py pipeline/music_social/picks.json
picks.json: [{"slug", "title", "artist", "pixabay_id", "page", "src", "moods", "categories"}] chosen from Pixabay Music
(Pixabay Content License: free for commercial use, no attribution; tracks registered with Content ID or marked as AI-made
are left out when picking). Each track is downloaded once, cut to its strongest ~75 s (starting on a beat), faded out,
encrypted with MUSIC_KEY (the repo is public, so plain audio is never committed) and added to catalog.json.
Tracks already in the catalog are skipped, so the script can be re-run with more picks.
"""
import json, os, pathlib, subprocess, sys, tempfile
import numpy as np, librosa, requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / "pipeline" / "music_social"
SEG, WIN_S, HOP, SR = 75.0, 50.0, 512, 22050
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
      "Referer": "https://pixabay.com/"}

def cut(src, dst):
    y, sr = librosa.load(src, sr=SR, mono=True)
    dur = len(y) / sr
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    win = int(WIN_S * sr / HOP); first = int(6 * sr / HOP)
    cs = np.concatenate([[0.0], np.cumsum(rms)])
    last = max(first + 1, len(rms) - win - int(10 * sr / HOP))      # keep clear of the ending
    means = [(cs[i + win] - cs[i]) / win for i in range(first, last)] or [float(np.mean(rms))]
    bi = first + int(np.argmax(means)) if len(rms) > first + win else 0
    start = float(t[bi]) if bi < len(t) else 0.0
    before = [b for b in beats if b <= start + 0.01]
    if before: start = float(before[-1])
    seg = min(SEG, dur - start)
    if seg < 55:
        start = max(0.0, dur - 60.0); seg = dur - start
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{seg:.3f}", "-i", str(src),
                    "-af", f"afade=t=out:st={max(0.0, seg - 2.5):.2f}:d=2.5", "-ac", "2", "-ar", "44100", "-b:a", "128k", str(dst)], check=True)
    part = y[int(start * sr):int((start + seg) * sr)]
    seg_rms = rms[bi:bi + win] if len(rms) > bi + 10 else rms
    return {"dur": round(seg, 1), "bpm": round(tempo, 1), "start": 0.0, "energy": round(float(np.mean(seg_rms)), 4),
            "beats": [round(float(b - start), 3) for b in beats if start <= b <= start + seg],
            "full_dur": round(dur, 1), "cut_from": round(start, 2),
            "brightness": round(float(np.mean(librosa.feature.spectral_centroid(y=part, sr=sr)))),
            "punch": round(float(np.mean(librosa.onset.onset_strength(y=part, sr=sr))), 2)}

def main(picks_path):
    if len(os.environ.get("MUSIC_KEY", "")) < 8: raise SystemExit("MUSIC_KEY secret missing")
    picks = json.loads(pathlib.Path(picks_path).read_text())
    cat_p = LIB / "catalog.json"
    cat = json.loads(cat_p.read_text()) if cat_p.exists() else []
    have = {c["slug"] for c in cat if (LIB / f"{c['slug']}.mp3.enc").exists()}
    cat = [c for c in cat if c["slug"] in have]
    report = {"added": [], "skipped": [], "failed": []}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for p in picks:
            if p["slug"] in have: report["skipped"].append(p["slug"]); continue
            try:
                r = requests.get(p["src"], headers=UA, timeout=120)
                if r.status_code != 200 or len(r.content) < 200_000 or b"<html" in r.content[:500].lower():
                    raise RuntimeError(f"download {r.status_code}, {len(r.content)} bytes, {r.headers.get('content-type')}")
                raw, out = tmp / f"{p['slug']}.src.mp3", LIB / f"{p['slug']}.mp3"
                raw.write_bytes(r.content)
                info = cut(raw, out)
                subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-in", str(out), "-out", str(out) + ".enc",
                                "-pass", "env:MUSIC_KEY"], check=True)
                out.unlink(); raw.unlink()
                cat.append({"slug": p["slug"], "title": p["title"], "artist": p["artist"], "genre": "", "mood": "", **info,
                            "moods": p["moods"], "categories": p["categories"], "source": "Pixabay Music",
                            "page": p["page"], "pixabay_id": p["pixabay_id"], "licence": "Pixabay Content License"})
                report["added"].append(f"{p['slug']} ({'/'.join(p['moods'])}, {info['bpm']} bpm, cut {info['cut_from']}s)")
                print("added", p["slug"], info["bpm"], info["cut_from"])
            except Exception as e:
                report["failed"].append(f"{p['slug']}: {e}"[:200]); print("FAILED", p["slug"], e)
    cat_p.write_text(json.dumps(cat, ensure_ascii=False, indent=0))
    report["total"] = len(cat)
    from collections import Counter
    report["moods"] = dict(Counter(m for c in cat for m in c["moods"]))
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / "music_social.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}))

if __name__ == "__main__":
    main(sys.argv[1])
