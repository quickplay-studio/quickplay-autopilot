"""Offline test of the live action list (pipeline/actions.py, 24 October): status/actions.json items with a "check" are marked
done (or open again) by GitHub itself; items without one get a needs-charlie issue, once, and closing it marks the item done.
HTTP and gh are stubbed; the real alerts.py helpers run against a fake gh."""
import pathlib as _p, sys, os, json, tempfile, datetime as dt, shutil, re, subprocess
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(tempfile.mkdtemp(prefix="qp-actions-"))
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import actions as AC
import keys as K
import alerts as AL
import mac_rows as M

NOW = dt.datetime(2026, 10, 24, 20, 20, tzinfo=dt.timezone.utc)          # 21:20 UK (BST until 25 October)
DAY = dt.timedelta(days=1)


class R:
    def __init__(self, code, data=None): self.status_code, self._d, self.text = code, data, ""
    def json(self):
        if self._d is None: raise ValueError("no json")
        return self._d


def getter(answers):
    calls = []
    def get(url, headers=None):
        calls.append(url)
        a = answers.get(next((k for k in answers if k in url), None), R(200, {}))
        if isinstance(a, Exception): raise a
        return a
    get.calls = calls
    return get


class Stub:
    """alerts.py as actions.py sees it: the open needs-charlie issues, issue states, gh api."""
    def __init__(self, scan=(), states=None, pages=None):
        self.scan = None if scan is None else [dict(i) for i in scan]
        self.states, self.log, self.n, self.pages = dict(states or {}), [], 40, pages
    def issues_with(self, label): assert label == "needs-charlie"; return None if self.scan is None else [dict(i) for i in self.scan]
    def issue_info(self, n): return self.states.get(n)
    def raise_issue(self, title, body, labels=None, howto=None):
        full = body + (("\n\n" + howto) if howto else "")          # what alerts.raise_issue puts in the issue
        self.n += 1; self.log.append(("raise", title, tuple(labels or ()), full)); self.scan = (self.scan or []) + [{"number": self.n, "title": title, "body": full}]
        return self.n
    def close_issue(self, n, comment):
        self.log.append(("close", n)); self.scan = [i for i in (self.scan or []) if i["number"] != n]
    def gh(self, *a):
        self.log.append(("gh",) + a)
        out = self.pages if self.pages is not None else json.dumps({"build_type": "workflow", "source": {"branch": "main", "path": "/docs"}})
        return type("P", (), {"stdout": out, "stderr": "", "returncode": 0 if out else 1})()


def item(id, **kw):
    d = {"id": id, "title": f"Do {id}", "why": "because", "steps": ["one", "two"], "links": [{"label": "L", "url": "https://x.example/"}], "added": "2026-10-24", "due": "", "done": False}
    d.update(kw); return d


def ctx(env=None, get=None, A=None, rows=(), cfg=None):
    from types import SimpleNamespace
    return SimpleNamespace(now=NOW, env=env or {}, get=get or getter({}), A=A or Stub(), rows=list(rows), cfg=cfg or {})


# 1. secret_works: one cheap call, exactly the endpoints named; a missing secret is "not yet", a refusal is a failure, an outage is unknown
c = ctx({"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s", "CF_API_TOKEN": "c", "CF_ACCOUNT_ID": "a" * 32}, getter({}))
res, note, _ = AC.run_check("secret_works:MISTRAL_API_KEY", c); assert res is True and c.get.calls == ["https://api.mistral.ai/v1/models"], (res, c.get.calls)
res, note, _ = AC.run_check("secret_works:SAMBANOVA_API_KEY", c); assert res is True and c.get.calls[-1] == "https://api.sambanova.ai/v1/models"
res, note, _ = AC.run_check("secret_works:CF_API_TOKEN", ctx(c.env, getter({"tokens/verify": R(200, {"success": True, "result": {"status": "active"}})})))
assert res is True and "CF_ACCOUNT_ID" in note, note
res, note, _ = AC.run_check("secret_works:CF_API_TOKEN", ctx({"CF_API_TOKEN": "c"}, getter({"tokens/verify": R(200, {"success": True, "result": {"status": "active"}})})))
assert res is False and "CF_ACCOUNT_ID" in note, (res, note)
res, note, _ = AC.run_check("secret_works:MISTRAL_API_KEY", ctx({}, getter({}))); assert res is False and "not set yet" in note, note
res, note, _ = AC.run_check("secret_works:MISTRAL_API_KEY", ctx(c.env, getter({"mistral": R(401, {})}))); assert res is False and "401" in note
res, note, _ = AC.run_check("secret_works:MISTRAL_API_KEY", ctx(c.env, getter({"mistral": R(503, {})}))); assert res is None
res, note, _ = AC.run_check("secret_works:MISTRAL_API_KEY", ctx(c.env, getter({"mistral": ConnectionError("down")}))); assert res is None
assert AC.run_check("secret_works:NOPE", c)[0] is None and AC.run_check("nonsense", c)[0] is None and AC.run_check("secret_works", c)[0] is None
print("1 secret_works ok")

# 2. pages_workflow: the Pages API says how the site builds
st = Stub(pages=json.dumps({"build_type": "workflow"})); assert AC.run_check("pages_workflow", ctx(A=st))[0] is True and st.log[0] == ("gh", "api", "repos/quickplay-studio/quickplay-autopilot/pages")
st = Stub(pages=json.dumps({"build_type": "legacy", "source": {"branch": "main", "path": "/docs"}})); res, note, _ = AC.run_check("pages_workflow", ctx(A=st)); assert res is False and "branch" in note, note
assert AC.run_check("pages_workflow", ctx(A=Stub(pages="")))[0] is None                # gh failed: unknown, nothing changes
assert AC.run_check("pages_workflow", ctx(A=Stub(pages="not json")))[0] is None
assert AC.run_check("pages_workflow", ctx(A=Stub(pages=json.dumps({"message": "Not Found"}))))[0] is None
print("2 pages_workflow ok")

# 3. vyro_today: done for the day once today's Vyro rows carry a submitted time (5 a day per account), open while one waits
cfg = {"campaigns": {"v1": {"platform": "Vyro (YouTube)"}, "cr": {"platform": "Content Rewards"}}, "submit_daily_limits": {"Vyro": 5}}
def vrow(clip, sub="", at="2026-10-24 19:00", ch="gaming", camp="v1", platform="youtube"):
    return {"clip": clip, "campaign": camp, "platform": platform, "video": "https://youtube.com/shorts/" + clip, "public_at_uk": at, "submitted": sub, "channel": ch}
vt = lambda *rows: AC.run_check("vyro_today", ctx(rows=rows, cfg=cfg))
assert vt()[0] is None and vt(vrow("a", at="2026-10-23 19:00"))[0] is None, "nothing due today: nothing to judge"
res, note, _ = vt(vrow("a"), vrow("b")); assert res is False and "2 Vyro clips still wait" in note and "Saturday 24 October" in note, note
res, note, when = vt(vrow("a", "2026-10-24 19:12"), vrow("b", "2026-10-24 19:09")); assert res is True and "2 Vyro clips submitted" in note and "19:12 UK" in note, note
assert when == dt.datetime(2026, 10, 24, 18, 12, tzinfo=dt.timezone.utc), when
assert vt(vrow("a", "2026-10-24 19:12"), vrow("b", ""))[0] is False
assert vt(vrow("a", "2026-10-24 19:12"), vrow("b", "pulled"), vrow("c", "expired: 31h old"), vrow("d", "failed: past the 30-minute window: x"))[0] is True, "dead rows need nothing"
assert vt(vrow("a", "2026-10-24 19:12"), vrow("b", "failed: no Submit button"))[0] is False, "a failure that will be retried still waits"
assert vt(vrow("a", ""), vrow("x", "", camp="cr"), vrow("y", "", platform="instagram"))[0] is False
assert vt(vrow("x", "", camp="cr"), vrow("y", "", platform="instagram"))[0] is None, "other campaigns and Reels are not the Mac's"
five = [vrow(f"s{i}", "2026-10-24 19:1%d" % i) for i in range(5)] + [vrow("over1", "failed: Vyro's daily limit for this account (5 posts a day): tomorrow"), vrow("over2")]
assert vt(*five)[0] is True, "the sixth and seventh cannot go today: the day is done"
assert vt(*five[:4], vrow("over2"))[0] is False
other = five + [vrow("z", "", ch="irl")]; assert vt(*other)[0] is False, "each account has its own five"
print("3 vyro_today ok")

# 4. a check's answer moves the item: done when it passes, open again when it stops, nothing when unknown
it = item("k", check="secret_works:X")
p = AC.by_check(it, True, "works", None, NOW); assert p == {"note": "works", "done": True, "done_at": "2026-10-24T20:20+00:00", "done_by": "check"}, p
p = AC.by_check(it, True, "works", dt.datetime(2026, 10, 24, 18, 12, tzinfo=dt.timezone.utc), NOW); assert p["done_at"] == "2026-10-24T18:12+00:00"
done = dict(it, done=True, done_at="2026-10-24T18:12+00:00", done_by="check", note="works")
assert AC.by_check(done, True, "works", None, NOW) == {}, "nothing to change, nothing to write"
p = AC.by_check(done, False, "not set yet", None, NOW); assert p["done"] is False and p["done_at"] is AC.DEL and p["done_by"] is AC.DEL and p["note"] == "not set yet", p
assert AC.by_check(done, None, "HTTP 503", None, NOW) == {}, "an unknown answer changes nothing"
assert AC.by_check(it, None, "HTTP 503", None, NOW) == {}
assert AC.by_check(it, False, "not set yet", None, NOW) == {"note": "not set yet"}
by_hand = dict(it, done=True, done_at="2026-10-24", done_by="Charlie")
assert AC.by_check(by_hand, True, "ok", None, NOW) == {"note": "ok", "done_by": "check"}, "done by hand, then proven"
assert AC.by_check(by_hand, False, "branch", None, NOW)["done"] is False, "a check that fails reopens even a hand-marked item"
print("4 transitions ok")

# 5. issues: one per item without a check, once; closing it marks the item done; reopening opens it; a lost link is found again
A = Stub(scan=[]); budget = [5]
cx = ctx(A=A)
it = item("fb", title="Check the Facebook Page", due="2026-10-27", repeat="")
patch, notes = AC.by_issue(it, A.scan, cx, budget)
assert patch == {"issue": 41} and A.log[0][0] == "raise" and A.log[0][1] == "Check the Facebook Page" and A.log[0][2] == ("needs-charlie",), (patch, A.log)
body = A.log[0][3]; assert "because" in body and "1. one" in body and "2. two" in body and "L: https://x.example/" in body and "<!-- qp-action:fb -->" in body and "Tuesday 27 October" in body, body
assert "Close this issue when it is done" in body and budget == [4]
it.update(patch)
patch, notes = AC.by_issue(it, A.scan, cx, budget); assert patch == {} and len(A.log) == 1, "open issue: nothing more to do"
# Charlie closes it in the app
A.scan = []; A.states[41] = {"state": "CLOSED", "closed_at": "2026-10-25T09:30:00Z", "reason": "COMPLETED", "url": "u"}
patch, notes = AC.by_issue(it, A.scan, cx, budget)
assert patch == {"done": True, "done_at": "2026-10-25T09:30+00:00", "done_by": "issue"}, patch
A.states[41]["reason"] = "NOT_PLANNED"; patch, _ = AC.by_issue(it, A.scan, cx, budget); assert patch["done_by"] == "issue (closed as not planned)", patch
A.states[41] = None; assert AC.by_issue(it, A.scan, cx, budget)[0] == {}, "GitHub cannot say: nothing changes"
# he reopens it: the item opens again
it2 = dict(it, done=True, done_at="2026-10-25T09:30+00:00", done_by="issue")
A.scan = [{"number": 41, "title": "x", "body": "<!-- qp-action:fb -->"}]
patch, notes = AC.by_issue(it2, A.scan, cx, budget); assert patch == AC.reopen() and "reopened" in notes[0], (patch, notes)
# a lost link is found by the marker, never made twice
lost = item("fb", title="Check the Facebook Page"); A.log.clear()
patch, notes = AC.by_issue(lost, A.scan, cx, [5]); assert patch == {"issue": 41} and not A.log, (patch, A.log)
# done by hand or by a check: its open issue is closed
byhand = item("fb", done=True, done_by="Charlie", issue=41); A.log.clear()
patch, notes = AC.by_issue(byhand, A.scan, cx, [5]); assert patch == {} and A.log == [("close", 41)], A.log
# GitHub could not be read: nothing is made or closed
A2 = Stub(scan=None); assert AC.by_issue(item("z"), A2.scan, ctx(A=A2), [5]) == ({}, []) and not A2.log
# the run may not flood: at most 5 new issues
A3 = Stub(scan=[]); bud = [2]
for i in range(4): AC.by_issue(item(f"i{i}"), A3.scan, ctx(A=A3), bud)
assert sum(1 for x in A3.log if x[0] == "raise") == 2
print("5 issues ok")

AC.log = lambda *a: None          # the run logs every step; the checks below read the file and the stub
# 6. the whole run on a copy of the real list: checks move items, issues are made once, the file is written only when it changed
work = SCRATCH / "actions.json"; shutil.copy(REPO_DIR + "/status/actions.json", work)
real = json.loads(work.read_text()); ids = [a["id"] for a in real]
# the live file carries what the audit runs have done (issue numbers, done marks): the test starts from the items as written
for a in real:
    for k in ("issue", "done_at", "done_by", "note"): a.pop(k, None)
    a["done"] = False
work.write_text(json.dumps(real, indent=1, ensure_ascii=False) + "\n")
assert {"facebook-status", "tiktok-status", "mac-vyro", "cloudflare-key", "mistral-key", "sambanova-key", "pages-from-actions"} <= set(ids), ids
checks_in_file = {a["id"]: a["check"] for a in real if a.get("check")}
assert {"mac-vyro": "vyro_today", "cloudflare-key": "secret_works:CF_API_TOKEN", "mistral-key": "secret_works:MISTRAL_API_KEY",
        "sambanova-key": "secret_works:SAMBANOVA_API_KEY", "pages-from-actions": "pages_workflow"}.items() <= checks_in_file.items(), checks_in_file
assert all(c.startswith(("secret_works:", "vyro_today", "pages_workflow")) for c in checks_in_file.values())
# a Facebook Page key item is checked from the key health rows (keys.py), not a probe of its own
import types as _ty
_ctx = _ty.SimpleNamespace(env={}, get=None, keys=[{"id": "FB_CLIPS_PAGE_TOKEN", "status": "missing", "detail": "FB_CLIPS_PAGE_TOKEN is not set"}])
assert AC.secret_works("FB_CLIPS_PAGE_TOKEN", _ctx)[0] is False
_ctx.keys[0].update(status="ok", detail="the Page accepts the key"); assert AC.secret_works("FB_CLIPS_PAGE_TOKEN", _ctx)[0] is True
A = Stub(scan=[])
get = getter({"mistral": R(200, {}), "sambanova": R(401, {})})
vrows = [vrow("a"), vrow("b")]
r = AC.run(NOW, {"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s"}, get, A, work, True, vrows, cfg)
after = {a["id"]: a for a in json.loads(work.read_text())}
assert after["mistral-key"]["done"] is True and after["mistral-key"]["done_by"] == "check" and after["mistral-key"]["done_at"] == "2026-10-24T20:20+00:00", after["mistral-key"]
assert after["sambanova-key"]["done"] is False and "401" in after["sambanova-key"]["note"], after["sambanova-key"]
assert after["cloudflare-key"]["done"] is False and "not set yet" in after["cloudflare-key"]["note"]
assert after["pages-from-actions"]["done"] is True and after["pages-from-actions"]["done_by"] == "check" and str(after["pages-from-actions"]["done_at"]).startswith("2026-10-24"), after["pages-from-actions"]
assert after["mac-vyro"]["done"] is False and "2 Vyro clips still wait" in after["mac-vyro"]["note"]
made = {x[1]: after[i].get("issue") for x in A.log if x[0] == "raise" for i in ids if after[i]["title"] == x[1]}
assert sorted(made) == sorted(a["title"] for a in real if not a.get("check")) and all(made.values()), made          # one issue per item without a check
assert all(after[i].get("issue") for i in ("facebook-status", "tiktok-status", "instagram-key")) and not any(after[i].get("issue") for i in checks_in_file)
assert r["wrote"] and len([x for x in A.log if x[0] == "raise"]) == len([a for a in real if not a.get("check")]) <= AC.MAX_NEW     # one each (the channel items of 25 October included)
# an hour later (still the 24th in the UK): nothing changed, so nothing is written or made
before = work.read_text(); n = len(A.log)
r = AC.run(NOW + dt.timedelta(hours=1), {"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s"}, get, A, work, True, vrows, cfg)
assert not r["wrote"] and work.read_text() == before and not [x for x in A.log[n:] if x[0] in ("raise", "close")], A.log[n:]
# Charlie pastes the right SambaNova key and the Mac submits: done by GitHub, no chat needed
get2 = getter({"mistral": R(200, {}), "sambanova": R(200, {})})
vdone = [vrow("a", "2026-10-24 19:12"), vrow("b", "2026-10-24 19:09")]
r = AC.run(NOW + dt.timedelta(hours=2), {"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s"}, get2, A, work, True, vdone, cfg)
after = {a["id"]: a for a in json.loads(work.read_text())}
assert after["sambanova-key"]["done"] is True and after["mac-vyro"]["done"] is True and after["mac-vyro"]["done_at"] == "2026-10-24T18:12+00:00", after["mac-vyro"]
# he closes the Facebook issue in the app: the item is done; the list says so on the next run
fb = after["facebook-status"]["issue"]; A.scan = [i for i in A.scan if i["number"] != fb]; A.states[fb] = {"state": "CLOSED", "closed_at": "2026-10-25T08:00:00Z", "reason": "COMPLETED", "url": "u"}
AC.run(NOW + DAY, {"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s"}, get2, A, work, True, vdone, cfg)
after = {a["id"]: a for a in json.loads(work.read_text())}
assert after["facebook-status"]["done"] is True and after["facebook-status"]["done_by"] == "issue" and after["facebook-status"]["done_at"].startswith("2026-10-25T08:00"), after["facebook-status"]
# a check that stops passing opens its item again (the key is revoked)
AC.run(NOW + 2 * DAY, {"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s"}, getter({"mistral": R(401, {}), "sambanova": R(200, {})}), A, work, True, vdone, cfg)
after = {a["id"]: a for a in json.loads(work.read_text())}
assert after["mistral-key"]["done"] is False and "done_at" not in after["mistral-key"] and "done_by" not in after["mistral-key"], after["mistral-key"]
# the next day the Vyro rows are new and unsubmitted: the daily item opens again
AC.run(NOW + DAY + dt.timedelta(hours=-8), {"MISTRAL_API_KEY": "m", "SAMBANOVA_API_KEY": "s"}, get2, A, work, True, [vrow("n1", at="2026-10-25 19:00")], cfg)
after = {a["id"]: a for a in json.loads(work.read_text())}
assert after["mac-vyro"]["done"] is False and "done_at" not in after["mac-vyro"], after["mac-vyro"]
print("6 whole run ok")

# 7. the file stays a list the hub reads: required fields, dates, no en or em dashes, ids unique; written the way it was
text = work.read_text(); assert text.endswith("\n") and text == json.dumps(json.loads(text), indent=1, ensure_ascii=False) + "\n"
for a in json.loads(text):
    assert {"id", "title", "why", "steps", "links", "added", "due", "done"} <= set(a), a.get("id")
    assert not any(chr(c) in json.dumps(a, ensure_ascii=False) for c in (0x2013, 0x2014)), a["id"]
assert not any(chr(c) in "".join(x[3] for x in A.log if x[0] == "raise") for c in (0x2013, 0x2014))
# an edit made while the checks ran survives: only the patched fields change, by id
cur = json.loads(work.read_text()); cur.append(item("added-meanwhile")); cur[0]["why"] = "edited meanwhile"; work.write_text(json.dumps(cur, indent=1, ensure_ascii=False) + "\n")
assert AC.save(work, {cur[1]["id"]: {"note": "n"}}) is True
now_ = json.loads(work.read_text()); assert now_[-1]["id"] == "added-meanwhile" and now_[0]["why"] == "edited meanwhile" and now_[1]["note"] == "n"
assert AC.save(work, {"gone": {"note": "n"}}) is False and AC.save(SCRATCH / "missing.json", {}) is False
print("7 file ok")

# 8. orphans: an issue this script made for an item that is gone is closed; a hand-made issue is left alone
A = Stub(scan=[{"number": 5, "title": "t", "body": "x <!-- qp-action:old-thing -->"}, {"number": 6, "title": "mine", "body": "no marker"}, {"number": 7, "title": "t2", "body": "<!-- qp-action:fb -->"}])
AC.orphans([item("fb")], A.scan, A); assert A.log == [("close", 5)], A.log
print("8 orphans ok")

# 9. the real alerts.py helpers against a fake gh: the plumbing the script stands on
class FakeGH:
    def __init__(self): self.calls, self.issues = [], {}
    def __call__(self, *a):
        self.calls.append(a); out, rc = "", 0
        if a[:2] == ("issue", "create"):
            n = len(self.issues) + 1; title = a[a.index("--title") + 1]; body = a[a.index("--body") + 1]
            self.issues[n] = {"number": n, "title": title, "body": body, "state": "OPEN", "labels": [a[i + 1] for i, x in enumerate(a) if x == "--label"]}
            out = f"https://github.com/quickplay-studio/quickplay-autopilot/issues/{n}\n"
        elif a[:2] == ("issue", "list"):
            lab = a[a.index("--label") + 1]
            out = json.dumps([{k: i[k] for k in ("number", "title", "body")} for i in self.issues.values() if i["state"] == "OPEN" and lab in i["labels"]])
        elif a[:2] == ("issue", "view"):
            i = self.issues.get(int(a[2]))
            if i: out = json.dumps({"state": i["state"], "closedAt": "2026-10-25T09:30:00Z" if i["state"] == "CLOSED" else None, "stateReason": "COMPLETED" if i["state"] == "CLOSED" else "", "url": "u"})
            else: rc = 1
        elif a[:2] == ("issue", "close"): self.issues[int(a[2])]["state"] = "CLOSED"
        elif a[:2] == ("api", "repos/quickplay-studio/quickplay-autopilot/pages"): out = json.dumps({"build_type": "workflow"})
        return type("P", (), {"stdout": out, "stderr": "", "returncode": rc})()
import contextlib, io
quiet = contextlib.redirect_stdout(io.StringIO()); quiet.__enter__()          # alerts.py prints "opened: ..." for each issue
fake = FakeGH(); AL.gh = fake
AL.open_issues = lambda: {i["title"]: i["number"] for i in fake.issues.values() if i["state"] == "OPEN" and "alert" in i["labels"]}
work2 = SCRATCH / "actions2.json"; work2.write_text(json.dumps([item("a1", title="Do the first thing"), item("a2", title="Pages", check="pages_workflow"), item("a3", title="Do the third thing")], indent=1, ensure_ascii=False) + "\n")
r = AC.run(NOW, {}, getter({}), AL, work2, True, [], {})
got = {a["id"]: a for a in json.loads(work2.read_text())}
assert got["a1"]["issue"] == 1 and got["a3"]["issue"] == 2 and "issue" not in got["a2"] and got["a2"]["done"] is True and got["a2"]["done_by"] == "check", got
assert fake.issues[1]["labels"] == ["alert", "needs-charlie"] and "<!-- qp-action:a1 -->" in fake.issues[1]["body"], fake.issues[1]
fake.issues[1]["state"] = "CLOSED"                                                       # Charlie closes the first in the app
AC.run(NOW + DAY, {}, getter({}), AL, work2, True, [], {})
got = {a["id"]: a for a in json.loads(work2.read_text())}
assert got["a1"]["done"] is True and got["a1"]["done_by"] == "issue" and got["a1"]["done_at"] == "2026-10-25T09:30+00:00" and fake.issues[2]["state"] == "OPEN", got["a1"]
fake.issues[1]["state"] = "OPEN"                                                         # and reopens it
AC.run(NOW + 2 * DAY, {}, getter({}), AL, work2, True, [], {})
got = {a["id"]: a for a in json.loads(work2.read_text())}
assert got["a1"]["done"] is False and "done_by" not in got["a1"], got["a1"]
quiet.__exit__(None, None, None)
assert sum(1 for a in fake.calls if a[:2] == ("issue", "create")) == 2, "two issues made in three runs"
print("9 alerts helpers ok")

# 10. the workflow that runs it: both scripts, the secrets they read, the schedule, the issue triggers, the files saved
wf = (_p.Path(REPO_DIR) / ".github" / "workflows" / "audit.yml").read_text()
runs = [re.search(r"run: python pipeline/(\w+)\.py", wf[m:]).group(1) for m in [wf.index("run: python pipeline/identity.py"), wf.index("run: python pipeline/keys.py"), wf.index("run: python pipeline/actions.py")]]
assert runs == ["identity", "keys", "actions"], "the audit first (keys reuses its calls), the action list last"
for name in list(K.PROBES) + ["CLAUDE_CODE_OAUTH_TOKEN", "CF_ACCOUNT_ID"]:
    assert f"secrets.{name}" in wf, f"audit.yml must pass {name} to the key check"
for check_ in checks_in_file.values():
    if check_.startswith("secret_works:"): assert check_.split(":")[1] in K.PROBES or check_.split(":")[1] in K.FB
save_step = wf[wf.index("name: Save"):]
assert "status/keys.json" in save_step and "status/actions.json" in save_step and "status/identity.json" in save_step, "the Save step commits the new files"
assert "cron: '20 */3 * * *'" in wf and "*/6" not in wf, "every 3 hours"
assert re.search(r"issues:\s*\n\s*types:\s*\[closed, reopened\]", wf) and "needs-charlie" in wf, "closing or reopening one of Charlie's issues runs it"
assert re.search(r"^\s*pages:\s*read", wf, re.M), "the Pages API needs pages: read"
assert "pip==26.2.1" in wf and "--uploaded-prior-to P7D" in wf, "the supply-chain rule stays"
for f in ("keys.py", "actions.py"):
    assert (_p.Path(REPO_DIR) / "pipeline" / f).read_text().count('labels=["needs-charlie"]') == 0, "label by constant: test_alert_labels counts the literal in its three files"
print("10 workflow ok")
print("actions ok")
