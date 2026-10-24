"""Offline test of pipeline/merge_driver.py (audit M3, 24 October): two workflows saving at once no longer lose each
other's keys. A real git repository with two writers runs each Save step's own commands (`git pull --rebase -X theirs`
with the driver set as the workflows set it): both sides' status keys, the Mac's submitted time and both hours' rows
survive; without the driver the same race loses a key (the bug)."""
import json, os, pathlib, shutil, subprocess, sys, tempfile
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
import merge_driver as M

# 1. the merge rules on their own
MISS = M.MISSING
assert M.merge3({"a": 1}, {"a": 1, "x": 2}, {"a": 1, "y": 3}) == {"a": 1, "x": 2, "y": 3}
assert M.merge3({"s": "rendered"}, {"s": "rendered"}, {"s": "scheduled"}) == {"s": "scheduled"}       # only this run changed it
assert M.merge3({"s": "a"}, {"s": "b"}, {"s": "c"}) == {"s": "c"}                                     # both: this run wins
assert M.merge3({"p": 1, "q": 1}, {"q": 1}, {"p": 1, "q": 1}) == {"q": 1}                             # deleted there only
assert M.merge3({"p": 1}, {"p": 2}, {}) == {"p": 2}                                                   # deleted here, changed there: kept
assert M.merge3({"ig": {"media": 1}}, {"ig": {"media": 1, "url": "u"}}, {"ig": {"media": 1, "at": "t"}}) == {"ig": {"media": 1, "url": "u", "at": "t"}}
assert M.submitted_rank("2026-10-24 19:12") > M.submitted_rank("pulled") > M.submitted_rank("expired: 31h old") > M.submitted_rank("")
assert M.merge_field("submitted", "", "2026-10-24 19:12", "expired: 31h old with 0 views") == "2026-10-24 19:12"
assert M.merge_field("submitted", "", "expired: x", "2026-10-24 19:12") == "2026-10-24 19:12"
assert M.kind("status/QD-161.json") == "json" and M.kind("status/social.json") is None
assert M.kind("clips/submit.csv") == "clips/submit.csv" and M.kind("analytics/shorts.csv") is None
print("rules ok")


# 2. two writers racing, as the workflows do
def sh(cwd, *a, check=True):
    r = subprocess.run(list(a), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode: raise AssertionError(f"{a}: {r.stdout} {r.stderr}")
    return r


def setup(tmp, files):
    remote = tmp / "remote.git"; sh(tmp, "git", "init", "-q", "--bare", "-b", "main", str(remote))
    seed = tmp / "seed"; sh(tmp, "git", "clone", "-q", str(remote), str(seed))
    for c in (seed,):
        sh(c, "git", "config", "user.name", "t"); sh(c, "git", "config", "user.email", "t@t")
    (seed / "pipeline").mkdir(); shutil.copy(REPO / "pipeline" / "merge_driver.py", seed / "pipeline" / "merge_driver.py")
    shutil.copy(REPO / ".gitattributes", seed / ".gitattributes")
    for rel, text in files.items():
        p = seed / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    sh(seed, "git", "add", "-A"); sh(seed, "git", "commit", "-q", "-m", "base"); sh(seed, "git", "push", "-q", "origin", "HEAD:main")
    clones = []
    for name in ("first", "second"):
        c = tmp / name; sh(tmp, "git", "clone", "-q", str(remote), str(c))
        sh(c, "git", "config", "user.name", name); sh(c, "git", "config", "user.email", f"{name}@t")
        clones.append(c)
    return remote, clones


def save(c, msg, driver=True):
    """The workflows' Save step: the driver line, then commit, rebase on main with -X theirs, push."""
    if driver: sh(c, "git", "config", "merge.qp.driver", "python3 pipeline/merge_driver.py %O %A %B %P")
    sh(c, "git", "add", "-A"); sh(c, "git", "commit", "-q", "-m", msg)
    r = sh(c, "git", "pull", "-q", "--rebase", "-X", "theirs", check=False)
    if r.returncode: sh(c, "git", "rebase", "--abort", check=False); raise AssertionError(r.stderr)
    sh(c, "git", "push", "-q", "origin", "HEAD:main")


def final(remote, tmp, rel):
    out = tmp / "check"; shutil.rmtree(out, ignore_errors=True); sh(tmp, "git", "clone", "-q", str(remote), str(out))
    return open(out / rel, encoding="utf-8", newline="").read()      # newline="": see the CRLF the files really hold


ST = "status/QD-200.json"
BASE_ST = json.dumps({"id": "QD-200", "state": "scheduled", "video": "abc"}, indent=1)
SUB = "clips/submit.csv"
HEAD = "clip,campaign,campaign_url,platform,video,public_at_uk,title,hashtags,submitted,channel\r\n"
ROW = lambda clip, sub="": f"{clip},kai,https://x,youtube,https://youtube.com/shorts/{clip},2026-10-23 19:00,t,#a,{sub},clips\r\n"
HOUR = "analytics/hourly.csv"
HH = "hour_utc,uk_day,yt_gained\r\n"

for with_driver in (True, False):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="qp-merge-"))
    remote, (social, engage) = setup(tmp, {ST: BASE_ST, SUB: HEAD + ROW("c1") + ROW("c2"), HOUR: HH + "2026-10-24T12:00Z,2026-10-24,5\r\n"})
    # social.py posts the Reel and records it; engage.py comments on the same Short, from the older main
    st = json.loads((social / ST).read_text()); st["instagram"] = {"media": "17", "url": "https://instagram.com/reel/1"}
    (social / ST).write_text(json.dumps(st, indent=1, ensure_ascii=False))
    # the Mac submits c1 on Vyro; GitHub's run marks c1 expired and adds c3 from the older main
    (social / SUB).write_text(HEAD + ROW("c1", "2026-10-24 19:12") + ROW("c2"))
    (social / HOUR).write_text(HH + "2026-10-24T12:00Z,2026-10-24,5\r\n2026-10-24T13:00Z,2026-10-24,7\r\n")
    save(social, "social", with_driver)
    st = json.loads((engage / ST).read_text()); st["engage"] = {"comment": "c-9", "playlist": True}; st["state"] = "public"
    (engage / ST).write_text(json.dumps(st, indent=1, ensure_ascii=False))
    (engage / SUB).write_text(HEAD + ROW("c1", "expired: 31h old with 0 views (a late row needs 500)") + ROW("c2") + ROW("c3"))
    (engage / HOUR).write_text(HH + "2026-10-24T12:00Z,2026-10-24,5\r\n2026-10-24T14:00Z,2026-10-24,9\r\n")
    save(engage, "engage", with_driver)
    got = json.loads(final(remote, tmp, ST)); sub = final(remote, tmp, SUB); hrs = final(remote, tmp, HOUR)
    if with_driver:
        assert got.get("instagram", {}).get("media") == "17" and got.get("engage", {}).get("comment") == "c-9", got
        assert got["state"] == "public" and got["video"] == "abc", got
        assert "c1,kai" in sub and "2026-10-24 19:12" in sub and "expired" not in sub and "c3,kai" in sub, sub
        assert sub.count("\r\n") == 4 and sub.startswith(HEAD), repr(sub)
        lines = hrs.strip().split("\r\n")
        assert lines == [HH.strip(), "2026-10-24T12:00Z,2026-10-24,5", "2026-10-24T13:00Z,2026-10-24,7", "2026-10-24T14:00Z,2026-10-24,9"], lines
        print("two writers with the driver: both keys, the Mac's submitted time and both hours survive")
    else:
        lost = "instagram" not in got or "2026-10-24 19:12" not in sub or "T13:00Z" not in hrs
        assert lost, "without the driver this race used to lose something; the test no longer shows the bug"
        print("two writers without the driver: a key or row is lost (the bug the driver fixes)")
    shutil.rmtree(tmp, ignore_errors=True)

# 3. a file the driver can't read falls back to git's line merge favouring this run, never a failed Save
tmp = pathlib.Path(tempfile.mkdtemp(prefix="qp-merge-"))
o, a, b = tmp / "o", tmp / "a", tmp / "b"
o.write_text('{\n "id": "QD-1"\n}'); a.write_text('{\n "id": "QD-1",\n "x": 1\n}'); b.write_text("not json\n")
assert M.main(str(o), str(a), str(b), "status/QD-1.json") == 0 and "not json" in a.read_text()
# every workflow that rebases with -X theirs sets the driver first
for wf in sorted((REPO / ".github" / "workflows").glob("*.yml")):
    t = wf.read_text()
    if "rebase -X theirs" in t:
        assert 'merge.qp.driver "python3 pipeline/merge_driver.py %O %A %B %P"' in t, f"{wf.name}: Save step without the merge driver"
        assert t.index("merge.qp.driver") < t.index("rebase -X theirs"), wf.name
shutil.rmtree(tmp, ignore_errors=True)
print("merge driver ok")
