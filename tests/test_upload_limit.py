"""Offline test of the render workflow's upload step (pipeline/upload.py): once YouTube refuses an upload for its daily
limit or quota, the run's other Shorts wait for the next run without another call (each refused call is still a call in
the day's upload bucket, which all four channels share)."""
import json, os, pathlib as _p, sys, tempfile, types
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(tempfile.mkdtemp(prefix="qp-test-"))
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")

Y = types.ModuleType("youtube")             # the Google client is not needed: the YouTube helpers are stubbed
class LimitReached(Exception): pass
CALLS = []
def upload(yt, path, title, *a, **k):
    CALLS.append(title)
    if len(CALLS) == 2: raise LimitReached("uploadLimitExceeded")
    return f"vid{len(CALLS)}"
Y.LimitReached, Y.upload, Y.available, Y.client = LimitReached, upload, (lambda: True), (lambda: object())
Y.recent_videos = lambda yt, limit=100: []
Y.video_status = lambda yt, vid: {"privacy": "private", "publish_at": "2026-10-25T07:30:00Z"}
sys.modules["youtube"] = Y
import upload as U

for i in range(1, 5):
    d = SCRATCH / f"QD-90{i}"; d.mkdir()
    (d / "status.json").write_text(json.dumps({"id": f"QD-90{i}", "state": "rendered", "mode": "schedule"}))
    (d / "upload.json").write_text(json.dumps({"title": f"Short {i}", "description": "", "tags": [], "category": "Gaming",
                                                "mode": "schedule", "slot": "2026-10-25T07:30:00Z"}))
    (d / "video.mp4").write_bytes(b"x")
U.main(str(SCRATCH))
states = [json.loads((SCRATCH / f"QD-90{i}" / "status.json").read_text())["state"] for i in range(1, 5)]
assert CALLS == ["Short 1", "Short 2"], CALLS                     # no call after the refusal
assert states == ["scheduled"] + ["waiting for YouTube's daily upload limit"] * 3, states
print("upload limit ok")
