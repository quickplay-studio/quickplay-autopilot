"""Offline test of the clock changes: UK clocks go back on Sunday 25 October 2026 (BST to GMT) and US Pacific time on
Sunday 1 November, and every cron is UTC. The writer's posting day, the slot grid, the clips batch time and the clips
social run's wait (the code in .github/workflows/clips.yml itself) must hold on both sides."""
import contextlib, datetime as dt, io, json, os, pathlib as _p, re, sys, types
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
U = dt.timezone.utc
at = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=U)

# 1. the writer's posting day: the 06:47 UTC breaking check starts at about 07:15 UTC, which was 08:15 UK until today and
# is 07:15 UK from 25 October; what it writes goes out an hour later at the soonest, so it belongs to that day either way
import writer as W
W.CFG = dict(W.CFG, slot_first="07:30", lead_hours=1)
os.environ.pop("WRITE_RUN", None); os.environ.pop("WRITE_COUNT", None)
for now, breaking, run, want in (("2026-10-24T07:15:00", True, "", "2026-10-24"),      # BST: 08:15 UK
                                 ("2026-10-25T07:15:00", True, "", "2026-10-25"),      # GMT: 07:15 UK (yesterday until this fix)
                                 ("2026-10-25T06:20:00", True, "", "2026-10-24"),      # 06:20 UK: its Shorts go out before 07:30
                                 ("2026-10-25T08:35:00", False, "morning", "2026-10-25"),
                                 ("2026-10-25T18:45:00", False, "evening", "2026-10-26"),
                                 ("2026-11-01T07:15:00", True, "", "2026-11-01")):
    W.NOW = at(now)
    got = W.plan(breaking, run)[1]
    assert str(got) == want, (now, got, want)
print("1 writer day ok")

# 2. the slot grid is UK wall time: 07:30 UK is 06:30 UTC in summer and 07:30 UTC from 25 October; the night of the change
# (01:00 to 02:00 UK happens twice) never repeats or loses a slot
import plan as P
P.learned_slots = lambda n: None
P.CFG = dict(P.CFG, slot_first="07:30")
s24, s25 = P.day_slots(dt.date(2026, 10, 24)), P.day_slots(dt.date(2026, 10, 25))
assert s24[0] == at("2026-10-24T06:30:00") and s25[0] == at("2026-10-25T07:30:00"), (s24[0], s25[0])
both = sorted(s24 + s25)
assert len(set(both)) == len(both) and all(b > a for a, b in zip(both, both[1:]))
print("2 slots ok")

# 3. the clips batch: 19:00 UK is 18:00 UTC until today and 19:00 UTC from 25 October
import clips as C
C.CFG = dict(C.CFG, batch_time="19:00", batch_times={})
for now, want in (("2026-10-24T12:10:00", "2026-10-24T18:00:00Z"), ("2026-10-25T12:10:00", "2026-10-25T19:00:00Z"),
                  ("2026-11-02T12:10:00", "2026-11-02T19:00:00Z")):
    C.NOW = at(now)
    assert C.batch_time()[0] == want, (now, C.batch_time())
print("3 clips batch ok")

# 4. the clips social run (crons 16:31 and 17:31 UTC, started by GitHub 20 to 60 minutes late) waits for 19:01 UK when the
# batch is under 100 minutes away and otherwise leaves it to the later run: the workflow's own code, run at fixed times
code = re.search(r'wait=\$\(python -c "(.+?)"\)', (_p.Path(REPO_DIR) / ".github" / "workflows" / "clips.yml").read_text()).group(1)
def wait_at(now):
    real = sys.modules["datetime"]
    class Fixed(real.datetime):
        @classmethod
        def now(cls, tz=None): return at(now).astimezone(tz) if tz else at(now)
    shim = types.ModuleType("datetime"); shim.__dict__.update(real.__dict__); shim.datetime = Fixed
    out = io.StringIO()
    sys.modules["datetime"] = shim
    try:
        with contextlib.redirect_stdout(out): exec(code, {})
    finally: sys.modules["datetime"] = real
    return int(out.getvalue().strip())
assert wait_at("2026-10-24T16:55:00") == 3960      # BST: 17:55 UK, waits 66 minutes for 19:01
assert wait_at("2026-10-24T17:55:00") == 360       # the 17:31 run, queued behind it, runs straight after
assert wait_at("2026-10-25T16:55:00") == -1        # GMT: 16:55 UK is over 100 minutes away, the 17:31 run posts
assert wait_at("2026-10-25T17:55:00") == 3960      # GMT: the 17:31 run waits 66 minutes for 19:01
assert wait_at("2026-10-25T19:20:00") == 0         # a run GitHub started late goes at once
print("4 clips social wait ok")
print("clock change ok")
