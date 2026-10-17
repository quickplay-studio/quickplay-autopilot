"""Looks: how each Short looks and sounds (caption style, voice and pace, camera energy, colour grade).

The options live in templates/looks.json. analytics.py scores every option from how long viewers keep watching
(analytics/looks.json); choose() gives each new Short one option per dimension, mostly the best scorers and sometimes
the others (Thompson-style sampling plus a little pure exploration), and never the same look twice running.
  python pipeline/looks.py QD-031     prints the look that Short would get now
"""
import json, math, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "templates" / "looks.json"
STATS = ROOT / "analytics" / "looks.json"
EXPLORE = 0.12          # chance per dimension of a pure random pick, so nothing is written off on a few unlucky Shorts
SPREAD = 0.35           # uncertainty of an option's score with no data; shrinks with every Short measured

def catalogue():
    return json.loads(CAT.read_text())

def load_stats():
    try: return json.loads(STATS.read_text())
    except Exception: return {}

def active(cat, dim):
    return {k: v for k, v in cat["dimensions"][dim]["options"].items() if not v.get("retired")}

def default(cat=None):
    cat = cat or catalogue()
    return {d: next(iter(active(cat, d))) for d in cat["dimensions"]}

def choose(sid, recent=(), stats=None, cat=None):
    """One option per dimension for Short `sid`. `recent`: the looks of the latest Shorts, oldest first."""
    cat = cat or catalogue(); stats = load_stats() if stats is None else stats
    rng = random.Random(f"look:{sid}")
    look = {}
    for dim in cat["dimensions"]:
        opts = list(active(cat, dim))
        if rng.random() < EXPLORE:
            look[dim] = rng.choice(opts); continue
        best, top = opts[0], -1e9
        for k in opts:
            s = (stats.get("dimensions", {}).get(dim) or {}).get(k) or {}
            n = int(s.get("n") or 0)
            mean = float(s.get("score") or 1.0) if n else 1.0
            if n < 3: mean = max(mean, 1.08)         # try new options early
            v = rng.gauss(mean, SPREAD / math.sqrt(n + 1))
            if v > top: best, top = k, v
        look[dim] = best
    recent = [r for r in recent if isinstance(r, dict)]
    caps = [k for k in active(cat, "captions") if k != look["captions"]]
    if len(recent) >= 2 and recent[-1].get("captions") == recent[-2].get("captions") == look["captions"] and caps:
        look["captions"] = rng.choice(caps)
    if recent and all(recent[-1].get(d) == look[d] for d in look):
        dims = [d for d in look if len(active(cat, d)) > 1]
        if dims:
            d = rng.choice(dims); look[d] = rng.choice([k for k in active(cat, d) if k != look[d]])
    return look

def resolve(ids=None, cat=None):
    """Fill in missing or retired choices and return what the renderer needs."""
    cat = cat or catalogue(); ids = dict(ids or {})
    for d in cat["dimensions"]:
        if ids.get(d) not in cat["dimensions"][d]["options"]: ids[d] = default(cat)[d]
    o = {d: cat["dimensions"][d]["options"][ids[d]] for d in cat["dimensions"]}
    render = {"captions": ids["captions"], "group": o["captions"].get("group", 3),
              "filter": o["grade"].get("filter", "none"), "vignette": o["grade"].get("vignette", 0),
              "motion": o["energy"].get("motion", 1.0), "punch": o["energy"].get("punch", 0.045),
              "beat_punches": bool(o["energy"].get("beat_punches"))}
    return {"ids": ids, "render": render, "voice": {"voice": o["voice"].get("voice", "F2"), "wps": o["voice"].get("wps", 3.0)}}

def describe(ids, cat=None):
    """One short line for the lineup message, e.g. 'pop captions, emma, punchy, vivid'."""
    cat = cat or catalogue(); ids = resolve(ids, cat)["ids"]
    return f"{ids['captions']} captions, {ids['voice'].replace('_', ' ')}, {ids['energy']}, {ids['grade']}"

if __name__ == "__main__":
    print(json.dumps(choose(sys.argv[1] if len(sys.argv) > 1 else "QD-999")))
