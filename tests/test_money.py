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

# clips YouTube shows to nobody: the reach check per channel (clips.reach_check) and one issue naming them (alerts.reach_alert)
import clips as C
C.ROOT = root
rows = [{"channel": "clips", "privacy": "public", "hours_public": "30", "views": "0", "rejected": "", "blocked_in": "0",
         "age_restricted": "0", "for_kids": "0"} for _ in range(9)]
rows += [{"channel": "clips", "privacy": "public", "hours_public": "30", "views": "4", "rejected": "", "blocked_in": "all but 0",
          "age_restricted": "0", "for_kids": "0"},
         {"channel": "gaming", "privacy": "public", "hours_public": "5", "views": "12", "rejected": "", "blocked_in": "0",
          "age_restricted": "0", "for_kids": "0"}]
got = C.reach_check(rows)
assert got["clips"]["unseen"] and got["clips"]["no_views"] == 9 and got["clips"]["blocked"] == 1, got
assert not got["gaming"]["unseen"] and got["gaming"]["public_a_day_old"] == 0
ISS, CLR = [], []
A.ROOT, A.raise_issue, A.clear = root, (lambda t, b: ISS.append((t, b))), (lambda t, b: CLR.append(t))
A.reach_alert()
assert len(ISS) == 1 and "clips: 9 of 10 clips a day old have no views" in ISS[0][1] and "1 blocked" in ISS[0][1] and "gaming" not in ISS[0][1], ISS
C.reach_check(rows[-1:]); A.reach_alert()
assert CLR == [ISS[0][0]]
print("reach ok")
