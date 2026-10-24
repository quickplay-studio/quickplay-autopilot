"""Narration with Chatterbox (MIT licence): one WAV per beat, checked by ear-proxy and sped to a target pace.

usage: python tts_cb.py <board.json> <out_dir> [--voice F2] [--target-wps 3.0] [--seed 1] [--beats 0,1]

Voices are presets in VOICES. Each beat is generated, checked with offline speech recognition (qa_asr),
and regenerated with a new seed (up to 2 more tries) if too few of its words are heard. Then every beat is
sped up by one shared factor (pitch kept) so the whole Short lands near --target-wps words a second.
Model files come from $CB_CKPT (see get_model.py). A preset with "engine": "turbo" (T2, 24 October) is read by Chatterbox-Turbo
instead (chatterbox-tts 0.1.7, chatterbox.tts_turbo: 350M, one-step decoder, no exaggeration or cfg), whose files come from
$CB_TURBO_CKPT (get_model.py <dir> --turbo).
"""
import argparse, json, os, pathlib, re, subprocess, sys, time
import numpy as np, soundfile as sf, torch

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CKPT = pathlib.Path(os.environ.get("CB_CKPT", HERE.parent / "models" / "chatterbox"))
TURBO_CKPT = pathlib.Path(os.environ.get("CB_TURBO_CKPT", HERE.parent / "models" / "chatterbox-turbo"))
TURBO_FILES = ("t3_turbo_v1.safetensors", "s3gen_meanflow.safetensors", "ve.safetensors", "vocab.json", "merges.txt",
               "tokenizer_config.json", "added_tokens.json", "special_tokens_map.json")      # what ChatterboxTurboTTS.from_local reads
VOICES = {
    "F2": {"ref": "voices/george_ref.wav", "exag": 0.6, "cfg": 0.5},    # British male, clear (default)
    "H2": {"ref": "voices/george_ref.wav", "exag": 0.85, "cfg": 0.4},   # British male, more dramatic
    "G": {"ref": "voices/emma_ref.wav", "exag": 0.6, "cfg": 0.4},       # British female
    "T2": {"ref": "voices/george_ref.wav", "engine": "turbo"},          # the same British male on Chatterbox-Turbo (the george_turbo look)
}
try: VOICES.update(json.loads((HERE / "voices" / "voices.json").read_text()))    # the voice bank (make_voices.py)
except (OSError, ValueError): pass
PRONOUNCE = json.loads((HERE / "pronounce.json").read_text())

def speakable(text):
    for a, b in PRONOUNCE.items():
        text = re.sub(rf"\b{re.escape(a)}", b, text)
    return text

def trim(y, sr, thr=0.01, pad=0.04):
    idx = np.where(np.abs(y) > thr)[0]
    if len(idx) == 0: return y
    return y[max(0, idx[0] - int(pad * sr)): min(len(y), idx[-1] + int(pad * sr))]

def heard(path, script):
    try:
        import qa_asr as Q
        return Q.recall(script, Q.hear(str(path)))[0]
    except Exception as e:  # recogniser missing: don't block the render
        print(f"  asr skipped: {e}", file=sys.stderr); return 1.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board"); ap.add_argument("out")
    ap.add_argument("--voice", default=os.environ.get("QP_VOICE", "F2"))
    ap.add_argument("--target-wps", type=float, default=3.0)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--beats", default="")
    a = ap.parse_args()
    v = VOICES[a.voice]
    turbo = v.get("engine") == "turbo"
    torch.set_num_threads(max(1, os.cpu_count() or 2))
    if turbo:       # Chatterbox-Turbo ignores exaggeration and cfg (its generate() warns if they are given), so none are passed
        missing = [f for f in TURBO_FILES if not (TURBO_CKPT / f).exists()]
        if missing: sys.exit(f"Chatterbox-Turbo files missing in {TURBO_CKPT}: {', '.join(missing)} (python pipeline/get_model.py {TURBO_CKPT} --turbo)")
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        t0 = time.time()
        m = ChatterboxTurboTTS.from_local(TURBO_CKPT, "cpu")
        m.prepare_conditionals(str(HERE / v["ref"]))
        gen = {}
    else:
        from chatterbox.tts import ChatterboxTTS
        t0 = time.time()
        m = ChatterboxTTS.from_local(CKPT, "cpu")
        m.prepare_conditionals(str(HERE / v["ref"]), exaggeration=v["exag"])
        gen = {"exaggeration": v["exag"], "cfg_weight": v["cfg"]}
    print(f"voice {a.voice} loaded in {time.time() - t0:.0f}s" + (" (Chatterbox-Turbo)" if turbo else ""), flush=True)
    sb = json.loads(pathlib.Path(a.board).read_text())
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    pick = {int(x) for x in a.beats.split(",") if x != ""}
    beats = []
    for bi, beat in enumerate(sb["beats"]):
        if pick and bi not in pick: continue
        text = speakable(beat.get("say_cb") or beat["say"]); best = None
        for attempt in range(3):
            torch.manual_seed(a.seed * 1000 + bi * 10 + attempt)
            y = trim(m.generate(text, **gen).squeeze(0).numpy().astype(np.float32), m.sr)
            f = out / f"cb_b{bi:02d}.wav"; sf.write(f, y, m.sr)
            r = heard(f, beat["say"])
            if best is None or r > best[0]: best = (r, y)
            if r >= 0.5 or len(beat["say"].split()) < 4: break
            print(f"  beat {bi}: only {r:.0%} of words heard, retrying", flush=True)
        sf.write(out / f"cb_b{bi:02d}.wav", best[1], m.sr)
        beats.append({"beat": bi, "file": f"cb_b{bi:02d}.wav", "dur": round(len(best[1]) / m.sr, 3), "recall": best[0], "text": text})
        print(json.dumps(beats[-1]), flush=True)
    words = sum(len(sb["beats"][b["beat"]]["say"].split()) for b in beats)
    secs = sum(b["dur"] for b in beats)
    tempo = float(np.clip(a.target_wps * secs / max(1, words), 1.0, 1.3))
    if tempo > 1.01:
        for b in beats:
            src = out / b["file"]; tmp = out / ("t_" + b["file"])
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"rubberband=tempo={tempo:.3f}", str(tmp)], check=True)
            tmp.replace(src); b["dur"] = round(b["dur"] / tempo, 3)
    (out / "cb_manifest.json").write_text(json.dumps({"sr": m.sr, "voice": a.voice, "tempo": round(tempo, 3),
                                                      "wps": round(words / max(0.1, secs) * tempo, 2), "beats": beats}, indent=1))
    print(f"done: tempo {tempo:.3f}, {words / max(0.1, secs) * tempo:.2f} words/s", flush=True)

if __name__ == "__main__":
    main()
