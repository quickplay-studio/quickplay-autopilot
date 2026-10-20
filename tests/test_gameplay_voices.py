"""Offline tests: gameplay footage source (fetch_media) and the voice bank (make_voices refs and samples), all mocked."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import json, os, pathlib, shutil, subprocess, sys, types
import numpy as np, soundfile as sf
REPO = pathlib.Path(REPO_DIR)
SCR = pathlib.Path(SCRATCH + "/t5")
shutil.rmtree(SCR, ignore_errors=True); SCR.mkdir(parents=True)
sys.path.insert(0, str(REPO / "pipeline"))
import fetch_media as FM

# a 40 second test clip, served as a release asset
clip = SCR / "parkour1.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=40", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", str(clip)], check=True)


class Resp:
    def __init__(self, ok, data=None, body=b""): self.ok, self.data, self.body = ok, data, body
    def json(self): return self.data
    def raise_for_status(self): pass
    def iter_content(self, n): yield self.body
    def __enter__(self): return self
    def __exit__(self, *a): pass


calls = []
def fake_get(url, **kw):
    calls.append((url, kw.get("headers")))
    if "releases/tags/gameplay" in url:
        return Resp(RELEASE is not None, {"assets": RELEASE or []})
    return Resp(True, body=clip.read_bytes())

FM.requests.get = fake_get
FM.GAMEPLAY = SCR / "gameplay"
stock = []
FM.pixabay = lambda kind, words, used, dark_ok=False: (stock.append((kind, words)) or (f"https://pixabay.example/{words.replace(' ', '_')}.mp4", "Pixabay", "pixabay page"))
FM.download = lambda url, d, stem: (d / f"{stem}.mp4").write_bytes(b"x") and d / f"{stem}.mp4"
board = lambda: {"id": "QD-T5", "beats": [{"say": "a", "shots": [{"src": "gameplay:parkour rooftop run"}]},
                                         {"say": "b", "shots": [{"src": "gameplay:parkour rooftop run"}, {"src": "gameplay:"}]}]}

# 1. no release yet: stock video of the same words, never the same clip twice (no caching)
RELEASE = None
sb = FM.resolve(board())
print("no release ->", [s["src"] for b in sb["beats"] for s in b["shots"]], stock)
assert stock == [("video", "parkour rooftop run"), ("video", "parkour rooftop run"), ("video", "parkour rooftop run")]
assert len({s["src"] for b in sb["beats"] for s in b["shots"]}) == 3

# 2. with recordings: our own clips, a start point inside each, credited to us, token sent
FM._CLIPS.clear(); stock.clear(); calls.clear()
os.environ["GITHUB_TOKEN"] = "test-token"
RELEASE = [{"name": "parkour1.mp4", "browser_download_url": "https://dl.example/parkour1.mp4"},
           {"name": "notes.txt", "browser_download_url": "https://dl.example/notes.txt"},
           {"name": "parkour2.MKV", "browser_download_url": "https://dl.example/parkour2.mkv"}]
sb = FM.resolve(board())
shots = [s for b in sb["beats"] for s in b["shots"]]
for s in shots: print("  ", s["src"], s["start"], s["credit"], s["source"])
assert not stock and all((FM.HERE / s["src"]).resolve().parent == FM.GAMEPLAY and s["credit"] == "Quickplay Daily" for s in shots)
assert all(0 <= s["start"] <= 20 for s in shots if s["src"].endswith("parkour1.mp4"))
assert calls[0][1] == {"Authorization": "Bearer test-token"} and not any("notes.txt" in c[0] for c in calls)
assert sum(1 for c in calls if "releases/tags" in c[0]) == 1        # the release is listed once per render
print("gameplay ok")

# 3. stock counting: gameplay counts as stock for the validator and is not a real picture for run_board's tally
import validate as V
b = json.loads((REPO / "boards" / "hold" / "QD-028.json").read_text())
for bt in b["beats"]: bt["shots"] = [{"src": "gameplay:marble run"}]
errs, warns = V.check(b)[:2]
print("validator:", errs[:2], [w for w in warns if "stock" in w][:2])
assert any("stock" in w for w in warns) and not any("src" in e for e in errs)

# 4. voice bank: refs with a stand-in Kokoro, samples with a stand-in Chatterbox
import make_voices as MV
(SCR / "voices").mkdir(); (SCR / "review").mkdir()
_l = json.loads((REPO / "templates" / "looks.json").read_text())
for _k in ("lewis", "daniel", "isabella", "lily", "michael", "heart"): _l["dimensions"]["voice"]["options"].pop(_k, None)
(SCR / "looks.json").write_text(json.dumps(_l))
MV.HERE = SCR; MV.PRESETS, MV.LOOKS, MV.OUT = SCR / "voices" / "voices.json", SCR / "looks.json", SCR / "review"


class KPipeline:
    def __init__(self, lang_code, repo_id=None): self.lang = lang_code; print("  KPipeline", lang_code)
    def __call__(self, text, voice=None, speed=1.0):
        if voice == "bf_lily": raise RuntimeError("voice missing")
        for _ in range(2): yield ("g", "p", np.sin(np.linspace(0, 900, 24000)).astype(np.float32))

sys.modules["kokoro"] = types.SimpleNamespace(KPipeline=KPipeline)
MV.refs()
presets = json.loads(MV.PRESETS.read_text())
print("presets:", sorted(presets))
assert sorted(presets) == ["DN", "HT", "IS", "LW", "MI"] and (SCR / "voices" / "lewis_ref.wav").exists()

real_run = subprocess.run
def fake_run(cmd, check=False, **kw):
    if str(cmd[1]).endswith("tts_cb.py"):
        out, voice = pathlib.Path(cmd[3]), cmd[cmd.index("--voice") + 1]
        out.mkdir(parents=True, exist_ok=True)
        beats = []
        for i in range(3):
            sf.write(out / f"cb_b{i:02d}.wav", np.zeros(4800, dtype=np.float32), 24000)
            beats.append({"beat": i, "file": f"cb_b{i:02d}.wav", "dur": 0.2, "recall": 0.3 if voice == "MI" else 0.9})
        (out / "cb_manifest.json").write_text(json.dumps({"sr": 24000, "voice": voice, "beats": beats}))
        return subprocess.CompletedProcess(cmd, 0)
    return real_run(cmd, check=check, **kw)
MV.subprocess.run = fake_run
MV.samples()
opts = json.loads(MV.LOOKS.read_text())["dimensions"]["voice"]["options"]
print("voice options:", sorted(opts))
print((SCR / "review" / "README.md").read_text())
assert {"lewis", "daniel", "isabella", "heart"} <= set(opts) and "michael" not in opts and "lily" not in opts
assert opts["lewis"] == {"desc": "British male, deeper and calm", "voice": "LW", "wps": 3.0}
assert (SCR / "review" / "en_george.mp3").exists() and (SCR / "review" / "en_heart.mp3").exists()
print("voice bank ok")
