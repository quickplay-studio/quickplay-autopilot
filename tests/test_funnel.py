"""Offline test of the daily funnel (pipeline/funnel.py): a stage that gets nothing while the one before it had work is
named as stuck (the 23 October clips: uploaded to YouTube, never posted to Instagram or submitted)."""
import pathlib as _p, sys
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO_DIR + "/pipeline")
import funnel as F
s = F.stuck({"packs": 11, "written": 19, "rendered": 17, "render_failed": 0, "target": 15, "clips_made": 58, "clips_uploaded": 42,
             "clips_instagram": 0, "clips_submitted": 0})
assert s == ["clips went up on YouTube but none to Instagram", "clips went up but none were submitted to a campaign"], s
s = F.stuck({"packs": 11, "written": 3, "rendered": 1, "render_failed": 2, "target": 15})
assert "over a third of the renders failed" in s and any("under half" in x for x in s), s
assert F.stuck({"packs": 0, "written": 0, "target": 0}) == []
print("funnel ok")
