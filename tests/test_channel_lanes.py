"""Offline test (26 October): a channel's evergreen ideas stay on its lane. With no Gaming news the gaming channel was given
"Highest Grossing Films" and the IRL channel "Best-Selling Games"; writer.evergreen_packs now tells the plan the lane and
drops an idea whose category is outside the channel's categories. The main channel (no cats) is unchanged."""
import pathlib as _p, os, sys
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import writer as W, factpack

calls = []
def fake(prompt, schema=None, **k):
    calls.append(prompt)
    return {"items": [{"kind": "top list", "idea": "Top 5 highest-grossing films of all time", "wikipedia": "List of highest-grossing films", "category": "Film"},
                      {"kind": "top list", "idea": "Top 10 best-selling video games", "wikipedia": "List of best-selling video games", "category": "Gaming"}]}, "stub"
factpack.gemini = fake
factpack.page_text = lambda url, wiki=True: ("x" * 900, None)
factpack.facts_from = lambda *a, **k: ({"hooks": []}, None, [f"fact {i}" for i in range(12)], None)
factpack.image_ideas = lambda x: []

out = W.evergreen_packs(["top list"], [], cats=["Gaming"], lane="Stay on the games.")
assert [p["topic"] for p in out] == ["Top 10 best-selling video games"], out
assert "covers only Gaming" in calls[-1] and "Stay on the games." in calls[-1]
out = W.evergreen_packs(["top list"], [])
assert out and "covers only" not in calls[-1], "the main channel keeps every category"
print("test_channel_lanes: ok")
