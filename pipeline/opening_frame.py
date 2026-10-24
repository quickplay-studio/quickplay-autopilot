"""The opening-frame scorecard (24 October): the first 1.5 seconds of a finished Short, read back as five numbers.

The leak is the first swipe (analytics/shorts.csv on 24 October: only 31.5% of views stayed past the first seconds, 88
Shorts), so the opening picture is where a Short is won or lost. run_board.py grabs 4 frames of the rendered video (0,
0.4, 0.8 and 1.2 seconds), scores each, and keeps the averages in status/<id>.json qa.opening. analytics.py copies them into shorts.csv
(the open_* columns) so drivers.py can test the first_frame arms ("cover", "photo", later "face" and "scored") against them.
A note, never a check: scorecard() cannot raise, and a number it cannot work out is None, not a failed render.

  sharpness         variance of the Laplacian of the grey frame at 540x960; higher is sharper, 0 is a flat frame
  contrast          RMS contrast: the spread of the grey levels as a share of the full range, 0 to 0.5 (a busy photo 0.2 to 0.3)
  face_area         share of the frame the largest face covers (OpenCV's frontal Haar cascade, as render3.face_focus reads a
                    picture); 0 when it finds none, None when OpenCV or its cascade file is missing
  text_area         share of the frame covered by text boxes (RapidOCR's detector), overlaps counted once; None when RapidOCR
                    is not installed (render.yml installs it as an optional extra)
  caption_contrast  WCAG contrast ratio (1 to 21) of the caption's near-white text against the rest of the band it sits in
                    (templates/looks.json captions, template3.html #caps); 4.5 reads well, under 3 is hard to read, as small
                    white words are over a bright picture; None when no caption text shows in any frame

usage: python pipeline/opening_frame.py <video.mp4> [caption class, e.g. low]      prints the scorecard of any rendered Short
"""
import importlib.metadata, json, pathlib, subprocess, sys, time
import numpy as np

W, H = 1080, 1920            # a Short's size (render3.py): every frame is scaled to it, so the caption bands below always fit
WINDOW, RATE = 1.5, 2.5      # seconds read, frames a second: 4 frames, at 0, 0.4, 0.8 and 1.2 seconds
OCR_BUDGET = 90              # seconds all the text reading may take; frames left after that are not read
AUTO = object()              # "build the usual detector" (a test passes its own, or None for "not available")

# Where each caption look sits, in rows of the 1080x1920 frame (template3.html, YouTube layout): #caps top to top + height. The
# look lab's captions ("lab") say their own top in the look's cap settings. While a full-screen picture has its person low down
# the captions jump to row 400 instead (template3.html renderAt), so a frame with no text in its band is looked at there too.
CAPTION_BANDS = {"low": (1385, 1507), "minimal": (1290, 1500), "clean": (1270, 1500), "pop": (1180, 1500), "boxed": (1230, 1500),
                 "punch": (1230, 1500)}
CAPTION_X, CAPTION_TOP, LAB_HEIGHT = (70, 840), 400, 230
TEXT_MIN = 185               # every colour channel at least this (0 to 255): the near-white caption text (#F5F8FA at 80 to 100%)
MIN_TEXT, MAX_TEXT = 0.003, 0.45     # share of a band that near-white text covers: under the first there is no caption in it;
                                     # over the second the band is near white all over and no words can stand out


# ---------------------------------------------------------------- the frames
def grab_frames(mp4, window=WINDOW, rate=RATE):
    """The first `window` seconds of a video as one RGB array (frames, 1920, 1080, 3): a single ffmpeg call, nothing on disk."""
    cmd = ["ffmpeg", "-v", "error", "-t", str(window), "-i", str(mp4), "-an", "-vf", f"fps={rate},scale={W}:{H}",
           "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=120).stdout
    n = len(raw) // (W * H * 3)
    if n == 0: raise RuntimeError("ffmpeg gave no frames")
    return np.frombuffer(raw, np.uint8, n * W * H * 3).reshape(n, H, W, 3)


def half(rgb):
    """A 1080x1920 frame at 540x960 (each 2x2 block averaged): the size sharpness, contrast, faces and text are scored at."""
    return rgb.reshape(H // 2, 2, W // 2, 2, 3).mean(axis=(1, 3)).astype(np.uint8)


def grey(rgb):
    """Grey levels, 0 to 255, as a float array (the usual 0.299, 0.587, 0.114 weights)."""
    return rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


# ---------------------------------------------------------------- the numbers
def sharpness(g):
    """Variance of the Laplacian (the 4-neighbour kernel) of a grey frame: sharp edges and fine detail raise it, blur flattens it."""
    lap = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4 * g[1:-1, 1:-1]
    return float(lap.var(dtype=np.float64))


def contrast(g):
    """RMS contrast of a grey frame: the standard deviation of its levels over the full range (255)."""
    return float(g.std() / 255)


def haar_faces():
    """(detector, note). The detector takes a grey uint8 frame and gives its faces as (x, y, width, height): OpenCV's frontal
    Haar cascade with render3.face_focus's settings. (None, why) without OpenCV or its cascade file."""
    try:
        import cv2
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if casc.empty(): return None, "off: no Haar cascade file with this OpenCV"
    except Exception as e: return None, f"off: {type(e).__name__}"

    def detect(g8):
        sc = min(1.0, 800 / max(g8.shape))
        small = cv2.resize(g8, (int(g8.shape[1] * sc), int(g8.shape[0] * sc))) if sc < 1 else g8
        found = casc.detectMultiScale(small, 1.1, 5, minSize=(max(24, int(min(small.shape) * 0.06)),) * 2)
        return [(x / sc, y / sc, w / sc, h / sc) for x, y, w, h in found]
    return detect, "haar"


def face_share(g8, detect):
    """Share of the frame the largest face covers; 0.0 when the detector finds none."""
    faces = detect(g8)
    if not len(faces): return 0.0
    _, _, w, h = max(faces, key=lambda f: f[2] * f[3])
    return min(1.0, float(w * h) / (g8.shape[0] * g8.shape[1]))


def rapidocr_text():
    """(detector, note). The detector takes an RGB frame and gives its text boxes, each four (x, y) corners: RapidOCR's text
    detector alone (the bundled models, no reading and no download). (None, why) when RapidOCR is not installed."""
    try:
        from rapidocr import RapidOCR
        engine = RapidOCR(params={"Global.log_level": "error"})
        note = "rapidocr " + importlib.metadata.version("rapidocr")
    except Exception as e: return None, f"off: {type(e).__name__}: rapidocr not usable here"

    def detect(rgb):
        out = engine(np.ascontiguousarray(rgb[..., ::-1]), use_det=True, use_cls=False, use_rec=False)      # it reads BGR, as cv2 does
        boxes = getattr(out, "boxes", None)
        return [] if boxes is None else [np.asarray(b, np.float32) for b in boxes]
    return detect, note


def text_share(rgb, detect):
    """Share of a frame covered by the text boxes the detector finds in it; two boxes over the same pixels count once."""
    from PIL import Image, ImageDraw
    k = 4
    mask = Image.new("L", (max(1, rgb.shape[1] // k), max(1, rgb.shape[0] // k)), 0)
    draw = ImageDraw.Draw(mask)
    for b in detect(rgb): draw.polygon([(float(x) / k, float(y) / k) for x, y in b], fill=255)
    return float(np.asarray(mask).mean() / 255)


def luminance(rgb):
    """WCAG relative luminance, 0 (black) to 1 (white), of every pixel of an RGB uint8 array."""
    c = rgb.astype(np.float32) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722


def grow(mask, r):
    """A boolean mask with every True pixel spread r pixels each way."""
    from PIL import Image, ImageFilter
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(2 * r + 1))) > 0


def caption_band(captions, cap=None):
    """(top row, bottom row) of the band a look's captions sit in (YouTube layout)."""
    if captions == "lab":
        try: top = int(float(str((cap or {}).get("top", 1290)).replace("px", "")))
        except ValueError: top = 1290
        return top, top + LAB_HEIGHT
    return CAPTION_BANDS.get(captions, (1290, 1500))


def caption_contrast(rgb, band, strict=False):
    """WCAG contrast ratio, 1 to 21, of the caption text (the near-white pixels of a band of a 1080x1920 frame) against the rest
    of that band, glyph edges left out. 1.0 when the band is near white all over (strict: None then); None when it holds no
    caption text."""
    top, bottom = band
    crop = rgb[max(0, top):min(rgb.shape[0], bottom), CAPTION_X[0]:CAPTION_X[1]]
    text = crop.min(axis=2) >= TEXT_MIN
    share = float(text.mean()) if text.size else 0.0
    if share < MIN_TEXT: return None
    if share > MAX_TEXT: return None if strict else 1.0
    lum = luminance(crop)
    rest = lum[~grow(text, 3)]
    if not rest.size: return 1.0
    fg, bg = float(np.median(lum[text])), float(np.median(rest))
    return (max(fg, bg) + 0.05) / (min(fg, bg) + 0.05)


def frame_caption(rgb, captions, cap=None):
    """A frame's caption contrast: in the look's own band, else (a person low in the picture moves the captions) at the top."""
    band = caption_band(captions, cap)
    got = caption_contrast(rgb, band)
    return got if got is not None else caption_contrast(rgb, (CAPTION_TOP, CAPTION_TOP + band[1] - band[0]), strict=True)


# ---------------------------------------------------------------- the scorecard
def _safe(fn, *a):
    try: return fn(*a)
    except Exception as e:
        print(f"opening scorecard: {fn.__name__} skipped ({type(e).__name__}: {str(e)[:100]})", flush=True)
        return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return None if not xs else (xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2)


def scorecard(mp4, captions="", cap=None, frames=None, faces=AUTO, text=AUTO):
    """The five numbers for the first 1.5 seconds of `mp4` (see the top of this file), as the dict run_board.py keeps in
    status qa.opening: the averages over the frames (the median for the captions), the per-frame values, and how each was
    read ("faces", "ocr"). `captions` and `cap` are the look's caption class and settings (looks.resolve()["render"]).
    `frames`, `faces` and `text` stand in for the video and the two detectors (tests); None for a detector means unavailable.
    Never raises: what cannot be read is None, and a video that cannot be read gives {"error": ...}."""
    try:
        frames = grab_frames(mp4) if frames is None else frames
        if not len(frames): raise RuntimeError("no frames")
    except Exception as e:
        return {"error": f"frames: {type(e).__name__}: {str(getattr(e, 'stderr', '') or e)[-160:]}"}
    out = {"frames": len(frames), "t": [round(i / RATE, 2) for i in range(len(frames))]}
    if faces is AUTO: faces, out["faces"] = _safe(haar_faces) or (None, "off")
    if text is AUTO: text, out["ocr"] = _safe(rapidocr_text) or (None, "off")
    if text is None and "ocr" not in out: out["ocr"] = "off"
    rows = {k: [] for k in ("sharpness", "contrast", "face_area", "text_area", "caption_contrast")}
    deadline = time.time() + OCR_BUDGET
    for rgb in frames:
        hr = _safe(half, rgb)
        g = _safe(grey, hr) if hr is not None else None
        g8 = np.clip(g, 0, 255).astype(np.uint8) if g is not None else None
        rows["sharpness"].append(_safe(sharpness, g) if g is not None else None)
        rows["contrast"].append(_safe(contrast, g) if g is not None else None)
        rows["face_area"].append(_safe(face_share, g8, faces) if faces and g8 is not None else None)
        rows["text_area"].append(_safe(text_share, hr, text) if text and hr is not None and time.time() < deadline else None)
        rows["caption_contrast"].append(_safe(frame_caption, rgb, captions, cap))
    digits = {"sharpness": 1, "contrast": 3, "face_area": 4, "text_area": 4, "caption_contrast": 2}
    for k, xs in rows.items():
        v = _median(xs) if k == "caption_contrast" else _mean(xs)
        out[k] = None if v is None else round(float(v), digits[k])
    out["by_frame"] = {k: [None if x is None else round(float(x), digits[k]) for x in xs] for k, xs in rows.items()}
    return out


if __name__ == "__main__":
    print(json.dumps(scorecard(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""), indent=1))
