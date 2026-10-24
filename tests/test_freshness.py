"""Offline test of the freshness gate (Charlie, 24 October: content that missed its window goes out later only with the
data's say-so): pipeline/freshness.py's every branch with stubbed HTTP, plan.py giving an expired board's upload place
and slot to the next one, and the clips rules (the post time on social rows, the 30-hour guard on uploads, the heat a late
test clip needs to be promoted, late submit rows expired unless the clip has views)."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, csv, datetime as dt, io, json, os, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import freshness as FR

FR.ROOT = SCRATCH; FR.LOG = SCRATCH / "analytics" / "late_uploads.csv"
(SCRATCH / "analytics").mkdir(); (SCRATCH / "trends").mkdir()
UK = FR.UK
AT = dt.datetime(2026, 10, 24, 15, 0, tzinfo=UK)          # Saturday 24 October, 15:00 UK


def board(kind="news", created="2026-10-23", say="The trailer is out and it is huge.", title="GTA 6 trailer lands",
          tags=("GTA 6 trailer",), sources=(("Guardian, GTA, 2026-10-23", "https://www.theguardian.com/games/gta"),), **kw):
    return {"id": kw.pop("id", "QD-900"), "kind": kind, "created": created,
            "meta": {"title": title, "summary": "", "tags": list(tags), "sources": [list(s) for s in sources]},
            "beats": [{"say": say}], **kw}


class R:
    def __init__(self, ok=True, js=None, text=""): self.ok, self._js, self.text = ok, js, text
    def json(self): return self._js


def stub(reads=None, article=None, news=0, calls=None):
    """A requests.get stand-in: Wikipedia search, page views and Google News answers."""
    def get(url, params=None, headers=None, timeout=None):
        if calls is not None: calls.append(url)
        if "w/api.php" in url: return R(js=[params["search"], [article] if article else []])
        if "pageviews" in url: return R(js={"items": [{"views": v} for v in (reads or [])]}) if reads else R(ok=False)
        if "news.google.com" in url: return R(text="<rss>" + "<item>x</item>" * news + "</rss>")
        raise AssertionError(url)
    return get


def nonet(*a, **k): raise AssertionError("no network expected")


# 1. on time, evergreen, the reserve, dry and private runs: nothing to decide, nothing logged
assert FR.check(board(created="2026-10-24"), AT, nonet) is None
assert FR.check(board(created="2026-10-25"), AT, nonet) is None                    # written for tomorrow (the evening run)
for k in ("evergreen", "true story", "top list"): assert FR.check(board(kind=k, created="2026-10-01"), AT, nonet) is None
assert FR.check(board(created="2026-10-01", reserve=True), AT, nonet) is None
assert FR.check(board(created="2026-10-01", mode="dry"), AT, nonet) is None and FR.check(board(created="2026-10-01", mode="private"), AT, nonet) is None
assert FR.check(board(created="not a date"), AT, nonet) is None
assert not FR.LOG.exists()
print("1 on time ok")

# 2. too late whatever the signals: 3 days for news and watchlist Shorts, 2 for breaking
out = FR.check(board(created="2026-10-21"), AT, nonet)
assert out == {"alive": False, "evidence": "3 days late: news Shorts expire after 2", "days_late": 3}, out
assert FR.check(board(kind="breaking", created="2026-10-22"), AT, nonet)["alive"] is False
assert FR.check(board(kind="evergreen", watch="GTA 6", created="2026-10-21"), AT, nonet)["alive"] is False      # a watchlist Short is timely
print("2 expiry ok")

# 3. words that are no longer true: day words once a day late, week words once the week has changed
out = FR.check(board(say="Tonight the trailer drops at eight."), AT, nonet)
assert out["alive"] is False and '"Tonight"' in out["evidence"] and "Friday 23 October" in out["evidence"], out
assert FR.check(board(say="Only three days to go until launch."), AT, nonet)["alive"] is False
assert FR.check(board(title="Out today: the trailer"), AT, nonet)["alive"] is False
mon = dt.datetime(2026, 10, 26, 12, 0, tzinfo=UK)
out = FR.check(board(created="2026-10-25", say="The biggest launch this week."), mon, nonet)       # Sunday's words on Monday
assert out["alive"] is False and "week has changed" in out["evidence"], out
CALLS = []
out = FR.check(board(created="2026-10-26", say="The biggest launch this week."), mon + dt.timedelta(days=1), stub(news=12, calls=CALLS))
assert out["alive"] is True and CALLS, out                    # Monday's "this week" on Tuesday: still true, the evidence decides
print("3 words ok")

# 4. alive: in today's trends (no network), Wikipedia reads well above usual, or plenty of news; otherwise expired
(SCRATCH / "trends" / "latest.json").write_text(json.dumps({"google_trends": {"GB": [{"q": "gta 6 trailer", "news": []}]}, "wikipedia_top": [], "youtube_charts": {}}))
out = FR.check(board(), AT, nonet)
assert out["alive"] is True and "today's trends" in out["evidence"], out
(SCRATCH / "trends" / "latest.json").write_text(json.dumps({"google_trends": {"GB": [{"q": "gta 6 trailers galore"}]}}))
assert FR.in_trends("GTA 6 trailer") is False         # whole words only: "trailers" is not "trailer"
assert FR.in_trends("gta") is False                    # under 4 letters: never a match
out = FR.check(board(), AT, stub(reads=[2000] * 14 + [9000], article="Grand Theft Auto VI"))
assert out["alive"] is True and "4.5x" in out["evidence"] and "Grand Theft Auto VI" in out["evidence"], out
out = FR.check(board(sources=(("Wikipedia", "https://en.wikipedia.org/wiki/Grand_Theft_Auto_VI"),)), AT, stub(reads=[2000] * 14 + [2500], news=3))
assert out["alive"] is False and "1.2x" in out["evidence"] and "3 news articles" in out["evidence"], out          # not surging, little news
out = FR.check(board(), AT, stub(reads=[200] * 14 + [900], article="Some page", news=10))
assert out["alive"] is True and "10 news articles" in out["evidence"], out          # 900 reads is under 1,000: the news carries it
out = FR.check(board(), AT, stub(article=None, news=0))
assert out == {"alive": False, "evidence": "0 news articles on \"GTA 6 trailer\" in 24 hours", "days_late": 1}, out
assert FR.subject_of(board(tags=(), title="Raye's song hits a billion 🎉 streams today"))[1] == "Raye's song hits a billion streams"
print("4 evidence ok")

# 5. the data decides the rule itself: a "cut back" or "stop" on late Shorts ends late uploads altogether
(SCRATCH / "analytics" / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict\nlate,Posted late,late,6,0.62,0.5,cut back\n")
out = FR.check(board(), AT, nonet)
assert out["alive"] is False and "cut back" in out["evidence"] and "6 late Shorts" in out["evidence"], out
(SCRATCH / "analytics" / "drivers.csv").write_text("feature,feature_label,value,n,lift,median_rel,verdict\nlate,Posted late,late,6,1.3,1.2,push\n")
assert FR.check(board(), AT, stub(news=11))["alive"] is True
print("5 verdict ok")

# 6. a check that breaks never lets a late Short through, and never stops the run for one on time
bad = board(); bad["meta"] = 5
out = FR.safe_check(bad, AT, nonet)
assert out["alive"] is False and "AttributeError" in out["evidence"], out
assert FR.safe_check(dict(bad, created="2026-10-24"), AT, nonet) is None
assert FR.safe_check(dict(bad, kind="evergreen"), AT, nonet) is None
print("6 safe ok")

# 7. the log: one line per decision, the same decision on the same board the same day once; record=False logs nothing
FR.LOG.unlink()
FR.check(board(id="QD-901", created="2026-10-21"), AT, nonet); FR.check(board(id="QD-901", created="2026-10-21"), AT, nonet)
FR.check(board(id="QD-902", created="2026-10-21"), AT, nonet, record=False)
rows = list(csv.DictReader(FR.LOG.open()))
assert [(r["id"], r["decision"], r["days_late"], r["where"]) for r in rows] == [("QD-901", "expired", "3", "render")], rows
assert list(rows[0]) == FR.FIELDS
assert FR.log_row("QD-901", "t", "news", 3, "posted late", "x", "render") and len(list(csv.DictReader(FR.LOG.open()))) == 2
assert FR.log_row("QD-901", "t", "news", 3, "posted late", "x", "publish")                 # another place, another line
print("7 log ok")

# 8. plan.py: an expired board takes neither an upload place nor a slot; a late but alive one carries its evidence
import plan as P, validate, background, looks
P.ROOT = SCRATCH / "plan"; (P.ROOT / "boards" / "queue").mkdir(parents=True); (P.ROOT / "status").mkdir()
(P.ROOT / "analytics").mkdir()
uk_today = dt.datetime.now(dt.timezone.utc).astimezone(UK).date()
(P.ROOT / "status" / f"weekly-{uk_today}.json").write_text(json.dumps({"video": "x"}))      # a Sunday keeps no place back
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(24)]
P.LEAD = dt.timedelta(hours=1)
P.schedule_state = lambda now: (set(), 0, True)
P.LIMIT = 1
validate.check = lambda b, p=None: ([], [])
background.wanted = lambda b, cfg: False
old = (uk_today - dt.timedelta(days=5)).isoformat(); new = (uk_today + dt.timedelta(days=1)).isoformat()     # tomorrow: on time at any hour
log_before = FR.LOG.read_text()
for sid, created in (("QD-001", old), ("QD-002", new)):
    (P.ROOT / "boards" / "queue" / f"{sid}.json").write_text(json.dumps({**board(id=sid, created=created), "beats": [{"say": "x"}]}))
buf = io.StringIO()
with contextlib.redirect_stdout(buf): P.main()
jobs = json.loads(buf.getvalue().strip().split("boards=", 1)[1])
by = {j["id"]: j for j in jobs}
assert by["QD-001"]["mode"] == "reject" and by["QD-001"]["expired"] and "days late: news Shorts expire" in by["QD-001"]["errors"], by
assert by["QD-002"]["mode"] == "schedule" and by["QD-002"]["slot"], by          # the one place went to the board on time
real = FR.safe_check
FR.safe_check = lambda b, at=None, get=None, where="render", record=True: {"alive": True, "evidence": "in today's trends", "days_late": 1} if b["id"] == "QD-001" else None
P.LIMIT = 2
with contextlib.redirect_stdout(buf := io.StringIO()): P.main()
by = {j["id"]: j for j in json.loads(buf.getvalue().strip().split("boards=", 1)[1])}
assert by["QD-001"]["late"]["evidence"] == "in today's trends" and by["QD-001"]["slot"] != by["QD-002"]["slot"], by
FR.safe_check = real
assert FR.LOG.read_text() == log_before          # the plan job cannot commit: record.py logs its decisions instead
print("8 plan ok")

# 9. run_board and record.py: an expired board's status and its folder, and the decision logged where it is committed
import run_board as RB, record as RC
RB.ROOT = RC.ROOT = SCRATCH / "plan"
os.environ["JOB_JSON"] = json.dumps({**by["QD-001"], "mode": "reject", "expired": True, "errors": "5 days late: news Shorts expire after 2",
                                     "late": {"alive": False, "evidence": "5 days late: news Shorts expire after 2", "days_late": 5}})
sys.argv = ["run_board.py", "x"]
with contextlib.redirect_stdout(io.StringIO()): RB.main()
st = json.loads((RB.ROOT / "result" / "QD-001" / "status.json").read_text())
assert st["state"].startswith("expired: 5 days late") and st["late"]["days_late"] == 5, st
os.environ.pop("JOB_JSON")
FR.LOG.unlink()
with contextlib.redirect_stdout(io.StringIO()): RC.main(RB.ROOT / "result")
assert (RC.ROOT / "boards" / "expired" / "QD-001.json").exists() and not (RC.ROOT / "boards" / "queue" / "QD-001.json").exists()
rows = list(csv.DictReader(FR.LOG.open()))
assert [(r["id"], r["decision"], r["where"]) for r in rows] == [("QD-001", "expired", "render")], rows
print("9 record ok")

# 10. clips: social rows carry the post time; a made clip over 30 hours old is never uploaded; a test clip over 30 hours old
# is promoted only when its subject is hot; a late submit row expires unless its clip has views
import clips as C
assert len(C.posted_uk()) == 16 and C.posted_uk()[10] == " "
import submit as SB
assert SB.due([{"public_at_uk": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).astimezone(UK).strftime("%Y-%m-%d %H:%M"),
                "video": "https://www.instagram.com/reel/abc/", "platform": "instagram", "submitted": ""}])         # Instagram rows are due now
C.NOW = dt.datetime(2026, 10, 24, 18, 0, tzinfo=dt.timezone.utc)
assert round(C.made_hours({"made": (C.NOW - dt.timedelta(hours=31)).isoformat()})) == 31 and C.made_hours({"made": "t"}) == 0.0
C.ROOT = SCRATCH / "clips_root"; (C.ROOT / "clips").mkdir(parents=True)
C.PLANS = C.ROOT / "clips" / "plans"; C.PLANS.mkdir(); C.OUT = C.ROOT / "clips" / "out"; C.OUT.mkdir(); C.STATE = C.ROOT / "clips" / "state"
for i in (1, 2): (C.OUT / f"speed-expedia-{i}.mp4").write_bytes(b"x")
(C.PLANS / "speed-expedia.json").write_text(json.dumps({"moments": [
    {"id": "speed-expedia-1", "made": (C.NOW - dt.timedelta(hours=40)).isoformat(timespec="minutes"), "file": "speed-expedia-1.mp4", "hook": "a", "title": "old one", "start": 0, "end": 30},
    {"id": "speed-expedia-2", "made": (C.NOW - dt.timedelta(hours=1)).isoformat(timespec="minutes"), "file": "speed-expedia-2.mp4", "hook": "b", "title": "new one", "start": 40, "end": 70}]}))
Y = sys.modules.get("youtube") or types.ModuleType("youtube"); sys.modules["youtube"] = Y
UPS = []
Y.upload = lambda client, path, *a, **k: (UPS.append(str(path).rsplit("/", 1)[-1]), f"vid{len(UPS)}")[1]
C.gh = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr="")
C.clips_client = lambda ch: ch; C.add_rows = lambda rows: None; C.ceiling_learn = lambda *a, **k: None
C.campaign_channels = lambda cid: ["clips"]
import quota
quota.allow, quota.spend = (lambda *a, **k: True), (lambda *a, **k: None)
FR.LOG.unlink()
C.upload("speed-expedia", mode="private")
assert UPS == ["speed-expedia-2.mp4"], UPS
rows = list(csv.DictReader(FR.LOG.open()))
assert [(r["id"], r["decision"], r["where"]) for r in rows] == [("speed-expedia-1", "expired", "clips upload")], rows

CALLS = []
class _V:
    def update(self, part, body): CALLS.append(body["id"]); return types.SimpleNamespace(execute=lambda: {})
C.clips_client = lambda ch: types.SimpleNamespace(videos=lambda: _V())
(C.PLANS / "speed-expedia.json").write_text(json.dumps({"moments": [
    {"id": "speed-expedia-3", "video": "v3", "publish_at": "private", "channel": "clips", "title": "late test", "uploaded": (C.NOW - dt.timedelta(hours=40)).isoformat(timespec="minutes")},
    {"id": "speed-expedia-4", "video": "v4", "publish_at": "private", "channel": "clips", "title": "fresh test", "uploaded": (C.NOW - dt.timedelta(hours=3)).isoformat(timespec="minutes")}]}))
HEAT = {"h": (0.3, ["Wikipedia 900 views a day"])}
SB.heat = lambda subject: HEAT["h"]
FR.LOG.unlink()
assert C.promote_tests(48) == 1 and CALLS == ["v4"], CALLS                   # not hot: the 40-hour-old test stays private
r = next(csv.DictReader(FR.LOG.open()))
assert (r["id"], r["decision"], r["where"]) == ("speed-expedia-3", "expired", "clips promote") and "heat 0.3" in r["evidence"], r
HEAT["h"] = (1.4, ["in Google Trends today"])
assert C.promote_tests(48) == 1 and CALLS == ["v4", "v3"], CALLS              # hot: it joins the batch, with the reason kept
assert [x["decision"] for x in csv.DictReader(FR.LOG.open())] == ["expired", "posted late"]

C.CFG = dict(C.CFG, campaigns={"speed-expedia": {"min_views": 10000}, "tdr-mitch": {"min_views": 5000}, "small": {"min_views": 0}})
uk = lambda h: (C.NOW - dt.timedelta(hours=h)).astimezone(UK).strftime("%Y-%m-%d %H:%M")
sub_rows = [
    {"clip": "a", "campaign": "speed-expedia", "platform": "youtube", "video": "https://youtube.com/shorts/vidA", "public_at_uk": uk(50), "submitted": ""},
    {"clip": "b", "campaign": "tdr-mitch", "platform": "youtube", "video": "https://youtube.com/shorts/vidB", "public_at_uk": uk(50), "submitted": "failed: no button"},
    {"clip": "c", "campaign": "tdr-mitch", "platform": "youtube", "video": "https://youtube.com/shorts/vidC", "public_at_uk": uk(10), "submitted": ""},
    {"clip": "d", "campaign": "small", "platform": "instagram", "video": "https://www.instagram.com/reel/D/", "public_at_uk": uk(60)[:10], "submitted": ""},
    {"clip": "e", "campaign": "tdr-mitch", "platform": "youtube", "video": "https://youtube.com/shorts/vidE", "public_at_uk": uk(50), "submitted": "2026-10-22 19:05"},
    {"clip": "f", "campaign": "tdr-mitch", "platform": "youtube", "video": "https://youtube.com/shorts/vidF", "public_at_uk": "private (test)", "submitted": ""},
    {"clip": "g", "campaign": "speed-expedia", "platform": "youtube", "video": "https://youtube.com/shorts/vidG", "public_at_uk": uk(50), "submitted": "failed: past the 30-minute window"}]
with (C.ROOT / "clips" / "submit.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=C.SUBMIT_FIELDS, extrasaction="ignore"); w.writeheader(); w.writerows(sub_rows)
with (C.ROOT / "clips" / "stats.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["clip", "video", "views", "instagram", "ig_views"]); w.writeheader()
    w.writerows([{"clip": "a", "video": "vidA", "views": "1500"}, {"clip": "b", "video": "vidB", "views": "40"},
                 {"clip": "d", "video": "vidD", "views": "0", "instagram": "https://www.instagram.com/reel/D", "ig_views": "150"}])
FR.LOG.unlink()
assert C.expire_rows() == 1
got = {r["clip"]: r["submitted"] for r in csv.DictReader((C.ROOT / "clips" / "submit.csv").open())}
assert got["a"] == "" and got["c"] == "" and got["d"] == "" and got["e"] == "2026-10-22 19:05" and got["f"] == "", got   # views, fresh, done, private
assert got["b"].startswith("expired: 50h old with 40 views (a late row needs 500)"), got
assert got["g"] == "failed: past the 30-minute window", got
dec = {r["id"]: r["decision"] for r in csv.DictReader(FR.LOG.open())}
assert dec == {"a": "posted late", "b": "expired", "d": "posted late"}, dec
assert C.expire_rows() == 0                                                          # once only
assert not SB.due([r for r in csv.DictReader((C.ROOT / "clips" / "submit.csv").open()) if r["clip"] == "b"])     # never submitted now
print("10 clips ok")
print("freshness ok")
