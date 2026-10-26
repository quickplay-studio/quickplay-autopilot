"""Offline test of the Daily line's other channels (25 October): the music channel, and the routing every channel shares.
A board's optional "channel" field (default main) picks the sign-in, the slot grid, the room per day and the peers; until a
channel's sign-in (tokens/youtube_<channel>.enc) exists nothing about it runs.
1. youtube.py: connected(), creds_for() / client_for() from a channel's own sign-in, the video's language on upload();
2. validate.py: the channel field;
3. plan.py: the slots taken and the uploads in the last 24 hours per channel, the music channel's grid, and the plan itself
   (a channel's own room, a channel that is not signed in stays queued);
4. upload.py: each Short through its own channel's client, a limit on one channel does not stop the others;
5. record.py: another channel's Shorts are never cross-posted;
6. publish.py: held Shorts go out through their channel's client, within that channel's room;
7. quota.py: the extra channels' uploads still to come are kept in the 100-upload bucket;
8. analytics.py, drivers.py, changes.py: every channel is measured, the main channel's numbers stay its own;
9. writer.py: the music channel's boards (series, overlap, room per run) and the main channel's counters ignore them."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, csv, datetime as dt, io, json, os, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
os.environ.update(YT_CLIENT_ID="cid", YT_CLIENT_SECRET="csec")


# ---------- 1. youtube.py (the Google libraries are stubbed) ----------
class Creds:
    def __init__(self, token=None, **kw): self.token, self.kw = token, kw


class Svc:
    """A Google service object: the sign-in it was built with, nothing more."""
    def __init__(self, name, credentials=None): self.name, self.credentials = name, credentials


def stub(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m


class HttpError(Exception): pass


stub("google"); stub("google.oauth2"); stub("google.oauth2.credentials", Credentials=Creds)
stub("googleapiclient"); stub("googleapiclient.errors", HttpError=HttpError); stub("googleapiclient.http", MediaFileUpload=lambda *a, **k: ("media", a))
stub("googleapiclient.discovery", build=lambda service, version, credentials=None, cache_discovery=False: Svc(service, credentials))
import youtube as Y

Y.ROOT = SCRATCH / "yt"; (Y.ROOT / "tokens").mkdir(parents=True)
assert Y.connected("main") and Y.connected("") and not Y.connected("music")
(Y.ROOT / "tokens" / "youtube_music.enc").write_bytes(b"")
assert not Y.connected("music"), "an empty file is no sign-in"
(Y.ROOT / "tokens" / "youtube_music.enc").write_bytes(b"x")
assert Y.connected("music") and not Y.connected("es")
stub("social", load=lambda name: {"refresh_token": "rt-music", "scope": "s1 s2"} if name == "youtube_music" else {})
c = Y.creds_for("music")
assert c.kw["refresh_token"] == "rt-music" and c.kw["scopes"] == ["s1", "s2"] and c.kw["client_id"] == "cid" and c.kw["client_secret"] == "csec", c.kw
try: Y.creds_for("es"); raise AssertionError("a channel with no sign-in has no credentials")
except RuntimeError as e: assert "es channel is not signed in" in str(e), e
cl = Y.client_for("music")
assert cl.name == "youtube" and cl.credentials.kw["refresh_token"] == "rt-music", cl
sent = []
Y._send = lambda yt, path, body: sent.append(body) or "vidX"
Y.named_copy = lambda path, title: path
Y._quota = lambda event: None
Y.upload("yt", "v.mp4", "T", "D", ["a"], "Music", None)
Y.upload("yt", "v.mp4", "T", "D", ["a"], "Music", None, language="es")
assert sent[0]["snippet"]["defaultLanguage"] == "en-GB" and sent[0]["snippet"]["defaultAudioLanguage"] == "en-GB", sent[0]
assert sent[1]["snippet"]["defaultLanguage"] == "es" and sent[1]["snippet"]["defaultAudioLanguage"] == "es", sent[1]
assert sent[1]["status"]["containsSyntheticMedia"] is False and sent[1]["status"]["selfDeclaredMadeForKids"] is False
print("1 youtube ok")

# ---------- 2. validate.py ----------
import validate as V
errs = V.check({"id": "TEST-CH", "channel": "nowhere"})[0]
assert any(e.startswith("channel:") for e in errs), errs
assert not any(e.startswith("channel:") for e in V.check({"id": "TEST-CH", "channel": "music"})[0])
assert not any(e.startswith("channel:") for e in V.check({"id": "TEST-CH"})[0])
assert not any(e.startswith("channel:") for e in V.check({"id": "TEST-CH", "channel": "main"})[0])
print("2 validate ok")

# ---------- 3. plan.py ----------
import plan as P, background
P.ROOT = SCRATCH / "plan"; (P.ROOT / "status").mkdir(parents=True); Q = P.ROOT / "boards" / "queue"; Q.mkdir(parents=True)
now = dt.datetime.now(dt.timezone.utc)
iso = lambda t: t.isoformat(timespec="seconds").replace("+00:00", "Z")
t1, t2, t3, t4 = [now + dt.timedelta(hours=h) for h in (5, 9, 30, 13)]
def status(sid, **kw): (P.ROOT / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, **kw}))
status("QD-1", video="v1", uploaded_at=iso(now - dt.timedelta(hours=2)), publish_at=iso(t1))
status("QD-2", video="v2", channel="music", uploaded_at=iso(now - dt.timedelta(hours=3)), publish_at=iso(t2))
status("QD-3", video="v3", channel="music", uploaded_at=iso(now - dt.timedelta(days=3)), publish_at=iso(t3))
vids = {"main-client": [], "music-client": [{"id": "v9", "title": "x", "uploaded": iso(now - dt.timedelta(hours=1)), "publish_at": iso(t4),
                                              "privacy": "private", "views": 0}]}
Y.available = lambda: True; Y.connected = lambda ch: ch in ("main", "music")
Y.client = lambda: "main-client"; Y.client_for = lambda ch: f"{ch}-client"; Y.recent_videos = lambda yt, limit=100: vids[yt]
tk, rc, on = P.schedule_state(now)
assert tk == {Y.utc(iso(t1))} and rc == 1 and on, (tk, rc)                  # the main channel's day alone
tk, rc, on = P.schedule_state(now, channel="music")
assert tk == {Y.utc(iso(t)) for t in (t2, t3, t4)} and rc == 2 and on, (tk, rc)       # its own Short and the private upload made by hand
tk, rc, on = P.schedule_state(now, channel="es")
assert not on and not tk and rc == 0, (tk, rc, on)                          # not signed in

day = dt.date(2026, 10, 27)
ms = P.day_slots(day, "music")
assert len(ms) == 6 and all(b - a == dt.timedelta(minutes=240) for a, b in zip(ms, ms[1:])), ms
assert [t.astimezone(P.UK).strftime("%H:%M") for t in ms] == ["07:30", "11:30", "15:30", "19:30", "23:30", "03:30"], ms     # round the 24 hours
assert P.board_channel({}) == "main" and P.board_channel({"channel": "music"}) == "music" and P.board_channel("not a board") == "main"

P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(24)]              # the main channel's grid: on the hour
P.LEAD = dt.timedelta(hours=1); P.LIMIT = 5
V.check = lambda b, p=None: ([], [])
background.wanted = lambda b, cfg: False
uk_today = now.astimezone(P.UK).date()
(P.ROOT / "status" / f"weekly-{uk_today}.json").write_text(json.dumps({"video": "x"}))
for k in ("QD-960", "QD-961", "QD-962", "QD-963"): status(k + "-old") if False else None
def board(sid, **kw):
    (Q / f"{sid}.json").write_text(json.dumps({"id": sid, "created": str(uk_today + dt.timedelta(days=1)), "kind": "evergreen", "format": "one_detail",
                                               "category": "Music", "meta": {"title": "t", "sources": []}, "beats": [{"say": "x"}], **kw}))
board("QD-960"); board("QD-961", channel="music"); board("QD-962", channel="es"); board("QD-963", channel="music")
room = {"main": 0, "music": 5}                                              # the music channel already has 5 of its 6 in the last 24 hours
P.schedule_state = lambda now, yt=None, channel="main": (set(), room.get(channel, 0), channel in ("main", "music"))
with contextlib.redirect_stdout(buf := io.StringIO()): P.main()
jobs = {j["id"]: j for j in json.loads(buf.getvalue().strip().split("boards=", 1)[1])}
assert sorted(jobs) == ["QD-960", "QD-961"], sorted(jobs)                  # QD-962: es is not signed in, QD-963: music has no room left
assert "channel" not in jobs["QD-960"] and jobs["QD-961"]["channel"] == "music", jobs
assert jobs["QD-960"]["mode"] == "schedule" and jobs["QD-961"]["mode"] == "schedule"
mslot = dt.datetime.fromisoformat(jobs["QD-961"]["slot"].replace("Z", "+00:00")).astimezone(P.UK)
mainslot = dt.datetime.fromisoformat(jobs["QD-960"]["slot"].replace("Z", "+00:00")).astimezone(P.UK)
assert mslot.strftime("%H:%M") in ("07:30", "11:30", "15:30", "19:30", "23:30", "03:30"), mslot      # the music grid, not the main channel's
assert mainslot.minute == 0, mainslot
room["music"] = 6
with contextlib.redirect_stdout(buf := io.StringIO()): P.main()
jobs = {j["id"]: j for j in json.loads(buf.getvalue().strip().split("boards=", 1)[1])}
assert sorted(jobs) == ["QD-960"], jobs                                    # the channel is full for the day: its boards wait, the main channel carries on
print("3 plan ok")

# ---------- 4. upload.py ----------
import upload as U
uploads, listed = [], []
Y.recent_videos = lambda yt, limit=100: listed.append(yt) or []
class LimitReached(Exception): pass
Y.LimitReached = LimitReached
def fake_upload(yt, path, title, description, tags, category, publish_at=None, localizations=None, **kw):
    if title == "refused": raise LimitReached("uploadLimitExceeded")
    uploads.append((yt, title, {k: v for k, v in kw.items() if k != "paid" or v})); return f"vid-{title}"
Y.upload = fake_upload
Y.video_status = lambda yt, vid: {"privacy": "private", "publish_at": "2026-10-27T10:00:00Z"}
res = SCRATCH / "results"
def result(sid, title, channel=None, state="rendered"):
    d = res / sid; d.mkdir(parents=True)
    (d / "video.mp4").write_bytes(b"v")
    (d / "status.json").write_text(json.dumps({"id": sid, "state": state, "mode": "schedule", **({"channel": channel} if channel else {})}))
    (d / "upload.json").write_text(json.dumps({"title": title, "description": "d", "tags": [], "category": "Music", "slot": "2026-10-27T10:00:00Z",
                                               "mode": "schedule", "flags": [], **({"channel": channel} if channel else {})}))
result("QD-901", "refused", "music"); result("QD-902", "main one"); result("QD-903", "music two", "music"); result("QD-904", "es one", "es")
with contextlib.redirect_stdout(io.StringIO()): U.main(res)
st = lambda sid: json.loads((res / sid / "status.json").read_text())
assert uploads == [("main-client", "main one", {})], uploads                 # the main Short through the main client; the music channel was refused, so its second waits
assert st("QD-902")["state"] == "scheduled" and st("QD-902")["video"] == "vid-main one" and "channel" not in st("QD-902")
assert st("QD-901")["state"] == U.LIMIT_WAIT and st("QD-903")["state"] == U.LIMIT_WAIT and (res / "QD-903" / "preview.mp4").exists()
assert st("QD-904")["state"] == U.signin_missing("es") and (res / "QD-904" / "preview.mp4").exists(), st("QD-904")      # es is not signed in
assert "main-client" in listed and "music-client" in listed and "es-client" not in listed, listed
# the same Short again, the music channel accepting it now: it goes through the music client, with its language when it has one
res2 = SCRATCH / "results2"; res = res2
result("QD-905", "music three", "music")
(res2 / "QD-905" / "upload.json").write_text(json.dumps({"title": "music three", "description": "d", "tags": [], "category": "Music",
                                                         "slot": "2026-10-27T10:00:00Z", "mode": "schedule", "flags": [], "language": "es"}))
with contextlib.redirect_stdout(io.StringIO()): U.main(res2)
assert uploads[-1] == ("music-client", "music three", {"language": "es"}), uploads
assert st("QD-905")["state"] == "scheduled" and st("QD-905")["channel"] == "music" and st("QD-905")["video"] == "vid-music three"
print("4 upload ok")

# ---------- 5. record.py ----------
import record as RC
RC.ROOT = SCRATCH / "rec"
for d in ("queue", "done"): (RC.ROOT / "boards" / d).mkdir(parents=True)
(RC.ROOT / "status").mkdir(); (RC.ROOT / "review").mkdir()
gh_calls = []
RC.subprocess = types.SimpleNamespace(run=lambda cmd, **k: gh_calls.append(cmd) or types.SimpleNamespace(returncode=0, stdout="", stderr=""))
rres = SCRATCH / "rres"
for sid, extra in (("QD-910", {}), ("QD-911", {"channel": "music"})):
    d = rres / sid; d.mkdir(parents=True)
    (RC.ROOT / "boards" / "queue" / f"{sid}.json").write_text(json.dumps({"id": sid}))
    (d / "status.json").write_text(json.dumps({"id": sid, "board": f"boards/queue/{sid}.json", "state": "scheduled", "video": "v", **extra}))
    (d / "social.mp4").write_bytes(b"s")
with contextlib.redirect_stdout(io.StringIO()): RC.main(rres)
made = [c[3] for c in gh_calls if c[:3] == ["gh", "release", "create"]]
assert made == ["social-QD-910"], gh_calls                                   # only the main channel's Short is cross-posted
assert json.loads((RC.ROOT / "status" / "QD-910.json").read_text())["social_release"] == "social-QD-910"
assert "social_release" not in json.loads((RC.ROOT / "status" / "QD-911.json").read_text())
print("5 record ok")

# ---------- 6. publish.py ----------
import publish as PB, quota
PB.ROOT = SCRATCH / "pub"; PB.READY = PB.ROOT / "boards" / "ready"; PB.STATUS = PB.ROOT / "status"; PB.RESERVE = PB.ROOT / "boards" / "reserve"
for d in (PB.READY, PB.STATUS, PB.RESERVE, PB.ROOT / "boards" / "done"): d.mkdir(parents=True)
for sid, extra in (("QD-970", {}), ("QD-971", {"channel": "music"}), ("QD-972", {"channel": "music"}), ("QD-973", {"channel": "es"})):
    (PB.READY / f"{sid}.json").write_text(json.dumps({"id": sid, "created": "2026-10-27", "kind": "evergreen", **extra}))
    (PB.STATUS / f"{sid}.json").write_text(json.dumps({"id": sid, "state": U.LIMIT_WAIT, "approved": "x", "preview_release": f"preview-{sid}", **extra}))
PB.plan.schedule_state = lambda now, yt=None, channel="main": (set(), {"main": 0, "music": 5}.get(channel, 0), True)
quota.learn = lambda recent: 40
quota.bucket_refused = lambda b: False
PB.FR.safe_check = lambda *a, **k: None
Y.recent_videos = lambda yt, limit=100: []
uploads.clear()
def fake_gh(*a, check=True):
    if a[:2] == ("release", "download"):
        out = pathlib_Path(a[a.index("-D") + 1])
        (out / "video.mp4").write_bytes(b"v")
        title = {"preview-QD-970": "main one", "preview-QD-971": "music one", "preview-QD-972": "music two", "preview-QD-973": "es one"}[a[2]]
        (out / "upload.json").write_text(json.dumps({"title": title, "description": "d", "tags": [], "category": "Music"}))
    return types.SimpleNamespace(returncode=0, stdout="", stderr="")
from pathlib import Path as pathlib_Path
PB.gh = fake_gh
with contextlib.redirect_stdout(io.StringIO()): PB.main()
pst = lambda sid: json.loads((PB.STATUS / f"{sid}.json").read_text())
assert [(u[0], u[1]) for u in uploads] == [("main-client", "main one"), ("music-client", "music one")], uploads
assert pst("QD-972")["state"] == "approved, waiting for YouTube's daily upload limit", pst("QD-972")      # the music channel's sixth Short today was the last
assert pst("QD-971")["state"] in ("scheduled", "uploaded but not scheduled (check Studio)") and pst("QD-971")["video"] == "vid-music one"
assert (PB.ROOT / "boards" / "done" / "QD-971.json").exists() and (PB.READY / "QD-972.json").exists()
# a Short of a channel that is not signed in waits as it is
Y.connected = lambda ch: ch in ("main",)
(PB.STATUS / "QD-974.json").write_text(json.dumps({"id": "QD-974", "state": U.LIMIT_WAIT, "approved": "x", "preview_release": "p", "channel": "music"}))
(PB.READY / "QD-974.json").write_text(json.dumps({"id": "QD-974", "created": "2026-10-27", "kind": "evergreen", "channel": "music"}))
n = len(uploads)
with contextlib.redirect_stdout(io.StringIO()): PB.main()
assert len(uploads) == n and pst("QD-974")["state"] == "approved, waiting for the music channel's sign-in", pst("QD-974")
Y.connected = lambda ch: ch in ("main", "music")
print("6 publish ok")

# ---------- 7. quota.py ----------
quota.ROOT = SCRATCH / "q"; (quota.ROOT / "status").mkdir(parents=True); (quota.ROOT / "tokens").mkdir()
quota.target = lambda: 15
def qstatus(sid, ch=None):
    (quota.ROOT / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "uploaded_at": iso(dt.datetime.now(dt.timezone.utc)), **({"channel": ch} if ch else {})}))
qstatus("QD-1"); qstatus("QD-2"); qstatus("QD-3", "music")
assert quota.uploads_left() == 15 + 1 - 2, quota.uploads_left()             # the music Short is not one of the main channel's 15
(quota.ROOT / "tokens" / "youtube_music.enc").write_bytes(b"x")
assert quota.uploads_left() == 15 + 1 - 2 + (6 - 1), quota.uploads_left()   # signed in: its other 5 are kept in the bucket
print("7 quota ok")

# ---------- 8. analytics.py, drivers.py, changes.py ----------
import analytics as A, drivers as DRV, changes as C
A.ROOT = SCRATCH / "an"; A.OUT = A.ROOT / "analytics"; A.CACHE = A.OUT / "cache"
for d in ("done", "queue", "failed"): (A.ROOT / "boards" / d).mkdir(parents=True)
A.OUT.mkdir(); (A.ROOT / "status").mkdir()
(A.ROOT / "boards" / "done" / "QD-1.json").write_text(json.dumps({"id": "QD-1", "category": "Film", "format": "one_detail", "beats": [{"say": "a b c"}]}))
(A.ROOT / "boards" / "done" / "QD-2.json").write_text(json.dumps({"id": "QD-2", "category": "Music", "format": "one_detail", "channel": "music", "beats": [{"say": "a b"}]}))
(A.ROOT / "status" / "QD-1.json").write_text(json.dumps({"id": "QD-1", "video": "vm", "title": "Main"}))
(A.ROOT / "status" / "QD-2.json").write_text(json.dumps({"id": "QD-2", "video": "vx", "title": "Music one", "channel": "music"}))
ours = A.our_shorts()
assert ours["vm"]["channel"] == "main" and ours["vx"]["channel"] == "music" and ours["vx"]["category"] == "Music", ours

class Q:      # one answer, whatever list() or query() is asked
    def __init__(self, data): self.data = data
    def list(self, **k): return self
    def query(self, **k): return self
    def execute(self): return self.data
class FakeYT:
    def channels(self): return Q({"items": [{"statistics": {"subscriberCount": "12"}}]})
    def videos(self): return Q({"items": [{"id": "vx", "statistics": {"viewCount": "340", "likeCount": "9", "commentCount": "2"}}]})
class FakeYA:
    def reports(self): return Q({"columnHeaders": [{"name": "video"}, {"name": "views"}, {"name": "subscribersGained"}], "rows": [["vx", 340, 7]]})
sys.modules["googleapiclient.discovery"].build = lambda service, version, credentials=None, cache_discovery=False: FakeYA()
Y.client_for = lambda ch: FakeYT()
Y.creds_for = lambda ch: f"creds-{ch}"
Y.recent_videos = lambda yt, limit=100: [{"id": "vx", "title": "Music one", "uploaded": iso(now - dt.timedelta(days=2)), "publish_at": None, "privacy": "public", "views": 340}]
x = A.extra_youtube(ours)
assert x["errors"] == {}, x["errors"]
assert x["subs"] == {"music": 12} and x["channel_of"] == {"vx": "music"} and x["stats"]["vx"] == {"views": 340, "likes": 9, "comments": 2}, x
assert x["analytics"]["vx"]["subscribersGained"] == 7, x["analytics"]
assert json.loads((A.CACHE / "youtube_music.json").read_text())["analytics"]["vx"]["views"] == 340          # kept for the hourly runs
A.FAST = True
x = A.extra_youtube(ours)
assert x["analytics"]["vx"]["subscribersGained"] == 7 and x["subs"] == {"music": 12}, x           # an hourly run reuses it
A.FAST = False
Y.connected = lambda ch: ch == "main"
assert A.extra_youtube(ours) == {"videos": {}, "stats": {}, "analytics": {}, "channel_of": {}, "subs": {}, "errors": {}}      # not signed in: nothing
Y.connected = lambda ch: ch in ("main", "music")

# the volume test counts the main channel's Shorts only
(A.OUT / "shorts.csv").write_text("short,channel,posted,views_24h\nQD-1,main,2026-10-20T10:00+00:00,100\nQD-2,music,2026-10-20T11:00+00:00,500\nQD-3,,2026-10-20T12:00+00:00,200\n")
(A.OUT / "hourly.csv").write_text("hour_utc,uk_day,hours,yt_gained\n")
days = A.volume_days()
assert days["2026-10-20"]["n"] == 2 and days["2026-10-20"]["v24"] == [100.0, 200.0], days

# each channel is judged against its own typical week-old Short; the verdicts are the main channel's
NOW = DRV.NOW
posted = (NOW - dt.timedelta(days=8)).isoformat()
rows = [{"short": f"QD-{i}", "channel": "main", "posted": posted, "yt_views": 1000, "category": "Film", "rel": 1.0, "format": "x"} for i in range(6)]
rows += [{"short": f"QD-{i + 10}", "channel": "music", "posted": posted, "yt_views": 100, "category": "Music", "rel": 5.0, "format": "x"} for i in range(6)]
assert DRV.dead_floor(rows) > 100, "pooled, the small channel's Shorts would all be dead"
assert DRV.dead(rows) == [], DRV.dead(rows)
rows[6]["yt_views"] = 3
assert [r["short"] for r in DRV.dead(rows)] == ["QD-10"], DRV.dead(rows)         # dead against the music channel's own floor
main_rows = [r for r in rows if r["channel"] == "main"]
assert DRV.dead([{k: v for k, v in r.items() if k != "channel"} for r in main_rows]) == []        # rows from before the column are the main channel's

# 26 October: the verdicts pool every channel's Shorts (rel is per channel already); each row keeps its own channel's floor
rows[6]["yt_views"] = 100
for i, r in enumerate(rows): r["category"] = ("Film", "Music")[i % 2]                       # both channels show both values
pooled = {(t["feature"], t["value"]): t for t in DRV.analyse(rows, {}, "2026-10-25")[0]}
assert ("category", "Music") in pooled and ("category", "Film") in pooled, sorted(pooled)       # the music channel's rows count
assert pooled[("category", "Music")]["n"] == 6 and pooled[("category", "Film")]["n"] == 6, pooled
assert ("channel", "music") not in pooled                                                   # the channel is not a test of its own
solo = rows + [{"short": f"QD-{50 + i}", "channel": "irl", "posted": posted, "yt_views": 100, "category": "Film", "rel": 9.0, "format": "x"} for i in range(3)]
assert {(t["feature"], t["value"]): t for t in DRV.analyse(solo, {}, "2026-10-25")[0]}[("category", "Film")]["n"] == 6   # a channel with one value says nothing about it (contrast)
assert DRV.floor_of({"main": 200.0, "music": 20.0}, rows[6]) == 20.0 and DRV.floor_of(200.0, rows[6]) == 200.0
# a choice is paused on its Shorts' views against their own channel's floor: 100 views on music (floor 20) is healthy, so
# the music rows do not pull the Film+Music pool under the main channel's floor; 3 views there would
pauses = {}
grp = main_rows + [r for r in rows if r["channel"] == "music"]
floors = {"main": 200.0, "music": 20.0}
assert DRV.pause_state("x|y", grp, floors, pauses, "2026-10-25") == (None, ""), pauses
for r in rows:
    if r["channel"] == "music": r["yt_views"] = 3
state, why = DRV.pause_state("x|y", grp, floors, pauses, "2026-10-25")
assert state is None, (state, why)          # 6 main rows at 1000 views and 6 music rows at 3: the median straddles, not under
grp2 = [dict(r, posted=(NOW - dt.timedelta(days=8 + i % 2)).isoformat()) for i, r in enumerate(rows) if r["channel"] == "music"]
assert DRV.pause_state("x|z", grp2, floors, {}, "2026-10-25")[0] == "pause"                  # all music rows under its floor, 2 UK days
assert DRV.pause_state("x|z", grp2, floors, {}, "2026-10-25")[1].endswith("under three quarters of the floor of 200")
for r in rows:
    if r["channel"] == "music": r["yt_views"] = 100

# the ledger: every metric is the main channel's, except a change that adds a channel (its target is the whole line's)
C.ROOT = SCRATCH / "chg"; (C.ROOT / "analytics").mkdir(parents=True)
today = dt.date(2026, 11, 20)
def srow(ch, day, subs, views=1000): return {"short": f"{ch}-{day}-{subs}", "channel": ch, "posted": f"{day}T12:00:00+00:00", "yt_subs_gained": subs, "yt_views": views}
srows = [srow("main", today - dt.timedelta(days=d), 1) for d in (15, 16, 17, 18, 19, 20)]       # before
srows += [srow("main", today - dt.timedelta(days=d), 1) for d in (8, 9, 10, 11, 12, 13)]        # after, the main channel
srows += [srow("music", today - dt.timedelta(days=d), 5) for d in (8, 9, 10, 11, 12, 13)]       # after, the new channel
buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=list(srows[0])); w.writeheader(); w.writerows(srows)
(C.ROOT / "analytics" / "shorts.csv").write_text(buf.getvalue())
D = C.Data(today=today, now=dt.datetime(2026, 11, 20, 12, tzinfo=dt.timezone.utc))
assert len(D.shorts) == 12 and len(D.all_shorts) == 18 and len(D.line().shorts) == 18, (len(D.shorts), len(D.all_shorts))
new = lambda area: {"id": "CH-1", "date": "2026-11-06", "area": area, "change": "c", "hypothesis": "h", "target": "subs_per_1k", "guardrails": "",
                    "before_days": "7", "after_days": "7", "check_on": "2026-11-13", "status": "live", "verdict": "", "result": "", "by": "Claude (session)"}
r = C.judge(new("shorts"), D, []); assert r["verdict"] == "no change", r["result"]          # the main channel alone: 1.00 before and after
r = C.judge(new("channels"), D, []); assert r["verdict"] == "better" and "3.00" in r["result"], r["result"]       # the line: 1.00 to 3.00
assert "channels" in C.AREAS
print("8 analytics, drivers and changes ok")

# ---------- 9. writer.py ----------
import writer as W
W.ROOT = SCRATCH / "wr"
for d in ("queue", "ready", "done", "failed", "reserve"): (W.ROOT / "boards" / d).mkdir(parents=True)
(W.ROOT / "analytics").mkdir()
W.channel_signed_in = lambda ch: ch == "music"
W.validate.check = lambda b, p=None: ([], [])
W.translations = lambda b: {}
cfg_music = W.CFG["shorts_channels"]["music"]
mon, fri = dt.date(2026, 10, 26), dt.date(2026, 10, 30)
assert W.pick_series(cfg_music, {"topic": "Taylor Swift's new album tops the charts"}, mon, 0) == "Chart Watch"
assert W.pick_series(cfg_music, {"topic": "Sabrina Carpenter new single out now"}, fri, 0) == "New Music Friday"
assert W.pick_series(cfg_music, {"topic": "Sabrina Carpenter new single out now"}, mon, 0) == "Song Secrets", "New Music Friday only on a Friday"
assert W.pick_series({"series": []}, {"topic": "x"}, mon, 0) is None
cfg_irl, cfg_clips = W.CFG["shorts_channels"]["irl"], W.CFG["shorts_channels"]["clips"]       # 26 October: the clip channels write original Shorts
assert W.pick_series(cfg_irl, {"topic": "Octopus escapes its tank", "category": "Animals"}, mon, 0) == "Wild World"      # a series bound to a category
assert W.pick_series(cfg_irl, {"topic": "The oldest cheese", "category": "Food"}, mon, 0) == "Food Facts"
assert W.pick_series(cfg_irl, {"topic": "A record crowd", "category": "Entertainment"}, mon, 0) == "Did You Know", "the plain series takes the rest"
assert W.pick_series(cfg_irl, {"topic": "A record crowd", "category": "Entertainment"}, mon, 1) == "Did You Know"
assert W.pick_series(cfg_clips, {"topic": "Hadron collider", "category": "Science"}, mon, 0) == "Big Science"
assert W.pick_series(cfg_clips, {"topic": "Hadron collider", "category": "Tech"}, mon, 0) == "Big Science"
assert W.pick_series(cfg_clips, {"topic": "Derby day", "category": "Sport"}, mon, 3) == "Match Day"
assert sorted(W.line_channels()) == ["music"], "only music is signed in in this test; gaming, irl and clips wait for their sign-in like any other"
note = W.channel_note("irl", cfg_irl, "Wild World", 3)
assert "Quickplay IRL Clips" in note and "dinner table" in note and "Wild World #3" in note, note
note = W.channel_note("x", {"name": "X", "categories": ["Cars", "History"]}, None, 0)
assert "Cars, History" in note and "#" not in note, note
assert W.main_board({}) and W.main_board({"channel": "main"}) and not W.main_board({"channel": "music"})

def pack(topic, cat, n=3, signal="Apple Music chart"):
    return {"topic": topic, "category": cat, "signal": signal, "verified": [{"claim": f"c{i}", "sources": [1]} for i in range(n)], "one_source": [],
            "sources": [["T", f"https://example.com/{topic.replace(' ', '-')}", "Ex", ""]]}
packs = [pack("Chart topper alpha", "Music"), pack("Film thing", "Film"), pack("Second song story", "Music", signal="evergreen question"),
         pack("Third song", "Music", n=1)]
asked = []
def fake_write_one(p, sid, day, head, extra="", kind="news", tests=None):
    asked.append((p["topic"], sid, extra))
    return {"id": sid, "created": str(day), "format": "one_detail", "category": p["category"], "beats": [{"say": "x"}],
            "meta": {"title": f"{p['topic']} 🎵", "sources": p["sources"], "hashtags": [], "summary": "s"}}, "fake"
W.write_one = fake_write_one
ever_asked = []
def no_evergreen(kinds, seen, trending=(), cats=None, lane=""): ever_asked.append((list(kinds), cats)); return []
W.evergreen_packs = no_evergreen                     # offline: the evergreen fill asks nothing until the check below
day = dt.date(2026, 10, 27)
W.DAY["boards"] = [{"id": "QD-40", "category": "Music", "meta": {"title": "Chart topper alpha explained", "sources": [["T", "https://example.com/Chart-topper-alpha"]]}}]
state = {"n": 100}
out = W.ROOT / "boards" / "queue"
got = W.extra_channel_boards(day, "morning", packs, "HEAD", state, out)
files = sorted(out.glob("QD-*.json"))
assert [f.stem for f in files] == ["QD-100", "QD-101"] and state["n"] == 102, (files, state)
b0, b1 = [json.loads(f.read_text()) for f in files]
assert [asked[0][0], asked[1][0]] == ["Second song story", "Chart topper alpha"], asked      # the subject the main channel has not covered goes first
assert b0["channel"] == "music" and b1["channel"] == "music" and b0["kind"] == "news" and "test" in b0
assert b0["channel_series"] == "Song Secrets #1" and b0["meta"]["title"].startswith("Song Secrets #1: Second song story")
assert b1["channel_series"] == "Chart Watch #1" and b1["meta"]["title"].startswith("Chart Watch #1: "), b1["meta"]["title"]
assert "Quickplay Music" in asked[0][2] and "Song Secrets #1" in asked[0][2] and "OTHER CHANNEL" not in asked[0][2], asked[0][2]
assert "OTHER CHANNEL" in asked[1][2] and "Chart Watch #1" in asked[1][2], asked[1][2]       # the overlap with the main channel's Short, said to the writer
assert "never gossip about private lives" in asked[0][2], "the channel's brief (config) reaches the writer"
assert all(len(b["meta"]["title"]) <= 70 for b in (b0, b1)) and all("franchise" not in b and "series" not in b for b in (b0, b1))
# one pooled model (26 October): the channel's first Short of the day explores, the next takes the round, the look and the hour
assert b0["test"].get("explore") == "yes" and not ({"fx_energy", "fx_slot", "round"} & set(b0["test"])), b0["test"]
assert {"fx_energy", "fx_grade", "fx_opening", "fx_slot", "round"} <= set(b1["test"]) and b1["test"]["explore"] == "no", b1["test"]
assert not ({"series", "franchise"} & set(b1["test"])), b1["test"]                          # always its own series
for b, a in ((b0, asked[0]), (b1, asked[1])):                                              # the subscribe line is tested on every channel
    assert b["test"].get("sub_push") in ("spoken", "none") or b["test"].get("explore") == "yes", b["test"]
    if b["test"].get("sub_push") == "spoken": assert "SUBSCRIBE LINE" in a[2] and f'our "{b["channel_series"].split(" #")[0]}" series' in a[2], a[2]
    if b["test"].get("sub_push") == "none": assert "tests having none" in a[2], a[2]
assert ever_asked and ever_asked[-1][1] == ["Music"], ever_asked                            # the places the news left: evergreen in the channel's own categories
assert [x["id"] for x in got] == ["QD-100", "QD-101"]
# the main channel's counters ignore them
assert W.recent() == [] and W.day_boards(day) == [] and W.day_formats(day) == []
for f in files: b = json.loads(f.read_text()); b["created"] = str(W.NOW.date()); f.write_text(json.dumps(b))
assert W.recent() == [], "recent(): what the main channel covered, not the music channel's"
b2 = dict(b0, id="QD-102", channel=None); b2.pop("channel"); b2["created"] = str(W.NOW.date())
(out / "QD-102.json").write_text(json.dumps(b2)); assert len(W.recent()) == 1 and len(W.day_boards(W.NOW.date())) == 1; (out / "QD-102.json").unlink()
# again in the same run window: the same two subjects are not written twice, and the channel's room for the day is counted
n = len(asked)
assert W.extra_channel_boards(day, "afternoon", packs, "HEAD", state, out) == [] and len(asked) == n
# a new chart subject: the next number of its series
got = W.extra_channel_boards(day, "afternoon", packs + [pack("Another chart story", "Music")], "HEAD", state, out)
assert [b["channel_series"] for b in got] == ["Chart Watch #2"], got
# the room for the day: six, then no more, whatever the pool
for name in ("Orchid anthem", "Velvet harbour", "Granite lullaby", "Copper skyline", "Marble echo", "Willow thunder"):
    W.extra_channel_boards(day, "evening", [pack(name, "Music")], "HEAD", state, out)
assert len(W.channel_boards("music", day)) == 6, len(W.channel_boards("music", day))
# a day with no news in the channel's categories: evergreen packs of those categories fill the places, each in its own kind
def some_evergreen(kinds, seen, trending=(), cats=None, lane=""):
    ever_asked.append((list(kinds), cats))
    assert cats == ["Music"] and all(k in ("evergreen", "top list", "true story") for k in kinds) and kinds, (kinds, cats)
    assert any("Chart topper alpha" in t for t, _, _ in seen), "what the channel and the main channel covered is passed as seen"
    return [dict(pack("Ten longest number ones", "Music", n=5, signal="evergreen top list"), kind="top list"),
            dict(pack("Why vinyl came back", "Music", signal="evergreen question"), kind="evergreen")][:len(kinds)]
W.evergreen_packs = some_evergreen
n = len(asked)
got = W.extra_channel_boards(dt.date(2026, 10, 29), "morning", [pack("Film thing", "Film")], "HEAD", state, out)
assert got and got[0]["kind"] == "top list" and got[0]["channel"] == "music" and len(asked) > n, got
assert W.KIND_NOTE["top list"][:60] in asked[n][2] and "Quickplay Music" in asked[n][2], asked[n][2]
assert got[0]["test"].get("sub_push") in ("spoken", "none") or got[0]["test"].get("explore") == "yes"
assert all(b["kind"] in ("top list", "evergreen") and b.get("channel_series") for b in got), got
W.evergreen_packs = no_evergreen
# not signed in: nothing is written, nothing asked
W.channel_signed_in = lambda ch: False
n, files_before = len(asked), len(list(out.glob("QD-*.json")))
assert W.extra_channel_boards(dt.date(2026, 10, 28), "morning", packs, "HEAD", state, out) == [] and len(asked) == n and len(list(out.glob("QD-*.json"))) == files_before
assert W.line_channels() == {} and W.line_channels(mirror=True) == {}
print("9 writer ok")
print("channels ok")
