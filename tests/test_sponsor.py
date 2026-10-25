"""Offline test of daily sponsorship (25 October; Charlie: campaigns on Whop Content Rewards and Vyro pay per 1,000 views for Shorts
that use a sound or carry a brand hashtag, no footage and no Partner Programme needed; Daily does about 1,300 views a day):
1. pipeline/sponsor.py: which campaigns are live, the share drawn by board id, the sad-story rule, hashtags, the #ad lines, the
   sound file checks, the clips/submit.csv rows (platform youtube, channel daily), and clips.py never making clips for one
2. the writer records test.sponsor (and leaves the board alone while no daily campaign is live)
3. run_board.py: the sound, the description, the localisations and the tags of a Short that carries a campaign; a campaign whose
   sound cannot be fetched, or that has ended, is not carried at all
4. render3.py plays the campaign's sound as the music track
5. cross-post captions start with #ad; drivers.py and analytics.py measure the arm
6. the scout tells a sound or hashtag campaign from a clips one and lists it under "For Quickplay Daily's own views"
7. the Mac's list names a campaign to join, and the Daily account on a Vyro row
8. upload.py passes paid promotion to YouTube
Stubs only: temp folders, no network, no key, no model."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, copy, csv, datetime as dt, inspect, io, json, os, shutil, subprocess, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
os.environ["WRITE_DRY"] = "1"
sys.argv = ["analytics.py", "--fast"]
DASHES = chr(0x2013) + chr(0x2014)
import sponsor as SP

# 1. sponsor.py ----------------------------------------------------------------------------------------------------------------
camps = {
    "spring": {"daily": True, "active": True, "name": "Spring Sound Challenge", "card": "Spring Sound Challenge (Reach)", "platform": "Vyro",
               "url": "https://app.vyro.com/campaigns/spring", "pay_per_1k": 1.5, "subject": "Spring", "ends": "2026-11-30",
               "hashtags": ["#SpringSound", "springfest", "#fyp", "#ad", "#springsound"], "sound_url": "https://example.com/spring.mp3"},
    "tags": {"daily": True, "active": True, "name": "Brand tags", "platform": "Content Rewards", "url": "https://contentrewards.com/c/campaigns/abc",
             "hashtags": ["#BrandX"], "ends": "2026-11-30"},
    "paused": {"daily": True, "active": False, "hashtags": ["#aaa1"]},
    "ended": {"daily": True, "active": True, "hashtags": ["#aaa2"], "ends": "2026-10-24"},
    "off": {"daily": True, "active": True, "why_off": "budget spent", "hashtags": ["#aaa3"]},
    "bare": {"daily": True, "active": True},
    "clips": {"active": True, "source": {"kind": "gdrive"}, "rules": {"focus": "x"}, "platform": "Vyro", "card": "Clips card"},
}
NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
live = SP.active(NOW, camps)
assert sorted(live) == ["spring", "tags"], sorted(live)                   # not paused, ended, switched off, empty or an ordinary clips campaign
camps["ended"]["ends"] = "2026-10-25"
assert "ended" in SP.active(NOW, camps)                                   # its last day still counts
camps["ended"]["ends"] = "2026-10-24"
assert SP.active(NOW, {}) == {}

assert SP.hashtags(camps["spring"]) == ["#SpringSound", "#springfest"], SP.hashtags(camps["spring"])      # no #fyp, #ad or repeat
assert SP.label(camps["spring"]) == "Spring Sound Challenge"
line = SP.ad_line(camps["spring"])
assert line.startswith("#ad Paid promotion") and "Spring Sound Challenge" in line and not any(c in line for c in DASHES), line
meta = SP.with_hashtags({"hashtags": ["#Gaming", "#springsound", "#Steam"]}, camps["spring"])
assert meta["hashtags"] == ["#ad", "#SpringSound", "#springfest", "#Gaming", "#Steam"], meta["hashtags"]
assert SP.track(camps["spring"]) == {"title": "Spring Sound Challenge", "artist": "Spring", "source": "supplied by the campaign"}
on = {"sponsor": {"applied": True, "hashtags": ["#SpringSound", "#springfest", "#third"]}}
assert SP.applied(on) and not SP.applied({"sponsor": {"applied": False}}) and not SP.applied({}) and not SP.applied({"sponsor": "x"})
assert SP.caption(on, "  Title\n\nSummary") == "#ad Title\n\nSummary" and SP.caption({}, "Title") == "Title"
cb = SP.caption_board(on, {"meta": {"title": "T", "hashtags": ["#Gaming", "#SpringSound", "#Steam"]}})
assert cb["meta"]["hashtags"] == ["#SpringSound", "#springfest", "#Gaming", "#Steam"] and cb["meta"]["title"] == "T", cb
plain_board = {"meta": {"hashtags": ["#a"]}}
assert SP.caption_board({}, plain_board) is plain_board

assert SP.share({}) == 0.3 and SP.share({"daily_sponsor_share": 0.5}) == 0.5 and SP.share({"daily_sponsor_share": "x"}) == 0.3
assert SP.share({"daily_sponsor_share": 7}) == 1.0 and json.loads(open("config.json").read())["daily_sponsor_share"] == 0.3
ids = [f"QD-{i:03d}" for i in range(1, 2001)]
arms = [SP.pick(i, live, 0.3) for i in ids]
frac = sum(a != "none" for a in arms) / len(arms)
assert 0.26 < frac < 0.34 and {a for a in arms if a != "none"} == {"spring", "tags"}, frac      # 3 in 10, both campaigns used
assert arms == [SP.pick(i, live, 0.3) for i in ids]                       # fixed by the board id
assert all(SP.pick(i, live, 1.0) in live for i in ids[:100]) and all(SP.pick(i, live, 0.0) == "none" for i in ids[:100])
assert SP.pick("QD-001", {}) is None                                      # dormant: nothing to decide

assert SP.sombre({"meta": {"title": "Famous singer dies at 70", "summary": ""}})
assert SP.sombre({"meta": {"title": "x", "summary": "y"}, "beats": [{"say": "A fatal crash closed the road."}]})
assert not SP.sombre({"meta": {"title": "Free Steam games this week", "summary": "Three games are free."}, "beats": [{"say": "Hurry."}]})
assert not SP.sombre({})

assert SP.direct_url("https://drive.google.com/file/d/AbC_123-x/view?usp=sharing") == "https://drive.google.com/uc?export=download&id=AbC_123-x"
assert SP.direct_url("https://drive.google.com/open?id=ZZ99") == "https://drive.google.com/uc?export=download&id=ZZ99"
assert SP.direct_url("https://www.dropbox.com/s/abc/song.mp3?dl=0") == "https://www.dropbox.com/s/abc/song.mp3?dl=1"
assert SP.direct_url("https://www.dropbox.com/s/abc/song.mp3") == "https://www.dropbox.com/s/abc/song.mp3?dl=1"
assert SP.direct_url("https://example.com/a.mp3") == "https://example.com/a.mp3"
print("1a campaigns, share, #ad lines ok")

# the sound file: what is accepted and what is not (the link, the size, a web page, no sound in it)
class Resp:
    def __init__(self, code=200, content=b"", ctype="audio/mpeg"): self.status_code, self.content, self.headers = code, content, {"content-type": ctype}
got = []
def getter(resp):
    def g(url, timeout=0): got.append(url); return resp
    return g
sd = SCRATCH / "sound"
audio = b"ID3" + bytes(9000)
c = {"sound_url": "https://drive.google.com/file/d/AbC/view"}
real_duration = SP.duration
SP.duration = lambda p: 12.0
path, why = SP.fetch_sound(c, sd, "QD-1", get=getter(Resp(200, audio)))
assert path == sd / "QD-1.sound" and path.read_bytes() == audio and why == "" and got[-1] == "https://drive.google.com/uc?export=download&id=AbC", (path, why, got)
for resp, frag in ((Resp(404), "404"), (Resp(200, b"<!DOCTYPE html><html>x" + bytes(9000), "text/html"), "web page"),
                   (Resp(200, b"x" * 100), "too small"), (Resp(200, bytes(26_000_000)), "over 25 MB")):
    path, why = SP.fetch_sound(c, sd, "QD-2", get=getter(resp))
    assert path is None and frag in why, (frag, why)
path, why = SP.fetch_sound({"sound_url": "http://example.com/a.mp3"}, sd, "QD-3", get=getter(Resp(200, audio)))
assert path is None and "https" in why
assert SP.fetch_sound({}, sd, "QD-3")[0] is None
def no_route(url, timeout=0): raise OSError("no route")
path, why = SP.fetch_sound(c, sd, "QD-4", get=no_route)
assert path is None and "download failed" in why
SP.duration = lambda p: 1.2
path, why = SP.fetch_sound(c, sd, "QD-5", get=getter(Resp(200, audio)))
assert path is None and "1.2 seconds" in why and not (sd / "QD-5.sound").exists()
SP.duration = lambda p: 0.0
assert "no sound" in SP.fetch_sound(c, sd, "QD-6", get=getter(Resp(200, audio)))[1]
SP.duration = lambda p: None                                              # no ffprobe on the machine: the file is taken as it is
assert SP.fetch_sound(c, sd, "QD-7", get=getter(Resp(200, audio)))[0] is not None
SP.duration = real_duration
if shutil.which("ffmpeg") and shutil.which("ffprobe"):
    wav = SCRATCH / "tone.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", str(wav)], check=True)
    junk = SCRATCH / "junk.bin"; junk.write_bytes(b"not a sound " * 1000)
    assert 3.5 < SP.duration(wav) < 4.5 and SP.duration(junk) == 0.0, (SP.duration(wav), SP.duration(junk))
print("1b the sound file checks ok")

# the submission rows: one for each Short that carries a campaign, once, in the file's own columns
R = SCRATCH / "rows"; (R / "clips").mkdir(parents=True); (R / "status").mkdir()
camps2 = copy.deepcopy(camps); camps2["tags"]["submit"] = {"where": "the add-clips page https://app.vyro.com/campaigns/add-clips"}
(R / "clips" / "campaigns.json").write_text(json.dumps({"campaigns": camps2}))
def status(sid, **kw): (R / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "title": f"Short {sid}", **kw}))
carries = lambda cid: {"campaign": cid, "applied": True}
status("QD-901", sponsor=carries("spring"), video="vidA", url="https://youtube.com/shorts/vidA", publish_at="2026-10-20T07:00:00Z")
status("QD-902", video="vidB", publish_at="2026-10-20T08:00:00Z")                                              # no campaign
status("QD-903", sponsor={"campaign": "spring", "applied": False, "why": "x"}, video="vidC", publish_at="2026-10-20T09:00:00Z")
status("QD-904", sponsor=carries("spring"), publish_at="2026-10-20T10:00:00Z")                                 # not uploaded yet
status("QD-905", sponsor=carries("paused"), video="vidE", publish_at="2026-10-20T11:00:00Z")                   # its campaign is off
status("QD-906", sponsor=carries("spring"), video="vidF", publish_at="2026-10-14T11:00:00Z")                   # long gone
status("QD-907", sponsor=carries("tags"), video="vidG", publish_at="2026-10-20T12:30:00Z")                     # has its row already
status("QD-908", sponsor=carries("tags"), video="vidH", publish_at="2026-10-20T13:30:00Z")
head = SP.SUBMIT_FIELDS + ["note"]
with (R / "clips" / "submit.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=head); w.writeheader()
    w.writerow({"clip": "old1", "campaign": "clips", "platform": "youtube", "submitted": "2026-10-19 19:05", "channel": "clips", "note": "kept"})
    w.writerow({"clip": "QD-907", "campaign": "tags", "platform": "youtube", "channel": "daily"})
T = dt.datetime(2026, 10, 20, 15, 0, tzinfo=dt.timezone.utc)
new = SP.rows(root=R, now=T, write=False)
assert [r["clip"] for r in new] == ["QD-901", "QD-908"], [r["clip"] for r in new]
r1, r2 = new
assert (r1["campaign"], r1["platform"], r1["channel"], r1["submitted"]) == ("spring", "youtube", "daily", ""), r1
assert r1["public_at_uk"] == "2026-10-20 08:00" and r1["video"] == "https://youtube.com/shorts/vidA", r1      # BST: the slot in UK time
assert r1["hashtags"] == "#SpringSound #springfest" and r1["campaign_url"] == "https://app.vyro.com/campaigns/spring" and r1["title"] == "Short QD-901", r1
assert r2["campaign_url"] == "https://app.vyro.com/campaigns/add-clips" and r2["video"] == "https://youtube.com/shorts/vidH" and r2["public_at_uk"] == "2026-10-20 14:30", r2
assert len(list(csv.DictReader((R / "clips" / "submit.csv").open()))) == 2                                       # write=False wrote nothing
SP.rows(root=R, now=T)
rows_out = list(csv.DictReader((R / "clips" / "submit.csv").open()))
assert [r["clip"] for r in rows_out] == ["old1", "QD-907", "QD-901", "QD-908"], [r["clip"] for r in rows_out]
assert rows_out[0]["note"] == "kept" and list(rows_out[0])[-1] == "note" and rows_out[2]["channel"] == "daily", rows_out[0]
assert SP.rows(root=R, now=T) == []                                                                              # again: nothing new
R2 = SCRATCH / "rows2"; (R2 / "clips").mkdir(parents=True); (R2 / "status").mkdir()
(R2 / "clips" / "campaigns.json").write_text(json.dumps({"campaigns": camps}))
(R2 / "status" / "QD-910.json").write_text(json.dumps({"id": "QD-910", "title": "T", "sponsor": carries("spring"), "video": "v1", "publish_at": "2026-10-20T07:00:00Z"}))
assert len(SP.rows(root=R2, now=T)) == 1                                                                         # no submit.csv yet: made with our columns
assert next(csv.reader((R2 / "clips" / "submit.csv").open())) == SP.SUBMIT_FIELDS
buf = io.StringIO()
with contextlib.redirect_stdout(buf): SP.main(["status"])
assert "dormant" in buf.getvalue() or "daily campaign(s) live" in buf.getvalue(), buf.getvalue()

try: import clips as C
except ImportError as e: C = None; print(f"(clips needs more packages than this environment has: {e})")
if C:
    assert SP.SUBMIT_FIELDS == C.SUBMIT_FIELDS, "the rows must keep clips.py's columns"
    real_cfg = C.CFG; C.CFG = {"campaigns": camps}
    assert sorted(C.campaigns()) == ["clips"], sorted(C.campaigns())      # a daily campaign has no source or rules: no clips are made for it
    C.CFG = real_cfg
print("1c submission rows ok")

# 2. the writer ----------------------------------------------------------------------------------------------------------------
import writer as W
real_active = SP.active
SP.active = lambda *a, **k: {}
b = {"id": "QD-500", "meta": {"title": "Free Steam games"}}
before = json.dumps(b)
assert W.sponsor_board(b) is None and json.dumps(b) == before             # dormant: the board is untouched
SP.active = lambda *a, **k: live
armed = {}
for i in range(1, 301):
    b = {"id": f"QD-{i:03d}", "meta": {"title": "Free Steam games", "summary": "Three games are free."}}
    armed[b["id"]] = W.sponsor_board(b)
    assert b["test"]["sponsor"] == armed[b["id"]]
share = sum(a != "none" for a in armed.values()) / len(armed)
assert 0.2 < share < 0.4 and set(armed.values()) <= {"none", "spring", "tags"}, share
assert W.sponsor_board({"id": "QD-501", "meta": {"title": "Singer dies at 70", "summary": ""}}) == "none"       # a sad story never carries one
part1 = W.sponsor_board({"id": "QD-502", "meta": {"title": "x"}}, {"id": "QD-502"})
part2 = W.sponsor_board({"id": "QD-503", "meta": {"title": "x"}}, {"id": "QD-502"})
assert part1 == part2                                                    # a series: every part follows its first
kept = {"id": "QD-504", "meta": {}, "test": {"length": "35 to 44 s"}}
W.sponsor_board(kept)
assert kept["test"]["length"] == "35 to 44 s" and "sponsor" in kept["test"], kept
def boom(*a, **k): raise RuntimeError("boom")
SP.active = boom
assert W.sponsor_board({"id": "QD-505"}) is None                         # a failure here never stops the writer
SP.active = real_active
assert "sponsor_board(b, series)" in inspect.getsource(W.main)
print("2 the writer's draw ok")

# 3. run_board.py --------------------------------------------------------------------------------------------------------------
import run_board as RB
SP.active = lambda *a, **k: live
snd = SCRATCH / "campaign.sound"; snd.write_bytes(b"x")
real_fetch, fetched = SP.fetch_sound, []
SP.fetch_sound = lambda c, d, sid, get=None: (fetched.append(sid), (snd, ""))[1]
st = {}
s = RB.sponsor_setup({"id": "QD-1", "test": {"sponsor": "spring"}}, "QD-1", st)
assert s["id"] == "spring" and s["sound"] == snd and s["c"]["card"].startswith("Spring"), s
assert st["sponsor"] == {"campaign": "spring", "applied": True, "sound": True, "hashtags": ["#SpringSound", "#springfest"]}, st
st = {}; fetched.clear()
s = RB.sponsor_setup({"test": {"sponsor": "tags"}}, "QD-2", st)                 # hashtags only: no sound link, nothing to fetch
assert s["sound"] is None and st["sponsor"]["applied"] is True and st["sponsor"]["sound"] is False and not fetched, (s, st)
SP.fetch_sound = lambda c, d, sid, get=None: (None, "the link answered 404")
st = {}
assert RB.sponsor_setup({"test": {"sponsor": "spring"}}, "QD-3", st) is None  # no sound, no campaign: no #ad, no paid promotion, no row
assert st["sponsor"]["applied"] is False and "sound not fetched" in st["sponsor"]["why"] and "404" in st["sponsor"]["why"], st
for sb in ({"test": {"sponsor": "none"}}, {"test": {}}, {}):
    st = {}
    assert RB.sponsor_setup(sb, "QD-4", st) is None and "sponsor" not in st, sb
SP.active = lambda *a, **k: {}
st = {}
assert RB.sponsor_setup({"test": {"sponsor": "spring"}}, "QD-5", st) is None
assert st["sponsor"]["applied"] is False and "no longer live" in st["sponsor"]["why"], st            # it ended after the board was written
SP.active, SP.fetch_sound = real_active, real_fetch

sb = {"meta": {"summary": "Three games are free.", "sources": [["Steam", "https://store.steampowered.com"]], "hashtags": ["#Gaming", "#Steam"]}}
plain = RB.description(sb, [], {"title": "Track", "artist": "Artist"})
assert "#ad" not in plain and "Paid promotion" not in plain, plain       # no campaign: the description is as it was
paid = RB.description(sb, [], SP.track(camps["spring"]), camps["spring"])
lines = paid.split("\n")
assert lines[0].startswith("#ad Paid promotion") and lines[1] == "" and lines[2] == "Three games are free.", lines[:4]
assert "Music: Spring Sound Challenge by Spring (supplied by the campaign)" in paid
assert lines[-1].startswith("#ad #SpringSound #springfest #Gaming #Steam") and lines[-1].endswith("#Shorts"), lines[-1]
assert not any(c in paid for c in DASHES)
loc = RB.localize({"translations": {"es": {"title": "Hola", "summary": "Resumen"}}}, paid, "#ad ")
assert loc["es"]["description"].startswith("#ad Resumen\n\n#ad Paid promotion"), loc
assert RB.localize({"translations": {"es": {"title": "Hola", "summary": "Resumen"}}}, "d")["es"]["description"] == "Resumen\n\nd"
assert RB.youtube_tags(SP.with_hashtags(sb["meta"], camps["spring"]))[:3] == ["ad", "SpringSound", "springfest"]
src = inspect.getsource(RB.main)
assert '"paid": True' in src and "sponsor_setup(sb, sid, status)" in src and 'sb["music"].update(file=' in src
print("3 run_board ok")

# 4. render3.py ----------------------------------------------------------------------------------------------------------------
try:
    import numpy as np
    from PIL import Image
    import render as R_, render3 as R3, looks as LK
except ImportError as e: R3 = None; print(f"(render3 needs more packages than this environment has: {e})")
if R3 and shutil.which("ffmpeg"):
    wav = SCRATCH / "tone.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(wav)], check=True)
    arr = R3.load_sound(wav, 0, 5.0)                                     # 2 seconds of sound looped to fill the Short
    assert arr.dtype == np.float32 and abs(len(arr) / R3.SR - 6.0) < 0.05 and float(np.abs(arr[-R3.SR:]).max()) > 0.1, len(arr)
    assert abs(len(R3.load_sound(wav, 1.5, 1.0)) / R3.SR - 2.0) < 0.05   # cut from 1.5 seconds in
    HERE = SCRATCH / "here"; (HERE / "media").mkdir(parents=True)
    Image.fromarray(np.full((1000, 1600, 3), 90, np.uint8)).save(HERE / "media" / "a.jpg", quality=90)
    R_.tts = lambda text, voice, speed: np.zeros(int(R_.SR * 0.33 * len(text.split())), np.float32)
    R3.face_focus = lambda p: None
    played = {}
    def fake_music(slug, start, dur, lib="music"):
        played["library"] = (slug, lib); return np.zeros(int(48000 * (dur + 1)), np.float32), [0.5], {"title": "Track", "artist": "Artist"}
    def fake_sound(path, start, dur):
        played["campaign"] = (str(path), start, round(dur, 1)); return np.zeros(int(48000 * (dur + 1)), np.float32)
    R3.load_music, R3.load_sound, R3.mix_audio3 = fake_music, fake_sound, (lambda *a, **k: None)
    class Fake:                                                          # no ffmpeg: the muxed file is just made
        @staticmethod
        def run(cmd, **kw):
            dest = _p.Path(str(cmd[-1])); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(b"x")
            return types.SimpleNamespace(returncode=0, stdout=b"")
    R3.subprocess = Fake
    async def fake_capture(html, data, duration, frames_cmd, poster_path, poster_t): pass
    R_.capture = fake_capture
    R3.HERE = HERE
    LK.DRIVERS = SCRATCH / "none" / "drivers.csv"
    cat = LK.catalogue(lab={})
    shot = lambda move: [{"src": "media/a.jpg", "move": move, "credit": "Photo: A, CC BY 4.0", "source": "https://commons.example/a"}]
    def run_main(name, music):
        sb = {"id": name, "category": "Gaming", "chipIcon": "gamepad-2", "accent": "#8B5CF6", "gap": 0.1, "tail": 0.6, "music": music,
              "beats": [{"say": "Hurry, these free Steam games are only here for a limited time.", "visual": {"type": "title", "lines": ["Free games", "Right now"]}, "shots": shot("in")},
                        {"say": "Which one will you grab first today? Tell us below, and follow along.", "visual": {"type": "none"}, "shots": shot("still")}]}
        look = LK.resolve({"style": "standard"}, cat)
        sb.update(look=look["ids"], look_render=look["render"], group=look["render"]["group"])
        p = SCRATCH / f"{name}.json"; p.write_text(json.dumps(sb)); out = SCRATCH / f"out-{name}"
        R3.FACES.clear(); sys.argv = ["render3.py", str(p), str(out)]
        with contextlib.redirect_stdout(io.StringIO()): R3.main()
        sys.argv = ["analytics.py", "--fast"]
        return [x["credit"] for x in json.loads((out / f"{name}.credits.json").read_text())]
    cr = run_main("TEST-SP1", {"slug": "ten", "gain_db": -15, "file": str(wav), "start": 0, "title": "Spring Sound Challenge", "artist": "Spring"})
    assert "campaign" in played and "library" not in played and played["campaign"][0] == str(wav), played
    assert "Music: Spring Sound Challenge by Spring (supplied by the campaign)" in cr, cr
    played.clear()
    cr = run_main("TEST-SP2", {"slug": "ten", "gain_db": -15})
    assert "library" in played and "campaign" not in played, played        # no campaign: the music library, as always
    assert "Music: Track by Artist (YouTube Audio Library)" in cr, cr
print("4 render3 ok")

# 5. captions, drivers and analytics -------------------------------------------------------------------------------------------
import social as SO
board = {"meta": {"title": "Free games", "summary": "Three are free.", "hashtags": ["#Gaming", "#Steam", "#Free", "#Deals", "#Pc", "#More"]}}
plain_st = {"title": "Free games"}
sp_st = {"title": "Free games", "sponsor": {"applied": True, "hashtags": ["#SpringSound", "#springfest"]}}
ig = SO.caption(sp_st, board, "instagram")
assert ig.startswith("#ad Free games") and ig.split("\n\n")[-1].split()[:2] == ["#SpringSound", "#springfest"], ig
assert len([w for w in ig.split() if w.startswith("#") and w != "#ad"]) == 5, ig                       # Instagram's 5 hashtags, the campaign's first
fb = SO.caption(sp_st, board, "facebook")
assert fb.startswith("#ad Free games") and "#SpringSound" in fb, fb
assert SO.caption(plain_st, board, "instagram") == SO.caption(plain_st, board, "instagram") and not SO.caption(plain_st, board, "instagram").startswith("#ad")
assert SO.caption({"title": "Free games", "sponsor": {"applied": False, "why": "x"}}, board, "tiktok") == SO.caption(plain_st, board, "tiktok")

import analytics as A, drivers as D
A.ROOT = SCRATCH / "an"; A.OUT = A.ROOT / "analytics"; A.CACHE = A.OUT / "cache"
(A.ROOT / "boards" / "done").mkdir(parents=True); (A.ROOT / "status").mkdir(); A.CACHE.mkdir(parents=True)
(A.ROOT / "boards" / "done" / "QD-700.json").write_text(json.dumps({"id": "QD-700", "kind": "news", "category": "Gaming", "beats": [{"say": "Hi"}],
                                                                    "test": {"sponsor": "spring"}, "meta": {"title": "t"}}))
(A.ROOT / "status" / "QD-700.json").write_text(json.dumps({"id": "QD-700", "video": "vid700"}))
assert A.our_shorts()["vid700"]["sponsor"] == "spring"
assert '"sponsor"' in inspect.getsource(A.main)                          # and a column of analytics/shorts.csv
assert "sponsor" in D.TESTED and "sponsor" in D.PIPELINE_ONLY and "sponsor" in D.NEVER_PAUSED and "sponsor" in dict(D.FEATURES)
print("5 captions and measuring ok")

# 6. the scout -----------------------------------------------------------------------------------------------------------------
import submit as S
page = ("Spring Sound Challenge\nUse this sound in your Short and add #SpringSound. No footage needed.\n"
        "YouTube Per 1K views $1.50 Min payout $15 Max payout $500\nTikTok Per 1K views $1.00 Min payout $10 Max payout $300")
ans = {"name": "Spring Sound Challenge", "mode": "sound", "subject": "Spring"}
cl = S.classify(page, ans, S.cr_terms(page))
assert cl["mode"] == "sound" and cl["daily"] is True and not cl["block"] and cl["window"] == 0, cl
assert cl["carry"]["hashtags"] == ["#SpringSound"] and cl["carry"]["ad"] is True, cl["carry"]
assert S.classify(page + "\nSubmit your link within 30 minutes of posting.", ans, S.cr_terms(page))["window"] == 30
named = S.classify("Brand Song\nUse the song \"Moonlight Drive\" in your Short. No footage needed.\nYouTube Per 1K views $1.00 Min payout $10 Max payout $100",
                   {"name": "Brand Song", "mode": "sound"}, {"YouTube": {"rate_per_1k": 1.0}})
assert named["daily"] and named["carry"]["sound"] == "Moonlight Drive", named
clips_page = "Streamer clips\nClip the best moments from the stream. Footage is in the Google Drive.\nYouTube Per 1K views $2.00 Min payout $20 Max payout $800"
c2 = S.classify(clips_page, {"name": "Streamer clips", "mode": "clips"}, S.cr_terms(clips_page))
assert c2["mode"] == "clips" and c2["daily"] is False
casino = "Casino Sound\nUse this sound and add #bigwin. No footage needed. Play at our casino.\nYouTube Per 1K views $3.00 Min payout $30 Max payout $900"
c3 = S.classify(casino, {"name": "Casino Sound", "mode": "sound"}, S.cr_terms(casino))
assert c3["mode"] == "sound" and c3["daily"] is False and "casino" in c3["block"], c3         # not family friendly: gambling
crypto = S.classify("Coin Beat\nUse this sound and add #coin. No footage needed.\nYouTube Per 1K views $3.00 Min payout $30 Max payout $900",
                    {"name": "Coin Beat", "subject": "Bitcoin exchange", "mode": "sound"}, {"YouTube": {"rate_per_1k": 3.0}})
assert not crypto["daily"] and "bitcoin" in crypto["block"], crypto
rules = "Brand Sound\nNo gambling, no crypto. Use this sound and add #BrandSound. No footage needed.\nYouTube Per 1K views $1.00 Min payout $10 Max payout $100"
assert S.classify(rules, {"name": "Brand Sound", "mode": "sound"}, S.cr_terms(rules))["daily"] is True      # a rule that bans them is not the campaign
dance = "Dance challenge\nUse this sound and dance to it on camera.\nYouTube Per 1K views $1.00 Min payout $10 Max payout $100"
assert S.classify(dance, {"name": "Dance", "mode": "sound"}, S.cr_terms(dance))["mode"] == "other"        # someone must appear on camera
tiktok = "TikTok only\nUse this sound.\nTikTok Per 1K views $1.00 Min payout $10 Max payout $100"
c4 = S.classify(tiktok, {"name": "TT", "mode": "sound"}, S.cr_terms(tiktok))
assert c4["mode"] == "sound" and c4["daily"] is False and "YouTube" in c4["block"], c4

cards = {"campaigns": [
    {"name": "Summer Beat", "card": "Summer Beat", "text": "Use the official sound Summer Beat in your Short and add the hashtag #SummerBeat. No footage needed.",
     "rate_per_1k": 1.2, "min_views": 5000, "max_payout": 300, "platforms": ["YouTube", "TikTok"], "youtube_allowed": True, "family_friendly": True,
     "mode": "sound", "sound": "Summer Beat", "must_carry": ["#SummerBeat"], "on_camera": False, "ends": "2026-11-15", "status": "open"},
    {"name": "Known Card", "card": "Known Card", "text": "Use this sound", "mode": "sound", "platforms": ["YouTube"], "status": "open"},
    {"name": "Full One", "card": "Full One", "text": "Use this sound", "mode": "sound", "platforms": ["YouTube"], "status": "full"},
    {"name": "TikTok Only", "card": "TikTok Only", "text": "Use this sound and add #x1y", "mode": "sound", "platforms": ["TikTok"], "status": "open"},
    {"name": "Stream Clips", "card": "Stream Clips", "text": "Clip the stream. Footage provided.", "mode": "clips", "platforms": ["YouTube"], "status": "open"},
    {"name": "Casino Beat", "card": "Casino Beat", "text": "Use this sound at our casino. No footage needed.", "mode": "sound", "platforms": ["YouTube"], "status": "open"},
    {"name": "Dance Beat", "card": "Dance Beat", "text": "Use this sound and dance on camera.", "mode": "sound", "platforms": ["YouTube"], "on_camera": True, "status": "open"}]}
asked = []
vy = S.vyro_daily("page text", ask=lambda prompt: (asked.append(prompt), cards)[1], known={"Known Card"})
assert [r["card"] for r in vy] == ["Summer Beat"] and len(asked) == 1, [r["card"] for r in vy]
sv = vy[0]
assert sv["platform"] == "Vyro" and sv["daily"] is True and sv["carry"]["hashtags"] == ["#SummerBeat"] and sv["carry"]["sound"] == "Summer Beat", sv
assert S.vyro_daily("", ask=lambda p: cards) == [] and S.vyro_daily("x", ask=lambda p: 1 / 0) == []        # nothing to read, or the model failed

rows = [dict(ans, url="https://contentrewards.com/c/campaigns/aaa", id="aaa", platform="Content Rewards", rate_per_1k=1.5, min_views=10000, max_payout=500, fits=False,
             heat=0.2, heat_why=[], mode=cl["mode"], daily=True, carry=cl["carry"], window=0),
        dict(name="Streamer clips", url="https://contentrewards.com/c/campaigns/bbb", id="bbb", platform="Content Rewards", rate_per_1k=2.0, min_views=10000,
             budget_remaining=900, fits=True, heat=0.5, heat_why=[], footage="google drive", why="footage supplied", mode="clips", daily=False, carry={}, window=0),
        dict(name="Casino Sound", url="https://contentrewards.com/c/campaigns/ccc", id="ccc", platform="Content Rewards", rate_per_1k=3.0, fits=True, heat=0.1,
             heat_why=[], mode="sound", daily=False, carry={}, window=0)]
W_ = SCRATCH / "scout"; (W_ / "clips").mkdir(parents=True); (W_ / "status").mkdir()
daily = S.write_scout(rows, vy, root=W_)
assert [r["name"] for r in daily] == ["Spring Sound Challenge", "Summer Beat"], [r["name"] for r in daily]       # best rate first
md = (W_ / "status" / "scout.md").read_text()
assert "## For Quickplay Daily's own views" in md and md.index("Streamer clips") < md.index("## For Quickplay Daily's own views"), md
section = md.split("## For Quickplay Daily's own views")[1]
assert "Spring Sound Challenge" in section and "Summer Beat" in section and "$1.5/1k" in section and "#SpringSound" in section and "; #ad" in section
assert "Streamer clips" not in section and "Casino Sound" not in section and "docs/CHROME_OCCASIONAL.md" in section
table = [ln for ln in md.split("## For Quickplay Daily's own views")[0].splitlines() if ln.startswith("|")]
assert any(ln.startswith("| sound | [Spring Sound Challenge]") for ln in table) and any(ln.startswith("| yes | [Streamer clips]") for ln in table), table
assert any(ln.startswith("| no | [Casino Sound]") for ln in table), table          # a blocked sound campaign is not a clips one
entries = [json.loads(ln.split("`")[1]) for ln in section.splitlines() if ln.startswith("- ") and "`" in ln]
assert len(entries) == 2 and all(e["daily"] is True and e["active"] is True and "source" not in e and "rules" not in e for e in entries), entries
assert not any(c in md for c in DASHES)
sj = json.loads((W_ / "clips" / "scout.json").read_text())
assert [d["name"] for d in sj["daily"]] == ["Spring Sound Challenge", "Summer Beat"] and len(sj["campaigns"]) == 3 and sj["daily"][0]["carry"]["hashtags"] == ["#SpringSound"], sj["daily"]
S.write_scout([], [], root=W_)
assert "None found in this run." in (W_ / "status" / "scout.md").read_text()
assert '"mode"' in S.JUDGE and "must_carry" in S.JUDGE and "mode" in S.VYRO_JUDGE
print("6 the scout ok")

# 7. the Mac -------------------------------------------------------------------------------------------------------------------
import mac_rows as M
MR = SCRATCH / "mac"
for d in ("clips", "status", "docs"): (MR / d).mkdir(parents=True)
M.ROOT, M.SUBMIT = MR, MR / "clips" / "submit.csv"
mcfg = {"min_active": 1, "campaigns": {"c1": {"platform": "Vyro", "card": "Card One", "active": True, "source": {"kind": "gdrive"}, "ends": "2027-01-01"}}}
def put(cfg): (MR / "clips" / "campaigns.json").write_text(json.dumps(cfg))
put(mcfg)
wed = dt.datetime(2026, 10, 28, 19, 7, tzinfo=M.UK)
assert "NOTHING TO DO" in M.show(wed, fetch_issues=False)                # no scout file, nothing to join
(MR / "clips" / "scout.json").write_text(json.dumps({"daily": [
    {"id": "aaa", "name": "Spring Sound Challenge", "card": "", "platform": "Content Rewards", "url": "https://contentrewards.com/c/campaigns/aaa", "rate_per_1k": 1.5},
    {"id": "summer-beat", "name": "Summer Beat", "card": "Summer Beat", "platform": "Vyro", "url": "https://app.vyro.com/campaigns", "rate_per_1k": 1.2}]}))
out = M.show(wed, fetch_issues=False)
assert "Daily sound campaigns: 0 live" in out and "Spring Sound Challenge ($1.5/1k, Content Rewards)" in out and "Summer Beat ($1.2/1k, Vyro)" in out, out
assert "NOTHING TO DO" not in out and "For Quickplay Daily's own views" in out
mcfg["campaigns"]["d1"] = {"daily": True, "active": True, "name": "Spring Sound Challenge", "url": "https://contentrewards.com/c/campaigns/aaa", "ends": "2026-11-30", "hashtags": ["#x1y"]}
put(mcfg)
out = M.show(wed, fetch_issues=False)
assert "Daily sound campaigns: 1 live" in out and "Summer Beat" in out and "Spring Sound Challenge (" not in out, out       # the joined one is not listed again
mcfg["daily_min_active"] = 1
put(mcfg)
assert "NOTHING TO DO" in M.show(wed, fetch_issues=False)               # enough are live
mcfg["campaigns"]["d1"]["ends"] = "2026-10-20"; mcfg["daily_min_active"] = 2
put(mcfg)
out = M.show(wed, fetch_issues=False)
assert "Daily sound campaigns: 0 live" in out and "Summer Beat" in out and "Spring Sound Challenge (" not in out, out         # an ended one is not live, not listed again
# a Vyro row of the Daily channel names the Daily account
mcfg["campaigns"]["d2"] = {"daily": True, "active": True, "name": "Summer Beat", "card": "Summer Beat", "platform": "Vyro", "url": "https://app.vyro.com/campaigns",
                           "ends": "2026-11-30", "hashtags": ["#SummerBeat"]}
put(mcfg)
with M.SUBMIT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=SP.SUBMIT_FIELDS); w.writeheader()
    w.writerow({"clip": "QD-901", "campaign": "d2", "campaign_url": "https://app.vyro.com/campaigns", "platform": "youtube", "video": "https://youtube.com/shorts/vidA",
                "public_at_uk": "2026-10-28 08:00", "title": "T", "hashtags": "#SummerBeat", "submitted": "", "channel": "daily"})
out = M.show(wed, fetch_issues=False)
assert "1. QD-901 | Quickplay Daily (@quickplaydaily) | card: Summer Beat | https://youtube.com/shorts/vidA" in out, out
assert M.mark("QD-901", "youtube", "now", now=wed) == 1                 # the Mac marks it as it does a clips row
out = M.show(wed, fetch_issues=False)
assert "QD-901" not in out and "NOTHING TO DO" in out, out
print("7 the Mac's list ok")

# 8. upload.py -----------------------------------------------------------------------------------------------------------------
Y = types.ModuleType("youtube")                                          # the Google client is not needed: the YouTube helpers are stubbed
class LimitReached(Exception): pass
CALLS = []
def upload(yt, path, title, *a, **k):
    CALLS.append((title, k)); return f"vid{len(CALLS)}"
Y.LimitReached, Y.upload, Y.available, Y.client = LimitReached, upload, (lambda: True), (lambda: object())
Y.recent_videos = lambda yt, limit=100: []
Y.video_status = lambda yt, vid: {"privacy": "private", "publish_at": "2026-10-25T07:30:00Z"}
sys.modules["youtube"] = Y
import upload as U
UD = SCRATCH / "up"
for sid, extra in (("QD-801", {"paid": True, "sponsor": "spring"}), ("QD-802", {})):
    d = UD / sid; d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"id": sid, "state": "rendered", "mode": "schedule"}))
    (d / "upload.json").write_text(json.dumps({"title": sid, "description": "", "tags": [], "category": "Gaming", "mode": "schedule",
                                                "slot": "2026-10-25T07:30:00Z", **extra}))
    (d / "video.mp4").write_bytes(b"x")
U.main(str(UD))
assert {t: k.get("paid") for t, k in CALLS} == {"QD-801": True, "QD-802": False}, CALLS       # paid promotion only for the Short that carries one
assert 'paid=bool(u.get("paid"))' in open("pipeline/publish.py").read()      # and for one published after approval
print("8 paid promotion ok")
print("sponsor ok")
