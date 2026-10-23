"""Offline test of the rule and law watch (pipeline/policy_watch.py): feed items are read, sorted by a stubbed model,
act and watch items logged to docs/POLICY.md with their links, an issue opened only for act, and items never re-read."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import policy_watch as P, factpack
P.SEEN, P.LOG = SCRATCH / "seen.json", SCRATCH / "POLICY.md"
P.FEEDS = [("YouTube blog", "https://blog.youtube/rss/")]
RSS = b"""<rss><channel><item><title>Shorts: original content gets priority</title><link>https://x/1</link><pubDate>1 Oct</pubDate></item>
<item><title>New cat filters</title><link>https://x/2</link></item><item><title>Partner Programme tweak</title><link>https://x/3</link></item></channel></rss>"""
class R:
    content = RSS
P.requests.get = lambda *a, **k: R()
factpack.gemini = lambda *a, **k: ({"items": [{"n": 1, "level": "act", "note": "Reposted clips lose reach \u2014 add our own take."},
                                              {"n": 2, "level": "ignore"}, {"n": 3, "level": "watch", "note": "Thresholds may change."}]}, "stub")
CALLS = []
P.subprocess.run = lambda cmd, **k: (CALLS.append(cmd), type("X", (), {"stdout": "ok", "stderr": ""})())[1]
got = P.run()
assert [g["level"] for g in got] == ["act", "watch"]
log = P.LOG.read_text()
assert "[act] Reposted clips lose reach, add our own take." in log and "https://x/3" in log and "cat filters" not in log, log
issues = [c for c in CALLS if c[:3] == ["gh", "issue", "create"]]
assert len(issues) == 1 and "Rule changes to act on" in issues[0][4] and "original content" in issues[0][8], issues
assert P.recent("Mon, 1 Jan 2024 10:00:00 GMT") is False and P.recent("") is True
assert P.run() == []                       # nothing new the second time
print("policy watch ok")
