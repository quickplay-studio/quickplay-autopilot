"""Offline tests of the better targets (28 October): the channel-day subscriber model, views at 7 and 28 days, the feed share:
1. pipeline/subs_daily.py: build (UK-day Shorts, the share of arm B among the Shorts that took an arm), merge (earlier days kept),
   the ridge on a planted effect (a known slope is recovered, a null factor is not clear, few days say so), the files;
2. analytics: views_7d and views_28d come off the same hourly curves as views_72h (no YouTube call: channel_daily is an Analytics
   query only), the channel days are read once per extra channel, the drivers table carries feed_pct, p and q;
3. changes.py: the metrics feed_share, views_7d_median and subs_day (views-weighted feed share, the 7-day median, the main
   channel's subscribers a day) can be ledger targets and are measured over their windows;
4. no em or en dash in what this adds."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, inspect, json, math, os, random, shutil, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import subs_daily as SD
import analytics as A
import changes as C
import drivers as DRV

UTC = dt.timezone.utc
AN = SCRATCH / "analytics"

# ---- 1. subs_daily ----
FACT = {"f0": ["a", "b"], "f1": ["a", "b"], "gene:g001": ["a", "b"]}
rows = [
    {"channel": "main", "posted": "2026-10-20T23:30:00+00:00", "f0": "b", "f1": "a", "genes": "gene:g001=b"},      # 00:30 on 21 October in the UK (BST)
    {"channel": "main", "posted": "2026-10-21T10:00:00+00:00", "f0": "a", "f1": "a", "genes": "gene:g001=a"},
    {"channel": "main", "posted": "2026-10-21T12:00:00+00:00", "f0": "b", "f1": "", "genes": ""},
    {"channel": "music", "posted": "2026-10-21T12:00:00+00:00", "f0": "b", "f1": "b", "genes": ""},
    {"channel": "main", "posted": "2026-10-22T12:00:00+00:00", "f0": "zzz", "f1": "", "genes": ""}]
daily = {"main": [{"day": "2026-10-21", "views": 3000, "engagedViews": 900, "subscribersGained": 4, "subscribersLost": 1},
                  {"day": "2026-10-22", "views": 10, "subscribersGained": 0, "subscribersLost": 0}],
         "music": [{"day": "2026-10-21", "views": 500, "engagedViews": 100, "subscribersGained": 1, "subscribersLost": 0}]}
out = {(r["channel"], r["day"]): r for r in SD.build(rows, daily, FACT)}
m21 = out[("main", "2026-10-21")]
assert m21["shorts"] == 3 and m21["subs_gained"] == 4 and m21["views"] == 3000 and m21["engaged_views"] == 900, m21        # the 00:30 BST Short is on the 21st
assert m21["share_f0"] == round(2 / 3, 3) and m21["share_f1"] == 0.0 and m21["share_gene:g001"] == 0.5, m21                 # arm B among the Shorts that took an arm
assert out[("music", "2026-10-21")]["share_f0"] == 1.0 and out[("music", "2026-10-21")]["share_f1"] == 1.0 and out[("music", "2026-10-21")]["shorts"] == 1
d22 = out[("main", "2026-10-22")]
assert d22["shorts"] == 1 and d22["share_f0"] == "" and d22["share_f1"] == "", d22                                          # an unknown arm and a blank take none
cols = SD.BASE + SD.share_cols(FACT)
assert cols[:7] == ["channel", "day", "subs_gained", "subs_lost", "views", "engaged_views", "shorts"] and "share_gene:g001" in cols
merged = SD.merge([{"channel": "main", "day": "2026-09-01", "subs_gained": "2"}, {"channel": "main", "day": "2026-10-21", "subs_gained": "99"}], list(out.values()), cols)
assert [(r["channel"], r["day"]) for r in merged] == [("main", "2026-09-01"), ("main", "2026-10-21"), ("main", "2026-10-22"), ("music", "2026-10-21")]
assert merged[1]["subs_gained"] == 4 and merged[0]["subs_gained"] == "2"                                                     # the new read wins, an older day stays


def synth(seed, days=40, slope=3.0, null_slope=0.0):
    """Two channels over `days` days: subscribers per 1,000 views = base + slope x share_f0 + null_slope x share_f1 + noise."""
    rng = random.Random(seed)
    out = []
    for ch, base in (("main", 1.5), ("music", 0.5)):
        for d in range(days):
            day = (dt.date(2026, 9, 1) + dt.timedelta(days=d)).isoformat()
            s0, s1 = rng.random(), rng.random()
            views = rng.randint(1500, 4500)
            rate = max(0.0, base + slope * s0 + null_slope * s1 + rng.gauss(0, 0.35))
            out.append({"channel": ch, "day": day, "subs_gained": round(rate * views / 1000), "subs_lost": 0, "views": views, "engaged_views": views // 3,
                        "shorts": 6, "share_f0": round(s0, 3), "share_f1": round(s1, 3)})
    return out


F2 = {"f0": ["a", "b"], "f1": ["a", "b"]}
res = SD.fit(synth(1), F2)
b0, lo0, hi0 = res["coef"]["f0"]; b1, lo1, hi1 = res["coef"]["f1"]
assert res["n"] == 80 and res["channels"] == ["main", "music"], res["n"]
assert 1.9 < b0 < 3.3 and lo0 > 0 and lo0 < b0 < hi0, (b0, lo0, hi0)                  # the planted slope is 3.0 subscribers per 1,000 views
assert lo1 < 0 < hi1 and abs(b1) < 0.8, (b1, lo1, hi1)                              # a null factor is not clear
assert 1.0 < res["mean_per_1k"] < 4.5
again = SD.fit(synth(1), F2); assert again == res                                    # seeded
res_neg = SD.fit(synth(2, slope=-2.0), F2)
assert res_neg["coef"]["f0"][2] < 0, res_neg["coef"]["f0"]
print(f"1a planted slope 3.0 recovered as {b0:.2f} ({lo0:.2f} to {hi0:.2f}); null factor {b1:+.2f} ({lo1:.2f} to {hi1:.2f})")
few = SD.fit(synth(3, days=3), F2)
assert few["coef"] == {} and few["n"] == 6
many_factors = {f"g{j}": ["a", "b"] for j in range(9)}
tenrows = [dict({"channel": "main", "day": f"2026-10-{d:02d}", "subs_gained": 3, "views": 2000, "shorts": 5}, **{f"share_g{j}": (d * (j + 3) % 10) / 10 for j in range(9)}) for d in range(10, 30)]
nine = SD.fit(tenrows, many_factors)
assert nine["coef"] == {} and nine["n"] == 20 and nine["need"] >= 28        # 20 days and 8 or 9 factors with a spread: 4 a factor
low_views = [dict(r, views=50) for r in synth(4)]
assert SD.fit(low_views, F2)["n"] == 0                                               # days under 100 views are left out
md = SD.render_md(res, F2, "2026-10-28")
for must in ("# The channel-day subscriber model (advisory only)", "Channel-days used: 80 on main, music", "| f0 (b against a)", "| yes |", "Pacific time"):
    assert must in md, (must, md)
assert "Not enough yet" in SD.render_md(few, F2) and "needs 20 channel-days" in SD.render_md(few, F2)
shutil.rmtree(AN, ignore_errors=True); AN.mkdir(parents=True)
sub_rows = [dict(channel="main", posted=f"2026-10-{10 + i % 8}T12:00:00+00:00", f0="b" if i % 2 else "a", f1="a") for i in range(40)]
daily2 = {"main": [{"day": f"2026-10-{d:02d}", "views": 1000 + 100 * d, "subscribersGained": d % 5, "subscribersLost": 0} for d in range(10, 18)]}
r1 = SD.write(AN, sub_rows, daily2, F2, "2026-10-28")
f = list(csv.DictReader((AN / "subs_daily.csv").open()))
assert len(f) == 8 and f[0]["channel"] == "main" and f[0]["day"] == "2026-10-10" and "share_f0" in f[0] and (AN / "subs_model.md").exists()
empty = SD.build([], {"main": [{"day": "2026-06-30", "views": 0, "subscribersGained": 0, "subscribersLost": 0}, {"day": "2026-07-01", "views": 5}]}, F2)
assert [r["day"] for r in empty] == ["2026-07-01"]                                                         # days with no views and no Shorts are left out
assert r1["n"] == 8
daily3 = {"main": [{"day": f"2026-10-{d:02d}", "views": 2000, "subscribersGained": 1, "subscribersLost": 0} for d in range(16, 20)]}
SD.write(AN, sub_rows, daily3, F2, "2026-10-29")
f = list(csv.DictReader((AN / "subs_daily.csv").open()))
assert [r["day"] for r in f] == [f"2026-10-{d:02d}" for d in range(10, 20)] and f[0]["subs_gained"] == "0" and f[6]["views"] == "2000", [(r["day"], r["views"]) for r in f]
print("1 subs_daily ok")

# ---- 2. analytics ----
curve = {"video": "x", "posted": "2026-09-01T00:00:00+00:00", "points": [[float(h), 10 * h + 5] for h in range(1, 169)] + [[float(h), 1700 + 4 * (h - 168)] for h in range(174, 704, 6)]}
assert A.VIEWS_LATER == (("views_7d", 168), ("views_28d", 672))
assert A.views_at(curve, 168) == 1685 and A.views_at(curve, 72) == 725
v28 = A.views_at(curve, 672)
assert v28 == 1700 + 4 * (672 - 168), v28
assert A.views_at({"video": "x", "points": curve["points"][:200]}, 672) is None            # the curve does not cover it yet: blank, not a guess
assert A.views_at({"video": "x", "points": [[200.0, 5]]}, 168) is None
src = open(REPO_DIR + "/pipeline/analytics.py").read()
assert "for col, h in VIEWS_LATER:" in src and "SD.write(OUT, all_rows" in src and "round_kw()" in src
body = inspect.getsource(A.channel_daily)
assert ".videos()" not in body and ".search()" not in body and ".channels()" not in body and "reports().query" in body      # an Analytics query: no Data API unit
assert 'channel_daily(ya, TODAY)' in src and src.count("videos().list(") == 2                # the two existing statistics reads, nothing added


class Stub:
    def __init__(self, fail_first=False): self.calls, self.fail_first = [], fail_first
    def reports(self): return self
    def query(self, **kw):
        self.calls.append(kw["metrics"])
        if self.fail_first and len(self.calls) == 1: raise RuntimeError("engagedViews unknown")
        class R:
            def execute(s):
                cols = [{"name": n} for n in ["day"] + kw["metrics"].split(",")]
                return {"columnHeaders": cols, "rows": [["2026-10-21", 100, 3, 0], ["2026-10-22", 120, 5, 1]][:2] if "engagedViews" not in kw["metrics"] else [["2026-10-21", 100, 30, 3, 0]]}
        return R()
    def execute(self): return None


st = Stub()
got = A.channel_daily(st, dt.date(2026, 10, 28))
assert got == [{"day": "2026-10-21", "views": 100, "engagedViews": 30, "subscribersGained": 3, "subscribersLost": 0}] and len(st.calls) == 1
st = Stub(fail_first=True)
got = A.channel_daily(st, dt.date(2026, 10, 28))
assert len(st.calls) == 2 and got[0]["subscribersGained"] == 3 and "engagedViews" not in st.calls[1]
class Dead(Stub):
    def query(self, **kw): raise RuntimeError("no")
assert A.channel_daily(Dead(), dt.date(2026, 10, 28)) == []
# the drivers table: feed_pct, p, q
rng = random.Random(4)
dr = []
for i in range(120):
    d = dt.datetime(2026, 10, 12 + i % 10, 8 + i % 9, 0, tzinfo=UTC)
    dr.append({"channel": "main", "posted": d.isoformat(), "posted_day": d.date().isoformat(), "ending": ["loop", "question"][i % 2], "slot_uk": "09:00",
               "rel": math.exp(rng.gauss(0.0, 0.5)), "yt_feed_pct": 60 + (i % 2) * 20, "yt_views": 100})
tb, base = DRV.analyse(dr, {}, "2026-10-30")
t = next(x for x in tb if x["feature"] == "ending" and x["value"] == "question")
assert t["feed_pct"] == 80 and next(x for x in tb if x["feature"] == "ending" and x["value"] == "loop")["feed_pct"] == 60 and "p" in t and "q" in t, t
assert base["yt_feed_pct"] == 70
assert "feed_pct" in src and '"why", "feed_pct", "p", "q"' in src
print("2 analytics ok")

# ---- 3. changes.py ----
assert {"feed_share", "views_7d_median", "subs_day"} <= set(C.METRICS)
assert C.METRICS["feed_share"][1] == "higher" and C.METRICS["subs_day"][1] == "higher"
root = _p.Path(_t.mkdtemp(prefix="qp-ledger-"))
(root / "analytics").mkdir(); (root / "clips").mkdir()
(root / "clips" / "campaigns.json").write_text('{"campaigns": {}}')
C.ROOT = root


def wr(p, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)


TODAY = dt.date(2026, 11, 20)
NOW = dt.datetime(2026, 11, 20, 12, tzinfo=UTC)
sh = []
for day in range(1, 15):                         # 1 to 14 November, two Shorts a day
    for k in range(2):
        before = day <= 7
        sh.append({"short": f"QD-{day}-{k}", "posted": dt.datetime(2026, 11, day, 11, k, tzinfo=UTC).isoformat(), "channel": "main",
                   "yt_feed_pct": "40" if before else "70", "views_7d": "100" if k == 0 else "300", "yt_views": "400", "views_24h": "100", "views_vs_typical": "1.0"})
sh.append({"short": "other", "posted": dt.datetime(2026, 11, 3, 11, tzinfo=UTC).isoformat(), "channel": "music", "yt_feed_pct": "5", "views_7d": "100000"})
wr(root / "analytics" / "shorts.csv", sh)
wr(root / "analytics" / "daily.csv", [{"day": str(dt.date(2026, 10, 20) + dt.timedelta(days=i)), "source": "snapshot", "yt_views_total": str(1000 * i)} for i in range(32)])
subs = [{"channel": "main", "day": str(dt.date(2026, 11, 1) + dt.timedelta(days=i)), "subs_gained": str(2 if i < 7 else 5), "views": "1000"} for i in range(19)]
subs += [{"channel": "music", "day": "2026-11-05", "subs_gained": "99", "views": "1000"}]
wr(root / "analytics" / "subs_daily.csv", subs)
D = C.Data(today=TODAY, now=NOW)
b = (dt.date(2026, 11, 1), dt.date(2026, 11, 8)); a = (dt.date(2026, 11, 8), dt.date(2026, 11, 15))
fs = C.METRICS["feed_share"][3]
vb, nb = fs(D, *b); va, na = fs(D, *a)
assert nb == 14 and na == 14 and abs(vb - 40) < 1e-9 and abs(va - 70) < 1e-9, (vb, va)                # views-weighted: equal mix of 100 and 300 views, the main channel only
sh[0]["yt_feed_pct"], sh[1]["yt_feed_pct"] = "100", "0"                                              # weighting by 7-day views: the 300-view Short counts three times
wr(root / "analytics" / "shorts.csv", sh)
vb2, _ = C.METRICS["feed_share"][3](C.Data(today=TODAY, now=NOW), *b)
assert abs(vb2 - 106000 / 2800) < 1e-9, vb2                                                           # (100 x 100 + 0 x 300 + 40 x 2,400) / 2,800
v7, n7 = C.METRICS["views_7d_median"][3](D, *b)
assert v7 == 200.0 and n7 == 14, (v7, n7)                                                              # the median of 100 and 300
sd = C.METRICS["subs_day"][3]
vs, ns = sd(D, *b); vs2, ns2 = sd(D, dt.date(2026, 11, 15), dt.date(2026, 11, 22))
assert vs == 2 and ns == 7 and vs2 == 5 and ns2 == 3, (vs, ns, vs2, ns2)                              # the main channel's days only; the newest two days (18 and 19 November) are still being counted
r = C.add("data", "false-winner control", "fewer false winners", "feed_share", "subs_day;views_7d_median", date="2026-11-08", rows=[])
assert r["target"] == "feed_share" and r["guardrails"].split(";")[:2] == ["subs_day", "views_7d_median"]      # changes.add may append its own guardrails
for name in ("feed_share", "views_7d_median", "subs_day"):
    try: C.add("data", "x", "y", name, "", date="2026-11-08", rows=[])
    except ValueError: raise AssertionError(name)
assert C.fmt("feed_share", 41.4) == "41%" and C.fmt("subs_day", 3.46) == "3.5" and C.fmt("views_7d_median", 1234.0) == "1,234"
print("3 ledger metrics ok")

# ---- 4. no dashes ----
em, en = chr(0x2014), chr(0x2013)
for fn in ("pipeline/subs_daily.py", "pipeline/changes.py", "pipeline/analytics.py", "tests/test_subs_daily.py"):
    txt = open(REPO_DIR + "/" + fn).read()
    assert em not in txt and en not in txt, fn
assert em not in md and en not in md and em not in (AN / "subs_model.md").read_text()
print("4 no dashes ok")
print("subs_daily ok")
