"""Offline tests of the style test (24 October; Charlie: "fast changing images with minimal text", nothing covering the
pictures; templates/looks.json "style": minimal against standard, 2 Shorts in 3 to 1):
1. looks.py draws the style by its 2:1 split (evenly for an exploration Short), fixes the low captions with minimal and
   never gives them to standard, hands the whole test to the proof rule (drivers.csv) once both arms have 70 Shorts, and
   renders a look from before the test (no style) as standard, exactly as it always did;
2. the style is recorded: in the look (status/<id>.json), in analytics' look_style column and options table, and scored by
   drivers.py (pipeline only: never put to the writer, never paused); the look lab leaves the style-only captions alone;
3. render3.main() hands the renderer the style: minimal turns text cards into photos, tags a name once, uses the low
   captions' 3-word groups and cuts to a new picture every 1.2 to 1.8 seconds; standard is unchanged (cards, a label on
   every picture, the board's own timing);
4. the pace: pace_cuts keeps every picture inside 1.2 to 1.8 seconds, split_segments uses the picture's own extra photos
   first, then the same photo with a new crop and move, and leaves video alone;
5. fetch_media.extras (stubbed network): more photos of the same subject, each credited, never a duplicate, never more than
   the cap or the description has room for, and never an error."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, copy, csv, datetime as dt, io, json, os, statistics, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import numpy as np
from PIL import Image

import looks as LK
(SCRATCH / "none").mkdir()
LK.DRIVERS = SCRATCH / "none" / "drivers.csv"            # no verdicts yet: the split is as written
cat = LK.catalogue(lab={})                               # templates/looks.json alone, not the lab's moving options

# 1. the split ------------------------------------------------------------------------------------------------------
assert cat["dimensions"]["style"]["assign"] == {"minimal": 2, "standard": 1}
assert set(cat["dimensions"]["style"]["options"]) == {"minimal", "standard"}
looks = {i: LK.choose(f"QD-{i}", [], {}, cat) for i in range(3000)}
n_min = sum(l["style"] == "minimal" for l in looks.values())
assert 1900 <= n_min <= 2100, n_min                      # 2 in 3 of 3000, drawn by the Short's id
assert all(LK.choose(f"QD-{i}", [], {}, cat) == looks[i] for i in range(0, 3000, 97))     # the same Short, the same look
assert all((l["captions"] == "low") == (l["style"] == "minimal") for l in looks.values())   # low captions come with minimal only
assert "low" not in LK.free(cat, "captions") and "low" in LK.active(cat, "captions") and LK.default(cat)["style"] == "standard"
assert all(l["captions"] in LK.free(cat, "captions") for l in looks.values() if l["style"] == "standard")
even = [LK.choose(f"QD-{i}", [], {}, cat, explore=True)["style"] for i in range(2000)]
assert 900 <= even.count("minimal") <= 1100, even.count("minimal")                      # an exploration Short: evenly
# never the same look twice running still works, and leaves the style (a fixed test) alone
again = LK.choose("QD-7", [looks[7]], {}, cat)
assert again["style"] == looks[7]["style"]
print("1a the 2:1 split ok", n_min)

rows = lambda a, b, na=80, nb=75: [{"feature": "look_style", "value": "minimal", "n": str(na), "verdict": a},
                                    {"feature": "look_style", "value": "standard", "n": str(nb), "verdict": b},
                                    {"feature": "look_captions", "value": "low", "n": "99", "verdict": "push"}]
w = lambda r: {k: round(v, 3) for k, v in LK.assign_weights(cat, "style", r).items()}
assert w([]) == {"minimal": 2.0, "standard": 1.0}
assert w(rows("push", "about typical")) == {"minimal": 0.9, "standard": 0.1}             # proven: the winner takes 9 in 10
assert w(rows("early sign", "cut back")) == {"minimal": 0.9, "standard": 0.1}            # the other arm proven worse
assert w(rows("about typical", "push")) == {"minimal": 0.1, "standard": 0.9}
assert w(rows("cut back", "about typical")) == {"minimal": 0.1, "standard": 0.9}
assert w(rows("push", "about typical", nb=60)) == {"minimal": 2.0, "standard": 1.0}      # an arm under 70 Shorts: not decided
assert w(rows("early sign", "early sign")) == {"minimal": 2.0, "standard": 1.0}
assert w(rows("push", "push")) == {"minimal": 2.0, "standard": 1.0}
decided = SCRATCH / "decided.csv"
with decided.open("w", newline="") as f:
    cw = csv.DictWriter(f, fieldnames=["feature", "value", "n", "verdict"]); cw.writeheader(); cw.writerows(rows("push", "cut back"))
LK.DRIVERS = decided
after = [LK.choose(f"QD-{i}", [], {}, cat)["style"] for i in range(2000)]
assert 1700 <= after.count("minimal") <= 1900, after.count("minimal")                    # about 9 in 10, and standard stays measured
assert after.count("standard") >= 100
LK.DRIVERS = SCRATCH / "none" / "drivers.csv"
print("1b the proof rule hands over ok")

old = LK.resolve({"captions": "clean", "voice": "george", "energy": "steady", "grade": "natural", "opening": "image_first"}, cat)
assert old["ids"]["style"] == "standard" and old["ids"]["captions"] == "clean"           # a look from before the test
assert (old["render"]["labels"], old["render"]["chip"], old["render"]["graphics"], old["render"]["pace"], old["render"]["shade"]) \
    == ("full", "full", "cards", "board", "full")
assert LK.resolve({"style": "wobbly"}, cat)["ids"]["style"] == "standard"                 # an unknown style is the control
mini = LK.resolve({"style": "minimal", "captions": "clean"}, cat)                         # a style brings its own captions
assert mini["ids"]["captions"] == "low" and mini["render"]["captions"] == "low" and mini["render"]["group"] == 3
assert (mini["render"]["labels"], mini["render"]["chip"], mini["render"]["graphics"], mini["render"]["pace"], mini["render"]["shade"]) \
    == ("brief", "brief", "photo", "fast", "light")
retired = copy.deepcopy(cat); retired["dimensions"]["captions"]["options"]["low"]["retired"] = "test"
assert LK.resolve({"style": "minimal"}, retired)["ids"]["captions"] != "low"                  # retired captions are not forced
assert LK.choose("QD-2", [], {}, retired)["captions"] != "low"
assert LK.describe({"style": "minimal"}, cat).startswith("low captions") and LK.describe({}, cat).endswith("standard")
print("1c resolve ok")

# 2. recorded and scored ---------------------------------------------------------------------------------------------
import analytics as A, drivers as DRV, validate
A.ROOT = SCRATCH / "an"; (A.ROOT / "status").mkdir(parents=True)
day = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
arows = []
for i in range(8):
    sid = f"QD-{700 + i}"
    style = "minimal" if i % 2 == 0 else "standard"
    (A.ROOT / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "look": LK.resolve({"style": style}, cat)["ids"]}))
    arows.append({"short": sid, "posted": (day + dt.timedelta(minutes=i)).isoformat(timespec="minutes"), "yt_views": 100 + i,
                  "yt_engaged_pct": 30 + (8 if style == "minimal" else 0), "yt_avg_viewed_pct": 50, "views_per_hour": 4})
arows.append({"short": "QD-799", "posted": day.isoformat(timespec="minutes"), "yt_views": 90})      # no status file: before the test
orig_catalogue = LK.catalogue
LK.catalogue = lambda lab=None: orig_catalogue(lab={})
out = A.look_scores(arows)
LK.catalogue = orig_catalogue
assert [r["look_style"] for r in arows] == ["minimal", "standard"] * 4 + [""], [r["look_style"] for r in arows]
assert [r["look_captions"] for r in arows[:2]] == ["low", arows[1]["look_captions"]] and arows[1]["look_captions"] != "low"
assert out["dimensions"]["style"]["minimal"]["n"] == 4 and out["dimensions"]["style"]["standard"]["n"] == 4, out["dimensions"]["style"]
assert out["dimensions"]["style"]["minimal"]["score"] > out["dimensions"]["style"]["standard"]["score"]
cols = [k for k in arows[0] if not k.startswith("_") and k != "rel"]                        # the columns analytics.py writes to shorts.csv
assert "look_style" in cols and "look_captions" in cols
f = DRV.features(arows[0])
assert f["look_style"] == "minimal" and DRV.features(arows[-1])["look_style"] == ""
assert ("look_style", "Style (text and pace)") in DRV.FEATURES
assert "look_style" in DRV.PIPELINE_ONLY and "look_style" in DRV.NEVER_PAUSED              # looks.py decides it; nothing to pause
scored = [dict(r, rel=(2.0 if r["look_style"] == "minimal" else 1.0) * (1 + 0.01 * i), posted=(day - dt.timedelta(days=i % 4)).isoformat(),
               category="Music", format="one_detail", hook="A hook here", seconds="30", slot_uk="09:00", title="t") for i, r in enumerate(arows[:8] * 4)]
table, _ = DRV.analyse(scored, {}, "2026-10-24")
vs = {t["value"]: t for t in table if t["feature"] == "look_style"}
assert set(vs) == {"minimal", "standard"} and vs["minimal"]["lift"] > vs["standard"]["lift"], vs
assert all(t["verdict"] not in ("pause", "stop", "retest") for t in vs.values())
assert not any("style" in line.lower() for line in DRV.recipe(table, scored))                # never put to the writer
b = {"look": {"style": "minimal"}}
assert not [e for e in validate.check(b)[0] if e.startswith("look.")], validate.check(b)[0]
assert any(e.startswith("look.style") for e in validate.check({"look": {"style": "wobbly"}})[0])
import lab as LAB                                  # the look lab never judges, prunes or builds on the style-only captions
real_lab, real_stats = LK.LAB, LK.STATS
for score in (1.5, 0.5):                           # "low" the best scorer, then the worst: either way it is left to the style test
    LK.LAB, LK.STATS = SCRATCH / f"lab{score}.json", SCRATCH / f"looks{score}.json"
    LK.STATS.write_text(json.dumps({"dimensions": {"captions": {"clean": {"n": 40, "score": 1.1}, "minimal": {"n": 40, "score": 1.05},
                                                                  "low": {"n": 60, "score": score}}}}))
    with contextlib.redirect_stdout(io.StringIO()): LAB.main(force=True)
    lab = json.loads(LK.LAB.read_text()); caps = lab["options"].get("captions") or {}
    assert "low" not in (lab["retired"].get("captions") or {}) and "low" not in caps, lab
    assert any(k.startswith("lab-captions-") for k in caps) and all(o.get("parent") != "low" for o in caps.values()), lab    # it worked on the others
LK.LAB, LK.STATS = real_lab, real_stats
print("2 recorded and scored ok")

# 3. what render3.main() hands the renderer ----------------------------------------------------------------------------
import render as R, render3 as R3
HERE = SCRATCH / "here"; (HERE / "media").mkdir(parents=True)
def photo(name, size=(1600, 1000), seed=0, flip=False):
    x = np.linspace(0, 255, size[0], dtype=np.float32)[None, :]; y = np.linspace(0, 255, size[1], dtype=np.float32)[:, None]
    arr = np.stack([(x * (1 - seed % 2) + y * (seed % 2)) % 256, (x + y * (seed % 3)) % 256, ((x * (seed + 1) + y) / 2) % 256], axis=2)
    Image.fromarray(np.broadcast_to(arr, (size[1], size[0], 3)).astype(np.uint8)).save(HERE / "media" / name, quality=90)
for i, n in enumerate(("a", "b", "c", "a2", "a3")): photo(f"{n}.jpg", seed=i + 1)
R.tts = lambda text, voice, speed: np.zeros(int(R.SR * 0.33 * len(text.split())), np.float32)      # a silent voice, 3 words a second
R3.face_focus = lambda p: None
R3.load_music = lambda slug, start, dur, lib="music": (np.zeros(int(48000 * (dur + 1)), np.float32), [round(0.5 * k, 2) for k in range(1, 80)],
                                                         {"title": "Track", "artist": "Artist"})
R3.mix_audio3 = lambda *a, **k: None
class Fake:                                                                                 # no ffmpeg: the muxed file is just made
    @staticmethod
    def run(cmd, **kw):
        pathlib_dest = _p.Path(str(cmd[-1])); pathlib_dest.parent.mkdir(parents=True, exist_ok=True); pathlib_dest.write_bytes(b"x")
        return types.SimpleNamespace(returncode=0, stdout=b"")
R3.subprocess = Fake
captured = {}
async def fake_capture(html, data, duration, frames_cmd, poster_path, poster_t): captured["data"] = copy.deepcopy(data)
R.capture = fake_capture
R3.HERE = HERE

CREDIT = "Photo: A. Photographer, CC BY 4.0, via Wikimedia Commons"
def board(extra_photos=False):
    sh = lambda src, move, **kw: [dict({"src": f"media/{src}.jpg", "move": move, "credit": CREDIT, "source": "https://commons.example/" + src}, **kw)]
    b = {"id": "TEST-LS1", "category": "Gaming", "chipIcon": "gamepad-2", "accent": "#8B5CF6", "gap": 0.1, "tail": 0.6, "music": {"slug": "ten"},
         "beats": [
             {"say": "Hurry, these free Steam games are only here for a limited time.", "visual": {"type": "title", "lines": ["Free games", "Right now"]},
              "shots": sh("a", "in", label={"t": "Steam", "s": "platform"})},
             {"say": "First up, the big one is free to keep until the twenty first of September.",
              "visual": {"type": "cards", "items": [{"icon": "rocket", "t": "Space Menace", "s": "Free to keep"}]},
              "shots": sh("b", "right", label={"t": "Steam", "s": "platform"})},
             {"say": "Then another game is free to play until the end of the month for everyone.", "visual": {"type": "stat", "value": "88%", "label": "score"},
              "shots": sh("c", "left", label={"t": "Deck", "s": "handheld"})},
             {"say": "Which one will you grab first today? Tell us below, and follow along.", "visual": {"type": "none"}, "shots": sh("a", "still")},
             {"say": "A last line with a card and no picture of its own at all here.", "visual": {"type": "date", "month": "September", "day": "21"}},
         ]}
    if extra_photos:
        b["beats"][0]["shots"] += [{"src": "media/a2.jpg", "extra": True, "of": "media/a.jpg", "credit": "Photo: B, CC BY 4.0", "source": "https://commons.example/a2"},
                                   {"src": "media/a3.jpg", "extra": True, "of": "media/a.jpg", "credit": "Photo: C, CC BY 4.0", "source": "https://commons.example/a3"}]
    return b

def run_main(style, extra_photos=False):
    sb = board(extra_photos)
    look = LK.resolve({"style": style}, cat)
    sb.update(look=look["ids"], look_render=look["render"], group=look["render"]["group"])
    sbp = SCRATCH / f"{style}-{extra_photos}.json"; sbp.write_text(json.dumps(sb))
    out = SCRATCH / f"out-{style}-{extra_photos}"
    R3.FACES.clear(); sys.argv = ["render3.py", str(sbp), str(out)]
    with contextlib.redirect_stdout(io.StringIO()): R3.main()
    return captured["data"], json.loads((out / "TEST-LS1.credits.json").read_text())

strip = lambda ms: [{k: v for k, v in it.items() if k != "fill"} for it in ms]       # `fill` holds the work folder, which differs per run
std, std_credits = run_main("standard")
sl = std["look"]
assert (sl["style"], sl["labels"], sl["chip"], sl["graphics"], sl["pace"], sl["shade"]) == ("standard", "full", "full", "cards", "board", "full"), sl
assert sl["captions"] != "low" and max(len(g["words"]) for g in std["groups"]) == sl["group"] == 4       # the captions dimension's own
assert [b["visual"]["type"] for b in std["beats"]] == ["title", "cards", "stat", "none", "date"]          # the cards stay
assert len(std["media"]) == 4 and not any(it.get("brief") for it in std["media"])                        # the board's own 4 pictures (the last beat has none)
assert [bool(it.get("label")) for it in std["media"]] == [True, True, True, False]
assert all(it["labelTop"] == 1020 for it in std["media"] if it.get("label"))                            # a label on every picture that has one
assert statistics.median(it["t1"] - it["t0"] for it in std["media"]) > 4.0                               # held as the board times them
assert all(it["dim"] >= 0.3 for it in std["media"][:3]) and std["media"][3]["dim"] <= 0.3                # a card dims its picture a lot

mini, mini_credits = run_main("minimal")
lk = mini["look"]
assert (lk["style"], lk["captions"], lk["group"], lk["labels"], lk["chip"], lk["graphics"], lk["pace"], lk["shade"]) \
    == ("minimal", "low", 3, "brief", "brief", "photo", "fast", "light"), lk
assert [b["visual"]["type"] for b in mini["beats"]] == ["none"] * 5                                      # every card gave way to a photo
assert [b["visual"].get("was") for b in mini["beats"]] == ["title", "cards", "stat", None, "date"]
assert max(len(g["words"]) for g in mini["groups"]) == 3                                                 # 3 words at a time, never 4
holds = [round(it["t1"] - it["t0"], 2) for it in mini["media"]]
assert len(mini["media"]) > 2.5 * len(std["media"]) and max(holds) <= 1.8 and min(holds) >= 1.19, holds   # a new picture every 1.2 to 1.8 s
assert all(abs(a["t1"] - b["t0"]) < 0.002 for a, b in zip(mini["media"], mini["media"][1:]))              # no gaps between pictures
assert mini["media"][0]["t0"] == 0.0 and abs(mini["media"][-1]["t1"] - mini["duration"]) < 0.002      # the last beat has a picture too
tags = [it for it in mini["media"] if it.get("brief")]
assert [t["label"]["t"] for t in tags] == ["Steam", "Deck"] and not any("labelTop" in it for it in mini["media"])   # a name once, not twice
assert all(it["dim"] <= 0.18 for it in mini["media"])                                                    # a light shade
looks_of = [(it["s0"], it["s1"], it["cx0"], it["cx1"], it["cy0"], it["cy1"]) for it in mini["media"]]
assert all(a != b for a, b in zip(looks_of, looks_of[1:]))                                               # a new crop or move at every cut
assert [it["src"] for it in mini["media"][:3]] == ["a", "a", "a"]                                        # no extra photos: the same one, cropped anew
beat5 = [it for it in mini["media"] if it["t0"] >= mini["beats"][4]["start"]]
assert len(beat5) >= 3 and all(it["src"] == "a" for it in beat5)                                         # the date card with no picture borrowed one
R3.LOOK = LK.resolve({"style": "minimal"}, cat)["render"]                                                 # a card stays a card with no picture in the Short
nopic = {"beats": [{"visual": {"type": "stat"}}]}; tl = [{"visual": {"type": "stat"}}]
assert R3.minimal_photos(nopic, tl) == {} and tl[0]["visual"]["type"] == "stat"

# photos of the same subject come in under the fast pace, and only there
mini_x, cr_x = run_main("minimal", extra_photos=True)
assert [it["src"] for it in mini_x["media"][:3]] == ["a", "a2", "a3"]                                    # the beat's own extras first
assert [it["src"] for it in mini_x["media"][3:]] == [it["src"] for it in mini["media"][3:]]               # the rest as before
assert [c["credit"] for c in cr_x[:3]] == [std_credits[0]["credit"], "Photo: B, CC BY 4.0", "Photo: C, CC BY 4.0"]    # each is credited
assert not any(c["credit"] in ("Photo: B, CC BY 4.0", "Photo: C, CC BY 4.0") for c in std_credits + mini_credits)
std_x, cr_sx = run_main("standard", extra_photos=True)
assert strip(std_x["media"]) == strip(std["media"]) and cr_sx == std_credits                             # the standard look never sees an extra
print("3 the renderer's data ok", len(std["media"]), "->", len(mini["media"]), "pictures")

# 4. the pace --------------------------------------------------------------------------------------------------------
for span in [x / 20 for x in range(48, 600)]:                                                   # 2.4 s to 30 s
    for beats in ([], [0.5 * k for k in range(1, 70)], [0.37 * k + 0.05 for k in range(1, 90)]):
        cs = R3.pace_cuts(0.0, span, beats)
        ps = [b - a for a, b in zip(cs, cs[1:])]
        assert cs[0] == 0.0 and cs[-1] == span and all(1.2 - 1e-6 <= p <= 1.8 + 1e-6 for p in ps), (span, ps)
assert R3.pace_cuts(3.0, 4.8, []) == [3.0, 4.8] and R3.pace_cuts(3.0, 5.0, []) == [3.0, 5.0]    # up to 2.0 s stays one picture
two = R3.pace_cuts(0.0, 2.3, [])
assert len(two) == 3 and all(0.9 <= b - a <= 1.2 for a, b in zip(two, two[1:]))                  # no whole count fits 1.8 to 2.4 s
snapped = R3.pace_cuts(0.0, 4.5, [1.58, 3.02])                                                  # ideal cuts at 1.5 and 3.0: onto the beat
assert snapped[1:3] == [1.58, 3.02], snapped
assert R3.pace_cuts(0.0, 4.5, [1.9, 3.5]) == [0.0, 1.5, 3.0, 4.5]                                # a beat too far away is ignored
assert R3.pace_cuts(0.0, 3.0, [1.7]) == [0.0, 1.5, 3.0]                                          # a beat 0.2 s off the even cut is too far to move to
assert R3.pace_cuts(0.0, 3.0, [1.65]) == [0.0, 1.65, 3.0]                                        # 0.15 s off: the cut lands on the beat (1.65 and 1.35)
mv = R3.MOVES
assert [R3.next_move(m) for m in mv] == list(mv[1:]) + [mv[0]] and R3.next_move("still") == mv[0]
shot = {"src": "media/a.jpg", "move": "in", "label": {"t": "Steam"}, "at": 2, "w": 2.0, "tin": "whip", "credit": CREDIT}
pool = [{"src": "media/a2.jpg", "extra": True, "of": "media/a.jpg"}, {"src": "media/a3.jpg", "extra": True, "of": "media/a.jpg"},
        {"src": "media/c.jpg", "extra": True, "of": "media/c.jpg"}]
segs = R3.split_segments([(shot, 0.0, 4.5)], pool, [])
assert [s["src"] for s, _, _ in segs] == ["media/a.jpg", "media/a2.jpg", "media/a3.jpg"], segs      # its own extras first, in order
assert [round(b - a, 2) for _, a, b in segs] == [1.5, 1.5, 1.5] and all(s["amp"] == 0.6 for s, _, _ in segs)
assert segs[0][0]["tin"] == "whip" and all(s["tin"] == "cut" for s, _, _ in segs[1:]) and "label" in segs[0][0]
assert all(s["move"] != p["move"] for (s, _, _), (p, _, _) in zip(segs[1:], segs))              # a different move each cut
assert pool[0]["of"] == "media/a.jpg" and "tin" not in pool[0]                                  # the board's own shots are copied, not changed
more = R3.split_segments([(shot, 0.0, 7.5)], pool[:1], [])                                       # 5 pictures, one extra: then the same photo again
assert [s["src"] for s, _, _ in more] == ["media/a.jpg", "media/a2.jpg"] + ["media/a.jpg"] * 3
crops = [s.get("crop") for s, _, _ in more]
assert crops[2:] == [1.26, 1.13, 1.0] and all("label" not in s and "at" not in s and "w" not in s and "extra" not in s for s, _, _ in more[2:])
moves = [s["move"] for s, _, _ in more]
assert all(a != b for a, b in zip(moves, moves[1:])) and "still" not in moves[1:], moves
vid = {"src": "media/clip.mp4", "start": 3}
assert R3.split_segments([(vid, 0.0, 6.0)], [], []) == [(vid, 0.0, 6.0)]                         # video keeps its own motion
short = R3.split_segments([(shot, 0.0, 1.7)], pool, [])
assert short == [(shot, 0.0, 1.7)]
print("4 the pace ok")

# 5. more photos of the same subject (stubbed network) ----------------------------------------------------------------------
import fetch_media as FM
real_cands, real_file, real_get = FM.commons_candidates, FM.commons_file, FM._get
FM.HERE = SCRATCH / "fm"; (FM.HERE / "media").mkdir(parents=True)
def stub_photo(path, kind):                          # five different pictures; two kinds are the same picture (a copy of the first)
    w, h = 800, 500
    x = np.linspace(0, 255, w, dtype=np.float32)[None, :]; y = np.linspace(0, 255, h, dtype=np.float32)[:, None]
    arr = {"h": np.broadcast_to(x, (h, w)), "v": np.broadcast_to(y, (h, w)), "d": (x + y) / 2,
           "r": np.sqrt((x - 400) ** 2 + (y - 250) ** 2) / 4, "x": np.abs(x - y)}[kind]
    Image.fromarray(np.broadcast_to(arr, (h, w)).astype(np.uint8)).convert("RGB").save(path, quality=92)
KIND = {"File:Steam_0.jpg": "h", "File:Steam_1.jpg": "h", "File:Steam_2.jpg": "v", "File:Steam_3.jpg": "d", "File:Steam_4.jpg": "r", "File:Steam_5.jpg": "x"}
calls = {"down": []}
FM.commons_candidates = lambda words: [] if words == "nothing here" else [{"title": t} for t in KIND]
FM.commons_file = lambda title: (f"https://upload.example/{title}", f"Photo: {title}, CC BY 4.0, via Wikimedia Commons", "https://commons.example/" + title)
broken = set()
def fake_download(url, d, stem):
    title = url.rsplit("/", 1)[1]; calls["down"].append(title)
    if title in broken: raise RuntimeError("download refused")
    p = d / f"{stem}.jpg"; stub_photo(p, KIND[title]); return p
FM.download = fake_download
def fboard():
    primary = FM.HERE / "media" / "TEST-FM" / "00_main.jpg"; primary.parent.mkdir(parents=True, exist_ok=True)
    for old in primary.parent.glob("x*"): old.unlink()
    stub_photo(primary, "h")                                                                     # candidate 0 is the shot's own photo
    rel = os.path.relpath(primary, FM.HERE)
    return {"id": "TEST-FM", "beats": [
        {"say": "a", "shots": [{"src": rel, "from": "commons-search:Steam logo", "credit": "Photo: own, CC BY 4.0", "source": "s"}]},
        {"say": "b", "shots": [{"src": rel, "from": "commons-search:Steam logo", "credit": "Photo: own, CC BY 4.0", "source": "s"},
                               {"src": "media/stock.mp4", "from": "pixabay:video:city", "credit": "Video: x / Pixabay"}]},
        {"say": "c", "shots": [{"src": "media/p.jpg", "from": "page:https://example.com"}, {"src": "media/n.jpg", "from": "commons-search:nothing here"}]}]}
def quiet(fn, *a, **k):
    with contextlib.redirect_stderr(io.StringIO()): return fn(*a, **k)
extra_of = lambda sb: [s for b in sb["beats"] for s in b["shots"] if s.get("extra")]

calls["down"].clear(); sb = fboard(); added = quiet(FM.extras, sb)
ex0, ex1 = [s for s in sb["beats"][0]["shots"] if s.get("extra")], [s for s in sb["beats"][1]["shots"] if s.get("extra")]
assert added == len(ex0) + len(ex1) == 4 and len(ex0) == len(ex1) == 2, (added, ex0, ex1)      # 2 for each name search; not for stock, a page or no match
assert not [s for s in sb["beats"][2]["shots"] if s.get("extra")] and len(sb["beats"][1]["shots"]) == 4
own = sb["beats"][0]["shots"][0]
assert not own.get("extra") and all(s["of"] == own["src"] for s in ex0 + ex1)                   # each says which picture it belongs to
assert all(s["credit"].startswith("Photo: File:Steam_") and s["source"].startswith("https://commons.example/") for s in ex0 + ex1)
assert len({s["src"] for s in ex0 + ex1}) == 4 and all((FM.HERE / s["src"]).exists() for s in ex0 + ex1)
assert calls["down"] == [f"File:Steam_{i}.jpg" for i in range(1, 6)], calls["down"]            # the first is the shot's own, so the next are fetched, once each
assert len(list((FM.HERE / "media" / "TEST-FM").glob("*.jpg"))) == 5                           # the copy of the shot's own photo (Steam_1) was dropped
# a download that fails is left out and the others fill in; the cap, the pace of fetching and the description's room are kept
broken.add("File:Steam_2.jpg"); calls["down"].clear(); sb = fboard(); added = quiet(FM.extras, sb)
assert added == 3 and "File:Steam_2.jpg" in calls["down"] and not any("Steam_2.jpg" in s["credit"] for s in extra_of(sb)), added
broken.clear()
assert quiet(FM.extras, fboard(), cap=3) == 3 and quiet(FM.extras, fboard(), per=1) == 2 and quiet(FM.extras, fboard(), seconds=-1) == 0
base = sum(len(f"{s['credit']} ({s['source']})" if s.get("source") else s["credit"]) + 1 for b in fboard()["beats"] for s in b["shots"] if s.get("credit"))
one = len("Photo: File:Steam_2.jpg, CC BY 4.0, via Wikimedia Commons (https://commons.example/File:Steam_2.jpg)") + 1
room = FM.EXTRA_CREDIT_ROOM
for n_fit in (0, 1, 3):                                                                         # the description has room for this many credit lines
    FM.EXTRA_CREDIT_ROOM = base + n_fit * one + 5
    assert quiet(FM.extras, fboard()) == n_fit, (n_fit, FM.EXTRA_CREDIT_ROOM)
FM.EXTRA_CREDIT_ROOM = room
FM.commons_candidates = lambda words: (_ for _ in ()).throw(RuntimeError("Commons is down"))
assert quiet(FM.extras, fboard()) == 0                                                          # never an error: the pace falls back to new crops
# resolve() keeps the form the board gave each shot, which is what extras() reads; the two chain
FM.commons_candidates = lambda words: [] if words == "nothing here" else [{"title": t} for t in KIND]
(FM.HERE / "media" / "keep.jpg").parent.mkdir(exist_ok=True); stub_photo(FM.HERE / "media" / "keep.jpg", "h")
res = FM.resolve({"id": "TEST-RES", "beats": [{"say": "x", "shots": [{"src": "commons-search:Steam logo"}, {"src": "media/keep.jpg"}]}]})
first, second = res["beats"][0]["shots"]
assert first["from"] == "commons-search:Steam logo" and first["src"].startswith("media/TEST-RES/") and second["from"] == second["src"] == "media/keep.jpg"
assert quiet(FM.extras, res) == 2 and [s["of"] for s in extra_of(res)] == [first["src"]] * 2     # only the name search gets more photos
# the candidates are the old commons_search's, best first, the first being what it always chose
page = lambda i, title, w: {"index": i, "title": title, "imageinfo": [{"width": w}]}
resp = {"query": {"pages": {"1": page(1, "File:Taylor Swift 2012.jpg", 1200), "2": page(2, "File:Taylor Swift Eras.jpg", 2400),
                            "3": page(3, "File:Swift river.jpg", 3000), "4": page(4, "File:Taylor Swift tour.jpg", 1700),
                            "5": page(5, "File:Taylor Swift Trump rally.jpg", 3000), "6": page(6, "File:Taylor Swift small.jpg", 400)}}}
FM.commons_candidates, FM.commons_file, FM._get = real_cands, lambda title: (title, "c", "s"), lambda url, **kw: types.SimpleNamespace(json=lambda: resp)
FM._CANDS.clear()
got = [p["title"] for p in FM.commons_candidates("Taylor Swift")]
assert got == ["File:Taylor Swift Eras.jpg", "File:Taylor Swift tour.jpg", "File:Taylor Swift 2012.jpg"], got   # 1600 px wide first, then 1000; the name; no politics
assert FM.commons_search("Taylor Swift")[0] == got[0]
FM._CANDS.clear(); FM._get = lambda url, **kw: types.SimpleNamespace(json=lambda: {"query": {"pages": {}}})
try: FM.commons_search("Nobody Here"); raise SystemExit("commons_search should have raised")
except RuntimeError as e: assert "no Commons image" in str(e)
FM.commons_candidates, FM.commons_file, FM._get = real_cands, real_file, real_get
print("5 more photos ok")
print("look style ok")
