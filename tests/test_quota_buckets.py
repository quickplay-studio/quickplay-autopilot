"""Offline test of the YouTube allowance guard with the API's buckets (since 1 June 2026): uploads (videos.insert) and
searches (search.list) each have their own 100 calls a day, everything else shares 10,000 units, and all four channels
draw on the one project. A clip upload keeps room for the main channel's Shorts still to come; a quotaExceeded on an
upload stops uploads only; records written before the change count each upload once."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, os, sys
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import quota as Q

Q.ROOT, Q.DIR = SCRATCH, SCRATCH / "status" / "quota"
(SCRATCH / "status").mkdir(parents=True)
Q.VOLUME_P, Q.LIMIT_P = SCRATCH / "volume.json", SCRATCH / "limit.json"
Q.CFG = dict(Q.CFG, shorts_per_day=15, daily_limit=40, youtube_quota_per_day=10000, youtube_quota_margin=1000)
Q.MODE, Q.BUCKETS, Q.COST = "buckets", {"upload": 100, "search": 100}, dict(Q.COST, upload=100, search=100)
os.environ["GITHUB_WORKFLOW"] = "clips"
rec = lambda name: json.loads((Q.DIR / f"{name}.json").read_text())

# 1. an upload is a call in its bucket, not 100 units; a search's video details stay in the units
Q.spend(100, "upload"); Q.spend(102, "competitor search"); Q.spend(50, "clip promote")
r = rec("clips")
assert r["calls"] == {"upload": 1, "search": 1} and r["units"] == 52, r
assert Q.state() == (52, False) and Q.calls("upload") == 1 and Q.calls("search") == 1
print("1 spend ok")

# 2. a clip upload keeps room for the Shorts still to come (15 planned + the weekly video, none made yet) and a margin
assert Q.uploads_left() == 16
for _ in range(79): Q.spend(100, "upload")                    # 80 upload calls made today across the channels
assert Q.allow(100, "clip upload")                            # 80 + 16 + 3 + 1 = 100: fits
Q.spend(100, "upload")
assert not Q.allow(100, "clip upload")                        # 81: would leave a Short unable to upload
assert Q.allow(50, "clip promote") and Q.allow(50, "clip comment")    # the shared units are nowhere near full
for i in range(3): (SCRATCH / "status" / f"QD-9{i:02d}.json").write_text(json.dumps({"uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat()}))
assert Q.uploads_left() == 13 and Q.allow(100, "clip upload")   # three Shorts are up: three more places for clips
print("2 upload bucket ok")

# 3. the shared units: an extra fits while units spent + margin + the extra stay under 10,000 (uploads no longer count)
os.environ["GITHUB_WORKFLOW"] = "engage"
Q.spend(8900, "engagement")
assert Q.state()[0] == 8952 and not Q.allow(100, "comment replies") and Q.allow(40, "series link")
print("3 shared units ok")

# 4. a quotaExceeded on an upload stops uploads only
os.environ["GITHUB_WORKFLOW"] = "render"
Q.exhausted("upload")
assert Q.bucket_refused("upload") and not Q.allow(100, "clip upload") and Q.allow(40, "clip comment")
print("4 refusal ok")

# 5. a record written before the buckets (24 October's clips record) counts its uploads once, also after a new upload
for p in Q.DIR.glob("*.json"): p.unlink()
(Q.DIR / "clips.json").write_text(json.dumps({"day": Q.today(), "units": 3950, "by": {"clip promote": 1400, "clip demote": 850, "upload": 1700}}))
(Q.DIR / "trends.json").write_text(json.dumps({"day": Q.today(), "units": 1326, "by": {"competitor search": 1326}}))
(Q.DIR / "publish.json").write_text(json.dumps({"day": Q.today(), "units": 200, "by": {"upload": 200}, "exhausted": "2026-10-24T10:00"}))
assert Q.calls("upload") == 19 and Q.calls("search") == 13 and Q.state() == (2250 + 26, False), (Q.calls("upload"), Q.state())
assert Q.bucket_refused("upload")                              # an old refusal was an upload's
os.environ["GITHUB_WORKFLOW"] = "clips"
Q.spend(100, "upload")
assert Q.calls("upload") == 20 and rec("clips")["units"] == 2250 and rec("clips")["calls"] == {"upload": 18}, rec("clips")
print("5 old records ok")

# 6. youtube_quota_model "units": the old accounting, unchanged
Q.MODE = "units"
for p in Q.DIR.glob("*.json"): p.unlink()
Q.spend(100, "upload"); Q.spend(102, "competitor search")
assert rec("clips")["units"] == 202 and "calls" not in rec("clips") and Q.calls("upload") == 0
keep = Q.uploads_left() * 100 + 1000
assert Q.allow(10000 - 202 - keep, "clip comment") and not Q.allow(10000 - 202 - keep + 1, "clip comment")
Q.exhausted("upload"); assert not Q.allow(1, "clip comment")    # as before: any refusal stops every extra
Q.MODE = "buckets"
os.environ.pop("GITHUB_WORKFLOW", None)
print("quota buckets ok")
