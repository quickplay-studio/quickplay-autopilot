"""Offline test of pipeline/hub_md.py, the hub inside GitHub (28 October): README.md built from small fixture files in a temp dir.
Section order, checkbox actions with their links, the YPP table, the mermaid xychart-beta block, the ledger and the contests,
the key table with fix links, the router row, the channel lines; every file missing or malformed gives "Not available yet."
and never an exception; no em or en dash anywhere; no key value ever appears; gh is skipped without GH_TOKEN. No live file is read."""
import csv, datetime as dt, json, os, pathlib, sys, tempfile

REPO_DIR = str(pathlib.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import hub_md as H

EM, EN = "—", "–"
FAKE = "sk-FAKEKEYVALUE1234567890abcdefXYZ"          # a key that must never reach the page
FAKE2 = "0123456789abcdef0123456789abcdef01234567"    # a long token-shaped string
NOW = dt.datetime(2026, 10, 28, 11, 40, tzinfo=dt.timezone.utc)      # 28 October is GMT in London (BST ended on the 25th)
ORDER = ["# Quickplay hub", "## Your actions", "## YPP progress", "## Is it getting better", "## Tests and changes", "## Keys", "## Channels"]


def put(root, rel, data):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data if isinstance(data, str) else json.dumps(data))


def put_csv(root, rel, head, rows):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=head); w.writeheader(); [w.writerow(r) for r in rows]


def fixture(root, router_ok=True):
    days = [f"2026-10-{d}" for d in range(14, 27)]
    put(root, "status/actions.json", [
        {"id": "fb", "title": f"Check the Page {EM} it may be restricted", "due": "2026-10-27", "issue": 34, "done": False},
        {"id": "mistral", "title": "A Mistral key", "due": "2026-10-30", "links": [{"label": "Mistral", "url": "https://console.mistral.ai/"}], "done": False},
        {"id": "far", "title": "Renew later", "due": "2026-12-10", "issue": 36, "done": False},
        {"id": "ok", "title": "Already done", "done": True}])
    put(root, "status/keys.json", {"checked": "2026-10-28T10:05+00:00", "keys": [
        {"id": "youtube", "what": "YouTube sign-in: Quickplay Daily", "group": "YouTube", "status": "ok", "expires": "", "needed": True,
         "detail": f"works, key {FAKE}", "value": FAKE, "secret": FAKE, "token": FAKE2, "fix": []},
        {"id": "instagram", "what": "Instagram key", "group": "Instagram", "status": "ok", "expires": "2026-12-22", "fix": []},
        {"id": "GROQ_API_KEY", "what": "Groq API key", "group": "AI models", "status": "failing", "expires": "", "needed": False,
         "detail": f"refused {FAKE}", "fix": ["Open https://console.groq.com/keys and press Create API Key.",
                                               "Paste it into the GitHub secret GROQ_API_KEY: https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/GROQ_API_KEY"]},
        {"id": "FB_TOKEN", "what": "Facebook key", "group": "Facebook", "status": "expiring", "expires": "2026-11-05", "fix": []},
        {"id": "CEREBRAS_API_KEY", "what": "Cerebras key", "group": "AI models", "status": "missing", "needed": False,
         "fix": ["Open https://cloud.cerebras.ai/ and generate one.", "Paste it: https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/CEREBRAS_API_KEY"]},
        {"id": "freellm", "what": "Router", "group": "AI models", "status": "ok", "fix": []}]})
    put(root, "status/freellm.json", {"ok": router_ok, "models": 26, "chat_platforms": ["kilo", "ovh"], "search_engines": [],
                                      "reason": "" if router_ok else f"image digest changed {FAKE}", "digest": FAKE2})
    put(root, "status/channel.json", {"uploads_last_24h": 19})
    put(root, "status/volume.json", {"per_day": 15})
    put(root, "config.json", {"clips_paused": "2026-10-26", "shorts_channels": {
        "gaming": {"name": "Quickplay Gaming Clips", "per_day": 6}, "music": {"name": "Quickplay Music", "per_day": 6}}})
    put_csv(root, "analytics/progress.csv", ["as_of", "subscribers", "engaged_views_90d", "views_last_24h"], [{"as_of": "x", "subscribers": 18, "engaged_views_90d": 12632, "views_last_24h": 4326}])
    put(root, "analytics/summary.json", {"youtube": {"subscribers": 18}})
    put(root, "analytics/improvement.json", {"goal": {"subs": 500, "views": 3000000, "subs_2027": 1000, "shorts_pool_2027": 10000000}, "days": days,
        "channel": {"engaged_day": [200 + 50 * i for i in range(10)] + [None] * 3, "engaged_day_7d": [None, None] + [300 + 40 * i for i in range(8)] + [None] * 3},
        "shorts": {"main": {"engaged_pct": {"week": [30.0] * 5 + [29.0] * 5 + [28.0] * 3}}}})
    put(root, "analytics/tests.json", {"factors": {
        "ending": {"label": "ending", "arms": {"loop": {"n": 8}, "question": {"n": 9}}, "verdict": "too few to tell", "days_left": 6},
        "replies": {"label": "comment replies", "arms": {"on": {"n": 22}, "off": {"n": 17}}, "verdict": "running", "leaning": "on", "days_left": 5}}})
    put(root, "analytics/evolve.json", {"champions": {"a": {}}, "adopted": {}, "genes": {"g1": {}, "g2": {}}})
    head = ["id", "date", "area", "change", "target", "status", "verdict", "by", "check_on"]
    put_csv(root, "analytics/changes.csv", head, [
        {"id": f"CH-{i:03d}", "date": "2026-10-2%d" % (i % 8), "area": "writer", "change": f"Change number {i} | with a pipe", "target": "yt_rel", "status": "checked",
         "verdict": ("better", "worse", "no change")[i % 3], "by": "analytics (automatic)" if i % 2 else "Claude (session)", "check_on": "2026-10-2%d" % (i % 8)} for i in range(1, 14)]
        + [{"id": "CH-014", "date": "2026-10-28", "area": "data", "change": "A live change", "target": "yt_views_day", "status": "live", "verdict": "", "by": "Claude (session)", "check_on": "2026-11-04"}])
    put_csv(root, "analytics/shorts.csv", ["short", "channel", "posted_day"], [
        {"short": "a", "channel": "main", "posted_day": "2026-10-28"}, {"short": "b", "channel": "main", "posted_day": "2026-10-28"},
        {"short": "c", "channel": "gaming", "posted_day": "2026-10-28"}, {"short": "d", "channel": "main", "posted_day": "2026-10-27"}])


def sections(text): return {h: text.split(h, 1)[1].split("\n## ", 1)[0].strip() for h in ORDER[1:] if h in text}


# 1. a full build: order, content, safety
tmp = pathlib.Path(tempfile.mkdtemp()); fixture(tmp)
issues = [{"number": 7, "title": f"Key failing {EN} fix it", "url": "https://github.com/quickplay-studio/quickplay-autopilot/issues/7", "createdAt": "2026-10-28T08:00:00Z"},
          {"number": 34, "title": "dup of an action's issue", "url": "https://x/34", "createdAt": "2026-10-24T08:00:00Z"}]
text = H.build(tmp, now=NOW, issues=issues)
pos = [text.index(h) for h in ORDER]
assert pos == sorted(pos), "sections out of order"
assert text.rstrip().splitlines()[-1].startswith("[How it works](docs/HOW_IT_WORKS.md)") and "analytics/weekly.md" in text and "/actions)" in text and "/issues)" in text
assert "Updated Wednesday 28 October, 11:40 UK." in text, text[:200]
assert len(text.splitlines()) < 150, len(text.splitlines())
assert EM not in text and EN not in text, "dash in the page"
assert FAKE not in text and FAKE2 not in text and "FAKEKEYVALUE" not in text, "a key value reached the page"
S = sections(text)
# actions: checkboxes, due words, links, the needs-charlie issue once, the done item absent
assert "- [ ] **Key failing - fix it** (alert, opened Wed 28 Oct): [issue #7](https://github.com/quickplay-studio/quickplay-autopilot/issues/7)" in S["## Your actions"], S["## Your actions"]
assert "overdue, was due Tue 27 Oct" in S["## Your actions"] and "[issue #34]" in S["## Your actions"] and "dup of an action" not in text
assert "(due Fri 30 Oct): [open](https://console.mistral.ai/)" in S["## Your actions"] and "Already done" not in text
assert "<summary>Coming up and optional (1)</summary>" in S["## Your actions"] and "Renew later" in S["## Your actions"]
# ypp
y = S["## YPP progress"]
assert "| Expanded, open now | 18 of 500 (3.60%) | 12,632 of 3,000,000 (0.42%) | 33,193 |" in y, y
assert "| Full, from 1 February 2027 | 18 of 1,000 (1.80%) | 12,632 of 10,000,000 (0.13%) | 110,971 |" in y
assert "| 4,326 | 19 | 96 |" in y and "(to Fri 23 Oct)" in y, y
# mermaid
b = S["## Is it getting better"]
assert "```mermaid\nxychart-beta\n" in b and '    x-axis ["14 Oct", "15 Oct"' in b and "    line [200, 250" in b and "    y-axis \"Views\" 0 --> " in b, b
assert b.count("line [") == 1 and "None" not in b and "7-day average: **580**" in b and "**28%**" in b, b
# tests and changes
t = S["## Tests and changes"]
assert t.index("comment replies") < t.index("| ending |") and "running, leaning on" in t and "loop 8, question 9" in t
assert "| Change | Date | What | Target | Verdict |" in t and t.count("| CH-0") == 8 and "CH-014 (Wed 4 Nov)" in t and "7 / with a pipe" in t
# keys: table, fix links, router, optional block
k = S["## Keys"]
assert k.startswith("**2 need fixing.**") and "| Groq API key | failing | none | [fix](https://console.groq.com/keys) / [add secret](https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/new) |" in k, k
assert "| Instagram key | ok | Tue 22 Dec 2026 |" in k and "| Facebook key | expiring | Thu 5 Nov 2026 |" in k
assert "| FreeLLMAPI router: 26 models on kilo, ovh; search: none | live | none | |" in k
assert "CEREBRAS_API_KEY ([sign up](https://cloud.cerebras.ai/))" in k and "<summary>Optional keys not set up (1)</summary>" in k
# channels
c = S["## Channels"]
assert "- **Quickplay Daily**: 2 of 15 posted today, sign-in ok" in c and "- **Quickplay Gaming Clips**: 1 of 6 posted today, no sign-in yet" in c and "Clipping paused since Mon 26 Oct" in c, c
# a failing router: state, link, secret-like text hidden
bad = tmp / "bad"; bad.mkdir(); fixture(bad, router_ok=False)
t2 = H.build(bad, now=NOW)
assert "| failing | none |" in t2 and "actions/workflows/freellm.yml" in t2 and FAKE not in t2 and "FAKEKEYVALUE" not in t2 and "(hidden)" in t2
assert "Key failing" not in t2 and "- [ ] **Check the Page - it may be restricted**" in t2        # no issues passed: that part is skipped quietly
# scrub and dashes alone
assert "[hidden]" in H.scrub(f"a {FAKE} b") and "[hidden]" in H.scrub(FAKE2) and "[hidden]" in H.scrub("ghp_abcdefghijklmnop")
assert H.scrub("quickplay-studio/quickplay-autopilot settings/secrets/actions/new CH-152 yt_views_24h") == "quickplay-studio/quickplay-autopilot settings/secrets/actions/new CH-152 yt_views_24h"
assert H.dashes(f"a {EM} b 2013{EN}2014") == "a - b 2013-2014"

# 2. every file missing: six "Not available yet." lines, no exception, the order kept
empty = pathlib.Path(tempfile.mkdtemp())
e = H.build(empty, now=NOW)
assert e.count(H.NA) == 6 and [e.index(h) for h in ORDER] == sorted(e.index(h) for h in ORDER), e
assert "Updated Wednesday 28 October, 11:40 UK." in e and EM not in e and EN not in e
assert H.build(empty, now=NOW, issues=[]).count(H.NA) == 5          # an empty issue list is still an answer for the actions

# 3. malformed files: wrong types, broken JSON and CSV, nulls
junk = pathlib.Path(tempfile.mkdtemp())
for rel in ("status/actions.json", "status/keys.json", "status/freellm.json", "status/channel.json", "status/volume.json", "config.json",
            "analytics/summary.json", "analytics/improvement.json", "analytics/tests.json", "analytics/evolve.json"):
    put(junk, rel, "{{{ not json")
for rel in ("analytics/progress.csv", "analytics/changes.csv", "analytics/shorts.csv"):
    (junk / rel).parent.mkdir(parents=True, exist_ok=True); (junk / rel).write_bytes(b"\xff\xfe\x00 not,a\ncsv\x00\x00")
j = H.build(junk, now=NOW); assert j.count(H.NA) >= 4 and "## Channels" in j
wrong = pathlib.Path(tempfile.mkdtemp())
put(wrong, "status/actions.json", {"items": [None, 5, {"title": None, "due": "tomorrow", "done": "no"}]})
put(wrong, "status/keys.json", {"keys": [None, 3, {"id": None, "status": "failing", "fix": "not a list", "expires": 5}], "checked": 7})
put(wrong, "analytics/improvement.json", {"days": "x", "channel": [], "shorts": None, "goal": []})
put(wrong, "analytics/tests.json", {"factors": {"a": None, "b": {"arms": "x", "days_left": "soon"}, "c": {"arms": {"x": None}}}})
put(wrong, "status/freellm.json", [1, 2])
put(wrong, "analytics/changes.csv", "id,date\nCH-1,notadate\n,\n")
put(wrong, "config.json", {"shorts_channels": {"a": 1, "b": None}})
w = H.build(wrong, now=NOW); assert [w.index(h) for h in ORDER] == sorted(w.index(h) for h in ORDER)

# 4. main writes README.md atomically (and gh is skipped without a token)
saved = {k: os.environ.pop(k, None) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
assert H.fetch_issues() is None
for k, v in saved.items():
    if v is not None: os.environ[k] = v
out = pathlib.Path(tempfile.mkdtemp()); fixture(out)
H.ROOT = out; H.fetch_issues = lambda: None; sys.argv = ["hub_md.py"]
H.main()
r = (out / "README.md").read_text()
assert r.startswith("# Quickplay hub") and not (out / "README.md.tmp").exists() and "Your actions" in r

# 5. the source itself has no em or en dash, and the repo front page is the hub with How it works one click away
src = pathlib.Path(REPO_DIR, "pipeline", "hub_md.py").read_text()
assert EM not in src and EN not in src
assert pathlib.Path(REPO_DIR, "docs", "HOW_IT_WORKS.md").exists()
print("hub_md: ok")
