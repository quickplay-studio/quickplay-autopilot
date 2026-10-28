"""Offline tests of re-testing before lock-in (28 October, pipeline/evolve.py and drivers.round_verdicts):
1. a winner starts a trial: the new champion (or an adopted gene) stays in the round with a fresh start, a "confirming" record
   (arm, previous choice, share, n) and a ledger row; the stale "winner" row of the next day settles nothing; confirm_n 0 locks in at once;
2. the draw: the previous choice keeps analysis.confirm_share of the Shorts (EV.draw, writer.test_plan), every other contest stays 50/50;
3. round_verdicts judges a trial "confirming" until confirm_n a side, then "confirmed" (not worse beyond the even band: 14%, 10% on
   the engaged share) or "reverted"; a trial is no discovery, so it stays out of the Benjamini-Hochberg family;
4. settle: confirmed locks in (leaves the round, the retest clock restarts); reverted brings back the previous champion (or none)
   and writes a decisions.csv row; a gene is dropped (a mutation's parent returns); a row from before the trial is ignored;
5. the record: evolve.md shows the trial; main() end to end with files; no dashes in what this adds."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import collections, csv, datetime as dt, json, math, os, random, shutil, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import evolve as EV
import drivers as DRV

EV.ROOT = SCRATCH
AN = SCRATCH / "analytics"
EVC = {"on": True, "width": 3, "max_changes_per_run": 3, "max_genes": 3, "max_new_genes_per_run": 1, "max_adopted": 6,
       "retest_days": 28, "neighbour_factors": ["hook_type"]}
ROUND = {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
         "factors": {"hook_type": ["statement", "number"], "ending": ["loop", "question"], "first_frame": ["cover", "photo"]}}
CFG = {"evolve": EVC, "test_round": ROUND}             # the analysis defaults: share 0.2, 20 a side, q 0.10
CFG0 = {**CFG, "analysis": {"confirm_n": 0}}
TESTS = {"hook_type": ["statement", "question", "number", "superlative", "twist"], "ending": ["loop", "question"], "first_frame": ["cover", "photo"]}
TODAY = "2026-11-10"


def fresh():
    shutil.rmtree(AN, ignore_errors=True); AN.mkdir(parents=True)


def put_state(st): (AN / "evolve.json").write_text(EV.dump(st))
def commit(run): put_state(run.st)
def go(cfg=CFG, today=TODAY, **kw): return EV.run_once(cfg, today, kw.pop("tests", TESTS), {}, set(), **kw)
def actions(run, *names): return [r for r in run.log if r["action"] in names]


def results(*rows):
    with (AN / "round.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DRV.ROUND_FIELDS); w.writeheader()
        for r in rows: w.writerow({"round": "round 1", "n_a": 30, "n_b": 30, **r})


def verdict(f, a, b, v, winner="", effect=1.0, low=0.8, high=1.2, **kw):
    return {"factor": f, "arm_a": a, "arm_b": b, "verdict": v, "winner": winner, "effect": effect, "low": low, "high": high, **kw}


def contest(st, f, arms, origin, start):
    st["round"]["factors"][f], st["round"]["starts"][f], st["round"]["origin"][f] = arms, start, origin


def gene(gid, text, kind="new", status="live", parent="", lineage=None, a_text="", **kw):
    return {"label": text[:20], "text": text, "a_text": a_text, "b_text": text, "parent": parent, "lineage": lineage or gid,
            "born": "2026-11-01", "status": status, "effect": "", "kind": kind, "why": "", **kw}


# ---- 1. a winner starts a trial ----
fresh()
results(verdict("hook_type", "statement", "number", "winner", "number", 1.6, 1.2, 2.0))
run = go()
tr = run.st["confirming"]["hook_type"]
assert run.st["champions"] == {"hook_type": "number"}
assert (tr["arm"], tr["prev"], tr["n"], tr["share"], tr["since"], tr["prev_champion"]) == ("number", "statement", 20, 0.2, TODAY, None), tr
assert run.st["round"]["factors"]["hook_type"] == ["statement", "number"] and run.st["round"]["starts"]["hook_type"] == TODAY
assert run.st["round"]["origin"]["hook_type"] == "confirm" and len(run.st["round"]["factors"]) == 3      # no neighbour contest took its place
assert actions(run, "champion") and "confirming on 80% of Shorts until 20 a side" in actions(run, "champion")[0]["note"]
assert len(run.ledger) == 1 and "champion" in run.ledger[0]["change"]
assert run.st["history"][-1]["verdict"] == "winner" and run.st["history"][-1]["retest_after"]
commit(run)
assert EV.confirming(CFG) == run.st["confirming"] and EV.confirming({"evolve": {"on": False}}) == {}
run2 = go()                                         # the same stale "winner" row the next day: nothing settles
assert run2.st["confirming"] == run.st["confirming"] and not actions(run2, "champion", "defended", "lock-in", "revert")
assert run2.st["round"]["starts"]["hook_type"] == TODAY
# a champion replaced: the previous champion is remembered for a revert
fresh()
st = EV.load_state(CFG); st["champions"] = {"hook_type": "statement"}; put_state(st)
results(verdict("hook_type", "statement", "number", "winner", "number"))
run = go()
assert run.st["confirming"]["hook_type"]["prev_champion"] == "statement" and run.st["champions"]["hook_type"] == "number"
# defended: the champion won again, nothing to confirm
fresh()
st = EV.load_state(CFG); st["champions"] = {"hook_type": "number"}; put_state(st)
results(verdict("hook_type", "statement", "number", "winner", "number"))
run = go()
assert not run.st["confirming"] and actions(run, "defended") and run.st["round"]["factors"]["hook_type"] == ["number", "question"]      # a new opening contest, as before
# an even factor is no trial; confirm_n 0 locks a winner in at once
fresh()
results(verdict("first_frame", "cover", "photo", "even"), verdict("hook_type", "statement", "number", "winner", "number"))
run = go()
assert "first_frame" not in run.st["round"]["factors"] and "first_frame" not in run.st["confirming"] and "hook_type" in run.st["confirming"]
run = go(CFG0)
assert not run.st["confirming"] and run.st["round"]["factors"]["hook_type"] == ["number", "question"] and run.st["champions"] == {"hook_type": "number"}
# a gene that wins is adopted and goes on trial; a retest that drops an adopted gene does not
fresh()
st = EV.load_state(CFG); st["round"].update(factors={}, starts={}, origin={})
contest(st, "gene:g001", ["a", "b"], "gene", "2026-11-01"); contest(st, "gene:g002", ["a", "b"], "retest", "2026-11-01")
st["genes"] = {"g001": gene("g001", "Name the place in the first line, before any date."), "g002": gene("g002", "Keep every sentence short.", kind="retest", parent="g003", lineage="g003", a_text="Keep every sentence short."),
               "g003": gene("g003", "Keep every sentence short.", status="adopted")}
st["adopted"] = {"g003": "g003"}
put_state(st)
results(verdict("gene:g001", "a", "b", "winner", "b", 1.5), verdict("gene:g002", "a", "b", "winner", "b", 1.4))
run = go()
assert run.st["genes"]["g001"]["status"] == "adopted" and run.st["adopted"]["g001"] == "g001"
assert run.st["confirming"]["gene:g001"]["arm"] == "b" and run.st["confirming"]["gene:g001"]["prev"] == "a" and "gene:g001" in run.st["round"]["factors"]
assert "gene:g002" not in run.st["confirming"] and "gene:g002" not in run.st["round"]["factors"] and run.st["genes"]["g003"]["status"] == "retired"
print("1 a winner starts a trial ok")

# ---- 2. the draw ----
fresh()
results(verdict("hook_type", "statement", "number", "winner", "number"))
run = go(); commit(run)
n = 4000
prev = sum(EV.draw("hook_type", ["statement", "number"], random.Random(f"round 1:hook_type:{k}"), CFG) == "statement" for k in range(n))
assert 0.17 * n < prev < 0.23 * n, prev                                                       # the previous choice keeps 20%
other = sum(EV.draw("ending", ["loop", "question"], random.Random(f"round 1:ending:{k}"), CFG) == "loop" for k in range(n))
assert 0.46 * n < other < 0.54 * n, other                                                     # a plain contest stays 50/50
assert all(EV.draw("ending", ["loop", "question"], random.Random(f"x:{k}"), CFG) == random.Random(f"x:{k}").choice(["loop", "question"]) for k in range(50))
assert EV.draw("hook_type", ["statement", "number"], random.Random(1), {"evolve": {"on": False}}) in ("statement", "number")
run = go({**CFG, "analysis": {"confirm_share": 0.3}}); assert run.st["confirming"]["hook_type"]["share"] == 0.2      # the share is in the record: a changed setting applies to a new trial only
fresh(); results(verdict("hook_type", "statement", "number", "winner", "number"))
assert go({**CFG, "analysis": {"confirm_share": 0.3, "confirm_n": 30}}).st["confirming"]["hook_type"] | {} == {**go().st["confirming"]["hook_type"], "share": 0.3, "n": 30}
fresh(); results(verdict("hook_type", "statement", "number", "winner", "number")); put_state(go().st)
import writer as W
W.ROOT = SCRATCH
W.stopped = lambda: {}
W.CFG = {**W.CFG, "evolve": EVC, "test_round": ROUND}
day = dt.date(2026, 11, 10)
plans = [W.test_plan(k, "news", today=day)[1] for k in range(600)]
c = collections.Counter(p["hook_type"] for p in plans)
assert 0.15 * 600 < c["statement"] < 0.26 * 600 and c["number"] + c["statement"] == 600, c         # 80% take the champion through test_plan
e = collections.Counter(p["ending"] for p in plans)
assert 240 < e["loop"] < 360, e
assert W.test_plan(7, "news", today=day) == W.test_plan(7, "news", today=day)                  # repeatable
print("2 the draw ok")


# ---- 3. round_verdicts: confirming, confirmed, reverted ----
def trial_rows(seed, n_prev, n_champ, effect, since="2026-11-01", sd=0.6, engaged=False):
    """Shorts since the trial began: arm_hook_type statement (previous) or number (champion); log rel = effect for the champion."""
    rng = random.Random(seed)
    rows = []
    for i in range(n_prev + n_champ):
        arm = "statement" if i < n_prev else "number"
        d = dt.datetime(2026, 11, 1 + i % 8, 8 + i % 10, 0, tzinfo=dt.timezone.utc)
        r = {"channel": "main", "posted": d.isoformat(), "posted_day": d.date().isoformat(), "arm_hook_type": arm,
             "rel": math.exp(rng.gauss(effect if arm == "number" else 0.0, sd))}
        if engaged:
            share = 0.30 * math.exp(rng.gauss(effect if arm == "number" else 0.0, 0.05))
            r.update(yt_an_views=200, yt_engaged_views=round(200 * min(0.95, share)))
        rows.append(r)
    return rows


F = {"hook_type": ["statement", "number"]}
CONF = {"hook_type": {"arm": "number", "n": 20}}
kw = dict(starts={"hook_type": "2026-11-01"}, confirming=CONF)
v = DRV.round_verdicts(trial_rows(1, 12, 60, 0.4), F, "2026-10-25", 70, "round 1", **kw)[0]
assert v["verdict"] == "confirming" and v["confirm"] == "number" and v["start"] == "2026-11-01" and "12 of 20" in v["why"], v
v = DRV.round_verdicts(trial_rows(2, 20, 80, 0.4), F, "2026-10-25", 70, "round 1", **kw)[0]
assert v["verdict"] == "confirmed" and v["winner"] == "number" and v["p"] != "" and v["q"] == "", v        # no q: a trial is no discovery
v = DRV.round_verdicts(trial_rows(3, 22, 80, -0.5), F, "2026-10-25", 70, "round 1", **kw)[0]
assert v["verdict"] == "reverted" and v["winner"] == "" and float(v["effect"]) < 0.8, v                   # the champion is clearly worse
v = DRV.round_verdicts(trial_rows(4, 40, 80, -0.07, sd=0.3), F, "2026-10-25", 70, "round 1", **kw)[0]
assert v["verdict"] == "confirmed", v                                                                      # a little worse is inside the even band (14%)
v = DRV.round_verdicts(trial_rows(5, 40, 80, -0.25, sd=0.3), F, "2026-10-25", 70, "round 1", **kw)[0]
assert v["verdict"] == "reverted", v
# the same trial without the record is an ordinary contest: the champion clearly better wins, and a clear loser is not "reverted"
v = DRV.round_verdicts(trial_rows(2, 20, 80, 0.4), F, "2026-10-25", 70, "round 1", starts={"hook_type": "2026-11-01"})[0]
assert v["verdict"] == "winner" and v["confirm"] == "", v
# the engaged share's band is 10%: a champion 12% worse is reverted on the opening factor (judged on the engaged share) and confirmed on views
rows_e = trial_rows(6, 40, 80, -0.12, sd=0.01, engaged=True)
for r in rows_e:
    r["rel"] = math.exp(-0.12 if r["arm_hook_type"] == "number" else 0.0)
    r["ending"] = "question" if r["arm_hook_type"] == "number" else "loop"
ve = DRV.round_verdicts(rows_e, F, "2026-10-25", 70, "round 1", **kw)[0]
vv = DRV.round_verdicts(rows_e, {"ending": ["loop", "question"]}, "2026-10-25", 70, "round 1", starts={"ending": "2026-11-01"}, confirming={"ending": {"arm": "question", "n": 20}})[0]
assert ve["metric"] == "engaged" and ve["verdict"] == "reverted", ve
assert vv["metric"] == "views" and vv["verdict"] == "confirmed", vv
# the champion is arm a: the sign flips
F2 = {"hook_type": ["number", "statement"]}
v = DRV.round_verdicts(trial_rows(3, 22, 80, -0.5), F2, "2026-10-25", 70, "round 1", starts=kw["starts"], confirming={"hook_type": {"arm": "statement", "n": 20}})[0]
assert v["verdict"] == "confirmed", v                                                                      # statement (the previous choice here) came out ahead
# a trial stays out of the false-winner family: its q is blank, and the other factor is a family of one (q equals its p)
rows = trial_rows(8, 40, 80, 0.5)
rng = random.Random(8)
for r in rows: r["ending"] = rng.choice(["loop", "question"])
two = {x["factor"]: x for x in DRV.round_verdicts(rows, {"hook_type": ["statement", "number"], "ending": ["loop", "question"]}, "2026-10-25", 70, "round 1", **kw)}
assert two["hook_type"]["q"] == "" and two["hook_type"]["p"] != "" and abs(two["ending"]["q"] - two["ending"]["p"]) < 2e-3, two
print("3 confirmation verdicts ok")


# ---- 4. settle: confirmed, reverted ----
def trial_state(prev_champion=None, gene_kind=None):
    st = EV.load_state(CFG); st["round"].update(factors={}, starts={}, origin={})
    contest(st, "hook_type", ["statement", "number"], "confirm", "2026-11-05")
    st["champions"] = {"hook_type": "number"}
    st["confirming"] = {"hook_type": {"arm": "number", "prev": "statement", "since": "2026-11-05", "n": 20, "share": 0.2, "source": "neighbour", "opening": True, "prev_champion": prev_champion}}
    return st


fresh(); put_state(trial_state())
results(verdict("hook_type", "statement", "number", "confirming", start="2026-11-05", confirm="number"))
run = go(); assert "hook_type" in run.st["confirming"] and not run.log or not actions(run, "lock-in", "revert")
results(verdict("hook_type", "statement", "number", "confirmed", "number", 1.3, 1.0, 1.7, start="2026-11-05", confirm="number"))
run = go()
left = lambda run: run.st["round"]["origin"].get("hook_type") != "confirm" and run.st["round"]["starts"].get("hook_type") != "2026-11-05"      # the trial's contest is gone (an opening factor is reopened as a new one)
assert not run.st["confirming"] and left(run) and run.st["champions"] == {"hook_type": "number"}
h = [x for x in run.st["history"] if x["source"] == "confirm"][-1]
assert h["verdict"] == "confirmed" and h["winner"] == "number" and h["retest_after"] == "2026-12-08" and h["source"] == "confirm" and h.get("metric") == "engaged", h
assert actions(run, "lock-in") and not run.decisions
# a row from before the trial (other start) settles nothing
results(verdict("hook_type", "statement", "number", "reverted", "", 0.5, 0.3, 0.8, start="2026-10-25", confirm="number"))
run = go(); assert "hook_type" in run.st["confirming"] and "hook_type" in run.st["round"]["factors"]
# reverted, no champion before: no champion again
fresh(); put_state(trial_state())
results(verdict("hook_type", "statement", "number", "reverted", "", 0.6, 0.4, 0.9, start="2026-11-05", confirm="number"))
run = go()
assert not run.st["confirming"] and run.st["champions"] == {} and left(run) and actions(run, "revert")
assert len(run.decisions) == 1 and run.decisions[0]["by"] == "evolve (confirmation)" and run.decisions[0]["check_on"] == "2026-12-08" and run.decisions[0]["area"] == "Confirmation"
hr = [x for x in run.st["history"] if x["source"] == "confirm"][-1]
assert hr["verdict"] == "reverted" and hr["winner"] == "statement"
# reverted, a champion before: it returns
fresh(); put_state(trial_state(prev_champion="statement"))
results(verdict("hook_type", "statement", "number", "reverted", "", 0.6, 0.4, 0.9, start="2026-11-05", confirm="number"))
run = go(); assert run.st["champions"] == {"hook_type": "statement"} and not run.st["confirming"]
# genes
def gene_trial(kind):
    st = EV.load_state(CFG); st["round"].update(factors={}, starts={}, origin={})
    contest(st, "gene:g002", ["a", "b"], "confirm", "2026-11-05")
    st["genes"] = {"g001": gene("g001", "Name the place in the first line, before any date.", status="retired" if kind == "mutate" else "live"),
                   "g002": gene("g002", "Name the place and the year in the first line.", kind=kind, status="adopted", parent="g001" if kind == "mutate" else "",
                                lineage="g001" if kind == "mutate" else "g002", a_text="Name the place in the first line, before any date." if kind == "mutate" else "", adopted="2026-11-05", retest_after="2026-12-03")}
    st["adopted"] = {("g001" if kind == "mutate" else "g002"): "g002"}
    st["confirming"] = {"gene:g002": {"arm": "b", "prev": "a", "since": "2026-11-05", "n": 20, "share": 0.2, "source": kind, "opening": False, "prev_champion": None}}
    return st


fresh(); put_state(gene_trial("new"))
results(verdict("gene:g002", "a", "b", "reverted", "", 0.7, 0.5, 0.95, start="2026-11-05", confirm="b"))
run = go()
assert run.st["genes"]["g002"]["status"] == "rejected" and run.st["adopted"] == {} and not run.st["confirming"] and "gene:g002" not in run.st["round"]["factors"]
assert len(run.decisions) == 1 and "g002" in run.decisions[0]["change"]
fresh(); put_state(gene_trial("mutate"))
results(verdict("gene:g002", "a", "b", "reverted", "", 0.7, 0.5, 0.95, start="2026-11-05", confirm="b"))
run = go()
assert run.st["genes"]["g002"]["status"] == "rejected" and run.st["genes"]["g001"]["status"] == "adopted" and run.st["adopted"] == {"g001": "g001"}     # the parent returns
fresh(); put_state(gene_trial("new"))
results(verdict("gene:g002", "a", "b", "confirmed", "b", 1.2, 1.0, 1.4, start="2026-11-05", confirm="b"))
run = go()
assert run.st["genes"]["g002"]["status"] == "adopted" and run.st["adopted"] == {"g002": "g002"} and run.st["genes"]["g002"]["retest_after"] == "2026-12-08"
assert not run.st["confirming"] and "gene:g002" not in run.st["round"]["factors"]
print("4 settle ok")

# ---- 5. the record ----
fresh(); put_state(trial_state(prev_champion="statement"))
results(verdict("hook_type", "statement", "number", "confirming", start="2026-11-05", confirm="number", n_a=7, n_b=31))
md = EV.render_md(go().st, EV.settings(CFG))
for must in ("## Confirming (1)", "- hook_type: number against the previous statement, since 2026-11-05; 7 and 31 Shorts so far of 20 a side, confirming",
             "80% of Shorts while the previous choice keeps 20%", "- hook_type: number (confirming)"):
    assert must in md, (must, md)
# main() end to end: a revert writes the decisions row and the log
fresh(); put_state(trial_state())
results(verdict("hook_type", "statement", "number", "reverted", "", 0.6, 0.4, 0.9, start="2026-11-05", confirm="number"))
(SCRATCH / "config.json").write_text(json.dumps(CFG))
EV.uk_today = lambda: dt.date.fromisoformat(TODAY)
assert EV.main([]) == 0
dec = list(csv.DictReader((AN / "decisions.csv").open()))
assert len(dec) == 1 and dec[0]["by"] == "evolve (confirmation)" and dec[0]["date"] == TODAY, dec
assert "revert" in (AN / "evolve_log.csv").read_text() and json.loads((AN / "evolve.json").read_text())["confirming"] == {}
em, en = chr(0x2014), chr(0x2013)
for f in ("pipeline/evolve.py", "pipeline/drivers.py", "tests/test_confirm.py", "config.json"):
    txt = open(REPO_DIR + "/" + f).read()
    assert em not in txt and en not in txt, f
assert em not in (AN / "evolve.md").read_text() + (AN / "decisions.csv").read_text() and en not in (AN / "evolve.md").read_text()
print("5 the record ok")
print("confirm ok")
