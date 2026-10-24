"""Faces for the renders: YuNet first, the Haar cascade when its model file is missing.

YuNet (OpenCV's FaceDetectorYN, MIT licence, a 232 KB ONNX file) finds the side, small and tilted faces the frontal Haar
cascade misses, so the Ken Burns window (render3.face_focus), the minimal style's name tag and the captions keep faces
clear more often, and the clips' person finder (clips.face_box) follows people it used to lose. The model is
face_detection_yunet_2023mar.onnx from the opencv_zoo repo, downloaded by get_pictures.py into models/yunet/ at a pinned
SHA-256 (render.yml and clips.yml keep it in the Actions cache). Here it is checked again (size and hash, once per run)
before OpenCV reads it.

yunet_faces(img, min_px) -> [(x, y, w, h)] in the picture's own pixels, the largest first; [] when YuNet looked and found
no face; None when YuNet is not available (no model file, another file under its name, OpenCV cannot build it, or it failed
on this picture): the caller then runs its own Haar cascade exactly as before. Never raises.
"""
import sys

SCORE, NMS, TOP_K, SIDE = 0.75, 0.3, 50, 640      # detection confidence, overlap merge, most faces kept, longest side YuNet sees
_STATE = {}                                        # the verified model path and the built detector, once per run


def note(msg):
    print(f"  faces: {msg}", file=sys.stderr)


def model_path():
    """models/yunet/face_detection_yunet_2023mar.onnx when it is there and is the pinned file, else None (said once)."""
    if "path" in _STATE: return _STATE["path"]
    path = None
    try:
        import get_pictures as GP
        p = GP.models_dir() / GP.YUNET["dir"] / GP.YUNET["file"]
        if not p.exists(): note("YuNet model file not found, using the Haar cascade")
        elif GP.yunet_ok(p): path = p
        else: note(f"{p.name} is not the pinned file (size or SHA-256 differ), using the Haar cascade")
    except Exception as e: note(f"YuNet model check failed ({type(e).__name__}: {str(e)[:100]}), using the Haar cascade")
    _STATE["path"] = path
    return path


def detector():
    """The cv2.FaceDetectorYN, built once; None when the model or OpenCV's detector is missing."""
    if "det" in _STATE: return _STATE["det"]
    det = None
    p = model_path()
    if p is not None:
        try:
            import cv2
            det = cv2.FaceDetectorYN.create(str(p), "", (320, 320), SCORE, NMS, TOP_K)
        except Exception as e: note(f"YuNet could not start ({type(e).__name__}: {str(e)[:100]}), using the Haar cascade")
    _STATE["det"] = det
    return det


def engine():
    """"yunet" when it is in use, else "haar" (for logs)."""
    return "yunet" if detector() is not None else "haar"


def yunet_faces(img, min_px=24):
    """Faces YuNet finds in a BGR picture (what cv2.imread returns): [(x, y, w, h)] in the picture's own pixels, boxes cut to
    the picture, the largest first, none narrower or shorter than `min_px`. None when YuNet is not available."""
    det = detector()
    if det is None: return None
    try:
        import cv2
        h, w = img.shape[:2]
        sc = min(1.0, SIDE / max(h, w))
        im = cv2.resize(img, (max(32, round(w * sc)), max(32, round(h * sc)))) if sc < 1 else img
        det.setInputSize((im.shape[1], im.shape[0]))
        _, found = det.detect(im)
        out = []
        for f in (found if found is not None else []):
            x, y, fw, fh = (float(v) / sc for v in f[:4])
            x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(float(w), x + fw), min(float(h), y + fh)
            if x1 - x0 >= min_px and y1 - y0 >= min_px:
                out.append((int(round(x0)), int(round(y0)), int(round(x1 - x0)), int(round(y1 - y0))))
        return sorted(out, key=lambda b: -(b[2] * b[3]))
    except Exception as e:
        note(f"YuNet failed on a picture ({type(e).__name__}: {str(e)[:100]}), using the Haar cascade for it")
        return None
