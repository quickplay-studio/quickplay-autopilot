"""Offline test of the money notes (pipeline/alerts.py clips_money): views over the minimum at the campaign's rate, capped per
clip, the latest row per clip only, private clips ignored."""
import pathlib as _p, sys as _s, tempfile as _t, json, os
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
os.chdir(REPO_DIR); _s.path.insert(0, REPO_DIR + "/pipeline")
import alerts as A
root = SCRATCH / "root"; (root / "clips").mkdir(parents=True)
(root / "clips" / "campaigns.json").write_text(json.dumps({"campaigns": {
    "a": {"pay_per_1k": 2.0, "min_views": 5000, "max_payout": 10}, "b": {"pay_per_1k": 1.0, "min_views": 1000, "max_payout": 500}}}))
(root / "clips" / "stats.csv").write_text(
    "clip,campaign,video,privacy,views,as_of\n"
    "a-1,a,v1,public,4000,2026-10-22T10:00\n"        # under the minimum: nothing yet
    "a-2,a,v2,public,8000,2026-10-22T10:00\n"        # 8 x 2.00 = 16, capped at 10
    "a-2,a,v2,public,6000,2026-10-21T10:00\n"        # an older row of the same clip: ignored
    "b-1,b,v3,public,12000,2026-10-22T10:00\n"       # 12 x 1.00 = 12
    "b-2,b,v4,private,90000,2026-10-22T10:00\n")     # private: ignored
total, by = A.clips_money(root)
assert total == 22.0 and by == {"a": 10.0, "b": 12.0}, (total, by)
assert A.clips_money(SCRATCH / "nowhere") == (0.0, {})
print("money ok")
