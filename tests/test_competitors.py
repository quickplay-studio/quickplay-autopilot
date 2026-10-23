"""Offline test of the competitor research (pipeline/competitors.py) and the clips' Instagram numbers: title features,
the daily table with the allowance guard, the writer's top titles, and a clip's Reel views from the Instagram cache."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import json, os, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import competitors as C
assert C.features("Why is Minecraft STILL everywhere? 🎮") == {"title_words": 5, "has_number": 0, "is_question": 1, "has_emoji": 1, "first_word": "why"}
assert C.iso_seconds("PT1M5S") == 65 and C.iso_seconds("PT45S") == 45

C.OUT, C.MD = SCRATCH / "competitors.csv", SCRATCH / "competitors.md"
class Exec:
    def __init__(self, data): self.data = data
    def execute(self): return self.data
class YT:
    def search(self): return self
    def videos(self): return self
    def list(self, **kw):
        if "q" in kw: return Exec({"items": [{"id": {"videoId": f"{kw['q'][:3]}{i}"}} for i in range(3)]})
        ids = kw["id"].split(",")
        return Exec({"items": [{"id": v, "snippet": {"title": f"Top {n} thing {v}?", "channelTitle": "Other", "publishedAt": "2026-10-23T00:00:00Z"},
                                "statistics": {"viewCount": str(1000 * (n + 1))}, "contentDetails": {"duration": "PT40S"}} for n, v in enumerate(ids)]})
Y = types.ModuleType("youtube"); Y.client = lambda: YT(); sys.modules["youtube"] = Y
import quota
quota.allow = lambda units, what="": True; quota.spend = lambda units, what="": None
got = C.run(force=True)
assert len(got) == 3 * len(C.QUERIES) and C.MD.exists() and "Top Shorts" in C.MD.read_text()
assert C.run() == []                                      # once a UK day
tt = C.top_titles("Music")
assert len(tt) == 3 and tt[0].startswith('"Top 2 thing') and "views an hour" in tt[0], tt
quota.allow = lambda units, what="": False                 # the allowance guard stops the searches
assert C.run(force=True) == []
print("competitors ok")

import clips as K
K.ROOT = SCRATCH; (SCRATCH / "analytics" / "cache").mkdir(parents=True)
(SCRATCH / "analytics" / "cache" / "instagram.json").write_text(json.dumps({"123": {"views": 840, "reach": 700, "ig_reels_avg_watch_time": 5300}}))
assert K.ig_numbers("123") == {"ig_views": 840, "ig_reach": 700, "ig_watch_s": 5.3}
assert K.ig_numbers(None)["ig_views"] == "" and K.ig_numbers("999")["ig_views"] == ""
print("clip instagram numbers ok")
