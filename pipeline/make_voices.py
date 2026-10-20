"""Voice bank (Charlie, 20 October): new narrators to test, as Chatterbox voices cloned from Kokoro's built-in voices.

  python pipeline/make_voices.py refs      Kokoro (Apache 2.0) speaks a short reference clip in each voice of BANK
                                           (pipeline/voices/<name>_ref.wav); the presets go into pipeline/voices/voices.json,
                                           which tts_cb.py reads alongside its own.
  python pipeline/make_voices.py samples   Chatterbox reads a sample in every voice exactly as it voices a Short (tts_cb.py):
                                           review/voices/en_<name>.mp3, for Charlie to listen to. Each new voice that reads
                                           clearly joins the voice options in templates/looks.json, where the looks system
                                           tries it on real Shorts and keeps whichever voices hold viewers best.
Run by .github/workflows/voicebank.yml (push requests/voicebank.txt): refs on Python 3.11 (Kokoro), samples on the
render's own setup.
"""
import json, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PRESETS, LOOKS, OUT = HERE / "voices" / "voices.json", ROOT / "templates" / "looks.json", ROOT / "review" / "voices"
REF_TEXT = ("Here's something most people never notice. The biggest stories often start small, with one strange detail "
            "that changes everything. So, what would you have done? Stick around, because the ending is the best part.")
SAMPLE = ["This could be the new voice of Quickplay Daily.",
          "Here's how a big moment sounds: the final whistle blows, and the whole stadium goes silent.",
          "And here's how a question sounds. Which voice should we keep?"]
BANK = [    # look name, Kokoro voice, Kokoro language (b British, a American), preset id, description, expressiveness, cfg
    ("lewis", "bm_lewis", "b", "LW", "British male, deeper and calm", 0.5, 0.5),
    ("daniel", "bm_daniel", "b", "DN", "British male, brisk", 0.6, 0.5),
    ("isabella", "bf_isabella", "b", "IS", "British female, warm", 0.55, 0.45),
    ("lily", "bf_lily", "b", "LY", "British female, bright", 0.65, 0.45),
    ("michael", "am_michael", "a", "MI", "American male, friendly", 0.6, 0.5),
    ("heart", "af_heart", "a", "HT", "American female, expressive", 0.7, 0.45),
]
CLEAR = 0.4     # least share of a beat's words the speech check must hear (run_board.py calls a beat under this unclear)


def refs():
    import numpy as np, soundfile as sf
    from kokoro import KPipeline
    pipes, made = {}, {}
    for name, kv, lang, pid, desc, exag, cfg in BANK:
        try:
            if lang not in pipes: pipes[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
            parts = [np.asarray(a.numpy() if hasattr(a, "numpy") else a, dtype=np.float32)
                     for _, _, a in pipes[lang](REF_TEXT, voice=kv, speed=1.0) if a is not None]
            sf.write(HERE / "voices" / f"{name}_ref.wav", np.concatenate(parts), 24000)
            made[pid] = {"ref": f"voices/{name}_ref.wav", "exag": exag, "cfg": cfg}
            print(name, "reference made", flush=True)
        except Exception as e:
            print(f"{name}: failed ({type(e).__name__}: {e})"[:300], flush=True)
    old = json.loads(PRESETS.read_text()) if PRESETS.exists() else {}
    PRESETS.write_text(json.dumps({**old, **made}, indent=1) + "\n")
    if not made: sys.exit("no voice references made")


def samples():
    import numpy as np, soundfile as sf
    looks = json.loads(LOOKS.read_text())
    opts = looks["dimensions"]["voice"]["options"]
    presets = json.loads(PRESETS.read_text()) if PRESETS.exists() else {}
    todo = {k: (o["voice"], float(o.get("wps", 3.0)), o.get("desc", "")) for k, o in opts.items()}   # today's voices too, to compare
    for name, kv, lang, pid, desc, exag, cfg in BANK:
        if pid in presets and (HERE / presets[pid]["ref"]).exists(): todo.setdefault(name, (pid, 3.0, desc))
    tmp = pathlib.Path(tempfile.mkdtemp())
    board = tmp / "sample.json"
    board.write_text(json.dumps({"id": "voice-sample", "beats": [{"say": s} for s in SAMPLE]}))
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, (pid, wps, desc) in todo.items():
        d = tmp / name
        try:
            subprocess.run([sys.executable, str(HERE / "tts_cb.py"), str(board), str(d), "--voice", pid, "--target-wps", str(wps)],
                           check=True)
            man = json.loads((d / "cb_manifest.json").read_text())
            sr = man["sr"]
            audio = []
            for b in man["beats"]:
                y, _ = sf.read(d / b["file"], dtype="float32")
                audio += [y, np.zeros(int(0.3 * sr), dtype=np.float32)]
            sf.write(tmp / f"{name}.wav", np.concatenate(audio), sr)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp / f"{name}.wav"), "-b:a", "96k",
                            str(OUT / f"en_{name}.mp3")], check=True)
        except Exception as e:
            print(f"{name}: no sample ({type(e).__name__}: {e})"[:300], flush=True); continue
        heard = min(b["recall"] for b in man["beats"])
        new = name not in opts
        if new and heard >= CLEAR: opts[name] = {"desc": desc, "voice": pid, "wps": 3.0}
        rows.append((name, desc, heard, "in the test" if name in opts else "left out: not clear enough"))
        print(name, f"heard {heard:.0%}", rows[-1][3], flush=True)
    LOOKS.write_text(json.dumps(looks, indent=1, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text(
        "# Voice samples\n\nEach file is the same three lines read by one narrator, exactly as a Short is voiced. Every voice "
        "marked \"in the test\" is tried on real Shorts, and the looks system keeps whichever hold viewers best.\n\n"
        "| Sample | Voice | Words heard by the speech check | Status |\n|---|---|---|---|\n"
        + "".join(f"| [en_{n}.mp3](en_{n}.mp3) | {d} | {h:.0%} | {s} |\n" for n, d, h, s in rows))


if __name__ == "__main__":
    {"refs": refs, "samples": samples}[sys.argv[1]]()
