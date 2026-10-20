"""Offline test: voices scored on viewers not swiping away; other dimensions unchanged."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import datetime as dt, json, pathlib, random, shutil, sys
sys.path.insert(0, REPO_DIR + "/pipeline")
import analytics as A, review_page as RP
tmp = pathlib.Path(SCRATCH + "/t6")
shutil.rmtree(tmp, ignore_errors=True); (tmp / "status").mkdir(parents=True)
A.ROOT, A.NOW = tmp, dt.datetime(2026, 10, 25, 12, tzinfo=dt.timezone.utc)
rng, rows = random.Random(1), []
stay = {"george": 40, "emma": 60, "george_dramatic": 30}
for i in range(30):
    sid, voice = f"QD-9{i:02d}", ["george", "emma", "george_dramatic"][i % 3]
    cap = ["clean", "pop"][i % 2]
    (tmp / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "look": {"voice": voice, "captions": cap}}))
    posted = A.NOW - dt.timedelta(hours=30 + 3 * i)
    rows.append({"short": sid, "posted": posted.isoformat(timespec="minutes"), "yt_views": 20 if i == 4 else 100 + 10 * i,
                 "yt_engaged_pct": (5 if i == 4 else stay[voice] + rng.randint(-3, 3)), "yt_held_3s_pct": "",
                 "yt_avg_viewed_pct": 50 + (10 if cap == "pop" else 0), "views_per_hour": 5})
out = A.look_scores(rows)
v = out["dimensions"]["voice"]
print({k: v[k] for k in ("george", "emma", "george_dramatic")})
print({k: out["dimensions"]["captions"][k] for k in ("clean", "pop")}, out["measure"])
assert v["emma"]["score"] > v["george"]["score"] > v["george_dramatic"]["score"]
assert v["emma"]["n"] == 9 and v["george_dramatic"]["n"] == 10          # the 20-view Short is too small to judge
assert out["dimensions"]["captions"]["pop"]["score"] > out["dimensions"]["captions"]["clean"]["score"]
print("\n".join(RP.voice_section()))
print("stay scoring ok")
