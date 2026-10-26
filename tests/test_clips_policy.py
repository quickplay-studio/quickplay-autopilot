"""Offline test of the clips policy (pipeline/clips.py, 25 October 2026): one creator or niche per channel, the day's clips on the
channel with the best 7-day median views a clip, the idle channels' one retest clip a week, the stop rule (a median under 100 views
a clip after 30 public clips in 14 days: YouTube off, Instagram only, one decisions row, a needs-charlie issue), the Instagram-only
path, and the argument-against-framing and Instagram numbers in clips/insights.json. Stubs only: no network, no YouTube, no Instagram."""
import contextlib, csv, datetime as dt, io, json, os, pathlib, re, subprocess, sys, tempfile, types
REPO_DIR = str(pathlib.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
for k in list(os.environ):                          # no real account here: a test sets what it needs
    if k.startswith(("IG_", "FB_", "TIKTOK_")) or k in ("SOCIAL_KEY", "CLIPS_MODE", "CLIPS_COUNT", "CLIPS_MINUTES"): os.environ.pop(k)
Y = types.ModuleType("youtube"); sys.modules["youtube"] = Y          # no Google libraries needed here
import clips as C
import alerts as A
import freshness
import quota

UTC = dt.timezone.utc
BASE = dt.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)         # Sunday 25 October: the clocks went back that night, so UK time is UTC
REAL = json.loads(pathlib.Path(REPO_DIR, "clips", "campaigns.json").read_text())
LOG = []
C.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
C.time.sleep = lambda s: None
quota.allow, quota.spend = (lambda *a, **k: True), (lambda *a, **k: None)
freshness.log_row = lambda *a, **k: False                  # the late-upload log is the repository's own file: not written here
ISSUES = []
A.gh = lambda *a: ISSUES.append(a) or types.SimpleNamespace(stdout="https://github.com/x/y/issues/9\n", stderr="", returncode=0)
A.open_issues = lambda: {}
N = [0]


def world(now=BASE, channels=("clips", "gaming", "irl")):
    """A fresh root: sign-ins for the channels, empty plans, state, out and analytics, the real campaigns.json, a clock."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="qp-policy-"))
    for d in ("tokens", "clips/plans", "clips/state", "clips/out", "analytics", "status"): (root / d).mkdir(parents=True)
    for ch in channels: (root / "tokens" / f"youtube_{ch}.enc").write_text("x")
    C.ROOT, C.PLANS, C.STATE, C.OUT = root, root / "clips" / "plans", root / "clips" / "state", root / "clips" / "out"
    C.CEILING = C.STATE / "ceiling.json"
    C.CFG = json.loads(json.dumps(REAL)); C.NOW = now
    C.CFG["youtube_off"] = {}      # every channel starts with YouTube on: the live stop rule's decisions (gaming and clips off since 25 October) are not this test's starting point
    (root / "clips" / "campaigns.json").write_text(json.dumps(C.CFG))
    LOG.clear(); ISSUES.clear()
    return root


def srow(ch, views, hours=48.0, privacy="public", ig=None, as_of="2026-10-25T10:00:00+00:00", **kw):
    """One clips/stats.csv row."""
    N[0] += 1
    r = {"clip": f"{ch or 'clips'}-{N[0]}", "video": f"v{N[0]}", "campaign": "x", "channel": ch, "privacy": privacy, "hours_public": hours, "views": views, "as_of": as_of}
    if ig is not None: r["ig_views"] = ig
    r.update(kw)
    return r


def write_stats(root, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (root / "clips" / "stats.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval=""); w.writeheader(); w.writerows(rows)


def put_plan(root, cid, moments): (root / "clips" / "plans" / f"{cid}.json").write_text(json.dumps({"moments": moments}))
def get_plan(root, cid): return {m["id"]: m for m in json.loads((root / "clips" / "plans" / f"{cid}.json").read_text())["moments"]}
def decisions(root):
    p = root / "analytics" / "decisions.csv"
    return list(csv.DictReader(p.open())) if p.exists() else []
def iso(t): return t.isoformat().replace("+00:00", "Z")


# 1. the numbers: public clips a day old up to the window, per channel; an Instagram-only clip counts for Instagram only
root = world()
rows = ([srow("gaming", v) for v in (5, 7, 9)]
        + [srow("gaming", 900, hours=5), srow("gaming", 900, hours=200), srow("gaming", 900, privacy="private")]      # too young, over 7 days, not public
        + [srow("irl", v, ig=g) for v, g in ((2, None), (4, 30), (6, 10), (8, 20))]
        + [srow("irl", "", privacy="instagram", ig=500)]                      # posted on Instagram only: its Reel counts for Instagram, not for YouTube
        + [srow("", 1)])                                                      # no channel written: the first channel, clips
n = C.channel_numbers(rows)
assert (n["gaming"]["n"], n["gaming"]["median"], n["gaming"]["mean"], n["gaming"]["total"], n["gaming"]["ig_n"]) == (3, 7, 7.0, 21, 0), n["gaming"]
assert (n["irl"]["n"], n["irl"]["median"], n["irl"]["total"], n["irl"]["ig_n"], n["irl"]["ig_median"]) == (4, 5.0, 20, 4, 25.0), n["irl"]
assert n["clips"]["n"] == 1 and n["clips"]["median"] == 1 and n["clips"]["ig_median"] is None
assert C.channel_numbers(rows, days=14)["gaming"]["n"] == 4 and C.channel_numbers(rows, min_hours=0)["gaming"]["n"] == 4
assert "gaming" not in C.channel_numbers(rows, after={"gaming": "2026-10-23"})        # all went public on 23 October: on or before it
assert C.channel_numbers(rows, after={"gaming": "2026-10-22"})["gaming"]["n"] == 3
assert C.published_on(srow("a", 1)) == dt.date(2026, 10, 23) and C.published_on({"as_of": "x", "hours_public": 1}) is None
write_stats(root, [srow("gaming", 1, as_of="2026-10-24T10:00:00+00:00", clip="dup", video="vdup"), srow("gaming", 9, clip="dup", video="vdup")])
assert [r["views"] for r in C.stat_rows()] == ["9"], C.stat_rows()          # the latest row of a clip
print("1 numbers ok")

# 2. the volume channel: the best median; ties by mean then Instagram median; the one that had it keeps it unless clearly beaten
nums = {"gaming": {"n": 7, "median": 6.0, "mean": 9.57, "ig_median": None}, "irl": {"n": 10, "median": 0.0, "mean": 0.0, "ig_median": 0.0}}
assert C.pick_volume(["gaming", "irl"], nums) == "gaming" and C.pick_volume(["irl", "gaming"], nums) == "gaming" and C.pick_volume([], nums) is None
assert C.pick_volume(["clips", "irl"], {"irl": {"n": 3, "median": 0.0, "mean": 0.0}}) == "irl"          # measured at 0 beats not measured
assert C.pick_volume(["gaming", "irl"], {}) == "gaming" and C.pick_volume(["gaming", "irl"], {}, "irl") == "irl"
tie = {"gaming": {"n": 5, "median": 3.0, "mean": 3.0, "ig_median": 1.0}, "irl": {"n": 5, "median": 3.0, "mean": 3.4, "ig_median": 0.0}}
assert C.pick_volume(["gaming", "irl"], tie) == "irl"                       # same median: the better mean
tie["irl"]["mean"] = 3.0
assert C.pick_volume(["gaming", "irl"], tie) == "gaming"                    # same mean: the better Instagram median
two = {"gaming": {"n": 7, "median": 6.0, "mean": 9.0, "ig_median": None}, "irl": {"n": 7, "median": 6.5, "mean": 9.0, "ig_median": None}}
assert C.pick_volume(["gaming", "irl"], two) == "irl" and C.pick_volume(["gaming", "irl"], two, "gaming") == "gaming"     # not a view ahead
two["irl"]["median"] = 7.0
assert C.pick_volume(["gaming", "irl"], two, "gaming") == "irl"             # a view ahead
two["gaming"]["median"], two["irl"]["median"] = 100.0, 109.0
assert C.pick_volume(["gaming", "irl"], two, "gaming") == "gaming"
two["irl"]["median"] = 110.0
assert C.pick_volume(["gaming", "irl"], two, "gaming") == "irl"             # 10% ahead
print("2 volume channel ok")

# 3. roles, and the retest: an idle channel gets one clip on the seventh day after its last, then waits seven more
root = world()
write_stats(root, [srow("gaming", v) for v in (4, 6, 8)] + [srow("irl", 0) for _ in range(5)])
chans = {"gaming": ["tdr-mitch"], "irl": ["speed-expedia"]}
vp = C.volume_plan(chans)
assert vp["volume"] == "gaming" and vp["role"] == {"gaming": "volume", "irl": "retest"}, vp          # irl never had a clip: its retest is due now
put_plan(root, "speed-expedia", [{"id": "speed-expedia-01", "channel": "irl", "made": "2026-10-25T11:00:00+00:00", "start": 0, "end": 30}])
assert C.last_clip_at("irl") == dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC) and C.last_clip_at("gaming") is None
assert C.next_retest("irl") == dt.date(2026, 11, 1) and C.next_retest("gaming") == dt.date(2026, 10, 25)
roles = []
for d in range(15):
    C.NOW = BASE + dt.timedelta(days=d)
    roles.append(C.volume_plan(chans)["role"]["irl"])
    if roles[-1] == "retest": put_plan(root, "speed-expedia", [{"id": f"speed-expedia-{d:02d}", "channel": "irl", "made": C.NOW.isoformat(), "start": 0, "end": 30}])
assert roles == ["idle"] * 7 + ["retest"] + ["idle"] * 6 + ["retest"], roles
for d in range(8):                                  # the retest clip is a single moment, never a series episode
    C.NOW = BASE + dt.timedelta(days=d)
    got = C.allocate(1, None, "gaming", exclude_series=True)
    assert len(got) == 1 and not (C.CFG["campaigns"][next(iter(got))].get("rules") or {}).get("series"), got
C.NOW = BASE
C.CFG["youtube_off"] = {"gaming": "2026-10-20"}                    # a channel with YouTube off is never the volume channel
vp = C.volume_plan(chans)
assert vp["volume"] == "irl" and vp["role"] == {"gaming": "off", "irl": "volume"}, vp
C.CFG["youtube_off"] = {"gaming": "2026-10-20", "irl": "2026-10-20"}
assert C.volume_plan(chans)["volume"] is None and set(C.volume_plan(chans)["role"].values()) == {"off"}
print("3 roles and retest ok")

# 4. the places each role gets
root = world()
cp = lambda *a, **k: C.channel_places(*a, dry=True, **k)
assert cp("gaming", "volume", 0)[0] == 10 and cp("gaming", "volume", 4)[0] == 6 and cp("gaming", "volume", 12)[0] == 0
assert cp("gaming", None, 0)[0] == 10                                  # no plan (the plan failed): the channel makes its own day's number
assert cp("irl", "idle", 0)[0] == 0 and "next retest clip 2026-10-25" in cp("irl", "idle", 0)[1] and "per_day 0" in cp("irl", "idle", 0)[1]
assert cp("irl", "retest", 0)[0] == 1 and cp("irl", "retest", 1)[0] == 0
(root / "clips" / "reach.json").write_text(json.dumps({"channels": {"gaming": {"take_unseen": True}}}))        # YouTube shows nobody: the unseen cap
places, why = cp("gaming", "volume", 1)
assert places == 3 and "not showing its clips, 4 a day" in why and not (C.STATE / "unseen_gaming.json").exists() and not decisions(root)      # read only
C.channel_places("gaming", "volume", 1); C.channel_places("gaming", "volume", 1)
assert sum("gaming channel: 4 clips a day" in r["change"] for r in decisions(root)) == 1 and (C.STATE / "unseen_gaming.json").exists()      # noted once
(root / "clips" / "reach.json").write_text(json.dumps({"channels": {"gaming": {"take_unseen": False}}}))
assert C.channel_places("gaming", "volume", 0)[0] == 10 and not (C.STATE / "unseen_gaming.json").exists()
assert cp("irl", "off", 0)[0] == 0 and "no Instagram sign-in" in cp("irl", "off", 0)[1]                  # no Instagram account: nothing is made
os.environ["IG_CLIPS_TOKEN"], os.environ["IG_CLIPS_USER_ID"] = "token", "user"
assert C.instagram_ready("irl") and cp("irl", "off", 0)[0] == 3 and cp("irl", "off", 2)[0] == 1 and cp("irl", "off", 3)[0] == 0
assert cp("irl", "off", 0, planned=5)[0] == 1 and cp("irl", "off", 0, planned=6)[0] == 0                # inside social_per_day (6) with the day's other clips
iso_, _ = C.batch_time()
put_plan(root, "tdr-mitch", [{"id": f"tdr-mitch-0{i}", "channel": "gaming", "publish_at": iso_} for i in range(1, 5)])
assert C.scheduled_today() == 4 and cp("irl", "off", 0)[0] == 2
print("4 places ok")

# 5. one creator or niche per channel: every active campaign names its one channel; a moment is made for one channel only
root = world()
active = {cid: c for cid, c in C.CFG["campaigns"].items() if c.get("active")}
assert active and all(str(c.get("channel") or "").strip() and "channels" not in c for c in active.values()), "every active campaign names its one channel"
assert all(C.campaign_channels(cid) == [c["channel"]] == [C.channel_of(cid)] for cid, c in active.items())
seen = {}
for ch in {c["channel"] for c in active.values()}:
    for cid in C.allocate(20, None, ch):                       # a channel's allocation holds only its own campaigns, none in two channels
        assert C.campaign_channels(cid) == [ch] and cid not in seen, (cid, ch, seen); seen[cid] = ch
assert seen and set(C.channels()) == {"gaming", "irl"}, C.channels()          # clips has no campaign pinned to it
c = C.CFG["campaigns"]                                          # an entry still written with a "channels" list (the Mac's joins) is pinned
c["speed-expedia"].pop("channel"); c["speed-expedia"]["channels"] = ["clips", "irl"]
c["tdr-mitch"].pop("channel"); c["tdr-mitch"]["channels"] = ["clips"]
c["tdr-jenny"].pop("channel"); c["tdr-jenny"]["channels"] = ["gaming", "irl"]
c["forgegui-roblox"]["channels"] = ["clips", "irl"]              # not active: left alone
changed = C.pin_channels()
assert changed == {"speed-expedia": "irl", "tdr-mitch": "clips", "tdr-jenny": "gaming"}, changed
saved = json.loads((root / "clips" / "campaigns.json").read_text())["campaigns"]
assert saved["speed-expedia"]["channel"] == "irl" and "channels" not in saved["speed-expedia"] and saved["tdr-mitch"]["channel"] == "clips"
assert "channels" in saved["forgegui-roblox"] and C.pin_channels() == {} and any("channels pinned" in l for l in LOG)
c["tdr-flamingo"]["channels"] = ["clips", "irl"]; assert C.campaign_channels("tdr-flamingo") == ["gaming"]      # the "channel" wins
put_plan(root, "tdr-mitch", [                                    # the same moment on two channels: overlapping moments made for different channels
    {"id": "a", "channel": "gaming", "made": "t", "start": 10, "end": 40}, {"id": "b", "channel": "clips", "made": "t", "start": 30, "end": 60},
    {"id": "c", "channel": "gaming", "made": "t", "start": 35, "end": 70}, {"id": "d", "channel": "clips", "made": "t", "start": 100, "end": 130},
    {"id": "e", "channel": "irl", "start": 10, "end": 40}])      # e is not made yet
assert sorted((a, b) for _, a, b in C.channel_conflicts()) == [("a", "b"), ("b", "c")], C.channel_conflicts()
put_plan(root, "tdr-mitch", [{"id": "a", "channel": "gaming", "made": "t", "start": 10, "end": 40}, {"id": "b", "channel": "gaming", "made": "t", "start": 30, "end": 60}])
assert C.channel_conflicts() == []
print("5 one channel each ok")

# 6. the stop rule: a median under 100 views a clip after 30 public clips in 14 days
root = world()
many = lambda ch, n, views, **kw: [srow(ch, views, **kw) for _ in range(n)]
rows = (many("gaming", 30, 99) + many("irl", 29, 0) + many("clips", 30, 100)
        + many("old", 40, 0, hours=15 * 24) + many("young", 40, 0, hours=10)               # over 14 days old; under a day old
        + many("mixed", 16, 500) + many("mixed", 14, 0))
st = C.stop_status(rows)
assert st["gaming"]["fires"] and st["gaming"]["clips"] == 30 and st["gaming"]["median"] == 99, st["gaming"]
assert not st["irl"]["fires"] and not st["clips"]["fires"] and not st["mixed"]["fires"] and "old" not in st and "young" not in st, st
assert C.stop_status(many("gaming", 31, 99, privacy="private")) == {}                       # private clips are not public clips
assert C.policy_n("clips_stop_median", 1) == 100 and C.policy_n("nothing_like_this", 7) == 7.0
fired = C.stop_check(rows)                                                                 # fires for gaming only
assert fired == ["gaming"] and C.youtube_off() == {"gaming": "2026-10-25"}, (fired, C.youtube_off())
assert json.loads((root / "clips" / "campaigns.json").read_text())["youtube_off"] == {"gaming": "2026-10-25"}
dec = decisions(root)
assert len(dec) == 1 and dec[0]["area"] == "Clips channels" and "gaming channel: YouTube uploads off, Instagram only" in dec[0]["change"], dec
assert dec[0]["by"] == "clips.py (automatic)" and dec[0]["date"] == "2026-10-25" and dec[0]["check_on"] == "2026-11-08" and "median 99" in dec[0]["why"], dec
made = [c for c in ISSUES if c[:2] == ("issue", "create")]
assert len(made) == 1 and made[0][made[0].index("--title") + 1] == "🛑 Clips: the gaming channel stops YouTube uploads", made
assert [made[0][i + 1] for i, x in enumerate(made[0]) if x == "--label"] == ["alert", "needs-charlie"], made[0]
body = made[0][made[0].index("--body") + 1]
assert "tdr-mitch" in body and "30 public clips" in body and "99 views" in body and "Nothing already on YouTube is deleted" in body
assert any("STOP RULE" in l and "gaming" in l for l in LOG) and json.loads((C.STATE / "stopped.json").read_text()) == {"gaming": "2026-10-25"}
assert C.stop_check(rows) == [] and len(decisions(root)) == 1 and len([c for c in ISSUES if c[:2] == ("issue", "create")]) == 1      # once only
del C.CFG["youtube_off"]["gaming"]                                                         # Charlie starts the channel again: the same 30 clips do not stop it
assert C.stop_check(rows) == [] and C.youtube_off() == {}
C.NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
fresh = many("gaming", 30, 50, as_of="2026-11-20T10:00:00+00:00")                          # 30 new clips, none of them a day older than the restart
assert C.stop_check(fresh) == ["gaming"] and C.youtube_off() == {"gaming": "2026-11-20"} and len(decisions(root)) == 2
root = world()
for cid, c in C.CFG["campaigns"].items():                  # a channel no campaign is pinned to: recorded and told, nothing else changes
    if c.get("channel") == "irl": c["channel"] = "gaming"
assert C.stop_check(many("irl", 30, 0)) == ["irl"]
made = [c for c in ISSUES if c[:2] == ("issue", "create")]
assert len(made) == 1 and "No active campaign is pinned to this channel" in made[0][made[0].index("--body") + 1], made
print("6 stop rule ok")

# 7. an allocation change is one decisions row; a retest day is not a change
root = world()
chans = {"gaming": ["tdr-mitch"], "irl": ["speed-expedia"]}
write_stats(root, [srow("gaming", v) for v in (4, 6, 8)] + [srow("irl", 0) for _ in range(5)])
C.note_plan(C.volume_plan(chans))
dec = decisions(root)
assert len(dec) == 1 and dec[0]["area"] == "Clips channels" and "The day's clips go to the gaming channel" in dec[0]["change"] and "irl idle" in dec[0]["change"], dec
assert "median 6 views a clip over 3 clips" in dec[0]["why"] and dec[0]["check_on"] == "2026-11-01", dec
state = json.loads((C.STATE / "allocation.json").read_text())
assert state["volume"] == "gaming" and state["idle"] == ["irl"] and state["off"] == [] and state["since"] == "2026-10-25"
C.note_plan(C.volume_plan(chans)); assert len(decisions(root)) == 1                          # the same plan again: no new row
C.NOW = BASE + dt.timedelta(days=7)                                                         # irl's retest day: still idle, still the same row
assert C.volume_plan(chans)["role"]["irl"] == "retest"
C.note_plan(C.volume_plan(chans)); assert len(decisions(root)) == 1
write_stats(root, [srow("gaming", v) for v in (4, 6, 8)] + [srow("irl", v) for v in (30, 40, 50)])        # irl overtakes gaming
C.note_plan(C.volume_plan(chans)); dec = decisions(root)
assert len(dec) == 2 and "go to the irl channel" in dec[1]["change"] and "gaming idle" in dec[1]["change"], dec
assert json.loads((C.STATE / "allocation.json").read_text())["volume"] == "irl"
print("7 decisions once ok")

# 8. Instagram only: a made clip of a channel with YouTube off is kept for Instagram, never uploaded to YouTube
root = world()
C.CFG["youtube_off"] = {"irl": "2026-10-25"}
GH = []
C.gh = lambda *a, **k: GH.append(a) or subprocess.CompletedProcess(a, 0, "", "")
fresh_t, stale_t = "2026-10-25T09:00:00+00:00", "2026-10-23T09:00:00+00:00"
mo = lambda i, ch, made=fresh_t, **kw: {"id": f"speed-expedia-0{i}", "file": f"speed-expedia-0{i}.mp4", "channel": ch, "made": made, "hook": "a", "title": "t", "start": 0, "end": 30, **kw}
for i in (1, 2, 3, 4, 6): (C.OUT / f"speed-expedia-0{i}.mp4").write_bytes(b"x")           # 05 has no file
put_plan(root, "speed-expedia", [mo(1, "irl"), mo(2, "gaming"), mo(3, "irl", stale_t), mo(4, "irl", None, skipped="x"), mo(5, "irl")])
done = C.ig_only_assets("speed-expedia")
batch_iso, _ = C.batch_time(C.CFG["campaigns"]["speed-expedia"].get("platform"))
ms = get_plan(root, "speed-expedia")
assert [m["id"] for m in done] == ["speed-expedia-01"], done
m1 = ms["speed-expedia-01"]
assert m1["video"] == C.IG_ONLY and m1["ig_only"] is True and m1["publish_at"] == batch_iso and m1["mode"] == "instagram" and m1["uploaded"], m1
assert m1["asset_url"] == f"https://github.com/{C.REPO}/releases/download/clips-out/speed-expedia-01.mp4"
assert ("release", "upload", "clips-out", str(C.OUT / "speed-expedia-01.mp4"), "--clobber") in GH
assert not any(ms[k].get("video") for k in ("speed-expedia-02", "speed-expedia-03", "speed-expedia-04", "speed-expedia-05"))       # another channel, stale, skipped, no file
assert any("Instagram only" in l and "speed-expedia-01" in l for l in LOG) and C.ig_only_assets("speed-expedia") == []             # once only
UPS = []
Y.upload = lambda client, path, title, *a, **k: (UPS.append((client, pathlib.Path(path).name)), f"vid{len(UPS)}")[1]
C.clips_client = lambda ch: ch
C.upload("speed-expedia")                                      # YouTube takes the gaming clip; the Instagram-only one and the stale one stay out
assert UPS == [("gaming", "speed-expedia-02.mp4")], UPS
ms = get_plan(root, "speed-expedia")
assert ms["speed-expedia-01"]["video"] == C.IG_ONLY and ms["speed-expedia-02"]["video"] == "vid1" and not ms["speed-expedia-03"].get("video")
assert C.uploads_24h("irl") == 0 and C.uploads_24h("gaming") == 1 and C.scheduled_today("irl") == 1      # the Instagram-only clip is not a YouTube upload
C.gh = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network"))                  # the file cannot be kept: not posted anywhere, never on YouTube
put_plan(root, "speed-expedia", [mo(6, "irl")])
assert C.ig_only_assets("speed-expedia") == []
m6 = get_plan(root, "speed-expedia")["speed-expedia-06"]
assert m6["video"] == C.IG_ONLY and m6["ig_only"] and m6["pulled"].startswith("Instagram asset not kept") and not m6.get("asset_url"), m6
UPS.clear(); C.upload("speed-expedia"); assert UPS == [] and any("not posted anywhere" in l for l in LOG)
print("8 instagram-only assets ok")

# 9. social_posts posts an Instagram-only clip from the asset release, with no YouTube video behind it; the YouTube-side jobs skip it
root = world()
os.environ["IG_CLIPS_TOKEN"], os.environ["IG_CLIPS_USER_ID"] = "token", "user"
C.CFG["youtube_off"] = {"irl": "2026-10-25"}
C.gh = lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
(C.OUT / "speed-expedia-01.mp4").write_bytes(b"x")
put_plan(root, "speed-expedia", [mo(1, "irl", start=5, end=35)])
C.ig_only_assets("speed-expedia")
POSTS = []
S = types.ModuleType("social"); sys.modules["social"] = S
S.IG_API, S._FB = "https://graph.example", {}
S.apply_stored_keys, S.load, S.ig_tokens, S.fb_tokens = (lambda: None), (lambda name: {}), (lambda: {}), (lambda: None)
S.ig_post = lambda ig, url, caption: (POSTS.append((ig["user"], url, caption)), "media123")[1]
real_requests = sys.modules.get("requests")
R = types.ModuleType("requests"); R.get = lambda url, **kw: types.SimpleNamespace(json=lambda: {"permalink": "https://www.instagram.com/reel/abc/"}); sys.modules["requests"] = R
C.NOW = dt.datetime(2026, 10, 25, 19, 5, tzinfo=UTC)         # the batch time has come
assert C.social_posts(force=True) == 1
if real_requests is not None: sys.modules["requests"] = real_requests
else: sys.modules.pop("requests")
assert POSTS and POSTS[0][1].endswith("/clips-out/speed-expedia-01.mp4") and POSTS[0][2].startswith("#ad "), POSTS
m1 = get_plan(root, "speed-expedia")["speed-expedia-01"]
assert m1["instagram"]["media"] == "media123" and m1["instagram"]["url"] == "https://www.instagram.com/reel/abc/" and m1["video"] == C.IG_ONLY
sub = list(csv.DictReader((root / "clips" / "submit.csv").open()))
assert len(sub) == 1 and sub[0]["platform"] == "instagram" and sub[0]["clip"] == "speed-expedia-01" and sub[0]["channel"] == "irl", sub
# a profane Instagram-only clip is pulled before it posts, without a call to YouTube; a YouTube clip is still made private
CALLS = []
class _V:
    def update(self, part, body): CALLS.append((part, body["id"])); return types.SimpleNamespace(execute=lambda: {})
C.clips_client = lambda ch: types.SimpleNamespace(videos=lambda: _V())
future = iso(C.NOW + dt.timedelta(hours=3))
put_plan(root, "speed-expedia", [
    mo(1, "irl", video=C.IG_ONLY, ig_only=True, publish_at=future, hook="WTF is this"),
    mo(2, "irl", video=C.IG_ONLY, ig_only=True, publish_at=future, hook="A clean one"),
    mo(3, "gaming", video="yt3", publish_at=future, hook="WTF is that")])
assert C.review() == 2 and CALLS == [("status", "yt3")], CALLS
ms = get_plan(root, "speed-expedia")
assert ms["speed-expedia-01"]["pulled"] == "profanity: WTF" and ms["speed-expedia-03"]["pulled"] == "profanity: WTF" and not ms["speed-expedia-02"].get("pulled")
# the comment job leaves an Instagram-only clip alone (there is no YouTube video to comment on)
C.clips_client = lambda ch: (_ for _ in ()).throw(AssertionError("an Instagram-only clip has no YouTube video"))
put_plan(root, "speed-expedia", [mo(1, "irl", video=C.IG_ONLY, ig_only=True, publish_at=iso(C.NOW - dt.timedelta(hours=1)))])
assert C.engage() == 0 and "question" not in get_plan(root, "speed-expedia")["speed-expedia-01"]
print("9 instagram posting and guards ok")

# 10. the stats row of an Instagram-only clip: its Reel's numbers, privacy "instagram", no YouTube views; the readers of public clips skip it
root = world(now=dt.datetime(2026, 10, 26, 20, 0, tzinfo=UTC))
C.CFG["youtube_off"] = {"irl": "2026-10-25"}
C.ig_numbers = lambda media: {"ig_views": 120, "ig_reach": 90, "ig_watch_s": 4.2}
put_plan(root, "speed-expedia", [mo(1, "irl", video=C.IG_ONLY, ig_only=True, publish_at="2026-10-25T19:00:00Z", start=5, end=35,
                                    instagram={"media": "media123", "url": "https://www.instagram.com/reel/abc/", "at": "2026-10-25T19:05"},
                                    tests={"take": "voice", "take_style": "argument", "layout": "full"}),
                                 mo(2, "irl", video=C.IG_ONLY, ig_only=True, publish_at="2026-10-25T19:00:00Z", pulled="profanity: WTF",      # pulled: no row
                                    instagram={"media": "m2"})])
C.stats()
srows = list(csv.DictReader((root / "clips" / "stats.csv").open()))
assert len(srows) == 1 and srows[0]["clip"] == "speed-expedia-01" and srows[0]["privacy"] == "instagram" and srows[0]["views"] == "", srows
assert srows[0]["ig_views"] == "120" and srows[0]["video"] == "" and srows[0]["channel"] == "irl" and srows[0]["hours_public"] == "25.0" and srows[0]["test_layout"] == "full"
assert C.channel_numbers()["irl"]["n"] == 0 and C.channel_numbers()["irl"]["ig_median"] == 120          # Instagram numbers, no YouTube clip
ins = json.loads((root / "clips" / "insights.json").read_text())
assert ins["clips"] == 0 and ins["channels"]["by_channel"]["irl"]["ig_median_views_7d"] == 120 and ins["channels"]["by_channel"]["irl"]["youtube_off_since"] == "2026-10-25"
assert ins["tests"]["layout"]["arms"]["full"]["ig_n"] == 1 and ins["tests"]["layout"]["arms"]["full"]["n"] == 0
assert C.median_views("speed-expedia") is None and C.reach_share(100) == 0.25            # an Instagram-only row is not a public clip
print("10 stats row ok")

# 11. insights: argument against framing by YouTube views and by Instagram views; never a verdict from clips nobody watched
def trow(arm, views, ig=None, hours=48, privacy="public", **kw):
    r = {"privacy": privacy, "hours_public": hours, "views": views, "campaign": "c", "test_take_style": arm}
    if ig is not None: r["ig_views"] = ig
    r.update(kw); return r
root = world()
both = [trow("argument", 50, 200) for _ in range(3)] + [trow("framing", 10, 100) for _ in range(3)]
ts = C.insights(both)["take_style"]
assert ts["verdict"] == "argument" and "leads on YouTube views and on Instagram views" in ts["note"] and "3 with Instagram views" in ts["note"], ts
split = [trow("argument", 50, 100) for _ in range(3)] + [trow("framing", 10, 400) for _ in range(3)]
ts = C.insights(split)["take_style"]
assert ts["verdict"] is None and "YouTube views favour argument, Instagram views favour framing" in ts["note"], ts
only_ig = [trow("argument", 0, 300) for _ in range(3)] + [trow("framing", 0, 50) for _ in range(3)]
ts = C.insights(only_ig)["take_style"]
assert ts["verdict"] == "argument" and "leads on Instagram views; the other measure has not decided" in ts["note"], ts
few = [trow("argument", 90, 90) for _ in range(2)] + [trow("framing", 5, 5) for _ in range(2)]
ts = C.insights(few)["take_style"]
assert ts["verdict"] is None and ts["note"].startswith("no verdict yet"), ts
ig_rows = [trow("argument", "", 300, privacy="instagram", hours=30) for _ in range(3)] + [trow("framing", 0, 50) for _ in range(3)]       # Instagram-only clips count for Instagram
out = C.insights(ig_rows)
arm = out["tests"]["take_style"]["arms"]["argument"]
assert arm["n"] == 0 and arm["ig_n"] == 3 and arm["ig_median_views"] == 300 and out["tests"]["take_style"]["best_ig"] == "argument" and out["clips"] == 3, out["tests"]["take_style"]
young = [trow("argument", 500, 500, hours=5) for _ in range(5)]                          # under a day old: not measured yet
assert C.insights(young)["take_style"]["verdict"] is None and C.insights(young)["tests"]["take_style"]["arms"]["argument"]["ig_n"] == 0
assert all(v["best"] is None and v["best_ig"] is None for v in C.insights([trow("argument", 0, 0) for _ in range(9)])["tests"].values())
print("11 take style ok")

# 12. the run: the volume channel gets the day, the idle one its retest clip, the stopped one Instagram only; the allocation command reads the same plan
root = world()
os.environ.pop("IG_CLIPS_TOKEN", None); os.environ.pop("IG_CLIPS_USER_ID", None)
write_stats(root, [srow("gaming", v) for v in (4, 6, 8)] + [srow("irl", 0) for _ in range(5)])
S.apply_stored_keys = lambda: None
MADE = []
C.check_campaigns, C.review, C.source, C.plan, C.plan_parts = (lambda: None), (lambda: 0), (lambda cid: None), (lambda cid, n=8: None), (lambda cid: None)
C.unmade, C.spill, C.stats, C.upload = (lambda cid: 99), (lambda *a, **k: 0), (lambda: None), (lambda cid, mode=None: [])
C.make = lambda cid, count=None, channel=None: (MADE.append((cid, count, channel)), [{"id": cid}])[1]
want_gaming, want_irl = C.allocate(10, None, "gaming"), C.allocate(1, None, "irl", exclude_series=True)
C.main(["run"])
got = {}
for cid, count, ch in MADE: got.setdefault(ch, {})[cid] = count
assert got == {"gaming": want_gaming, "irl": want_irl} and sum(want_irl.values()) == 1 and sum(want_gaming.values()) >= 5, (got, want_gaming, want_irl)
lines = [l for l in LOG if l.startswith("channel ")]
assert lines[0].startswith("channel gaming: volume: ") and "7-day median 6 views a clip over 3 clips" in lines[0], lines     # the volume channel is planned first
assert lines[1].startswith("channel irl: retest: idle, but its one retest clip is due") and len(lines) == 2, lines
assert len(decisions(root)) == 1 and "gaming" in decisions(root)[0]["change"]
MADE.clear(); C.main(["run"])
assert len(decisions(root)) == 1                              # the same plan on the next run: no new row
printed = io.StringIO()
with contextlib.redirect_stdout(printed): C.main(["allocation"])
rep = json.loads(printed.getvalue())
assert rep["volume"] == "gaming" and rep["channels"]["gaming"]["role"] == "volume" and rep["channels"]["gaming"]["campaigns"] == want_gaming, rep["channels"]["gaming"]
assert rep["channels"]["irl"]["places"] in (0, 1) and set(rep["channels"]) == {"gaming", "irl"}
# a stopped channel: Instagram only, inside social_per_day with the day's other clips
os.environ["IG_CLIPS_TOKEN"], os.environ["IG_CLIPS_USER_ID"] = "token", "user"
C.CFG["youtube_off"] = {"irl": "2026-10-25"}
MADE.clear(); LOG.clear(); C.main(["run"])
off_made = sum(n for cid, n, ch in MADE if ch == "irl")
assert off_made == max(0, min(3, 6 - sum(want_gaming.values()))) and any(l.startswith("channel irl: off: YouTube off, Instagram only") for l in LOG), (MADE, LOG)
# a test run (CLIPS_MODE=private) makes no clip for a stopped channel
os.environ["CLIPS_MODE"] = "private"; MADE.clear(); LOG.clear(); C.main(["run"])
assert not [1 for _, _, ch in MADE if ch == "irl"] and any("YouTube uploads are off, no test clips" in l for l in LOG), (MADE, LOG)
os.environ.pop("CLIPS_MODE")
print("12 the run ok")

# 13. new text and settings carry no em or en dashes; every policy setting is a number
bad = chr(0x2013) + chr(0x2014)
campaigns_text = pathlib.Path(REPO_DIR, "clips", "campaigns.json").read_text()
assert not any(ch in campaigns_text for ch in bad)
src = pathlib.Path(REPO_DIR, "pipeline", "clips.py").read_text()
for text in (src[src.index("# ----- one creator or niche per channel"):src.index("def submit_site(c)")],        # the policy block
             src[src.index("def lead(arms"):src.index("def insights(rows)")], src[src.index("def ig_only_row"):src.index("def reach_check")]):
    assert not any(ch in text for ch in bad)
for k in ("clips_window_days", "clips_retest_days", "clips_stop_median", "clips_stop_clips", "clips_stop_days", "clips_ig_only_per_day"):
    assert isinstance(REAL[k], int) and REAL[k] > 0, k
assert isinstance(REAL["youtube_off"], dict) and all(dt.date.fromisoformat(str(v)) for v in REAL["youtube_off"].values()), REAL["youtube_off"]    # channels the stop rule switched off, each with the day it did
print("13 text ok")
print("clips policy ok")
