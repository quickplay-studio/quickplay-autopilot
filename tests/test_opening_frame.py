"""Offline test of the opening-frame scorecard (24 October; pipeline/opening_frame.py): the first 1.5 seconds of a render read
back as five numbers, kept in status qa.opening and in shorts.csv (open_*) for drivers.py to test the first_frame arms against.
1. the numbers on synthetic Pillow frames: sharpness (blur lowers it, a flat frame is 0), contrast, the largest face's share of
   the frame (a stand-in detector, and OpenCV's real one when it is here), the share covered by text with overlaps counted once
   (a stand-in detector, and RapidOCR's real one when it is installed), and the caption's contrast against its band (dark,
   middle, bright, no caption, and captions moved to the top);
2. scorecard(): the averages and per-frame values from injected frames; a detector that fails or is missing leaves its one number
   None and the others standing; an unreadable video gives an error dict; it never raises;
3. a real ffmpeg grab of a synthetic video (when ffmpeg is here): 4 frames at 0, 0.4, 0.8 and 1.2 seconds, in order;
4. run_board.record_opening keeps the scorecard in status qa.opening and swallows any failure (it can never fail a render);
5. analytics: the scores reach each Short's shorts.csv row under the open_* names ("" where a number was not read)."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, importlib.util, io, json, os, shutil, subprocess, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import opening_frame as OF
W, H = OF.W, OF.H
assert (W, H) == (1080, 1920) and OF.WINDOW == 1.5 and OF.RATE == 2.5     # 4 frames: 0, 0.4, 0.8, 1.2 seconds


def photo(seed=1, level=90):
    """A photo-like frame: smooth colour gradients with fine noise; no pixel is near white."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.stack([level + 60 * xx / W, level + 40 * yy / H, level + 30 * np.sin(xx / 70.0)], axis=2) + rng.normal(0, 8, (H, W, 3))
    return np.clip(img, 0, 255).astype(np.uint8)


def font(size):
    try: return ImageFont.load_default(size)         # Pillow 10.1 and later: a scalable font that comes with it
    except Exception: return ImageFont.load_default()


def with_caption(frame, top, text="the moon always shows", size=46):
    im = Image.fromarray(frame.copy())
    ImageDraw.Draw(im).text((110, top + 30), text, font=font(size), fill=(245, 248, 250))
    return np.asarray(im)


def captioned(level, band=(1385, 1507), **kw):
    """A frame whose caption band is a flat grey `level` with the caption's near-white words on it."""
    f = photo(); f[band[0]:band[1], :, :] = level
    return with_caption(f, band[0], **kw)


g = lambda rgb: OF.grey(OF.half(rgb))

# 1. the numbers ------------------------------------------------------------------------------------------------------------
flat = np.full((H, W, 3), 128, np.uint8)
assert OF.half(flat).shape == (960, 540, 3) and abs(float(OF.half(photo()).mean()) - float(photo().mean())) < 1
checks = np.kron((np.indices((120, 68)).sum(axis=0) % 2) * 255, np.ones((16, 16))).astype(np.uint8)[:H, :W]      # 16 px squares
sharp = np.stack([checks] * 3, axis=2)
soft = np.asarray(Image.fromarray(sharp).filter(ImageFilter.GaussianBlur(10)))
s_flat, s_sharp, s_soft = OF.sharpness(g(flat)), OF.sharpness(g(sharp)), OF.sharpness(g(soft))
assert s_flat == 0 and s_sharp > 20 * max(s_soft, 1) > 0, (s_flat, s_sharp, s_soft)               # blur takes the edges away
assert OF.contrast(g(flat)) == 0
halves = np.zeros((H, W, 3), np.uint8); halves[H // 2:] = 255
assert abs(OF.contrast(g(halves)) - 0.5) < 0.01 and 0 < OF.contrast(g(photo())) < 0.2
print("1a sharpness and contrast ok", round(s_sharp), round(s_soft, 1))

g8 = np.clip(g(photo()), 0, 255).astype(np.uint8)
area = g8.shape[0] * g8.shape[1]
assert OF.face_share(g8, lambda im: []) == 0.0 and OF.face_share(g8, lambda im: np.zeros((0, 4))) == 0.0
assert abs(OF.face_share(g8, lambda im: [(10, 10, 100, 100), (50, 50, 200, 100)]) - 20000 / area) < 1e-9      # the largest face counts
assert OF.face_share(g8, lambda im: [(0, 0, 9999, 9999)]) == 1.0
det, note = OF.haar_faces()
if det is None: assert note.startswith("off:"), note                      # this OpenCV has no cascade file: the number is None, not an error
else: assert note == "haar" and 0.0 <= OF.face_share(g8, det) <= 1.0
print("1b faces ok:", note)

box = lambda x0, y0, x1, y1: np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float32)
hr = OF.half(photo())
two = lambda im: [box(0, 0, 270, 480), box(135, 240, 405, 720)]           # two boxes overlapping by a quarter of each
assert abs(OF.text_share(hr, two) - (2 * 270 * 480 - 135 * 240) / (540 * 960)) < 0.01, OF.text_share(hr, two)       # the overlap counts once
assert OF.text_share(hr, lambda im: []) == 0.0
ocr, ocr_note = OF.rapidocr_text()
if ocr is None: assert ocr_note.startswith("off:"), ocr_note              # RapidOCR is an optional extra: without it the number is None
else:
    page = Image.fromarray(np.full((H // 2, W // 2, 3), 235, np.uint8)); ImageDraw.Draw(page).text((40, 300), "TOP 10 SONGS", font=font(60), fill=(20, 20, 20))
    assert ocr_note.startswith("rapidocr ") and OF.text_share(np.asarray(page), ocr) > 0.003      # its real detector finds a big title
    assert OF.text_share(np.full((H // 2, W // 2, 3), 235, np.uint8), ocr) == 0.0                  # and nothing on a blank frame
print("1c text ok:", ocr_note)

low = OF.caption_band("low")
assert low == (1385, 1507) and OF.caption_band("clean") == (1270, 1500) and OF.caption_band("nonesuch") == (1290, 1500)
assert OF.caption_band("lab", {"top": "1290px"}) == (1290, 1520) and OF.caption_band("lab", {"top": "bad"}) == (1290, 1520)
dark, mid, bright, white = (OF.caption_contrast(captioned(v), low) for v in (20, 128, 170, 235))
assert dark >= 7 and 2.5 < mid < 6 and bright < 3 and white == 1.0, (dark, mid, bright, white)      # darker behind the words reads better
assert dark > mid > bright >= white and 1.0 <= dark <= 21
assert OF.caption_contrast(photo(), low) is None                         # no caption text in the band
assert OF.caption_contrast(captioned(235), low, strict=True) is None     # near white all over: nothing to measure when asked to be strict
top_frame = with_caption(photo(), 400)                                   # a person low in the picture: the captions sit at the top
assert OF.caption_contrast(top_frame, low) is None
got = OF.frame_caption(top_frame, "low")
assert got is not None and got == OF.caption_contrast(top_frame, (400, 400 + 122), strict=True) and got > 2
assert OF.frame_caption(captioned(20), "low") == dark and OF.frame_caption(photo(), "low") is None
print("1d captions ok", round(dark, 1), round(mid, 1), round(bright, 1), white)

# 2. scorecard() ------------------------------------------------------------------------------------------------------------
frames = np.stack([captioned(20), captioned(20), captioned(128), photo()])
seen = []
def faces(im):
    seen.append(im.shape)
    return [(0, 0, 54, 96)] if len(seen) == 3 else []                    # a face in the third frame only: 54 x 96 of 540 x 960 = 1%
text = lambda im: [box(0, 0, 540, 96)]                                   # a tenth of every frame
card = OF.scorecard("unused.mp4", "low", {}, frames=frames, faces=faces, text=text)
print(json.dumps({k: v for k, v in card.items() if k != "by_frame"}))
assert card["frames"] == 4 and card["t"] == [0.0, 0.4, 0.8, 1.2] and seen == [(960, 540)] * 4
assert abs(card["face_area"] - 0.0025) < 1e-4 and abs(card["text_area"] - 0.1) < 0.01 and card["by_frame"]["face_area"][2] == 0.01
per = card["by_frame"]["caption_contrast"]
assert per[0] == per[1] == round(dark, 2) and per[2] == round(mid, 2) and per[3] is None          # no caption in the last frame
assert card["caption_contrast"] == per[0] == round(sorted([dark, dark, mid])[1], 2)                  # the median of the frames that had one
assert card["sharpness"] > 0 and 0 < card["contrast"] < 0.5 and set(card["by_frame"]) == {"sharpness", "contrast", "face_area", "text_area", "caption_contrast"}
assert all(len(v) == 4 for v in card["by_frame"].values()) and len(json.dumps(card)) < 1500           # small enough for every status file
assert json.loads(json.dumps(card)) == card                                                            # plain numbers: it serialises as it is

off = OF.scorecard("unused.mp4", "low", {}, frames=frames, faces=lambda im: [], text=None)             # no OCR: text_area is None, the rest stands
assert off["text_area"] is None and off["ocr"] == "off" and off["face_area"] == 0.0 and off["caption_contrast"] == card["caption_contrast"]
def boom(im): raise RuntimeError("detector broke")
with contextlib.redirect_stdout(io.StringIO()) as log:
    broke = OF.scorecard("unused.mp4", "low", {}, frames=frames, faces=boom, text=boom)               # both detectors fail on every frame
assert broke["face_area"] is None and broke["text_area"] is None and broke["sharpness"] == card["sharpness"] and "skipped" in log.getvalue()
assert OF.scorecard("unused.mp4", "low", {}, frames=np.zeros((0, H, W, 3), np.uint8)) == {"error": "frames: RuntimeError: no frames"}
bad = OF.scorecard(str(SCRATCH / "missing.mp4"), "low")                                                 # a video that is not there
assert list(bad) == ["error"] and bad["error"].startswith("frames: "), bad
with contextlib.redirect_stdout(io.StringIO()):
    odd = OF.scorecard("unused.mp4", "low", frames=np.zeros((2, 10, 10, 3), np.uint8), faces=None, text=None)   # frames of the wrong size: every number None
assert odd["sharpness"] is None and odd["caption_contrast"] is None and odd["frames"] == 2
print("2 scorecard ok")

# 3. a real ffmpeg grab -----------------------------------------------------------------------------------------------------
if shutil.which("ffmpeg"):
    mp4 = SCRATCH / "segments.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "270x480", "-r", "25", "-i", "-",
                          "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16", "-pix_fmt", "yuv420p", str(mp4)], stdin=subprocess.PIPE)
    for colour in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)):
        for _ in range(10): p.stdin.write(np.full((480, 270, 3), colour, np.uint8).tobytes())          # 10 frames of 25 a second: 0.4 s each
    p.stdin.close(); p.wait()
    got = OF.grab_frames(mp4)
    assert got.shape == (4, H, W, 3), got.shape                          # scaled to the Short's size, however big the video was
    for k, want in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255))):
        mean = got[k].reshape(-1, 3).mean(axis=0)
        assert np.abs(mean - np.array(want)).max() < 45, (k, mean)         # frame k is the k-th 0.4 s of the video: 0, 0.4, 0.8, 1.2 s
    live = OF.scorecard(mp4, "low", {}, faces=None, text=None)
    assert live["frames"] == 4 and live["t"] == [0.0, 0.4, 0.8, 1.2] and live["sharpness"] < 5 and live["contrast"] < 0.02 and live["caption_contrast"] in (None, 1.0), live
    print("3 ffmpeg grab ok")
else: print("3 skipped (no ffmpeg here)")

# 4. run_board keeps it, and never fails a render over it ---------------------------------------------------------------------
import run_board as RB
asked = []
class FakeOF:
    @staticmethod
    def scorecard(mp4, captions="", cap=None, **kw): asked.append((str(mp4), captions, cap)); return {"sharpness": 41.5, "contrast": 0.2, "face_area": 0.05, "text_area": None, "caption_contrast": 6.1, "ocr": "off"}
real_of = sys.modules["opening_frame"]
sys.modules["opening_frame"] = FakeOF
look = {"render": {"captions": "low", "cap": {"top": "1290px"}}}
status = {"qa": {"duration": 30.2}}
with contextlib.redirect_stdout(io.StringIO()) as log: RB.record_opening(status, SCRATCH / "x.mp4", look)
assert status["qa"]["opening"]["caption_contrast"] == 6.1 and status["qa"]["duration"] == 30.2 and asked == [(str(SCRATCH / "x.mp4"), "low", {"top": "1290px"})]
assert "opening scorecard:" in log.getvalue()
FakeOF.scorecard = staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("scorecard broke")))
status2 = {"qa": {"duration": 30.2}}
with contextlib.redirect_stdout(io.StringIO()) as log: RB.record_opening(status2, SCRATCH / "x.mp4", look)
assert status2 == {"qa": {"duration": 30.2}} and "skipped" in log.getvalue()                       # nothing recorded, nothing raised
with contextlib.redirect_stdout(io.StringIO()): RB.record_opening({}, SCRATCH / "x.mp4", look)         # a status with no qa yet: still no error
sys.modules["opening_frame"] = real_of
src = open("pipeline/run_board.py").read()
call = src.index("\n        record_opening(status, mp4, look)")                  # the call, not the def
assert src.index('status["qa"] = {') < call < src.index("problems = []")        # read once qa exists and before the checks, which never look at it
assert "raise RuntimeError(\"checks failed" in src and "opening" not in src.split("problems = []")[1].split("if problems")[0]
print("4 run_board ok")

# 5. analytics: shorts.csv ------------------------------------------------------------------------------------------------------
import analytics as A
A.ROOT = SCRATCH / "an"; (A.ROOT / "status").mkdir(parents=True); (A.ROOT / "boards" / "done").mkdir(parents=True)
for sid, vid, st in (("QD-980", "vid980", {"qa": {"duration": 31.2, "opening": card}}),
                     ("QD-981", "vid981", {"qa": {"duration": 29.0, "opening": off}}),            # OCR off: the text number is None
                     ("QD-982", "vid982", {"qa": {"duration": 30.0}}),                            # from before the scorecard
                     ("QD-983", "vid983", {"qa": {"duration": 30.0, "opening": {"error": "frames: x"}}})):
    (A.ROOT / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "video": vid, **st}))
ours = A.our_shorts()
assert A.OPENING_COLUMNS == {"open_sharp": "sharpness", "open_contrast": "contrast", "open_face": "face_area", "open_text": "text_area",
                             "open_caption": "caption_contrast"}
assert set(A.OPENING_COLUMNS.values()) <= set(card), "analytics asks for a number the scorecard does not give"
assert [ours["vid980"][c] for c in A.OPENING_COLUMNS] == [card["sharpness"], card["contrast"], card["face_area"], card["text_area"], card["caption_contrast"]]
assert ours["vid981"]["open_text"] == "" and ours["vid981"]["open_caption"] == card["caption_contrast"]         # None becomes a blank cell
assert all(ours["vid982"][c] == "" and ours["vid983"][c] == "" for c in A.OPENING_COLUMNS)
assert ours["vid980"]["seconds"] == 31.2                                 # the duration still comes through beside them
src = open("pipeline/analytics.py").read()
assert '"writer_arm_used") + ARM_COLUMNS + tuple(OPENING_COLUMNS)' in src          # the shorts.csv row takes them, after the arms' columns
print("5 analytics ok")
print("opening frame ok")
