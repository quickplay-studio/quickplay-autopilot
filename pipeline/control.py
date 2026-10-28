"""The frozen control group (Charlie, 28 October 2026; goal: the Partner Programme).

"Is the learning loop improving things?" cannot be read off the channel's numbers alone: trends, the volume test and mega pushes
move them too. So a share of the normal Shorts (config "control": share, 0.1) is written with the recipe as it stood on the day
the loop was frozen (analytics/control_recipe.json), whatever the loop has learned since: no pushed or paused choice, no adopted
writing instruction, no champion, no round arm, no exploration, no new Recipe lines, the look as the channel's looks were
spread then, and the first free posting slot instead of the learned best hour. Same channel, same UK day, same kinds of
topic: pipeline/trend.py compares the loop's Shorts with them ("Loop vs frozen control", heat allowed for).
What stays live on purpose: the rules in code (RULES, validators, the channel's safety rules), the packs and topics, the model
chain (the free models answer or do not), and the pair check of the sameness guard.

A board is a control board by its own seeded draw, random.Random(f"control:{k}") for board number k, independent of every other
draw. Only normal quota Shorts can be: never a mega trend's, the reserve, a follow-up, breaking or remake Short, an exploration
Short, a part of a series, a mirror, or one of another channel. Marked "control": 1 on the board and control_arm 1 in
shorts.csv; drivers, round, channel_drivers, subscriber drivers, looks, writer scores and evolve leave those rows out of every
verdict (analytics.py learning rows).
  python pipeline/control.py --freeze     writes analytics/control_recipe.json from today's analytics files (once; refuses to overwrite)
"""
import json, pathlib, random, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP = ROOT / "analytics" / "control_recipe.json"
DEFAULTS = {"share": 0.1, "frozen": "", "on": False, "min_n": 8}
ELIGIBLE_KINDS = ("news", "evergreen")
LOOK_DIMS = ("captions", "voice", "energy", "grade", "opening", "style", "closing")


def settings(cfg=None):
    if cfg is None:
        try: cfg = json.loads((ROOT / "config.json").read_text())
        except Exception: cfg = {}
    return {**DEFAULTS, **((cfg or {}).get("control") or {})}


def on(cfg=None):
    return bool(settings(cfg).get("on"))


def drawn(k, cfg=None):
    """Whether board number k is a control board by its own draw (before the eligibility rules)."""
    s = settings(cfg)
    return bool(s.get("on")) and random.Random(f"control:{k}").random() < float(s.get("share", 0.1))


def eligible(kind="news", reserve=False, mega=False, explore=False, follow=False, part=False, channel="main"):
    """Whether a Short can be a control Short at all: a normal quota Short of the main channel."""
    return (kind in ELIGIBLE_KINDS and not reserve and not mega and not explore and not follow and not part
            and (channel or "main") == "main")


def is_control(k, kind="news", cfg=None, **kw):
    return drawn(k, cfg) and eligible(kind, **kw) and bool(load())


def load(path=None):
    """analytics/control_recipe.json as a dict; {} when it is missing or broken (then no Short is a control Short)."""
    try:
        s = json.loads(pathlib.Path(path or SNAP).read_text())
        return s if isinstance(s, dict) and s.get("frozen") else {}
    except Exception:
        return {}


# ---------------- what a control Short is written with ----------------
def tests(k, dims, snap=None, no_title=()):
    """The tests recorded on control Short number k: the frozen winners (those among `dims`, the tests this kind of Short takes),
    the frozen title and subscribe-line arms, the replies rule as it always was (alternate Shorts); no round arm, no gene, no
    exploration."""
    snap = snap if snap is not None else load()
    t = {f: a for f, a in (snap.get("winners") or {}).items() if f in dims and not str(f).startswith("gene:")}
    for name, arm in (snap.get("title") or {}).items():
        if name not in no_title: t[name] = arm
    if snap.get("sub_push"): t["sub_push"] = snap["sub_push"]
    t["replies"] = "on" if k % 2 == 0 else "off"
    t["explore"] = "no"
    return t


def look(k, snap=None, catalogue=None):
    """The control Short's look: one option per dimension drawn from the spread of looks at the freeze (a seeded draw a dimension),
    only among options still active; a style that brings its own captions sets them. {} without a frozen spread."""
    snap = snap if snap is not None else load()
    spread = snap.get("looks") or {}
    if not spread: return {}
    cat = catalogue
    if cat is None:
        try:
            import looks as LK
            cat = LK.catalogue()
        except Exception: cat = None
    out = {}
    for dim in LOOK_DIMS:
        w = {o: float(x) for o, x in (spread.get(dim) or {}).items() if float(x) > 0}
        if cat is not None:
            opts = (cat.get("dimensions", {}).get(dim) or {}).get("options") or {}
            w = {o: x for o, x in w.items() if o in opts and not opts[o].get("retired")}
        if not w: continue
        x = random.Random(f"control-look:{dim}:{k}").random() * sum(w.values())
        for o, v in sorted(w.items()):
            x -= v
            if x < 0: out[dim] = o; break
        else: out[dim] = sorted(w)[-1]
    if cat is not None:
        st = ((cat.get("dimensions", {}).get("style") or {}).get("options") or {}).get(out.get("style")) or {}
        if st.get("captions"): out["captions"] = st["captions"]
    return out


# ---------------- the freeze ----------------
def look_spread(root=None, last=60):
    """{dimension: {option: share}} over the looks of the last `last` rendered Shorts (their status files)."""
    root = pathlib.Path(root or ROOT)
    seen = []
    for sp in (root / "status").glob("QD-*.json"):
        try: st = json.loads(sp.read_text())
        except Exception: continue
        if isinstance(st, dict) and isinstance(st.get("look"), dict): seen.append((str(st.get("rendered") or ""), st["look"]))
    seen = [lk for _, lk in sorted(seen, key=lambda x: x[0])][-last:]
    out = {}
    for dim in LOOK_DIMS:
        vals = [str(lk[dim]) for lk in seen if lk.get(dim)]
        if vals: out[dim] = {o: round(vals.count(o) / len(vals), 3) for o in sorted(set(vals))}
    return out


def freeze(today, writer, force=False):
    """Build and write analytics/control_recipe.json from what the writer reads today (module `writer`): the pushed and champion
    arms, the pauses, the adopted writing instructions, the Recipe lines and drop-off notes in the prompt, the title and
    subscribe-line arms, the spread of looks. Refuses to overwrite a frozen recipe unless `force`."""
    if load() and not force: raise SystemExit("analytics/control_recipe.json is frozen already: a control group is only meaningful against one fixed recipe")
    EV = writer.EV
    import subscribe as SUB
    snap = {"frozen": str(today),
            "note": ("The recipe the loop had learned on this day, copied once. Control Shorts (config.json control) are written with "
                     "exactly this and nothing the loop learns later; trend.py compares the loop's Shorts with them."),
            "winners": {f: a for f, a in sorted(writer.winners().items()) if not EV.is_gene(f)},
            "paused": {f: sorted(v) for f, v in sorted(writer.stopped().items())},
            "genes": {lin: t for lin, t in sorted(EV.adopted_texts().items())},
            "champions": dict(sorted(EV.champions().items())),
            "recipe": writer.recipe(),
            "dropoff": writer.dropoff_notes(),
            "title": {"title_emoji": writer.title_winner("title_emoji") or "emoji",
                      "title_answer": writer.title_winner("title_answer") or "stated"},
            "sub_push": SUB.winner("sub_push") if SUB.winner("sub_push") in SUB.ARMS else "none",
            "looks": look_spread(),
            "slot": "first free slot (the learned best hour is not used)"}
    SNAP.parent.mkdir(exist_ok=True)
    SNAP.write_text(json.dumps(snap, indent=1, ensure_ascii=False) + "\n")
    return snap


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        import datetime as dt
        sys.path.insert(0, str(ROOT / "pipeline"))
        import writer
        s = freeze(dt.date.fromisoformat(next((a for a in sys.argv[1:] if a[:2] == "20"), str(dt.date.today()))), writer,
                   force="--force" in sys.argv)
        print(json.dumps({k: (v if k not in ("recipe", "dropoff", "looks") else f"{len(v)} items") for k, v in s.items()}, indent=1))
    else:
        print(json.dumps(settings())); print("frozen:", bool(load()))
