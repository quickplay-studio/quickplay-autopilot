"""Offline tests of the opening tests judged on the engaged share (26 October, Charlie: YPP counts the views that stay past
the opening, and only about a third do):
1. drivers: metric_of and engaged_pair; round_verdicts judges hook_type on the engaged share (a 10% bar), withholds a winner
   that costs views (the views guard), falls back to views when the data has no engaged views, takes a metrics override for
   a gene, explains the lag when the round's Shorts have none in yet, and leaves a non-opening factor on views;
2. evolve: round_metrics (the live opening genes), opening_turn (every other new gene, one live at a time), focus_first
   (an absent opening factor is reopened before the draw, with its next untried arm), launch_gene and make_gene carry the
   metric (a mutation and a retest inherit it), record_ledger targets engaged_share, render_md marks the opening;
3. analytics.test_progress counts an opening arm only once its engaged views are in and writes the metric to tests.json;
   changes.py knows the engaged_share metric."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import csv, datetime as dt, json, os, random, shutil, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import drivers as DRV
import evolve as EV

# 1. drivers
assert DRV.metric_of("hook_type") == "engaged" and DRV.metric_of("first_frame") == "engaged" and DRV.metric_of("fx_opening") == "engaged"
assert DRV.metric_of("ending") == "views" and DRV.metric_of("gene:g009") == "views"
assert DRV.metric_of("gene:g009", {"gene:g009": "engaged"}) == "engaged" and DRV.metric_of("hook_type", {"hook_type": "views"}) == "views"
assert DRV.engaged_pair({"yt_engaged_views": "30", "yt_an_views": "100"}) == (30.0, 100.0)
assert DRV.engaged_pair({"yt_engaged_views": "30", "yt_engaged_pct": "25"}) == (30.0, 120.0)        # rebuilt from the share
assert DRV.engaged_pair({"yt_engaged_views": "", "yt_an_views": "100"}) is None and DRV.engaged_pair({}) is None
assert DRV.engaged_pair({"yt_engaged_views": "5", "yt_an_views": "0"}) is None

rng = random.Random(11)
def short(i, hook, share, views, day=None, eng=True, ending="loop"):
    r = {"short": f"E-{i}", "channel": ("main", "music")[i % 3 == 0], "posted": f"2026-10-{day or 25 + i % 6}T12:00:00+00:00",
         "rel": views, "arm_hook_type": hook, "ending": ending}
    if eng: r.update(yt_engaged_views=str(round(1000 * views * share)), yt_an_views=str(round(1000 * views)))
    return r
def batch(b_share, b_views, eng=True):
    out = []
    for i in range(60):
        b = i % 2 == 1
        out.append(short(i, ("statement", "number")[b], (b_share if b else 0.30) * rng.uniform(0.94, 1.06),
                         (b_views if b else 1.0) * rng.uniform(0.9, 1.1), eng=eng, ending=("loop", "question")[(i // 2) % 2]))
    return out
F = {"hook_type": ["statement", "number"], "ending": ["loop", "question"]}
V = {r["factor"]: r for r in DRV.round_verdicts(batch(0.39, 1.0), F, "2026-10-25")}
h = V["hook_type"]
assert h["metric"] == "engaged" and h["verdict"] == "winner" and h["winner"] == "number" and 1.2 < h["effect"] < 1.4, h
assert h["views_effect"] != "" and 0.85 < h["views_effect"] < 1.15, h
assert V["ending"]["metric"] == "views" and V["ending"]["views_effect"] == "", V["ending"]          # not about the opening
g = {r["factor"]: r for r in DRV.round_verdicts(batch(0.39, 0.5), F, "2026-10-25")}["hook_type"]
assert g["metric"] == "engaged" and g["verdict"] == "running" and g["winner"] == "" and g["views_effect"] < 0.7, g
assert "costs views" in g["why"], g                                                                    # the guard
vf = {r["factor"]: r for r in DRV.round_verdicts(batch(0.39, 1.6, eng=False), F, "2026-10-25")}["hook_type"]
assert vf["metric"] == "views" and vf["verdict"] == "winner" and vf["winner"] == "number", vf            # no engaged data: views
gene_rows = [{**r, "genes": f"gene:g009={'ab'[r['arm_hook_type'] == 'number']}"} for r in batch(0.39, 1.0)]
gv = DRV.round_verdicts(gene_rows, {"gene:g009": ["a", "b"]}, "2026-10-25", metrics={"gene:g009": "engaged"})[0]
assert gv["metric"] == "engaged" and gv["verdict"] == "winner" and gv["winner"] == "b", gv
assert DRV.round_verdicts(gene_rows, {"gene:g009": ["a", "b"]}, "2026-10-25")[0]["metric"] == "views"
old = [short(100 + i, ("statement", "number")[i % 2], 0.3, 1.0, day=20) for i in range(20)]           # before the round, engaged in
new = [short(200 + i, ("statement", "number")[i % 2], 0.3, 1.0, eng=False) for i in range(20)]         # the round's: not yet
lag = DRV.round_verdicts(old + new, {"hook_type": F["hook_type"]}, "2026-10-25")[0]
assert lag["metric"] == "engaged" and lag["verdict"] == "too few to tell" and lag["n_a"] == lag["n_b"] == 0 and "about 3 days" in lag["why"], lag
assert DRV.EVEN_ENG < DRV.EVEN and set(DRV.OPENING) == {"hook_type", "first_frame", "fx_opening"}
assert {"metric", "views_effect"} <= set(DRV.ROUND_FIELDS)
print("1 drivers judge the opening on the engaged share ok")

# 2. evolve
EV.ROOT = SCRATCH
AN = SCRATCH / "analytics"
def fresh():
    shutil.rmtree(AN, ignore_errors=True); AN.mkdir(parents=True)
TESTS = {"hook_type": ["statement", "question", "number", "superlative", "twist"], "ending": ["loop", "question"],
         "first_frame": ["cover", "photo"]}
EVC = {"on": True, "width": 6, "max_changes_per_run": 1, "max_genes": 3, "max_new_genes_per_run": 1, "max_adopted": 6,
       "retest_days": 28, "neighbour_factors": ["hook_type", "ending", "first_frame"]}
CFG = {"evolve": EVC, "test_round": {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
                                     "factors": {"ending": ["loop", "question"], "first_frame": ["cover", "photo"]}}}
def gene(gid, text, kind="new", born="2026-11-01", **kw):
    return {"label": text[:20], "text": text, "a_text": "", "b_text": text, "parent": "", "lineage": gid, "born": born,
            "status": "live", "effect": "", "kind": kind, "why": "", **kw}
def state(**kw):
    st = EV.load_state(CFG)
    for k, v in kw.items(): st[k] = v
    return st

fresh()
assert EV.DEFAULTS["focus"] == ["hook_type", "first_frame", "fx_opening"] and EV.DEFAULTS["opening_gene_every"] == 2
st = state(genes={"g005": gene("g005", "Open on the most surprising number.", metric="engaged"), "g006": gene("g006", "End on a question.")})
st["round"]["factors"].update({"gene:g005": ["a", "b"], "gene:g006": ["a", "b"]})
(AN / "evolve.json").write_text(EV.dump(st))
assert EV.round_metrics(CFG) == {"gene:g005": "engaged"}
assert EV.round_metrics({**CFG, "evolve": {**EVC, "on": False}}) == {}
assert EV.is_opening(st, "gene:g005") and not EV.is_opening(st, "gene:g006") and EV.is_opening(st, "hook_type") and not EV.is_opening(st, "ending")
S = EV.settings(CFG)
assert not EV.opening_turn(st, S)                                                   # an opening gene is live: one at a time
st0 = state(genes={})
assert EV.opening_turn(st0, S) and not EV.opening_turn(st0, {**S, "opening_gene_every": 0})
st1 = state(genes={"g001": gene("g001", "x", born="2026-11-01", metric="engaged", status="rejected")})
assert not EV.opening_turn(st1, S)                                                  # the last new gene was an opening one
st1["genes"]["g002"] = gene("g002", "y", born="2026-11-03", status="rejected")
assert EV.opening_turn(st1, S)                                                      # one since: its turn again
assert not EV.opening_turn(st1, {**S, "opening_gene_every": 3})
print("2a round_metrics, is_opening and opening_turn ok")

fresh()
st = state(champions={"hook_type": "statement"})
(AN / "evolve.json").write_text(EV.dump(st))
run = EV.run_once(CFG, "2026-11-10", TESTS, {}, set())
op = [r for r in run.log if r["action"] == "open"]
assert len(op) == 1 and op[0]["factor"] == "hook_type" and op[0]["arms"] == "statement vs question" and "focus" in op[0]["note"], run.log
assert run.st["round"]["factors"]["hook_type"] == ["statement", "question"] and run.st["round"]["starts"]["hook_type"] == "2026-11-10"
st["history"] = [{"factor": "hook_type", "arms": ["statement", "question"], "verdict": "even"}]
(AN / "evolve.json").write_text(EV.dump(st))
run = EV.run_once(CFG, "2026-11-10", TESTS, {}, set())
assert run.st["round"]["factors"].get("hook_type") == ["statement", "number"], run.st["round"]["factors"]   # the next untried arm
(AN / "evolve.json").write_text(EV.dump(st))
run = EV.run_once({**CFG, "evolve": {**EVC, "focus": []}}, "2026-11-10", TESTS, {}, set())
assert not any("focus" in r["note"] for r in run.log)                                # focus off: the draw alone
full = state(champions={"hook_type": "statement"})
for i in range(4): full["round"]["factors"][f"x{i}"] = ["a", "b"]
(AN / "evolve.json").write_text(EV.dump(full))
run = EV.run_once(CFG, "2026-11-10", TESTS, {}, set())
assert "hook_type" not in run.st["round"]["factors"] and all(r["action"] != "open" for r in run.log)   # a full round waits
print("2b focus_first reopens the opening before the draw ok")

fresh()
PROMPTS = []
TEXTS = iter(["Open on the single most surprising fact, said plainly in the first line.",
              "Put the place name in the very first words of the script."])
def claude(label, prompt):
    PROMPTS.append(prompt); return {"genes": [{"label": "t", "text": next(TEXTS), "why": "w"}]}
EV.ask_claude, EV.ask_free = claude, lambda p: (_ for _ in ()).throw(RuntimeError("no free model in tests"))
st = state(genes={})
run = EV.Run(st, EV.settings(CFG), "2026-11-10", TESTS)
assert EV.launch_gene(run, "gene")
g1 = [g for g in st["genes"].values()][0]
assert g1["metric"] == "engaged" and "first two seconds" in PROMPTS[-1] and "opening gene" in run.log[-1]["note"], (g1, run.log[-1])
run2 = EV.Run(st, EV.settings(CFG), "2026-11-11", TESTS)
assert EV.launch_gene(run2, "gene")
g2 = st["genes"]["g002"]
assert "metric" not in g2 and "first two seconds" not in PROMPTS[-1] and "opening gene" not in run2.log[-1]["note"], g2
st["genes"]["g001"]["status"] = "adopted"
mid = EV.make_gene(run2, "mutate", {"text": "Open on the most surprising fact, in under six words.", "label": "m"}, "g001")
rid = EV.make_gene(run2, "retest", None, "g001")
assert st["genes"][mid]["metric"] == "engaged" and st["genes"][rid]["metric"] == "engaged" and st["genes"][mid]["lineage"] == "g001"
assert "metric" not in st["genes"][EV.make_gene(run2, "retest", None, "g002")]
print("2c opening genes carry the metric ok")

fresh()
ids = EV.record_ledger([{"change": "Evolve: hook_type now runs question as its champion", "hypothesis": "question lifts the share", "opening": True},
                        {"change": "Evolve: ending now runs loop as its champion", "hypothesis": "loop lifts views", "opening": False}], "2026-11-10")
assert len(ids) == 2, ids
led = list(csv.DictReader((AN / "changes.csv").open()))
assert led[0]["target"] == "engaged_share" and led[0]["guardrails"] == "yt_rel;dead_share", led[0]
assert led[1]["target"] == "yt_rel" and led[1]["guardrails"] == "dead_share;avg_viewed_pct", led[1]
import changes as C
assert "engaged_share" in C.METRICS and C.METRICS["engaged_share"][1] == "higher"
assert all(m in C.METRICS for m in (EV.LEDGER_TARGET_OPENING, *EV.LEDGER_GUARDS_OPENING.split(";")))
st = state(genes={"g005": gene("g005", "Open on the most surprising number.", metric="engaged")})
st["round"]["factors"].update({"hook_type": ["statement", "question"], "gene:g005": ["a", "b"]})
md = EV.render_md(st, EV.settings(CFG))
assert "| hook_type (opening) |" in md and "| ending |" in md and "g005 (new, opening, judged on the engaged share)" in md, md
assert "Opening contests" in md and chr(0x2014) not in md and chr(0x2013) not in md
print("2d ledger target and evolve.md ok")

# 3. analytics
import analytics as A
fresh()
A.OUT = AN
A.CFG = {**A.CFG, "evolve": {"on": False}, "test_round": {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
                                                          "factors": {"hook_type": ["statement", "number"], "ending": ["loop", "question"]}}}
rows = [{**r, "views_24h": "50"} for r in batch(0.39, 1.0)]
for r in rows[:20]: r.pop("yt_engaged_views"); r.pop("yt_an_views")              # 20 Shorts still waiting on engaged views
A.test_progress(rows, [], today=dt.date(2026, 11, 1))
T = json.loads((AN / "tests.json").read_text())["factors"]
assert T["hook_type"]["metric"] == "engaged" and sum(a["n"] for a in T["hook_type"]["arms"].values()) == 40, T["hook_type"]
assert T["ending"]["metric"] == "views" and sum(a["n"] for a in T["ending"]["arms"].values()) == 60, T["ending"]
assert "views_effect" in T["hook_type"]
hub = (_p.Path(REPO_DIR) / "docs" / "hub.html").read_text()
assert 'r.x.metric === "engaged"' in hub and "judged on the engaged share" in hub
print("3 analytics counts and the hub ok")
print("engaged ok")
