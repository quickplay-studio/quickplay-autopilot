"""Offline test of pipeline/prune_releases.py (audit L3, 24 October): old draft previews and clip files go only when
nothing needs them; anything pending, scheduled, recent or unknown stays; deletions are capped and logged; a dry run
deletes nothing."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, datetime as dt, io, json, os, sys, types
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import prune_releases as PR

PR.ROOT = SCRATCH
for d in ("boards/ready", "boards/queue", "boards/done", "status", "clips/plans"): (SCRATCH / d).mkdir(parents=True)
NOW = PR.NOW
ago = lambda days: (NOW - dt.timedelta(days=days)).isoformat().replace("+00:00", "Z")
def status(sid, **kw): (SCRATCH / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, **kw}, indent=1))

status("QD-001", state="scheduled", publish_at=ago(20), social_release="social-QD-001")          # old and public: goes
status("QD-002", state="scheduled", publish_at=ago(2), social_release="social-QD-002")           # public 2 days: stays
status("QD-003", state="awaiting approval", preview_release="preview-QD-003")                    # waiting: stays
(SCRATCH / "boards" / "ready" / "QD-004.json").write_text("{}")                                  # its board is in ready: stays
status("QD-004", state="scheduled", publish_at=ago(20))
status("QD-005", state="scheduled", publish_at=(NOW + dt.timedelta(days=1)).isoformat())         # goes public tomorrow: stays
# QD-006: no status at all, 10 days old: stays; QD-007: no status, 40 days old: goes
RELEASES = [
    {"tagName": "social-QD-001", "isDraft": True, "createdAt": ago(15)},
    {"tagName": "social-QD-002", "isDraft": True, "createdAt": ago(9)},
    {"tagName": "preview-QD-003", "isDraft": True, "createdAt": ago(12)},
    {"tagName": "preview-QD-004", "isDraft": True, "createdAt": ago(12)},
    {"tagName": "social-QD-005", "isDraft": True, "createdAt": ago(8)},
    {"tagName": "preview-QD-006", "isDraft": True, "createdAt": ago(10)},
    {"tagName": "preview-QD-007", "isDraft": True, "createdAt": ago(40)},
    {"tagName": "social-QD-008", "isDraft": True, "createdAt": ago(2)},             # young: stays whatever
    {"tagName": "clips-src", "isDraft": False, "createdAt": ago(60)},              # not ours to prune
    {"tagName": "preview-QD-009", "isDraft": False, "createdAt": ago(60)},         # published, not a draft: never touched
]
(SCRATCH / "clips" / "plans" / "kai.json").write_text(json.dumps({"moments": [
    {"file": "old-public.mp4", "publish_at": ago(20)}, {"file": "recent.mp4", "publish_at": ago(3)},
    {"file": "private-old.mp4", "publish_at": "private"}, {"file": "future.mp4", "publish_at": (NOW + dt.timedelta(days=1)).isoformat()}]}))
ASSETS = [{"name": "old-public.mp4", "createdAt": ago(20)}, {"name": "recent.mp4", "createdAt": ago(16)},
          {"name": "private-old.mp4", "createdAt": ago(20)}, {"name": "future.mp4", "createdAt": ago(15)},
          {"name": "orphan-old.mp4", "createdAt": ago(45)}, {"name": "orphan-new.mp4", "createdAt": ago(20)},
          {"name": "young.mp4", "createdAt": ago(5)}]
CALLS = []
def gh(*a):
    CALLS.append(a)
    if a[:2] == ("release", "list"): return types.SimpleNamespace(stdout=json.dumps(RELEASES), returncode=0)
    if a[:3] == ("release", "view", "clips-out"): return types.SimpleNamespace(stdout=json.dumps({"assets": ASSETS}), returncode=0)
    return types.SimpleNamespace(stdout="", returncode=0)
PR.gh = gh

with contextlib.redirect_stdout(io.StringIO()): n, log = PR.main(dry=True)
assert n == 4 and not [c for c in CALLS if "delete" in c or "delete-asset" in c], (n, log, CALLS)       # dry: nothing deleted
CALLS.clear()
with contextlib.redirect_stdout(io.StringIO()): n, log = PR.main()
deleted = sorted(c[2] for c in CALLS if c[:2] == ("release", "delete")) + sorted(c[3] for c in CALLS if c[:2] == ("release", "delete-asset"))
assert deleted == ["preview-QD-007", "social-QD-001", "old-public.mp4", "orphan-old.mp4"], deleted
assert "social_release" not in json.loads((SCRATCH / "status" / "QD-001.json").read_text())         # nothing downloads it again
assert json.loads((SCRATCH / "status" / "QD-002.json").read_text())["social_release"] == "social-QD-002"
assert (SCRATCH / "status" / "prune_log.txt").read_text().count("deleted") == 4
# the cap
PR.MAX = 1; CALLS.clear()
status("QD-001", state="scheduled", publish_at=ago(20), social_release="social-QD-001")
with contextlib.redirect_stdout(io.StringIO()): n, log = PR.main()
assert n == 1 and any("stopped at 1" in l for l in log), (n, log)
print("prune ok")
