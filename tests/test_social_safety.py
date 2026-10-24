"""Offline test of the 24 October social changes (pipeline/social.py, clips.py take): Facebook's short caption and its
probe (1 Reel a day until a week shows plays, then the ramp from that day), TikTok never choosing public by itself, the
24-hour draft count, posting only once TikTok confirms an upload, the spam stop, the read-only stats, and a clip take
that argues rather than narrates."""
import csv, datetime as dt, io, json, os, pathlib as _p, sys, tempfile, types
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
ISSUES = []                                  # never a real GitHub issue from a test: alerts is stubbed
_al = types.ModuleType("alerts"); _al.raise_issue = lambda t, b: ISSUES.append(t); _al.clear = lambda t, b: None
sys.modules["alerts"] = _al
import social as S

TMP = _p.Path(tempfile.mkdtemp(prefix="qp-social-"))
(TMP / "status").mkdir(); (TMP / "analytics").mkdir()
S.ROOT = TMP
NOW = dt.datetime.now(dt.timezone.utc)
iso = lambda t: t.isoformat(timespec="seconds")

# 1. Facebook gets the title and at most 3 hashtags; Instagram keeps its summary, YouTube line and 5 hashtags
board = {"meta": {"title": "GTA 6 trailer: the detail everyone missed", "summary": "A longer summary line.",
                  "hashtags": ["#GTA6", "#Rockstar", "#Gaming", "#Shorts", "#Trailer", "#GTAVI", "#News"]}}
fb = S.caption({}, board, "facebook")
assert fb == "GTA 6 trailer: the detail everyone missed\n\n#GTA6 #Rockstar #Gaming", fb
ig = S.caption({}, board, "instagram")
assert "A longer summary line." in ig and ig.count("#") == 5 and "#Shorts" not in ig, ig
print("1 facebook caption ok")

# 2. the Facebook probe: 1 a day while it runs, whatever the days since the first Reel; clears after a week with plays
S.CFG.update(facebook_probe=True, facebook_per_day=1, facebook_target=30, facebook_ramp_per_day=4,
             facebook_probe_min_reels=5, facebook_probe_min_plays=10)
rows = []
for i in range(10):
    sid = f"QD-80{i}"
    (TMP / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "facebook": {"video": f"v{i}", "at": iso(NOW - dt.timedelta(days=i + 1, hours=2))}}))
    rows.append({"short": sid, "fb_views": "0"})
def shorts_csv(rows):
    with (TMP / "analytics" / "shorts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["short", "fb_views", "views_3h"]); w.writeheader(); w.writerows(rows)
shorts_csv(rows)
assert S.ramp_cap("facebook") == 1                                   # without the probe: 1 + 4 x 10 days, capped at 30
state = json.loads((TMP / "status" / "facebook_probe.json").read_text())
assert state["started"] and not state.get("cleared") and state["reels_measured"] == 7, state     # posted 1 to 8 days ago
S.CFG["facebook_probe"] = False
assert S.ramp_cap("facebook") == 30
S.CFG["facebook_probe"] = True
# a week on, with plays: it clears, a line goes in decisions.csv, and the ramp counts from that day
(TMP / "status" / "facebook_probe.json").write_text(json.dumps({"started": iso(NOW - dt.timedelta(days=8)), "checked": "2000-01-01"}))
shorts_csv([dict(r, fb_views="25") for r in rows])
assert S.ramp_cap("facebook") == 1                                   # cleared today: day 0 of the ramp
state = json.loads((TMP / "status" / "facebook_probe.json").read_text())
assert state.get("cleared") and state["median_plays"] == 25, state
dec = list(csv.DictReader((TMP / "analytics" / "decisions.csv").open()))
assert len(dec) == 1 and dec[0]["area"] == "Facebook" and "cleared" in dec[0]["change"], dec
state["cleared"] = iso(NOW - dt.timedelta(days=3)); (TMP / "status" / "facebook_probe.json").write_text(json.dumps(state))
assert S.ramp_cap("facebook") == 1 + 4 * 3
# a week on, still no plays: it keeps running and decides nothing
(TMP / "status" / "facebook_probe.json").write_text(json.dumps({"started": iso(NOW - dt.timedelta(days=8)), "checked": "2000-01-01"}))
shorts_csv(rows)
assert S.ramp_cap("facebook") == 1 and not json.loads((TMP / "status" / "facebook_probe.json").read_text()).get("cleared")
assert len(list(csv.DictReader((TMP / "analytics" / "decisions.csv").open()))) == 1
print("2 facebook probe ok")

# 3. TikTok privacy: never public by itself
S.CFG["tiktok_privacy"] = ""
opts = {"privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "SELF_ONLY"]}
assert S.tt_privacy(opts) == "SELF_ONLY"
S.CFG["tiktok_privacy"] = "PUBLIC_TO_EVERYONE"                       # only when Charlie has chosen it
assert S.tt_privacy(opts) == "PUBLIC_TO_EVERYONE"
S.CFG["tiktok_privacy"] = ""
try: S.tt_privacy({"privacy_level_options": ["PUBLIC_TO_EVERYONE"]}); raise AssertionError("public chosen by itself")
except RuntimeError as e: assert "SELF_ONLY" in str(e)

class R:
    def __init__(self, j=None, status=200): self._j, self.status_code, self.ok, self.content, self.text = j or {}, status, status < 400, b"x", json.dumps(j or {})
    def json(self): return self._j
SENT = []
def fake_post(url, headers=None, json=None, timeout=None, params=None, data=None):
    SENT.append((url, json))
    if url.endswith("/creator_info/query/"):
        return R({"data": {**opts, "max_video_post_duration_sec": 600, "comment_disabled": False}, "error": {"code": "ok"}})
    if url.endswith("/video/init/"):
        return R(INIT)
    if url.endswith("/status/fetch/"):
        return R({"data": STATUS, "error": {"code": "ok"}})
    raise AssertionError(url)
S.requests.post = fake_post
S.requests.put = lambda url, data=None, timeout=None, headers=None: R({}, 201)
vid = TMP / "v.mp4"; vid.write_bytes(b"0" * 100)
INIT = {"data": {"publish_id": "p1", "upload_url": "https://upload"}, "error": {"code": "ok"}}
assert S.tt_post({"access_token": "t"}, vid, "caption", "direct", seconds=40) == "p1"
body = next(b for u, b in SENT if u.endswith("/post/publish/video/init/"))["post_info"]
assert body["privacy_level"] == "SELF_ONLY" and body["is_aigc"] is True and body["brand_content_toggle"] is False, body
try: S.tt_post({"access_token": "t"}, vid, "caption", "direct", seconds=900); raise AssertionError("too long accepted")
except RuntimeError as e: assert "over the account" in str(e)
INIT = {"error": {"code": "spam_risk_too_many_posts", "message": "too many"}}
try: S.tt_post({"access_token": "t"}, vid, "c", "inbox"); raise AssertionError("spam not raised")
except S.TikTokStop: pass
INIT = {"error": {"code": "spam_risk_too_many_pending_share", "message": "pending"}}
try: S.tt_post({"access_token": "t"}, vid, "c", "inbox"); raise AssertionError("pending not raised")
except S.TikTokStop: raise AssertionError("pending drafts are a wait, not a stop")
except RuntimeError as e: assert any(c in str(e) for c in S.TT_WAIT_CODES)
print("3 tiktok privacy ok")

# 4. drafts in the last 24 hours, landed or pending; the cap never passes TikTok's 5 for the inbox
sts = [{"tiktok": {"at": iso(NOW - dt.timedelta(hours=2))}}, {"tiktok_pending": {"at": iso(NOW - dt.timedelta(hours=5))}},
       {"tiktok": {"at": iso(NOW - dt.timedelta(hours=30))}}, {}]
assert S.tt_sent_24h(sts) == 2
S.CFG["tiktok_per_day"] = 9
assert S.tt_cap("inbox") == 5 and S.tt_cap("direct") == 9
S.CFG["tiktok_per_day"] = 2
assert S.tt_cap("inbox") == 2
print("4 tiktok draft count ok")

# 5. an upload counts only once TikTok confirms it; a failure is an error; still processing waits
st = {"id": "QD-1", "tiktok_pending": {"publish_id": "p1", "mode": "inbox", "at": iso(NOW)}}
STATUS = {"status": "PROCESSING_UPLOAD"}
assert S.tt_settle({"access_token": "t"}, st) and "tiktok" not in st and st["tiktok_pending"]["last_status"] == "PROCESSING_UPLOAD"
STATUS = {"status": "SEND_TO_USER_INBOX"}
S.tt_settle({"access_token": "t"}, st)
assert st["tiktok"]["status"] == "SEND_TO_USER_INBOX" and "tiktok_pending" not in st, st
st = {"id": "QD-2", "tiktok_pending": {"publish_id": "p2", "mode": "inbox", "at": iso(NOW)}}
STATUS = {"status": "FAILED", "fail_reason": "file_format_check_failed"}
S.tt_settle({"access_token": "t"}, st)
assert "file_format_check_failed" in st["tiktok_error"] and "tiktok" not in st and "tiktok_pending" not in st, st
print("5 tiktok confirm ok")

# 6. the spam stop: a file and an issue; TikTok stays off until the file goes
S.tt_stop("spam_risk_too_many_posts")
assert S.tt_safety().get("why") == "spam_risk_too_many_posts" and ISSUES and "TikTok stopped" in ISSUES[-1], ISSUES
(TMP / "status" / "tiktok_safety.json").unlink()
assert S.tt_safety() == {}
print("6 tiktok stop ok")

# 7. stats: dormant without a sign-in; with one, every public post's numbers, matched to its Short
S.load = lambda name: {}
assert S.tt_stats() == 0 and not (TMP / "analytics" / "tiktok.csv").exists()
S.load = lambda name: {"access_token": "t", "saved": iso(NOW)}
(TMP / "status" / "QD-900.json").write_text(json.dumps({"id": "QD-900", "title": "Raye's billion stream song explained",
                                                        "tiktok": {"at": iso(NOW - dt.timedelta(hours=6)), "post_ids": ["7001"]}}))
(TMP / "status" / "QD-901.json").write_text(json.dumps({"id": "QD-901", "tiktok": {"at": iso(NOW - dt.timedelta(hours=6)),
                                                        "caption": "Ballon d'Or comes to London for the first time ever"}}))
def stats_post(url, headers=None, json=None, timeout=None, params=None):
    assert url.endswith("/video/list/"), url
    t = int((NOW - dt.timedelta(hours=1)).timestamp())
    return R({"data": {"videos": [
        {"id": "7001", "create_time": t, "title": "x", "view_count": 120, "like_count": 9, "comment_count": 1, "share_count": 2},
        {"id": "7002", "create_time": t, "title": "Ballon d'Or comes to London: first time ever", "view_count": 40},
        {"id": "7003", "create_time": t, "title": "something else entirely", "view_count": 5}], "has_more": False}, "error": {"code": "ok"}})
S.requests.post = stats_post
S.requests.get = lambda url, params=None, headers=None, timeout=None: R({"data": {"user": {"display_name": "Quickplay", "follower_count": 12}}})
assert S.tt_stats() == 3
got = {r["video"]: r for r in csv.DictReader((TMP / "analytics" / "tiktok.csv").open())}
assert got["7001"]["short"] == "QD-900" and got["7001"]["views"] == "120", got["7001"]
assert got["7002"]["short"] == "QD-901" and got["7003"]["short"] == "", (got["7002"], got["7003"])
assert json.loads((TMP / "status" / "tiktok_account.json").read_text())["follower_count"] == 12
print("7 tiktok stats ok")

# 8. the scopes a new sign-in asks for: no video.publish
assert "video.publish" not in S.TT_SCOPES and "video.list" in S.TT_SCOPES and "user.info.profile" not in S.TT_SCOPES
print("8 tiktok scopes ok")

# 9. a clip take that argues: a planned arguing take is used as it is; an old one is written again; one that still
# narrates after two tries is used but recorded as "framing"
import clips as C
fp = types.ModuleType("factpack"); ANS = []
def gemini(*a, **k): return ANS.pop(0), "stub"
fp.gemini, fp.undash = gemini, (lambda s: s)
sys.modules["factpack"] = fp
c = {"source": {"label": "Speed in Tokyo"}, "subject": "IShowSpeed"}
m = {"id": "x-01", "start": 0, "end": 5, "hook": "H", "take_intro": "Nobody packs for Tokyo in ten seconds flat",
     "take_outro": "Bold or reckless? Would you have done it?", "take_style": "argument"}
assert C.take_lines(c, m, []) == (m["take_intro"], m["take_outro"]) and not ANS
m = {"id": "x-02", "start": 0, "end": 5, "hook": "H", "take_intro": "Watch what happens when he opens the case",
     "take_outro": "Would you have picked Tokyo? Tell us below"}
ANS[:] = [{"intro": "This is why Speed never plans anything in advance", "outro": "Spontaneous or silly? Which side are you on?"}]
assert C.take_lines(c, m, [])[0].startswith("This is why") and m["take_style"] == "argument", m
m = {"id": "x-03", "start": 0, "end": 5, "hook": "H"}
ANS[:] = [{"intro": "Watch what happens when he opens the case", "outro": "Would you have picked Tokyo? Tell us below"},
          {"intro": "Look at his face when the case opens up", "outro": "Would you have picked Tokyo? Tell us below"}]
assert C.take_lines(c, m, []) and m["take_style"] == "framing" and not ANS, m
assert C.NARRATES.search("Watch what happens next") and not C.NARRATES.search("Nobody expected Speed to choose Tokyo")
assert "take_style" in C.TESTS and C.RECORDED_ARMS["take_style"] == ["argument", "framing"]
print("9 clip take ok")
print("social safety ok")
