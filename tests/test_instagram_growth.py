"""Offline test of Instagram's own tests (pipeline/social.py, 24 October): arms fixed per Short, a proven arm taking 80%,
category scores from Instagram views, the picks (category fit, exploration, the morning arm and its share of the cap, at
most 2 a run), the cover frame, trial reels with their fallbacks (Meta's refusal remembered for 14 days), the short
caption, a whole post() run, and drivers.analyse_instagram scoring them against Instagram views (never the writer's)."""
import csv, datetime as dt, json, os, pathlib as _p, sys, tempfile, types
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
_al = types.ModuleType("alerts"); _al.raise_issue = lambda *a, **k: None; _al.clear = lambda *a, **k: None
sys.modules["alerts"] = _al                   # never a real GitHub issue from a test
import social as S
import drivers as DRV

TMP = _p.Path(tempfile.mkdtemp(prefix="qp-ig-"))
(TMP / "status").mkdir(); (TMP / "analytics").mkdir()
S.ROOT = TMP
NOW = dt.datetime.now(dt.timezone.utc)
iso = lambda t: t.isoformat(timespec="seconds")

# 1. arms: fixed per Short and test, about the share asked for
a = [S.ig_arm(f"QD-{i}", "ig-trial", 0.5, "yes", "no") for i in range(2000)]
assert a == [S.ig_arm(f"QD-{i}", "ig-trial", 0.5, "yes", "no") for i in range(2000)]
assert 900 < a.count("yes") < 1100, a.count("yes")
b = [S.ig_arm(f"QD-{i}", "ig-caption", 0.5, "yes", "no") for i in range(2000)]
assert sum(x == y for x, y in zip(a, b)) < 1150            # the tests are independent of each other
assert S.ig_arm("QD-1", "x", 0.0, "a", "b") == "b" and S.ig_arm("QD-1", "x", 1.0, "a", "b") == "a"
print("1 arms ok")

# 2. a proven arm takes 80%, never all; the reverse 20%; nothing proven: the default
assert S.ig_share("ig_trial", "yes", "no", 0.5) == 0.5
def drivers_csv(rows):
    with (TMP / "analytics" / "drivers.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["feature", "value", "verdict"]); w.writeheader(); w.writerows(rows)
drivers_csv([{"feature": "ig_trial", "value": "yes", "verdict": "push"}])
assert S.ig_share("ig_trial", "yes", "no") == 0.8
drivers_csv([{"feature": "ig_trial", "value": "no", "verdict": "push"}, {"feature": "ig_caption", "value": "short", "verdict": "cut back"}])
assert S.ig_share("ig_trial", "yes", "no") == 0.2 and S.ig_share("ig_caption", "short", "full") == 0.2
drivers_csv([{"feature": "ig_hour", "value": "any", "verdict": "cut back"}])
assert S.ig_share("ig_hour", "morning", "any") == 0.8
(TMP / "analytics" / "drivers.csv").unlink()
print("2 learned shares ok")

# 3. category scores: the data report's order until 15 Reels are measured; then Instagram's own numbers, shrunk
assert S.ig_category_scores() == {"Gaming": 1.5, "Sport": 1.5}
def shorts_csv(rows):
    keys = ["short", "category", "ig_views", "ig_posted", "posted"]
    with (TMP / "analytics" / "shorts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows([{k: r.get(k, "") for k in keys} for r in rows])
rows = [{"short": f"QD-{i}", "category": c, "ig_views": v, "ig_posted": iso(NOW - dt.timedelta(days=2))}
        for i, (c, v) in enumerate([("Gaming", 300)] * 8 + [("Music", 60)] * 8 + [("Film", 100)] * 8)]
rows.append({"short": "QD-new", "category": "Music", "ig_views": 9999, "ig_posted": iso(NOW - dt.timedelta(hours=3))})   # under a day: left out
shorts_csv(rows)
sc = S.ig_category_scores()
assert sc["Gaming"] > sc["Film"] == 1.0 > sc["Music"], sc
assert abs(sc["Gaming"] - 3 ** (8 / 13)) < 0.01, sc        # 3x the median, shrunk by 5 Reels' worth (8 of 13 on the log scale)
print("3 category scores ok", sc)

# 4. the picks: category fit first, the morning arm only in the morning and with its own share of the cap, 2 a run
S.CFG.update(instagram_explore_share=0.0, instagram_hour_share=0.5, instagram_morning_hours=[6, 10], instagram_max_per_run=2,
             crosspost_max_age_hours=48)
cats = {}
def status(sid, cat, hours_ago, **kw):
    cats[sid] = cat
    return {"id": sid, "video": "v" + sid, "social_release": "social-" + sid, "publish_at": iso(NOW - dt.timedelta(hours=hours_ago)), **kw}
sts = [status("QD-901", "Music", 1), status("QD-902", "Gaming", 2), status("QD-903", "Film", 1), status("QD-904", "Gaming", 5),
       status("QD-905", "Gaming", 60), status("QD-906", "Sport", 1, instagram={"media": "m", "at": iso(NOW)})]
morning = dt.datetime(2026, 10, 27, 8, 0, tzinfo=dt.timezone.utc)      # 08:00 UK (GMT)
evening = dt.datetime(2026, 10, 27, 20, 0, tzinfo=dt.timezone.utc)
shift = lambda t: [dict(s, publish_at=iso(t - (NOW - dt.datetime.fromisoformat(s["publish_at"])))) for s in sts]
hours = {s["id"]: S.ig_arm(s["id"], "ig-hour", 0.5, "morning", "any") for s in sts}
got_m = S.ig_choose(shift(morning), 8, now=morning, category_of=lambda s: cats[s["id"]])
got_e = S.ig_choose(shift(evening), 8, now=evening, category_of=lambda s: cats[s["id"]])
assert len(got_m) <= 2 and len(got_e) <= 2, (got_m, got_e)
assert "QD-905" not in got_m and "QD-906" not in got_m          # too old; already on Instagram
assert all(v["hour"] == "any" for v in got_e.values()) and all(hours[k] == "any" for k in got_e)
assert all(hours[k] == v["hour"] for k, v in got_m.items())
assert list(got_m)[0] in ("QD-902", "QD-904"), got_m                             # a Gaming Short leads
# the arms' shares of the cap over 24 hours: 4 morning Reels already posted today leave the morning arm no room
busy = shift(morning) + [{"id": f"QD-7{i}", "instagram": {"media": "m", "at": iso(morning - dt.timedelta(hours=1)), "hour": "morning"}} for i in range(4)]
got_b = S.ig_choose(busy, 8, now=morning, category_of=lambda s: cats.get(s["id"], ""))
assert all(v["hour"] == "any" for v in got_b.values()), got_b
# exploration: with every Short an exploration pick, the order is newest first whatever the category
S.CFG.update(instagram_explore_share=1.0, instagram_hour_test=False)
got_x = S.ig_choose(shift(evening), 8, now=evening, category_of=lambda s: cats[s["id"]])
assert set(got_x) == {"QD-901", "QD-903"} and all(v["pick"] == "explore" for v in got_x.values()), got_x
S.CFG.update(instagram_explore_share=0.25, instagram_hour_test=True)
print("4 picks ok", got_m, got_e)

# 5. the cover frame: inside the opening beat
assert S.ig_hook_ms({"timeline": [[0.06, 3.56, "title", 0], [3.56, 8.9, "stat", 2]]}) == 1260
assert S.ig_hook_ms({"timeline": [[0.06, 1.7, "title", 0]]}) == 880
assert S.ig_hook_ms({}) == 1000 and S.ig_hook_ms({"timeline": []}) == 1000
print("5 cover frame ok")

# 6. trial reels and their fallbacks (a stubbed Graph API)
class R:
    def __init__(self, ok=True, data=None, status=200, text=""):
        self.ok, self._d, self.status_code, self.text = ok, data or {}, status, text or json.dumps(data or {})
    def json(self): return self._d
SENT, REFUSE = [], set()
def fake_post(url, data=None, timeout=None, **kw):
    if url.endswith("/media"):
        SENT.append(dict(data))
        bad = [k for k in REFUSE if k in data]
        if bad: return R(False, {"error": {"message": f"Invalid parameter {bad[0]}", "code": 100}}, 400)
        return R(True, {"id": f"c{len(SENT)}"})
    if url.endswith("/media_publish"):
        if "publish" in REFUSE: return R(False, {"error": {"message": "server", "code": 2}}, 500)
        return R(True, {"id": f"m{len(SENT)}"})
    raise AssertionError(url)
S.requests.post = fake_post
S.requests.get = lambda url, params=None, timeout=None, **kw: R(True, {"status_code": "FINISHED"})
tok = {"token": "t", "user": "17841"}
mid, used = S.ig_publish(tok, "https://x/social.mp4", "cap", trial=True, thumb_ms=1260)
assert used == {"trial": "yes", "thumb_ms": 1260, "thumb": "accepted"} and mid == "m1", (mid, used)
assert json.loads(SENT[-1]["trial_params"]) == {"graduation_strategy": "SS_PERFORMANCE"} and SENT[-1]["thumb_offset"] == "1260"
assert SENT[-1]["media_type"] == "REELS" and SENT[-1]["share_to_feed"] == "true"
assert S.ig_trial_ok()
REFUSE.add("trial_params"); SENT.clear()
mid, used = S.ig_publish(tok, "https://x/social.mp4", "cap", trial=True, thumb_ms=1260)
assert used == {"trial": "refused", "thumb_ms": 1260, "thumb": "accepted"} and len(SENT) == 2 and "trial_params" not in SENT[1], used
assert not S.ig_trial_ok()                                       # Meta refused: no trial asked for 14 days
st = json.loads((TMP / "status" / "instagram_trial.json").read_text()); assert "trial_params" in st["error"]
REFUSE.add("thumb_offset"); SENT.clear()
mid, used = S.ig_publish(tok, "https://x/social.mp4", "cap", trial=False, thumb_ms=1260)
assert used == {"trial": "no", "thumb_ms": None, "thumb": "refused"} and len(SENT) == 2 and SENT[1].keys() >= {"media_type", "caption"}
REFUSE.clear(); REFUSE.add("publish"); SENT.clear()
try: S.ig_publish(tok, "https://x/social.mp4", "cap", trial=True, thumb_ms=1000); raise SystemExit("publish failure not raised")
except RuntimeError as e: assert "instagram publish" in str(e) and len(SENT) == 1      # not about the settings: no retry
REFUSE.clear(); (TMP / "status" / "instagram_trial.json").unlink()
print("6 trial reels and fallbacks ok")

# 7. the short caption: the spoken hook and 3 hashtags; the full one unchanged
board = {"meta": {"title": "GTA 6: the detail everyone missed", "summary": "A longer summary.",
                  "hashtags": ["#GTA6", "#Rockstar", "#Gaming", "#Shorts", "#Trailer", "#GTAVI"]},
         "beats": [{"say": "Rockstar hid one number in the GTA 6 trailer."}], "category": "Gaming"}
S.CFG["instagram_hashtags"] = {"Gaming": ["#gaming", "#gamingnews", "#videogames"]}      # the category's own set (25 October)
short = S.caption({}, board, "instagram", "short")
FOLLOW = "\n\nFollow @quickplaydaily for a new %s Short every day."       # the subscriber push's last line (25 October)
assert short == "Rockstar hid one number in the GTA 6 trailer.\n\n#gaming #gamingnews #videogames" + FOLLOW % "Gaming", short
nocat = S.caption({}, {**board, "category": "Music"}, "instagram", "short")                # no set for the category: the board's first 3
assert nocat == "Rockstar hid one number in the GTA 6 trailer.\n\n#GTA6 #Rockstar #Gaming" + FOLLOW % "Music", nocat
full = S.caption({}, board, "instagram")
assert "A longer summary." in full and full.count("#") == 5
assert S.caption({}, board, "instagram", "full") == full
print("7 captions ok")

# 8. a whole post() run: Instagram takes its picks with every test recorded on the post
for p in (TMP / "status").glob("*.json"): p.unlink()
(TMP / "analytics" / "shorts.csv").unlink()
S.CFG.update(instagram_morning_hours=[0, 24], instagram_explore_share=0.25, tiktok_mode="off", instagram_mode="all",
             instagram_per_day=4, instagram_target=8, instagram_ramp_per_day=2, facebook_probe=False)
for sid, cat in (("QD-951", "Gaming"), ("QD-952", "Music"), ("QD-953", "Sport")):
    s = status(sid, cat, 1, timeline=[[0.06, 3.0, "title", 0]])
    (TMP / "status" / f"{sid}.json").write_text(json.dumps(s))
S.board_for = lambda st: {**board, "category": cats.get(st["id"], "")}
S.ig_tokens = lambda: {"token": "t", "user": "17841", "saved": iso(NOW)}
S.fb_tokens = lambda: None
S.tt_safety = lambda: None
S.gh = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr="")
SENT.clear()
S.post()
posted = {p.stem: json.loads(p.read_text()).get("instagram") for p in (TMP / "status").glob("QD-95*.json")}
done = {k: v for k, v in posted.items() if v}
assert len(done) == 2, posted                                    # 2 a run at most
for k, v in done.items():
    assert v["caption"] in ("full", "short") and v["trial"] in ("yes", "no") and v["hour"] in ("morning", "any")
    assert v["pick"] in ("category", "explore") and v["thumb_ms"] == 1260 and isinstance(v["hour_uk"], int), v
assert "QD-952" not in done or posted["QD-952"]["pick"] == "explore"     # Music only as an exploration pick
print("8 post() ok", {k: (v["pick"], v["hour"], v["trial"], v["caption"]) for k, v in done.items()})

# 9. analytics: the post's tests become shorts.csv columns; drivers scores them against Instagram views
import analytics as A
assert A.ig_tests({"instagram": {"media": "m", "at": "2026-10-25T08:00:00+00:00", "trial": "yes", "caption": "short", "hour": "morning",
                                 "pick": "category", "hour_uk": 8}}) == {"ig_trial": "yes", "ig_caption": "short", "ig_hour": "morning",
                                                                         "ig_pick": "category", "ig_posted": "2026-10-25T08:00:00+00:00", "ig_hour_uk": 8}
assert A.ig_tests({}) == {k: "" for k in A.IG_TESTS}
rows = []
for d in range(4):
    for i in range(10):
        trial = "yes" if i % 2 == 0 else "no"
        rows.append({"short": f"QD-{d}{i}", "category": "Gaming" if i < 5 else "Music", "ig_trial": trial, "ig_caption": "full",
                     "ig_hour": "any", "ig_pick": "category", "ig_views": "300" if trial == "yes" else "100",
                     "ig_posted": iso(NOW - dt.timedelta(days=d + 2, hours=i % 3)), "posted": iso(NOW - dt.timedelta(days=d + 2))})
table = DRV.analyse_instagram(rows)
v = {(t["feature"], t["value"]): t for t in table}
assert v[("ig_trial", "yes")]["verdict"] == "push" and v[("ig_trial", "no")]["verdict"] == "cut back", v
assert ("ig_caption", "full") not in v                           # one arm only: nothing to compare
assert v[("ig_trial", "yes")]["feature_label"] == "Instagram trial reel" and "Instagram views" in v[("ig_trial", "yes")]["why"]
assert ("ig_category", "Gaming") in v
assert all(t["feature"] in DRV.PIPELINE_ONLY for t in table)    # never put to the writer
assert not any("Instagram" in line for line in DRV.recipe(table, rows))
young = [dict(r, ig_posted=iso(NOW - dt.timedelta(hours=5))) for r in rows]
assert DRV.analyse_instagram(young) == []                        # Reels under a day old wait
print("9 analytics and drivers ok")
print("instagram growth ok")
