"""Offline test of the picture ranking and the face finder (24 October; no network, no model download):
1. get_pictures.py: the YuNet file is kept only at its pinned size and SHA-256 (a wrong or poisoned file is deleted), the SigLIP 2
   files get a manifest, are checked against it and against any pin on every later run, and nothing ever raises;
2. faces.py: YuNet boxes come back in the picture's own pixels, cut to its edge, largest first, with None (not []) when YuNet is
   not available so the callers run their Haar cascade;
3. render3.face_focus and clips.face_box: the YuNet path, the Haar fallback, and no face at all;
4. pictures.py with a fake model: the on-topic picture beats the search's first hit, logos are marked down, near-duplicates are
   dropped, pictures already used go to the back, and every failure hands the choice back (None);
5. fetch_media with a faked Commons, Pixabay, NASA and Openverse: ranking picks, relevance stays on the shot, the old order
   stands without a model, a beat that finds nothing borrows a neighbour's picture and the Short's numbers come out right;
6. analytics: pic_relevance and pic_found_share reach each Short's row;
7. the workflows hold the cache keys, save a cache only when its download is complete, and install imagehash pinned;
8. importing pictures, faces and get_pictures needs neither torch, transformers nor OpenCV;
9. when torch and transformers are installed: the real model code on a tiny random SigLIP checkpoint."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, hashlib, importlib.util, inspect, io, json, os, re, subprocess, sys, time, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
os.environ["QP_MODELS"] = str(SCRATCH / "models")          # nothing here reads or writes the repo's own models/ folder
import numpy as np
from PIL import Image
REPO = _p.Path(REPO_DIR)


def quiet(fn, *a, **k):
    """fn's result and everything it printed."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err): r = fn(*a, **k)
    return r, out.getvalue() + err.getvalue()


# 1. get_pictures: pinned downloads ------------------------------------------------------------------------------------------
import get_pictures as GP, requests

good = b"yunet stand-in file " * 20
bad = bytes(reversed(good))                                      # the same size, another hash
real_yunet, real_siglip = GP.YUNET, GP.SIGLIP
GP.YUNET = dict(real_yunet, size=len(good), sha256=hashlib.sha256(good).hexdigest())
dest = SCRATCH / "m1"; yf = dest / "yunet" / GP.YUNET["file"]
class Resp:
    def __init__(self, content): self.content = content
    def raise_for_status(self): pass
served, hits = {}, []
def fake_get(url, **kw):
    hits.append(url)
    if url not in served: raise requests.ConnectionError("blocked")
    return Resp(served[url])
real_get = requests.get; requests.get = fake_get
try:
    u1, u2 = GP.YUNET["urls"]
    assert not GP.yunet_ok(yf)
    served[u1], served[u2] = bad, good
    ok, text = quiet(GP.get_yunet, dest)
    assert ok and GP.yunet_ok(yf) and hits == [u1, u2], hits         # the first url gave another file: not kept; the second was right
    assert "another hash: deleted" in text and not list(yf.parent.glob("*.part"))
    hits.clear(); ok, text = quiet(GP.get_yunet, dest)
    assert ok and not hits and "ok" in text                          # kept in the cache: nothing downloaded
    yf.write_bytes(bad); assert not GP.yunet_ok(yf)                  # a poisoned cache entry is replaced
    hits.clear(); ok, _ = quiet(GP.get_yunet, dest); assert ok and GP.yunet_ok(yf) and hits == [u1, u2]
    yf.write_bytes(good[:-1]); assert not GP.yunet_ok(yf)            # so is a cut-short one
    served.clear(); ok, text = quiet(GP.get_yunet, dest)
    assert not ok and not yf.exists() and "::warning::yunet" in text   # every address down: no file, a warning, no exception
finally: requests.get = real_get

assert real_yunet["size"] == 232589 and len(real_yunet["sha256"]) == 64 and real_yunet["sha256"][:7] in GP.CACHE_KEYS["yunet"]
assert all(u.startswith("https://") for u in real_yunet["urls"])

def fake_dl(d):
    dl_calls.append(1)
    (d / "config.json").write_text('{"model_type": "siglip"}'); (d / "model.safetensors").write_bytes(b"w" * 1000); (d / "tokenizer.json").write_text("{}")
    (d / ".cache" / "huggingface" / "download").mkdir(parents=True, exist_ok=True)       # huggingface_hub's own bookkeeping is not a model file
    (d / ".cache" / "huggingface" / "download" / "config.json.metadata").write_text("c0ffee\netag\n")
dl_calls = []
sdest = SCRATCH / "m2"
ok, text = quiet(GP.get_siglip, sdest, fake_dl)
man = json.loads((sdest / "siglip2" / "MANIFEST.json").read_text())
whash = hashlib.sha256(b"w" * 1000).hexdigest()
assert ok and sorted(man["files"]) == ["config.json", "model.safetensors", "tokenizer.json"], man
assert man["files"]["model.safetensors"]["sha256"] == whash and man["commit"] == "c0ffee" and man["pinned"] == []
assert "UNPINNED model.safetensors sha256 " + whash in text                      # the log line to copy the pin from
ok, text = quiet(GP.get_siglip, sdest, fake_dl)
assert ok and len(dl_calls) == 1 and "cached" in text                            # a restored cache is verified, not downloaded again
(sdest / "siglip2" / "model.safetensors").write_bytes(b"tampered")              # an entry that changed since it was written
ok, text = quiet(GP.get_siglip, sdest, fake_dl)
assert ok and len(dl_calls) == 2 and (sdest / "siglip2" / "model.safetensors").read_bytes() == b"w" * 1000 and "differ from the manifest" in text
GP.SIGLIP = dict(real_siglip, pins={"model.safetensors": whash})                 # a pin that holds
ok, text = quiet(GP.get_siglip, SCRATCH / "m3", fake_dl)
assert ok and json.loads((SCRATCH / "m3" / "siglip2" / "MANIFEST.json").read_text())["pinned"] == ["model.safetensors"] and "UNPINNED model" not in text
GP.SIGLIP = dict(real_siglip, pins={"model.safetensors": "0" * 64})              # a pin that breaks: file deleted, no manifest, the model stays off
ok, text = quiet(GP.get_siglip, SCRATCH / "m4", fake_dl)
assert not ok and "breaks its pin" in text and "::warning::" in text
assert not (SCRATCH / "m4" / "siglip2" / "model.safetensors").exists() and not (SCRATCH / "m4" / "siglip2" / "MANIFEST.json").exists()
GP.SIGLIP = dict(real_siglip, pins={})                                           # cached before the pin existed, pinned later: caught
quiet(GP.get_siglip, SCRATCH / "m5", fake_dl)
GP.SIGLIP = dict(real_siglip, pins={"model.safetensors": "1" * 64})
ok, text = quiet(GP.get_siglip, SCRATCH / "m5", fake_dl)
assert not ok and not (SCRATCH / "m5" / "siglip2" / "MANIFEST.json").exists(), text
GP.SIGLIP = dict(real_siglip, pins={})
def partial(d): (d / "config.json").write_text("{}")
ok, text = quiet(GP.get_siglip, SCRATCH / "m6", partial); assert not ok and "missing" in text
def offline(d): raise OSError("offline")
ok, text = quiet(GP.get_siglip, SCRATCH / "m7", offline); assert not ok and "download failed" in text and "::warning::" in text
assert real_siglip["repo"] == "google/siglip2-base-patch16-224" and "*.safetensors" in real_siglip["patterns"] and "*.bin" not in real_siglip["patterns"]
real_argv, real_fy, real_fs = sys.argv, GP.get_yunet, GP.get_siglip                # main() never fails the job
sys.argv = ["get_pictures.py", str(SCRATCH / "m8")]
def boom(d): raise RuntimeError("boom")
GP.get_yunet, GP.get_siglip = boom, lambda d: False
_, text = quiet(GP.main)
assert '"yunet": false' in text and '"siglip2": false' in text and "::warning::yunet" in text, text
GP.get_yunet, GP.get_siglip, sys.argv = real_fy, real_fs, real_argv
GP.YUNET, GP.SIGLIP = real_yunet, real_siglip
print("1 pinned downloads ok")


# 2. faces.py: YuNet boxes ---------------------------------------------------------------------------------------------------
try: import cv2
except ImportError: cv2 = None
import faces as FC

class StubDet:
    """Stands in for cv2.FaceDetectorYN: rows are (x, y, w, h) in the picture it is given, as YuNet reports them."""
    def __init__(self, rows, fail=False): self.rows, self.fail, self.size = rows, fail, None
    def setInputSize(self, s): self.size = s
    def detect(self, im):
        if self.fail: raise RuntimeError("detector fell over")
        return 1, (np.array([list(r) + [0.0] * 10 + [0.9] for r in self.rows], dtype=np.float32) if self.rows else None)

if cv2 is None: print("2 faces skipped (no OpenCV here)")
else:
    big = np.zeros((720, 1280, 3), np.uint8)                       # shrunk to 640 x 360 for YuNet: boxes come back doubled
    det = StubDet([(100, 50, 80, 90), (400, 100, 40, 40), (600, 300, 100, 100), (-10, -5, 50, 50)])
    FC._STATE.clear(); FC._STATE.update(path="stand-in", det=det)
    got = FC.yunet_faces(big, 24)
    assert det.size == (640, 360), det.size
    assert got == [(200, 100, 160, 180), (1200, 600, 80, 120), (0, 0, 80, 90), (800, 200, 80, 80)], got   # scaled, cut to the picture, largest first
    assert FC.yunet_faces(big, 85) == [(200, 100, 160, 180)] and FC.yunet_faces(big, 80)[1] == (1200, 600, 80, 120)    # nothing narrower or shorter than min_px
    small = np.zeros((200, 300, 3), np.uint8)
    FC._STATE["det"] = det = StubDet([(10, 20, 100, 120)])
    assert FC.yunet_faces(small, 24) == [(10, 20, 100, 120)] and det.size == (300, 200)                      # a small picture is not scaled
    FC._STATE["det"] = StubDet([]); assert FC.yunet_faces(small, 24) == []                                    # looked, no face: [] and not None
    FC._STATE["det"] = None
    assert FC.yunet_faces(small, 24) is None and FC.engine() == "haar"                                       # not available: the caller runs Haar
    FC._STATE["det"] = StubDet([(1, 2, 3, 4)], fail=True)
    assert quiet(FC.yunet_faces, small, 24)[0] is None                                                       # a failure on one picture: Haar for it
    FC._STATE["det"] = StubDet([]); assert FC.engine() == "yunet"
    # the real model check: nothing there, the wrong file, the pinned file (a stand-in with patched pins)
    FC._STATE.clear()
    assert quiet(FC.model_path)[0] is None and FC.engine() == "haar"
    ydir = SCRATCH / "models" / "yunet"; ydir.mkdir(parents=True)
    GP.YUNET = dict(real_yunet, size=len(good), sha256=hashlib.sha256(good).hexdigest())
    (ydir / GP.YUNET["file"]).write_bytes(bad)
    FC._STATE.clear(); path, text = quiet(FC.model_path); assert path is None and "not the pinned file" in text
    (ydir / GP.YUNET["file"]).write_bytes(good)
    FC._STATE.clear(); path, text = quiet(FC.model_path); assert path == ydir / GP.YUNET["file"], text
    FC._STATE.pop("det", None)
    assert quiet(FC.detector)[0] is None and FC.engine() == "haar"                                          # the stand-in is not an ONNX file: Haar
    GP.YUNET = real_yunet; FC._STATE.clear()
    print("2 faces ok")


# 3. render3.face_focus and clips.face_box -------------------------------------------------------------------------------------
try: import render3 as R3, clips as C
except ImportError as e: R3 = C = None; print(f"(render3 and clips need more packages than this environment has: {e})")
if cv2 is None or R3 is None: print("3 face fallbacks skipped")
else:
    class HaarStub:
        made, args, found = [], None, [[100, 50, 60, 60]]
        def __init__(self, path): HaarStub.made.append(path)
        def detectMultiScale(self, grey, scale, neighbours, minSize=None):
            HaarStub.args = (scale, neighbours, minSize); return np.array(HaarStub.found)
    real_casc, real_data, real_faces = getattr(cv2, "CascadeClassifier", None), getattr(cv2, "data", None), FC.yunet_faces
    cv2.CascadeClassifier, cv2.data = HaarStub, types.SimpleNamespace(haarcascades="/nowhere/")      # OpenCV 5 ships no cascades
    photo = SCRATCH / "face.png"; Image.fromarray(np.full((300, 400, 3), 128, np.uint8)).save(photo)
    FC.yunet_faces = lambda img, minpx: [(10, 20, 100, 120), (300, 40, 50, 50)]
    assert R3.face_focus(photo) == (0.15, 0.267) and not HaarStub.made                             # YuNet's largest face; Haar not even built
    FC.yunet_faces = lambda img, minpx: None
    assert R3.face_focus(photo) == (0.325, 0.267) and HaarStub.args == (1.1, 5, (24, 24)), HaarStub.args   # no YuNet: the old call, unchanged
    HaarStub.made.clear()
    FC.yunet_faces = lambda img, minpx: []
    assert R3.face_focus(photo) is None and not HaarStub.made                                      # YuNet looked and found nobody: no second opinion
    FC.yunet_faces = lambda img, minpx: (_ for _ in ()).throw(RuntimeError("never raises into a render"))
    assert R3.face_focus(photo) is None

    C.WORK = SCRATCH / "work"; C.WORK.mkdir()
    seen, frames = [], [(np.arange(240 * 320 * 3).reshape(240, 320, 3) * (7 + k) % 251).astype(np.uint8) for k in range(4)]   # four unlike frames
    def fake_run(cmd, *a, **k):
        seen.append(cmd); Image.fromarray(frames[(len(seen) - 1) % 4]).save(cmd[-1], quality=95)
    real_sub, wanted = C.subprocess, []
    C.subprocess = types.SimpleNamespace(run=fake_run)
    def yunet_one(img, minpx): wanted.append(minpx); return [(100, 60, 80, 90)]
    FC.yunet_faces = yunet_one
    box, _ = quiet(C.face_box, SCRATCH / "clip.mp4", 0.0, 8.0)
    assert box == (0.3125, 0.25, 0.25, 0.375) and len(seen) == 4 and set(wanted) == {19}, (box, len(seen), wanted)   # 4 frames, min size 8% of the height
    seen.clear(); HaarStub.made.clear(); HaarStub.found = [[100, 60, 80, 90]]
    FC.yunet_faces = lambda img, minpx: None
    box, text = quiet(C.face_box, SCRATCH / "clip.mp4", 0.0, 8.0)
    assert box == (0.3125, 0.25, 0.25, 0.375) and len(HaarStub.made) == 1 and HaarStub.args == (1.2, 6, (19, 19)), (box, HaarStub.args)   # Haar built once, lazily
    assert "faces (haar)" in text
    frames[:] = [frames[0]] * 4; seen.clear()                                                      # a patch that never changes is a wall, not a person
    FC.yunet_faces = lambda img, minpx: [(100, 60, 80, 90)]
    assert quiet(C.face_box, SCRATCH / "clip.mp4", 0.0, 8.0)[0] is None
    C.subprocess = real_sub
    FC.yunet_faces = real_faces
    if real_casc is None: del cv2.CascadeClassifier
    else: cv2.CascadeClassifier = real_casc
    if real_data is not None: cv2.data = real_data
    print("3 face fallbacks ok")


# 4. pictures.py with a fake model ----------------------------------------------------------------------------------------------
import pictures as PX

AXES = ["steam", "deck", "handheld", "train", "locomotive", "logo", "map", "document", "screenshot", "blurry", "game", "cat"]
NOISE = 24
D = len(AXES) + NOISE + 1
PALETTE = {"deck": (200, 40, 40), "train": (40, 160, 60), "logo": (40, 60, 200), "map": (210, 200, 40), "document": (200, 200, 200), "cat": (150, 80, 200)}

def pic(concept, seed):
    """A 64 x 64 picture of a concept (its colour) with a blocky pattern of its own: the same seed is the same picture, another seed
    a different photo of it. Whole-number arithmetic only, so the pictures never change between numpy versions."""
    i, j = np.meshgrid(np.arange(8, dtype=np.int64), np.arange(8, dtype=np.int64), indexing="ij")
    cell = ((i * 73856093) ^ (j * 19349663) ^ (seed * 83492791 + 12345)) % 256
    big = np.kron(cell, np.ones((8, 8), dtype=np.int64)).astype(np.float32)
    arr = np.clip(np.array(PALETTE[concept], np.float32)[None, None, :] + (big[:, :, None] - 128.0) * 0.3, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))

class FakeModel:
    """Words are axes. A picture is its concept's axis plus a detail of its own (a second axis chosen by its pixels), so two
    photos of one thing are alike (cos 0.89) and a picture seen twice is identical (cos 1)."""
    name = "fake"; scale = 24.0; bias = -6.0; probe = None
    def __init__(self): self.n_images = self.n_texts = 0; self.boom = False
    def texts(self, texts):
        self.n_texts += len(texts); out = []
        for t in texts:
            v = np.zeros(D, np.float32)
            for w in re.findall(r"[a-z]+", t):
                if w in AXES: v[AXES.index(w)] += 1.0
            v[-1] = 0.05
            out.append(v / np.linalg.norm(v))
        return np.stack(out)
    def images(self, imgs):
        if self.boom: raise RuntimeError("model fell over")
        self.n_images += len(imgs); out = []
        for im in imgs:
            a = np.asarray(im.convert("RGB"), np.float32); mean = a.reshape(-1, 3).mean(axis=0)
            concept = min(PALETTE, key=lambda k: np.abs(np.array(PALETTE[k]) - mean).sum())
            v = np.zeros(D, np.float32); v[AXES.index(concept)] = 1.0
            v[len(AXES) + int(hashlib.md5(a.astype(np.uint8).tobytes()).hexdigest()[:8], 16) % NOISE] = 0.35
            v[-1] = 0.05
            out.append(v / np.linalg.norm(v))
        return np.stack(out)

def thumb_of(url):
    """https://thumb/<concept>-<seed> is a picture, anything else cannot be read."""
    m = re.match(r"https://thumb/(\w+)-(\d+)$", url or "")
    return pic(m.group(1), int(m.group(2))) if m else None

PX.fetch_thumb = thumb_of
fm = FakeModel()
E = fm.images([pic("deck", 3), pic("deck", 3), pic("deck", 4), pic("train", 1)])
assert float(E[0] @ E[1]) > 0.999 and float(E[0] @ E[2]) < PX.EMB_DUP and float(E[0] @ E[3]) < 0.1        # the fake behaves as described
assert PX.hamming(PX.ahash(pic("deck", 3)), PX.ahash(pic("deck", 4))) > PX.PH_DIST and PX.hamming(PX.phash(pic("deck", 3)), PX.phash(pic("deck", 4))) > PX.PH_DIST

# the beat's text
PX.reset(); PX.begin({"category": "Gaming", "meta": {"tags": ["Steam Deck"], "title": "Steam Deck news"}})
ctx = PX.context("Steam Deck handheld", "Free games to grab on the Steam Deck this week!", {"t": "Steam", "s": "platform"})
assert ctx["parts"] == [("a photo of steam deck handheld", 0.40), ("a photo of steam, platform", 0.15),
                        ("free games to grab on the steam deck this week", 0.25), ("a photo of steam deck, gaming", 0.20)], ctx["parts"]
assert ctx["junk"] == list(PX.JUNK) and ctx["name"] == "steam deck handheld"
assert "a logo" not in PX.context("Steam logo", "")["junk"] and "a map" not in PX.context("", "Where on the map is it?")["junk"]
assert len(PX.context("", "word " * 200)["parts"][0][0]) <= 240
PX.begin({"meta": {"title": "Katie Boulter wins at Wimbledon today in a thriller"}})
assert PX.context("")["parts"] == [("a photo of katie boulter wins at wimbledon today", 0.20)]            # no tags: the title's first six words
PX.begin({}); assert PX.context("", "", None) is None and PX.context("   ", None, {}) is None             # no text at all

# ranking
PX.reset(); model = FakeModel(); PX.use(model); PX._S["sha"] = "abcdef0123456789ffff"
PX.begin({"category": "Gaming", "meta": {"tags": ["Steam Deck"]}})
ctx = PX.context("Steam Deck handheld", "Free games to grab on the Steam Deck this week.", {"t": "Steam", "s": "platform"})
urls = ["https://thumb/train-1", "https://thumb/logo-2", "https://thumb/deck-3", "https://thumb/deck-3", "https://thumb/deck-4", "https://nowhere/x.jpg"]
out, text = quiet(PX.rank, urls, ctx)
assert [i for i, _ in out] == [2, 4, 0, 1, 5], out                       # the deck first; its copy (3) dropped; the unreadable one at the back
assert out[-1][1] is None and all(isinstance(inf, dict) for _, inf in out[:-1])
rel = {i: inf["rel"] for i, inf in out[:-1]}
assert rel[2] > 0.99 and rel[4] > 0.99 and rel[0] < 0.01 and rel[1] < 0.01, rel                         # the logo is marked down as well as off topic
assert out[0][1]["junk"] < 0.1 and 0.9 < [inf for i, inf in out if i == 1][0]["junk"] <= 1.0           # it looks like "a logo"
assert 'picked #3' in text and "1 near-duplicates dropped" in text, text
assert model.n_images == 4 and quiet(PX.rank, urls, ctx)[0] == out and model.n_images == 4            # 4 different pictures read once; seen again, not read again
n_text = model.n_texts; quiet(PX.rank, urls, ctx); assert model.n_texts == n_text                      # nor a prompt
PX.commit(out[0][1])                                                                                   # the deck was used: the next search puts it last
again, _ = quiet(PX.rank, urls, ctx)
assert [i for i, _ in again] == [4, 0, 1, 2, 5], again
PX.begin({"category": "Gaming", "meta": {"tags": ["Steam Deck"]}})                                    # a new Short forgets what was used
assert [i for i, _ in quiet(PX.rank, urls, ctx)[0]] == [2, 4, 0, 1, 5]
bonus, _ = quiet(PX.rank, urls, ctx, [0, 0, 0, 0, 0.3, 0])                                             # a small edge reorders near ties
assert [i for i, _ in bonus][:2] == [4, 2]
st = PX.summary()
assert st["pic_model"] == "siglip2-base-patch16-224:abcdef012345" and st["pic_secs"] >= 0, st
assert (st["pic_scored"], st["pic_searches"], st["pic_dups"], st["pic_reranked"]) == (10, 2, 2, 2), st      # since the new Short began: two searches, 5 pictures each
# the first 8 only
many = [f"https://thumb/cat-{k}" for k in range(10, 22)]
d0 = PX._S["stats"]["dups"]; out, _ = quiet(PX.rank, many, ctx)
kept = [i for i, inf in out if inf]
assert [i for i, _ in out][-4:] == [8, 9, 10, 11] and all(inf is None for _, inf in out[-4:]), out        # past the 8th: in the source's order, unscored
assert max(kept) < 8 and len(kept) + PX._S["stats"]["dups"] - d0 == 8                                    # the first 8 were scored: kept or dropped as copies
# nothing to rank, no model, over the time budget, and a model that fails
assert PX.rank([], ctx) is None and PX.rank(urls, None) is None and quiet(PX.rank, ["https://nowhere/a", None], ctx)[0] is None
PX.use(None)
assert quiet(PX.rank, urls, ctx)[0] is None and PX.summary()["pic_model"] == "off: switched off"
model = FakeModel(); PX.use(model); PX.begin({"meta": {"tags": ["Steam Deck"]}})
PX._S["deadline"] = time.time() - 1
res, text = quiet(PX.rank, urls, ctx); assert res is None and "ranking budget" in text and quiet(PX.rank, urls, ctx)[1] == ""     # said once
assert PX.score_file(SCRATCH / "x.png", ctx) is None
PX.begin({"meta": {"tags": ["Steam Deck"]}}); model.boom = True
for k in range(3):
    res, text = quiet(PX.rank, urls, ctx)
    assert res is None and "scoring failed" in text
assert PX._S["model"] is None and PX.why() == "three failures in a row" and not PX.available() and "ranking off for this Short" in text
PX.use(model); model.boom = False; assert quiet(PX.rank, urls, ctx)[0] is not None                      # one failure then success counts from zero again
model.boom = True; quiet(PX.rank, urls, ctx); model.boom = False; quiet(PX.rank, urls, ctx); model.boom = True; quiet(PX.rank, urls, ctx)
assert PX._S["model"] is model
# one downloaded still (a shot from an explicit source)
PX.use(FakeModel()); PX.begin({"meta": {"tags": ["Steam Deck"]}})
pic("deck", 3).save(SCRATCH / "deck.png"); pic("train", 1).save(SCRATCH / "train.png")
info = PX.score_file(SCRATCH / "deck.png", ctx)
assert info["rel"] > 0.99 and PX.score_file(SCRATCH / "train.png", ctx)["rel"] < 0.01
assert PX.score_file(SCRATCH / "clip.mp4", ctx) is None and PX.score_file(SCRATCH / "deck.png", None) is None and PX.score_file(SCRATCH / "none.png", ctx) is None
# hashes
sys.modules["imagehash"] = None                                                     # not installed: the average hash stands in
assert PX.phash(pic("deck", 3)) == PX.ahash(pic("deck", 3))
del sys.modules["imagehash"]
if importlib.util.find_spec("imagehash"):
    import imagehash
    assert PX.phash(pic("deck", 3)) == int(str(imagehash.phash(pic("deck", 3))), 16) < 2 ** 64
# the model class's own helpers
assert PX.Model._pooled(types.SimpleNamespace(pooler_output="p")) == "p" and PX.Model._pooled(("last", "p")) == "p" and PX.Model._pooled("tensor") == "tensor"
probe = PX.Model.__new__(PX.Model); probe.np = np
probe.texts = lambda texts: np.eye(4, dtype=np.float32)                              # the words red, green, blue, yellow are four distinct directions
def pictures_as(rows):                                                               # what the four colour pictures look like to the model
    m = np.array(rows, dtype=np.float32); m /= np.linalg.norm(m, axis=1, keepdims=True); probe.images = lambda imgs: m
pictures_as(np.eye(4)); assert probe._probe() == 4
pictures_as([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0.9, 0.1]]); assert probe._probe() == 3        # one colour read as another: still on
for rows, why_not in (([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0.1, 0.9], [0, 0, 0.9, 0.1]], "2 of 4"),
                      ([[0, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], "0 of 4")):
    pictures_as(rows)
    try: probe._probe(); raise AssertionError(f"{why_not} must fail the probe")
    except RuntimeError as e: assert f"colour probe {why_not}" in str(e), e
probe.texts = lambda texts: np.ones((4, 4), dtype=np.float32) / 2                    # four words that are all the same vector
pictures_as(np.eye(4))
try: probe._probe(); raise AssertionError("indistinct text vectors must fail")
except RuntimeError as e: assert "not distinct" in str(e)
probe.texts = lambda texts: np.full((4, 4), np.nan, dtype=np.float32)
try: probe._probe(); raise AssertionError("non-finite vectors must fail")
except RuntimeError as e: assert "not finite" in str(e)
# no model files: off, with the reason
PX.reset(); assert quiet(PX.available)[0] is False and "no model files in" in PX.why()
assert PX.summary()["pic_model"].startswith("off: FileNotFoundError") and quiet(PX.available)[0] is False
print("4 picture ranking ok")


# 5. fetch_media with the sources faked ----------------------------------------------------------------------------------------------
import fetch_media as FM

ALL = [("File:Steam Deck locomotive.jpg", "train", 1, 2000), ("File:Steam Deck logo.jpg", "logo", 2, 2000),
       ("File:Steam Deck handheld.jpg", "deck", 3, 1800), ("File:Steam Deck handheld 2.jpg", "deck", 3, 1700),      # the same picture twice
       ("File:Steam Deck OLED.jpg", "deck", 4, 1650)]
class J:
    def __init__(self, data=None, content=b""): self.data, self.content = data, content
    def json(self): return self.data
def png_bytes(im):
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
CALLS = []
def fake_api(url, **kw):
    params = kw.get("params") or {}; CALLS.append((url, dict(params)))
    if url == FM.COMMONS and "generator" in params:
        rows = ALL if params["gsrsearch"].startswith("Steam Deck ") else []
        pages = {str(i): {"title": t, "index": i + 1, "imageinfo": [{"width": w, "height": 900, "thumburl": f"https://thumb/{c}-{s}", "url": f"https://full/{c}-{s}.jpg"}]}
                 for i, (t, c, s, w) in enumerate(rows)}
        return J({"query": {"pages": pages}} if pages else {})
    if url == FM.COMMONS and "titles" in params:
        c, s = next((c, s) for t, c, s, w in ALL if t == params["titles"])
        return J({"query": {"pages": {"1": {"imageinfo": [{"thumburl": f"https://full/{c}-{s}.jpg", "url": f"https://full/{c}-{s}.jpg",
                  "descriptionurl": "https://commons.example/" + params["titles"].replace(" ", "_"),
                  "extmetadata": {"Artist": {"value": "Ann"}, "LicenseShortName": {"value": "CC BY 4.0"}}}]}}}})
    if url.startswith("https://thumb/"): return J(content=png_bytes(thumb_of(url)))
    if url == "https://pixabay.com/api/videos/":
        return J({"hits": [{"id": 1, "tags": "steam deck, console", "user": "ann", "pageURL": "https://pixabay.com/v/1", "duration": 9, "type": "film",
                            "videos": {"large": {"url": "https://vid/1.mp4", "width": 1920, "height": 1080, "thumbnail": "https://thumb/train-1"}}},
                           {"id": 2, "tags": "game, console", "user": "bob", "pageURL": "https://pixabay.com/v/2", "duration": 9, "type": "film",
                            "videos": {"large": {"url": "https://vid/2.mp4", "width": 1920, "height": 1080, "thumbnail": "https://thumb/deck-3"}}}]})
    if url == "https://pixabay.com/api/":
        return J({"hits": [{"id": 11, "tags": "steam deck", "user": "ann", "pageURL": "https://pixabay.com/p/11", "imageWidth": 1600, "imageHeight": 900,
                            "webformatURL": "https://thumb/train-1", "previewURL": "https://thumb/train-1", "largeImageURL": "https://img/11.jpg"},
                           {"id": 12, "tags": "console", "user": "bob", "pageURL": "https://pixabay.com/p/12", "imageWidth": 1600, "imageHeight": 900,
                            "webformatURL": "https://thumb/deck-3", "previewURL": "https://thumb/deck-3", "largeImageURL": "https://img/12.jpg"}]})
    if url == f"{FM.NASA}/search":
        return J({"collection": {"items": [
            {"data": [{"nasa_id": "a", "title": "Steam deck locomotive", "keywords": [], "center": "JSC"}], "href": "https://nasa.example/a/collection.json",
             "links": [{"rel": "preview", "href": "https://thumb/train-1"}]},
            {"data": [{"nasa_id": "b", "title": "Steam deck console", "keywords": [], "center": "JSC"}], "href": "https://nasa.example/b/collection.json",
             "links": [{"rel": "preview", "href": "https://thumb/deck-3"}]}]}})
    if url.startswith("https://nasa.example/"): return J([f"http://images.example/{url.split('/')[-2]}~large.jpg"])
    if url == "https://api.openverse.org/v1/images/":
        return J({"results": [dict(id="o1", title="Steam Deck on a train", tags=[], width=2000, thumbnail="https://thumb/train-1", url="https://ov/1.jpg", license="by",
                                   license_version="4.0", creator="Cy", source="flickr", foreign_landing_url="https://flickr.example/1"),
                              dict(id="o2", title="Steam Deck in hands", tags=[], width=2000, thumbnail="https://thumb/deck-3", url="https://ov/2.jpg", license="by",
                                   license_version="4.0", creator="Di", source="flickr", foreign_landing_url="https://flickr.example/2")]})
    raise AssertionError(f"unexpected request {url} {params}")
DOWNLOADS = []
def fake_download(url, d, stem):
    DOWNLOADS.append(url)
    m = re.match(r"https://full/(\w+)-(\d+)\.jpg$", url)
    p = d / f"{stem}.png"; pic(m.group(1), int(m.group(2))).save(p) if m else pic("cat", 9).save(p); return p
real = (FM.HERE, FM._get, FM.download, FM.rescue_cfg)
FM.HERE = SCRATCH / "fm"; (FM.HERE / "media").mkdir(parents=True); FM._get, FM.download = fake_api, fake_download
FM.rescue_cfg = lambda: dict(FM.RESCUE, on=False)          # the subject rescue has its own test (tests/test_pictures_rescue.py)
os.environ["PIXABAY_API_KEY"] = "test"

assert FM._words("pixabay", "video:crowd cheering") == "crowd cheering" and FM._words("nasa", "image:Apollo 11") == "Apollo 11"
assert FM._words("commons", "File:Katie_Boulter_2023.jpg") == "Katie Boulter 2023" and FM._words("commons-search", "Katie Boulter") == "Katie Boulter"
assert FM._words("url", "https://x/y.jpg") == "" == FM._words("page", "https://x") and FM._words("gameplay", "parkour") == "parkour"

def board():
    return {"id": "TEST-PX", "category": "Gaming", "meta": {"title": "Steam Deck news", "tags": ["Steam Deck"]},
            "beats": [{"say": "The Steam Deck is a handheld game console.", "shots": [{"src": "commons-search:Steam Deck", "label": {"t": "Steam Deck", "s": "handheld"}}]},
                      {"say": "Nobody photographed this one.", "shots": [{"src": "commons-search:Nothing Here"}]},
                      {"say": "Here is the same console again.", "shots": [{"src": "commons:File:Steam Deck handheld.jpg"}]},
                      {"say": "Follow for more.", "visual": {"type": "none"}}]}
def fresh(model):
    FM._CANDS.clear(); FM._RANKED.clear(); FM.PICK.clear(); DOWNLOADS.clear(); CALLS.clear(); PX.reset()
    if model: PX.use(model)
    else: PX.use(None)
FIRST_COMMONS = lambda: next(p for u, p in CALLS if u == FM.COMMONS and "generator" in p)

# the model on: the search's first hit (a locomotive) is not the one taken
fresh(FakeModel()); sb, text = quiet(FM.resolve, board())
s0, s1, s2 = (sb["beats"][i]["shots"][0] for i in range(3))
assert DOWNLOADS[0] == "https://full/deck-3.jpg", DOWNLOADS                                       # the handheld, not the locomotive or the logo
assert s0["relevance"] > 0.99 and s0["from"] == "commons-search:Steam Deck" and s0["credit"].startswith("Photo: Ann, CC BY 4.0")
assert FIRST_COMMONS()["iiprop"] == "size|url" and FIRST_COMMONS()["iiurlwidth"] == 330           # the search asks for the thumbnails it ranks by
assert "relevance" not in s1 and s1["src"] == s0["src"] and sb["_media_notes"][0].startswith("beat 2 reused a nearby picture")   # a beat with no photo borrows one, not its score
assert DOWNLOADS[1] == "https://full/deck-3.jpg" and s2["relevance"] > 0.99 and s2["src"] != s0["src"]    # an explicit file is scored too (and is its own download)
assert sb["_pic_found"] == [2, 3]
assert [p["title"] for p in FM._CANDS["Steam Deck"]] == ["File:Steam Deck handheld.jpg", "File:Steam Deck OLED.jpg", "File:Steam Deck locomotive.jpg", "File:Steam Deck logo.jpg"]
info = FM.pictures_summary(sb)
assert "_pic_found" not in sb and info["pic_found_share"] == 0.67 and info["pic_relevance"] == round((s0["relevance"] + s2["relevance"]) / 2, 3), info
assert info["pic_model"] == "siglip2-base-patch16-224" and info["pic_scored"] >= 6 and info["pic_searches"] == 1 and info["pic_reranked"] == 1 and info["pic_dups"] == 1, info
# its more photos of the subject: the ranked list, each with its own relevance
added, _ = quiet(FM.extras, sb); ex = [s for s in sb["beats"][0]["shots"] if s.get("extra")]
assert len(ex) == 2 and [e["credit"].startswith("Photo: Ann") for e in ex] == [True, True] and ex[0]["relevance"] > 0.99 and ex[1]["relevance"] < 0.01, ex
assert added == 3 and sb["beats"][1]["shots"][-1]["extra"]                       # the borrowed picture's beat gets the last of the ranked list too
vals = [x["relevance"] for b in sb["beats"] for x in b.get("shots", []) if "relevance" in x]
assert len(vals) == 5 and FM.pictures_summary(sb)["pic_relevance"] == round(sum(vals) / 5, 3)      # the extras count in the Short's mean
# the model off: the search's own order, as it always was
fresh(None); sb, _ = quiet(FM.resolve, board()); s0 = sb["beats"][0]["shots"][0]
assert DOWNLOADS[0] == "https://full/train-1.jpg" and "relevance" not in s0 and sb["_pic_found"] == [2, 3], DOWNLOADS
info = FM.pictures_summary(sb)
assert info["pic_found_share"] == 0.67 and "pic_relevance" not in info and info["pic_model"].startswith("off"), info
# the other sources (the ranker's log lines go to stderr: kept out of the test's output)
hush = contextlib.redirect_stderr(io.StringIO()); hush.__enter__()
fresh(FakeModel()); PX.begin(board()); FM.PICK["ctx"] =PX.context("steam deck", "The Steam Deck is a handheld game console.", None)
used = set(); url, credit, page = FM.pixabay("video", "steam deck", used)
assert url == "https://vid/2.mp4" and used == {2} and credit == "Video: bob / Pixabay" and FM.PICK["info"]["rel"] > 0.99      # tags favour the locomotive clip; the picture does not
used = set(); url, credit, page = FM.pixabay("image", "steam deck", used)
assert url == "https://img/12.jpg" and used == {12} and FM.PICK["info"]["rel"] > 0.99
FM.PICK.pop("info"); used = set(); url, credit, page = FM.nasa("image", "steam deck", used)
assert url == "https://images.example/b~large.jpg" and used == {"b"} and FM.PICK["info"]["rel"] > 0.99
FM.PICK.pop("info"); used = set(); url, credit, page = FM.openverse("Steam Deck", used)
assert url == "https://ov/2.jpg" and used == {"o2"} and FM.PICK["info"]["rel"] > 0.99 and credit.startswith("Photo: Di")
fresh(None); FM.PICK["ctx"] = {"parts": [("a photo of steam deck", 1.0)], "junk": [], "name": "x"}
assert FM.pixabay("video", "steam deck", set())[0] == "https://vid/1.mp4" and FM.pixabay("image", "steam deck", set())[0] == "https://img/11.jpg"
assert FM.nasa("image", "steam deck", set())[0] == "https://images.example/a~large.jpg" and FM.openverse("Steam Deck", set())[0] == "https://ov/1.jpg"
assert FM.PICK.get("info") is None
FM.PICK.clear(); assert FM._ranked([1, 2], ["a", "b"]) is None                                   # no beat text: nothing to rank by
hush.__exit__(None, None, None)
FM.HERE, FM._get, FM.download, FM.rescue_cfg = real
print("5 fetch_media ok")


# 6. analytics ---------------------------------------------------------------------------------------------------------------------
sys.argv = ["analytics.py", "--fast"]
import analytics as AN
assert AN.PIC_COLUMNS == ("pic_relevance", "pic_found_share", "pic_low_share", "pic_rescued")
assert AN.pic_fields({}) == {"pic_relevance": "", "pic_found_share": "", "pic_low_share": "", "pic_rescued": ""} == AN.pic_fields({"media": "x"})
assert AN.pic_fields({"media": {"real_shots": 3, "pic_relevance": 0.81, "pic_found_share": 0.75}}) == {"pic_relevance": 0.81, "pic_found_share": 0.75, "pic_low_share": "", "pic_rescued": ""}
root = SCRATCH / "an"; (root / "boards" / "done").mkdir(parents=True); (root / "status").mkdir(); (root / "analytics").mkdir()
for sid, vid, media in (("T1", "vid1", {"real_shots": 1, "planned_real": 1, "pic_relevance": 0.812, "pic_found_share": 1.0}), ("T0", "vid0", {"real_shots": 1})):
    (root / "boards" / "done" / f"{sid}.json").write_text(json.dumps({"id": sid, "category": "Gaming", "meta": {"title": "t"}, "beats": [{"say": "Hook words", "shots": [{}]}]}))
    (root / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "video": vid, "media": media}))
real_root, real_out = AN.ROOT, AN.OUT
AN.ROOT, AN.OUT = root, root / "analytics"
try: ours = AN.our_shorts()
finally: AN.ROOT, AN.OUT = real_root, real_out
assert (ours["vid1"]["pic_relevance"], ours["vid1"]["pic_found_share"]) == (0.812, 1.0) and ours["vid1"]["real_share"] == 1.0
assert (ours["vid0"]["pic_relevance"], ours["vid0"]["pic_found_share"]) == ("", "")                    # rendered before the ranker: blank, not 0
assert "row.update({k: o.get(k, \"\") for k in PIC_COLUMNS})" in inspect.getsource(AN.main)              # and they reach the row in shorts.csv
src = (REPO / "pipeline" / "run_board.py").read_text()
assert "status[\"media\"].update(fetch_media.pictures_summary(sb))" in src and "fetch_media.PX.unload()" in src
assert src.index("fetch_media.extras(sb)") < src.index("pictures_summary(sb)") < src.index("sb[\"voice_dir\"]")     # after the extras, before the resolved board is written
print("6 analytics ok")


# 7. the workflows ---------------------------------------------------------------------------------------------------------------
render_yml, clips_yml = [(REPO / ".github" / "workflows" / n).read_text() for n in ("render.yml", "clips.yml")]
KEYS = GP.CACHE_KEYS
assert KEYS["yunet"] in render_yml and KEYS["siglip2"] in render_yml and KEYS["yunet"] in clips_yml and KEYS["siglip2"] not in clips_yml
assert "python pipeline/get_pictures.py models\n" in render_yml and "python pipeline/get_pictures.py models --only yunet" in clips_yml
for text, key, probe_file in ((render_yml, KEYS["siglip2"], "models/siglip2/MANIFEST.json"), (render_yml, KEYS["yunet"], "models/yunet/" + GP.YUNET["file"]),
                              (clips_yml, KEYS["yunet"], "models/yunet/" + GP.YUNET["file"])):
    saves = [blk.split("\n      - ")[0] for blk in text.split("- uses: actions/cache/save@v4")[1:] if f"key: {key}" in blk.split("\n      - ")[0]]
    assert saves and f"hashFiles('{probe_file}') != ''" in saves[0] and "cache-hit != 'true'" in saves[0], (key, saves)          # saved only when complete
    assert "actions/cache/restore@v4" in text and f"path: {probe_file.rsplit('/', 1)[0]}, key: {key}" in text
line = next(l for l in render_yml.splitlines() if "imagehash==4.3.2" in l and "pip install" in l)
assert "pip==26.2.1" in line and "--uploaded-prior-to P7D imagehash==4.3.2" in line and "|| echo" in line, line      # pinned, aged, and optional
print("7 workflows ok")


# 8. light imports ---------------------------------------------------------------------------------------------------------------
code = ("import sys\nfor m in ('torch', 'transformers', 'cv2', 'imagehash', 'requests', 'PIL', 'numpy'): sys.modules[m] = None\n"
        "sys.path.insert(0, 'pipeline')\nimport pictures, get_pictures, faces\nprint('light imports ok')")
r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=REPO_DIR)
assert r.returncode == 0 and "light imports ok" in r.stdout, r.stderr[-400:]
print("8 light imports ok")


# 9. the real model code on a tiny random SigLIP checkpoint (only where torch and transformers are installed) ------------------------------
if not (importlib.util.find_spec("torch") and importlib.util.find_spec("transformers") and importlib.util.find_spec("tokenizers")):
    print("9 real model code skipped (torch or transformers not installed here)")
else:
    import torch
    from tokenizers import Tokenizer, models as tkm, pre_tokenizers
    from transformers import PreTrainedTokenizerFast, SiglipConfig, SiglipImageProcessor, SiglipModel
    models = SCRATCH / "real"; d = models / "siglip2"; d.mkdir(parents=True)
    vocab = {"<pad>": 0, "<unk>": 1}
    for w in "a photo of steam deck handheld train logo red green blue yellow picture the".split(): vocab.setdefault(w, len(vocab))
    for k in range(len(vocab), 500): vocab[f"w{k}"] = k
    tk = Tokenizer(tkm.WordLevel(vocab, unk_token="<unk>")); tk.pre_tokenizer = pre_tokenizers.Whitespace()
    PreTrainedTokenizerFast(tokenizer_object=tk, pad_token="<pad>", unk_token="<unk>", model_max_length=64).save_pretrained(d)
    cfg = SiglipConfig(text_config=dict(vocab_size=500, hidden_size=32, intermediate_size=64, num_hidden_layers=1, num_attention_heads=2,
                                        max_position_embeddings=64, projection_size=32),
                       vision_config=dict(hidden_size=32, intermediate_size=64, num_hidden_layers=1, num_attention_heads=2, image_size=224, patch_size=16))
    torch.manual_seed(0); sm = SiglipModel(cfg).eval()
    with torch.no_grad(): sm.logit_scale.fill_(4.7); sm.logit_bias.fill_(-16.0)
    sm.save_pretrained(d); SiglipImageProcessor(size={"height": 224, "width": 224}).save_pretrained(d)
    files = {f.name: {"size": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()} for f in d.iterdir() if f.is_file()}
    (d / "MANIFEST.json").write_text(json.dumps({"model": "tiny", "files": files}))
    os.environ["QP_MODELS"] = str(models)
    PX.reset(); PX.fetch_thumb = thumb_of
    res, text = quiet(PX.available); assert res is False and "colour probe" in PX.why(), (PX.why(), text)       # random weights cannot read colours: the probe keeps it off
    PX.reset(); PX.Model.check = False
    try:
        res, text = quiet(PX.available); assert res is True, (PX.why(), text)
        m = PX._S["model"]
        E = m.images([pic("deck", 3), pic("train", 1)]); T = m.texts(["a photo of steam deck", "a logo"])
        assert E.shape == (2, 32) and T.shape == (2, 32) and np.allclose(np.linalg.norm(E, axis=1), 1, atol=1e-4) and np.isfinite(T).all()
        assert m.scale > 100 and m.bias == -16.0                                    # logit_scale.exp() and logit_bias, the checkpoint's own
        PX.begin({"meta": {"tags": ["Steam Deck"]}}); ctx = PX.context("steam deck", "a handheld", None)
        out, _ = quiet(PX.rank, urls, ctx)
        idx = [i for i, _ in out]          # random weights make every picture look alike, so the vector check may drop more than the copy
        assert idx[-1] == 5 and out[-1][1] is None and 3 not in idx and len(set(idx)) == len(idx) and set(idx) <= {0, 1, 2, 4, 5}, out
        assert all(0.0 <= inf["rel"] <= 1.0 and isinstance(inf["hash"], int) for _, inf in out if inf), out
    finally: PX.Model.check = True; PX.reset()
    print("9 real model code ok")
print("pictures ok")
