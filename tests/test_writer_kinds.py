"""Offline test of the new kinds: evergreen questions, top lists, true stories, fiction, and two-part series."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import collections, json, os, pathlib, sys
os.chdir(REPO_DIR)
sys.path.insert(0, "pipeline")
os.environ["WRITE_DRY"] = "1"
import writer as W, factpack as F, validate as V

print("kinds for 12:", collections.Counter(W.pick_kinds(12)))
ex = json.loads(W.example())
SENT = ["Minecraft is the best-selling video game of all time with over 300 million copies sold.",
        "Grand Theft Auto V is second with more than 210 million copies sold.",
        "Tetris has sold around 100 million copies in its paid mobile versions alone.",
        "Wii Sports sold 82.9 million copies, mostly bundled with the Wii.",
        "PUBG: Battlegrounds has sold 75 million copies on PC and consoles.",
        "Mario Kart 8 and its Deluxe version together sold over 75 million copies."]
TEXT = (" ".join(SENT) + " ") * 3
calls = []


def fake(prompt, schema=None, timeout=100, temperature=0.1, lite=False, **kw):
    kind = ("premise" if prompt.startswith("You write premises") else "plan" if prompt.startswith("You plan evergreen")
            else "facts" if prompt.startswith("You check facts for a family-friendly Shorts channel. The Short is about")
            else "translate" if prompt.startswith("Translate") else "check" if prompt.startswith("You check a YouTube Short") else "write")
    calls.append(kind)
    if kind == "premise": return {"premise": "A speedrunner finds a level that plays itself", "category": "Gaming"}, "f"
    if kind == "plan":
        return {"items": [{"kind": "top list", "idea": "Top 10 best-selling video games", "category": "Gaming", "wikipedia": "List of best-selling video games"},
                          {"kind": "true story", "idea": "How Tetris escaped the Soviet Union", "category": "Gaming", "wikipedia": "Tetris"},
                          {"kind": "question", "idea": "Why is Minecraft so popular", "category": "Gaming", "wikipedia": "Minecraft"}]}, "f"
    if kind == "facts":
        return {"what_is_new": "", "hooks": ["Number 1 sold 300 million"], "facts": [
            {"claim": s, "evidence": [{"source": 1, "quote": s}]} for s in SENT]}, "f"
    if kind == "translate": return {}, "f"
    if kind == "check": return {"ok": True}, "f"
    b = json.loads(json.dumps(ex))
    part = " (Part 2)" if "Part 2 of 2" in prompt else " (Part 1)" if "Part 1 of 2" in prompt else ""
    b["meta"]["title"] = f"Test {len(calls)}{part} 🎮"
    if "FICTION:" in prompt:
        b["format"] = "story"
        b["meta"]["sources"] = [["Quickplay Daily original story", "https://www.youtube.com/@quickplaydaily"]]
        b["meta"]["facts"] = [["This is an original fictional story.", [1]]]
        for bt in b["beats"]: bt["shots"] = [{"src": "gameplay:parkour rooftop run", "move": "in"}]
    return b, "f"


F.gemini = fake
d = json.loads(F.OUT.read_text()); d["mode"] = "full"; d["topics"] = []     # no news: evergreen kinds and fiction fill the run
F.OUT = pathlib.Path(SCRATCH + "/facts_full.json"); F.OUT.write_text(json.dumps(d))
F.page_text = lambda url, wiki=False: (TEXT, "")
W.reserve_count = lambda: 9
W.recent = lambda days=14: []      # the real queue must not count as "covered already"
W.pick_kinds = lambda n: (["top list", "true story", "evergreen"] * 4)[:n]     # every kind, whatever the day's shuffle
W.plan = lambda breaking=False, hint="": ("morning", __import__("datetime").date(2026, 10, 21), 6)
orig = W.test_plan
W.test_plan = lambda k, kind="news": (lambda st, t: (st, {**t, "series": "two parts"} if kind in ("top list", "true story", "fiction") else t))(*orig(k, kind))
before = {p.name for p in pathlib.Path("boards/queue").glob("QD-*.json")}
W.main()
new = sorted(p for p in pathlib.Path("boards/queue").glob("QD-*.json") if p.name not in before)
got = [json.loads(p.read_text()) for p in new]
for p in new: p.unlink()
for b in got: print(b["id"], b["kind"], b.get("series"), b["meta"]["title"], "errors:", V.check(b)[0][:1])
print("calls:", collections.Counter(calls))
assert {"fiction", "top list", "true story"} <= {b["kind"] for b in got}
assert any((b.get("series") or {}).get("part") == 2 for b in got)
one = json.loads(json.dumps(ex)); one["meta"]["facts"] = [[one["meta"]["facts"][0][0], [1]]]
print("one-source fact errors:", [e for e in V.check(one)[0] if "facts" in e])
print("tests ok")
