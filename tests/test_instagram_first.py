"""Offline test of Instagram as its own product (pipeline/social.py, 25 October): per-category hashtag sets in the short
caption (the long caption keeps the board's), the categories Instagram favours (its own medians, the configured order until
15 Reels are measured), Instagram-first picks (a favoured Short goes at the first run after it is public, newest first, inside
the hour test's rules, and never filtered on YouTube views), the cover frame check (accepted, refused or off on every post, a
refusal remembered, a transient failure not), the numbers behind status/instagram.json and the Instagram section of
analytics/insights.md, the hub's Instagram card, and docs/SERVICE.md. Stubs only: no network, no real GitHub issue."""
import csv, datetime as dt, json, os, pathlib as _p, re, sys, tempfile, time, types
REAL_SLEEP, time.sleep = time.sleep, lambda s: None           # ig_post waits 10 s between status reads: a test never waits
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
_al = types.ModuleType("alerts"); _al.raise_issue = lambda *a, **k: None; _al.clear = lambda *a, **k: None
sys.modules["alerts"] = _al                   # never a real GitHub issue from a test
import social as S
import validate as V                          # the categories the writer can use, and the dash rule

REAL = json.loads((_p.Path(REPO_DIR) / "config.json").read_text())      # the real config, before any test changes S.CFG
TMP = _p.Path(tempfile.mkdtemp(prefix="qp-ig1-"))
(TMP / "status").mkdir(); (TMP / "analytics").mkdir()
S.ROOT = TMP
REAL_NOW = dt.datetime.now(dt.timezone.utc)
NOW = REAL_NOW
iso = lambda t: t.isoformat(timespec="seconds")

# 1. the real config: a hashtag set for every category, 3 to 5 family-friendly UK English tags, no dashes in the notes
sets = REAL["instagram_hashtags"]
assert set(sets) == V.CATS, set(sets) ^ V.CATS                                  # every category the writer can use
OFF_LIMITS = re.compile(r"politic|election|brexit|gambl|casino|betting|lotter|nsfw|sexy|porn|drug|vape|alcohol|crime|murder|invest|crypto|forex|money", re.I)
US_SPELLING = re.compile(r"color|center|favorite|theater|soccer|neighbor|humor")
for cat, tags in sets.items():
    assert 3 <= len(tags) <= 5, (cat, tags)
    assert all(re.fullmatch(r"#[a-z0-9_]+", t) for t in tags), (cat, tags)      # lower case, letters and numbers after one #
    assert len({t.lower() for t in tags}) == len(tags), (cat, tags)
    assert not any(OFF_LIMITS.search(t) or US_SPELLING.search(t) for t in tags), (cat, tags)
for k, v in REAL.items():
    if k.startswith("instagram"): assert not V.DASH.search(json.dumps(v, ensure_ascii=False)), k      # no em or en dashes anywhere
assert REAL["instagram_first"] is True and REAL["instagram_favour_min"] >= 1.0 and REAL["instagram_cover_pause_days"] >= 1
print("1 config ok", {c: len(t) for c, t in sets.items()})

# 2. captions: the short arm takes the category's own set, the long arm keeps the board's hashtags
S.CFG["instagram_hashtags"] = REAL["instagram_hashtags"]
board = {"category": "Sport", "meta": {"title": "Hamilton in Rwanda", "summary": "A longer summary.",
                                       "hashtags": ["#Hamilton", "#F1", "#Rwanda", "#Shorts", "#GrandPrix", "#Formula1"]},
         "beats": [{"say": "Lewis Hamilton wants to race in Rwanda."}]}
short = S.caption({}, board, "instagram", "short")
assert short == "Lewis Hamilton wants to race in Rwanda.\n\n" + " ".join(sets["Sport"]), short
full = S.caption({}, board, "instagram", "full")
assert "#Hamilton #F1 #Rwanda #GrandPrix #Formula1" in full and "A longer summary." in full and "#sport" not in full, full
assert S.caption({}, board, "instagram") == full                                 # the long caption is the default and is unchanged
assert S.caption({}, board, "facebook").endswith("#Hamilton #F1 #Rwanda")        # Facebook keeps the board's first 3
assert S.caption({}, {**board, "category": "Weather"}, "instagram", "short").endswith("#Hamilton #F1 #Rwanda")      # no set: the board's first 3
assert S.caption({"category": "Gaming"}, {k: v for k, v in board.items() if k != "category"}, "instagram", "short").endswith(" ".join(sets["Gaming"]))
S.CFG["instagram_hashtags"] = {"Sport": ["#sport", "sport", "#sport news", "#Sport", "#football", "#a", "#b", "#c", "#d"]}
assert S.ig_hashtags({}, board) == ["#sport", "#football", "#a", "#b", "#c"]      # well formed, no repeats, 5 at most
S.CFG["instagram_hashtags"] = REAL["instagram_hashtags"]
print("2 captions ok")

# 3. the categories Instagram favours: its own medians once 15 Reels are measured, the configured order before and for a
#    category it has no numbers for yet
def reels_csv(rows):
    keys = ["short", "category", "ig_views", "ig_posted", "posted", "ig_trial", "ig_caption", "ig_hour", "ig_pick", "yt_views_3h"]
    with (TMP / "analytics" / "shorts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows([{k: r.get(k, "") for k in keys} for r in rows])
def mk(cat, views, n, days=2, **kw):
    when = iso(NOW - dt.timedelta(days=days))
    return [{"short": f"QD-{cat[:2]}{days}{i}", "category": cat, "ig_views": views, "ig_posted": when, "posted": when, **kw} for i in range(n)]
S.CFG.update(instagram_category_order=["Gaming", "Sport"], instagram_favour_min=1.05)
assert S.ig_favoured() == {"Gaming", "Sport"}                                    # no numbers yet: the configured order
base = mk("Gaming", 300, 8) + mk("Sport", 200, 8) + mk("Film", 100, 8) + mk("Music", 60, 8)
reels_csv(base)
sc = S.ig_category_scores()
assert sc["Gaming"] > sc["Sport"] > 1.05 > sc["Film"] > sc["Music"], sc
assert S.ig_favoured(sc) == {"Gaming", "Sport"} and S.ig_favoured() == {"Gaming", "Sport"}
S.CFG["instagram_favour_min"] = 0.7
assert S.ig_favoured() == {"Gaming", "Sport", "Film"}                            # the bar is the config's
S.CFG["instagram_favour_min"] = 1.6
assert S.ig_favoured() == set()                                                  # Gaming and Sport have numbers, so the order no longer holds them
S.CFG.update(instagram_favour_min=1.05, instagram_category_order=["Gaming", "Sport", "History"])
assert S.ig_favoured() == {"Gaming", "Sport", "History"}                         # History has no Reels yet: the prior stands until the data speaks
reels_csv(mk("Gaming", 300, 3) + mk("Music", 60, 3))
assert S.ig_favoured() == {"Gaming", "Sport", "History"}                         # under 15 measured Reels: the configured order alone
S.CFG["instagram_category_order"] = ["Gaming", "Sport"]
print("3 favoured categories ok", {c: round(v, 2) for c, v in sc.items()})

# 4. Instagram-first picks
S.CFG.update(instagram_explore_share=0.0, instagram_hour_test=False, instagram_max_per_run=2, crosspost_max_age_hours=48, instagram_first=True)
evening = dt.datetime(2026, 10, 27, 20, 0, tzinfo=dt.timezone.utc)              # 20:00 UK (GMT)
morning = dt.datetime(2026, 10, 27, 8, 0, tzinfo=dt.timezone.utc)
cats = {}
def status(sid, cat, minutes_ago, now=evening, **kw):
    cats[sid] = cat
    return {"id": sid, "video": "v" + sid, "social_release": "social-" + sid, "publish_at": iso(now - dt.timedelta(minutes=minutes_ago)), **kw}
catof = lambda s: cats[s["id"]]
reels_csv(base + [{"short": "QD-801", "category": "Gaming", "yt_views_3h": "0"}, {"short": "QD-803", "category": "Music", "yt_views_3h": "5000"}])
def boom(*a, **k): raise AssertionError("the picker read YouTube views")
S.views_3h = boom                                                                # any read of YouTube's numbers fails the test
fn = S.ig_choose.__code__
assert "views_3h" not in fn.co_names and not any("views" in c for c in fn.co_consts if isinstance(c, str) and c != S.ig_choose.__doc__)
sts = [status("QD-801", "Gaming", 10), status("QD-802", "Sport", 30 * 60), status("QD-803", "Music", 60), status("QD-804", "Film", 120)]
plan = S.ig_choose(sts, 8, now=evening, category_of=catof)
assert list(plan) == ["QD-801", "QD-802"], plan          # Gaming public 10 minutes ago with no YouTube views first; Music's 5,000 views change nothing
assert all(v["favoured"] for v in plan.values()) and plan["QD-801"]["hour"] == "any"
# a fresh favoured Short is not held behind an older one with a higher weight; the old order puts the score first
old_gaming, fresh_sport = status("QD-811", "Gaming", 30 * 60), status("QD-812", "Sport", 10)
S.CFG["instagram_max_per_run"] = 1
assert list(S.ig_choose([old_gaming, fresh_sport], 8, now=evening, category_of=catof)) == ["QD-812"]
S.CFG["instagram_first"] = False
plan_old = S.ig_choose([old_gaming, fresh_sport], 8, now=evening, category_of=catof)
assert list(plan_old) == ["QD-811"] and plan_old["QD-811"]["favoured"] is False
S.CFG.update(instagram_first=True, instagram_max_per_run=3)
# the rest follow by weight, and only when room is left: one slot goes to the favoured Short
rest = [status("QD-821", "Music", 5), status("QD-822", "Film", 6), status("QD-823", "Gaming", 600)]
p3 = S.ig_choose(rest, 8, now=evening, category_of=catof)
assert list(p3) == ["QD-823", "QD-822", "QD-821"] and [v["favoured"] for v in p3.values()] == [True, False, False], p3
assert list(S.ig_choose(rest, 1, now=evening, category_of=catof)) == ["QD-823"]
# an exploration pick shares the top tier (newest first); a plain non-favoured Short goes after both
S.CFG["instagram_explore_share"] = 0.5
ex_id = next(f"QD-{i}" for i in range(900, 1900) if S.ig_arm(f"QD-{i}", "ig-explore", 0.5, "explore", "category") == "explore")
no_id = next(f"QD-{i}" for i in range(1900, 2900) if S.ig_arm(f"QD-{i}", "ig-explore", 0.5, "explore", "category") == "category")
p4 = S.ig_choose([status(ex_id, "Tech", 60), status(no_id, "Music", 30), status("QD-830", "Gaming", 20 * 60)], 8, now=evening, category_of=catof)
assert list(p4) == [ex_id, "QD-830", no_id] and p4[ex_id]["pick"] == "explore", p4
# the hour test's rules still hold: a favoured Short in the morning arm waits for the morning, and the arms share the cap
S.CFG.update(instagram_explore_share=0.0, instagram_hour_test=True, instagram_hour_share=0.5, instagram_morning_hours=[6, 10], instagram_max_per_run=8)
mo = next(f"QD-{i}" for i in range(900, 1900) if S.ig_arm(f"QD-{i}", "ig-hour", 0.5, "morning", "any") == "morning")
an = next(f"QD-{i}" for i in range(1900, 2900) if S.ig_arm(f"QD-{i}", "ig-hour", 0.5, "morning", "any") == "any")
pair = lambda now: [status(mo, "Gaming", 10, now), status(an, "Gaming", 20, now)]
assert list(S.ig_choose(pair(evening), 8, now=evening, category_of=catof)) == [an]
p_m = S.ig_choose(pair(morning), 8, now=morning, category_of=catof)
assert set(p_m) == {mo, an} and p_m[mo]["hour"] == "morning" and p_m[an]["hour"] == "any", p_m
busy = [{"id": f"QD-7{i}", "instagram": {"media": "m", "at": iso(evening - dt.timedelta(hours=1)), "hour": "any"}} for i in range(4)]
assert S.ig_choose(pair(evening) + busy, 8, now=evening, category_of=lambda s: cats.get(s["id"], "")) == {}     # the 4 'any' slots are used
print("4 picks ok", list(plan), list(p4))

# 5. the cover frame: asked with the trial, tried alone when the trial goes, remembered when refused, not blamed for a hiccup
class R:
    def __init__(self, ok=True, data=None, status=200, text=""):
        self.ok, self._d, self.status_code, self.text = ok, data or {}, status, text or json.dumps(data or {})
    def json(self): return self._d
SENT, REFUSE, CONTAINER = [], set(), [None]
def fake_post(url, data=None, timeout=None, **kw):
    if url.endswith("/media"):
        SENT.append(dict(data))
        if CONTAINER[0]: return R(False, {}, CONTAINER[0][0], CONTAINER[0][1])
        bad = [k for k in REFUSE if k in data]
        if bad: return R(False, {"error": {"message": f"Invalid parameter {bad[0]}", "code": 100}}, 400)
        return R(True, {"id": f"c{len(SENT)}"})
    if url.endswith("/media_publish"): return R(True, {"id": f"m{len(SENT)}"})
    raise AssertionError(url)
S.requests.post = fake_post
# one stub for every Graph API read: a container that is finished (ig_post), and the account (check)
S.requests.get = lambda url, params=None, timeout=None, **kw: R(True, {"status_code": "FINISHED", "user_id": "17841", "username": "quickplaydaily",
                                                                      "account_type": "MEDIA_CREATOR", "data": []})
tok = {"token": "t", "user": "17841"}
def publish(**kw):
    SENT.clear(); return S.ig_publish(tok, "https://x/social.mp4", "cap", **kw)
sent = lambda: [sorted(k for k in d if k in ("trial_params", "thumb_offset")) for d in SENT]
marker = lambda n: (TMP / "status" / n).exists()
def clear_markers():
    for n in ("instagram_trial.json", "instagram_cover.json"): (TMP / "status" / n).unlink(missing_ok=True)
mid, used = publish(trial=True, thumb_ms=1260)
assert used == {"trial": "yes", "thumb_ms": 1260, "thumb": "accepted"} and len(SENT) == 1 and not marker("instagram_cover.json")
REFUSE.add("thumb_offset")                       # only the cover frame refused: the trial is still asked for (it used to be dropped as well)
mid, used = publish(trial=True, thumb_ms=1260)
assert used == {"trial": "yes", "thumb_ms": None, "thumb": "refused"}, used
assert sent() == [["thumb_offset", "trial_params"], ["thumb_offset"], ["trial_params"]], sent()
assert marker("instagram_cover.json") and not marker("instagram_trial.json") and S.ig_trial_ok() and not S.ig_cover_ok()
assert "thumb_offset" in json.loads((TMP / "status" / "instagram_cover.json").read_text())["error"]
clear_markers(); REFUSE.clear(); REFUSE.add("trial_params")      # only the trial refused: the cover frame is kept
mid, used = publish(trial=True, thumb_ms=1260)
assert used == {"trial": "refused", "thumb_ms": 1260, "thumb": "accepted"} and sent() == [["thumb_offset", "trial_params"], ["thumb_offset"]]
assert marker("instagram_trial.json") and not marker("instagram_cover.json") and S.ig_cover_ok() and not S.ig_trial_ok()
clear_markers(); REFUSE.add("thumb_offset")                      # both refused: a plain Reel, both remembered
mid, used = publish(trial=True, thumb_ms=1260)
assert used == {"trial": "refused", "thumb_ms": None, "thumb": "refused"} and sent()[-1] == [] and len(SENT) == 4
assert marker("instagram_trial.json") and marker("instagram_cover.json")
clear_markers(); REFUSE.clear(); REFUSE.add("thumb_offset")      # no trial asked: the cover frame, then a plain Reel
mid, used = publish(trial=False, thumb_ms=1260)
assert used == {"trial": "no", "thumb_ms": None, "thumb": "refused"} and len(SENT) == 2 and not marker("instagram_trial.json")
clear_markers(); REFUSE.clear()
mid, used = publish(trial=False, thumb_ms=None)                  # nothing asked: one call, the cover frame is "off", not refused
assert used == {"trial": "no", "thumb_ms": None, "thumb": "off"} and len(SENT) == 1
for answer in ((500, "server"), (503, '{"error": {"message": "unavailable"}}'), (429, "slow down"),
               (400, '{"error": {"message": "An unexpected error has occurred.", "is_transient": true, "code": 2}}')):
    CONTAINER[0] = answer                                        # Meta failing for a moment: nothing is blamed on the settings
    try: publish(trial=True, thumb_ms=1260); raise SystemExit(f"{answer} was not raised")
    except RuntimeError as e: assert str(e).startswith("instagram container") and len(SENT) == 1, (answer, e, len(SENT))
    assert not marker("instagram_trial.json") and not marker("instagram_cover.json")
CONTAINER[0] = (400, "media could not be fetched")               # a 400 that is not transient is tried without the settings, then raised
try: publish(trial=True, thumb_ms=1260); raise SystemExit("not raised")
except RuntimeError as e: assert len(SENT) == 4 and "media could not be fetched" in str(e)
CONTAINER[0] = None
(TMP / "status" / "instagram_cover.json").write_text(json.dumps({"refused": iso(REAL_NOW), "error": "x"}))
assert not S.ig_cover_ok() and S.ig_cover_until() is not None
S.NOW = lambda: REAL_NOW + dt.timedelta(days=int(S.CFG.get("instagram_cover_pause_days", 3)) + 1)
assert S.ig_cover_ok()                                           # the pause ends
S.NOW = lambda: REAL_NOW
clear_markers()
print("5 cover frame fallbacks ok")

# 6. the cover frame check: tallied from the posts, in status/social.json
def post_rec(hours_ago, **ig): return {"id": f"QD-c{hours_ago}", "instagram": {"media": "m", "at": iso(REAL_NOW - dt.timedelta(hours=hours_ago)), **ig}}
recs = [post_rec(2, thumb="accepted", thumb_ms=1260), post_rec(5, thumb="refused", thumb_ms=None), post_rec(72, thumb_ms=900),
        post_rec(1, thumb="off", thumb_ms=None), post_rec(24 * 20, thumb="accepted", thumb_ms=1000), post_rec(30, thumb_ms=None), {"id": "QD-none"}]
c = S.ig_cover_check(recs)
assert (c["asked"], c["accepted"], c["refused"], c["last"], c["ok"]) == (3, 2, 1, "accepted", True), c    # off, old and unknown are not counted
recs[0]["instagram"]["thumb"] = "refused"
c = S.ig_cover_check(recs)
assert (c["asked"], c["accepted"], c["refused"], c["last"], c["ok"]) == (3, 1, 2, "refused", False), c
assert S.ig_cover_check([])["ok"] is None and S.ig_cover_check([])["asked"] == 0
S.ig_tokens = lambda: {"token": "t", "user": "17841", "saved": iso(REAL_NOW)}
S.fb_tokens = lambda: None
S.load = lambda name: {}                                          # no encrypted token store in a test
S.CFG["tiktok_mode"] = "off"
for p in (TMP / "status").glob("*.json"): p.unlink()
for r in recs[:2]: (TMP / "status" / f"{r['id']}.json").write_text(json.dumps(r))
S.check()
cover = json.loads((TMP / "status" / "social.json").read_text())["instagram"]["cover"]
assert (cover["asked"], cover["accepted"], cover["refused"], cover["ok"]) == (2, 0, 2, False), cover
assert cover == S.ig_cover_check(), cover
print("6 cover check ok", cover)

# 7. a whole post() run: favoured Reels go first whatever their YouTube views, every post records the cover frame answer
for p in (TMP / "status").glob("*.json"): p.unlink()
S.CFG.update(instagram_morning_hours=[0, 24], instagram_explore_share=0.0, instagram_hour_test=False, instagram_trial=False, tiktok_mode="off",
             instagram_mode="all", instagram_per_day=8, instagram_target=8, instagram_ramp_per_day=2, instagram_max_per_run=2,
             instagram_caption_test=True, instagram_caption_share=1.0, facebook_probe=False)
reels_csv(base + [{"short": "QD-951", "category": "Gaming", "yt_views_3h": "0"}, {"short": "QD-953", "category": "Music", "yt_views_3h": "9999"}])
S.board_for = lambda st: {**board, "category": cats.get(st["id"], "")}
S.gh = lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr="")
S.tt_safety = lambda: None
def put(sid, cat):
    (TMP / "status" / f"{sid}.json").write_text(json.dumps(status(sid, cat, 60, now=REAL_NOW, timeline=[[0.06, 3.0, "title", 0]])))
rec = lambda sid: json.loads((TMP / "status" / f"{sid}.json").read_text()).get("instagram")
for sid, cat in (("QD-951", "Gaming"), ("QD-952", "Sport"), ("QD-953", "Music")): put(sid, cat)
SENT.clear(); S.post()
assert rec("QD-951") and rec("QD-952") and not rec("QD-953"), "the two favoured Shorts go; Music (9,999 YouTube views at 3 hours) waits"
for sid in ("QD-951", "QD-952"):
    assert rec(sid)["favoured"] is True and rec(sid)["thumb"] == "accepted" and rec(sid)["thumb_ms"] == 1260 and rec(sid)["caption"] == "short", rec(sid)
gaming_caption = next(d["caption"] for d in SENT if "#gaming" in d["caption"])
assert gaming_caption.endswith(" ".join(sets["Gaming"])) and "Lewis Hamilton" in gaming_caption          # the hook and the category's own set
REFUSE.add("thumb_offset"); put("QD-954", "Gaming"); put("QD-955", "Sport")
SENT.clear(); S.post()
assert sorted(rec(s)["thumb"] for s in ("QD-954", "QD-955")) == ["off", "refused"], (rec("QD-954"), rec("QD-955"))   # the first found Meta refusing it;
assert all(rec(s)["thumb_ms"] is None for s in ("QD-954", "QD-955"))                                              # the next in the run did not ask again
assert marker("instagram_cover.json") and not rec("QD-953")
REFUSE.clear(); put("QD-956", "Gaming")
SENT.clear(); S.post()
assert rec("QD-956")["thumb"] == "off" and rec("QD-956")["thumb_ms"] is None and all("thumb_offset" not in d for d in SENT), rec("QD-956")   # paused: not asked
c = S.ig_cover_check()
assert (c["asked"], c["accepted"], c["refused"], c["ok"]) == (3, 2, 1, False) and c["paused_until"], c       # "off" is not counted as asked
S.NOW = lambda: REAL_NOW + dt.timedelta(days=4)
assert S.ig_cover_ok()
S.NOW = lambda: REAL_NOW
print("7 post() ok", {k: (rec(k)["thumb"], rec(k)["favoured"]) for k in ("QD-951", "QD-952", "QD-954", "QD-955", "QD-956")})

# 8. the numbers behind insights.md and the hub: category medians, the three tests, followers, the week, the cover frame
for p in (TMP / "status").glob("*.json"): p.unlink()
today = REAL_NOW.date()
rows = []
for cat, views, days in (("Gaming", 300, 2), ("Sport", 200, 2), ("Film", 100, 9), ("Music", 60, 9)):
    for i, r in enumerate(mk(cat, views, 8, days=days)):
        rows.append({**r, "ig_trial": "yes" if i % 2 == 0 else "no", "ig_caption": "short" if i % 4 < 2 else "full", "ig_hour": "morning" if i % 2 else "any"})
reels_csv(rows)
with (TMP / "analytics" / "drivers.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["feature", "value", "verdict", "lift"]); w.writeheader()
    w.writerows([{"feature": "ig_trial", "value": "yes", "verdict": "push", "lift": "1.5"}, {"feature": "ig_trial", "value": "no", "verdict": "cut back", "lift": "0.7"}])
with (TMP / "analytics" / "daily.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["day", "source", "ig_followers"]); w.writeheader()
    w.writerows([{"day": str(today - dt.timedelta(days=d)), "source": "snapshot", "ig_followers": v} for d, v in ((9, 0), (7, 1), (3, 2), (0, 3))])
(TMP / "analytics" / "summary.json").write_text(json.dumps({"instagram": {"followers": 3, "posts": 40}}))
RECIPE = "# What's working (updated x)\n\n## Recipe from the data (the writer follows this)\n- Follow up QD-1: x.\n- Format: lean towards one_detail.\n\n## What drives views\n- Push: something\n"
(TMP / "analytics" / "insights.md").write_text(RECIPE)
S.CFG.update(instagram_trial=True, instagram_caption_test=True, instagram_hour_test=True, instagram_trial_share=0.5, instagram_caption_share=0.5, instagram_hour_share=0.5)
st = S.ig_state()
assert st["reels"] == 32 and st["median_views"] == 150 and st["own_medians"] and st["favoured"] == ["Gaming", "Sport"], st
assert [c["category"] for c in st["categories"]] == ["Gaming", "Sport", "Film", "Music"] and st["categories"][0]["median"] == 300 and st["categories"][0]["n"] == 8
assert (st["followers"], st["followers_week_ago"]) == (3, 1)                                    # summary.json now; the snapshot 7 days ago
assert st["week"] == {"reels": 16, "median": 250, "before_reels": 16, "before_median": 80}, st["week"]
t = st["tests"]
assert set(t) == {"trial", "caption", "hour"} and t["trial"]["arms"]["yes"]["n"] == 16 and t["trial"]["arms"]["no"]["n"] == 16
assert (t["trial"]["arms"]["yes"]["share"], t["trial"]["arms"]["no"]["share"]) == (0.8, 0.2)    # a proven arm takes 80% (drivers.csv)
assert t["trial"]["arms"]["yes"]["verdict"] == "push" and t["trial"]["arms"]["no"]["verdict"] == "cut back"
assert (t["caption"]["arms"]["short"]["share"], t["hour"]["arms"]["morning"]["share"]) == (0.5, 0.5) and all(x["on"] for x in t.values())
assert sum(a["n"] for a in t["hour"]["arms"].values()) == 32 and t["hour"]["arms"]["morning"]["median"] == 150
S.CFG["instagram_hour_test"] = False
assert S.ig_state()["tests"]["hour"]["on"] is False
S.CFG["instagram_hour_test"] = True
lines = S.ig_lines(st)
text = "\n".join(lines)
assert lines[0].startswith("## Instagram") and not V.DASH.search(text), text
assert "Gaming 300 (8), Sport 200 (8), Film 100 (8), Music 60 (8)" in text and "(32 Reels, typical 150)" in text, text
assert "Posted first, as soon as they are public: Gaming, Sport (Instagram's own medians" in text
assert "trial reel yes 16 at" in text and ", push against no 16" in text and "(80/20)" in text and "(50/50)" in text, text
assert "Followers: 3 (1 a week ago)" in text and "Last 7 days: 16 Reels measured, median 250 views" in text and "Cover frame at the hook: not asked yet" in text, text
out = S.ig_report()
written = (TMP / "analytics" / "insights.md").read_text()
assert written.startswith(RECIPE.rstrip("\n")) and written.count("## Instagram") == 1 and written.rstrip().endswith(lines[-1]), written
assert "## Instagram" not in re.search(r"## Recipe.*?(?=\n## )", written, re.S).group(0)         # the writer's Recipe section never reaches it
assert json.loads((TMP / "status" / "instagram.json").read_text())["favoured"] == ["Gaming", "Sport"] and out["reels"] == 32
S.ig_report()
assert (TMP / "analytics" / "insights.md").read_text() == written                                 # a rerun gives the same file
(TMP / "analytics" / "insights.md").unlink()
assert S.ig_write_insights(lines) is False and S.ig_report()["reels"] == 32                      # no insights.md yet: only the JSON
S.CFG.update(instagram_trial=True)
(TMP / "status" / "instagram_trial.json").write_text(json.dumps({"refused": iso(REAL_NOW), "error": "x"}))
assert S.ig_state()["tests"]["trial"]["paused"] is True and "paused after Meta refused one" in "\n".join(S.ig_lines(S.ig_state()))
(TMP / "status" / "instagram_trial.json").unlink()
STATE_FOR_HUB = S.ig_state()
print("8 state, insights section and status file ok")

# 9. analytics.py calls it after writing insights.md; docs/SERVICE.md is one page with the parts Charlie asked for
src = (_p.Path(REPO_DIR) / "pipeline" / "analytics.py").read_text()
assert src.index('(OUT / "insights.md").write_text') < src.index("social.ig_report()"), "analytics.py must call social.ig_report() after insights.md is written"
doc = (_p.Path(REPO_DIR) / "docs" / "SERVICE.md").read_text()
assert not V.DASH.search(doc) and 250 <= len(doc.split()) <= 800, len(doc.split())              # one page, no em or en dashes
for part in ("Proof", "Cost", "Risks", "First step", "inauthentic content", "1,000 subscribers", "10 million", "No public action"):
    assert part.lower() in doc.lower(), part
assert not re.search(r"\b(color|favorite|optimize|organize|analyze|center)\b", doc, re.I), "UK English"
print("9 hook and service note ok", len(doc.split()), "words")

# 10. the hub's Instagram card reads status/instagram.json (skipped where Playwright is missing)
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("10 hub card: playwright missing, skipped"); print("instagram first ok"); sys.exit(0)
REPO = _p.Path(REPO_DIR)
time.sleep = REAL_SLEEP
def run_hub(override):
    def raw(route):
        rel = route.request.url.split("/main/", 1)[-1].split("?")[0]
        if rel in override: route.fulfill(status=200, body=override[rel]); return
        f = REPO / rel
        if rel != "status/instagram.json" and f.is_file(): route.fulfill(status=200, body=f.read_bytes())
        else: route.fulfill(status=404, body="")
    with sync_playwright() as pw:
        b = pw.chromium.launch(); p = b.new_context(viewport={"width": 390, "height": 844}).new_page(); errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.route("https://raw.githubusercontent.com/**", raw)
        p.route("https://api.github.com/**", lambda r: r.fulfill(status=200, content_type="application/json", body="[]"))
        for pat in ("https://fonts.**", "https://api.frankfurter.app/**", "https://open.er-api.com/**", "https://cdnjs.cloudflare.com/**"):
            p.route(pat, lambda r: r.abort())
        p.goto((REPO / "docs" / "hub.html").as_uri()); p.wait_for_timeout(2500)
        p.click('#tabs [data-tab="insights"]'); p.wait_for_timeout(300)
        txt = p.inner_text("#insights"); wide = p.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        b.close()
    assert not errs, errs
    return txt, wide
txt, wide = run_hub({"status/instagram.json": json.dumps(STATE_FOR_HUB)})
card = txt.split("Instagram picks its own Reels", 1)[1].split("What is being changed now", 1)[0]
for want in ("Followers", "Reels measured", "Cover frame", "none asked yet", "Gaming 300", "Sport 200", "Posted first, as soon as public: Gaming, Sport",
             "Instagram's own medians", "Trial reel", "Caption", "Posting hour", "yes 16", "80%", "push", "cut back"):
    assert want in card, (want, card[:900])
assert wide, "no sideways scroll on a phone"
txt, wide = run_hub({})                                                  # the file is not there yet: a plain note, no error
assert "Filled in by the next full analytics run." in txt.split("Instagram picks its own Reels", 1)[1].split("What is being changed now", 1)[0]
print("10 hub card ok")
print("instagram first ok")
