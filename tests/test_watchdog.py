"""Offline tests of the missed-run watchdog (26 October, pipeline/watchdog.py): a dropped trends slot is started after
the grace time and not before; a run already going stops it; a gap workflow starts only past its gap."""
import pathlib as _p, sys, datetime as dt
sys.path.insert(0, str(_p.Path(__file__).resolve().parent.parent / "pipeline"))
import watchdog as W

U = dt.timezone.utc
def at(h, m, d=26): return dt.datetime(2026, 10, d, h, m, tzinfo=U)
def run(t, status="completed"): return {"createdAt": t.isoformat().replace("+00:00", "Z"), "status": status}

# 26 October: the 12:47 slot dropped; the last trends run was 11:23
assert W.last_slot(at(14, 5), W.SLOTS["trends.yml"]) == at(12, 47)
assert W.last_slot(at(7, 0), W.SLOTS["trends.yml"]) == at(18, 23, 25)
assert "12:47" in W.overdue("trends.yml", at(14, 5), [run(at(11, 23))])
assert W.overdue("trends.yml", at(13, 20), [run(at(11, 23))]) == "", "inside the grace time"
assert W.overdue("trends.yml", at(14, 5), [run(at(12, 50))]) == "", "the slot ran"
assert W.overdue("trends.yml", at(14, 5), [run(at(12, 40))]) == "", "a run just before the slot counts (GitHub starts early rarely, a hand run often)"
assert W.overdue("trends.yml", at(14, 5), [run(at(14, 0), "in_progress"), run(at(11, 23))]) == ""
assert W.overdue("trends.yml", at(14, 5), []) != ""
# gap workflows
assert W.overdue("render.yml", at(14, 5), [run(at(11, 30))]) == ""
assert "4 hours" in W.overdue("render.yml", at(16, 0), [run(at(11, 30))])
assert W.overdue("render.yml", at(16, 0), [run(at(15, 0), "queued")]) == ""
assert "publish.yml" not in W.GAPS and "publish.yml" not in W.SLOTS, "a dispatch there defaults to approve all"
print("test_watchdog: ok")
