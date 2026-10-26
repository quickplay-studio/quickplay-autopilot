"""Offline tests of the self-evolving round (26 October, pipeline/evolve.py):
1. the state: bootstrapped from config's test_round; live_round falls back to config when the file is missing or broken;
2. settling: a TESTS winner becomes a champion and a neighbour contest takes its slot; an even factor is retired with a
   retest date and is "settled" until then; a stale round.csv row (other arms) is ignored; max_changes_per_run, width and the
   long-length exclusion hold;
3. genes: check_gene (dash, banned subject, subscribe, negative, near duplicate, not an instruction); a winning gene is adopted,
   a losing one rejected; a mutation replaces its parent in the lineage; a retest can drop it; proposals go to Claude first
   (one call a run, config evolve.model), the free chain only when Claude returns nothing, each gene records its "by", and bad
   or missing answers are survived; at most max_new_genes_per_run new genes; the oldest adopted gene is retested over max_adopted;
4. sources: Thompson sampling follows each source's record, deterministically; retests of a champion and a gene come due;
5. drivers: assigned() reads the genes cell, round_verdicts judges a contest from its own start;
6. writer: with evolve on every live contest (a champion's too, genes on every kind) is drawn 50/50 and style_note carries the
   gene text and the adopted texts, a lineage under contest giving way to its arm; settled() and winners() read the state; with
   evolve off test_plan is what it was;
7. analytics: the genes column, the live round's starts and labels in the tests table; the change ledger row; main() end to end."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import collections, csv, datetime as dt, json, os, random, shutil, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]
import evolve as EV
import drivers as DRV

EV.ROOT = SCRATCH
AN = SCRATCH / "analytics"
DASH_EM, DASH_EN = chr(0x2014), chr(0x2013)
EVC = {"on": True, "width": 3, "max_changes_per_run": 3, "max_genes": 3, "max_new_genes_per_run": 1, "max_adopted": 6,
       "retest_days": 28, "neighbour_factors": ["hook_type"]}
ROUND = {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
         "factors": {"hook_type": ["statement", "number"], "ending": ["loop", "question"], "first_frame": ["cover", "photo"]}}
CFG = {"evolve": EVC, "test_round": ROUND}
TESTS = {"hook_type": ["statement", "question", "number", "superlative", "twist"],
         "length": ["under 25 s", "25 to 34 s", "35 to 44 s", "about 60 s", "about 2 min"],
         "ending": ["loop", "question"], "first_frame": ["cover", "photo"]}
LONG = {"about 60 s", "about 2 min"}
TODAY = "2026-11-10"
GOOD = {"genes": [{"label": "Name the place first", "text": "Name the place in the first line, before any date or number.",
                   "why": "Viewers place a story faster."}]}


def fresh():
    shutil.rmtree(AN, ignore_errors=True); AN.mkdir(parents=True)


def ask_fails(*a): raise RuntimeError("no model answers in tests")


CLAUDE_CALLS, FREE_CALLS = [], []
def use(claude=ask_fails, free=ask_fails):
    """Stubs for the two doors: claude(label, prompt) -> JSON, free(prompt) -> (JSON, model); a call is recorded, then answers or raises."""
    def c(label, prompt): CLAUDE_CALLS.append((label, prompt)); return claude(label, prompt)
    def f(prompt): FREE_CALLS.append(prompt); return free(prompt)
    CLAUDE_CALLS.clear(); FREE_CALLS.clear()
    EV.ask_claude, EV.ask_free = c, f


use()


def results(*rows):
    fields = DRV.ROUND_FIELDS
    with (AN / "round.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({"round": "round 1", "n_a": 30, "n_b": 30, **r})


def verdict(f, a, b, v, winner="", effect=1.0, low=0.8, high=1.2):
    return {"factor": f, "arm_a": a, "arm_b": b, "verdict": v, "winner": winner, "effect": effect, "low": low, "high": high}


def commit(run): (AN / "evolve.json").write_text(EV.dump(run.st))


def go(cfg=CFG, today=TODAY, tests=TESTS, **kw):
    return EV.run_once(cfg, today, tests, kw.pop("texts", {}), kw.pop("exclude", LONG), **kw)


def actions(run, *names): return [r for r in run.log if r["action"] in names]


def put_state(st): (AN / "evolve.json").write_text(EV.dump(st))


def gene(gid, text, kind="new", status="live", parent="", lineage=None, a_text=None, **kw):
    return {"label": text[:20], "text": text, "a_text": ("" if kind == "new" else "") if a_text is None else a_text, "b_text": text,
            "parent": parent, "lineage": lineage or gid, "born": "2026-11-01", "status": status, "effect": "", "kind": kind, "why": "", **kw}


def contest(st, f, arms, origin, start="2026-11-01"):
    st["round"]["factors"][f], st["round"]["starts"][f], st["round"]["origin"][f] = arms, start, origin


# 1. the state
fresh()
assert EV.live_round(CFG) == ROUND and EV.champions() == {} and EV.genes() == {} and EV.settled_factors(TODAY) == set()
assert EV.live_round({"test_round": ROUND}) == ROUND                                   # evolve not on: config's
st = EV.load_state(CFG)
r = st["round"]
assert (r["name"], r["start"], r["per_arm"], r["factors"]) == ("round 1", "2026-10-25", 70, ROUND["factors"]), r
assert set(r["starts"].values()) == {"2026-10-25"} and set(r["origin"].values()) == {"round 1"} and set(r["starts"]) == set(r["factors"])
run = go()
assert actions(run, "bootstrap") and run.st["round"]["factors"] == ROUND["factors"]        # round 1 continues unchanged
assert not actions(run, "open", "champion", "retire"), run.log
(AN / "evolve.json").write_text("{not json")
assert EV.live_round(CFG) == ROUND and EV.read_state() == {}                              # broken: config's round stands
put_state({**EV.load_state(CFG), "round": {"name": "x", "start": "2026-11-01", "factors": {"ending": ["loop", "question"]}}})
assert EV.live_round(CFG)["name"] == "x" and EV.live_round({"test_round": ROUND}) == ROUND
put_state({**EV.load_state(CFG), "round": {"name": "empty", "start": "2026-11-01", "factors": {}}})
assert EV.live_round(CFG)["factors"] == {}                                                 # an emptied round is not config's again
print("1 state ok")

# 2. settling and filling
fresh()
results(verdict("hook_type", "statement", "number", "winner", "number", 1.6, 1.2, 2.0))
run = go()
assert run.st["champions"] == {"hook_type": "number"}, run.st["champions"]
live = run.st["round"]
assert len(live["factors"]) == 3 and live["factors"]["hook_type"][0] == "number" and live["factors"]["hook_type"][1] in ("question", "superlative", "twist"), live
assert live["origin"]["hook_type"] == "neighbour" and live["starts"]["hook_type"] == TODAY and live["starts"]["ending"] == "2026-10-25"
h = run.st["history"][0]
assert (h["factor"], h["winner"], h["verdict"], h["end"], h["retest_after"], h["effect"]) == ("hook_type", "number", "winner", TODAY, "2026-12-08", 1.6), h
assert "sources" in run.st and run.st["sources"]["neighbour"] == {"contests": 0, "wins": 0}
assert len(run.ledger) == 1 and "number" in run.ledger[0]["change"]
assert [r["action"] for r in run.log] == ["bootstrap", "champion", "open"], run.log
again = go()
assert [r["factor"] for r in again.log] == [r["factor"] for r in run.log] and again.st["round"] == run.st["round"]      # a run repeats
print("2a winner becomes a champion, a neighbour fills the slot ok")

fresh()
results(verdict("ending", "loop", "question", "even", "", 1.02, 0.92, 1.1))
run = go()
assert "ending" not in run.st["round"]["factors"] and len(run.st["round"]["factors"]) == 2    # hook_type is live: no neighbour, no model
h = run.st["history"][0]
assert h["verdict"] == "even" and h["retest_after"] == "2026-12-08" and run.st["champions"] == {}
assert actions(run, "retire") and actions(run, "skip") and not run.ledger                     # the gene source had no model: skipped
commit(run)
assert EV.settled_factors(TODAY) == {"ending"} and EV.settled_factors("2026-12-09") == set()
print("2b even factor retired and settled until its retest ok")

fresh()
results(verdict("hook_type", "question", "number", "winner", "number"), verdict("ending", "question", "loop", "winner", "loop"))
run = go()                                                                                   # arms differ from the live arms: stale
assert run.st["round"]["factors"] == ROUND["factors"] and run.st["champions"] == {} and not run.st["history"], run.log
print("2c stale round.csv row ignored ok")

fresh()
wide = {**CFG, "evolve": {**EVC, "width": 6, "neighbour_factors": ["hook_type", "length", "ending", "first_frame"]}}
st0 = EV.load_state(wide); st0["round"].update(factors={}, starts={}, origin={}); put_state(st0)
run = go(wide)
opened = actions(run, "open")
assert len(opened) == 3 and len(run.st["round"]["factors"]) == 3, run.log                    # max_changes_per_run 3 of 6 free
assert all(r["source"] == "neighbour" for r in opened)
for d in range(1, 15):                                                                      # never a long length, whatever the day
    day = str(dt.date(2026, 11, 10) + dt.timedelta(days=d))
    run = go(wide, day)
    assert not [a for arms in run.st["round"]["factors"].values() for a in arms if a in LONG], run.st["round"]["factors"]
    assert all(arms[0] != "about 60 s" for arms in run.st["round"]["factors"].values())
single = {**CFG, "evolve": {**EVC, "width": 1, "neighbour_factors": ["length"]}}
st0 = EV.load_state(single); st0["round"].update(factors={}, starts={}, origin={}); put_state(st0)
assert go(single, TODAY, {"length": ["under 25 s", "about 60 s", "about 2 min"]}).st["round"]["factors"] == {}    # only long arms left: none
print("2d width, max_changes_per_run and the long-length exclusion ok")

# 3. genes
bad = {"dash": f"Open with the place {DASH_EM} then the year.", "en": f"Name the place {DASH_EN} before the year, in the first line.",
       "crime": "Open with the biggest crime detail in the facts.", "health": "Say how the story helps your health and fitness.",
       "sub": "End by asking viewers to subscribe for the next part.", "negative": "Open with how the star slams the director.",
       "short": "Name the place.", "long": "Name the place " + "and the year " * 30, "pronoun": "We open with the place, then the year.",
       "lower": "open with the place and then the year in one line", "article": "The first line names the place before the year.",
       "viral": "Open with the moment that made the story go viral.", "invent": "Invent a number that makes the first line pop.", "lie": "Open with a line that sounds like a lie but is true."}
for k, t in bad.items(): assert EV.check_gene(t), (k, t)
clean = "Name the place in the first line, before any date or number."
assert EV.check_gene(clean) == "" and EV.check_gene("Keep every sentence under twelve words so it reads fast.") == ""
assert EV.check_gene(clean, ["Name the place in the first line, before any date or numbers."]) == "near duplicate"
assert EV.check_gene(clean, ["Say what changes for the viewer in the last line."]) == ""
assert EV.check_gene("Use the word you at least twice in the narration.") == ""
print("3a gene validation ok")

fresh()
CFG0 = {**CFG, "evolve": {**EVC, "max_changes_per_run": 0}}                                    # settle only
def gene_state(kind="new", **g):
    st = EV.load_state(CFG0); st["round"].update(factors={}, starts={}, origin={})
    return st
for win, status in (("b", "adopted"), ("a", "rejected"), ("", "rejected")):
    st = gene_state()
    st["genes"] = {"g001": gene("g001", clean)}
    contest(st, "gene:g001", ["a", "b"], "gene"); put_state(st)
    results(verdict("gene:g001", "a", "b", "winner" if win else "even", win, 1.3 if win == "b" else 0.8 if win else 1.0))
    run = go(CFG0)
    g = run.st["genes"]["g001"]
    assert g["status"] == status and "gene:g001" not in run.st["round"]["factors"], (win, g)
    assert (run.st["adopted"] == {"g001": "g001"}) == (status == "adopted"), run.st["adopted"]
    assert run.st["sources"]["gene"] == {"contests": 1, "wins": int(win == "b")}, run.st["sources"]
    assert bool(actions(run, "adopt")) == (status == "adopted") and len(run.ledger) == int(status == "adopted")
    if status == "adopted":
        assert g["retest_after"] == "2026-12-08" and g["adopted"] == TODAY and EV.check_gene(g["text"]) == ""
        assert "proposed by unknown" in EV.render_md(run.st, run.S) and "g001" in EV.render_md(run.st, run.S)
print("3b gene adopted or rejected ok")

st = gene_state()                                                                               # a mutation
st["genes"] = {"g001": gene("g001", clean, status="adopted"),
               "g002": gene("g002", "Name the place and the year in the first line.", "mutate", parent="g001", lineage="g001", a_text=clean)}
st["adopted"] = {"g001": "g001"}
contest(st, "gene:g002", ["a", "b"], "mutate"); put_state(st)
results(verdict("gene:g002", "a", "b", "winner", "b", 1.25))
run = go(CFG0)
assert run.st["adopted"] == {"g001": "g002"} and run.st["genes"]["g001"]["status"] == "retired" and run.st["genes"]["g002"]["status"] == "adopted"
assert run.st["sources"]["mutate"] == {"contests": 1, "wins": 1} and EV.adopted_texts() == {"g001": clean}      # the file still holds the old state
commit(run)
assert EV.adopted_texts() == {"g001": "Name the place and the year in the first line."}
put_state(st)
results(verdict("gene:g002", "a", "b", "winner", "a", 0.8))
run = go(CFG0)
assert run.st["adopted"] == {"g001": "g001"} and run.st["genes"]["g002"]["status"] == "rejected" and run.st["genes"]["g001"]["status"] == "adopted"
assert run.st["sources"]["mutate"] == {"contests": 1, "wins": 0}
print("3c mutation replaces its parent, or loses ok")

st = gene_state()                                                                               # a retest of an adopted gene against none
st["genes"] = {"g001": gene("g001", clean, status="adopted", retest_after="2026-11-09"),
               "g002": {**gene("g002", clean, "retest", parent="g001", lineage="g001", a_text=clean), "b_text": ""}}
st["adopted"] = {"g001": "g001"}
contest(st, "gene:g002", ["a", "b"], "retest"); put_state(st)
results(verdict("gene:g002", "a", "b", "winner", "b", 1.2))                                      # no instruction won
run = go(CFG0)
assert run.st["adopted"] == {} and run.st["genes"]["g001"]["status"] == "retired" and run.st["sources"]["retest"] == {"contests": 1, "wins": 1}
results(verdict("gene:g002", "a", "b", "even"))
run = go(CFG0)
assert run.st["adopted"] == {"g001": "g001"} and run.st["genes"]["g001"]["retest_after"] == "2026-12-08", run.st["genes"]["g001"]
print("3d retest can drop an adopted gene ok")

fresh()                                                                                         # the model's answers
free = {**CFG, "evolve": {**EVC, "width": 3, "neighbour_factors": []}}
st0 = EV.load_state(free); put_state(st0)
BAD = (("garbage", "not json at all"), ("empty", {}), ("wrong shape", {"genes": "oops"}), ("none", None),
       ("all invalid", {"genes": [{"text": f"Open with the place {DASH_EM} now."}, {"text": "crime first, always"}, {"label": "x"}]}))
for name, ans in BAD:
    for door in ("claude", "free"):
        if door == "claude": use(claude=lambda l, p, a=ans: a)
        else: use(free=lambda p, a=ans: (a, "gemini-test"))
        st0["round"]["factors"] = {k: v for k, v in ROUND["factors"].items() if k != "ending"}; put_state(st0)
        run = go(free)
        assert "gene:g001" not in run.st["round"]["factors"] and actions(run, "skip"), (name, door, run.log)
        assert len(run.st["round"]["factors"]) == 2 and not run.st["genes"]
        assert len(CLAUDE_CALLS) == 1 and len(FREE_CALLS) == (0 if door == "claude" else 1), (name, door)   # an answer from Claude is not asked for twice
use()
run = go(free)
assert actions(run, "skip") and not actions(run, "open") and len(CLAUDE_CALLS) == 1 and len(FREE_CALLS) == 1       # neither answers: survived
st0["round"]["factors"] = {"hook_type": ["statement", "number"]}; st0["round"]["starts"] = {"hook_type": "2026-10-25"}
st0["round"]["origin"] = {"hook_type": "round 1"}; put_state(st0)
def answer(label, prompt):
    return {"genes": [{"label": "dash one", "text": f"Open with the place {DASH_EM} now.", "why": "x"}, GOOD["genes"][0]]}
use(claude=answer, free=lambda p: (_ for _ in ()).throw(AssertionError("the free chain is asked only when Claude returns nothing")))
run = go(free)
g = run.st["genes"].get("g001")
assert g and g["text"] == GOOD["genes"][0]["text"] and g["kind"] == "new" and g["a_text"] == "" and g["b_text"] == g["text"] and g["lineage"] == "g001", g
assert g["by"] == "claude:opus", g                                                                       # Claude first, the model that proposed it recorded
assert run.st["round"]["factors"]["gene:g001"] == ["a", "b"] and run.st["round"]["origin"]["gene:g001"] == "gene" and run.st["round"]["starts"]["gene:g001"] == TODAY
assert len(CLAUDE_CALLS) == 1 and not FREE_CALLS and len(run.st["genes"]) == 1 and len(run.st["round"]["factors"]) == 2     # max_new_genes_per_run 1: one call, one gene
label, prompt = CLAUDE_CALLS[0]
assert label == "claude:opus" and (go({**free, "evolve": {**free["evolve"], "model": "sonnet"}}) and CLAUDE_CALLS[-1][0] == "claude:sonnet")
for must in ("anonymous", "UK English", "subscribe", "no em dashes", "JSON", "3 new instructions"): assert must in prompt, must
assert DASH_EM not in prompt and DASH_EN not in prompt
use(free=lambda p: ({"genes": [GOOD["genes"][0]]}, "gemini-test"))                                    # Claude failing falls back to the free chain
run = go(free)
assert run.st["genes"]["g001"]["by"] == "gemini-test" and len(CLAUDE_CALLS) == 1 and len(FREE_CALLS) == 1, run.st["genes"]
two = {**free, "evolve": {**free["evolve"], "width": 4, "max_new_genes_per_run": 2, "max_changes_per_run": 2}}     # two proposals in one run: one Claude call
st0["round"]["factors"] = {"hook_type": ["statement", "number"]}; put_state(st0)
second = {"genes": [{"label": "second", "text": "Say what changes for the viewer in the last line.", "why": "y"}]}
use(claude=lambda l, p: GOOD, free=lambda p: (second, "gemini-test"))
run = go(two)
assert len(CLAUDE_CALLS) == 1 and len(FREE_CALLS) == 1 and sorted(g["by"] for g in run.st["genes"].values()) == ["claude:opus", "gemini-test"], (run.log, CLAUDE_CALLS)
use()
run = go({**free, "evolve": {**free["evolve"], "claude_calls_per_run": 0}})
assert not CLAUDE_CALLS and len(FREE_CALLS) == 1                                                       # a cap of 0 leaves Claude out
print("3e the model's bad answers survived, one good gene opened ok")

fresh()                                                                                         # the oldest adopted gene is retested over max_adopted
over = {**CFG, "evolve": {**EVC, "max_adopted": 2, "width": 4, "neighbour_factors": []}}
st0 = EV.load_state(over)
for i, day in ((1, "2026-10-28"), (2, "2026-10-30"), (3, "2026-11-02")):
    st0["genes"][f"g00{i}"] = gene(f"g00{i}", f"Keep sentence number {i} short and plain for every viewer.", status="adopted", adopted=day, retest_after="2027-01-01")
    st0["adopted"][f"g00{i}"] = f"g00{i}"
put_state(st0)
use()
run = go(over)
op = actions(run, "open")
assert len(op) == 1 and op[0]["source"] == "retest", run.log
rg = [g for g in run.st["genes"].values() if g["kind"] == "retest"]
assert len(rg) == 1 and rg[0]["parent"] == "g001" and rg[0]["a_text"] == st0["genes"]["g001"]["text"] and rg[0]["b_text"] == "" and rg[0]["lineage"] == "g001"
assert run.st["genes"]["g001"]["retest_after"] == "" and actions(run, "prune")
print("3f over max_adopted the oldest is retested ok")

# 4. sources and retests
fresh()
both = {**CFG, "evolve": {**EVC, "width": 3, "max_changes_per_run": 1, "neighbour_factors": ["hook_type"], "focus": []}}   # the draw alone
use(claude=lambda l, p: {"genes": [{"label": "n", "text": "Open with the place name before anything else in the facts."}]})
picks = collections.Counter()
for strong in ("gene", "neighbour"):
    for d in range(30):
        st0 = EV.load_state(both)
        st0["round"]["factors"] = {"ending": ["loop", "question"], "first_frame": ["cover", "photo"]}
        st0["round"]["starts"] = {"ending": "2026-10-25", "first_frame": "2026-10-25"}
        st0["round"]["origin"] = {"ending": "round 1", "first_frame": "round 1"}
        st0["sources"][strong] = {"contests": 30, "wins": 24}
        st0["sources"]["gene" if strong == "neighbour" else "neighbour"] = {"contests": 30, "wins": 1}
        put_state(st0)
        run = go(both, str(dt.date(2026, 11, 1) + dt.timedelta(days=d)))
        picks[(strong, actions(run, "open")[0]["source"])] += 1
assert picks[("gene", "gene")] >= 27 and picks[("neighbour", "neighbour")] >= 27, picks              # the record steers, not decides
use()

fresh()
st0 = EV.load_state(CFG)                                                                          # a champion against its best rival
st0["round"].update(factors={}, starts={}, origin={})
st0["champions"] = {"hook_type": "number"}
st0["history"] = [{"factor": "hook_type", "arms": ["statement", "number"], "source": "round 1", "start": "2026-10-25", "end": "2026-11-01",
                   "verdict": "winner", "winner": "number", "effect": 1.9, "low": 1.2, "high": 2.4, "retest_after": ""},
                  {"factor": "hook_type", "arms": ["number", "question"], "source": "neighbour", "start": "2026-11-01", "end": "2026-11-08",
                   "verdict": "winner", "winner": "number", "effect": 0.7, "low": 0.5, "high": 0.9, "retest_after": ""},
                  {"factor": "hook_type", "arms": ["number", "twist"], "source": "neighbour", "start": "2026-11-01", "end": "2026-11-09",
                   "verdict": "winner", "winner": "number", "effect": 1.1, "low": 0.9, "high": 1.3, "retest_after": "2026-11-09"}]
put_state(st0)
only_retest = {**CFG, "evolve": {**EVC, "max_changes_per_run": 1, "neighbour_factors": []}}
run = go(only_retest)
assert run.st["round"]["factors"] == {"hook_type": ["number", "twist"]} or run.st["round"]["factors"]["hook_type"][0] == "number", run.st["round"]
assert run.st["round"]["factors"]["hook_type"] == ["number", "twist"] and run.st["round"]["origin"]["hook_type"] == "retest", run.st["round"]      # the closest rival
assert all(h["retest_after"] == "" for h in run.st["history"])
not_yet = go(only_retest, "2026-11-08")
assert not not_yet.st["round"]["factors"]
print("4 sources and retests ok")

# 5. drivers
r = {"genes": "gene:g001=b;gene:g002=a", "arm_hook_type": "number", "ending": "loop", "arm_length": "35 to 44 s"}
assert DRV.assigned(r, "gene:g001") == "b" and DRV.assigned(r, "gene:g002") == "a" and DRV.assigned(r, "gene:g003") == ""
assert DRV.assigned({}, "gene:g001") == "" and DRV.assigned(r, "hook_type") == "number" and DRV.assigned(r, "ending") == "loop" and DRV.assigned(r, "length") == "35 to 44 s"
rng = random.Random(3)
rows = []
for i in range(80):
    day = 25 + i % 7
    g = "b" if i % 2 else "a"
    rows.append({"short": f"E-{i}", "channel": "main", "posted": f"2026-10-{day}T12:00:00+00:00", "rel": (1.7 if g == "b" else 1.0) * rng.uniform(0.9, 1.1),
                 "arm_hook_type": ("statement", "number")[(i // 2) % 2], "genes": f"gene:g001={g}"})
F = {"hook_type": ["statement", "number"], "gene:g001": ["a", "b"]}
v = {x["factor"]: x for x in DRV.round_verdicts(rows, F, "2026-10-25", 70, "round 1")}
assert v["gene:g001"]["verdict"] == "winner" and v["gene:g001"]["winner"] == "b" and v["gene:g001"]["n_a"] + v["gene:g001"]["n_b"] == 80, v["gene:g001"]
late = {x["factor"]: x for x in DRV.round_verdicts(rows, F, "2026-10-25", 70, "round 1", starts={"gene:g001": "2026-10-29"})}
after = sum(r["posted"] >= "2026-10-29" for r in rows)
assert late["gene:g001"]["n_a"] + late["gene:g001"]["n_b"] == after < 80 and late["hook_type"]["n_a"] + late["hook_type"]["n_b"] == 80, late     # days 29 to 31 only
assert [x["n_a"] + x["n_b"] for x in DRV.round_verdicts(rows, F, "2026-10-25", starts={})] == [80, 80]
assert [x["n_a"] + x["n_b"] for x in DRV.round_verdicts(rows, F, "2026-10-25", starts={"gene:g001": "2026-10-20"})] == [80, 80]       # earlier than the round: the round's start
print("5 drivers ok")

# 6. the writer
import writer as W
fresh()
W.ROOT = SCRATCH
W.stopped = lambda: {}
day = dt.date(2026, 11, 10)
PARENT, CHILD = "Name the place in the first line, before any date or number.", "Name the place and the year in the first line."
OTHER, NEWG = "Keep every sentence under twelve words.", "Say what changes for the viewer in the last line."
st = EV.load_state(CFG); st["round"].update(factors={}, starts={}, origin={})
contest(st, "hook_type", ["number", "question"], "neighbour", "2026-11-01"); contest(st, "first_frame", ["cover", "photo"], "round 1", "2026-10-25")
contest(st, "gene:g002", ["a", "b"], "gene", "2026-11-05"); contest(st, "gene:g003", ["a", "b"], "mutate", "2026-11-05")
st["champions"] = {"hook_type": "number"}
st["genes"] = {"g001": gene("g001", PARENT, status="adopted"), "g004": gene("g004", OTHER, status="adopted"), "g002": gene("g002", NEWG),
               "g003": gene("g003", CHILD, "mutate", parent="g001", lineage="g001", a_text=PARENT)}
st["adopted"] = {"g001": "g001", "g004": "g004"}
put_state(st)
W.CFG = {**W.CFG, "evolve": EVC, "test_round": ROUND}
plans = [W.test_plan(k, "news", today=day)[1] for k in range(400)]
c = collections.Counter(p["hook_type"] for p in plans)
assert set(c) == {"number", "question"} and all(160 <= n <= 240 for n in c.values()), c                  # the champion is drawn 50/50, not kept
for f in ("gene:g002", "gene:g003", "first_frame"):
    c = collections.Counter(p[f] for p in plans)
    assert len(c) == 2 and all(160 <= n <= 240 for n in c.values()), (f, c)
assert all(p["round"] == "round 1" and p["explore"] == "no" for p in plans)
ev = W.test_plan(3, "evergreen", today=day)[1]
assert "gene:g002" in ev and "gene:g003" in ev and "hook_type" in ev                                     # genes ride on every kind
for kind in ("breaking", "fiction", "top list"): assert "gene:g002" in W.test_plan(5, kind, today=day)[1]
ex = [W.test_plan(k, "news", explore=True, today=day)[1] for k in range(200)]
assert all(p["explore"] == "yes" and p["gene:g002"] in ("a", "b") for p in ex) and 70 <= sum(p["gene:g002"] == "b" for p in ex) <= 130
assert W.arms("gene:g002") == ["a", "b"] and W.test_round(day)["factors"]["gene:g002"] == ["a", "b"]
assert "gene:g009" not in W.test_round(day)["factors"]
note = lambda picks: W.style_note(picks)
n = note({"gene:g002": "b", "gene:g003": "b"})
assert n.startswith("STYLE FOR THIS SHORT: ") and NEWG in n and CHILD in n and OTHER in n and PARENT not in n, n          # the child stands for its lineage
n = note({"gene:g002": "a", "gene:g003": "a"})
assert PARENT in n and OTHER in n and NEWG not in n and CHILD not in n and n.count(PARENT) == 1, n                       # arm a is the parent's text
n = note({"hook_type": "number"})
assert W.TESTS["hook_type"]["number"] in n and PARENT in n and OTHER in n and NEWG not in n and n.count(PARENT) == 1, n  # no contest in the picks: every adopted text
assert note({}) .startswith("STYLE FOR THIS SHORT: ") and PARENT in note({})
real = W.test_plan(2, "news", today=day)
assert real[0] == note(real[1]) and (NEWG in real[0]) == (real[1]["gene:g002"] == "b")
(AN / "drivers.csv").write_text("feature,value,lift,verdict\nhook_type,statement,1.4,push\nending,loop,1.3,push\n")
results(verdict("hook_type", "number", "question", "winner", "question"), verdict("first_frame", "cover", "photo", "even"))
assert W.winners()["hook_type"] == "question" and W.winners()["ending"] == "loop"                          # drivers push, champion, then the round's winner
results(verdict("hook_type", "statement", "number", "winner", "statement"))
assert W.winners()["hook_type"] == "number"                                                              # a stale row (other arms) does not override the champion
assert W.settled() == set(), W.settled()                                                                  # nor does a stale "even" close the live contest
results(verdict("first_frame", "cover", "photo", "even"))
assert W.settled() == {"first_frame"}
st["champions"] = {"hook_type": "number", "ending": "bogus", "length": "under 25 s"}
st["history"] = [{"factor": "length", "arms": ["under 25 s", "25 to 34 s"], "verdict": "even", "retest_after": "2099-01-01"},
                 {"factor": "series", "arms": ["single", "two parts"], "verdict": "even", "retest_after": "2099-01-01"}]
put_state(st)
assert W.winners()["ending"] == "loop" and W.winners()["length"] == "under 25 s" and W.settled() == {"first_frame", "series"}
os.remove(AN / "drivers.csv"); os.remove(AN / "round.csv")
st["champions"] = {"hook_type": "number"}; st["history"] = []; put_state(st)
assert W.winners() == {"hook_type": "number"}
# evolve off: test_plan is what it was
def old_plan(k, kind="news", explore=False, today=None, channel=None):
    done = W.settled()
    dims = [t for t in W.TESTS if t not in W.NOT_FOR.get(kind, ())]
    if explore:
        rng = random.Random(f"explore-arms:{k}")
        picks = {t: rng.choice(W.arms(t)) for t in dims if t not in W.FX}
        picks.update(replies=rng.choice(["on", "off"]), explore="yes")
        return W.style_note(picks), picks
    won = {t: a for t, a in W.winners(channel).items() if t in dims}
    rnd = W.test_round(today)
    factors = {f: [a for a in arms_ if a in W.arms(f)] for f, arms_ in (rnd.get("factors") or {}).items() if f in dims and f not in done}
    factors = {f: a for f, a in factors.items() if len(a) >= 2}
    picks = dict(won)
    for f, options in factors.items():
        if f in won and k % W.RETEST: continue
        picks[f] = random.Random(f"{rnd.get('name', 'round')}:{f}:{k}").choice(options)
    still = [t for t in dims if t not in won and t not in factors and t not in done]
    others = [t for t in won if t not in factors]
    if others and k % W.RETEST == 0:
        t = others[(k // W.RETEST) % len(others)]
        rivals = [a for a in W.arms(t) if a != won[t]]
        if rivals: picks[t] = rivals[(k // (W.RETEST * len(others))) % len(rivals)]
    elif still:
        n = max(W.OPEN_SLOTS, len(still))
        t = (still + [None] * n)[k % n]
        if t:
            options = W.arms(t)
            picks[t] = options[(k // n) % len(options)]
    picks["replies"] = "on" if k % 2 == 0 else "off"
    picks["explore"] = "no"
    if factors: picks["round"] = rnd.get("name", "round")
    return W.style_note(picks), picks
(AN / "drivers.csv").write_text("feature,value,lift,verdict\nending,loop,1.3,push\nlength,35 to 44 s,1.5,push\n")
W.CFG = {**W.CFG, "evolve": {"on": False}, "test_round": ROUND}                                            # the state file is still there, ignored
for kind in ("news", "evergreen", "true story", "breaking"):
    for ch in (None, "music"):
        for k in range(60):
            for exp in (False, True):
                assert W.test_plan(k, kind, explore=exp, today=day, channel=ch) == old_plan(k, kind, exp, day, ch), (kind, ch, k, exp)
assert not any(EV.is_gene(f) for k in range(60) for f in W.test_plan(k, "news", today=day)[1])
assert W.style_note({}) == "" and "hook_type" in W.test_round(day)["factors"] and W.winners() == {"ending": "loop", "length": "35 to 44 s"}
ends = collections.Counter(W.test_plan(k, "news", today=day)[1]["ending"] for k in range(100))
assert ends["loop"] > 75, ends                                                                            # a winner still skips its draw 4 Shorts in 5
print("6 writer ok")

# 7. analytics, the ledger and main()
assert EV.genes_column({"gene:g002": "b", "gene:g001": "a", "hook_type": "number", "gene:g009": "x"}) == "gene:g001=a;gene:g002=b"
assert EV.genes_column(None) == "" and EV.genes_column({"hook_type": "number"}) == ""
import analytics as A
src = (_p.Path(REPO_DIR) / "pipeline" / "analytics.py").read_text()
assert '"genes": o.get("genes", "")' in src and '"genes": EV.genes_column(b.get("test"))' in src
A.OUT = AN
A.CFG = {**A.CFG, "evolve": EVC, "test_round": ROUND}
assert A.round_starts()["gene:g002"] == "2026-11-05" and A.round_starts()["first_frame"] == "2026-10-25"
rf, start, per, name = A.round_factors()
assert rf["gene:g002"] == ["a", "b"] and rf["hook_type"] == ["number", "question"] and start == "2026-10-25" and name == "round 1" and "replies" in rf
A.CFG = {**A.CFG, "evolve": {"on": False}}
assert A.round_factors()[0]["hook_type"] == ["statement", "number"] and A.round_starts() == {}
A.CFG = {**A.CFG, "evolve": EVC}
prow = lambda i: {"short": f"P-{i}", "channel": "main", "posted": f"2026-11-0{1 + i % 9}T10:00:00+00:00", "views_24h": "50", "rel": 1.0,
                  "genes": f"gene:g002={'ab'[i % 2]}", "arm_hook_type": ("number", "question")[(i // 2) % 2], "first_frame": "cover"}
rows = [prow(i) for i in range(36)]
lines = A.test_progress(rows, [], today=day)
T = json.loads((AN / "tests.json").read_text())["factors"]
want = sum(int(r["posted"][8:10]) >= 5 for r in rows)
assert T["gene:g002"]["label"] == "writing instruction g002: " + NEWG[:20] and sum(a["n"] for a in T["gene:g002"]["arms"].values()) == want < 36, T["gene:g002"]
assert sum(a["n"] for a in T["hook_type"]["arms"].values()) == 36 and "writing instruction g002" in "\n".join(lines)      # hook_type counts from 1 November
import changes as C
fresh()
ids = EV.record_ledger([{"change": "Evolve: gene g001 adopted", "hypothesis": "lifts views"}, {"change": "no hypothesis"}], "2026-11-10")
assert ids == ["CH-001"] and C.ROOT == SCRATCH
row = next(csv.DictReader((AN / "changes.csv").open()))
assert row["area"] == "learning" and row["target"] == "yt_rel" and row["guardrails"] == "dead_share;avg_viewed_pct" and row["by"] == "evolve (GitHub)", row
assert "learning" in C.AREAS and all(m in C.METRICS for m in (EV.LEDGER_TARGET, *EV.LEDGER_GUARDS.split(";")))

fresh()
(SCRATCH / "config.json").write_text(json.dumps({**CFG, "evolve": {**EVC, "neighbour_factors": ["hook_type"]}}))
EV.load_tests = lambda: (TESTS, {"hook_type": {"number": "Open with a number."}}, LONG)
EV.uk_today = lambda: day
results(verdict("hook_type", "statement", "number", "winner", "number", 1.6, 1.2, 2.0))
assert EV.main([]) == 0
saved = json.loads((AN / "evolve.json").read_text())
assert saved["champions"] == {"hook_type": "number"} and saved["updated"] == str(day) and len(saved["round"]["factors"]) == 3
text = (AN / "evolve.json").read_text()
assert text == json.dumps(saved, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
log = list(csv.DictReader((AN / "evolve_log.csv").open()))
assert list(log[0]) == EV.LOG_FIELDS and [r["action"] for r in log] == ["bootstrap", "champion", "open"], log
md = (AN / "evolve.md").read_text()
for must in ("# The self-evolving round", "## Live round (3 of 3)", "## Champions", "- hook_type: number", "## Where contests come from", "| neighbour | 0 | 0 |", "## Last 10 log lines"):
    assert must in md, must
assert not any(DASH_EM in t or DASH_EN in t for t in (md, text, (AN / "evolve_log.csv").read_text()))
assert (AN / "changes.csv").exists() and "learning" in (AN / "changes.csv").read_text()
assert EV.main([]) == 0 and (AN / "evolve.json").read_text() == text and len(list(csv.DictReader((AN / "evolve_log.csv").open()))) == 3   # a quiet day changes nothing
fresh()
results(verdict("hook_type", "statement", "number", "winner", "number"))
assert EV.main(["--dry"]) == 0 and not (AN / "evolve.json").exists() and not (AN / "evolve_log.csv").exists() and not (AN / "evolve.md").exists()
(SCRATCH / "config.json").write_text(json.dumps({**CFG, "evolve": {**EVC, "on": False}}))
assert EV.main([]) == 0 and not (AN / "evolve.json").exists()                                              # off: nothing happens
print("7 analytics, ledger and main ok")
# 8. a proposal that restates an arm under test is refused (26 October: Claude's first two restated the hook test)
_st = {"genes": {}}
_texts = {"hook_type": {"statement": "Open with a plain statement of the news, naming the best-known person, band or team first (the game or title when there is none)."}}
_pick, _why = EV.pick_proposal([{"label": "x", "text": "Open with a plain statement of the news, naming the best-known person, band or team first.", "why": ""}], _st, _texts)
assert _pick is None and _why, _why
_pick, _ = EV.pick_proposal([{"label": "x", "text": "Name the source of each number in the same sentence as the number.", "why": ""}], _st, _texts)
assert _pick and _pick["text"].startswith("Name the source")
print("8 overlap with arms under test ok")
print("evolve ok")
