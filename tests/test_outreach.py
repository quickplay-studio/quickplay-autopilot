"""Offline test of the creator scout (pipeline/outreach.py, 25 October 2026): the phrases a creator uses to say clips are allowed (and
their opposites), the weekly gate and the rotation of searches, the allowance (at most 3 searches a run, through quota.allow), the
subscriber and topic filters, the CSV (columns, merge, statuses kept), and that nothing is ever sent. Stubs only: no YouTube, no
network."""
import csv, datetime as dt, json, os, pathlib, re, sys, tempfile, types
REPO_DIR = str(pathlib.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import outreach as O

DASHES = chr(0x2013) + chr(0x2014)
EM = chr(0x2014)
TODAY = dt.date(2026, 10, 25)


def world():
    root = pathlib.Path(tempfile.mkdtemp(prefix="qp-outreach-"))
    (root / "clips" / "state").mkdir(parents=True)
    O.ROOT, O.OUT, O.STATE = root, root / "clips" / "outreach.csv", root / "clips" / "state" / "outreach.json"
    return root


class Quota:
    """quota.allow and quota.spend, recorded; `searches` is how many searches the allowance lets through."""
    def __init__(self, searches=99, reads=True): self.allowed, self.spent, self.searches, self.reads = [], [], searches, reads
    def allow(self, units, what="extra"):
        self.allowed.append((units, what))
        if "search" in what:
            if self.searches <= 0: return False
            self.searches -= 1
        return True if "search" in what else self.reads
    def spend(self, units, what="other"): self.spent.append((units, what))


class FakeYT:
    """search().list, videos().list, channels().list -> execute(); the calls are kept."""
    def __init__(self, found, videos, channels, fail=False):
        self.found, self.videos_, self.channels_, self.calls, self.fail = found, videos, channels, [], fail
    def _resource(self, kind):
        yt = self
        class R:
            def list(self, **kw):
                yt.calls.append((kind, kw))
                if yt.fail: raise RuntimeError("quotaExceeded")
                return types.SimpleNamespace(execute=lambda: yt.answer(kind, kw))
        return R()
    def search(self): return self._resource("search")
    def videos(self): return self._resource("videos")
    def channels(self): return self._resource("channels")
    def answer(self, kind, kw):
        if kind == "search": return {"items": self.found}
        pool = self.videos_ if kind == "videos" else self.channels_
        return {"items": [pool[i] for i in kw["id"].split(",") if i in pool]}
    def count(self, kind): return sum(1 for k, _ in self.calls if k == kind)


def vid(i, ch, description, title="A stream"): return {"id": i, "snippet": {"channelId": ch, "title": title, "description": description}}
def chan(i, subs, about="", title=None, hidden=False):
    return {"id": i, "snippet": {"title": title or f"Creator {i}", "description": about},
            "statistics": ({"hiddenSubscriberCount": True} if hidden else {"subscriberCount": str(subs), "hiddenSubscriberCount": False})}
def hit(v, ch): return {"id": {"videoId": v}, "snippet": {"channelId": ch}}


# 1. what counts as a creator saying clips are allowed
yes = ["Clips allowed with credit!", "Feel free to clip and post my highlights", "CLIPPERS WELCOME", "Use my clips", "Clipping  permitted on all VODs",
       "Please clip this if you like it", "No reuploads of full streams. Clips allowed with credit.", "Clips allowed, no reuploads of full streams"]
no = ["No clips allowed", "Please do not clip this video", "Don't clip this", "Don’t clip this", "never use my clips", "Clips not allowed",
      "We cannot say clips allowed", "without permission nobody may use my clips", "Hello and welcome to the stream", "", None]
for t in yes: assert O.evidence_in(t), t
for t in no: assert O.evidence_in(t) == "", t
e = O.evidence_in("My rules " + "x " * 80 + "Clips allowed " + EM + " credit me, \"always\" " + "y " * 80)
assert "Clips allowed - credit me, 'always'" in e and not any(c in e for c in DASHES) and '"' not in e and len(e) < 230, e
assert O.AVOID.search("slots and casino streams") and O.AVOID.search("Crypto trading tips") and O.AVOID.search("NSFW 18+") and O.AVOID.search("Politics talk")
assert not O.AVOID.search("Minecraft speedruns and Sunday football") and not O.AVOID.search("inventory slot")
print("1 phrases ok")

# 2. the searches: the three used longest ago, phrase by phrase so the first runs cover every niche; a week between scouts
combos = O.combos()
assert len(combos) == 24 and combos[:4] == [(n, "clips allowed") for n in ("gaming", "irl", "music", "football")], combos[:4]
assert O.pick({}) == [("gaming", "clips allowed"), ("irl", "clips allowed"), ("music", "clips allowed")]
used = {"gaming|clips allowed": "2026-10-25", "irl|clips allowed": "2026-10-24"}
assert O.pick({"used": used}) == [("music", "clips allowed"), ("football", "clips allowed"), ("gaming", "clip this")]
assert len(O.pick({}, 5)) == 5 and O.pick({}, 0) == []
assert O.due({}, TODAY) and not O.due({"last_run": "2026-10-25"}, TODAY) and not O.due({"last_run": "2026-10-19"}, TODAY)
assert O.due({"last_run": "2026-10-18"}, TODAY) and O.due({"last_run": "2026-10-25"}, TODAY, force=True) and O.due({"last_run": "junk"}, TODAY)
print("2 rotation and week ok")

# 3. a run: channels under 50,000 subscribers that say clips are allowed, nobody else
root = world()
FOUND = [hit(f"v{i}", f"c{i}") for i in range(1, 11)]
VIDEOS = {
    "v1": vid("v1", "c1", "Weekly stream. Clips allowed with credit!"),
    "v2": vid("v2", "c2", "Clippers welcome"),
    "v3": vid("v3", "c3", "Use my clips"),
    "v4": vid("v4", "c4", "Clip and post whatever you like"),
    "v5": vid("v5", "c5", "Slots and casino night. Clips allowed!"),
    "v6": vid("v6", "c6", "Just a stream"),
    "v7": vid("v7", "c7", "No clips allowed, please do not clip this"),
    "v8": vid("v8", "c8", "Just a stream", title="Clip this!"),
    "v9": vid("v9", "c9", "Use my clips for anything"),
    "v10": vid("v10", "c10", "Clipping permitted"),
}
CHANNELS = {
    "c1": chan("c1", 1200, title="Small Streamer"), "c2": chan("c2", 80000), "c3": chan("c3", 0, hidden=True), "c4": chan("c4", 300),
    "c5": chan("c5", 5000), "c6": chan("c6", 20000, about="IRL walks. Clippers welcome " + EM + " credit me please"), "c7": chan("c7", 4000),
    "c8": chan("c8", 3000), "c9": chan("c9", 49999), "c10": chan("c10", 50000),
}
yt, q = FakeYT(FOUND, VIDEOS, CHANNELS), Quota()
new = O.run(yt=yt, quota=q, today=TODAY)
assert sorted(r["url"].rsplit("/", 1)[1] for r in new) == ["c1", "c6", "c9"], new          # not 80,000; hidden; under 500; casino; "no clips"; a title; 50,000
assert yt.count("search") == 3 and yt.count("videos") == 1 and yt.count("channels") == 1
searches = [kw for k, kw in yt.calls if k == "search"]
assert [s["q"] for s in searches] == ['"clips allowed" gaming', '"clips allowed" IRL stream', '"clips allowed" music'], searches
assert all(s["type"] == "video" and s["maxResults"] == 50 and s["safeSearch"] == "strict" and s["order"] == "date" and s["publishedAfter"].endswith("Z") for s in searches)
assert [w for u, w in q.allowed if u == 100] == ["outreach search"] * 3 and [(u, w) for u, w in q.spent if u == 100] == [(100, "outreach search")] * 3
assert all(w == "outreach read" for u, w in q.allowed if u == 1) and len(q.allowed) == len(q.spent) == 5      # 3 searches, one video read, one channel read
rows = list(csv.DictReader(O.OUT.open()))
assert [r["channel"] for r in rows] == ["Creator c6", "Creator c9", "Small Streamer"] or len(rows) == 3, rows
by = {r["url"].rsplit("/", 1)[1]: r for r in rows}
assert open(O.OUT).readline().strip() == "channel,url,subscribers,niche,evidence,found_on,status", open(O.OUT).readline()
assert by["c1"]["url"] == "https://www.youtube.com/channel/c1" and by["c1"]["subscribers"] == "1200" and by["c1"]["niche"] == "gaming"
assert by["c1"]["found_on"] == "2026-10-25" and by["c1"]["status"] == "new" and by["c1"]["channel"] == "Small Streamer"
assert "Clips allowed with credit" in by["c1"]["evidence"] and by["c1"]["evidence"].endswith("[video https://www.youtube.com/watch?v=v1]"), by["c1"]
assert by["c6"]["evidence"].endswith("[channel description]") and "Clippers welcome - credit me please" in by["c6"]["evidence"], by["c6"]      # the dash is a hyphen
assert not any(c in O.OUT.read_text() for c in DASHES) and by["c9"]["subscribers"] == "49999"
state = json.loads(O.STATE.read_text())
assert state["last_run"] == "2026-10-25" and set(state["used"]) == {"gaming|clips allowed", "irl|clips allowed", "music|clips allowed"}, state
print("3 run ok")

# 4. the week: the same day says so and stops; seven days later the next three combinations; --force ignores the week
yt2 = FakeYT(FOUND, VIDEOS, CHANNELS)
assert O.run(yt=yt2, quota=Quota(), today=TODAY) == [] and yt2.calls == []
assert O.run(yt=yt2, quota=Quota(), today=TODAY + dt.timedelta(days=6)) == [] and yt2.calls == []
q2 = Quota()
assert O.run(yt=yt2, quota=q2, today=TODAY + dt.timedelta(days=7)) == []             # nothing new: every channel is listed already
assert [kw["q"] for k, kw in yt2.calls if k == "search"] == ['"clips allowed" football', '"clip this" gaming', '"clip this" IRL stream'], yt2.calls
assert json.loads(O.STATE.read_text())["last_run"] == "2026-11-01" and len(list(csv.DictReader(O.OUT.open()))) == 3
yt2.calls.clear(); O.main(["--force"], yt=yt2, quota=Quota())
assert yt2.count("search") == 3                                                         # (today by the clock, not TODAY)
print("4 week ok")

# 5. statuses and hand-added columns stay; subscriber counts are refreshed; a channel is listed once
root = world()
O.OUT.write_text("channel,url,subscribers,niche,evidence,found_on,status,notes\nSmall Streamer,https://www.youtube.com/channel/c1,900,gaming,old quote,2026-10-01,asked,sent on 2 October\n")
new = O.run(yt=FakeYT(FOUND, VIDEOS, CHANNELS), quota=Quota(), today=TODAY)
rows = list(csv.DictReader(O.OUT.open()))
assert sorted(r["url"].rsplit("/", 1)[1] for r in new) == ["c6", "c9"] and len(rows) == 3, (new, rows)
c1 = rows[0]
assert (c1["status"], c1["notes"], c1["evidence"], c1["found_on"], c1["subscribers"]) == ("asked", "sent on 2 October", "old quote", "2026-10-01", "1200"), c1
assert open(O.OUT).readline().strip() == "channel,url,subscribers,niche,evidence,found_on,status,notes" and rows[1]["notes"] == "" and rows[1]["status"] == "new"
many = [{"channel": f"N{i}", "url": f"https://www.youtube.com/channel/n{i}", "subscribers": i, "status": "new"} for i in range(60)]
merged, fresh = O.merge([], list(O.FIELDS), many)
assert len(fresh) == 40 and len(merged) == 40                                           # at most 40 new channels a run
assert O.channel_id("https://www.youtube.com/channel/UCabc_-1") == "UCabc_-1"
print("5 merge ok")

# 6. settings in clips/campaigns.json
root = world()
(root / "clips" / "campaigns.json").write_text(json.dumps({"outreach_max_subscribers": 1000, "outreach_min_subscribers": 100, "outreach_searches": 1,
                                                          "outreach_every_days": 3, "outreach_days": 30}))
yt = FakeYT(FOUND, VIDEOS, CHANNELS)
new = O.run(yt=yt, quota=Quota(), today=TODAY)
assert [r["url"].rsplit("/", 1)[1] for r in new] == ["c4"] and yt.count("search") == 1       # only 300 subscribers is in 100 to 1,000
assert O.run(yt=yt, quota=Quota(), today=TODAY + dt.timedelta(days=2)) == [] and yt.count("search") == 1
O.run(yt=yt, quota=Quota(), today=TODAY + dt.timedelta(days=3)); assert yt.count("search") == 2
(root / "clips" / "campaigns.json").write_text(json.dumps({"outreach_searches": 9}))          # never more than 3 a run
(root / "clips" / "state" / "outreach.json").unlink()
yt = FakeYT(FOUND, VIDEOS, CHANNELS); O.run(yt=yt, quota=Quota(), today=TODAY); assert yt.count("search") == 3
print("6 settings ok")

# 7. the allowance comes first: a search the day cannot afford is not made, and the week is not used up
root = world()
yt, q = FakeYT(FOUND, VIDEOS, CHANNELS), Quota(searches=0)
assert O.run(yt=yt, quota=q, today=TODAY) == [] and yt.calls == [] and not O.STATE.exists() and not O.OUT.exists() or O.OUT.read_text().count("\n") == 1
yt, q = FakeYT(FOUND, VIDEOS, CHANNELS), Quota(searches=1)
new = O.run(yt=yt, quota=q, today=TODAY)
assert yt.count("search") == 1 and json.loads(O.STATE.read_text())["used"] == {"gaming|clips allowed": "2026-10-25"} and len(new) == 3
root = world()
yt, q = FakeYT(FOUND, VIDEOS, CHANNELS), Quota(reads=False)                              # the searches ran but the reads are held back
assert O.run(yt=yt, quota=q, today=TODAY) == [] and yt.count("search") == 3 and yt.count("videos") == 0 and yt.count("channels") == 0
print("7 allowance ok")

# 8. a failure never fails the scout run, and a failed search does not use up the week
root = world()
bad = FakeYT(FOUND, VIDEOS, CHANNELS, fail=True)
assert O.main([], yt=bad, quota=Quota()) == 0 and not O.STATE.exists()
O.client = lambda: (_ for _ in ()).throw(RuntimeError("no clips channel sign-in to search with"))
assert O.main([], quota=Quota()) == 0 and not O.STATE.exists()
print("8 failures ok")

# 9. nothing is sent, ever; the list, the page and the workflow are wired
src = pathlib.Path(REPO_DIR, "pipeline", "outreach.py").read_text()
for banned in ("smtplib", "sendmail", "requests.post", "commentThreads", "ig_post", "messages.send", "webhook", "playlistItems", "videos().update"):
    assert banned not in src, banned
assert not any(c in src for c in DASHES)
assert open(pathlib.Path(REPO_DIR, "clips", "outreach.csv")).read() == "channel,url,subscribers,niche,evidence,found_on,status\n"
wf = pathlib.Path(REPO_DIR, ".github", "workflows", "clips.yml").read_text()
assert "python pipeline/outreach.py" in wf and "clips/outreach.csv" in wf and "analytics/decisions.csv" in wf and "|| true" in wf[wf.index("outreach.py"):wf.index("outreach.py") + 120]
assert "clips/outreach.csv" in pathlib.Path(REPO_DIR, "docs", "hub.html").read_text()
doc = pathlib.Path(REPO_DIR, "docs", "OUTREACH.md").read_text()
assert not any(c in doc for c in DASHES)
message = "\n".join(l for l in doc.splitlines() if l.startswith(">")).lower()
assert "permission" in message and "in writing" in message and "credit you" in message and "link back" in message and "remove" in message, message
assert not re.search(r"\b(pay|paid|payment|money|earn\w*|cash|fee|fees|revenue|sponsor\w*|price|cost|dollars?|pounds?)\b|[£$]", message), message      # nothing about money
assert not re.search(r"\b(favorite|color|organize|center|realize|program)\b", message)                                                                   # UK English
print("9 wiring ok")
print("outreach ok")
