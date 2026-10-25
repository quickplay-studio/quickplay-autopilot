"""Offline test of the commentary Shorts (25 October: pipeline/commentary.py, clips.make_commentary, the clip: shot of fetch_media.py,
the footage's own sound in render3.py, the stats and the comparison in clips.insights). The model, Wikipedia and the Daily render are
stubbed; ffmpeg is real (a synthetic 60 second segment with a tone for its sound)."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import contextlib, copy, csv, datetime as dt, io, json, os, pathlib, re, shutil, subprocess, sys, types
import numpy as np, soundfile as sf
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
ROOT = pathlib.Path(SCRATCH)
os.environ["CLIPS_WORK"] = str(ROOT / "work")
(ROOT / "work").mkdir()
import clips as C, commentary as CM, validate, fetch_media as FM, factpack
import render as R, render3 as R3
C.NOW = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
C.PLANS, C.OUT, C.BOARDS, C.STATE = ROOT / "plans", ROOT / "out", ROOT / "boards" / "clips", ROOT / "state"
CM.STATE = ROOT / "state"
for d in (C.PLANS, C.OUT, C.STATE): d.mkdir(parents=True)
LOG = []
C.log = lambda *a: LOG.append(" ".join(str(x) for x in a))
CM.log = C.log
dur = lambda p: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)

# a campaign of the test's own: a gaming channel, rules that keep pictures to the campaign's footage, no AI rule
C.CFG["clips_format"] = "commentary"
C.CFG["campaigns"]["comm-test"] = {
    "active": True, "name": "Mitch Gaming test campaign", "platform": "Vyro", "url": "https://app.vyro.com/campaigns", "subject": "Mitch Gaming",
    "per_day": 2, "channel": "gaming", "wikipedia": ["Roblox"], "source": {"kind": "url", "url": "https://f.io/x", "label": "Mitch Gaming's tournament video"},
    "rules": {"focus": "The funniest and most dramatic moments.", "on_screen": "On-screen text must match what happens.", "hashtags": ["#paidpartnership", "#TotalDramaRoblox"],
              "description": "", "avoid": ["any logo, hashtag, watermark or footage not from this campaign", "profanity or anything not brand safe"], "min_s": 25, "max_s": 75}}
CAMP = C.CFG["campaigns"]["comm-test"]

# 1. the punchline window: the sentence the peak is in, 2.5 to 6 seconds, inside the moment
words = [{"w": w, "s": 20 + i * 0.5, "e": 20.4 + i * 0.5} for i, w in enumerate(
    "so we go in and then he opens the door. Oh my god no way he just did that. I cannot believe it, that was crazy. Next up we have another one".split())]
m = {"id": "comm-test-01", "start": 18.0, "end": 55.0, "peak": 27.0, "hook": "HE OPENS THE DOOR", "label": "", "title": "Mitch Gaming opens the door",
     "why": "he opens the door and cannot believe it", "score": 8, "question": "Would you open it?"}
pa, pl = CM.punchline(m, words)
assert 18.0 <= pa <= 27.0 and 2.5 <= pl <= 6.0 and pa + pl <= 55.0, (pa, pl)
sentence_start = next(w["s"] for w in words if w["w"] == "Oh")
assert abs(pa - (sentence_start - 0.3)) < 0.01, (pa, sentence_start)           # it opens at the start of the sentence the peak is in
assert CM.punchline(dict(m, start=26.0, end=28.0), words) is None               # a moment with no room for 2.5 seconds has no punchline
print("1 punchline ok", pa, pl)

# 2. which campaigns get which format
assert CM.format_of(CAMP, C.CFG) == "commentary" and C.format_of("comm-test", CAMP, m) == "commentary"
assert CM.format_of(dict(CAMP, format="cut"), C.CFG) == "cut"                    # the campaign's own format wins
assert CM.format_of(dict(CAMP, rules=dict(CAMP["rules"], series="parts")), C.CFG) == "cut" and CM.format_of(CAMP, C.CFG, dict(m, episode=1)) == "cut"
assert CM.format_of(dict(CAMP, rules=dict(CAMP["rules"], avoid=["AI-generated video"])), C.CFG) == "cut"      # a campaign that avoids AI-made video
assert CM.format_of(CAMP, {}) == "cut" and CM.format_of(CAMP, dict(C.CFG, clips_format="cut")) == "cut"
os.environ["CLIPS_FORMAT"] = "cut"; assert CM.format_of(CAMP, C.CFG) == "cut"; del os.environ["CLIPS_FORMAT"]
real = json.loads((pathlib.Path(REPO_DIR) / "clips" / "campaigns.json").read_text())
assert real["clips_format"] == "commentary" and real["campaigns"]["speed-expedia"]["format"] == "cut"       # the shipped defaults
assert all(real["campaigns"][k].get("wikipedia") for k in ("mrbeast-cod", "tdr-mitch", "valorant-champs"))
assert not CM.outside_pictures(CAMP) and CM.outside_pictures(dict(CAMP, rules=dict(CAMP["rules"], avoid=[])))
print("2 formats ok")

# 3. the clip: source: a file already on the runner, never downloaded, only from the clips work areas
work = ROOT / "work"
vid = work / "ev.mp4"
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=20", "-f", "lavfi",
                "-i", "sine=frequency=700:duration=20", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(vid)], check=True)
FM.download = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a clip: source must never be downloaded"))
FM.requests.get = FM.download
assert FM.clip_parse(f"{vid}:4:12.5") == (str(vid), 4.0, 12.5) and FM.clip_parse(f"{vid}") == (str(vid), None, None) and FM.clip_parse("/a:b/c.mp4:3") == ("/a:b/c.mp4", 3.0, None)
sb = {"id": "CLIP-T3", "beats": [
    {"say": "a", "shots": [{"src": f"clip:{vid}:4:12.5", "credit": "Clip from X, posted with permission", "source": "https://app.vyro.com/campaigns"}]},
    {"say": "b", "shots": [{"src": f"clip:{vid}:7.5:7.5"}, {"src": f"clip:{vid}"}]}]}
FM.HERE = pathlib.Path(REPO_DIR) / "pipeline"
sb = FM.resolve(sb)
v, f1, f2 = sb["beats"][0]["shots"][0], sb["beats"][1]["shots"][0], sb["beats"][1]["shots"][1]
assert (FM.HERE / v["src"]).resolve() == vid.resolve() and v["start"] == 4.0 and v["clip_end"] == 12.5 and v["credit"] == "Clip from X, posted with permission"
assert (FM.HERE / f1["src"]).resolve().suffix == ".jpg" and (FM.HERE / f1["src"]).stat().st_size > 1000       # start == end: a freeze frame, a picture
assert (FM.HERE / f2["src"]).resolve() == vid.resolve() and "start" not in f2                                     # no times: the file as it is
shutil.rmtree(FM.HERE / "media" / "CLIP-T3", ignore_errors=True)
for bad in ("clip:/etc/hostname", f"clip:{ROOT}/nothing.mp4:1:2", "clip:../../../etc/hostname:1:2"):
    try: FM.resolve({"id": "CLIP-T3", "beats": [{"say": "a", "shots": [{"src": bad}]}]}); assert False, bad
    except RuntimeError as e: assert "no usable media" in str(e), e              # refused: the shot fails, a board with nothing else cannot render
shutil.rmtree(FM.HERE / "media" / "CLIP-T3", ignore_errors=True)
good = {"id": "CLIP-T3B", "kind": CM.KIND, "beats": [{"say": "a", "shots": [{"src": f"clip:{vid}:1:3"}]}]}
assert not [e for e in validate.check(dict(good, id="QD-999"))[0] if "clip:" in e]
assert any("clip: shots are for" in e for e in validate.check({"id": "QD-999", "beats": good["beats"], "kind": "news"})[0])    # no other board may use one
assert not any("id:" in e for e in validate.check({"id": "CLIP-SPEED-EXPEDIA-01"})[0])
print("3 clip source ok")

# 4. the footage's own sound (render3): ducked under our voice, full in the let-it-play window, the music bed hushed there
SR = R.SR
t = lambda secs: np.arange(int(secs * SR)) / SR
voice = (0.2 * np.sin(2 * np.pi * 300 * t(3.0))).astype(np.float32)           # our voice for 3 seconds
segs = [(0.06, voice)]
n = int(9.0 * SR) + SR
entry = {"file": str(vid), "start": 2.0, "t0": 0.06, "t1": 8.06, "duck": 0.18, "play": (3.1, 8.06)}
foot, hush = R3.clip_sound([entry], segs, n)
rms = lambda a, t0, t1: float(np.sqrt(np.mean(a[int(t0 * SR):int(t1 * SR)] ** 2)))
under, window = rms(foot, 0.5, 2.8), rms(foot, 3.6, 7.8)
assert hush == [(3.1, 8.06)] and len(foot) == n
assert 0.14 < under / window < 0.24, (under, window)                                # the streamer is at 18% under us, at full in the window
assert abs(window - 0.9 * float(np.sqrt(np.mean(voice ** 2)))) < 0.02, window       # and as loud there as we are
assert rms(foot, 8.4, 9.0) == 0.0                                                     # nothing after the shot
assert R3.clip_sound([dict(entry, file=str(work / "nope.mp4"))], segs, n)[0].max() == 0.0     # a clip with no readable sound adds nothing
music = (0.3 * np.sin(2 * np.pi * 220 * t(9.5))).astype(np.float32)
def band(path, hz, a, b):
    y, _ = sf.read(path); y = y[:, 0] if y.ndim > 1 else y
    seg = y[int(a * SR):int(b * SR)] * np.hanning(int((b - a) * SR))
    return float(np.abs(np.fft.rfft(seg))[int(hz * (b - a))])
R3.mix_audio3(segs, 9.0, music, [], str(ROOT / "plain.wav"), -16, footage=foot)
R3.mix_audio3(segs, 9.0, music, [], str(ROOT / "hushed.wav"), -16, footage=foot, hush=hush)
ratio = band(ROOT / "hushed.wav", 220, 4.5, 7.5) / band(ROOT / "plain.wav", 220, 4.5, 7.5)
assert 0.05 < ratio < 0.3, ratio                                                      # the music bed drops to about 12% where the clip's own sound plays
assert abs(band(ROOT / "hushed.wav", 220, 0.4, 2.8) / band(ROOT / "plain.wav", 220, 0.4, 2.8) - 1) < 0.1      # and is untouched while we speak
print("4 footage sound ok", round(under / window, 3), round(ratio, 3))

# 4b. render3.main with a commentary board: the let-it-play beat gets its gap, the footage starts early enough that its punchline opens the window
here = ROOT / "here"; (here / "media").mkdir(parents=True)
shutil.copy(vid, here / "media" / "ev.mp4")
from PIL import Image
Image.fromarray(np.random.default_rng(1).integers(0, 255, (1920, 1080, 3), dtype=np.uint8)).save(here / "media" / "a.jpg")
R.tts = lambda text, voice, speed: np.zeros(int(R.SR * len(text.split()) / 3), np.float32)      # a silent voice, 3 words a second
R3.load_music = lambda slug, start, d, lib="music": (np.zeros(int(SR * (d + 1)), np.float32), [], {"title": "Track", "artist": "Artist"})
real_run = subprocess.run
class Sub:
    @staticmethod
    def run(cmd, **kw):
        c = [str(x) for x in cmd]
        if c[0] == "ffmpeg" and any(x.endswith("%05d.jpg") or x == "f32le" for x in c): return real_run(cmd, **kw)        # frames and the footage's sound: real
        pathlib.Path(c[-1]).parent.mkdir(parents=True, exist_ok=True); pathlib.Path(c[-1]).write_bytes(b"x")              # the mux and the capture: made up
        return types.SimpleNamespace(returncode=0, stdout=b"")
R3.subprocess, R3.HERE = Sub, here
captured = {}
async def fake_capture(html, data, duration, frames_cmd, poster_path, poster_t): captured["data"] = copy.deepcopy(data)
R.capture = fake_capture
R3.face_focus = lambda p: None
sbm = {"id": "CLIP-T4", "category": "Gaming", "chipIcon": "gamepad-2", "accent": "#8B5CF6", "gap": 0.1, "tail": 0.6, "music": {"slug": "ten"}, "kind": CM.KIND,
       "beats": [{"say": "Mitch Gaming just proved it in one go.", "visual": {"type": "none"}, "impact": True, "shots": [{"src": "media/a.jpg", "move": "in", "credit": "c", "source": "s"}]},
                 {"say": "Hear it for yourself right here now.", "visual": {"type": "none"}, "letplay": 4.0,
                  "shots": [{"src": "media/ev.mp4", "start": 0, "play_at": 10.0, "move": "still", "zoom": 1.0, "sound": {"duck": 0.18}, "credit": "Clip from X", "source": "s"}]},
                 {"say": "That is the whole argument, would you have done it?", "visual": {"type": "none"}, "impact": True, "shots": [{"src": "media/a.jpg", "move": "out"}]}]}
sbp = ROOT / "sbm.json"; sbp.write_text(json.dumps(sbm))
sys.argv = ["render3.py", str(sbp), str(ROOT / "out4")]
with contextlib.redirect_stdout(io.StringIO()): R3.main()
d4 = captured["data"]
b1 = d4["beats"][1]
assert abs((b1["end"] - b1["speech_end"]) - 4.0) < 0.01, b1                          # our voice stops for exactly the window
assert d4["play"] == [[b1["speech_end"], b1["end"]]], d4["play"]                      # captions are off inside it
assert len(R3.CLIP_AUDIO) == 1 and R3.CLIP_AUDIO[0]["play"] == (b1["speech_end"], b1["end"])
lead = b1["speech_end"] - b1["start"]
assert abs(R3.CLIP_AUDIO[0]["start"] - (10.0 - lead)) < 0.01, (R3.CLIP_AUDIO[0]["start"], lead)      # the punchline (10 s in the file) opens the window
w4, _ = sf.read(ROOT / "out4" / "CLIP-T4.wav")
w4 = w4[:, 0]
assert 0.12 < rms(w4, b1["start"] + 0.3, b1["speech_end"] - 0.1) / rms(w4, b1["speech_end"] + 0.3, b1["end"] - 0.1) < 0.26      # ducked, then full
vids = [it for it in d4["media"] if it["kind"] == "video"]
assert len(vids) == 1 and vids[0]["play"] == [b1["speech_end"], b1["end"]] and abs(vids[0]["t1"] - vids[0]["t0"] - (b1["end"] - b1["start"])) < 0.05
tl = json.loads((ROOT / "out4" / "CLIP-T4.timeline.json").read_text())
assert [s["kind"] for s in tl["shots"]] == ["image", "video", "image"] and tl["shots"][1]["play"]
print("4b render3 timeline ok", b1)

# 5. the board shape and the rules a commentary Short must keep (commentary.assemble, check, timing)
import time
CM.log = C.log
pack = {"topic": "Mitch Gaming", "kind": "evergreen", "signal": "clip commentary", "category": "", "what_is_new": "", "hooks": [],
        "sources": [["Roblox", "https://en.wikipedia.org/wiki/Roblox", "Wikipedia", ""]], "verified": [], "images": [], "subject": "Mitch Gaming", "built": "2026-10-20",
        "one_source": [{"claim": f"Roblox fact {k}", "sources": [1]} for k in range(4)]}
pack2, foot = CM.with_moment(pack, CAMP, m, "oh my god no way he just did that")
assert foot == 2 and pack2["sources"][1][:2] == ["Mitch Gaming test campaign", CAMP["url"]] and len(pack["sources"]) == 1       # the footage is the last source; the cached pack is not touched
assert pack2["one_source"][-2]["claim"].startswith("In the footage, as said:") and pack2["one_source"][-2]["sources"] == [2]
assert pack2["one_source"][-1]["claim"] == "What the moment is: he opens the door and cannot believe it"

def mkctx(**kw):
    ctx = {"id": "CLIP-COMM-TEST-01", "cid": "comm-test", "campaign": CAMP, "moment": m, "day": "2026-10-25", "category": "Gaming", "handle": "Quickplay Gaming Clips",
           "role": "creator", "outside": False, "foot": foot, "sources": pack2["sources"], "play_at": pa, "play_len": pl, "ev_lo": pa - 10.0, "ev_path": str(vid),
           "stills": [f"clip:{work}/s{k}.jpg" for k in range(5)], "credit": "Clip from Mitch Gaming's tournament video, posted with permission",
           "source_url": CAMP["url"], "profane": C.PROFANE, "unsafe": C.UNSAFE}
    ctx.update(kw); return ctx
CTX = mkctx()
ANS = {"beats": [
    {"role": "hook", "say": "Mitch Gaming just turned a tough room into a tidy win.", "pic": ""},
    {"role": "context", "say": "Roblox lets players build their own games, so much of the fun comes from what other people make. That is why one good moment travels fast.", "pic": "Roblox"},
    {"role": "context", "say": "Most people would rush a choice like that. The calm option usually decides who comes out ahead, and it takes real nerve to wait for it.", "pic": ""},
    {"role": "evidence", "say": "So listen to how Mitch Gaming reacts in the next few seconds.", "pic": ""},
    {"role": "payoff", "say": "A calm head beats a fast hand almost every time, and that is the whole case for patience in one clip. Would you have waited as long as he did?", "pic": ""}],
    "title": "Mitch Gaming keeps cool when it counts \U0001F3AE", "alt_title": "How Mitch Gaming wins a tough room \U0001F3AE", "summary": "Mitch Gaming stays calm and it pays off.",
    "hashtags": ["#MitchGaming", "#Roblox", "#Shorts", "#roblox"], "tags": ["mitch gaming", "roblox clips"], "comment": "Would you have waited that long?",
    "facts": [["Roblox lets players build their own games", [1]], ["In the footage Mitch Gaming reacts in surprise", [2]], ["a made up source", [9]]]}
b = CM.assemble(copy.deepcopy(ANS), CTX, "stub-model")
errs, warns = CM.check(b, CTX)
assert errs == [], errs
tm = CM.timing(b)
assert 0.15 < tm["share"] < CM.FOOTAGE_MAX and tm["piece"] <= CM.PIECE_MAX and 30 <= tm["seconds"] <= 52, tm        # one piece of footage, well under the 40% rule
assert b["kind"] == CM.KIND and b["id"] == "CLIP-COMM-TEST-01" and b["category"] == "Gaming" and b["handle"] == "Quickplay Gaming Clips" and b["bgvideo"] is False
assert b["clip"]["roles"] == ["hook", "context", "context", "evidence", "payoff"] and 90 <= sum(CM.words_of(x["say"]) for x in b["beats"]) <= 120
evs = [x for x in b["beats"] if x.get("letplay")]
assert len(evs) == 1 and CM.PLAY[0] <= evs[0]["letplay"] <= CM.PLAY[1] and len(evs[0]["shots"]) == 1             # one beat lets the footage play, on one shot
es = evs[0]["shots"][0]
assert es["src"].startswith(f"clip:{vid}:") and es["sound"] == {"duck": CM.DUCK} and es["play_at"] == 10.0 and CM.footage_shot(es)
assert [CM.footage_shot(s) for x in b["beats"] for s in x["shots"]].count(True) == 1                              # everything else is a still: freeze or picture
assert all(s["src"].startswith("clip:") and not CM.footage_shot(s) for x in b["beats"] if not x.get("letplay") for s in x["shots"])      # no outside pictures for this campaign
assert b["beats"][0]["shots"][0]["label"] == {"t": "Mitch Gaming", "s": "creator"} and b["beats"][0]["impact"] and b["beats"][-1]["impact"]
assert all(s["credit"] == CTX["credit"] and s["source"] == CAMP["url"] for x in b["beats"] for s in x["shots"])    # every picture carries its credit
assert b["meta"]["facts"] == [["Roblox lets players build their own games", [1]], ["In the footage Mitch Gaming reacts in surprise", [2]]]      # a fact citing a source that is not there is dropped
h = b["meta"]["hashtags"]
assert h[:2] == ["#paidpartnership", "#TotalDramaRoblox"] and "#Shorts" not in h and "#Gaming" in h and len(h) == len({x.lower() for x in h}) <= 15, h
assert b["meta"]["sources"] == [["Roblox", "https://en.wikipedia.org/wiki/Roblox"], ["Mitch Gaming test campaign", CAMP["url"]]]
EM, EN = chr(0x2014), chr(0x2013)
assert EM not in json.dumps(b, ensure_ascii=False) and EN not in json.dumps(b, ensure_ascii=False)
dashed = CM.assemble({"beats": [{"role": "hook", "say": f"Mitch Gaming {EM} wins {EN} big."}]}, CTX, "m")["beats"][0]["say"]
assert EM not in dashed and EN not in dashed and dashed.startswith("Mitch Gaming")       # a model's dashes are taken out
# a campaign that allows outside pictures gets a Commons photo first on a context beat that names one
b2 = CM.assemble(copy.deepcopy(ANS), mkctx(outside=True), "stub-model")
assert b2["beats"][1]["shots"][0]["src"] == "commons-search:Roblox" and b2["beats"][1]["shots"][1]["src"].startswith("clip:")
# the shots resolve: the footage is the file on the runner, the stills are the pictures cut from it (nothing is downloaded)
for k in range(5): shutil.copy(here / "media" / "a.jpg", work / f"s{k}.jpg")
res = FM.resolve(copy.deepcopy(b))
rs = [s for x in res["beats"] for s in x["shots"]]
assert sum(1 for s in rs if "start" in s and "clip_end" in s) == 1 and all((FM.HERE / s["src"]).exists() for s in rs), rs
shutil.rmtree(FM.HERE / "media" / b["id"], ignore_errors=True)

def broken(fn):
    """the check's errors for a board changed by fn(board)"""
    bb = CM.assemble(copy.deepcopy(ANS), CTX, "stub-model"); fn(bb); return " | ".join(CM.check(bb, CTX)[0])
def say(i, text): return lambda bb: bb["beats"][i].update(say=text)
assert "hook: name Mitch Gaming in the first four words" in broken(say(0, "A tough room turned into a tidy win for the whole group today."))
assert "hook:" in broken(say(0, "Mitch Gaming just turned one tough room into a tidy win after a very long and winding road of tries."))
assert "negative framing" in broken(say(2, "Most people would rush a choice like that. He admits the calm option usually decides who comes out ahead, and it takes real nerve."))
assert "narrates the picture" in broken(say(1, "Watch what happens next because Roblox lets players build their own games and much of the fun comes from what other people make."))
assert "strong language" in broken(say(2, "Most people would rush a choice like that, wtf. The calm option usually decides who comes out ahead, and it takes real nerve to wait for it."))
assert "evidence beat: 2" in broken(say(3, "So listen very closely to how Mitch Gaming reacts in the next few seconds because it says a lot about how he thinks."))      # over 22 words
assert "narration:" in broken(say(4, "Would you have waited?"))
assert "beats:" in broken(lambda bb: bb["beats"].pop(1)) and "roles:" in broken(lambda bb: bb["clip"].update(roles=["hook", "context", "context", "payoff", "payoff"]))
assert "meta.facts" in broken(lambda bb: bb["meta"].update(facts=[]))
def long_play(bb): bb["beats"][3]["letplay"] = 20.0; bb["beats"][3]["shots"][0]["src"] = bb["beats"][3]["shots"][0]["src"].rsplit(":", 1)[0] + ":24.00"
e20 = broken(long_play)
assert "the footage must play 2.5 to 6.0 seconds" in e20 and "of the runtime, at most 40%" in e20 and "seconds in one piece, at most 15" in e20, e20       # the 40% rule and the 15 second piece
tiny = CM.assemble({"beats": [{"role": "hook", "say": "Mitch Gaming wins."}, {"role": "evidence", "say": "Listen up now."}, {"role": "payoff", "say": "Good."}]}, CTX, "m")
assert tiny["beats"][1]["letplay"] < 1.0, tiny["beats"][1]      # the window shrinks to what the 40% rule allows; check() then refuses the script
assert not any(CM.footage_shot(s) for s in [{"src": "clip:/a.mp4:5:5"}, {"src": "clip:/a.mp4"}, {"src": "media/a.jpg"}, {}])
assert CM.subject_in("Mitch Gaming", "Mitch's big night") and CM.subject_in("Mitch Gaming", "Tonight Gaming wins") and not CM.subject_in("Mitch Gaming", "A big night for a gamer today")
print("5 board and rules ok", tm)

# 6. write(): the free chain, fixed with the problems named, never Claude, at most three tries
ASKS = []
def fake_gemini(script):
    def g(prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None, writing=False):
        if prompt.startswith("You check a YouTube Short script"):
            ASKS.append(("check", temperature)); return script.get("check", {"ok": True}), "stub-check"
        ASKS.append(("write", temperature, writing, lite, "YOUR SCRIPT" in prompt)); a = script["answers"].pop(0) if len(script["answers"]) > 1 else script["answers"][0]
        return (copy.deepcopy(a), "stub-model")
    return g
bad_hook = copy.deepcopy(ANS); bad_hook["beats"][0]["say"] = "A tough room turned into a tidy win for the whole group today."
factpack.gemini = fake_gemini({"answers": [bad_hook, ANS]})
wb, wm, note = CM.write(CTX, pack2, "oh my god no way he just did that")
assert wb and wm == "stub-model" and wb["writer"] == "stub-model" and not CM.check(wb, CTX)[0], note
assert ASKS[0] == ("write", 0.7, True, True, False) and ASKS[1] == ("write", 0.3, True, True, True) and ASKS[2][0] == "check", ASKS      # free chain, writing, lite; the fix round carries the script
ASKS.clear(); factpack.gemini = fake_gemini({"answers": [bad_hook]})
wb, wm, note = CM.write(CTX, pack2, "x")
assert wb is None and note.startswith("still failing") and [a[0] for a in ASKS] == ["write"] * 3, (note, ASKS)       # three tries and no more
ASKS.clear(); factpack.gemini = fake_gemini({"answers": [ANS], "check": {"ok": False, "problems": [{"beat": 2, "issue": "a number the pack does not have"}]}})
wb, wm, note = CM.write(CTX, pack2, "x")
assert wb is None and "facts: beat 2: a number the pack does not have" in note, note                                  # the model fact check blocks a script it finds wrong
ASKS.clear(); factpack.gemini = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("every model down"))
try: CM.write(CTX, pack2, "x"); assert False
except RuntimeError: pass                        # the make loop catches it and the cut stands in
print("6 write ok")

# 7. the Wikipedia pack: checked facts only, cached for two weeks, none without an article that gives three
CALLS7 = []
def fake_page(url, wiki=False): CALLS7.append(url); return ("Roblox is an online platform. " * 60, None)
def fake_facts(prompt, texts, names, want=3): return [], None, [{"claim": f"Roblox fact {k}", "sources": [1]} for k in range(want + 1)], None
factpack.page_text, factpack.facts_from = fake_page, fake_facts
cache = ROOT / "wcache"
p1 = CM.wiki_pack("comm-test", CAMP, cache=cache, today=dt.date(2026, 10, 25))
assert p1 and p1["sources"][0][:3] == ["Roblox", "https://en.wikipedia.org/wiki/Roblox", "Wikipedia"] and len(p1["one_source"]) >= 3 and len(CALLS7) == 1
assert (cache / "comm-test.json").exists() and CM.wiki_pack("comm-test", CAMP, cache=cache, today=dt.date(2026, 11, 1)) == p1 and len(CALLS7) == 1      # a week on: the cache
assert CM.wiki_pack("comm-test", CAMP, cache=cache, today=dt.date(2026, 11, 9)) and len(CALLS7) == 2                                                  # 15 days on: rebuilt
assert CM.wiki_pack("comm-test", dict(CAMP, subject="Someone Else"), cache=cache, today=dt.date(2026, 10, 26)) and len(CALLS7) == 3                    # another subject: rebuilt
factpack.facts_from = lambda *a, **k: ([], None, [{"claim": "one", "sources": [1]}], None)
assert CM.wiki_pack("comm-test-2", CAMP, cache=cache) is None                                                      # one checked fact is not enough
factpack.page_text = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network"))
assert CM.wiki_pack("comm-test-3", CAMP, cache=cache) is None                                                      # an unreachable article is no pack
class Resp:
    ok = True
    def json(self): return ["Kevin Langue", ["Kevin Lang", "Kevin Langue", "Kevin Langue (streamer)"], [], []]
import requests
requests.get = lambda *a, **k: Resp()
assert CM.search_titles("Kevin Langue") == ["Kevin Langue", "Kevin Langue (streamer)"]       # "Kevin Lang" is somebody else
assert CM.wiki_candidates({"subject": "Kevin Langue"}) == ["Kevin Langue", "Kevin Langue (streamer)"] and CM.wiki_candidates({"wikipedia": "Roblox"}) == ["Roblox"]
requests.get = FM.download
print("7 wikipedia pack ok")

# 8. clips.make(): a commentary Short from a moment, end to end (model, Wikipedia and the Daily render stubbed; ffmpeg real)
seg, rendered = work / "comm-test.mp4", work / "rendered.mp4"
def synth(path, size, secs, rate):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={secs}", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={secs}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
synth(seg, "1280x720", 60, 25); synth(rendered, "1080x1920", 42, 10)
C.ROOT = ROOT; (ROOT / "clips").mkdir(exist_ok=True)
C.segment, C.transcribe = (lambda cid: seg), (lambda cid: WORDS8[0])
WORDS8 = [words]
os.environ["CB_CKPT"] = "/models/chatterbox"
CM.wiki_pack = lambda cid, c, cache=None, today=None: pack
factpack.gemini = fake_gemini({"answers": [ANS]})
ready_t = 1000.0
assert CM.ready(None)[0] and CM.ready(ready_t, now=ready_t - 10 * 60)[0] and not CM.ready(ready_t, now=ready_t - 8 * 60)[0]        # nine minutes are needed before the deadline
del os.environ["CB_CKPT"]; assert CM.ready(None) == (False, "no house voice on this runner (CB_CKPT)"); os.environ["CB_CKPT"] = "/models/chatterbox"
RENDERS, CUTS = [], []
def fake_render(board, path, sid, channel="clips", timeout=1500):
    on_disk = json.loads(pathlib.Path(path).read_text())
    assert on_disk == board and not validate.check(on_disk)[0], validate.check(on_disk)[0]          # the render reads the board file, and it is a valid board
    res = FM.resolve(copy.deepcopy(on_disk)); shots = [s for x in res["beats"] for s in x["shots"]]
    ev = next(s for s in shots if "clip_end" in s)
    assert (FM.HERE / ev["src"]).exists() and ev["start"] == 4.0 and ev["clip_end"] > 14.0 and all((FM.HERE / s["src"]).exists() for s in shots)       # the files are there to render from
    assert dur(FM.HERE / ev["src"]) > ev["clip_end"] and "clip_end" in ev          # the evidence file holds the lead and the window
    shutil.rmtree(FM.HERE / "media" / sid, ignore_errors=True)
    RENDERS.append((sid, channel)); (ROOT / "result" / sid).mkdir(parents=True, exist_ok=True); shutil.copy(rendered, ROOT / "result" / sid / "video.mp4")
    if RENDERS and os.environ.get("RENDER_FAILS"): raise RuntimeError("the render failed: no voice")
    return {"video": ROOT / "result" / sid / "video.mp4", "seconds": 41.8, "footage_seconds": 9.4, "footage_share": 0.225, "status": {"state": "rendered"},
            "upload": {"description": "A summary line.\n\nVisuals:\nStill from Mitch Gaming test campaign\n\nMusic: Track by Artist\n\n#tags"}}
CM.render = fake_render
def fake_cut(cid, mm, wd):
    CUTS.append(mm["id"]); out = C.OUT / f"{mm['id']}.mp4"; shutil.copy(rendered, out); mm["tests"] = {"layout": "letterbox", "take": "voice", "take_style": "argument"}; return out
C.make_clip = fake_cut
def moment(i, **kw): return dict(m, id=f"comm-test-{i:02d}", **kw)
def plan_of(*ms): (C.PLANS / "comm-test.json").write_text(json.dumps({"moments": list(ms)}))
def planned(): return {x["id"]: x for x in json.loads((C.PLANS / "comm-test.json").read_text())["moments"]}
def make_one(mm, wds=None, env=None):
    LOG.clear(); WORDS8[0] = wds or words; plan_of(mm)
    with contextlib.ExitStack() as st:
        for k, v in (env or {}).items(): os.environ[k] = v; st.callback(os.environ.pop, k, None)
        got = C.make("comm-test", 1)
    return got, planned()[mm["id"]], "\n".join(LOG)

got, r1, lg = make_one(moment(1))
assert len(got) == 1 and r1["format"] == "commentary" and r1["file"] == "comm-test-01.mp4" and (C.OUT / "comm-test-01.mp4").exists() and not CUTS, lg
assert RENDERS == [("CLIP-COMM-TEST-01", "clips")] and r1["channel"] == "gaming" and r1["category"] == "Gaming" and r1["seconds"] == 42
assert r1["tests"]["take_style"] == "board" and r1["tests"]["take"] == "board" and r1["title"].startswith("Mitch Gaming") and r1["title_planned"] == "Mitch Gaming opens the door"
assert r1["credits"] == ["Visuals:", "Still from Mitch Gaming test campaign", "Music: Track by Artist"] and r1["hashtags"][:2] == ["#paidpartnership", "#TotalDramaRoblox"]
assert r1["commentary"]["board"] == "boards/clips/CLIP-COMM-TEST-01.json" and (ROOT / r1["commentary"]["board"]).exists() and r1["commentary"]["writer"] == "stub-model"
assert r1["commentary"]["beats"] == 5 and 90 <= r1["commentary"]["words"] <= 120 and r1["commentary"]["footage_share"] == 0.225 and r1["commentary"]["estimated_share"] < 0.4
assert r1["sources"][0] == ["Roblox", "https://en.wikipedia.org/wiki/Roblox"] and not list(work.glob("comm-test-01.ev.mp4")) and not list(work.glob("comm-test-01.s*.jpg"))      # sources kept, working files gone
assert "commentary Short made, 42 s, footage 22%" in lg or "commentary Short made, 42 s, footage 23%" in lg, lg
# the cut stands in for a moment that commentary cannot be made for: every reason logged, the day's number kept
CUTS.clear(); gem_calls = len(ASKS)
got, r, lg = make_one(moment(2), env={"CLIPS_FORMAT": "cut"})
assert r["format"] == "cut" and CUTS == ["comm-test-02"] and "commentary" not in lg.replace("comm-test", "")
C.DEADLINE = time.time() + 60; CUTS.clear()
got, r, lg = make_one(moment(3))
assert r["format"] == "cut" and CUTS == ["comm-test-03"] and "under 9 minutes left in this run" in lg and len(got) == 1, lg      # the JOB_T0 cap: no commentary started when the run is nearly out of time
C.DEADLINE = None; CUTS.clear()
got, r, lg = make_one(moment(4, start=26.0, end=28.0))
assert r["format"] == "cut" and CUTS == ["comm-test-04"] and "no 2.5 second punchline" in lg, lg
CUTS.clear(); got, r, lg = make_one(moment(5), wds=words + [{"w": "shit", "s": 16.0, "e": 16.3}])      # in the lead before the moment, inside the evidence file
assert r["format"] == "cut" and CUTS == ["comm-test-05"] and "strong language near the punchline" in lg, lg
CUTS.clear(); CM.wiki_pack = lambda *a, **k: None
got, r, lg = make_one(moment(6))
assert r["format"] == "cut" and CUTS == ["comm-test-06"] and "no checked facts about Mitch Gaming" in lg, lg
CM.wiki_pack = lambda cid, c, cache=None, today=None: pack
CUTS.clear(); factpack.gemini = fake_gemini({"answers": [bad_hook]})
got, r, lg = make_one(moment(7))
assert r["format"] == "cut" and CUTS == ["comm-test-07"] and "still failing" in lg
factpack.gemini = fake_gemini({"answers": [ANS]})
CUTS.clear(); got, r, lg = make_one(moment(8), env={"RENDER_FAILS": "1"})
assert r["format"] == "cut" and CUTS == ["comm-test-08"] and "commentary failed, the cut stands in: RuntimeError: the render failed" in lg, lg
CUTS.clear(); series = dict(CAMP, rules=dict(CAMP["rules"], series="parts")); C.CFG["campaigns"]["comm-test"] = series
got, r, lg = make_one(moment(9)); C.CFG["campaigns"]["comm-test"] = CAMP
assert r["format"] == "cut" and CUTS == ["comm-test-09"]             # a series stays a cut
print("8 make end to end ok")

# 9. the upload (title, description, tags, category), the stats field and the comparison
Y = sys.modules.get("youtube") or types.ModuleType("youtube"); sys.modules["youtube"] = Y
import quota
quota.allow, quota.spend = (lambda *a, **k: True), (lambda *a, **k: None)
UP, ROWS = [], []
Y.upload = lambda client, path, title, desc, tags, category, publish_at, paid=False: UP.append(dict(client=client, path=path, title=title, desc=desc, tags=tags, category=category, publish=publish_at, paid=paid)) or f"vid{len(UP)}"
C.gh, C.clips_client, C.add_rows = (lambda *a, **k: subprocess.CompletedProcess(a, 0)), (lambda ch: ch), ROWS.extend
make_one(moment(1))
comm = planned()["comm-test-01"]
(C.OUT / "comm-test-90.mp4").write_bytes(b"x")
cut_m = {"id": "comm-test-90", "made": comm["made"], "file": "comm-test-90.mp4", "hook": "he opens the door", "title": "Cut title", "start": 18, "end": 40, "channel": "gaming", "category": "Gaming",
         "tests": {"layout": "letterbox", "take": "voice", "take_style": "argument"}}
plan_of(comm, cut_m)
rows = C.upload("comm-test", mode="private")
u, uc = UP[0], UP[1]
assert len(rows) == 2 and u["client"] == "gaming" and u["paid"] is True and u["category"] == "Gaming" and u["publish"] is None and u["title"] == comm["title"]
d = u["desc"]
assert d.startswith("#ad Mitch Gaming stays calm and it pays off."), d
assert "Sources:\nRoblox: https://en.wikipedia.org/wiki/Roblox" in d and "app.vyro.com" not in d.split("Clip from")[0] and "Music: Track by Artist" in d and "Visuals:" in d
assert "#paidpartnership #TotalDramaRoblox" in d.replace("\n", " ") and "Clip from Mitch Gaming's tournament video, posted with the creator's permission" in d and C.AD_NOTE in d
assert "paidpartnership" in u["tags"] and "Mitch Gaming" in u["tags"] and "Roblox" in u["tags"] and len(u["tags"]) == len(set(u["tags"]))
assert uc["desc"].startswith("#ad He opens the door.") and "Sources:" not in uc["desc"]            # the cut's description and tags are as they were
assert C.social_caption(CAMP, comm).startswith("#ad Mitch Gaming stays calm and it pays off.") and C.social_caption(CAMP, cut_m).startswith("#ad He opens the door.")
# stats: the field the comparison reads
ig_m = dict(comm, publish_at="2026-10-24T11:00:00Z", instagram={"url": "https://instagram.com/reel/x", "media": "999"})
irow = C.ig_only_row("comm-test", ig_m)
assert irow["format"] == "commentary" and irow["seconds"] == 42 and irow["test_take_style"] == "board" and irow["privacy"] == "instagram" and irow["hours_public"] == 25.0, irow
assert C.ig_only_row("comm-test", dict(cut_m, publish_at="2026-10-24T11:00:00Z"))["format"] == "cut"
class _Videos:
    def list(self, part, id): return types.SimpleNamespace(execute=lambda: {"items": [{"id": i, "statistics": {"viewCount": "7"}, "status": {"privacyStatus": "public", "publishAt": "2026-10-24T09:00:00Z"}, "contentDetails": {}} for i in id.split(",")]})
C.clips_client = lambda ch: types.SimpleNamespace(videos=lambda: _Videos())
C.reach_traffic = lambda ch, days=14: {}
C.stop_check, C.expire_rows = (lambda *a, **k: None), (lambda *a, **k: None)
C.stats()
srows = {r["clip"]: r for r in csv.DictReader((ROOT / "clips" / "stats.csv").open())}
assert srows["comm-test-01"]["format"] == "commentary" and srows["comm-test-01"]["test_take_style"] == "board" and srows["comm-test-01"]["seconds"] == "42" and srows["comm-test-01"]["views"] == "7"
assert srows["comm-test-90"]["format"] == "cut" and srows["comm-test-90"]["test_take_style"] == "argument"
assert C.style_of(srows["comm-test-01"]) == "board" and C.style_of({"test_take": "voice"}) == "voice" and C.style_of({"test_take": "text"}) == "cut" and C.style_of({}) == "cut"
# the comparison: board against voice against cut, YouTube and Instagram views, the rule every clip test has
def row(arm, views, ig=None, n=0):
    base = {"privacy": "public", "hours_public": "30", "campaign": "comm-test", "views": str(views), "ig_views": "" if ig is None else str(ig),
            **{f"test_{t}": C.TESTS[t][0] for t in C.TESTS}}
    return dict(base, **{"board": {"test_take_style": "board", "format": "commentary", "test_take": "board"}, "voice": {"test_take": "voice", "test_take_style": "argument"},
                         "cut": {"test_take": "text"}}[arm])
mixed = [row("board", 40, 60) for _ in range(4)] + [row("voice", 5, 10) for _ in range(4)] + [row("cut", 2, 3) for _ in range(3)]
ins = C.insights(mixed)["format"]
assert ins["arms"]["board"]["n"] == 4 and ins["arms"]["board"]["mean_views"] == 40.0 and ins["arms"]["voice"]["n"] == 4 and ins["arms"]["cut"]["n"] == 3
assert ins["arms"]["board"]["ig_mean_views"] == 60.0 and ins["best"] == "board" and ins["best_ig"] == "board" and ins["verdict"] == "board" and "board leads on YouTube views and on Instagram views" in ins["note"], ins
thin = C.insights([row("board", 90, 90), row("board", 90, 90)] + mixed[4:])["format"]
assert thin["best"] is None and thin["verdict"] is None and "no verdict yet" in thin["note"]                  # 2 clips is no verdict
split = C.insights([row("board", 40, 1) for _ in range(3)] + [row("voice", 3, 50) for _ in range(3)])["format"]
assert split["best"] == "board" and split["best_ig"] == "voice" and split["verdict"] is None and "no verdict: YouTube views favour board, Instagram views favour voice" in split["note"]
assert json.loads((ROOT / "clips" / "insights.json").read_text())["format"]["arms"]["board"]["n"] == 3
# reach: the board clips decide the unseen cap once 3 are a day old (the cut's record no longer holds the commentary back)
old_voice = [dict(row("voice", 0), channel="gaming") for _ in range(10)]
assert C.reach_check(old_voice)["gaming"]["take_unseen"] is True
three = old_voice + [dict(row("board", 12), channel="gaming") for _ in range(3)]
rc = C.reach_check(three)["gaming"]
assert rc["board_day_old"] == 3 and rc["board_views"] == 36 and rc["take_unseen"] is False, rc
eight = old_voice + [dict(row("board", 0), channel="gaming") for _ in range(8)]
assert C.reach_check(eight)["gaming"]["take_unseen"] is True and C.reach_check(eight)["gaming"]["board_no_views"] == 8
print("9 upload, stats and comparison ok")
