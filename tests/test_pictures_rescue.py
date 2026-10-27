"""Offline test of subject first (fetch_media.rescue, 27 October; no network, no model):
1. _names and subjects find the beat's named subjects ("Harry Kane", "Ballon d'Or", "Virgil van Dijk"), drop a possessive, a
   sentence's lone opening word and a single word already inside a longer name, and take the shot's label and search first;
2. wiki_leads keeps a free lead picture of each article (redirects followed, one Wikipedia call, cached), and leaves out a
   disambiguation page, a political page, a missing page and a picture under min_width; any failure gives [];
3. rescue swaps an off-topic or missing picture for the subject's when it scores better by the margin (a stock video needs
   video_margin), skips pictures already in the Short, never raises and leaves the shot as it was when it cannot help;
4. resolve rescues at most max_per_short shots, never reuses a rescued stock shot for another and keeps a rescued search;
5. extras looks for more photos of the rescued subject; pictures_summary counts pic_low_share and pic_rescued;
6. drivers bands pic_relevance (on topic, loose, off topic) and config.json holds every setting."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import atexit, contextlib, io, json, os, shutil, sys
atexit.register(shutil.rmtree, SCRATCH, True)
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import fetch_media as FM
import pictures as PX
import drivers as D
REPO = _p.Path(REPO_DIR)


def quiet(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): return fn(*a, **k)


# ---- 1. the beat's named subjects ----
line = "Harry Kane's season ended with the Ballon d'Or in Paris. Tied on two trophies are Virgil van Dijk and Alfredo Di Stéfano."
got = FM._names(line)
assert ("Harry Kane", False) in got and ("Ballon d'Or", False) in got, got
assert ("Tied", True) in got, got                                  # a sentence's lone opening word is marked
assert ("Virgil van Dijk", False) in got and ("Alfredo Di Stéfano", False) in got, got
assert FM.subjects({"say": line}, {"from": "pixabay:photo:football trophy"}) == ["Harry Kane", "Ballon d'Or", "Virgil van Dijk"]
assert FM.subjects({"say": "Today the Eiffel Tower turned gold."}, {"from": "commons-search:Eiffel Tower night", "label": {"t": "Gustave Eiffel"}},
                   {"viral": "Paris"}) == ["Gustave Eiffel", "Eiffel Tower", "Paris"]
assert FM.subjects({"say": "Tied on goals. Kane scored."}, {"from": "pixabay:photo:goal"}) == []
assert FM.subjects({"say": "Kane scored again and Kane is top."}, {"from": "pixabay:photo:goal"}, {"watch": "yes"}) == ["Kane"]
assert FM.subjects({"say": "Harry Kane scored. Then Kane celebrated with the Bayern fans."}, {"from": "pixabay:photo:x"}) == ["Harry Kane", "Bayern"]
assert FM._title_of("https://commons.wikimedia.org/wiki/File:Harry_Kane_2024.jpg") == "File:Harry Kane 2024.jpg"
assert FM._title_of("https://pixabay.com/photos/123") is None


# ---- 2. Wikipedia lead pictures ----
class R:
    def __init__(self, js): self.js = js
    def json(self): return self.js


CALLS = []


def fake_get(url, params=None, **kw):
    CALLS.append((url, dict(params or {})))
    if url == FM.WIKI:
        assert params["pilicense"] == "free" and params["redirects"] == 1, params
        return R({"query": {
            "redirects": [{"from": "Ballon d'Or", "to": "Ballon d'Or (France Football)"}],
            "pages": [{"title": "Harry Kane", "pageimage": "Harry_Kane_2024.jpg", "description": "English footballer (born 1993)"},
                      {"title": "Ballon d'Or (France Football)", "pageimage": "Ballon_d'Or_trophy.jpg", "description": "Annual football award"},
                      {"title": "Kane", "pageimage": "Kane_x.jpg", "description": "Topics referred to by the same term"},
                      {"title": "Prime Minister Example", "pageimage": "PM.jpg", "description": "British politician and minister"},
                      {"title": "Tiny Pic", "pageimage": "Tiny.jpg", "description": "A small picture"},
                      {"title": "Missing Person", "missing": True}]}})
    assert url == FM.COMMONS, url
    ii = {"File:Harry Kane 2024.jpg": 2400, "File:Ballon d'Or trophy.jpg": 1600, "File:Tiny.jpg": 640}
    asked = params["titles"].split("|")
    assert set(asked) <= set(ii), asked                            # only the kept lead pictures are looked up
    return R({"query": {"pages": [{"title": t, "imageinfo": [{"width": ii[t], "thumburl": "https://thumb.example/" + t[5:]}]} for t in asked]}})


real_get = FM._get
FM._get = fake_get
FM._LEADS.clear()
names = ["Harry Kane", "Ballon d'Or", "Kane", "Prime Minister Example", "Tiny Pic", "Missing Person"]
leads = quiet(FM.wiki_leads, names)
assert [(p["_name"], p["title"]) for p in leads] == [("Harry Kane", "File:Harry Kane 2024.jpg"), ("Ballon d'Or", "File:Ballon d'Or trophy.jpg")], leads
assert leads[0]["imageinfo"][0]["thumburl"].startswith("https://thumb.example/"), leads
assert [u for u, _ in CALLS].count(FM.WIKI) == 1, CALLS             # one Wikipedia call for every name
assert FM._LEADS["Kane"] is None and FM._LEADS["Prime Minister Example"] is None and FM._LEADS["Missing Person"] is None
CALLS.clear()
assert [p["_name"] for p in quiet(FM.wiki_leads, ["Harry Kane"])] == ["Harry Kane"] and [u for u, _ in CALLS] == [FM.COMMONS], CALLS
assert [p["_name"] for p in quiet(FM.wiki_leads, ["Harry Kane", "Tiny Pic"], min_width=600)] == ["Harry Kane", "Tiny Pic"]
assert quiet(FM.wiki_leads, ["Kane", "Missing Person"]) == []      # nothing kept: no Commons call either


def boom(*a, **k): raise ConnectionError("offline")


FM._get = boom
assert quiet(FM.wiki_leads, ["Someone New"]) == []
FM._get = real_get


# ---- 3. rescue ----
FM.HERE = SCRATCH / "fm"; (FM.HERE / "media").mkdir(parents=True)
D_ = FM.HERE / "media" / "T1"; D_.mkdir()
CFG = dict(FM.RESCUE)
REL = {}                                  # a candidate's thumbnail -> the relevance the fake ranker gives it
TAKEN, COMMITTED, DOWNLOADED = set(), [], []


def cand(title, width=2000):
    return {"title": title, "imageinfo": [{"thumburl": "https://thumb.example/" + title[5:], "width": width}]}


def fake_rank(thumbs, ctx, bonus=None):
    assert ctx, ctx
    order = sorted(range(len(thumbs)), key=lambda i: -REL.get(thumbs[i], 0.0))
    return [(i, {"rel": REL.get(thumbs[i], 0.0), "hash": abs(hash(thumbs[i])) % 100000}) for i in order]


def fake_download(url, d, stem):
    f = _p.Path(d) / f"{stem}.jpg"; f.write_bytes(b"jpg"); DOWNLOADED.append(url); return f


LEADS, CANDS = {}, {}
FM.wiki_leads = lambda names, min_width=1000: [dict(LEADS[n], _name=n) for n in names if n in LEADS]
FM.commons_candidates = lambda words: CANDS.get(words, [])
FM.commons_file = lambda title: ("https://upload.example/" + title[5:].replace(" ", "_"), f"Photo: someone, CC BY 4.0, via Wikimedia Commons",
                                 "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"))
FM.download = fake_download
PX.rank, PX.is_taken, PX.commit = fake_rank, (lambda h: h in TAKEN), (lambda info: COMMITTED.append(info))
PX.score_file = lambda f, ctx: {"rel": 0.31, "hash": 7}
FM.PICK.clear(); FM.PICK["ctx"] = {"parts": [("a photo of harry kane", 1.0)]}

kane = cand("File:Harry Kane 2024.jpg")
trophy = cand("File:Ballon d'Or trophy.jpg")
LEADS["Harry Kane"] = kane
CANDS["Harry Kane"] = [cand("File:Harry Kane Bayern 2025.jpg"), cand("File:Harry Kane England.jpg"), cand("File:Harry Kane fans.jpg"), cand("File:Harry Kane fourth.jpg")]
CANDS["Ballon d'Or"] = [trophy]
REL.update({kane["imageinfo"][0]["thumburl"]: 0.45, trophy["imageinfo"][0]["thumburl"]: 0.40,
            "https://thumb.example/Harry Kane Bayern 2025.jpg": 0.30})
beat = {"say": "Harry Kane's season ended with the Ballon d'Or."}


def shot(**k):
    return dict({"src": "media/T1/00_stock.jpg", "from": "pixabay:photo:football trophy", "credit": "Pixabay", "source": "https://pixabay.com/1",
                 "relevance": 0.10, "cuts": "auto", "start": 1.0}, **k)


s = shot(); used = set()
assert FM.rescue(s, beat, {}, D_, "01r_", used, CFG) is True
assert s["rescued"] is True and s["subject"] == "Harry Kane" and s["relevance"] == 0.45, s
assert s["src"].startswith("media/T1/01r_") and s["credit"].endswith("via Wikimedia Commons") and "Harry_Kane_2024" in s["source"], s
assert "cuts" not in s and "start" not in s and s["from"] == "pixabay:photo:football trophy", s
assert used == {"File:Harry Kane 2024.jpg"} and COMMITTED[-1]["rel"] == 0.45, (used, COMMITTED)
pool_sizes = []
real_ranked = FM._ranked
FM._ranked = lambda items, thumbs, bonus=None: (pool_sizes.append(len(items)), real_ranked(items, thumbs, bonus))[1]

# the picture already in the Short is skipped: the next best (the trophy) comes in
s2 = shot()
assert FM.rescue(s2, beat, {}, D_, "02r_", used, CFG) is True and s2["subject"] == "Ballon d'Or" and s2["relevance"] == 0.40, s2
assert "File:Harry Kane 2024.jpg" not in str(s2["source"]).replace("_", " ")
assert pool_sizes[-1] <= PX.TOP_K, pool_sizes

# a near-duplicate of a picture taken earlier goes the same way
TAKEN.add(fake_rank([trophy["imageinfo"][0]["thumburl"]], {"x": 1})[0][1]["hash"])
s3 = shot()
assert FM.rescue(s3, beat, {}, D_, "03r_", set(), CFG) is True and s3["subject"] == "Harry Kane" and s3["relevance"] == 0.45, s3
TAKEN.clear()

# not better by the margin: the shot stays exactly as it was
s4 = shot(relevance=0.21); before = dict(s4)
REL[kane["imageinfo"][0]["thumburl"]] = 0.25; REL[trophy["imageinfo"][0]["thumburl"]] = 0.24
REL["https://thumb.example/Harry Kane Bayern 2025.jpg"] = 0.2
assert FM.rescue(s4, beat, {}, D_, "04r_", set(), CFG) is False and s4 == before, s4
s4b = shot(relevance=0.19)
assert FM.rescue(s4b, beat, {}, D_, "04r_", set(), CFG) is True and s4b["relevance"] == 0.25, s4b

# a stock video needs the bigger margin
REL[kane["imageinfo"][0]["thumburl"]] = 0.22
v = shot(src="media/T1/00_stock.mp4", from_="x", relevance=0.15); v.pop("from_"); v["from"] = "pixabay:video:stadium crowd"; before = dict(v)
assert FM.rescue(v, beat, {}, D_, "05r_", set(), CFG) is False and v == before, v
REL[kane["imageinfo"][0]["thumburl"]] = 0.30
assert FM.rescue(v, beat, {}, D_, "05r_", set(), CFG) is True and v["src"].endswith(".jpg") and v["relevance"] == 0.30, v

# on topic already, settings off, not a rescuable source, no score, nobody named: untouched
for sh, b, cfg in ((shot(relevance=0.3), beat, CFG), (shot(), beat, dict(CFG, on=False)),
                   (shot(**{"from": "commons:File:Harry Kane 2024.jpg"}), beat, CFG), (shot(relevance=None), beat, CFG),
                   (shot(relevance="0.1"), beat, CFG), (shot(), {"say": "the trophy shone under the lights."}, CFG)):
    before = dict(sh)
    assert FM.rescue(sh, b, {}, D_, "06r_", set(), cfg) is False and sh == before, sh

# a missing picture (the search failed) is given the subject's even with no ranking: the lead picture first
FM.PICK["ctx"] = None
miss = {"src": "commons-search:Harry Kane trophy", "from": "commons-search:Harry Kane trophy", "_failed": "no photo found"}
assert FM.rescue(miss, beat, {}, D_, "07r_", set(), CFG) is True, miss
assert "_failed" not in miss and miss["subject"] == "Harry Kane" and miss["relevance"] == 0.31 and "Harry_Kane_2024" in miss["source"], miss
FM.PICK["ctx"] = {"parts": [("a photo of harry kane", 1.0)]}
# a stock shot with no ranking is left alone (nothing proves the subject's picture is better)
FM.PICK["ctx"] = None
st = shot(); before = dict(st)
assert FM.rescue(st, beat, {}, D_, "08r_", set(), CFG) is False and st == before
FM.PICK["ctx"] = {"parts": [("a photo of harry kane", 1.0)]}
# a missing picture with nothing to offer stays missing
lone = {"src": "commons-search:Zzyzx Qwerty", "from": "commons-search:Zzyzx Qwerty", "_failed": "no photo found"}
assert FM.rescue(lone, {"say": "Zzyzx Qwerty."}, {}, D_, "09r_", set(), CFG) is False and lone["_failed"] == "no photo found"

# any failure leaves the shot as it was and raises nothing
REL[kane["imageinfo"][0]["thumburl"]] = 0.45
FM.commons_file = boom
s5 = shot(); before = dict(s5)
assert quiet(FM.rescue, s5, beat, {}, D_, "10r_", set(), CFG) is False and s5 == before
FM.commons_file = lambda title: ("https://upload.example/" + title[5:].replace(" ", "_"), "Photo: someone, CC BY 4.0, via Wikimedia Commons",
                                 "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"))
FM.download = boom
assert quiet(FM.rescue, s5, beat, {}, D_, "10r_", set(), CFG) is False and s5 == before
FM.download = fake_download
FM.commons_candidates = boom                                        # a Commons search that fails still leaves the lead picture
s6 = shot()
assert quiet(FM.rescue, s6, beat, {}, D_, "11r_", set(), CFG) is True and s6["subject"] == "Harry Kane"
FM.commons_candidates = lambda words: CANDS.get(words, [])
FM._ranked = real_ranked


# ---- 4. resolve ----
FILE_REL = {}
pix = iter(range(100))


def fake_pixabay(kind, words, used, dark_ok=False):
    u = f"https://pixabay.example/{words.replace(' ', '-')}-{next(pix)}.jpg"; used.add(u); return u, "Pixabay", "https://pixabay.com/x"


def fake_download2(url, d, stem):
    f = fake_download(url, d, stem); FILE_REL[str(f)] = 0.1 if "pixabay" in url else 0.6; return f


FM.pixabay, FM.download = fake_pixabay, fake_download2
FM.commons_search = lambda words: ("https://upload.example/stadium.jpg", "Photo: x, CC0, via Wikimedia Commons",
                                   "https://commons.wikimedia.org/wiki/File:Empty_stadium.jpg")
FM._relevance = lambda f: {"relevance": FILE_REL.get(str(f), 0.6)}
PX.begin, PX.context = (lambda sb: None), (lambda *a, **k: {"parts": [("a photo", 1.0)]})
REL[kane["imageinfo"][0]["thumburl"]] = 0.45; REL[trophy["imageinfo"][0]["thumburl"]] = 0.40
FM._LEADS.clear(); FM._CANDS.clear()


def board(n_stock=3):
    beats = [{"say": "Harry Kane lifted the Ballon d'Or.", "shots": [{"src": "pixabay:photo:football trophy"}]} for _ in range(n_stock)]
    beats.append({"say": "Harry Kane lifted the Ballon d'Or.", "shots": [{"src": "commons-search:Harry Kane trophy"}]})
    beats.append({"say": "Harry Kane lifted the Ballon d'Or.", "shots": [{"src": "commons-search:Harry Kane trophy"}]})
    return {"id": "T2", "beats": beats}


FM.rescue_cfg = lambda: dict(FM.RESCUE, max_per_short=2, floor=0.5)
sb = quiet(FM.resolve, board())
shots = [b["shots"][0] for b in sb["beats"]]
assert [bool(s.get("rescued")) for s in shots[:3]] == [True, True, False], shots   # at most max_per_short
assert shots[0]["subject"] == "Harry Kane" and shots[1]["subject"] == "Ballon d'Or", shots          # never the same picture twice
assert shots[2]["src"].startswith("media/T2/") and shots[2]["relevance"] == 0.1 and shots[2]["from"] == "pixabay:photo:football trophy"
assert not shots[3].get("rescued") and shots[3]["relevance"] == 0.6, shots[3]                      # on topic: kept
FM.rescue_cfg = lambda: dict(FM.RESCUE, floor=0.7)
FM._ranked = lambda items, thumbs, bonus=None: real_ranked(items, thumbs, bonus)
CANDS["Harry Kane"] = []
REL[kane["imageinfo"][0]["thumburl"]] = 0.9
sb = quiet(FM.resolve, board(0))
a, b = sb["beats"][0]["shots"][0], sb["beats"][1]["shots"][0]
assert a.get("rescued") and a["subject"] == "Harry Kane" and a == b, (a, b)                        # a rescued search is kept for its repeat
FM.rescue_cfg = lambda: dict(FM.RESCUE, on=False)
sb = quiet(FM.resolve, board(1))
assert not any(s.get("rescued") for bt in sb["beats"] for s in bt["shots"])


# ---- 5. extras and the Short's numbers ----
ASKED = []
FM.commons_candidates = lambda words: (ASKED.append(words), [])[1]
sb = {"id": "T3", "beats": [{"shots": [{"src": "media/T1/01r_x.jpg", "from": "pixabay:photo:trophy", "rescued": True, "subject": "Harry Kane"}]},
                            {"shots": [{"src": "media/T1/02.jpg", "from": "pixabay:photo:crowd"}]},
                            {"shots": [{"src": "media/T1/03.jpg", "from": "commons-search:Wembley Stadium"}]}]}
assert quiet(FM.extras, sb) == 0 and ASKED == ["Harry Kane", "Wembley Stadium"], ASKED

FM.rescue_cfg = lambda: dict(FM.RESCUE)
PX.summary = lambda: {}
sb = {"beats": [{"shots": [{"relevance": 0.1}, {"relevance": 0.3, "rescued": True}]},
                {"shots": [{"relevance": 0.5, "rescued": True, "extra": True}, {"src": "x.mp4"}]}], "_pic_found": [2, 2]}
out = FM.pictures_summary(sb)
assert out["pic_low_share"] == 0.33 and out["pic_rescued"] == 1 and out["pic_relevance"] == 0.3 and out["pic_found_share"] == 1.0, out
out = FM.pictures_summary({"beats": [{"shots": [{"src": "x.mp4"}]}]})
assert "pic_low_share" not in out and out["pic_rescued"] == 0, out


# ---- 6. drivers and the settings ----
for v, band in (("0.42", "on topic"), ("0.35", "on topic"), ("0.25", "loose"), ("0.2", "loose"), ("0.12", "off topic"), ("", ""), (None, "")):
    assert D.features({"pic_relevance": v})["pic_band"] == band, (v, D.features({"pic_relevance": v})["pic_band"])
assert "pic_band" in dict(D.FEATURES) and "pic_band" in D.PIPELINE_ONLY and "pic_band" in D.NEVER_PAUSED
cfg = json.loads((REPO / "config.json").read_text())["pictures"]
assert set(cfg) == set(FM.RESCUE), cfg
assert cfg["on"] is True and 0 < cfg["floor"] < 1 and cfg["margin"] <= cfg["video_margin"] and cfg["max_per_short"] >= 1, cfg
FM.HERE = REPO / "pipeline"
del FM.rescue_cfg
import importlib
FMR = importlib.reload(FM)
assert FMR.rescue_cfg() == dict(FMR.RESCUE, **cfg)
src = (REPO / "pipeline" / "fetch_media.py").read_text()
assert "\u2013" not in src and "\u2014" not in src
print("pictures rescue ok")
