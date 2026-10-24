"""Offline test of the george_turbo voice (24 October): Chatterbox-Turbo as one more voice option in the looks system. No model is
loaded and nothing is downloaded; every model, download and render step is a stand-in.
1. templates/looks.json and looks.py: george_turbo is a voice option on the T2 preset at the house pace, drawn like the others;
2. tts_cb.py: a "turbo" preset loads ChatterboxTurboTTS from $CB_TURBO_CKPT with the george reference and passes no exaggeration or
   cfg; missing model files end the run with the fix; the standard voices are read exactly as before;
3. get_model.py: the Turbo pins (a commit, a hash for every file the loader reads), both kinds of hash, a bad file deleted, --turbo;
4. run_board.py: a voice that cannot start is read in the house voice with a note, the house voice failing still fails the render,
   an unclear read still falls back, a clear Turbo read stays;
5. render.yml: only a Short drawn that voice fetches the model, a failed fetch never fails the job, the OCR extra is pinned."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, copy, hashlib, io, json, os, re, runpy, subprocess, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import numpy as np

# 1. the option ----------------------------------------------------------------------------------------------------------------
import looks as LK
raw = json.loads(open("templates/looks.json").read())["dimensions"]["voice"]["options"]
assert raw["george_turbo"]["voice"] == "T2" and raw["george_turbo"]["wps"] == 3.0 and raw["george_turbo"]["born"] == "2026-10-24"
assert "Turbo" in raw["george_turbo"]["desc"] and "retired" not in raw["george_turbo"]
cat = copy.deepcopy(LK.catalogue())
cat["dimensions"]["voice"]["options"]["george_turbo"].pop("retired", None)       # the weekly review may retire it later: this test is about the option, not that verdict
assert "george_turbo" in LK.active(cat, "voice")
assert LK.resolve({"voice": "george_turbo"}, cat)["voice"] == {"voice": "T2", "wps": 3.0}
drawn = [LK.choose(f"QD-{i}", [], {}, cat)["voice"] for i in range(1500)]
share = drawn.count("george_turbo") / len(drawn)
assert 0.03 < share < 0.25, share                       # with no data, about one Short in the number of active voices: no more than any other
print(f"1 option ok: drawn {share:.1%} of Shorts with no data")

# 2. tts_cb.py: stand-ins for torch (when it is not here), the two model classes and the speech check ---------------------------
try: import torch
except ImportError: sys.modules["torch"] = types.SimpleNamespace(set_num_threads=lambda n: None, manual_seed=lambda s: None)

class Wave:
    """What generate() gives back: a (1, n) tensor, as far as tts_cb.py uses one."""
    def __init__(self, a): self.a = a
    def squeeze(self, dim): return Wave(self.a[0])
    def numpy(self): return self.a

loaded = []
class Model:
    sr = 24000
    def __init__(self): self.cond, self.made = [], []
    def prepare_conditionals(self, wav, **kw): self.cond.append((wav, kw))
    def generate(self, text, **kw): self.made.append((text, kw)); return Wave(np.full((1, 24000), 0.2, np.float32))      # one second of tone
def loader(kind):
    def from_local(ckpt, device): m = Model(); loaded.append((kind, str(ckpt), device, m)); return m
    return staticmethod(from_local)
def module(name, **attrs):
    """A stand-in module in sys.modules, whatever is installed."""
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m
    return m
module("chatterbox", __path__=[])
module("chatterbox.tts", ChatterboxTTS=type("ChatterboxTTS", (), {"from_local": loader("standard")}))
module("chatterbox.tts_turbo", ChatterboxTurboTTS=type("ChatterboxTurboTTS", (), {"from_local": loader("turbo")}))
module("qa_asr", hear=lambda p: "", recall=lambda script, said: (1.0, []))        # every word heard: no beat is read twice
import tts_cb as T
T.CKPT, T.TURBO_CKPT = SCRATCH / "standard", SCRATCH / "turbo"
(SCRATCH / "turbo").mkdir()
for name in T.TURBO_FILES: (SCRATCH / "turbo" / name).write_bytes(b"x")
board = SCRATCH / "board.json"
board.write_text(json.dumps({"id": "QD-990", "beats": [{"say": "one two three"}, {"say": "four five six"}]}))       # 3 words a second at 1 s a beat: no speed-up, no ffmpeg
george = str(T.HERE / "voices" / "george_ref.wav")

def read(voice, out):
    sys.argv = ["tts_cb.py", str(board), str(out), "--voice", voice, "--target-wps", "3.0"]
    loaded.clear()
    with contextlib.redirect_stdout(io.StringIO()) as log: T.main()
    return json.loads((out / "cb_manifest.json").read_text()), log.getvalue()

assert T.VOICES["T2"] == {"ref": "voices/george_ref.wav", "engine": "turbo"} and T.VOICES["F2"]["ref"] == T.VOICES["T2"]["ref"]       # the same voice reference as george
assert not any(v.get("engine") for k, v in T.VOICES.items() if k != "T2")
man, log = read("T2", SCRATCH / "o1")
(kind, ckpt, device, m), = loaded
assert (kind, ckpt, device) == ("turbo", str(SCRATCH / "turbo"), "cpu"), loaded
assert m.cond == [(george, {})]                                                  # the george reference, no exaggeration
assert [kw for _, kw in m.made] == [{}, {}]                                      # generate() got the text and nothing else: Turbo has no exaggeration or cfg
assert man["voice"] == "T2" and man["sr"] == 24000 and man["wps"] == 3.0 and len(man["beats"]) == 2 and "(Chatterbox-Turbo)" in log

(SCRATCH / "turbo" / "merges.txt").unlink()
try: read("T2", SCRATCH / "o2"); raise AssertionError("a voice with missing model files must not start")
except SystemExit as e: msg = str(e)
assert "merges.txt" in msg and "get_model.py" in msg and "--turbo" in msg and not loaded       # told what to fetch; nothing was loaded
(SCRATCH / "turbo" / "merges.txt").write_bytes(b"x")

man, log = read("F2", SCRATCH / "o3")                                            # the standard voices, as before
(kind, ckpt, device, m), = loaded
assert (kind, ckpt, device) == ("standard", str(SCRATCH / "standard"), "cpu") and "Turbo" not in log
assert m.cond == [(george, {"exaggeration": 0.6})] and [kw for _, kw in m.made] == [{"exaggeration": 0.6, "cfg_weight": 0.5}] * 2
print("2 tts_cb ok")

# 3. get_model.py: pins and hash checks, with a stand-in for the download ------------------------------------------------------
CONTENT = {}
fetched = []
def hf_hub_download(repo, name, revision=None, local_dir=None):
    fetched.append((repo, name, revision)); (_p.Path(local_dir) / name).write_bytes(CONTENT.get(name, b"wrong"))
module("huggingface_hub", hf_hub_download=hf_hub_download)
import get_model as GM
assert GM.TURBO_REPO == "ResembleAI/chatterbox-turbo" and re.fullmatch(r"[0-9a-f]{40}", GM.TURBO_REV)
assert set(GM.TURBO_FILES) == set(T.TURBO_FILES), "the files fetched are not the files the loader reads"
assert all(re.fullmatch(r"[0-9a-f]{64}|[0-9a-f]{40}", h) for h in GM.TURBO_FILES.values())       # every file is checked, by SHA-256 or git blob id
assert GM.TURBO_FILES["ve.safetensors"] == GM.FILES["ve.safetensors"]            # the voice encoder is the standard model's, byte for byte
assert GM.REV == "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18" and set(GM.FILES) == {"t3_cfg.safetensors", "s3gen.safetensors", "ve.safetensors", "tokenizer.json"}

hello = SCRATCH / "hello.txt"; hello.write_bytes(b"hello\n")
assert GM.blob_id(hello) == "ce013625030ba8dba906f756967f9e9ca394464a"           # what `git hash-object` gives for these bytes
assert GM.sha256(hello) == hashlib.sha256(b"hello\n").hexdigest()
assert GM.matches(hello, GM.blob_id(hello)) and GM.matches(hello, GM.sha256(hello))
assert not GM.matches(hello, "0" * 40) and not GM.matches(hello, "0" * 64)

CONTENT.update({"a.txt": b"alpha\n", "b.bin": b"beta", "c.json": b"{}"})
files = {"a.txt": hashlib.sha1(b"blob 6\0alpha\n").hexdigest(), "b.bin": hashlib.sha256(b"beta").hexdigest(), "c.json": None}
dest = SCRATCH / "dl"
with contextlib.redirect_stdout(io.StringIO()): GM.fetch("o/r", "abc123", files, dest)
assert fetched == [("o/r", n, "abc123") for n in files] and all((dest / n).exists() for n in files)
fetched.clear()
with contextlib.redirect_stdout(io.StringIO()): GM.fetch("o/r", "abc123", files, dest)
assert fetched == []                                                             # the files are there and still match: nothing downloaded again
(dest / "b.bin").write_bytes(b"tampered")
try:
    with contextlib.redirect_stdout(io.StringIO()): GM.fetch("o/r", "abc123", files, dest)
    raise AssertionError("a file with the wrong hash must stop the run")
except SystemExit as e: assert str(e) == "b.bin: hash mismatch, deleted"
assert not (dest / "b.bin").exists() and (dest / "a.txt").exists()               # the bad file is gone

def cli(*argv):
    fetched.clear(); sys.argv = ["get_model.py", *argv]
    try:
        with contextlib.redirect_stdout(io.StringIO()): runpy.run_path("pipeline/get_model.py", run_name="__main__")
    except SystemExit as e: return str(e)
assert cli(str(SCRATCH / "m1"), "--turbo") == "t3_turbo_v1.safetensors: hash mismatch, deleted"       # the stand-in file is not the real weights
assert fetched == [(GM.TURBO_REPO, "t3_turbo_v1.safetensors", GM.TURBO_REV)]    # --turbo: the Turbo repo, at its pinned commit
assert cli(str(SCRATCH / "m2")) == "t3_cfg.safetensors: hash mismatch, deleted"
assert fetched == [(GM.REPO, "t3_cfg.safetensors", GM.REV)]                      # without it: the standard model, as before
print("3 get_model ok")

# 4. run_board.py: main() as far as the narration, with tts_cb.py and the media stood in for -----------------------------------
import run_board as RB
repo = SCRATCH / "repo"
(repo / "pipeline").mkdir(parents=True); (repo / "boards" / "queue").mkdir(parents=True)
(repo / "config.json").write_text(json.dumps({"approval": "none"}))
(repo / "boards" / "queue" / "QD-990.json").write_text(json.dumps({"id": "QD-990", "category": "Science", "meta": {"title": "The moon"},
    "beats": [{"say": "The moon is slowly drifting away"}, {"say": "Each year it moves a little further"}]}))
RB.ROOT, RB.P = repo, repo / "pipeline"
module("fetch_media", resolve=lambda sb: sb, extras=lambda sb: 0)
module("background", wanted=lambda sb, cfg: False, fetch=lambda *a: ([], []), settings=lambda cfg: {})
RB.pick_music, RB.pick_social_music = (lambda sb: {"slug": "calm"}), (lambda sb: None)

def drive(option, recall=None, crash=()):
    """Voices asked for by tts_cb.py, in order, and the status file. `crash`: voices that cannot start; `recall`: what the speech check hears."""
    asked = []
    def fake_sh(*cmd, cwd=None):
        if str(cmd[1]) == "render3.py": raise RuntimeError("stop after the narration")        # the test ends where the video would begin
        voice = cmd[cmd.index("--voice") + 1]; asked.append(voice)
        if voice in crash: raise subprocess.CalledProcessError(3, [str(c) for c in cmd])
        d = _p.Path(cmd[3]); d.mkdir(parents=True, exist_ok=True)
        beats = [{"beat": i, "file": f"cb_b{i:02d}.wav", "dur": 2.0, "recall": (recall or {}).get(voice, 0.9), "text": "x"} for i in range(2)]
        (d / "cb_manifest.json").write_text(json.dumps({"sr": 24000, "voice": voice, "tempo": 1.0, "wps": 3.0, "beats": beats}))
    RB.sh = fake_sh
    look = LK.choose("QD-990", [], {}, cat); look["voice"] = option
    os.environ["JOB_JSON"] = json.dumps({"board": "boards/queue/QD-990.json", "id": "QD-990", "slot": "", "mode": "none", "look": look})
    sys.argv = ["run_board.py"]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): RB.main()
    return json.loads((repo / "result" / "QD-990" / "status.json").read_text()), asked

st, asked = drive("george_turbo", crash=("T2",))                                  # Turbo cannot start (its files did not download)
assert asked == ["T2", "F2"] and st["look"]["voice"] == "george", (asked, st)
assert st["look_note"] == "voice T2 could not run (exit 3), used george"
assert st["state"] == "failed" and "stop after the narration" in st["error"]      # on to the video, as for any Short
st, asked = drive("george_turbo")                                                 # Turbo reads clearly: it stays
assert asked == ["T2"] and st["look"]["voice"] == "george_turbo" and "look_note" not in st
st, asked = drive("george_turbo", recall={"T2": 0.1})                             # unclear: the house voice, as for every new voice
assert asked == ["T2", "F2"] and st["look"]["voice"] == "george" and st["look_note"] == "voice T2 was less clear, used george"
st, asked = drive("lewis", recall={"LW": 0.1})
assert asked == ["LW", "F2"] and st["look_note"] == "voice LW was less clear, used george"
st, asked = drive("lewis", crash=("LW",))                                         # any other voice that cannot start is covered the same way
assert asked == ["LW", "F2"] and st["look_note"] == "voice LW could not run (exit 3), used george"
st, asked = drive("george_turbo", crash=("T2", "F2"))                             # the house voice failing is a real failure
assert asked == ["T2", "F2"] and st["state"] == "failed" and st["error"].startswith("CalledProcessError") and "look_note" not in st
st, asked = drive("george_quick", crash=("F2",))
assert asked == ["F2"] and st["error"].startswith("CalledProcessError")
print("4 run_board ok")

# 5. render.yml -----------------------------------------------------------------------------------------------------------------
yml = open(".github/workflows/render.yml").read()
only = "matrix.job.mode != 'reject' && matrix.job.look.voice == 'george_turbo'"
assert yml.count(only) == 2                                                       # the cache and the download, and only for a Short drawn that voice
steps = yml.split("\n      - ")
fetch = [s for s in steps if "get_model.py models/chatterbox-turbo --turbo" in s]
assert len(fetch) == 1 and only in fetch[0] and "continue-on-error: true" in fetch[0]      # a failed download costs a voice test, never a Short
cache = [s for s in steps if "path: models/chatterbox-turbo" in s]
assert len(cache) == 1 and only in cache[0] and f"key: chatterbox-turbo-{GM.TURBO_REV[:7]}" in cache[0]
assert "CB_TURBO_CKPT: ${{ github.workspace }}/models/chatterbox-turbo" in yml
ocr = [l for l in yml.splitlines() if "pip install" in l and "rapidocr" in l]
assert len(ocr) == 1 and "--uploaded-prior-to P7D" in ocr[0] and "rapidocr==3.10.0" in ocr[0] and "onnxruntime==1.31.0" in ocr[0]
assert "|| echo" in ocr[0]                                                        # an extra: a failed install only drops the text number
print("5 render.yml ok")
print("turbo voice ok")
