"""Offline tests of the arms that act after the writing (24 October, data report items 4 and 7):
1. writer.test_plan: the round's fx_energy and fx_slot arms on every non-exploration Short, about 50/50; never on an
   exploration Short (its look and hour are drawn evenly);
2. looks.choose honours the camera-energy arm (not for an exploration Short, not an unknown option), and the "never the
   same look twice" nudge leaves it alone;
3. plan.py's slot picker honours the posting-quarter arm on the board's own day, keeps 1 board in 5 in the first slot,
   never makes a Short late for an arm (breaking news only within its 6 hours), and finds a half hour in the quarter
   when the grid's slots there are taken;
4. factpack.writer_test: 6 boards in 10, 50/50 between gpt-oss-120b and Gemini Flash, only while both have a model, only
   within the dates; writer_arm_of names the arm of any model label;
5. writer.write_board: the assigned arm's model is asked first (unless capped), and the board records the arm as
   assigned and as used;
6. drivers.features and analytics.test_progress: the arms judged as assigned, with how often each was followed."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import collections, datetime as dt, json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
sys.argv = ["analytics.py", "--fast"]

# 1. the writer's test plan
import writer as W
day = dt.date(2026, 10, 26)
W.CFG["test_round"] = {"name": "round 1", "start": "2026-10-25", "per_arm": 70,
                       "factors": {"hook_type": ["statement", "number"], "fx_energy": ["steady", "lab-energy-1019"], "fx_slot": ["06:00 to 12:00", "12:00 to 18:00"]}}
W.winners = lambda: {}
W.stopped = lambda: {}
seen = collections.Counter()
for k in range(400):
    _, picks = W.test_plan(k, "news", today=day)
    assert picks["fx_energy"] in ("steady", "lab-energy-1019") and picks["fx_slot"] in ("06:00 to 12:00", "12:00 to 18:00"), picks
    seen[picks["fx_energy"]] += 1; seen[picks["fx_slot"]] += 1
assert 160 <= seen["steady"] <= 240 and 160 <= seen["06:00 to 12:00"] <= 240, seen
for k in range(50):
    _, picks = W.test_plan(k, "news", explore=True, today=day)
    assert not set(picks) & {"fx_energy", "fx_slot"} and picks["explore"] == "yes", picks
_, before = W.test_plan(7, "news", today=dt.date(2026, 10, 24))          # before the round: no round factors forced
assert before.get("round") is None
assert W.style_note({"fx_energy": "lab-energy-1019", "fx_slot": "06:00 to 12:00"}) == ""     # nothing for the prompt
print("1 test plan ok")

# 2. looks.choose
import looks as LK
cat = LK.catalogue()
lab_e = next(k for k in LK.active(cat, "energy") if k != "steady")       # whatever variant the look lab runs today
for i in range(30):
    assert LK.choose(f"QD-{i}", [], {}, cat, energy=lab_e)["energy"] == lab_e
    assert LK.choose(f"QD-{i}", [], {}, cat, energy="steady")["energy"] == "steady"
assert len({LK.choose(f"QD-{i}", [], {}, cat, explore=True, energy="steady")["energy"] for i in range(60)}) > 1    # exploration: drawn evenly
assert LK.choose("QD-1", [], {}, cat, energy="wobbly")["energy"] in LK.active(cat, "energy")                  # unknown: ignored
assert LK.choose("QD-1", [], {}, cat, energy="punchy")["energy"] in LK.active(cat, "energy")                  # retired: never brought back
first = LK.choose("QD-9", [], {}, cat, energy="steady")
again = LK.choose("QD-9", [first], {}, cat, energy="steady")      # the same look twice running is nudged, never the arm
assert again["energy"] == "steady" and any(again[d] != first[d] for d in first), (first, again)
print("2 looks ok")

# 3. the slot picker
import plan as P
(SCRATCH / "analytics").mkdir()
P.ROOT = SCRATCH
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(24)]          # a slot every hour
P.LEAD = dt.timedelta(hours=1)
uk = lambda t: t.astimezone(P.UK)
at = lambda d, h, m=0: dt.datetime(2026, 10, d, h, m, tzinfo=P.UK).astimezone(dt.timezone.utc)
now = at(24, 5, 10)                                                        # first free slot 07:00 UK (06-12)
hours = collections.Counter()
for i in range(60):
    hours[uk(P.slot_picker(now, set())("2026-10-24", "Music", "news", f"QD-{i}", arm="12:00 to 18:00")).hour] += 1
assert set(hours) == {12, 7} and 40 <= hours[12] <= 55, hours              # the arm's quarter, 1 in 5 keeps the first slot
assert uk(P.slot_picker(now, set())("2026-10-24", "Music", "news", "QD-3", arm="06:00 to 12:00")).hour == 7    # already in it
moved = [i for i in range(60) if uk(P.slot_picker(now, set())("2026-10-24", "Music", "news", f"QD-{i}", arm="12:00 to 18:00")).hour == 12]
sid = f"QD-{moved[0]}"
# breaking news: only within its 6 hours (from 00:10 UK the first slot is 02:00, 12:00 is out of reach)
assert uk(P.slot_picker(at(24, 0, 10), set())("2026-10-24", "Music", "breaking", sid, arm="12:00 to 18:00")).hour == 2
assert uk(P.slot_picker(at(24, 0, 10), set())("2026-10-24", "Music", "follow-up", sid, arm="12:00 to 18:00")).hour == 2   # a follow-up too
assert uk(P.slot_picker(at(24, 0, 10), set())("2026-10-24", "Music", "news", sid, arm="12:00 to 18:00")).hour == 12       # news: its own day
# never late: written for the 24th at 19:10, the morning quarter is tomorrow, so the usual slot instead
t = P.slot_picker(at(24, 19, 10), set())("2026-10-24", "Music", "news", sid, arm="06:00 to 12:00")
assert uk(t).date() == dt.date(2026, 10, 24) and uk(t).hour == 21, uk(t)
# written in the evening for tomorrow: the arm's quarter on its own day (the 25th, the day the clocks go back)
t = P.slot_picker(at(24, 20, 0), set())("2026-10-25", "Music", "news", sid, arm="12:00 to 18:00")
assert uk(t).date() == dt.date(2026, 10, 25) and 12 <= uk(t).hour < 18, uk(t)
# the grid's slots in the quarter taken: a half hour in it at least 45 minutes from every taken slot
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(0, 24, 3)]    # a slot every 3 hours: 12:00 and 15:00 in 12-18
taken = {at(24, 12), at(24, 15)}
t = P.slot_picker(now, taken)("2026-10-24", "Music", "news", sid, arm="12:00 to 18:00")
assert uk(t).hour == 13 and uk(t).minute == 0 and t in taken, uk(t)      # 12:30 is too close to 12:00
# no arm, no data: the first slot, as before; an exploration Short ignores the arm (plan.main never passes one)
assert uk(P.slot_picker(now, set())("2026-10-24", "Music", "news", sid)).hour == 9
print("3 slot picker ok")

# 4. the writer-model test's draw
import factpack as F
F.CFG["writer_test"] = {"start": "2026-10-25", "until": "2026-11-08", "share": 0.6, "arms": ["gpt-oss-120b", "gemini flash"]}
order = ["cloudflare:@cf/openai/gpt-oss-120b", "groq:openai/gpt-oss-120b", "gemini:gemini-3.7-flash", "gemini:gemma-3-27b-it",
         "gemini:gemini-3.7-flash-lite", "claude:sonnet"]
F.STATE.clear()
got = [F.writer_test(k, day, order) for k in range(1000)]
inside = [g for g in got if g[0]]
assert 540 <= len(inside) <= 660, len(inside)
arms = collections.Counter(a for a, _ in inside)
assert 0.4 <= arms["gpt-oss-120b"] / len(inside) <= 0.6, arms
assert {l for a, l in inside if a == "gpt-oss-120b"} == {"groq:openai/gpt-oss-120b"}       # groq's, the one the data measured
assert {l for a, l in inside if a == "gemini flash"} == {"gemini:gemini-3.7-flash"}          # never Lite or Gemma
assert F.writer_test(5, day, order) == F.writer_test(5, day, order)                           # the same board, the same arm
assert all(F.writer_test(k, dt.date(2026, 10, 24), order) == ("", None) for k in range(50))   # before the start
assert all(F.writer_test(k, dt.date(2026, 11, 9), order) == ("", None) for k in range(50))    # after the end
F.STATE["spent_models"] = {"gemini-3.7-flash"}                                                # Flash out of quota this run
assert all(F.writer_test(k, day, order) == ("", None) for k in range(50))                     # no test without both arms
F.STATE["spent_models"] = {"groq:openai/gpt-oss-120b"}
assert {l for a, l in (F.writer_test(k, day, order) for k in range(200)) if a == "gpt-oss-120b"} == {"cloudflare:@cf/openai/gpt-oss-120b"}
F.STATE.clear()
assert F.writer_arm_of("gemini-3.7-flash") == "gemini flash" and F.writer_arm_of("gemini:gemini-3.7-flash") == "gemini flash"
assert F.writer_arm_of("groq:openai/gpt-oss-120b") == "gpt-oss-120b" and F.writer_arm_of("sambanova:gpt-oss-120b") == "gpt-oss-120b"
assert F.writer_arm_of("gemini-3.7-flash-lite") == "other" and F.writer_arm_of("cerebras:llama-3.3-70b") == "other"
print("4 writer test draw ok")

# 5. write_board: the arm's model asked first, assigned and used recorded
asked = []
def fake_gemini(prompt, schema=None, timeout=100, temperature=0.1, lite=False, prefer=None, writing=False):
    asked.append(prefer)
    return {"beats": [{"say": "x"}], "meta": {"title": "t"}}, ANSWER[0]
ANSWER = ["groq:openai/gpt-oss-120b"]
W.factpack.gemini = fake_gemini
W.factpack.writer_test = lambda k, today=None, order=None: ("gpt-oss-120b", "groq:openai/gpt-oss-120b")
W.claude_arm = lambda sid: None
W.choose_writer = lambda sid: "gemini:gemini-3.7-flash"
W.clean = lambda a: dict(a); W.unwiki = lambda b: None; W.pack_text = lambda p: "pack"
W.BG.fill = lambda b: 0
W.validate.check = lambda b, *a: ([], [])
W.media_problems = lambda b: []; W.fact_check = lambda b, p: []
W.writer_capped = lambda m, stats=None: False
b, note = W.write_board({}, "QD-500", day, "head", tests={"hook_type": "statement"})
assert asked[-1] == "groq:openai/gpt-oss-120b", asked
assert b["test"]["writer_arm"] == "gpt-oss-120b" and b["test"]["writer_arm_used"] == "gpt-oss-120b" and b["test"]["hook_type"] == "statement", b["test"]
ANSWER[0] = "gemini-3.7-flash"                                     # the arm's model failed: the chain's next one wrote it
b, _ = W.write_board({}, "QD-501", day, "head", tests={})
assert b["test"]["writer_arm"] == "gpt-oss-120b" and b["test"]["writer_arm_used"] == "gemini flash", b["test"]
W.writer_capped = lambda m, stats=None: True                       # the 35% cap: the writer's own pick, the arm still recorded
b, _ = W.write_board({}, "QD-502", day, "head", tests=None)
assert asked[-1] == "gemini:gemini-3.7-flash" and b["test"]["writer_arm"] == "gpt-oss-120b", (asked, b.get("test"))
W.factpack.writer_test = lambda k, today=None, order=None: ("", None)
b, _ = W.write_board({}, "QD-503", day, "head", tests={"hook_type": "number"})
assert "writer_arm" not in b["test"] and asked[-1] == "gemini:gemini-3.7-flash"
print("5 write_board ok")

# 6. judged as assigned, followed or not
import drivers as DRV, analytics as A
r = {"short": "QD-600", "posted": "2026-10-26T09:00+00:00", "views_24h": "50", "hook": "Raye just did this", "fx_energy": "steady",
     "fx_energy_used": "steady", "fx_slot": "06:00 to 12:00", "fx_slot_used": "12:00 to 18:00", "writer_arm": "gpt-oss-120b",
     "writer_arm_used": "gpt-oss-120b"}
f = DRV.features(r)
assert f["fx_energy"] == "steady" and f["fx_slot"] == "06:00 to 12:00" and f["writer_arm"] == "gpt-oss-120b", f
assert {"fx_energy", "fx_slot", "writer_arm"} <= DRV.PIPELINE_ONLY and {"fx_energy", "fx_slot", "writer_arm"} <= DRV.NEVER_PAUSED
A.OUT = SCRATCH / "analytics"
A.CFG["test_round"] = dict(W.CFG["test_round"])
A.CFG["writer_test"] = dict(F.CFG["writer_test"])
rows = [dict(r, short=f"QD-{600 + i}", fx_slot_used=("06:00 to 12:00" if i % 4 else "12:00 to 18:00")) for i in range(8)]
lines = A.test_progress(rows, [], today=dt.date(2026, 10, 27))
t = json.loads((A.OUT / "tests.json").read_text())
assert t["factors"]["fx_slot"]["arms"]["06:00 to 12:00"]["n"] == 8 and t["factors"]["fx_slot"]["followed_pct"] == 75, t["factors"]["fx_slot"]
assert t["factors"]["fx_energy"]["followed_pct"] == 100 and t["factors"]["writer_arm"]["arms"]["gpt-oss-120b"]["n"] == 8, t["factors"]
assert t["factors"]["fx_slot"]["label"] == "posting quarter (UK)" and any("writer model" in l for l in lines), lines
print("6 judged as assigned ok")
print("factorial arms ok")
