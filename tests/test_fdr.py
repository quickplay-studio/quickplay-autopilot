"""Offline tests of the false-winner control (28 October, pipeline/fdr.py and its use in pipeline/drivers.py):
1. p-values: the t test behind every interval (fdr.t_p) matches reference values; BH adjusted values are monotone, keep order and
   skip None; settings read config analysis.fdr_q;
2. the luck check on a drivers table: a push or cut back with q over fdr_q becomes an early sign with the reason, one under it
   stays, p and q are written;
3. drivers.analyse on synthetic Shorts with a known effect: the planted choice passes, a weaker lucky one is held back, and with
   the check off (fdr_q 1.01) the lucky one would have been called;
4. round_verdicts with 20 null factors over 15 seeded passes: the plain 90% rule would call many winners, the luck check
   removes most of them ("running" with luck "yes"); a planted effect still wins with its p and q written; fdr_q is honoured;
5. channel_table carries p and q, and an exception needs the check too;
6. no em or en dash in the files this adds or changes."""
import pathlib as _p
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
import datetime as dt, json, math, os, random, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import drivers as DRV
import fdr as FDR

CFG_OFF = 1.01      # fdr_q above 1: the luck check cannot withhold anything (the old rule)

# ---- 1. p-values and Benjamini-Hochberg ----
for t, df, ref in [(2.228, 10, 0.05001177), (1.0, 1, 0.5), (12, 3, 0.001245016), (0.5, 30, 0.62072301), (2.5, 120, 0.01376953), (3.2, 7, 0.01506581)]:
    got = FDR.t_p(t, df)
    assert abs(got - ref) < 1e-6, (t, df, got, ref)
assert FDR.t_p(0, 5) == 1.0 and FDR.t_p("x", 5) is None and FDR.t_p(1, 0) is None
assert abs(FDR.normal_p(1.645) - 0.0999) < 1e-3
# mean_p is the one-sample t test drivers.interval's interval is made from: the 90% interval excludes 0 exactly when p < 0.10
rng = random.Random(3)
for _ in range(200):
    logs = [rng.gauss(rng.uniform(-0.6, 0.6), 0.8) for _ in range(rng.randint(6, 40))]
    lo, hi = DRV.interval(logs)
    clear = lo > 1.0 or hi < 1.0
    p = FDR.mean_p(logs)
    if abs(p - 0.10) > 0.012: assert clear == (p < 0.10), (p, lo, hi)      # t90() is a coarse table, so only the margin around 0.10 is excused
ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216, None, 0.222]
qs = FDR.bh(ps)
assert qs[10] is None and all(q is not None for i, q in enumerate(qs) if i != 10)
ordered = [qs[i] for i in sorted((i for i in range(len(ps)) if ps[i] is not None), key=lambda i: ps[i])]
assert all(a <= b + 1e-12 for a, b in zip(ordered, ordered[1:])), ordered              # monotone in p
assert all(qs[i] >= ps[i] - 1e-12 and qs[i] <= 1.0 for i in range(len(ps)) if ps[i] is not None)
assert abs(qs[0] - 0.011) < 1e-9 and abs(qs[1] - 0.044) < 1e-9, qs                      # 0.001*11/1 and 0.008*11/2 (11 values with a p)
assert FDR.bh([]) == [] and FDR.bh([None]) == [None] and FDR.bh([0.5]) == [0.5]
assert FDR.settings({})["fdr_q"] == 0.10 and FDR.settings({"analysis": {"fdr_q": 0.2}})["fdr_q"] == 0.2
assert FDR.settings({"analysis": {"confirm_n": 0, "confirm_share": 0.3}}) == {"fdr_q": 0.1, "confirm_share": 0.3, "confirm_n": 0}
assert json.loads(open("config.json").read())["analysis"]["fdr_q"] == 0.1
print("1 p-values and Benjamini-Hochberg ok")

# ---- 2. the luck check on a table ----
table = [{"feature": "x", "value": str(i), "verdict": v, "why": "", "p": p, "q": None}
         for i, (v, p) in enumerate([("push", 0.0004), ("push", 0.03), ("cut back", 0.05), ("early sign", 0.5), ("about typical", None), ("push", 0.06)])]
table += [{"feature": "y", "value": str(i), "verdict": "about typical", "why": "", "p": 0.4 + 0.01 * i, "q": None} for i in range(14)]
DRV.luck_check(table, 0.10)
by = {(t["feature"], t["value"]): t for t in table}
assert by[("x", "0")]["verdict"] == "push" and by[("x", "0")]["q"] < 0.10                 # 0.0004 * 19 / 1
assert by[("x", "1")]["verdict"] == "early sign" and "luck check" in by[("x", "1")]["why"] and by[("x", "1")]["q"] > 0.10
assert by[("x", "2")]["verdict"] == "early sign" and by[("x", "5")]["verdict"] == "early sign"
assert by[("x", "4")]["p"] == "" and by[("x", "4")]["q"] == ""                            # no p, no q
assert by[("x", "0")]["p"] == 0.0004 and isinstance(by[("x", "0")]["q"], float)
t2 = [{"verdict": "push", "why": "", "p": 0.03, "q": None}] + [{"verdict": "about typical", "why": "", "p": 0.9, "q": None}] * 3
DRV.luck_check(t2, 0.5); assert t2[0]["verdict"] == "push"                                  # q = 0.12, under a looser level
print("2 luck check on a table ok")


# ---- synthetic Shorts ----
def make(seed, n=300, features=None, plant=None, days=12, factors=0, mu_sd=0.8):
    """Shorts over `days` UK days, every one with rel = exp(noise + planted effect). features: {column: [values]} drawn evenly
    and independently; plant: {(column, value): log effect}; factors: that many two-arm round factors f0..f(k-1) (arms a, b)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        d = dt.datetime(2026, 10, 12 + i % days, 6 + (i * 7) % 14, 0, tzinfo=dt.timezone.utc)
        r = {"channel": "main" if i % 3 else "music", "posted": d.isoformat(), "posted_day": d.date().isoformat(), "slot_uk": f"{(d.hour + 1) % 24:02d}:00"}
        mu = 0.0
        for col, vals in (features or {}).items():
            r[col] = rng.choice(vals)
            mu += (plant or {}).get((col, r[col]), 0.0)
        for j in range(factors):
            r[f"f{j}"] = rng.choice(["a", "b"])
            mu += (plant or {}).get((f"f{j}", r[f"f{j}"]), 0.0)
        r["rel"] = math.exp(rng.gauss(mu, mu_sd))
        rows.append(r)
    return rows


# ---- 3. drivers.analyse: a planted choice passes, lucky ones are held back ----
feats = {"ending": ["loop", "question"], "title_search": ["search phrase", "curiosity"], "first_frame": ["cover", "photo"],
         "angles": ["shown", "hidden"], "franchise": ["named", "plain"], "kind": ["news", "evergreen", "fiction"],
         "source": ["Google Trends", "Wikipedia", "Reddit", "YouTube"], "category": ["Music", "Film", "Gaming", "Sport", "Tech"]}
rows = make(5, n=400, features=feats, plant={("ending", "loop"): 0.55, ("ending", "question"): -0.55})
t_on, _ = DRV.analyse(rows, {}, "2026-10-30", fdr_q=0.10)
t_off, _ = DRV.analyse(rows, {}, "2026-10-30", fdr_q=CFG_OFF)
calls = lambda t: {(x["feature"], x["value"]) for x in t if x["verdict"] in ("push", "cut back")}
assert ("ending", "loop") in calls(t_on) and ("ending", "question") in calls(t_on), calls(t_on)
row = next(x for x in t_on if (x["feature"], x["value"]) == ("ending", "loop"))
assert row["p"] != "" and row["p"] < 0.001 and row["q"] != "" and row["q"] < 0.10 and row["verdict"] == "push", row
assert all("p" in x and "q" in x for x in t_on)
# across many null datasets the plain rule calls some pushes by luck and the check removes most of them
naive = bh_calls = 0
for seed in range(40):
    nul = make(100 + seed, n=150, features=feats, mu_sd=1.1)
    a, _ = DRV.analyse(nul, {}, "2026-10-30", fdr_q=CFG_OFF); b, _ = DRV.analyse(nul, {}, "2026-10-30", fdr_q=0.10)
    naive += len(calls(a)); bh_calls += len(calls(b))
    assert calls(b) <= calls(a)
assert naive >= 12, naive
assert bh_calls <= max(2, 0.25 * naive), (naive, bh_calls)
print(f"3 analyse ok ({naive} lucky calls by the plain rule across 40 null datasets, {bh_calls} after the luck check)")

# ---- 4. round_verdicts: 20 null factors ----
naive = held = bh_won = 0
for seed in range(15):
    rows = make(200 + seed, n=240, factors=20)
    fac = {f"f{j}": ["a", "b"] for j in range(20)}
    out = DRV.round_verdicts(rows, fac, "2026-10-01", 5000, "t", fdr_q=0.10)
    w = [x for x in out if x["verdict"] == "winner"]
    lucky = [x for x in out if x["luck"] == "yes"]
    naive += len(w) + len(lucky); held += len(lucky); bh_won += len(w)
    for x in lucky:
        assert x["verdict"] == "running" and x["winner"] == "" and "luck check" in x["why"] and x["q"] > 0.10, x
    for x in out: assert x["p"] != "" and x["q"] != "" and x["q"] >= x["p"] - 1e-3
    off = DRV.round_verdicts(rows, fac, "2026-10-01", 5000, "t", fdr_q=CFG_OFF)
    assert sum(x["verdict"] == "winner" for x in off) == len(w) + len(lucky)               # the old rule: every candidate wins
assert naive >= 8, naive
assert held >= 0.8 * naive and bh_won <= max(1, 0.2 * naive), (naive, held, bh_won)       # the check rejects most of the lucky winners
# a planted effect still wins, with its p and q written
rows = make(7, n=240, factors=6, plant={("f0", "b"): 0.7})
fac = {f"f{j}": ["a", "b"] for j in range(6)}
out = {x["factor"]: x for x in DRV.round_verdicts(rows, fac, "2026-10-01", 5000, "t", fdr_q=0.10)}
assert out["f0"]["verdict"] == "winner" and out["f0"]["winner"] == "b" and out["f0"]["p"] < 0.001 and out["f0"]["q"] <= 0.10, out["f0"]
assert 1.6 < out["f0"]["effect"] < 2.6 and out["f0"]["luck"] == ""                         # exp(0.7) = 2.0
# a middling effect: a winner on the plain rule only when the luck check is off; fdr_q is honoured
for seed in range(30):
    rows = make(300 + seed, n=240, factors=20, plant={("f0", "b"): 0.36})
    fac = {f"f{j}": ["a", "b"] for j in range(20)}
    a = {x["factor"]: x for x in DRV.round_verdicts(rows, fac, "2026-10-01", 5000, "t", fdr_q=CFG_OFF)}
    b = {x["factor"]: x for x in DRV.round_verdicts(rows, fac, "2026-10-01", 5000, "t", fdr_q=0.10)}
    assert b["f0"]["verdict"] != "winner" or a["f0"]["verdict"] == "winner"
    if a["f0"]["verdict"] == "winner" and b["f0"]["verdict"] != "winner":
        assert b["f0"]["luck"] == "yes" and b["f0"]["verdict"] == "running" and float(b["f0"]["q"]) > 0.10
        break
else: raise AssertionError("no seed held back a middling winner")
print(f"4 round verdicts ok ({naive} candidate winners among 15 x 20 null factors, {held} held back, {bh_won} won)")

# ---- 5. channel_table ----
rows = make(9, n=400, features={"ending": ["loop", "question"], "category": ["Music", "Film", "Gaming"]},
            plant={("ending", "loop"): 0.6, ("ending", "question"): -0.6})
table, _ = DRV.analyse(rows, {}, "2026-10-30", fdr_q=0.10)
ch = DRV.channel_table(rows, table, fdr_q=0.10)
assert ch and all("p" in x and "q" in x for x in ch) and "p" in DRV.CHANNEL_FIELDS and "q" in DRV.CHANNEL_FIELDS
assert any(x["feature"] == "ending" and x["verdict"] == "push" for x in ch)
nul = make(11, n=200, features={"ending": ["loop", "question"], "category": ["Music", "Film", "Gaming"], "kind": ["news", "fiction"]}, mu_sd=1.2)
tn, _ = DRV.analyse(nul, {}, "2026-10-30", fdr_q=0.10)
cn = DRV.channel_table(nul, tn, fdr_q=0.10)
assert all(not x["exception"] or x["verdict"] in ("push", "cut back") for x in cn)
print("5 channel table ok")

# ---- 6. no dashes ----
em, en = chr(0x2014), chr(0x2013)
for f in ("pipeline/fdr.py", "pipeline/drivers.py", "tests/test_fdr.py"):
    txt = open(f).read()
    assert em not in txt and en not in txt, f
print("6 no dashes ok")
print("fdr ok")
