"""The joint model (28 October): every test factor at once.

usage: python pipeline/joint.py [--dry]      (analytics.yml, after the hourly numbers and the verdicts; a failure never blocks the commit)

The verdicts in drivers.py and round_verdicts compare one choice at a time, each adjusted for the others by a plain regression
on the Shorts that carry the arm. This fits ONE regularised regression of the round's outcome, log(24-hour views / the same-UK-day
channel median) (log rel), on every test factor together:
- each factor of the round (the live contests, the writer-model test, the title tests, the subscribe line, the comment replies,
  the writing-instruction genes) as one-hot columns for its two arms, a Short that took neither arm having both at 0;
- the controls: channel (one-hot), exploration Short, topic heat (heat.py, less the channel-day's mean), weekday posted (UK);
- pairwise interactions of category with each factor (category one-hot times the factor's contrast, +0.5 arm B, -0.5 arm A), the
  extra effect an arm has in that category beyond what it does everywhere.
Ridge shrinkage with a penalty sigma^2 / tau^2 per group (the empirical-Bayes form of a ridge: tau, the spread of true effects,
is 0.25 for a factor, 0.15 for an interaction, so interactions are shrunk harder; sigma is the data's own residual spread,
found by one refit; controls get a light tau of 1). Intervals are 90% bootstrap intervals over Shorts (seeded, so a run repeats).
The opening factors (drivers.OPENING and the engaged genes) are fitted a second time on the engaged share, as round_verdicts judges
them (log((engaged + 10 p0) / (views + 10))).

Outputs: analytics/joint.csv (factor, level, effect, low, high, n, outcome, kind, p, q): effect is the multiple an arm gets against the
factor's other arm (main), or the extra multiple in a category (interaction, factor "category x <factor>", level "<category>:
<arm>"), with its 90% interval; kind "control" rows are the controls. p is a z test of the fitted effect against its bootstrap
spread and q its Benjamini-Hochberg value across the interactions (or the main effects) of that outcome: with 100 or more
interaction cells one clears a 90% interval by luck most runs, so evolve.py only acts on an interaction with q at or under
analysis.fdr_q as well. analytics/joint.md: the top effects and every interaction whose interval clears no difference.
Used twice: drivers.round_verdicts withholds a winner whose arm the joint interval puts wholly on the losing side, and
evolve.py turns a clear interaction into a category-specific writing instruction (source "joint", one live at a time).
Needs numpy (the analytics workflow installs it, pinned)."""
import csv, datetime as dt, json, math, pathlib, sys
from zoneinfo import ZoneInfo
import numpy as np
import fdr as FDR           # p-values and Benjamini-Hochberg: a category interaction must also pass the luck check

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
UK = ZoneInfo("Europe/London")
TAU_MAIN, TAU_INT, TAU_CTRL, SIGMA0 = 0.25, 0.15, 1.0, 0.8
BOOT, SEED, MIN_CELL, MIN_ARM = 200, 7, 8, 3
ENG_K = 10.0                # as drivers.ENG_K
OPENING = ("hook_type", "first_frame", "fx_opening")
# the title tests, as analytics.TITLE_FACTORS (they ride beside the round)
TITLE_FACTORS = {"title_emoji": ["emoji", "none"], "title_answer": ["stated", "held back"], "sub_push": ["spoken", "none"]}
FIELDS = ["factor", "level", "effect", "low", "high", "n", "outcome", "kind", "p", "q"]


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError): return None


def factors_now(cfg=None):
    """({factor: [arm_a, arm_b]}, {opening factors}) as analytics.round_factors builds the round, from the live round
    (evolve.live_round) or config's test_round."""
    import evolve as EV
    cfg = cfg if cfg is not None else json.loads((ROOT / "config.json").read_text())
    rnd = EV.live_round(cfg)
    factors = {f: list(a) for f, a in (rnd.get("factors") or {}).items() if len(a) == 2}
    wt = cfg.get("writer_test") or {}
    if len(wt.get("arms") or []) == 2: factors["writer_arm"] = list(wt["arms"])
    for f, arms in TITLE_FACTORS.items(): factors.setdefault(f, list(arms))
    factors.setdefault("replies", ["on", "off"])
    opening = {f for f in factors if f in OPENING} | set(EV.round_metrics(cfg))
    return factors, opening


def uk_day(r):
    try: return dt.datetime.fromisoformat(str(r["posted"])).astimezone(UK).date().isoformat()
    except (KeyError, ValueError, TypeError): return str(r.get("posted_day") or "")


def weekday(r):
    d = uk_day(r)
    try: return dt.date.fromisoformat(d).strftime("%a")
    except ValueError: return ""


def design(rows, factors, interactions=True):
    """(X, names, kinds, tau, meta): the design matrix of the module docstring. names: (group, label) per column; tau: the prior
    spread per column (0 = unpenalised intercept)."""
    import drivers
    try:
        import heat as HEAT
        cen = HEAT.centred(rows)
        hv = [cen.get(id(r), 0.0) for r in rows]
        if sum(1 for r in rows if HEAT.value(r) is not None) < 3 or max(hv) - min(hv) < 1e-9: hv = None
    except Exception: hv = None
    n = len(rows)
    cols, names, tau = [np.ones(n)], [("intercept", "intercept")], [0.0]
    for ch in sorted({r.get("channel") or "main" for r in rows}):
        cols.append(np.array([1.0 if (r.get("channel") or "main") == ch else 0.0 for r in rows])); names.append(("channel", ch)); tau.append(TAU_CTRL)
    cols.append(np.array([1.0 if r.get("explore") == "yes" else 0.0 for r in rows])); names.append(("control", "exploration Short")); tau.append(TAU_CTRL)
    if hv is not None: cols.append(np.array(hv)); names.append(("control", "topic heat (per point)")); tau.append(TAU_CTRL)
    for wd in sorted({weekday(r) for r in rows} - {""}):
        cols.append(np.array([1.0 if weekday(r) == wd else 0.0 for r in rows])); names.append(("weekday", wd)); tau.append(TAU_CTRL)
    arm = {f: np.array([drivers.assigned(r, f) for r in rows]) for f in factors}
    usable = {}
    for f, (a, b) in factors.items():
        na, nb = int((arm[f] == a).sum()), int((arm[f] == b).sum())
        if min(na, nb) < MIN_ARM: continue
        usable[f] = (a, b)
        for lv in (a, b):
            cols.append((arm[f] == lv).astype(float)); names.append(("factor", f"{f}\t{lv}")); tau.append(TAU_MAIN)
    if interactions:
        cats = np.array([r.get("category") or "" for r in rows])
        for c in sorted(set(cats) - {""}):
            inc = cats == c
            for f, (a, b) in usable.items():
                code = np.where(arm[f] == b, 0.5, np.where(arm[f] == a, -0.5, 0.0)) * inc
                if int(((arm[f] == a) & inc).sum()) < MIN_ARM or int(((arm[f] == b) & inc).sum()) < MIN_ARM or int(inc.sum()) < MIN_CELL: continue
                cols.append(code); names.append(("interaction", f"{c}\t{f}")); tau.append(TAU_INT)
    return np.column_stack(cols), names, np.array(tau), usable


def ridge(X, y, pen):
    """Solve (X'X + diag(pen)) b = X'y; the intercept is unpenalised (a hair of ridge keeps it solvable)."""
    A = X.T @ X + np.diag(np.where(pen > 0, pen, 1e-8))
    return np.linalg.solve(A, X.T @ y)


def fit_one(X, y, tau, seed=SEED, boot=BOOT):
    """(beta, draws, sigma, edf): the ridge fit (sigma from one refit) and `boot` seeded bootstrap refits over rows."""
    n = len(y)
    sig = SIGMA0
    for _ in range(2):
        pen = np.where(tau > 0, (sig / np.maximum(tau, 1e-9)) ** 2, 0.0)
        beta = ridge(X, y, pen)
        A = X.T @ X + np.diag(np.where(pen > 0, pen, 1e-8))
        edf = float(np.trace(X @ np.linalg.solve(A, X.T)))
        sig = max(0.05, math.sqrt(max(1e-9, float(((y - X @ beta) ** 2).sum())) / max(1.0, n - edf)))
    pen = np.where(tau > 0, (sig / np.maximum(tau, 1e-9)) ** 2, 0.0)
    rng = np.random.default_rng(seed)
    draws = np.empty((boot, X.shape[1]))
    for i in range(boot):
        idx = rng.integers(0, n, n)
        draws[i] = ridge(X[idx], y[idx], pen)
    return beta, draws, sig, edf


def outcome_rows(rows, kind):
    """(rows kept, y): "views" is log rel on the Shorts with a rel; "engaged" the engaged share's log on those with engaged
    views (drivers.round_verdicts' own outcome)."""
    import drivers
    ok = [r for r in rows if num(r.get("rel")) is not None and num(r.get("rel")) > 0]
    if kind == "views": return ok, np.array([math.log(max(0.05, float(r["rel"]))) for r in ok])
    pairs = [(r, drivers.engaged_pair(r)) for r in ok]
    pairs = [(r, p) for r, p in pairs if p]
    if not pairs: return [], np.array([])
    p0 = max(0.01, sum(e for _, (e, _) in pairs) / sum(v for _, (_, v) in pairs))
    return [r for r, _ in pairs], np.array([math.log((e + ENG_K * p0) / (v + ENG_K)) for _, (e, v) in pairs])


def ratio(v): return float(math.exp(max(-8.0, min(8.0, v))))


def analyse(rows, factors, opening=(), seed=SEED, boot=BOOT):
    """{"rows": [joint.csv rows], "meta": {...}} for shorts.csv-like `rows` (each with rel, channel, posted, category, explore, the
    factors' arm columns, engaged views and heat when known). factors: {factor: [arm_a, arm_b]}; opening: the factors also fitted
    on the engaged share."""
    out, meta = [], {}
    for kind in ("views", "engaged"):
        sub, y = outcome_rows(rows, kind)
        fs = {f: a for f, a in factors.items() if kind == "views" or f in set(opening)}
        if len(y) < 20 or not fs: meta[kind] = {"n": len(y)}; continue
        X, names, tau, usable = design(sub, factors)       # all factors in the model; the engaged outcome reports only the opening ones
        beta, draws, sig, edf = fit_one(X, y, tau, seed, boot)
        meta[kind] = {"n": len(y), "sigma": round(sig, 3), "edf": round(edf, 1), "columns": len(names)}
        col = {nm: i for i, nm in enumerate(names)}

        def contrast(i_pos, i_neg, sign=1.0):
            v = sign * (beta[i_pos] - (beta[i_neg] if i_neg is not None else 0.0))
            d = sign * (draws[:, i_pos] - (draws[:, i_neg] if i_neg is not None else 0.0))
            lo, hi = np.percentile(d, [5, 95])
            sd = float(d.std(ddof=1))
            return v, lo, hi, (FDR.normal_p(v / sd) if sd > 1e-12 else 1.0)
        cats = np.array([r.get("category") or "" for r in sub])
        import drivers
        arms = {f: np.array([drivers.assigned(r, f) for r in sub]) for f in usable}
        for f, (a, b) in usable.items():
            if f not in fs: continue
            ia, ib = col[("factor", f"{f}\t{a}")], col[("factor", f"{f}\t{b}")]
            for lv, ip, ineg in ((a, ia, ib), (b, ib, ia)):
                v, lo, hi, pv = contrast(ip, ineg)
                out.append({"factor": f, "level": lv, "effect": round(ratio(v), 3), "low": round(ratio(lo), 3), "high": round(ratio(hi), 3),
                            "n": int((arms[f] == lv).sum()), "outcome": kind, "kind": "main", "p": pv, "q": None})
        for (grp, label), i in col.items():
            if grp == "interaction":
                c, f = label.split("\t")
                if f not in fs: continue
                a, b = usable[f]
                inc = cats == c
                for lv, sign in ((b, 1.0), (a, -1.0)):
                    v, lo, hi, pv = contrast(i, None, sign)
                    out.append({"factor": f"category x {f}", "level": f"{c}: {lv}", "effect": round(ratio(v), 3), "low": round(ratio(lo), 3),
                                "high": round(ratio(hi), 3), "n": int(((arms[f] == lv) & inc).sum()), "outcome": kind, "kind": "interaction",
                                "p": pv, "q": None})
            elif grp in ("control", "channel") and kind == "views":
                v, lo, hi, pv = contrast(i, None)
                out.append({"factor": grp, "level": label, "effect": round(ratio(v), 3), "low": round(ratio(lo), 3), "high": round(ratio(hi), 3),
                            "n": int(round(float((X[:, i] != 0).sum()))), "outcome": kind, "kind": "control", "p": pv, "q": None})
        for fam in ("main", "interaction"):         # the luck check, one family per kind and outcome (a cell's two arms are one comparison)
            mine = [r for r in out if r["outcome"] == kind and r["kind"] == fam]
            uniq = {}
            for r in mine: uniq.setdefault((r["factor"], r["level"].split(": ")[0]) if fam == "interaction" else r["factor"], r["p"])
            keys = list(uniq)
            qs = dict(zip(keys, FDR.bh([uniq[k] for k in keys])))
            for r in mine: r["q"] = qs[(r["factor"], r["level"].split(": ")[0]) if fam == "interaction" else r["factor"]]
    for r in out:
        r["p"] = "" if r["p"] is None else round(r["p"], 4)
        r["q"] = "" if r["q"] is None else round(r["q"], 3)
    return {"rows": out, "meta": meta}


def clear(r): return float(r["low"]) > 1.0 or float(r["high"]) < 1.0


def render_md(res, today=""):
    rows, meta = res["rows"], res["meta"]
    L = ["# The joint model (every test factor at once)", "",
         f"Updated {today}. pipeline/joint.py: one ridge regression of log(24-hour views / the same-UK-day channel median) on every factor "
         "of the round at once, with channel, exploration, topic heat and weekday held fixed, plus category-by-factor interactions shrunk "
         "harder. Opening factors are fitted again on the engaged share. Intervals are 90% bootstrap intervals (seeded). An effect is the "
         "multiple an arm gets against the factor's other arm; a main effect whose interval sits wholly on the losing side withholds a "
         "pairwise winner (drivers.round_verdicts), and a clear interaction is offered to evolve.py as a category-specific writing "
         "instruction (source joint).", ""]
    for k, m in meta.items():
        L.append(f"- {k}: " + (f"{m['n']} Shorts, {m['columns']} columns, residual spread {m['sigma']}, effective parameters {m['edf']}" if m.get("sigma") else f"{m.get('n', 0)} Shorts (too few to fit)"))
    mains = sorted((r for r in rows if r["kind"] == "main" and float(r["effect"]) >= 1.0), key=lambda r: -abs(math.log(float(r["effect"]))))
    L += ["", "## Top main effects (the better arm of each factor)", "", "| factor | arm | outcome | effect | 90% interval | Shorts | clear |", "|---|---|---|---|---|---|---|"]
    L += [f"| {r['factor']} | {r['level']} | {r['outcome']} | {r['effect']}x | {r['low']}x to {r['high']}x | {r['n']} | {'yes' if clear(r) else 'no'} |" for r in mains[:12]] or ["| none | | | | | | |"]
    ints = [r for r in rows if r["kind"] == "interaction" and clear(r)]
    qlim = FDR.settings()["fdr_q"]
    L += ["", "## Interactions whose interval clears no difference", "",
          f"{len(ints)} of {sum(1 for r in rows if r['kind'] == 'interaction')} interaction rows. With this many cells some clear a 90% interval by luck, "
          f"so only those with q at or under {qlim} (Benjamini-Hochberg) are offered to evolve.py.", ""]
    L += [f"- {r['level']} on {r['factor'][len('category x '):]} ({r['outcome']}): {r['effect']}x beyond its usual effect, 90% interval {r['low']}x to {r['high']}x, "
          f"{r['n']} Shorts; q {r['q']}, " + ("passes the luck check" if r["q"] != "" and float(r["q"]) <= qlim else "fails the luck check")
          for r in sorted(ints, key=lambda r: -abs(math.log(float(r["effect"]))))[:15]] or ["- none yet"]
    ctr = [r for r in rows if r["kind"] == "control" and r["factor"] == "control"]
    if ctr: L += ["", "## Controls", ""] + [f"- {r['level']}: {r['effect']}x ({r['low']}x to {r['high']}x)" for r in ctr]
    return "\n".join(L) + "\n"


def load_rows(path=None):
    """shorts.csv as dicts with rel set from views_vs_typical where the 24-hour views are in (as analytics sets rel)."""
    rows = list(csv.DictReader(open(path or ROOT / "analytics" / "shorts.csv")))
    for r in rows: r["rel"] = r.get("views_vs_typical") if r.get("views_24h") not in ("", None) else ""
    return rows


def write(out_dir, res, today=""):
    out_dir = pathlib.Path(out_dir)
    with (out_dir / "joint.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n"); w.writeheader(); w.writerows(res["rows"])
    (out_dir / "joint.md").write_text(render_md(res, today))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    factors, opening = factors_now()
    rows = load_rows()
    res = analyse(rows, factors, opening)
    today = dt.datetime.now(UK).date().isoformat()
    if "--dry" in argv:
        print(render_md(res, today)); return 0
    write(ROOT / "analytics", res, today)
    print("joint:", {k: v.get("n") for k, v in res["meta"].items()}, f"{len(res['rows'])} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
