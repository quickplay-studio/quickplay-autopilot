"""Looks: how each Short looks and sounds (caption style, voice and pace, camera energy, colour grade).

The options live in templates/looks.json. analytics.py scores every option from how long viewers keep watching, and
voices from how many viewers don't swipe away (analytics/looks.json); choose() gives each new Short one option per dimension, mostly the best scorers and sometimes
the others (Thompson-style sampling plus a little pure exploration), and never the same look twice running.
A dimension with an "assign" split (style, 24 October: minimal text and fast pictures, 2 Shorts in 3, against the
standard look) is a fixed test instead: drawn by its split until drivers.csv proves an arm (assign_weights). The style is
recorded in the Short's look (status/<id>.json, then analytics look_style in shorts.csv, scored by drivers.py), and the
look's render settings (resolve) carry its text, graphics, pace and shade choices to render3.py and template3.html.
The closing dimension (25 October, the subscriber push: a small "Subscribe for ..." line in the last 1.5 seconds, "chip" or
"none", 50/50) is a fixed split too, drawn on its own seed so it is independent of the style; it is decided by subscribers per
1,000 views (analytics/subs.csv, "decide_by": "subs") with views as the guardrail (subs_rows), and recorded in the look.
  python pipeline/looks.py QD-031     prints the look that Short would get now
"""
import json, math, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "templates" / "looks.json"
STATS = ROOT / "analytics" / "looks.json"
LAB = ROOT / "analytics" / "lab_looks.json"     # the look lab's new options and retirements (lab.py)
EXPLORE = 0.12          # chance per dimension of a pure random pick, so nothing is written off on a few unlucky Shorts
SPREAD = 0.35           # uncertainty of an option's score with no data; shrinks with every Short measured

def catalogue(lab=None):
    """templates/looks.json plus the look lab's new options and retirements (analytics/lab_looks.json, see lab.py)."""
    cat = json.loads(CAT.read_text())
    if lab is None:
        try: lab = json.loads(LAB.read_text())
        except Exception: lab = {}
    for dim, opts in (lab.get("options") or {}).items():
        if dim in cat["dimensions"]:
            for k, o in opts.items(): cat["dimensions"][dim]["options"].setdefault(k, dict(o))
    for dim, gone in (lab.get("retired") or {}).items():
        for k, why in gone.items():
            o = cat["dimensions"].get(dim, {}).get("options", {}).get(k)
            if o is not None and not o.get("retired"): o["retired"] = why
    return cat

def load_stats():
    try: return json.loads(STATS.read_text())
    except Exception: return {}

def active(cat, dim):
    return {k: v for k, v in cat["dimensions"][dim]["options"].items() if not v.get("retired")}

def free(cat, dim):
    """The active options a dimension can choose on its own: an option marked "style_only" (the low captions) only comes
    with its style."""
    return {k: v for k, v in active(cat, dim).items() if not v.get("style_only")}

def default(cat=None):
    """The option a missing or unknown choice falls back to: the dimension's "default" when it is active (the style
    dimension's is "standard", the control: a look from before the style test, or an unknown style, renders as it always
    did), else its first option that can be chosen on its own."""
    cat = cat or catalogue(); out = {}
    for d, spec in cat["dimensions"].items():
        opts = free(cat, d) or active(cat, d)
        out[d] = spec.get("default") if spec.get("default") in opts else next(iter(opts))
    return out

DRIVERS = ROOT / "analytics" / "drivers.csv"
SUBS = ROOT / "analytics" / "subs.csv"
DECIDE_N, WIN_SHARE = 70, 0.9    # a fixed-split test (a dimension's "assign") is decided once both arms have this many Shorts

def subs_rows(dim, views_rows):
    """The verdicts of a dimension decided by subscribers (looks.json "decide_by": "subs", the closing chip of 25 October):
    analytics/subs.csv's rows for feature subs:look_<dim>, named as assign_weights reads them (look_<dim>). The subscriber
    push must not cost views, so an arm the views test (drivers.csv, look_<dim>) has cut back or paused is never a winner:
    its "push" reads "early sign"."""
    import csv
    try: rows = [r for r in csv.DictReader(SUBS.open()) if r.get("feature") == f"subs:look_{dim}"]
    except Exception: return []
    hurt = {r.get("value") for r in views_rows if r.get("feature") == f"look_{dim}" and r.get("verdict") in ("cut back", "pause", "stop")}
    return [dict(r, feature=f"look_{dim}", verdict=("early sign" if r.get("verdict") == "push" and r.get("value") in hurt else r.get("verdict")))
            for r in rows]

def assign_weights(cat, dim, drivers=None):
    """The split of a fixed test (looks.json "assign", the style test of 24 October): as written, until drivers.csv (feature
    look_<dim>, the proof rule of drivers.py) shows a "push" for one arm or a "cut back" for the other with at least
    DECIDE_N measured Shorts in every arm; then the winner gets WIN_SHARE and the others share the rest, so they stay
    measured. A dimension with "decide_by": "subs" (the closing chip) is decided by subscribers per 1,000 views instead
    (subs_rows)."""
    opts = [k for k in (cat["dimensions"][dim].get("assign") or {}) if k in active(cat, dim)]
    w = {k: float(cat["dimensions"][dim]["assign"][k]) for k in opts}
    if len(opts) < 2: return w
    rows = drivers
    if rows is None:
        try:
            import csv
            rows = list(csv.DictReader(DRIVERS.open()))
        except Exception: rows = []
        if cat["dimensions"][dim].get("decide_by") == "subs": rows = subs_rows(dim, rows)
    got = {r.get("value"): r for r in rows if r.get("feature") == f"look_{dim}" and r.get("value") in w}
    if len(got) < len(w) or any(int(float(got[k].get("n") or 0)) < DECIDE_N for k in w): return w
    win = [k for k in w if got[k].get("verdict") == "push"]
    lose = [k for k in w if got[k].get("verdict") == "cut back"]
    if len(win) != 1 and not (len(w) == 2 and len(lose) == 1): return w
    best = win[0] if len(win) == 1 else next(k for k in w if k not in lose)
    rest = (1 - WIN_SHARE) / (len(w) - 1)
    return {k: (WIN_SHARE if k == best else rest) for k in w}

def pick_weighted(rng, weights):
    tot = sum(weights.values()); x = rng.random() * tot
    for k, v in weights.items():
        x -= v
        if x < 0: return k
    return list(weights)[-1]

CAP, CAP_UNTIL = 0.7, 30    # no option above 70% of the latest looks until every option of its dimension has 30 measured Shorts


def choose(sid, recent=(), stats=None, cat=None, explore=False, energy=None):
    """One option per dimension for Short `sid`. `recent`: the looks of the latest Shorts (about 20), oldest first.
    `explore`: an exploration Short (writer.py): every dimension drawn evenly. Otherwise an option already on 70% or more
    of the recent looks sits out while its dimension still has an option under 30 measured Shorts (24 October: grade
    "natural" was on 79% to 92% of Shorts and opening "image_first" on 83% to 89%, with no proven effect).
    `energy`: the board's camera-energy arm in the factorial round (test "fx_energy", writer.py), used as it is when it
    is an active option, never for an exploration Short; the other dimensions are chosen as usual."""
    cat = cat or catalogue(); stats = load_stats() if stats is None else stats
    rng = random.Random(f"look:{sid}")
    look = {}
    recent = [r for r in recent if isinstance(r, dict)]
    fixed = {"energy": energy} if energy and not explore and energy in active(cat, "energy") else {}
    # a fixed-split test ("assign", the style test of 24 October) is drawn first with its own seed, by its split (evenly
    # for an exploration Short), never by the scores; a style that brings its own captions (minimal: the low ones) sets them
    for dim, spec in cat["dimensions"].items():
        if spec.get("assign"):
            w = assign_weights(cat, dim)
            if explore: w = {k: 1.0 for k in w}
            if w: fixed[dim] = pick_weighted(random.Random(f"{dim}:{sid}"), w)
    st = (cat["dimensions"].get("style") or {}).get("options", {}).get(fixed.get("style")) or {}
    if st.get("captions") in active(cat, "captions"): fixed["captions"] = st["captions"]
    for dim in cat["dimensions"]:
        opts = list(free(cat, dim) or active(cat, dim))
        if dim in fixed:
            look[dim] = fixed[dim]; continue
        if explore or rng.random() < EXPLORE:
            look[dim] = rng.choice(opts); continue
        seen = [r.get(dim) for r in recent[-20:] if r.get(dim)]
        n_of = lambda k: int(((stats.get("dimensions", {}).get(dim) or {}).get(k) or {}).get("n") or 0)
        if len(seen) >= 10 and len(opts) > 1 and any(n_of(k) < CAP_UNTIL for k in opts):
            over = {k for k in opts if seen.count(k) / len(seen) >= CAP}
            opts = [k for k in opts if k not in over] or opts
        best, top = opts[0], -1e9
        for k in opts:
            s = (stats.get("dimensions", {}).get(dim) or {}).get(k) or {}
            n = int(s.get("n") or 0)
            mean = float(s.get("score") or 1.0) if n else 1.0
            if n < 3: mean = max(mean, 1.08)         # try new options early
            if cat["dimensions"][dim]["options"][k].get("lab") and n < 8: mean = max(mean, 1.12)   # the lab's new option, until it can be judged
            v = rng.gauss(mean, SPREAD / math.sqrt(n + 1))
            if v > top: best, top = k, v
        look[dim] = best
    caps = [k for k in free(cat, "captions") if k != look["captions"]]
    if "captions" not in fixed and len(recent) >= 2 and recent[-1].get("captions") == recent[-2].get("captions") == look["captions"] and caps:
        look["captions"] = rng.choice(caps)
    if recent and all(recent[-1].get(d) == look[d] for d in look):
        dims = [d for d in look if len(free(cat, d)) > 1 and d not in fixed]
        if dims:
            d = rng.choice(dims); look[d] = rng.choice([k for k in free(cat, d) if k != look[d]])
    return look

def resolve(ids=None, cat=None):
    """Fill in missing or retired choices and return what the renderer needs."""
    cat = cat or catalogue(); ids = dict(ids or {})
    dflt = default(cat)                      # a look chosen before the style test has no style: it renders as it always did (standard)
    for d in cat["dimensions"]:
        if ids.get(d) not in cat["dimensions"][d]["options"]: ids[d] = dflt[d]
    st = (cat["dimensions"].get("style") or {}).get("options", {}).get(ids.get("style")) or {}
    caps = cat["dimensions"]["captions"]["options"].get(st.get("captions")) or {}
    if caps and not caps.get("retired"): ids["captions"] = st["captions"]      # a style's own captions (minimal: low)
    o = {d: cat["dimensions"][d]["options"][ids[d]] for d in cat["dimensions"]}
    render = {"captions": o["captions"].get("class", ids["captions"]), "cap": o["captions"].get("cap") or {}, "group": o["captions"].get("group", 3),
              "filter": o["grade"].get("filter", "none"), "vignette": o["grade"].get("vignette", 0),
              "motion": o["energy"].get("motion", 1.0), "punch": o["energy"].get("punch", 0.045),
              "beat_punches": bool(o["energy"].get("beat_punches")),
              "reveal_word": int((o.get("opening") or {}).get("reveal_word", 0)),
              # the style test (24 October): how much text sits on the pictures and how fast they change (render3.py,
              # template3.html); a look from before it has none of these, so it renders as it always did
              "style": ids.get("style", ""), "labels": st.get("labels", "full"), "chip": st.get("chip", "full"),
              "graphics": st.get("graphics", "cards"), "pace": st.get("pace", "board"), "shade": st.get("shade", "full"),
              # the closing chip (25 October, subscriber push): seconds of the small subscribe line at the very end, 0 for none;
              # a look from before the test has no closing, so it renders as it always did
              "closing": ids.get("closing", ""), "end_chip": float((o.get("closing") or {}).get("chip_seconds") or 0)}
    return {"ids": ids, "render": render, "voice": {"voice": o["voice"].get("voice", "F2"), "wps": o["voice"].get("wps", 3.0)}}

def describe(ids, cat=None):
    """One short line for the lineup message, e.g. 'pop captions, emma, punchy, vivid, image first'."""
    cat = cat or catalogue(); ids = resolve(ids, cat)["ids"]
    rest = [ids[d].replace("_", " ") for d in cat["dimensions"] if d not in ("captions", "closing")]
    return ", ".join([f"{ids['captions']} captions"] + rest + (["end chip"] if ids.get("closing") == "chip" else []))

if __name__ == "__main__":
    print(json.dumps(choose(sys.argv[1] if len(sys.argv) > 1 else "QD-999")))
