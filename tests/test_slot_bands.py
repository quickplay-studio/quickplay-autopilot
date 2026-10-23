"""Offline test of timing by category (Charlie, 23 October: post music when the Americans watch): band scores from
analytics/slots.json, a board moved to its category's best quarter of the UK day only when the data is clearly better,
news kept close, and 1 board in 5 left in the first slot so every hour stays measured."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import plan as P

(SCRATCH / "analytics").mkdir()
P.ROOT = SCRATCH
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(24)]          # a slot every hour
P.LEAD = dt.timedelta(hours=1)
(SCRATCH / "analytics" / "slots.json").write_text(json.dumps({"bands": {
    "_all": {b: {"n": 30, "score": 1.0} for b in P.BANDS},
    "Music": {"00-06": {"n": 8, "score": 4.5}, "06-12": {"n": 4, "score": 1.2}, "12-18": {"n": 11, "score": 1.0}, "18-24": {"n": 3, "score": 1.0}},
    "Tech": {"12-18": {"n": 3, "score": 9.0}}}}))           # too few Shorts: no opinion yet

sc = P.band_scores()
assert set(sc) == {"Music"} and sc["Music"]["00-06"] > 2.5 and abs(sc["Music"]["12-18"] - 1.0) < 1e-9, sc
now = dt.datetime(2026, 10, 24, 13, 10, tzinfo=P.UK).astimezone(dt.timezone.utc)     # 13:10 UK: first free slot 15:00

picks = []
for i in range(40):
    nxt = P.slot_picker(now, set())
    picks.append(nxt("2026-10-24", "Music", "evergreen", f"QD-{i}").astimezone(P.UK).hour)
moved = sum(1 for h in picks if h < 6)
assert 25 <= moved <= 38 and set(picks) <= {15, 0}, picks           # most go to midnight UK (US evening), about 1 in 5 stays
nxt = P.slot_picker(now, set())
assert nxt("2026-10-24", "Music", "news", "QD-1").astimezone(P.UK).hour == 15     # news: midnight is past the 6-hour window
assert P.slot_picker(now, set())("2026-10-24", "Tech", "evergreen", "QD-1").astimezone(P.UK).hour == 15
assert P.slot_picker(now, set())("2026-10-24").astimezone(P.UK).hour == 15          # old callers: first free slot
taken = set(); nxt = P.slot_picker(now, taken)
a, b = nxt("2026-10-24", "Music", "evergreen", "QD-2"), nxt("2026-10-24", "Music", "evergreen", "QD-3")
assert a != b and {a, b} <= taken                                          # a slot is never given twice
print("slot bands ok", picks[:10])
