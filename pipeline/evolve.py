"""The self-evolving test round (26 October): keeps config.json's test round full without a person.

usage: python pipeline/evolve.py [--dry]     (evolve.yml, daily at 07:23 UTC, before the 08:10 trends run)

Until 26 October a person designed each round (config "test_round": 11 two-arm factors, drawn 50/50 and independent on every
Short, judged by drivers.round_verdicts into analytics/round.csv), and when its factors settled nothing new was tested until a
Claude session edited the config. This keeps the round full by itself:
- a settled contest leaves the round: a winner becomes a champion (analytics/evolve.json), an even or unclear factor waits
  retest_days and is then tested again;
- a free slot (up to `width`, at most max_changes_per_run new contests a day) is filled from four sources, picked by Thompson
  sampling on each source's own record (contests and wins): "neighbour" (an arm never tried against the champion), "retest"
  (a champion against its best rival, or an adopted gene against no instruction), "gene" (a writing
  instruction Claude proposes, one call a run, the free models behind it) and "mutate" (a refined child of an adopted gene,
  tested against its parent);
- a gene is a short writing instruction. Its contest is the factor "gene:<id>", arms "a" and "b": a fresh gene tests its text
  ("b") against no instruction ("a", empty), a mutation tests the child ("b") against the adopted parent ("a"). A winning gene
  is adopted into the recipe (writer.style_note adds it to every Short), a losing one is rejected, and when more than
  max_adopted are adopted the oldest is tested against no instruction again;
- the opening comes first (Charlie, 26 October: only about a third of views stay past it, and engaged views are what the
  Partner Programme counts): the focus factors (hook_type, first_frame, fx_opening) are reopened before any draw, every
  opening_gene_every-th new gene is about the first two seconds, and both are judged on the engaged share (round_metrics,
  drivers.OPENING) with a views guard.
Everything the writer, analytics and the hub need is a helper below that reads analytics/evolve.json (missing or broken: the
config's test_round stands). Standard library at import; factpack (Claude for the proposals, the free model door behind it),
validate and changes load when used. Writes analytics/evolve.json (the state), evolve_log.csv (every action) and evolve.md (a
summary), and a ledger row (area "learning") for each adoption and new champion. The proposals are the complex step, so they go
to Claude first (config evolve.model, "opus"; evolve.claude_calls_per_run, 1, a call returns every proposal); everything else
is plain code, and each gene records which model proposed it ("by").
28 October (Charlie approved, serving the Partner Programme): a winner is no longer locked in on its first win. A new champion or
an adopted gene stays in the round as a "confirming" contest: most Shorts (1 - analysis.confirm_share, 0.8) take it, the
rest keep the previous choice (draw), until analysis.confirm_n (20) Shorts a side are measured; round.csv then says confirmed
(not worse than the previous choice beyond the even band) and it is locked in, or reverted and the previous champion or no
instruction returns, with a row in analytics/decisions.csv. The win itself already passed the luck check (fdr.py: a
Benjamini-Hochberg q at analysis.fdr_q) and the joint model's veto (joint.py) in drivers.round_verdicts. A fifth source,
"joint", turns a category interaction the joint model finds clear into a writing instruction for that category, at most one
live at a time.
"""
import csv, datetime as dt, difflib, json, math, os, pathlib, random, re, sys

ROOT = pathlib.Path(os.environ.get("EVOLVE_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fdr as FDR           # the analysis settings (fdr_q, confirm_share, confirm_n) and the luck check's p-values

SOURCES = ("neighbour", "retest", "gene", "mutate", "joint")
SETTLED = ("even", "no clear difference")
GENE = "gene:"
DEFAULTS = {"on": False, "model": "opus", "claude_calls_per_run": 1, "width": 11, "max_changes_per_run": 3, "max_genes": 3, "max_new_genes_per_run": 1, "max_adopted": 6,
            "retest_days": 28, "neighbour_factors": ["hook_type", "length", "ending", "title_search", "first_frame", "fx_energy",
                                                      "fx_grade", "fx_opening", "fx_slot"],
            # Charlie, 26 October: the hook decides whether a view becomes an engaged view (what YPP counts; about a third do).
            # The opening factors go first among neighbour and retest contests, and every other new gene is an opening gene
            # (the first two seconds), judged on the engaged share like the opening factors (drivers.OPENING).
            "focus": ["hook_type", "first_frame", "fx_opening"], "opening_gene_every": 2}
LOG_FIELDS = ["date", "action", "factor", "arms", "source", "verdict", "effect", "note"]
LEDGER_TARGET, LEDGER_GUARDS = "yt_rel", "dead_share;avg_viewed_pct"      # the 24 hour views against typical; changes.py metrics
LEDGER_TARGET_OPENING, LEDGER_GUARDS_OPENING = "engaged_share", "yt_rel;dead_share"   # an opening contest's own target

# A gene (a writing instruction) must pass check_gene before it is tested: the channel's own rules (CLAUDE.md), so a model
# cannot propose its way past them.
DASH = re.compile(r"[\u2014\u2013]")
BANNED = re.compile(r"\b(?:politic\w*|election\w*|crim(?:e|inal)\w*|murder\w*|health\w*|cure\w*|diet\w*|invest\w*|stock\w*|crypto\w*|"
                    r"gambl\w*|casino\w*|betting|sex\w*|nude\w*|adult\w*|drug\w*|viral\w*)\b", re.I)
HONEST = re.compile(r"\b(?:invent\w*|fake\w*|exaggerat\w*|mislead\w*|clickbait\w*|rumou?r\w*|lie|lies|lied|lying|liar|"
                    r"ma(?:ke|de) up)\b", re.I)
NOT_VERBS = {"i", "we", "you", "they", "he", "she", "it", "this", "that", "these", "those", "there", "my", "our", "your", "their",
             "his", "her", "its", "the", "a", "an"}      # a sentence that starts like this describes; it does not instruct


def nodash(s):
    return DASH.sub(",", str(s))


def check_gene(text, others=()):
    """"" when `text` is a usable writing instruction, else the reason it is not. 20 to 220 characters; no em or en dash; none of
    the banned subjects (politics, crime, health, money, adult content, gambling, virality; also validate.BANNED); nothing about inventing, faking, lying or
    clickbait; nothing about subscribing (the subscriber push is its own test); none of validate.NEGATIVE (negative framing of
    a real person); it must read as an instruction, so its first word is capitalised and is not a pronoun or an article; and
    it is not a near duplicate (difflib ratio over 0.8) of any text in `others`."""
    t = " ".join(str(text or "").split())
    import validate
    if not 20 <= len(t) <= 220: return "length"
    if DASH.search(t): return "dash"
    if BANNED.search(t) or validate.BANNED.search(t): return "banned subject"
    if HONEST.search(t): return "honesty"
    if re.search(r"subscri", t, re.I): return "subscribe"
    if validate.NEGATIVE.search(t): return "negative framing"
    first = t.split()[0]
    if not first[0].isupper() or first.strip(",.:;'\"").lower() in NOT_VERBS: return "not an instruction"
    for o in others:
        if o and difflib.SequenceMatcher(None, t.lower(), str(o).lower()).ratio() > 0.8: return "near duplicate"
    return ""


def clean_text(t):
    return " ".join(str(t or "").split()).strip("\"' ")


# ---------------- state and the helpers the writer, analytics and the hub read ----------------
def state_path(): return ROOT / "analytics" / "evolve.json"
def log_path(): return ROOT / "analytics" / "evolve_log.csv"
def md_path(): return ROOT / "analytics" / "evolve.md"


def uk_today():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo("Europe/London")).date()


def settings(cfg):
    a = FDR.settings(cfg or {})
    return {**DEFAULTS, **((cfg or {}).get("evolve") or {}), "fdr_q": a["fdr_q"], "confirm_share": a["confirm_share"], "confirm_n": a["confirm_n"]}


def on(cfg):
    """Whether the self-evolving round is switched on (config "evolve": {"on": true})."""
    return bool(((cfg or {}).get("evolve") or {}).get("on"))


def is_gene(f): return str(f).startswith(GENE)
def gene_id(f): return str(f)[len(GENE):]


def read_state():
    """analytics/evolve.json as a dict; {} when it is missing or broken."""
    try:
        s = json.loads(state_path().read_text())
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def live_round(cfg):
    """The round in force: the evolving state's round when evolve is on and the state has one, else config "test_round"."""
    if on(cfg):
        r = read_state().get("round")
        if isinstance(r, dict) and isinstance(r.get("factors"), dict): return r
    return (cfg or {}).get("test_round") or {}


def round_metrics(cfg):
    """{gene factor: "engaged"} for the live round's opening genes (a gene with "metric": "engaged"): drivers.round_verdicts
    judges them on the engaged share, as it does the opening factors. {} when evolve is off or none is live."""
    if not on(cfg): return {}
    gs = read_state().get("genes") or {}
    return {f: "engaged" for f in (live_round(cfg).get("factors") or {})
            if is_gene(f) and (gs.get(gene_id(f)) or {}).get("metric") == "engaged"}


def round_scopes(cfg):
    """{gene factor: category} for the live contests about one category (a "joint" gene, scope.category): drivers.round_verdicts
    judges only that category's Shorts. {} when evolve is off or none is live."""
    if not on(cfg): return {}
    gs = read_state().get("genes") or {}
    return {f: (gs.get(gene_id(f)) or {})["scope"]["category"] for f in (live_round(cfg).get("factors") or {})
            if is_gene(f) and isinstance((gs.get(gene_id(f)) or {}).get("scope"), dict) and (gs[gene_id(f)]["scope"] or {}).get("category")}


def confirming(cfg=None):
    """{factor: {"arm", "prev", "n", "share", "since", ...}} the adopted winners still on trial (analytics/evolve.json
    "confirming"): each is also a live contest in the round, drawn 1 - share for the new arm and share for the previous choice
    (draw); drivers.round_verdicts judges it "confirming", then "confirmed" or "reverted". {} when evolve is off (cfg given)."""
    if cfg is not None and not on(cfg): return {}
    st = read_state()
    live = (st.get("round") or {}).get("factors") or {}
    c = st.get("confirming")
    return {f: v for f, v in c.items() if isinstance(v, dict) and f in live and v.get("arm") and v.get("prev")} if isinstance(c, dict) else {}


def draw(f, options, rng, cfg=None):
    """The arm factor f takes on one Short (writer.test_plan): 50/50 as ever, except an adopted winner still being confirmed,
    which keeps its previous choice on `share` of the Shorts (analysis.confirm_share, 0.2) and takes the new arm on the rest.
    `rng` is the Short's own seeded random.Random, so the draw repeats."""
    c = confirming(cfg).get(f)
    if c and len(options) == 2 and c["arm"] in options and c["prev"] in options and c["arm"] != c["prev"]:
        return c["prev"] if rng.random() < float(c.get("share", 0.2)) else c["arm"]
    return rng.choice(options)


def is_opening(st, f):
    """Whether contest f is about the opening: an opening factor (drivers.OPENING) or an opening gene."""
    if is_gene(f): return ((st.get("genes") or {}).get(gene_id(f)) or {}).get("metric") == "engaged"
    return f in ("hook_type", "first_frame", "fx_opening")


def champions():
    """{factor: arm} the contests have settled with a winner."""
    c = read_state().get("champions")
    return {f: a for f, a in c.items() if isinstance(a, str)} if isinstance(c, dict) else {}


def genes():
    g = read_state().get("genes")
    return g if isinstance(g, dict) else {}


def adopted_texts():
    """{lineage: instruction} for the adopted genes."""
    st = read_state(); gs = st.get("genes") or {}
    out = {}
    for lin, gid in (st.get("adopted") or {}).items():
        g = gs.get(gid) or {}
        if g.get("status") == "adopted" and str(g.get("text") or "").strip(): out[lin] = g["text"]
    return out


def gene_text(factor, arm):
    """The instruction a gene factor's arm gives the writer ("" for the control arm)."""
    g = genes().get(gene_id(factor)) or {}
    return str(g.get("a_text" if arm == "a" else "b_text") or "")


def gene_label(factor):
    g = genes().get(gene_id(factor)) or {}
    return f"writing instruction {gene_id(factor)}: {g['label']}" if g.get("label") else str(factor)


def genes_column(test):
    """The shorts.csv "genes" cell for a board's test dict: "gene:g001=b;gene:g002=a"."""
    if not isinstance(test, dict): return ""
    return ";".join(f"{k}={v}" for k, v in sorted(test.items()) if is_gene(k) and v in ("a", "b"))


def settled_factors(today=None):
    """Factors the last contest closed even or with no clear difference, with no champion, still waiting their retest and not in
    the round: writer.settled() keeps them out of the open-test rotation meanwhile."""
    st = read_state(); today = str(today or uk_today())
    live = set((st.get("round") or {}).get("factors") or {}); champs = st.get("champions") or {}
    last = {}
    for h in st.get("history") or []:
        if isinstance(h, dict) and h.get("factor") and not is_gene(h["factor"]): last[h["factor"]] = h
    return {f for f, h in last.items() if f not in live and f not in champs and h.get("verdict") in SETTLED
            and h.get("retest_after") and str(h["retest_after"]) > today}


def sentence(t):
    t = str(t).strip()
    return t if not t or t[-1] in ".!?" else t + "."


def style_texts(picks):
    """The instructions for a Short's style note: each picked gene arm's text (non-empty only), then every adopted gene's text
    unless that gene's lineage is under contest in these picks (then the picked arm's text stands for it)."""
    st = read_state(); gs = st.get("genes") or {}
    out, contested = [], set()
    for f, arm in (picks or {}).items():
        g = gs.get(gene_id(f)) if is_gene(f) else None
        if not g: continue
        contested.add(g.get("lineage"))
        t = str(g.get("a_text" if arm == "a" else "b_text") or "").strip()
        if t: out.append(sentence(t))
    for lin, gid in (st.get("adopted") or {}).items():
        g = gs.get(gid) or {}
        if lin not in contested and g.get("status") == "adopted" and str(g.get("text") or "").strip(): out.append(sentence(g["text"]))
    return out


def skeleton(cfg):
    """A new state: config's test_round copied exactly, every factor started with the round and marked "round 1"."""
    r = (cfg or {}).get("test_round") or {}
    factors = {f: list(a) for f, a in (r.get("factors") or {}).items()}
    start = str(r.get("start") or "")
    return {"round": {"name": r.get("name", "round 1"), "start": start, "per_arm": int(r.get("per_arm", 70)), "factors": factors,
                      "starts": {f: start for f in factors}, "origin": {f: "round 1" for f in factors}},
            "champions": {}, "genes": {}, "adopted": {}, "confirming": {}, "history": [],
            "sources": {s: {"contests": 0, "wins": 0} for s in SOURCES}, "updated": ""}


def load_state(cfg):
    """The state with every key present: bootstrapped from config when the file is missing or has no usable round."""
    st, base = read_state(), skeleton(cfg)
    if not (isinstance(st.get("round"), dict) and isinstance(st["round"].get("factors"), dict)): st["round"] = base["round"]
    for k in ("starts", "origin"):
        if not isinstance(st["round"].get(k), dict): st["round"][k] = dict(base["round"][k]) if k == "origin" else {}
    for f in st["round"]["factors"]:
        st["round"]["starts"].setdefault(f, st["round"].get("start") or "")
        st["round"]["origin"].setdefault(f, "round 1")
    for k in ("champions", "genes", "adopted", "confirming"):
        if not isinstance(st.get(k), dict): st[k] = {}
    if not isinstance(st.get("history"), list): st["history"] = []
    if not isinstance(st.get("sources"), dict): st["sources"] = {}
    for s in SOURCES: st["sources"].setdefault(s, {"contests": 0, "wins": 0})
    st.setdefault("updated", "")
    return st


# ---------------- one run ----------------
def ask_claude(label, prompt):
    """JSON from one Claude call (factpack.claude_call: the CLI with CLAUDE_CODE_OAUTH_TOKEN, or the Messages API with
    ANTHROPIC_API_KEY; no tools). Raises when it returns nothing."""
    import factpack
    ans, err = factpack.claude_call(label, prompt, 300)
    if ans is None: raise RuntimeError(err or f"{label}: no answer")
    return ans


def ask_free(prompt):
    """(JSON, model) from the free model chain (factpack.gemini: Gemini, Gemma, the keyed free providers). lite keeps Claude out
    of this chain, so the one Claude call a run is the one made by ask_claude. Raises when no model answers."""
    import factpack
    return factpack.gemini(prompt, None, timeout=90, temperature=0.7, lite=True)


def ask(run, prompt):
    """(answer, who) for a proposal. The complex step goes to Claude first (config evolve.model, "opus"), at most
    claude_calls_per_run calls a run (one call returns every proposal, the first usable one is taken); only when Claude
    returns nothing does the free chain answer. Raises when neither does."""
    errs = []
    if run.claude_calls < int(run.S["claude_calls_per_run"]):
        run.claude_calls += 1
        label = "claude:" + str(run.S["model"])
        try: return ask_claude(label, prompt), label
        except Exception as e: errs.append(str(e)[:100])
    try: return ask_free(prompt)
    except Exception as e: raise RuntimeError("; ".join(errs + [str(e)[:100]]))


class Run:
    """One evolve run: the state, the settings, today's date, the arms the writer can use (tests: {factor: [arms]}, texts: the
    writer's TESTS with their prompt text, exclude: arms never put in a neighbour contest) and what the run did."""
    def __init__(self, st, S, today, tests, texts=None, exclude=(), dry=False, rows=None):
        self.st, self.S, self.today = st, S, str(today)
        self.tests, self.texts, self.exclude, self.dry = tests, texts or {}, set(exclude), dry
        self.rows = rows if rows is not None else {}
        self.log, self.ledger, self.new_genes, self.added, self.claude_calls = [], [], 0, 0, 0
        self.decisions = []             # rows for analytics/decisions.csv (a reverted trial)

    def note(self, action, factor="", arms=(), source="", verdict="", effect="", note=""):
        self.log.append({"date": self.today, "action": action, "factor": factor, "arms": " vs ".join(str(a) for a in arms),
                         "source": source, "verdict": verdict, "effect": effect, "note": nodash(note)})
        print("evolve:", action, factor, " vs ".join(str(a) for a in arms), source, verdict, effect, nodash(note))

    def live_genes(self):
        return [f for f in self.st["round"]["factors"] if is_gene(f)]

    def contested(self):
        gs = self.st["genes"]
        return {(gs.get(gene_id(f)) or {}).get("lineage") for f in self.live_genes()}

    def days(self, n):
        return str(dt.date.fromisoformat(self.today) + dt.timedelta(days=int(n)))


def num(x):
    try: return round(float(x), 2)
    except (TypeError, ValueError): return ""


def read_results():
    """{factor: analytics/round.csv row}; {} when the file is missing."""
    try: return {r["factor"]: r for r in csv.DictReader(open(ROOT / "analytics" / "round.csv")) if r.get("factor")}
    except Exception: return {}


def confirm_text(S):
    return f"{round(100 * (1 - S['confirm_share']))}% of Shorts until {S['confirm_n']} a side are measured"


def begin_trial(run, f, arms, w, src, op, prev_champion):
    """An adopted winner starts its confirmation (28 October): it stays a live contest (settle keeps it in the round with a fresh
    start), drawn for the winner on 1 - confirm_share of the Shorts and for the previous choice on the rest (draw), until
    confirm_n Shorts a side are in. prev_champion: the champion before it (None: there was none, and a revert returns to that)."""
    S = run.S
    run.st["confirming"][f] = {"arm": w, "prev": arms[0] if w == arms[1] else arms[1], "since": run.today, "n": int(S["confirm_n"]),
                               "share": float(S["confirm_share"]), "source": src, "opening": bool(op), "prev_champion": prev_champion}


def settle_confirm(run, f, arms, row):
    """Step 3b: a trial's verdict in round.csv is "confirming" (nothing to do), "confirmed" (locked in: the contest leaves the
    round, the retest clock restarts) or "reverted" (the adopted winner was worse than the previous choice beyond the even band:
    the previous champion, or no champion or no instruction, returns, with a row in decisions.csv). A row from before the trial
    began (its start is not the trial's) is ignored."""
    st, S = run.st, run.S
    rnd, gs, conf = st["round"], st["genes"], st["confirming"][f]
    v = row.get("verdict")
    if v not in ("confirmed", "reverted") or str(row.get("start") or "") != str(rnd["starts"].get(f) or ""): return
    eff, low, high = num(row.get("effect")), num(row.get("low")), num(row.get("high"))
    champ, prev = conf.get("arm"), conf.get("prev")
    for k in ("factors", "starts", "origin"): rnd[k].pop(f, None)
    st["confirming"].pop(f, None)
    retest_after = "" if is_gene(f) else run.days(S["retest_days"])
    hist = {"factor": f, "arms": arms, "source": "confirm", "start": conf.get("since"), "end": run.today, "verdict": v,
            "winner": champ if v == "confirmed" else prev, "effect": eff, "low": low, "high": high, "retest_after": retest_after}
    if conf.get("opening"): hist["metric"] = "engaged"
    st["history"].append(hist)
    if v == "confirmed":
        if is_gene(f): (gs.get(gene_id(f)) or {})["retest_after"] = run.days(S["retest_days"])
        run.note("lock-in", f, arms, "confirm", v, eff, f"{champ} holds up against {prev} ({low} to {high}); locked in")
        return
    if is_gene(f):
        g = gs.get(gene_id(f)) or {}
        parent = gs.get(g.get("parent") or "")
        g["status"], g["effect"] = "rejected", eff
        st["adopted"].pop(g.get("lineage"), None)
        if g.get("kind") == "mutate" and parent and parent.get("text"):         # the parent it replaced returns
            parent["status"] = "adopted"; st["adopted"][g["lineage"]] = g.get("parent")
        what = f"writing instruction {gene_id(f)} ({g.get('label', '')}) dropped"
    else:
        old = conf.get("prev_champion")
        if old: st["champions"][f] = old
        else: st["champions"].pop(f, None)
        what = f"{f} back to {old or 'no champion'}"
    run.note("revert", f, arms, "confirm", v, eff, f"{champ} was worse than {prev} in confirmation ({low} to {high}); {what}")
    run.decisions.append({"date": run.today, "area": "Confirmation", "change": nodash(f"Revert {f}: {what}"),
                          "why": nodash(f"{champ} won its contest but was worse than {prev} over {conf.get('n')}+ Shorts a side ({eff}x for arm b, 90% interval {low} to {high})"),
                          "evidence": f"round.csv: {f} reverted, trial from {conf.get('since')}, {conf.get('n')} Shorts a side", "check_on": run.days(S["retest_days"]),
                          "by": "evolve (confirmation)"})


def settle(run, results):
    """Step 3: each live factor whose round.csv row is trusted (the factor is live and the row's arms are the live arms) and
    has a verdict of winner, even or no clear difference leaves the round, with its consequences."""
    st, S = run.st, run.S
    rnd, gs = st["round"], st["genes"]
    for f in list(rnd["factors"]):
        arms = list(rnd["factors"][f])
        if is_gene(f) and gene_id(f) not in gs:                      # a contest whose gene is gone: drop it quietly
            for k in ("factors", "starts", "origin"): rnd[k].pop(f, None)
            run.note("drop", f, arms, note="no gene record")
            continue
        row = results.get(f)
        if not row or [row.get("arm_a"), row.get("arm_b")] != arms: continue
        if f in st["confirming"]:                                     # an adopted winner on trial: only its confirmation counts
            settle_confirm(run, f, arms, row)
            continue
        v = row.get("verdict")
        if v != "winner" and v not in SETTLED: continue
        w = row.get("winner") or ""
        eff, low, high = num(row.get("effect")), num(row.get("low")), num(row.get("high"))
        start, src = rnd["starts"].get(f, rnd.get("start", "")), rnd["origin"].get(f, "")
        g0 = gs.get(gene_id(f)) if is_gene(f) else None
        trial = bool(S["confirm_n"] > 0 and v == "winner" and (g0 is None and st["champions"].get(f) != w
                                                                or g0 is not None and w == "b" and g0.get("kind", "new") in ("new", "mutate", "joint")))
        if trial: rnd["starts"][f], rnd["origin"][f] = run.today, "confirm"      # stays in the round, drawn mostly for the winner
        else:
            for k in ("factors", "starts", "origin"): rnd[k].pop(f, None)
        beat = v == "winner" and w == arms[1]                         # the challenger (arm b) won
        if src in st["sources"]:
            st["sources"][src]["contests"] += 1
            st["sources"][src]["wins"] += int(beat)
        op = is_opening(st, f)
        lifts = "lifts the share of views that stay past the opening (engaged views)" if op else "lifts a Short's views against the Shorts around it"
        hist = {"factor": f, "arms": arms, "source": src, "start": start, "end": run.today, "verdict": v, "winner": w,
                "effect": eff, "low": low, "high": high, "retest_after": "" if is_gene(f) else run.days(run.S["retest_days"])}
        if op: hist["metric"] = "engaged"
        st["history"].append(hist)
        if not is_gene(f):
            if v == "winner":
                prev = st["champions"].get(f)
                st["champions"][f] = w
                if trial: begin_trial(run, f, arms, w, src, op, prev)
                run.note("champion" if prev != w else "defended", f, arms, src, v, eff, f"{w} wins ({low} to {high})" + (f"; confirming on {confirm_text(S)}" if trial else ""))
                if prev != w:
                    run.ledger.append({"change": f"Evolve: {f} now runs {w} as its champion (won against {arms[0] if w == arms[1] else arms[1]})",
                                       "hypothesis": f"{w} {lifts} ({eff}x for arm b, 90% interval {low} to {high})", "opening": op})
            else:
                run.note("retire", f, arms, src, v, eff, f"retest after {hist['retest_after']}")
            continue
        g = gs[gene_id(f)]
        kind, parent = g.get("kind", "new"), gs.get(g.get("parent") or "")
        g["effect"] = eff
        if kind == "retest":                  # arm a: the adopted text, arm b: no instruction
            if v == "winner" and w == "b":
                st["adopted"].pop(g.get("lineage"), None)
                if parent: parent["status"], parent["why"] = "retired", f"no better than no instruction on retest ({eff}x)"
                g["status"] = "retired"
                run.note("dropped", f, arms, src, v, eff, f"{(parent or {}).get('label', '')}: no instruction did as well or better")
            else:
                g["status"] = "retired"
                if parent: parent["retest_after"] = run.days(S["retest_days"])
                run.note("kept", f, arms, src, v, eff, f"{(parent or {}).get('label', '')} survives its retest")
        elif v == "winner" and w == "b":
            g["status"], g["adopted"], g["retest_after"] = "adopted", run.today, run.days(S["retest_days"])
            st["adopted"][g["lineage"]] = gene_id(f)
            if kind == "mutate" and parent: parent["status"] = "retired"
            if trial: begin_trial(run, f, arms, "b", src, op, None)
            run.note("adopt", f, arms, src, v, eff, f"{g['label']}: {g['text']}" + (f"; confirming on {confirm_text(S)}" if trial else ""))
            run.ledger.append({"change": f"Evolve: writing instruction {gene_id(f)} adopted into the recipe: {g['text']}",
                               "hypothesis": f"Writing to this instruction {lifts} ({eff}x, 90% interval {low} to {high})", "opening": op})
        else:
            g["status"] = "rejected"
            run.note("reject", f, arms, src, v, eff, f"{g['label']}: " + ("the control won" if v == "winner" else "no difference")
                     + ("; the parent stays" if kind == "mutate" else ""))


# ---------------- candidates ----------------
def pair_tested(st, f, a, b):
    """Whether arms a and b of factor f have met, in history or in the live round."""
    pair = {a, b}
    if set((st["round"]["factors"].get(f) or [])) == pair: return True
    return any(h.get("factor") == f and set(h.get("arms") or []) == pair for h in st["history"])


def neighbour_candidates(run):
    """[(factor, [base, arm])]: for each neighbour factor not in the round, each arm the writer has that never met the champion
    (arm 0 when there is no champion). Arms in run.exclude (the long lengths need a rich pack, so a Short could be given the
    arm and then written to another: writer.LONG_NEEDS) are never used."""
    st, out = run.st, []
    for f in run.S["neighbour_factors"]:
        names = [a for a in run.tests.get(f, [])]
        if f in st["round"]["factors"] or len(names) < 2: continue
        base = st["champions"].get(f)
        if base not in names: base = names[0]
        if base in run.exclude: continue
        out += [(f, [base, a]) for a in names if a != base and a not in run.exclude and not pair_tested(st, f, base, a)]
    return out


def best_rival(st, f, champ, names):
    """The arm that came closest to beating the champion of factor f in history, or None."""
    best = None
    for h in st["history"]:
        arms = h.get("arms") or []
        if h.get("factor") != f or champ not in arms or len(arms) != 2: continue
        other = arms[0] if arms[1] == champ else arms[1]
        if other not in names or other == champ: continue
        e = h.get("effect")
        adv = 1.0 if e in ("", None, 0) else (float(e) if arms[1] == champ else 1 / float(e))      # the champion's edge
        if best is None or abs(math.log(adv)) <= best[0]: best = (abs(math.log(adv)), other)
    return best[1] if best else None


def retest_candidates(run):
    """[{"factor", "arms"} or {"gene"}]: a factor whose last history entry is due a retest and is not in the round, arms
    [champion, best rival] (the last pair when there is no champion); an adopted gene due a retest and not under contest."""
    st, today, out, seen = run.st, run.today, [], set()
    for h in reversed(st["history"]):
        f = h.get("factor")
        if f in seen or is_gene(f): continue
        seen.add(f)
        if not h.get("retest_after") or str(h["retest_after"]) > today or f in st["round"]["factors"]: continue
        names = run.tests.get(f, [])
        champ = st["champions"].get(f)
        if champ:
            rival = best_rival(st, f, champ, names)
            arms = [champ, rival] if rival and champ in names else None
        else:
            arms = list(h.get("arms") or []) if len(h.get("arms") or []) == 2 and all(a in names for a in h["arms"]) else None
        if arms and not set(arms) & run.exclude: out.append({"factor": f, "arms": arms})
    out += [{"gene": gid} for lin, gid in sorted(st["adopted"].items()) if gene_retest_due(run, lin, gid)]
    return out


def gene_retest_due(run, lin, gid):
    g = run.st["genes"].get(gid) or {}
    return (g.get("status") == "adopted" and g.get("retest_after") and str(g["retest_after"]) <= run.today
            and lin not in run.contested())


def adoptable(run):
    """[(lineage, gene id)] of adopted genes with no contest running: what a mutation can start from."""
    gs, con = run.st["genes"], run.contested()
    return [(lin, gid) for lin, gid in sorted(run.st["adopted"].items())
            if lin not in con and (gs.get(gid) or {}).get("status") == "adopted" and (gs[gid].get("text") or "").strip()]


def llm_room(run):
    return len(run.live_genes()) < run.S["max_genes"] and run.new_genes < run.S["max_new_genes_per_run"]


# ---------------- opening contests ----------------
def open_contest(run, f, arms, source):
    rnd = run.st["round"]
    rnd["factors"][f], rnd["starts"][f], rnd["origin"][f] = list(arms), run.today, source


def next_gene_id(gs):
    return "g%03d" % (max([int(m.group(1)) for k in gs for m in [re.fullmatch(r"g(\d+)", k)] if m] or [0]) + 1)


def make_gene(run, kind, prop=None, parent=None):
    """Adds a gene record and returns its id. new: arm a is no instruction, arm b the text; mutate: arm a the parent's text,
    arm b the child's; retest: arm a the adopted text, arm b no instruction."""
    gs = run.st["genes"]
    gid, kind = next_gene_id(gs), "new" if kind == "gene" else kind
    par = gs.get(parent) if parent else None
    lin = (par or {}).get("lineage") or gid
    if kind == "retest":
        g = {"label": ("retest " + str(par.get("label") or ""))[:40], "text": par["text"], "a_text": par["text"], "b_text": "",
             "why": "tests the adopted instruction against none", "by": "evolve"}
    else:
        g = {"label": nodash(prop.get("label") or prop["text"])[:40].strip(), "text": prop["text"], "b_text": prop["text"],
             "a_text": par["text"] if kind == "mutate" else "", "why": nodash(prop.get("why") or ""), "by": prop.get("by") or ""}
    metric = (par or {}).get("metric") if kind in ("retest", "mutate") else (prop or {}).get("metric")
    if metric == "engaged": g["metric"] = "engaged"           # an opening gene: judged on the engaged share (round_metrics)
    scope = (prop or {}).get("scope") or ((par or {}).get("scope") if kind in ("retest", "mutate") else None)      # a category contest stays one
    gs[gid] = {**g, "parent": parent or "", "lineage": lin, "born": run.today, "status": "live", "effect": "", "kind": kind,
               **({"scope": scope, "joint_key": (prop or {}).get("joint_key", "")} if scope else {})}
    return gid


def launch_retest_gene(run, gid):
    new = make_gene(run, "retest", parent=gid)
    run.st["genes"][gid]["retest_after"] = ""
    open_contest(run, GENE + new, ["a", "b"], "retest")
    run.note("open", GENE + new, ["a", "b"], "retest", note=f"adopted {gid} ({run.st['genes'][gid]['label']}) against no instruction")


def launch_prune(run):
    """Step 6: more adopted genes than max_adopted: the oldest is tested against no instruction."""
    st = run.st
    if len(st["adopted"]) <= run.S["max_adopted"] or len(st["round"]["factors"]) >= run.S["width"] or run.added >= run.S["max_changes_per_run"]:
        return
    con = run.contested()
    old = sorted((g.get("adopted") or g.get("born") or "", gid) for lin, gid in st["adopted"].items()
                 for g in [st["genes"].get(gid) or {}] if g.get("status") == "adopted" and lin not in con)
    if old:
        run.note("prune", GENE + old[0][1], source="retest", note=f"{len(st['adopted'])} adopted, over {run.S['max_adopted']}: the oldest is retested")
        launch_retest_gene(run, old[0][1]); run.added += 1


# ---------------- the joint model's interactions (28 October) ----------------
JOINT_CSV = "joint.csv"
JOINT_MIN_N = 15


def joint_rows():
    """The joint model's category interactions (analytics/joint.csv, joint.py, kind "interaction") as dicts with the category,
    factor and arm split out: effect, low and high are the arm's multiple in that category beyond what it does everywhere
    else. [] when the file is missing."""
    out = []
    try:
        for r in csv.DictReader(open(ROOT / "analytics" / JOINT_CSV)):
            fac, lvl = str(r.get("factor") or ""), str(r.get("level") or "")
            if r.get("kind") != "interaction" or not fac.startswith("category x ") or ": " not in lvl: continue
            cat, _, arm = lvl.partition(": ")
            try: out.append({"category": cat, "factor": fac[len("category x "):], "arm": arm, "effect": float(r["effect"]),
                             "low": float(r["low"]), "high": float(r["high"]), "n": int(float(r.get("n") or 0)), "outcome": r.get("outcome") or "views",
                             "q": float(r["q"]) if r.get("q") not in (None, "") else 1.0})
            except (KeyError, TypeError, ValueError): continue
    except Exception: return []
    return out


def joint_text(category, arm_text):
    """The writing instruction for a category-specific arm: the arm's own text, for that category's Shorts only."""
    t = " ".join(str(arm_text or "").split())
    return f"For {category} Shorts, {t[:1].lower()}{t[1:]}" if t else ""


def joint_room(run):
    """At most one joint contest is live, and the round keeps its gene room."""
    gs = run.st["genes"]
    live = [f for f in run.live_genes() if (gs.get(gene_id(f)) or {}).get("kind") == "joint"]
    return not live and len(run.live_genes()) < run.S["max_genes"]


def joint_candidates(run):
    """[{"category", "factor", "arm", "text", "key", "low"}] for category interactions the joint model finds clear (its 90%
    interval above no difference and a Benjamini-Hochberg q at or under analysis.fdr_q, 15+ Shorts behind it) whose arm has a writing instruction (run.texts) and whose factor is
    not itself under contest or confirmation (the instruction would pull against the drawn arm), never tried before
    (a gene's joint_key), best first. Needs no model: the arm's own text is the instruction."""
    st, out = run.st, []
    tried = {g.get("joint_key") for g in st["genes"].values() if g.get("joint_key")}
    others = [t for g in st["genes"].values() for t in (g.get("text"), g.get("a_text"), g.get("b_text")) if t]
    for r in joint_rows():
        f, arm = r["factor"], r["arm"]
        key = f"{r['category']}|{f}|{arm}"
        text = joint_text(r["category"], (run.texts.get(f) or {}).get(arm))
        if (r["low"] <= 1.0 or r["q"] > run.S["fdr_q"] or r["n"] < JOINT_MIN_N or not text or key in tried or f in st["round"]["factors"] or f in st["confirming"]
                or check_gene(text, others)): continue
        out.append({**r, "text": text, "key": key})
    return sorted(out, key=lambda c: (-c["low"], c["key"]))


def launch_joint(run):
    """Opens a contest for the best joint candidate: a writing instruction scoped to its category (round.csv judges only that
    category's Shorts, drivers.round_verdicts scopes), arm b the instruction and arm a none. True when one opened."""
    cands = joint_candidates(run)
    if not cands: return False
    c = cands[0]
    label = f"{c['category']}: {c['factor']} {c['arm']}"
    why = f"the joint model finds {c['arm']} on {c['factor']} does {c['effect']:.2f}x better for {c['category']} than elsewhere (90% interval from {c['low']:.2f}x, {c['n']} Shorts)"
    gid = make_gene(run, "joint", {"label": label, "text": c["text"], "why": why, "by": "joint model", "scope": {"category": c["category"]},
                                   "joint_key": c["key"], **({"metric": "engaged"} if c["outcome"] == "engaged" else {})})
    open_contest(run, GENE + gid, ["a", "b"], "joint")
    run.new_genes += 1
    run.note("open", GENE + gid, ["a", "b"], "joint", note=f"{label}: {c['text']} (a category interaction from the joint model)")
    return True


# ---------------- the model's proposals ----------------
RULES_FOR_GENES = ("The channel's rules, which every instruction must respect: anonymous, family friendly, UK English; never "
                   "politics, crime, health claims, money or investing advice, adult content or gambling; never negative about a "
                   "real person; nothing invented (every claim comes from the fact pack); no em dashes or en dashes; never ask "
                   "viewers to subscribe (that is tested on its own).")


def recent_shorts(today, days=14, n=8, key="views"):
    """(best n, weakest n) Shorts posted in the last `days` days as (views against typical, row), from analytics/shorts.csv;
    key "engaged": as (the share of views that stayed, row), Shorts with engaged data only."""
    try: rows = [r for r in csv.DictReader(open(ROOT / "analytics" / "shorts.csv")) if r.get("control_arm") != "1"]     # a control Short never teaches (control.py)
    except Exception: return [], []
    cut, ok = str(dt.date.fromisoformat(str(today)) - dt.timedelta(days=days)), []
    for r in rows:
        if str(r.get("posted_day") or "") < cut: continue
        if not str(r.get("short") or "").startswith("QD-") or not r.get("hook"): continue      # our own written Shorts only, never clips
        try: ok.append((float(r.get("yt_engaged_pct") or "") / 100 if key == "engaged" else float(r.get("views_vs_typical") or r.get("rel") or ""), r))
        except ValueError: continue
    ok.sort(key=lambda x: -x[0])
    top = ok[:n]
    return top, [x for x in ok[::-1][:n] if x not in top]


def breakouts(n=5):
    try: return list(csv.DictReader(open(ROOT / "analytics" / "breakouts.csv")))[:n]
    except Exception: return []


def short_line(rel, r, key="views"):
    how = f"{100 * rel:.0f}% of views stayed" if key == "engaged" else f"{rel:.2f}x typical"
    return (f'- "{nodash(r.get("title", ""))}" ({r.get("category", "")}, {how}). Opening line: '
            f'{nodash(str(r.get("hook", ""))[:110])}')


def build_prompt(run, kind, parent=None, n=3, opening=False):
    """The prompt for `n` new genes (kind "gene") or `n` refinements of the adopted gene `parent` (kind "mutate"). opening: an
    opening gene (the first two seconds, judged on the engaged share), which may shape the opening but never its form."""
    st = run.st
    recipe = [f"- {f}: {a}" + (f" ({run.texts[f][a]})" if run.texts.get(f, {}).get(a) else "") for f, a in sorted(st["champions"].items())]
    recipe += [f"- adopted instruction {gid}: {st['genes'][gid]['text']}" for gid in sorted(st["adopted"].values()) if gid in st["genes"]]
    past = [f'- {gid} "{g.get("label", "")}": {g.get("text", "")} ({g.get("status", "")}'
            + (f", {g['effect']}x" if g.get("effect") not in ("", None) else "") + ")" for gid, g in sorted(st["genes"].items())[-40:]]
    under = [f"- {f}: " + "; ".join(f"{a}: {run.texts[f][a]}" for a in arms if run.texts.get(f, {}).get(a))
             for f, arms in sorted(st["round"]["factors"].items()) if not is_gene(f) and any(run.texts.get(f, {}).get(a) for a in arms)]
    key = "engaged" if opening else "views"
    top, bottom = recent_shorts(run.today, key=key)
    brk = breakouts()
    aim = ("must not choose the form of the opening line (statement, question, number, superlative or twist: the hook test "
           "covers that) and must not be about the length or the ending. It is about the first two seconds whatever the hook's "
           "form: how fast the subject is named, how short and plain the first sentence is, no preamble, the tension it sets "
           "up, the promise the payoff keeps." if opening else
           "must not be about the same thing (so never about the form of the opening line, the length or the ending, which these "
           "cover). Aim at what nothing here covers: the middle beats, the order of the facts, the payoff, word choice, pacing, "
           "how the source is named, how a number is made vivid.")
    rank = ("the share of views that stayed past the opening (engaged views, what YouTube pays and judges the Partner Programme "
            "on; about a third today)" if opening else "views against typical Shorts, 1.0 is typical")
    lines = ["You help a fully automated YouTube Shorts channel (Quickplay Daily) improve how its script writer works. The writer "
             "is given a list of writing instructions on top of its fixed rules; each instruction is tested against none on real "
             "Shorts and kept only if it wins.", RULES_FOR_GENES,
             "The recipe in force now (do not repeat any of it):\n" + ("\n".join(recipe) or "- nothing adopted yet"),
             "Instructions already tried, with their verdicts (never repeat or rephrase one):\n" + ("\n".join(past) or "- none yet"),
             "Already under test: every Short is "
             "given one arm of each factor below, at random. A new instruction must work alongside ANY of these arms, must not "
             "contradict one and " + aim + "\n" + ("\n".join(under) or "- nothing"),
             f"The best Shorts of the last 14 days ({rank}):\n" + ("\n".join(short_line(*x, key=key) for x in top) or "- no data yet"),
             "The weakest Shorts of the last 14 days:\n" + ("\n".join(short_line(*x, key=key) for x in bottom) or "- no data yet")]
    if brk:
        lines.append("Recent breakouts (far above typical):\n" + "\n".join(
            f'- "{nodash(b.get("title", ""))}" ({b.get("category", "")}, {b.get("times_typical", "")}x typical)' for b in brk))
    if kind == "mutate":
        g = st["genes"][parent]
        lines.append(f"The instruction to refine was adopted after beating no instruction ({g.get('effect', '')}x): \"{g['text']}\"")
        lines.append(f"Propose {n} refinements of it. Each keeps its idea but is sharper, more concrete or better aimed, and each "
                     "differs clearly from the original and from the others.")
    elif opening:
        lines.append(f"Propose {n} new instructions for the first two seconds: what makes a viewer who sees the opening stay "
                     "rather than swipe away. Only about one view in three stays today. Look at what the Shorts most viewers stayed "
                     "with share and the weakest lack. Each must suit every hook form above, is concrete enough to follow and to "
                     "check, and differs clearly from everything above.")
    else:
        lines.append(f"Propose {n} new instructions. Look at what the best Shorts share and the weakest lack: how they open, which "
                     "name comes first, the pacing, the payoff, the ending. Each is concrete enough to follow and to check, and "
                     "differs clearly from everything above.")
    lines.append('Each instruction is one imperative sentence of 20 to 200 characters that starts with a verb ("Open with", "Name", '
                 '"End", "Use", "Say", "Keep"). Reply with JSON only: {"genes": [{"label": "up to 40 characters", "text": '
                 f'"one writing instruction, up to 200 characters", "why": "one sentence"}}]}} with {n} proposals.')
    return "\n\n".join(lines)


def proposals(ans):
    """[{"label", "text", "why"}] from a model's answer: {"genes": [...]}, a bare list, or strings."""
    items = ans.get("genes") if isinstance(ans, dict) else ans if isinstance(ans, list) else []
    out = []
    for it in items or []:
        if isinstance(it, dict): out.append({k: str(it.get(k) or "") for k in ("label", "text", "why")})
        elif isinstance(it, str): out.append({"label": "", "text": it, "why": ""})
    return out


def pick_proposal(props, st, texts=None):
    """(the first proposal that passes check_gene and is no near duplicate of any gene text or of the writer's arm texts in
    `texts` ({factor: {arm: text}}), "") or (None, the reasons)."""
    others = [t for g in st["genes"].values() for t in (g.get("text"), g.get("a_text"), g.get("b_text")) if t]
    others += [t for arms in (texts or {}).values() for t in arms.values() if t]
    why = []
    for p in props:
        text = clean_text(p.get("text"))
        r = check_gene(text, others)
        if not r: return {**p, "text": text}, ""
        why.append(r)
    return None, ", ".join(why) or "none returned"


def opening_turn(st, S):
    """Whether the next new gene is an opening gene: every `opening_gene_every`th new gene is (2: every other), and at most one
    opening gene is live at a time, so two instructions about the first two seconds never pull against each other."""
    every = int(S.get("opening_gene_every") or 0)
    gs = st.get("genes") or {}
    if every <= 0: return False
    if any(is_opening(st, f) for f in st["round"]["factors"] if is_gene(f)): return False
    since = 0
    for gid in sorted((k for k, g in gs.items() if g.get("kind") == "new"), key=lambda k: (gs[k].get("born") or "", k), reverse=True):
        if gs[gid].get("metric") == "engaged": return since >= every - 1
        since += 1
    return True


def launch_gene(run, kind, parent=None):
    """Asks Claude (the free models if it returns nothing) for genes, or refinements of the adopted `parent`, and opens a
    contest for the first usable one, recording which model proposed it (the gene's "by"). An opening gene (opening_turn, or a
    refinement of one) is asked for the first two seconds and judged on the engaged share."""
    opening = (opening_turn(run.st, run.S) if kind == "gene" else
               kind == "mutate" and (run.st["genes"].get(parent) or {}).get("metric") == "engaged")
    tag = " (an opening gene, judged on the engaged share)" if opening else ""
    if run.dry:
        run.note("plan", source=kind, note="a dry run does not ask a model" + tag)
        run.new_genes += 1
        return True
    try: ans, who = ask(run, build_prompt(run, kind, parent, opening=opening))
    except Exception as e:
        run.note("skip", source=kind, note=f"no proposal: {str(e)[:120]}")
        return False
    pick, why = pick_proposal(proposals(ans), run.st, run.texts)
    if not pick:
        run.note("skip", source=kind, note=f"no usable proposal ({why})")
        return False
    gid = make_gene(run, kind, {**pick, "by": who, **({"metric": "engaged"} if opening else {})}, parent)
    open_contest(run, GENE + gid, ["a", "b"], kind)
    run.new_genes += 1
    run.note("open", GENE + gid, ["a", "b"], kind, note=f"{run.st['genes'][gid]['label']}: {pick['text']} (by {who}){tag}")
    return True


def open_retest(run, c):
    """Opens a retest candidate (retest_candidates): a settled factor tried again, or an adopted gene against none."""
    if "gene" in c: return launch_retest_gene(run, c["gene"])
    open_contest(run, c["factor"], c["arms"], "retest")
    for h in run.st["history"]:
        if h.get("factor") == c["factor"]: h["retest_after"] = ""
    run.note("open", c["factor"], c["arms"], "retest", note="a settled factor tried again")


def focus_first(run):
    """Charlie, 26 October: the opening decides whether a view becomes an engaged view, so each focus factor (hook_type,
    first_frame, fx_opening) that is not in the round is reopened before anything else is drawn: its next arm never tried
    against the champion (hook_type: question, superlative, twist), else a retest that is due."""
    st, S = run.st, run.S
    for f in S.get("focus") or []:
        if len(st["round"]["factors"]) >= S["width"] or run.added >= S["max_changes_per_run"]: return
        if f in st["round"]["factors"]: continue
        nb = [arms for g, arms in neighbour_candidates(run) if g == f]
        rt = [c for c in retest_candidates(run) if c.get("factor") == f]
        if nb:
            open_contest(run, f, nb[0], "neighbour")
            run.note("open", f, nb[0], "neighbour", note="an opening factor (focus): an arm never tried against the champion")
        elif rt: open_retest(run, rt[0])
        else: continue
        run.added += 1


def fill(run):
    """Steps 4 to 6: up to max_changes_per_run new contests, until the round holds `width`. The source of each is drawn by
    Thompson sampling (Beta(1 + wins, 1 + contests - wins)) among the sources with something to try, seeded by date and
    attempt so a run repeats; a source that cannot deliver (no model answer) is left out for the rest of the run."""
    st, S = run.st, run.S
    launch_prune(run)
    focus_first(run)
    failed, i = set(), 0
    while len(st["round"]["factors"]) < S["width"] and run.added < S["max_changes_per_run"] and i < 12:
        i += 1
        cands = {"neighbour": neighbour_candidates(run), "retest": retest_candidates(run)}
        have = {"neighbour": bool(cands["neighbour"]), "retest": bool(cands["retest"]), "gene": llm_room(run),
                "mutate": llm_room(run) and bool(adoptable(run)), "joint": joint_room(run) and bool(joint_candidates(run))}
        avail = [s for s in SOURCES if have[s] and s not in failed]
        if not avail: break
        rng = random.Random(f"evolve:{run.today}:{i}")
        draw = {}
        for s in avail:
            c, w = int(st["sources"][s]["contests"]), int(st["sources"][s]["wins"])
            draw[s] = rng.betavariate(1 + min(w, c), 1 + max(0, c - w))
        src = max(avail, key=lambda s: draw[s])
        ok = False
        if src == "neighbour":
            f, arms = rng.choice(cands["neighbour"])
            open_contest(run, f, arms, "neighbour")
            run.note("open", f, arms, "neighbour", note="an arm never tried against the champion")
            ok = True
        elif src == "retest":
            open_retest(run, rng.choice(cands["retest"]))
            ok = True
        elif src == "gene": ok = launch_gene(run, "gene")
        elif src == "joint": ok = launch_joint(run)
        else:
            lin, gid = rng.choice(adoptable(run))
            ok = launch_gene(run, "mutate", gid)
        if ok: run.added += 1
        else: failed.add(src)


# ---------------- writing the record ----------------
def dump(st):
    return json.dumps(st, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def append_log(rows):
    p = log_path()
    new = not p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS, lineterminator="\n")
        if new: w.writeheader()
        w.writerows([{k: r.get(k, "") for k in LOG_FIELDS} for r in rows])


DEC_FIELDS = ["date", "area", "change", "why", "evidence", "check_on", "by"]


def append_decisions(rows):
    """Rows for analytics/decisions.csv (the Recipe's changes; a reverted trial is one), header written when the file is new."""
    if not rows: return
    p = ROOT / "analytics" / "decisions.csv"
    new = not p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DEC_FIELDS, extrasaction="ignore", lineterminator="\n")
        if new: w.writeheader()
        w.writerows([{k: r.get(k, "") for k in DEC_FIELDS} for r in rows])


def log_tail(n=10):
    try: return list(csv.DictReader(open(log_path())))[-n:]
    except Exception: return []


def render_md(st, S):
    """analytics/evolve.md: the live round, champions, genes, how each source has paid off and the last 10 log lines."""
    rnd, gs = st["round"], st["genes"]
    L = ["# The self-evolving round", "",
         f"Updated {st.get('updated') or 'not yet'}. pipeline/evolve.py runs daily (evolve.yml): it retires settled contests, keeps "
         "winners as champions, opens new contests from four sources, adopts winning writing instructions (genes) into the recipe "
         "and prunes them. Settings: config.json evolve.", "",
         "Opening contests (hook_type, first_frame, fx_opening and the opening genes, marked below) are judged on the engaged "
         "share, the share of views that stay past the opening (what YouTube counts for the Partner Programme), and are reopened "
         "first when they settle; a win there that costs views is withheld.", "",
         f"## Live round ({len(rnd['factors'])} of {S['width']})", "", "| factor | arms | origin | started |", "|---|---|---|---|"]
    for f, arms in rnd["factors"].items():
        g = gs.get(gene_id(f)) if is_gene(f) else None
        name = (f"writing instruction {gene_id(f)}: {g.get('label', '')}" if g else f) + (" (opening)" if is_opening(st, f) else "")
        L.append(f"| {name} | {' vs '.join(arms)} | {rnd['origin'].get(f, '')} | {rnd['starts'].get(f, '')} |")
    res = read_results()
    trial = st.get("confirming") or {}
    L += ["", f"## Confirming ({len(trial)})", "",
          f"A new champion or adopted gene is kept for {round(100 * (1 - S['confirm_share']))}% of Shorts while the previous choice keeps "
          f"{round(100 * S['confirm_share'])}%, until {S['confirm_n']} Shorts a side are measured: then it is locked in (not worse than "
          "the previous choice beyond the even band) or reverted.", ""]
    L += [f"- {f}: {c.get('arm')} against the previous {c.get('prev')}, since {c.get('since')}; "
          f"{(res.get(f) or {}).get('n_a', '?')} and {(res.get(f) or {}).get('n_b', '?')} Shorts so far of {c.get('n')} a side, "
          f"{(res.get(f) or {}).get('verdict') or 'no reading yet'}" for f, c in sorted(trial.items())] or ["- none"]
    L += ["", "## Champions", ""] + ([f"- {f}: {a}" + (" (confirming)" if f in trial else "") for f, a in sorted(st["champions"].items())] or ["- none yet"])
    adopted = [(lin, gid) for lin, gid in sorted(st["adopted"].items()) if gid in gs]
    L += ["", f"## Adopted genes ({len(adopted)} of at most {S['max_adopted']})", ""]
    L += [f"- {gid} ({gs[gid].get('label', '')}): {gs[gid].get('text', '')} Effect {gs[gid].get('effect', '')}x, adopted {gs[gid].get('adopted', '')}, proposed by {gs[gid].get('by') or 'unknown'}."
          for lin, gid in adopted] or ["- none yet"]
    live = [gid for f in rnd["factors"] if is_gene(f) for gid in [gene_id(f)] if gid in gs]
    L += ["", "## Genes under test", ""] + ([f"- {gid} ({gs[gid].get('kind', '')}{', opening, judged on the engaged share' if gs[gid].get('metric') == 'engaged' else ''}{', ' + gs[gid]['scope']['category'] + ' Shorts only' if (gs[gid].get('scope') or {}).get('category') else ''}): {gs[gid].get('label', '')}" for gid in live] or ["- none"])
    n_rej = sum(g.get("status") == "rejected" for g in gs.values())
    L += ["", f"Rejected so far: {n_rej}. Retired: {sum(g.get('status') == 'retired' for g in gs.values())}.", "",
          "## Where contests come from", "", "| source | contests settled | wins | win rate |", "|---|---|---|---|"]
    for s in SOURCES:
        c, w = st["sources"][s]["contests"], st["sources"][s]["wins"]
        L.append(f"| {s} | {c} | {w} | {f'{100 * w / c:.0f}%' if c else 'no contests yet'} |")
    L += ["", "A win is a challenger (arm b, the new arm) that beat the incumbent.", "", "## Last 10 log lines", ""]
    L += [f"- {r.get('date')} {r.get('action')} {r.get('factor')} {r.get('arms')} {r.get('source')} {r.get('verdict')} {r.get('note')}".rstrip()
          for r in log_tail()] or ["- nothing yet"]
    return nodash("\n".join(L)) + "\n"


def record_ledger(entries, today):
    """A change ledger row for each adoption and new champion (analytics/changes.csv); a failure is logged and carried past."""
    out = []
    try:
        import changes as C
        C.ROOT = ROOT
    except Exception as e:
        print("evolve: ledger unavailable:", str(e)[:100]); return out
    for e in entries:
        try:
            tg, gd = (LEDGER_TARGET_OPENING, LEDGER_GUARDS_OPENING) if e.get("opening") else (LEDGER_TARGET, LEDGER_GUARDS)
            r = C.add("learning", e["change"], e["hypothesis"], tg, gd, date=today, by="evolve (GitHub)")
            out.append(r["id"])
        except Exception as ex:
            print("evolve: ledger row failed:", str(ex)[:120])
    return out


def load_tests():
    """(tests, texts, exclude) from the writer: the arms it can use now, its prompt text per arm, and the arms never put in a
    neighbour contest (writer.LONG_NEEDS: a long arm falls back to another length when the pack is short, which would skew
    the contest)."""
    import writer as W
    return {f: list(W.arms(f)) for f in W.TESTS}, W.TESTS, set(W.LONG_NEEDS)


def run_once(cfg, today, tests, texts=None, exclude=(), dry=False):
    """The whole run on the state file's content (nothing written): returns the Run, whose .st is the new state."""
    S = settings(cfg)
    run = Run(load_state(cfg), S, today, tests, texts, exclude, dry)
    if not state_path().exists(): run.note("bootstrap", note=f"round copied from config test_round ({len(run.st['round']['factors'])} factors)")
    settle(run, read_results())
    fill(run)
    return run


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry" in argv
    cfg = json.loads((ROOT / "config.json").read_text())
    if not on(cfg): return 0
    tests, texts, exclude = load_tests()
    today = str(uk_today())
    run = run_once(cfg, today, tests, texts, exclude, dry)
    if not run.log: print("evolve: nothing to do;", len(run.st["round"]["factors"]), "live contests")
    if dry:
        print("evolve: dry run, nothing written")
        return 0
    if run.log or not state_path().exists(): run.st["updated"] = today
    record_ledger(run.ledger, today)
    append_decisions(run.decisions)
    state_path().parent.mkdir(parents=True, exist_ok=True)
    state_path().write_text(dump(run.st))
    if run.log: append_log(run.log)
    md_path().write_text(render_md(run.st, run.S))
    return 0


if __name__ == "__main__":
    sys.exit(main())
