"""Offline tests of the joint model (28 October, pipeline/joint.py) and its two uses:
1. the model recovers a planted main effect and a planted category interaction (known truth), puts nothing else clear, and is
   repeatable (seeded bootstrap); a null dataset gives no clear interaction after the luck check; the opening factors are fitted
   on the engaged share too; controls (channel, topic heat, weekday, exploration) are reported;
2. the files: joint.csv has the columns the readers need, joint.md lists the top effects and the clear interactions;
3. the veto: drivers.round_verdicts withholds a winner whose arm the joint interval puts wholly on the losing side, and only that
   (load_joint reads main rows only; no reading, no veto);
4. evolve's "joint" source: a clear interaction (interval above no difference, q under fdr_q, 15+ Shorts, a factor with a writing
   instruction and not under contest) opens one category-scoped writing instruction; at most one live; never twice; a scoped
   contest is judged on its category's Shorts only; it is adopted and goes on trial like any gene;
5. no em or en dash in what this adds."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import collections, csv, datetime as dt, json, math, os, random, shutil, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import numpy as np
import joint as J
import drivers as DRV
import evolve as EV

EV.ROOT = SCRATCH
AN = SCRATCH / "analytics"
CATS = ["Music", "Film", "Gaming", "Sport", "Tech"]
FACTORS = {"ending": ["loop", "question"], "hook_type": ["statement", "number"], "title_search": ["search phrase", "curiosity"],
           "first_frame": ["cover", "photo"], "angles": ["shown", "hidden"], "franchise": ["named", "plain"],
           "title_emoji": ["emoji", "none"], "replies": ["on", "off"]}


def make(seed, n=700, plant=None, inter=None, sd=0.8, engaged=False):
    """Shorts over 14 UK days on 2 channels; log rel = noise + plant[(factor, arm)] + inter[(category, factor, arm)]."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        d = dt.datetime(2026, 10, 1 + i % 14, 6 + (i * 5) % 15, 0, tzinfo=dt.timezone.utc)
        r = {"channel": "main" if i % 4 else "music", "posted": d.isoformat(), "posted_day": d.date().isoformat(),
             "category": rng.choice(CATS), "explore": "yes" if rng.random() < 0.1 else "no"}
        mu = 0.0
        for f, (a, b) in FACTORS.items():
            r[f] = rng.choice([a, b])
            mu += (plant or {}).get((f, r[f]), 0.0) + (inter or {}).get((r["category"], f, r[f]), 0.0)
        r["arm_hook_type"] = r["hook_type"]
        r["rel"] = math.exp(rng.gauss(mu, sd))
        if engaged:
            share = 0.3 * math.exp(rng.gauss((plant or {}).get(("hook_type", r["hook_type"]), 0.0) * 0.3, 0.1))
            r.update(yt_an_views=300, yt_engaged_views=round(300 * min(0.95, share)))
        rows.append(r)
    return rows


def pick(res, factor, level, outcome="views"):
    return next(r for r in res["rows"] if r["factor"] == factor and r["level"] == level and r["outcome"] == outcome)


# ---- 1. the planted effects ----
PLANT = {("ending", "loop"): 0.5}                              # ending=loop 1.65x the question ending (0.5 log)
INTER = {("Music", "hook_type", "number"): 0.9}                # the number hook gains 0.9 log in Music only (2.46x)
rows = make(21, n=900, plant=PLANT, inter=INTER, engaged=True)
res = J.analyse(rows, FACTORS, opening={"hook_type", "first_frame"})
loop, ques = pick(res, "ending", "loop"), pick(res, "ending", "question")
assert 1.4 < loop["effect"] < 1.9 and loop["low"] > 1.0, loop                              # the truth is 1.65x
assert abs(loop["effect"] * ques["effect"] - 1.0) < 0.01 and ques["high"] < 1.0, (loop, ques)
cell = pick(res, "category x hook_type", "Music: number")
assert cell["kind"] == "interaction" and cell["low"] > 1.0 and cell["effect"] > 1.3 and cell["q"] <= 0.10 and cell["n"] > 20, cell       # truth 2.46x; the ridge shrinks it
assert pick(res, "category x hook_type", "Music: statement")["high"] < 1.0
clear_ints = [r for r in res["rows"] if r["kind"] == "interaction" and r["outcome"] == "views" and r["q"] <= 0.10]
assert {(r["factor"], r["level"]) for r in clear_ints} == {("category x hook_type", "Music: number"), ("category x hook_type", "Music: statement")}, clear_ints
clear_main = [r for r in res["rows"] if r["kind"] == "main" and r["outcome"] == "views" and (r["low"] > 1.0 or r["high"] < 1.0) and r["q"] <= 0.10]
assert {r["factor"] for r in clear_main} <= {"ending", "hook_type"}, clear_main           # nothing else is called (hook_type: the Music gain is a fifth of the rows, a real 0.12 on average)
print(f"1a planted ending effect 1.65x recovered as {loop['effect']}x ({loop['low']} to {loop['high']}); planted Music x number interaction 2.46x as {cell['effect']}x ({cell['low']} to {cell['high']}, q {cell['q']})")
again = J.analyse(rows, FACTORS, opening={"hook_type", "first_frame"})
assert again["rows"] == res["rows"]                                                       # seeded: a run repeats
other = J.analyse(rows, FACTORS, opening={"hook_type", "first_frame"}, seed=99)
assert other["rows"] != res["rows"] and abs(pick(other, "ending", "loop")["effect"] - loop["effect"]) < 0.02       # another seed moves the interval, not the fit
ctrl = {(r["factor"], r["level"]) for r in res["rows"] if r["kind"] == "control"}
assert ("control", "exploration Short") in ctrl and ("channel", "main") in ctrl and ("channel", "music") in ctrl, ctrl
assert all(r["factor"] in ("channel", "control") for r in res["rows"] if r["kind"] == "control")
# null data: across 10 seeded datasets the luck check leaves (almost) nothing; the plain 90% interval would call many cells
n_int = n_main = hit_int = hit_main = plain = 0
for seed in range(30, 40):
    nul = J.analyse(make(seed), FACTORS)
    ints = [r for r in nul["rows"] if r["kind"] == "interaction" and r["outcome"] == "views"]
    mains = [r for r in nul["rows"] if r["kind"] == "main" and r["outcome"] == "views"]
    plain += sum(1 for r in ints if r["low"] > 1.0 or r["high"] < 1.0) // 2
    hit_int += any(r["q"] <= 0.10 for r in ints); hit_main += any(r["q"] <= 0.10 for r in mains)
    n_int += len(ints) // 2
assert plain >= 20, plain                                                                  # about 10% of the cells clear a 90% interval by luck
assert hit_int <= 3 and hit_main <= 4, (hit_int, hit_main)                                 # BH at 0.10: a false call in about 1 dataset in 10 (60 seeded datasets: 6 and 13, the z test of a bootstrap spread is a little liberal)
print(f"1b null data: {n_int} interaction cells over 10 datasets, {plain} clear a plain 90% interval, {hit_int} datasets with one past the luck check")
# the opening factors on the engaged share: a planted engaged effect
rows_e = make(23, plant={("hook_type", "number"): 1.2}, engaged=True)               # engaged share moves 0.3 x 1.2 log = 0.36
re_ = J.analyse(rows_e, FACTORS, opening={"hook_type", "first_frame"})
e_num = pick(re_, "hook_type", "number", "engaged")
assert e_num["low"] > 1.0 and 1.15 < e_num["effect"] < 1.6, e_num                          # the share's truth is 1.43x
assert not any(r["factor"] == "ending" and r["outcome"] == "engaged" for r in re_["rows"])         # only the opening factors are fitted twice
assert {r["outcome"] for r in re_["rows"] if r["factor"] == "first_frame"} == {"views", "engaged"}
# controls: topic heat is a column when it varies
rh = make(24, plant={("ending", "loop"): 0.3})
rng = random.Random(1)
for r in rh: r["heat"] = round(rng.uniform(0, 2), 2); r["rel"] *= math.exp(0.4 * (r["heat"] - 1))
rh_res = J.analyse(rh, FACTORS)
hc = next(r for r in rh_res["rows"] if r["level"].startswith("topic heat"))
assert 1.2 < hc["effect"] < 1.7, hc                                                        # exp(0.4) = 1.49 per heat point
print("1 the joint model ok")

# ---- 2. the files ----
fresh = lambda: (shutil.rmtree(AN, ignore_errors=True), AN.mkdir(parents=True))
fresh()
J.write(AN, res, "2026-10-28")
cs = list(csv.DictReader((AN / "joint.csv").open()))
assert list(cs[0].keys()) == ["factor", "level", "effect", "low", "high", "n", "outcome", "kind", "p", "q"], cs[0].keys()
md = (AN / "joint.md").read_text()
for must in ("# The joint model", "## Top main effects", "| ending | loop | views |", "## Interactions whose interval clears no difference",
             "Music: number on hook_type (views)", "passes the luck check", "## Controls", "residual spread"):
    assert must in md, (must, md[:1500])
loaded = DRV.load_joint(AN / "joint.csv")
assert loaded[("ending", "loop", "views")][0] == loop["effect"] and ("category x hook_type", "Music: number", "views") not in loaded and all(k[2] in ("views", "engaged") for k in loaded)
assert DRV.load_joint(AN / "nope.csv") == {}
print("2 the files ok")

# ---- 3. the veto ----
def rv_rows(seed, plant):
    rng = random.Random(seed)
    out = []
    for i in range(240):
        d = dt.datetime(2026, 10, 12 + i % 12, 6 + (i * 7) % 14, 0, tzinfo=dt.timezone.utc)
        r = {"channel": "main", "posted": d.isoformat(), "posted_day": d.date().isoformat(), "f0": rng.choice(["a", "b"])}
        r["rel"] = math.exp(rng.gauss(plant if r["f0"] == "b" else 0.0, 0.6))
        out.append(r)
    return out


F0 = {"f0": ["a", "b"]}
base = DRV.round_verdicts(rv_rows(1, 0.7), F0, "2026-10-01", 5000, "t")[0]
assert base["verdict"] == "winner" and base["winner"] == "b", base
agree = DRV.round_verdicts(rv_rows(1, 0.7), F0, "2026-10-01", 5000, "t", joint={("f0", "b", "views"): (1.3, 1.05, 1.6)})[0]
assert agree["verdict"] == "winner"                                                        # the joint model agrees: nothing changes
against = DRV.round_verdicts(rv_rows(1, 0.7), F0, "2026-10-01", 5000, "t", joint={("f0", "b", "views"): (0.7, 0.55, 0.9)})[0]
assert against["verdict"] == "running" and against["winner"] == "" and "joint model" in against["why"], against
straddle = DRV.round_verdicts(rv_rows(1, 0.7), F0, "2026-10-01", 5000, "t", joint={("f0", "b", "views"): (0.9, 0.7, 1.2)})[0]
assert straddle["verdict"] == "winner"                                                     # an interval across no difference does not veto
other_arm = DRV.round_verdicts(rv_rows(1, 0.7), F0, "2026-10-01", 5000, "t", joint={("f0", "a", "views"): (0.7, 0.5, 0.9)})[0]
assert other_arm["verdict"] == "winner"                                                    # it is the winning arm's interval that counts
engaged_only = DRV.round_verdicts(rv_rows(1, 0.7), F0, "2026-10-01", 5000, "t", joint={("f0", "b", "engaged"): (0.7, 0.5, 0.9)})[0]
assert engaged_only["verdict"] == "winner"                                                 # a reading on another outcome does not count
assert DRV.joint_against({}, "f0", "b", "views") is False and DRV.joint_against(None, "f0", "b", "views") is False
print("3 the veto ok")

# ---- 4. evolve's joint source ----
import writer as W
TEXTS = W.TESTS
EVC = {"on": True, "width": 5, "max_changes_per_run": 2, "max_genes": 3, "max_new_genes_per_run": 0, "max_adopted": 6, "retest_days": 28,
       "neighbour_factors": [], "focus": []}
ROUND = {"name": "round 1", "start": "2026-10-25", "per_arm": 70, "factors": {"first_frame": ["cover", "photo"]}}
CFG = {"evolve": EVC, "test_round": ROUND}
TODAY = "2026-11-10"
JFIELDS = ["factor", "level", "effect", "low", "high", "n", "outcome", "kind", "p", "q"]


def joint_file(*cells):
    with (AN / "joint.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=JFIELDS); w.writeheader()
        for cat, f, arm, low, q, n in cells:
            w.writerow({"factor": f"category x {f}", "level": f"{cat}: {arm}", "effect": round(low + 0.2, 2), "low": low, "high": low + 0.4, "n": n,
                        "outcome": "views", "kind": "interaction", "p": q / 5, "q": q})


def go(cfg=CFG, tests=None, **kw):
    tests = tests or {f: list(W.arms(f)) for f in ("ending", "first_frame", "hook_type", "length", "title_search")}
    return EV.run_once(cfg, TODAY, tests, TEXTS, set(), **kw)


fresh()
joint_file(("Music", "ending", "loop", 1.12, 0.03, 40), ("Film", "ending", "question", 1.20, 0.08, 30),       # two good cells
           ("Gaming", "ending", "loop", 1.30, 0.40, 40),            # q over the level: luck
           ("Sport", "ending", "loop", 0.95, 0.01, 40),             # interval includes no difference
           ("Tech", "ending", "loop", 1.40, 0.01, 9),               # too few Shorts
           ("Music", "first_frame", "cover", 1.5, 0.01, 40),        # first_frame is under contest
           ("Music", "angles", "shown", 1.5, 0.01, 40))             # angles has no writing instruction
pre = EV.Run(EV.load_state(CFG), EV.settings(CFG), TODAY, {"ending": list(W.arms("ending"))}, TEXTS)
cands = EV.joint_candidates(pre)
run = go()
assert [c["key"] for c in cands] == ["Film|ending|question", "Music|ending|loop"], [c["key"] for c in cands]          # best (highest low) first
assert cands[1]["text"].startswith("For Music Shorts, end with a line that flows straight back") and EV.check_gene(cands[1]["text"]) == ""
launched = [r for r in run.log if r["action"] == "open"]
assert len(launched) == 1 and launched[0]["source"] == "joint", run.log                    # one live at a time, the best first
gid = launched[0]["factor"][len("gene:"):]
g = run.st["genes"][gid]
assert g["kind"] == "joint" and g["scope"] == {"category": "Film"} and g["by"] == "joint model" and g["a_text"] == "" and g["joint_key"] == "Film|ending|question"
assert g["text"].startswith("For Film Shorts, end with a short question") and run.st["round"]["origin"][f"gene:{gid}"] == "joint"
assert run.st["sources"]["joint"] == {"contests": 0, "wins": 0}
(AN / "evolve.json").write_text(EV.dump(run.st))
assert EV.round_scopes(CFG) == {f"gene:{gid}": "Film"} and EV.round_scopes({"evolve": {"on": False}}) == {}
run2 = go()
assert not [r for r in run2.log if r["action"] == "open" and r["source"] == "joint"], run2.log                     # capped at one live joint contest
assert [c["key"] for c in EV.joint_candidates(run2)] == ["Music|ending|loop"]                # the one in the round is no longer a candidate
# a scoped contest is judged on its category's Shorts only
sc_rows = []
rng = random.Random(5)
for i in range(300):
    d = dt.datetime(2026, 11, 1 + i % 8, 8 + i % 10, 0, tzinfo=dt.timezone.utc)
    cat = CATS[i % 5]
    arm = rng.choice(["a", "b"])
    sc_rows.append({"channel": "main", "posted": d.isoformat(), "posted_day": d.date().isoformat(), "category": cat, "genes": f"gene:{gid}={arm}",
                    "rel": math.exp(rng.gauss(0.8 if (arm == "b" and cat == "Film") else 0.0, 0.6))})
f_all = DRV.round_verdicts(sc_rows, {f"gene:{gid}": ["a", "b"]}, "2026-10-25", 5000, "t")[0]
f_sc = DRV.round_verdicts(sc_rows, {f"gene:{gid}": ["a", "b"]}, "2026-10-25", 5000, "t", scopes={f"gene:{gid}": "Film"})[0]
film = [r for r in sc_rows if r["category"] == "Film"]
assert f_sc["n_a"] + f_sc["n_b"] == len(film) == 60 and f_all["n_a"] + f_all["n_b"] == 300, (f_sc, f_all)
assert f_sc["verdict"] == "winner" and f_sc["winner"] == "b" and 1.8 < f_sc["effect"] < 2.9, f_sc          # diluted to nothing across all categories
assert f_all["verdict"] != "winner" or f_all["effect"] < f_sc["effect"]
# it is adopted and goes on trial like any gene; a rejected one is never proposed again
with (AN / "round.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=DRV.ROUND_FIELDS); w.writeheader()
    w.writerow({"round": "round 1", "factor": f"gene:{gid}", "arm_a": "a", "arm_b": "b", "verdict": "winner", "winner": "b", "effect": 1.9, "low": 1.2, "high": 2.8, "n_a": 30, "n_b": 30})
run3 = go()
assert run3.st["genes"][gid]["status"] == "adopted" and run3.st["confirming"][f"gene:{gid}"]["arm"] == "b" and run3.st["sources"]["joint"] == {"contests": 1, "wins": 1}
assert run3.st["round"]["factors"][f"gene:{gid}"] == ["a", "b"]                            # the trial keeps the scoped contest, so it stays judged on Film only
st = run3.st
st["genes"][gid]["status"] = "rejected"; st["confirming"] = {}; st["round"]["factors"].pop(f"gene:{gid}"); st["adopted"] = {}
(AN / "evolve.json").write_text(EV.dump(st))
os.remove(AN / "round.csv")
assert "Film|ending|question" not in [c["key"] for c in EV.joint_candidates(go())]            # tried once, never again
# a mutation or retest of a scoped gene stays in its category
run4 = go(); r4 = EV.make_gene(run4, "retest", parent=gid)
assert run4.st["genes"][r4]["scope"] == {"category": "Film"}
# no joint.csv, or off: nothing to propose
os.remove(AN / "joint.csv"); assert EV.joint_candidates(go()) == []
print("4 evolve's joint source ok")

# ---- 5. no dashes ----
em, en = chr(0x2014), chr(0x2013)
for f in ("pipeline/joint.py", "pipeline/evolve.py", "pipeline/subs_daily.py", "tests/test_joint.py", ".github/workflows/analytics.yml"):
    txt = open(REPO_DIR + "/" + f).read()
    assert em not in txt and en not in txt, f
assert em not in md and en not in md
print("5 no dashes ok")
print("joint ok")
