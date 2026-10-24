"""Offline tests of the 24 October repair of the learning loop (data report: about three quarters of the verdicts were
noise, and the loop was narrowing the channel):
1. drivers.py: verdicts need proof (90% interval clear of typical, both halves agree, 2 UK days), shrink 12;
2. analytics.py: peers from the same UK day, retention capped at 100%, topic source and the explore flag reach shorts.csv,
   only acting verdict changes are logged, a new method is one line;
3. writer.py: 1 in 5 Shorts a day explores, category floors and caps, no writer model over 35% until proven;
4. looks.py and plan.py: an exploration Short draws its look and posting quarter evenly; no look option over 70%."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, json, math, os, random, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import drivers as D

now = dt.datetime.now(dt.timezone.utc)
def row(i, hours_ago, rel, **kw):
    posted = now - dt.timedelta(hours=hours_ago)
    return {"short": f"T-{i:03d}", "posted": posted.isoformat(timespec="minutes"), "posted_day": str(posted.date()),
            "yt_views": "100", "rel": rel, "category": "Music", "format": "one_detail", "hook": "A hook here", "seconds": "30",
            "slot_uk": "09:00", "title": "t", **kw}

# 1a. a real effect, steady over time and over days, is a "push"; the same lift on one day is only an early sign
rng = random.Random(1)
rows = []
for i in range(60):
    good = i % 3 == 0
    rows.append(row(i, 30 + i * 6, round(math.exp(rng.gauss(1.0 if good else -0.3, 0.4)), 3), category="Music" if good else "Film"))
table, _ = D.analyse(rows, {}, "2026-10-24")
v = {t["value"]: t for t in table if t["feature"] == "category"}
assert v["Music"]["verdict"] == "push" and v["Film"]["verdict"] in ("cut back", "early sign", "about typical"), v
one_day = [row(i, 30 + i % 5, 3.0, category="Sport") for i in range(8)] + [row(100 + i, 30 + i * 6, 1.0, category="Film") for i in range(30)]
t1, _ = D.analyse(one_day, {}, "2026-10-24")
s = next(t for t in t1 if t["feature"] == "category" and t["value"] == "Sport")
assert s["verdict"] == "early sign" and "UK day" in s["why"], s
print("1a proof needed ok")

# 1b. halves that disagree are no verdict: a choice great early and poor late stays an early sign
flip = [row(i, 30 + i * 6, 6.0 if i >= 20 else 0.9, category="Gaming" if i % 2 == 0 else "Film") for i in range(40)]
t2, _ = D.analyse(flip, {}, "2026-10-24")
g = next(t for t in t2 if t["feature"] == "category" and t["value"] == "Gaming")
assert g["verdict"] != "push", g
print("1b halves ok")

# 1c. shrink 12: 5 lucky Shorts at 3x come out well under 3x; noise from shuffled data almost never reaches a verdict
assert D.SHRINK == 12
few = [row(i, 30 + i * 20, 3.0, category="Animals") for i in range(5)] + [row(50 + i, 31 + i * 7, 1.0, category="Film") for i in range(40)]
t3, _ = D.analyse(few, {}, "2026-10-24")
a = next(t for t in t3 if t["feature"] == "category" and t["value"] == "Animals")
assert a["lift"] < 1.6, a
noise = [row(i, 30 + i * 5, round(math.exp(rng.gauss(0, 1.5)), 3), category=rng.choice(["Music", "Film", "Sport", "Gaming"]),
             format=rng.choice(["one_detail", "three_details", "story"])) for i in range(100)]
acts = sum(1 for t in D.analyse(noise, {}, "2026-10-24")[0] if t["verdict"] in ("push", "cut back"))
assert acts <= 2, acts
print("1c shrink ok")

# 1d. UK days: two Shorts just after midnight UK in summer time are still the UK day before in UTC: the check counts UK days
assert D.uk_day({"posted": "2026-10-22T23:30+00:00"}) == "2026-10-23"
print("1d UK days ok")

# 1e. the category mix: every category at least 5% and none over 35%; paused none, retested 5%
mix = D.category_mix([{"feature": "category", "value": c, "lift": l, "verdict": v} for c, l, v in
                      (("Music", 3.0, "push"), ("Film", 2.5, "push"), ("Sport", 1.0, ""), ("Science", 0.2, "pause"),
                       ("Tech", 0.3, "retest"), ("Gaming", 0.5, ""), ("Entertainment", 0.6, ""))])
assert abs(sum(mix.values()) - 1) < 1e-9 and mix["Science"] == 0 and abs(mix["Tech"] - 0.05) < 0.01, mix
assert max(mix.values()) <= 0.35 + 1e-9 and min(v for k, v in mix.items() if k not in ("Science",)) >= 0.05 - 1e-9, mix
print("1e category mix ok")

# 2. analytics
import analytics as A
mk = lambda i, posted, v: {"short": f"S{i}", "posted": posted, "views_24h": v, "yt_views": v}
day = [mk(i, f"2026-10-21T{8 + i:02d}:00+00:00", 10 * (i + 1)) for i in range(4)]
other = [mk(10 + i, f"2026-10-18T{8 + i:02d}:00+00:00", 1000) for i in range(4)]
A.relative(day + other, "views_24h", "_r")
assert day[0]["_r"] == round(10 / 25, 3), day[0]["_r"]          # same UK day peers only (median 25), not 1,000s from 3 days before
lone = [mk(20, "2026-10-19T12:00+00:00", 50)]
A.relative(lone + day + other, "views_24h", "_r")
assert lone[0]["_r"] != "", lone[0]                              # a day with too few Shorts widens to ±36 hours, then ±3 days
assert A.at_point({0.1: 3.19, 0.5: 0.6}, 0.05) == 100 and A.at_point({0.1: 0.8}, 0.05) == 80
print("2a peers and retention cap ok")

A.ROOT = SCRATCH; A.OUT = SCRATCH / "analytics"; A.CACHE = A.OUT / "cache"
(SCRATCH / "boards" / "done").mkdir(parents=True); (SCRATCH / "status").mkdir(); A.CACHE.mkdir(parents=True)
(SCRATCH / "boards" / "done" / "QD-900.json").write_text(json.dumps({"id": "QD-900", "kind": "news", "source": "Google Trends",
    "category": "Music", "format": "one_detail", "beats": [{"say": "Hello there"}], "test": {"explore": "yes"}, "meta": {"title": "t"}}))
(SCRATCH / "status" / "QD-900.json").write_text(json.dumps({"id": "QD-900", "video": "vid900", "source": "pipeline"}))
o = A.our_shorts()["vid900"]
assert o["source"] == "Google Trends" and o["origin"] == "pipeline" and o["explore"] == "yes", o
print("2b topic source and explore flag ok")

t = lambda feat, val, verdict, n=6: {"feature": feat, "feature_label": feat.title(), "value": val, "verdict": verdict, "n": n,
                                     "lift": 1.3, "median_rel": 1.2, "why": ""}
A.log_decisions([t("category", "Music", "push"), t("format", "story", "about typical")], "rule one")
rows_ = list(csv.DictReader((A.OUT / "decisions.csv").open()))
assert len(rows_) == 1 and rows_[0]["change"] == "New judging rule: rule one", rows_       # a new method: one line
A.log_decisions([t("category", "Music", "push"), t("format", "story", "early sign")], "rule one")
assert len(list(csv.DictReader((A.OUT / "decisions.csv").open()))) == 1                  # typical to early sign: not logged
A.log_decisions([t("category", "Music", "about typical"), t("format", "story", "pause")], "rule one")
ch = [r["change"] for r in csv.DictReader((A.OUT / "decisions.csv").open())]
assert any(c.startswith("Back to normal for category") for c in ch) and any(c.startswith("Pause format") for c in ch), ch
print("2c decisions log ok")

# 3. writer allocation
import writer as W
boards = [{"test": {"explore": "yes" if i == 0 else "no"}, "category": "Music", "writer": "gemini:flash"} for i in range(5)]
assert W.explore_due([]) and not W.explore_due(boards[:2]) and W.explore_due(boards[:5])   # 1 of 6 is under 1 in 5
made = []
for i in range(15):
    e = W.explore_due(made); made.append({"test": {"explore": "yes" if e else "no"}})
assert sum(1 for b in made if b["test"]["explore"] == "yes") == 3, made                 # 3 of 15
_, picks = W.test_plan(7, "news", explore=True)
assert picks["explore"] == "yes" and all(picks[t] in W.TESTS[t] for t in picks if t in W.TESTS)
assert W.test_plan(7, "news")[1]["explore"] == "no"
packs = [{"topic": f"m{i}", "category": "Music"} for i in range(8)] + [{"topic": "g", "category": "Gaming"}, {"topic": "s", "category": "Science"}]
got = [W.explore_pick(packs, n)["category"] for n in range(300)]
assert all(70 <= got.count(c) <= 130 for c in ("Music", "Gaming", "Science")), {c: got.count(c) for c in set(got)}   # evenly by category
assert W.explore_pick(packs, 1)["topic"] in ("m0", "g", "s") and W.explore_pick([], 1) is None                   # its best pack
W.ROOT = SCRATCH
need = W.floor_needs([{"category": "Music"}, {"category": "Film"}], 15)
assert "Music" not in need and "Gaming" in need, need
need40 = W.floor_needs([{"category": "Music"}], 40)
assert "Music" in need40                                                                    # 7% of 40 is 3 a day
print("3a exploration and floors ok")

class FP:
    STATE = {}
    @staticmethod
    def writing_order(): return ["groq:big", "gemini:flash", "gemini:pro"]
W.factpack = FP
(SCRATCH / "analytics" / "models.json").write_text(json.dumps({"writers": {"gemini:flash": {"n": 2, "score": 20.0}}}))
W.DAY["boards"] = [{"writer": "gemini:flash"}] * 4 + [{"writer": "groq:big"}] * 2
assert all(W.choose_writer(f"QD-{i}") != "gemini:flash" for i in range(30))              # 4 of 6 already: capped until proven
(SCRATCH / "analytics" / "models.json").write_text(json.dumps({"writers": {"gemini:flash": {"n": 12, "score": 20.0}}}))
assert all(W.choose_writer(f"QD-{i}") != "gemini:flash" for i in range(30))              # 12 measured: still capped (20 needed, data report item 7)
(SCRATCH / "analytics" / "models.json").write_text(json.dumps({"writers": {"gemini:flash": {"n": 22, "score": 20.0}}}))
assert any(W.choose_writer(f"QD-{i}") == "gemini:flash" for i in range(30))              # proven: no cap
W.DAY["boards"] = []
W.ROOT = _p.Path(REPO_DIR)                      # the real formats catalogue
assert "format" in W.explore_format(3, "one_detail") and "one_detail" not in W.explore_format(3, "one_detail")
print("3b writer cap ok")

# 4. looks and posting quarters
import looks as LK
cat = LK.catalogue()
dim = next(d for d in cat["dimensions"] if len(LK.active(cat, d)) > 1)
top = next(iter(LK.active(cat, dim)))
recent = [{dim: top} for _ in range(20)]
stats = {"dimensions": {dim: {top: {"n": 40, "score": 5.0}}}}           # the others are under 30 measured
chosen = [LK.choose(f"QD-{i}", recent, stats)[dim] for i in range(30)]
assert top not in chosen, chosen                                      # on 100% of the latest looks: it sits out
ex = {LK.choose(f"QD-{i}", [], stats, explore=True)[dim] for i in range(60)}
assert len(ex) == len(LK.active(cat, dim)), ex                        # exploration draws every option
import plan as P
P.band_scores = lambda: {}
nows = dt.datetime(2026, 10, 26, 9, 0, tzinfo=dt.timezone.utc)
bands = set()
for i in range(40):
    ns = P.slot_picker(nows, set())
    bands.add(P.band(ns("2026-10-26", "Music", "evergreen", f"QD-{i}", explore=True)))
assert len(bands) >= 2, bands
print("4 looks and quarters ok")
print("learning loop ok")
