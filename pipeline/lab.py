"""Look lab: keeps inventing and testing new looks, so the Shorts keep getting better with nobody redesigning them
(Charlie, 19 October: constant improvement from how the Shorts perform; with Shorts every day there is plenty to test on).

analytics.yml runs it every hour; it acts once a UTC day, after the morning numbers. For each look dimension (caption
design, voice pace, camera energy, colour grade, opening):
1. Judge: a lab option measured on 8 or more Shorts stays if it beats the option it came from, and becomes the base for
   the next change; if not, it retires.
2. Prune: an option measured on 10 or more Shorts that scores 15% or more below the dimension's best retires (at least
   2 options always stay).
3. Try something new: when nothing new is being tested, a new option is made from the current best by changing one or
   two settings, within limits that keep the Shorts neat and minimal (LIMITS). At most 5 options per dimension, so each
   new one gets enough Shorts to be judged.
Scores come from analytics.py (analytics/looks.json): how long viewers keep watching, against Shorts posted around the
same time. looks.choose() tries a new option early, then gives most Shorts the best scorers. The lab's options,
retirements and log are in analytics/lab_looks.json; looks.catalogue() merges them into templates/looks.json.
  python pipeline/lab.py [--force]
"""
import datetime as dt, json, pathlib, random, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import looks as LK

NOW = dt.datetime.now(dt.timezone.utc)
TODAY = str(NOW.date())
JUDGE, PRUNE_N, PRUNE_GAP, MAX_ACTIVE = 8, 10, 0.85, 5
LIMITS = {      # what the lab may change: (lowest, highest, step)
    "voice": {"wps": (3.0, 3.8, 0.15)},                     # words a second (tts_cb.py can only speed speech up, to 1.3x)
    "energy": {"motion": (0.6, 1.2, 0.1), "punch": (0.02, 0.06, 0.01)},
    "grade": {"contrast": (0.95, 1.15, 0.04), "saturate": (0.82, 1.12, 0.06), "sepia": (0.0, 0.2, 0.05),
              "brightness": (0.96, 1.06, 0.03), "vignette": (0.0, 0.8, 0.2)},
    "opening": {"reveal_word": (0, 5, 1)},
    "captions": {"size": (60, 88, 4), "top": (1220, 1320, 20), "weight": (600, 800, 100), "group": (2, 4, 1)},
}
CHOICES = {"captions": {"on": ["var(--accent)", "#FFFFFF", "#FFD54A", "#7CE3FF"], "box": ["transparent", "rgba(9,13,19,.62)"]}}
CAP_BASE = {"size": 68, "top": 1290, "weight": 700, "on": "#FFFFFF", "box": "transparent"}     # like "minimal"


def load():
    try: return json.loads(LK.LAB.read_text())
    except Exception: return {"options": {}, "retired": {}, "log": []}


def num(x, d):
    try: return float(str(x).replace("px", ""))
    except (TypeError, ValueError): return d


def params(dim, o):
    """The settings of an option the lab can change."""
    if dim == "voice": return {"wps": num(o.get("wps"), 3.0)}
    if dim == "energy": return {"motion": num(o.get("motion"), 1.0), "punch": num(o.get("punch"), 0.045)}
    if dim == "opening": return {"reveal_word": num(o.get("reveal_word"), 0)}
    if dim == "grade":
        p = {"contrast": 1.0, "saturate": 1.0, "sepia": 0.0, "brightness": 1.0, "vignette": num(o.get("vignette"), 0)}
        for k, v in re.findall(r"(contrast|saturate|sepia|brightness)\(([\d.]+)\)", str(o.get("filter") or "")): p[k] = float(v)
        return p
    if dim == "captions":
        c = dict(CAP_BASE, **(o.get("cap") or {}))
        return {"size": num(c["size"], 68), "top": num(c["top"], 1290), "weight": num(c["weight"], 700),
                "group": num(o.get("group"), 3), "on": c["on"], "box": c["box"]}
    return {}


def build(dim, p, parent, po):
    """An option from its settings."""
    r2 = lambda x: round(x, 2)
    if dim == "voice":
        return {"desc": f"{str(po.get('desc', parent)).split(',')[0]}, {r2(p['wps'])} words a second",
                "voice": po.get("voice", "F2"), "wps": r2(p["wps"])}
    if dim == "energy":
        return {"desc": f"camera motion {r2(p['motion'])}, punch-ins {r2(p['punch'])}", "motion": r2(p["motion"]),
                "punch": r2(p["punch"]), "beat_punches": bool(po.get("beat_punches"))}
    if dim == "opening":
        r = int(p["reveal_word"])
        return {"desc": "the hook's card from the first frame" if r == 0 else f"the picture alone for {r} word{'s' if r > 1 else ''}, then the hook's card",
                "reveal_word": r}
    if dim == "grade":
        f = " ".join(f"{k}({r2(p[k])})" for k in ("contrast", "saturate", "sepia", "brightness"))
        return {"desc": f"{f}, vignette {r2(p['vignette'])}", "filter": f, "vignette": r2(p["vignette"])}
    if dim == "captions":
        boxed = p["box"] != "transparent"
        cap = {"size": f"{int(p['size'])}px", "top": f"{int(p['top'])}px", "weight": str(int(p["weight"])), "on": p["on"],
               "box": p["box"], "pad": "14px 30px 20px" if boxed else "0"}
        return {"desc": f"{cap['size']} weight {cap['weight']} at {cap['top']}, {int(p['group'])} words at a time, spoken word "
                        f"{p['on']}, {'dark panel' if boxed else 'no panel'}",
                "class": "lab", "group": int(p["group"]), "cap": cap}
    return {}


def mutate(dim, parent, po, rng):
    """A new option from `parent`: one or two of its settings moved a step, within LIMITS."""
    p = params(dim, po)
    keys = list(LIMITS.get(dim, {})) + list(CHOICES.get(dim, {}))
    for _ in range(20):
        q = dict(p)
        for k in rng.sample(keys, min(len(keys), rng.choice((1, 2)))):
            if k in LIMITS[dim]:
                lo, hi, step = LIMITS[dim][k]
                q[k] = min(hi, max(lo, q[k] + rng.choice((-1, 1)) * step))
            else:
                q[k] = rng.choice([c for c in CHOICES[dim][k] if c != q[k]] or CHOICES[dim][k])
        o = build(dim, q, parent, po)
        if o and o != build(dim, p, parent, po): return o
    return None


def main(force=False):
    lab = load()
    if not force and lab.get("day") == TODAY: print("look lab: already ran today"); return
    if not force and NOW.hour < 5: print("look lab: waits for the morning numbers"); return
    stats = LK.load_stats().get("dimensions") or {}
    rng = random.Random(TODAY)
    lab.setdefault("options", {}); lab.setdefault("retired", {}); log = lab.setdefault("log", [])

    def note(dim, what, why):
        log.append({"day": TODAY, "dimension": dim, "change": what, "why": why}); print(f"{dim}: {what} ({why})")

    def retire(dim, k, why):
        if k in lab["options"].get(dim, {}): lab["options"][dim][k]["retired"] = f"{TODAY}: {why}"
        else: lab["retired"].setdefault(dim, {})[k] = f"{TODAY}: {why}"
        note(dim, f"retired {k}", why)

    for dim in LK.catalogue(lab)["dimensions"]:
        if dim not in LIMITS: continue
        st = stats.get(dim) or {}
        sc = lambda k: (int((st.get(k) or {}).get("n") or 0), float((st.get(k) or {}).get("score") or 1.0))
        for k, o in list(LK.active(LK.catalogue(lab), dim).items()):        # 1. judge
            n, s = sc(k)
            if o.get("lab") and n >= JUDGE:
                pn, ps = sc(o.get("parent"))
                why = f"{s:.2f}x against {ps:.2f}x for {o.get('parent')} over {n} Shorts"
                if s > ps:
                    lab["options"][dim][k].update(lab=False, kept=TODAY); note(dim, f"kept {k}: {o.get('desc')}", why)
                else: retire(dim, k, why)
        act = LK.active(LK.catalogue(lab), dim)
        best = max(act, key=lambda k: (sc(k)[0] >= 3, sc(k)[1]))
        for k in list(act):                                                  # 2. prune
            n, s = sc(k)
            if k != best and len(LK.active(LK.catalogue(lab), dim)) > 2 and n >= PRUNE_N and s <= PRUNE_GAP * sc(best)[1]:
                retire(dim, k, f"{s:.2f}x against {sc(best)[1]:.2f}x for {best} over {n} Shorts")
        act = LK.active(LK.catalogue(lab), dim)
        if any(o.get("lab") and sc(k)[0] < JUDGE for k, o in act.items()): continue     # one new option at a time
        if len(act) >= MAX_ACTIVE:
            weak = [k for k in act if k != best and sc(k)[0] >= 6]
            if not weak: continue
            w = min(weak, key=lambda k: sc(k)[1])
            retire(dim, w, f"making room for a new test ({sc(w)[1]:.2f}x over {sc(w)[0]} Shorts)")
        o = mutate(dim, best, act[best], rng)                                # 3. try something new
        if not o: continue
        k = f"lab-{dim}-{NOW:%m%d}"
        lab["options"].setdefault(dim, {})[k] = dict(o, lab=True, parent=best, born=TODAY)
        note(dim, f"testing {k}: {o['desc']}", f"one or two settings changed from the best so far, {best}")
    lab["day"] = TODAY
    lab["log"] = log[-200:]
    LK.LAB.write_text(json.dumps(lab, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(force="--force" in sys.argv)
