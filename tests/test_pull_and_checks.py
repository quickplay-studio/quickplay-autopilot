"""Offline test: "pull QD-xxx" keeps a scheduled Short private and off social; Wikipedia citations are refused."""
import pathlib as _p, sys as _s, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _t.mkdtemp(prefix="qp-test-")
import json, pathlib, shutil, sys, types
sys.path.insert(0, REPO_DIR + "/pipeline")
import publish as P, validate as V
tmp = pathlib.Path(SCRATCH + "/t8")
shutil.rmtree(tmp, ignore_errors=True)
for d in ("status", "boards/done", "boards/rejected", "approvals"): (tmp / d).mkdir(parents=True)
P.ROOT, P.STATUS = tmp, tmp / "status"
(tmp / "status" / "QD-901.json").write_text(json.dumps({"id": "QD-901", "state": "scheduled", "video": "vid901", "publish_at": "2026-10-21T15:30:00Z"}))
(tmp / "status" / "QD-903.json").write_text(json.dumps({"id": "QD-903", "state": "scheduled", "video": "vid903"}))
(tmp / "boards" / "done" / "QD-901.json").write_text("{}")
updates = []
class Videos:
    def update(self, part, body): updates.append((part, body)); return types.SimpleNamespace(execute=lambda: {})
yt = types.SimpleNamespace(videos=lambda: Videos())
privacy = {"vid901": "private", "vid903": "public"}
sys.modules["youtube"] = types.SimpleNamespace(available=lambda: True, client=lambda: yt,
                                               video_status=lambda y, v: {"privacy": privacy[v], "publish_at": "x"})
later = P.pull_step(["pull QD-901 QD-902", "unschedule 903"])
st = json.loads((tmp / "status" / "QD-901.json").read_text())
print("later:", later, "| updates:", updates, "| state:", st["state"], st.get("instagram_skipped"), st.get("facebook_skipped"))
assert later == {"QD-902"} and len(updates) == 1 and updates[0][1] == {"id": "vid901", "status": {"privacyStatus": "private",
       "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}}
assert (tmp / "boards" / "rejected" / "QD-901.json").exists() and st["pulled"]
assert json.loads((tmp / "status" / "QD-903.json").read_text())["state"] == "scheduled"     # already public: left alone
finished = lambda l: P.is_reserve_line(l) or (P.is_pull_line(l) and not P.pull_ids(l) & later)
assert not finished("pull QD-901 QD-902") and finished("pull QD-901") and not finished("approve all")
print("pull ok")

b = json.loads(pathlib.Path(REPO_DIR + "/boards/hold/QD-028.json").read_text())
b["beats"][1]["say"] = "According to Wikipedia, the Moon is slowly drifting away from us."
assert any("Wikipedia" in e for e in V.check(b)[0])
b["beats"][1]["say"] = "The Moon is slowly drifting away from us, about 3.8 centimetres a year."
assert not any("Wikipedia" in e for e in V.check(b)[0])
print("wikipedia check ok")
