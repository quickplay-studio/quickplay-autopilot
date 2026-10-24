"""Offline test of the render, upload and record path's resilience (audit H3, M5, M9, 24 October):
1. plan.py: a board file holding a JSON list or string becomes a reject job instead of crashing the plan (which stopped
   every render), and without the YouTube keys a Short still renders as a schedule job (not mode "none", which filed it
   as done without an upload);
2. record.py: a Short upload.py held (YouTube's daily limit, or the keys missing) is kept as its draft preview and its board
   moves to boards/ready, approved, so publish.py uploads it without a new render; if the draft can't be kept it stays
   queued as before; while Shorts wait for the keys there is one needs-charlie issue;
3. publish.py: once YouTube refused an upload for quota today, approved Shorts wait without another call."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, datetime as dt, io, json, os, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")

# 1. plan.py
import plan as P, validate, background
P.ROOT = SCRATCH / "plan"; Q = P.ROOT / "boards" / "queue"; Q.mkdir(parents=True); (P.ROOT / "status").mkdir()
uk_today = dt.datetime.now(dt.timezone.utc).astimezone(P.UK).date()
(P.ROOT / "status" / f"weekly-{uk_today}.json").write_text(json.dumps({"video": "x"}))      # a Sunday keeps no place back
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(24)]
P.LEAD = dt.timedelta(hours=1)
P.LIMIT = 5
validate.check = lambda b, p=None: ([], [])
background.wanted = lambda b, cfg: False
good = {"id": "QD-950", "created": str(uk_today + dt.timedelta(days=1)), "kind": "evergreen", "format": "one_detail", "category": "Music",
        "meta": {"title": "t", "sources": []}, "beats": [{"say": "x"}]}
(Q / "QD-950.json").write_text(json.dumps(good))
(Q / "QD-951.json").write_text(json.dumps(["beats", "a list, not a board"]))
(Q / "QD-952.json").write_text(json.dumps("a string"))
(Q / "QD-953.json").write_text("{not json")


def run_plan(online):
    P.schedule_state = lambda now: (set(), 0, online)
    with contextlib.redirect_stdout(buf := io.StringIO()): P.main()
    return {j["id"]: j for j in json.loads(buf.getvalue().strip().split("boards=", 1)[1])}


by = run_plan(True)
assert by["QD-951"]["mode"] == "reject" and "a JSON list" in by["QD-951"]["errors"], by["QD-951"]
assert by["QD-952"]["mode"] == "reject" and "a JSON str" in by["QD-952"]["errors"], by["QD-952"]
assert by["QD-953"]["mode"] == "reject" and by["QD-950"]["mode"] == "schedule" and by["QD-950"]["slot"], by
by = run_plan(False)                                            # no YouTube keys: it still renders, to be held as a preview
assert by["QD-950"]["mode"] == "schedule", by["QD-950"]
print("1 plan ok")

# 2. record.py with held Shorts (the Google client is not needed: the YouTube helpers are stubbed)
calls = []
Y = types.ModuleType("youtube")
class LimitReached(Exception): pass
Y.LimitReached = LimitReached; Y.available = lambda: True; Y.client = lambda: object()
Y.recent_videos = lambda yt, limit=100: []
Y.upload = lambda *a, **k: calls.append("upload") or "vid"
sys.modules["youtube"] = Y
import record as RC, upload as U
RC.ROOT = SCRATCH / "rec"; res = SCRATCH / "results"
for d in ("queue", "ready", "done", "failed"): (RC.ROOT / "boards" / d).mkdir(parents=True, exist_ok=True)
(RC.ROOT / "status").mkdir(); (RC.ROOT / "review").mkdir()
def held(sid, state):
    (RC.ROOT / "boards" / "queue" / f"{sid}.json").write_text(json.dumps({"id": sid, "created": "2026-10-24"}))
    d = res / sid; d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"id": sid, "board": f"boards/queue/{sid}.json", "state": state, "mode": "schedule",
                                               "approved": "2026-10-24T20:00:00+00:00"}))
    (d / "preview.mp4").write_bytes(b"v"); (d / "upload.json").write_text("{}")
held("QD-960", U.LIMIT_WAIT); held("QD-961", U.KEYS_MISSING); held("QD-962", U.LIMIT_WAIT)
made, issues = [], []
def fake_preview(r, sid, prev, notes=""):
    made.append(sid)
    return {"preview_error": "release refused"} if sid == "QD-962" else {"preview_release": f"preview-{sid}", "preview_url": "u"}
RC.preview = fake_preview
A = types.ModuleType("alerts")
A.raise_issue = lambda title, body, labels=None: issues.append(("raise", title, labels))
A.clear = lambda title, body: issues.append(("clear", title))
sys.modules["alerts"] = A
with contextlib.redirect_stdout(io.StringIO()): RC.main(res)
st = lambda sid: json.loads((RC.ROOT / "status" / f"{sid}.json").read_text())
assert (RC.ROOT / "boards" / "ready" / "QD-960.json").exists() and st("QD-960")["preview_release"] == "preview-QD-960" and st("QD-960")["approved"]
assert (RC.ROOT / "boards" / "ready" / "QD-961.json").exists() and st("QD-961")["state"] == U.KEYS_MISSING
# the draft could not be kept: queued again, to render again (as before 24 October), and no longer approved
assert (RC.ROOT / "boards" / "queue" / "QD-962.json").exists() and st("QD-962")["state"].startswith("waiting") and not st("QD-962").get("approved")
assert sorted(made) == ["QD-960", "QD-961", "QD-962"]
assert issues and issues[0][0] == "raise" and issues[0][1] == RC.KEYS_TITLE and issues[0][2] == ["needs-charlie"], issues
print("2 record ok")

# 3. publish.py: no upload call after a quota refusal today
import publish as PB, quota
PB.ROOT = SCRATCH / "pub"; PB.READY = PB.ROOT / "boards" / "ready"; PB.STATUS = PB.ROOT / "status"; PB.RESERVE = PB.ROOT / "boards" / "reserve"
for d in (PB.READY, PB.STATUS, PB.RESERVE): d.mkdir(parents=True)
(PB.READY / "QD-970.json").write_text(json.dumps({"id": "QD-970", "created": "2026-10-24", "kind": "evergreen"}))
(PB.STATUS / "QD-970.json").write_text(json.dumps({"id": "QD-970", "state": U.LIMIT_WAIT, "approved": "x", "preview_release": "preview-QD-970"}))
PB.plan.schedule_state = lambda now, yt=None: (set(), 0, True)
quota.learn = lambda recent: 40
quota.bucket_refused = lambda b: b == "upload"
PB.gh = lambda *a, check=True: calls.append(("gh",) + a) or types.SimpleNamespace(returncode=0, stdout="", stderr="")
with contextlib.redirect_stdout(io.StringIO()): PB.main()
s = json.loads((PB.STATUS / "QD-970.json").read_text())
assert s["state"] == "approved, waiting for YouTube's daily upload limit" and calls == [], (s, calls)
quota.bucket_refused = lambda b: False                     # no refusal today: the same Short goes for its preview (not vacuous)
with contextlib.redirect_stdout(io.StringIO()): PB.main()
assert calls and calls[0][:3] == ("gh", "release", "download"), calls
print("3 publish ok")
print("render path ok")
