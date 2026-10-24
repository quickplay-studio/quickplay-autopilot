"""Offline test of the change ledger (pipeline/changes.py) on synthetic data: better, worse, too early, trade-off (and its
issue, opened once and closed when kept), overlap, the automatic decisions scored once, the CLI."""
import csv, datetime as dt, pathlib as _p, sys, tempfile
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO_DIR + "/pipeline")
import changes as C

UTC = dt.timezone.utc
TODAY = dt.date(2026, 11, 1)
NOW = dt.datetime(2026, 11, 1, 12, tzinfo=UTC)
D = lambda m, d: dt.date(2026, m, d)


def write(p, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r)) or ["x"]
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows(rows)


def world(spec, decisions=()):
    """spec: [(first day, last day, Shorts a day, fields)] -> a temporary repository the ledger reads."""
    root = _p.Path(tempfile.mkdtemp(prefix="qp-ledger-"))
    (root / "analytics").mkdir(); (root / "clips").mkdir()
    rows, i = [], 0
    for a, b, n, fields in spec:
        d = a
        while d <= b:
            for k in range(n):
                i += 1
                r = {"short": f"QD-{i:03d}", "title": "a title", "posted": dt.datetime(d.year, d.month, d.day, 11, k, tzinfo=UTC).isoformat(),
                     "category": "Music", "yt_views": "100", "views_24h": "100", "views_vs_typical": "1.0"}
                r.update(fields(k) if callable(fields) else fields); rows.append(r)
            d += dt.timedelta(days=1)
    write(root / "analytics" / "shorts.csv", rows)
    snaps, d, j = [], D(9, 20), 0
    while d <= TODAY:
        snaps.append({"day": str(d), "source": "snapshot", "yt_views_total": str(1000 * j)}); d += dt.timedelta(days=1); j += 1
    write(root / "analytics" / "daily.csv", snaps)
    if decisions: write(root / "analytics" / "decisions.csv", list(decisions))
    (root / "clips" / "campaigns.json").write_text('{"campaigns": {}}')
    C.ROOT = root
    return root


calls = {"raise": [], "clear": []}
def stub_raise(t, b): calls["raise"].append((t, b))
def stub_clear(t, b): calls["clear"].append((t, b))
def run(today=TODAY):
    return {r["id"]: r for r in C.check(today=today, now=dt.datetime(today.year, today.month, today.day, 12, tzinfo=UTC),
                                        raise_issue=stub_raise, clear=stub_clear)}


# 1. better, worse, too early (live, then final), overlapped
world([(D(10, 3), D(10, 9), 2, {"views_24h": "100", "yt_avg_viewed_pct": "50"}),
       (D(10, 10), D(10, 16), 2, {"views_24h": "150", "yt_avg_viewed_pct": "60"}),
       (D(10, 17), D(10, 23), 2, {"views_24h": "150"}),
       (D(10, 24), D(10, 31), 2, {"views_24h": "100"})])
rows = []
a = C.add("shorts", "A: hooks", "more views", "yt_views_24h", "uploads_day", date="2026-10-10", rows=rows)
b = C.add("writer", "B: worse writer", "more views", "yt_views_24h", "", date="2026-10-24", rows=rows)
e = C.add("shorts", "E: no data", "held longer", "held_3s", "", date="2026-10-20", rows=rows)
d = C.add("shorts", "D: not due", "more subscribers", "subs_per_1k", "", date="2026-10-28", rows=rows)
f = C.add("shorts", "F: first of two", "watched longer", "avg_viewed_pct", "", date="2026-10-10", rows=rows)
g = C.add("shorts", "G: second of two", "watched longer", "avg_viewed_pct", "", date="2026-10-13", rows=rows)
assert [r["id"] for r in rows] == ["CH-001", "CH-002", "CH-003", "CH-004", "CH-005", "CH-006"] and a["check_on"] == "2026-10-17"
C.save(rows)
got = run()
assert got["CH-001"]["verdict"] == "better" and got["CH-001"]["status"] == "checked", got["CH-001"]
assert "100 -> 150 (+50%, n 14/14)" in got["CH-001"]["result"] and "Shorts posted a day 2 -> 2 ok" in got["CH-001"]["result"], got["CH-001"]["result"]
assert got["CH-002"]["verdict"] == "worse" and "-33%" in got["CH-002"]["result"], got["CH-002"]
assert got["CH-003"]["verdict"] == "too early" and got["CH-003"]["status"] == "live", got["CH-003"]
assert got["CH-004"]["verdict"] == "" and got["CH-004"]["status"] == "live", got["CH-004"]
assert got["CH-005"]["verdict"] == "overlapped" and "CH-006" in got["CH-005"]["result"], got["CH-005"]
assert got["CH-006"]["verdict"] == "overlapped" and "CH-005" in got["CH-006"]["result"], got["CH-006"]
assert not calls["raise"], calls
late = run(D(10, 31) + dt.timedelta(days=1) + dt.timedelta(days=30))          # long after: "too early" becomes final
assert late["CH-003"]["status"] == "checked" and late["CH-003"]["verdict"] == "too early", late["CH-003"]
assert late["CH-001"]["result"] == got["CH-001"]["result"]                     # a checked row is never judged again
print("ledger verdicts ok")

# 2. a trade-off: the target better, a guardrail more than 15% worse; the issue opens once and closes when kept
calls["raise"].clear(); calls["clear"].clear()
world([(D(10, 3), D(10, 9), 4, {"yt_held_3s_pct": "60"}), (D(10, 10), D(10, 16), 2, {"yt_held_3s_pct": "80"})])
C.save([]); C.add("shorts", "Faster first frame", "held longer", "held_3s", "uploads_day", date="2026-10-10")
got = run()
assert got["CH-001"]["verdict"] == "trade-off" and "Shorts posted a day 4 -> 2 BROKEN (-50%)" in got["CH-001"]["result"], got["CH-001"]
assert len(calls["raise"]) == 1 and calls["raise"][0][0] == C.TRADE_TITLE and "CH-001" in calls["raise"][0][1], calls
run(); assert len(calls["raise"]) == 1, "the same trade-off is not raised again"
C.main(["set", "CH-001", "--status", "kept"])
run(); assert len(calls["clear"]) == 1 and not C.open_tradeoffs(C.load()), calls
print("trade-off ok")

# 3. the writer's automatic decisions: scored once each, on the value's Shorts against the week's others
music = {"category": "Music", "views_vs_typical": "1.5", "views_24h": "100"}
sport = {"category": "Sport", "views_vs_typical": "1.0", "views_24h": "100"}
world([(D(10, 3), D(10, 9), 2, lambda k: music if k == 0 else sport), (D(10, 10), D(10, 16), 2, lambda k: music if k == 0 else sport)],
      decisions=[{"date": "2026-10-10", "area": "Category", "change": 'Lean towards category "Music"', "why": "1.6x typical",
                  "evidence": "drivers.csv: category = Music, n 5, lift 1.6, median 2.0", "check_on": "2026-10-17", "by": C.AUTO},
                 {"date": "2026-10-10", "area": "Category", "change": 'Use less category "Sport"', "why": "0.7x typical",
                  "evidence": "drivers.csv: category = Sport, n 5, lift 0.7, median 0.6", "check_on": "2026-10-17", "by": C.AUTO},
                 {"date": "2026-10-30", "area": "Category", "change": 'Lean towards category "Film"', "why": "1.4x typical",
                  "evidence": "drivers.csv: category = Film, n 5, lift 1.4, median 1.5", "check_on": "2026-11-06", "by": C.AUTO},
                 {"date": "2026-10-10", "area": "Volume", "change": "Back to 24 Shorts a day", "why": "Charlie asked",
                  "evidence": "", "check_on": "2026-10-17", "by": "Claude (at Charlie's request)"}])
C.save([])
got = run()
auto = [r for r in got.values() if r["by"] == C.AUTO]
assert len(auto) == 2, auto                                             # not yet due, and Claude's own rows, are left out
push = next(r for r in auto if "Music" in r["change"]); cut = next(r for r in auto if "Sport" in r["change"])
assert push["verdict"] == "better" and "1.50x the week's other Shorts (n 7 against 7)" in push["result"] and "used in 50% of Shorts before, 50% after" in push["result"], push
assert cut["verdict"] == "better" and "0.67x" in cut["result"] and "confirmed weak" in cut["result"], cut
again = run()
assert len([r for r in again.values() if r["by"] == C.AUTO]) == 2, "each decision is imported once"
print("automatic decisions ok")

# 4. the CLI and its checks
world([(D(10, 3), D(10, 9), 1, {})]); C.save([])
C.main(["add", "--area", "clips", "--change", "Spoken take", "--hypothesis", "shown more", "--target", "clip_views",
        "--guardrails", "clips_day;submissions_day", "--date", "2026-10-20"])
r = C.load()[0]
assert r["id"] == "CH-001" and r["check_on"] == "2026-10-27" and r["guardrails"] == "clips_day;submissions_day" and r["status"] == "live", r
for bad in (["add", "--area", "clips", "--change", "x", "--hypothesis", "y", "--target", "nonsense"],
            ["add", "--area", "moon", "--change", "x", "--hypothesis", "y", "--target", "clip_views"]):
    try: C.main(bad); raise AssertionError(bad)
    except SystemExit: pass
try: C.add("clips", "x", "y", "clip_views", "views_of_the_moon"); raise AssertionError("an unknown guardrail must fail")
except ValueError: pass
assert list(C.load()[0]) == C.FIELDS
import weekly_report as W
lines = W.ledger_lines(dt.datetime(2026, 10, 25, tzinfo=UTC), dt.datetime(2026, 11, 1, tzinfo=UTC))
assert any("CH-001" in x and "Spoken take" in x for x in lines), lines
print("ledger CLI ok")
