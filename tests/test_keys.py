"""Offline test of the key health (pipeline/keys.py, 24 October): one row per sign-in or key in status/keys.json, built from
what the identity audit's own calls showed plus one cheap call per API key; a key that fails or ends within 14 days becomes
one needs-charlie issue (once, not every 3 hours), closed again when it works. HTTP and gh are stubbed, nothing is real."""
import pathlib as _p, sys, os, json, tempfile, datetime as dt, types
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(tempfile.mkdtemp(prefix="qp-keys-"))
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import keys as K
import identity as I

T = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc)
DAY = dt.timedelta(days=1)


class R:
    def __init__(self, code, data=None, text=""): self.status_code, self._d, self.text = code, data, text
    def json(self):
        if self._d is None: raise ValueError("no json")
        return self._d


def iso(t): return t.isoformat(timespec="minutes")


# 1. the probes: one cheap GET per API key, exactly the endpoints named
CALLS = []
def getter(answers):
    def get(url, headers=None):
        CALLS.append((url, dict(headers or {})))
        a = answers.get(next((k for k in answers if k in url), None), R(200, {}))
        if isinstance(a, Exception): raise a
        return a
    return get


ENV = {"GEMINI_API_KEY": "g-key", "GROQ_API_KEY": "q-key", "CEREBRAS_API_KEY": "c-key", "OPENROUTER_API_KEY": "o-key", "CF_API_TOKEN": "cf-key",
       "CF_ACCOUNT_ID": "a" * 32, "MISTRAL_API_KEY": "m-key", "SAMBANOVA_API_KEY": "s-key", "CLAUDE_CODE_OAUTH_TOKEN": "claude-key"}
p = K.probe("MISTRAL_API_KEY", ENV, getter({})); assert p["status"] == "ok" and CALLS[-1][0] == "https://api.mistral.ai/v1/models" and CALLS[-1][1] == {"Authorization": "Bearer m-key"}, (p, CALLS)
p = K.probe("SAMBANOVA_API_KEY", ENV, getter({})); assert p["status"] == "ok" and CALLS[-1][0] == "https://api.sambanova.ai/v1/models", p
p = K.probe("GEMINI_API_KEY", ENV, getter({})); assert p["status"] == "ok" and CALLS[-1][1] == {"x-goog-api-key": "g-key"}, CALLS[-1]
n = len(CALLS); p = K.probe("GROQ_API_KEY", {}, getter({})); assert p["status"] == "missing" and len(CALLS) == n, "a missing key makes no call"
p = K.probe("GROQ_API_KEY", {"GROQ_API_KEY": "  "}, getter({})); assert p["status"] == "missing"
for code, want in ((401, "failing"), (403, "failing"), (429, "unverified"), (500, "unverified"), (503, "unverified"), (404, "unverified")):
    assert K.probe("MISTRAL_API_KEY", ENV, getter({"mistral": R(code, {})}))["status"] == want, code
assert K.probe("MISTRAL_API_KEY", ENV, getter({"mistral": ConnectionError("down")}))["status"] == "unverified"       # the network says nothing about the key
assert K.probe("GEMINI_API_KEY", ENV, getter({"generativelanguage": R(400, {}, '{"error": {"details": [{"reason": "API_KEY_INVALID"}]}}')}))["status"] == "failing"
assert K.probe("GEMINI_API_KEY", ENV, getter({"generativelanguage": R(400, {}, "bad request")}))["status"] == "unverified"
o = K.probe("OPENROUTER_API_KEY", ENV, getter({"openrouter": R(200, {"data": {"expires_at": "2026-11-01T00:00:00Z"}})})); assert o["status"] == "ok" and o["ends"].day == 1, o
print("1 probes ok")

# 1b. Cloudflare: the token verify endpoint plus CF_ACCOUNT_ID set (and shaped like an account id)
cf_ok = R(200, {"success": True, "result": {"status": "active"}})
CALLS.clear(); p = K.probe("CF_API_TOKEN", ENV, getter({"tokens/verify": cf_ok}))
assert p["status"] == "ok" and CALLS[0][0] == "https://api.cloudflare.com/client/v4/user/tokens/verify" and len(CALLS) == 1, (p, CALLS)
# an account-owned token fails the user endpoint and passes the account's own
seq = [R(401, {"success": False, "result": None}), cf_ok]
CALLS.clear(); p = K.probe("CF_API_TOKEN", ENV, lambda url, headers=None: (CALLS.append(url), seq[len(CALLS) - 1])[1])
assert p["status"] == "ok" and CALLS[1].endswith(f"/accounts/{'a' * 32}/tokens/verify"), (p, CALLS)
assert K.probe("CF_API_TOKEN", {"CF_API_TOKEN": "x"}, getter({"tokens/verify": cf_ok}))["status"] == "failing"        # no CF_ACCOUNT_ID
assert "CF_ACCOUNT_ID" in K.probe("CF_API_TOKEN", {"CF_API_TOKEN": "x"}, getter({"tokens/verify": cf_ok}))["detail"]
assert K.probe("CF_API_TOKEN", dict(ENV, CF_ACCOUNT_ID="my account"), getter({"tokens/verify": cf_ok}))["status"] == "failing"      # not an account id
assert K.probe("CF_API_TOKEN", ENV, getter({"tokens/verify": R(200, {"success": True, "result": {"status": "disabled"}})}))["status"] == "failing"
assert K.probe("CF_API_TOKEN", ENV, getter({"tokens/verify": R(401, {"success": False})}))["status"] == "failing"
assert K.probe("CF_API_TOKEN", ENV, getter({"tokens/verify": R(500, {})}))["status"] == "unverified"
assert K.probe("CF_API_TOKEN", ENV, getter({"tokens/verify": TimeoutError("slow")}))["status"] == "unverified"
assert K.probe("CF_API_TOKEN", {}, getter({}))["status"] == "missing"
p = K.probe("CF_API_TOKEN", ENV, getter({"tokens/verify": R(200, {"success": True, "result": {"status": "active", "expires_on": "2026-11-05T00:00:00Z"}})})); assert p["ends"].day == 5, p
print("1b cloudflare ok")

# 2. a row's status from its end date: ending within 14 days is expiring; a passed end is failing only when the end is what
# keeps it alive (hard); a key that still answers with a stale recorded end stays ok
def row(status="ok", ends=None, hard=False, detail="works"): return K.make("X", "x", "g", status, detail, ["step"], ends, False, T, None, hard)
assert row(ends=T + 20 * DAY)["status"] == "ok" and row(ends=T + 20 * DAY)["expires"] == "2026-11-13"
assert row(ends=T + 14 * DAY - dt.timedelta(minutes=1))["status"] == "expiring" and row(ends=T + 15 * DAY)["status"] == "ok"
r = row(ends=T + 3 * DAY); assert r["status"] == "expiring" and "in 3 days" in r["detail"] and "works" in r["detail"], r
assert "within a day" in row(ends=T + dt.timedelta(hours=5))["detail"]
assert row(ends=T - DAY, hard=True)["status"] == "failing" and row(ends=T - DAY)["status"] == "ok" and "has passed" in row(ends=T - DAY)["detail"]
assert row(status="failing", ends=T + DAY)["status"] == "failing"                          # a failure is never softened by a date
assert K.when(0) is None and K.when("") is None and K.when(None) is None and K.when("nonsense") is None       # Meta's 0 is "never"
assert K.when(int(T.timestamp())) == T and K.when("2026-10-24T12:00:00Z") == T and K.when("2026-10-24T12:00") == T
assert K.nice(T + 3 * DAY, T) == "Tuesday 27 October" and K.nice(T + 365 * DAY, T).endswith("2027")
print("2 end dates ok")

# 3. rows from the audit's own facts (status/identity.json "key" under each check)
tokens = SCRATCH / "root" / "tokens"; tokens.mkdir(parents=True)
for n in ("youtube", "youtube_clips", "youtube_gaming", "youtube_irl", "instagram", "tiktok", "login_whop", "login_vyro"): (tokens / f"{n}.enc").write_bytes(b"x")
(SCRATCH / "root" / "status").mkdir(); (SCRATCH / "root" / "clips").mkdir()
K.ROOT = SCRATCH / "root"; K.OUT = K.ROOT / "status" / "keys.json"; K.IDENTITY = K.ROOT / "status" / "identity.json"


def chk(what, ok=True, found="", note="", key=None, **kw):
    c = {"what": what, "found": found, "ok": ok, "expected": "", "note": note}
    if key: c["key"] = key
    c.update(kw); return c


def yt(state, channel="", expires=None): return {"kind": "youtube", "state": state, "channel": channel, "saved": iso(T - 3 * DAY), "expires_at": expires}


def identity(*checks): return {"checked": iso(T - dt.timedelta(minutes=40)), "ok": True, "checks": list(checks)}


ID = identity(
    chk("youtube", key=yt("ok", "Quickplay Daily")),
    chk("youtube_clips", key=yt("ok", "Quickplay Clips", iso(T + 2 * DAY))),                     # Google's app in Testing: the sign-in ends in 2 days
    chk("youtube_gaming", found="expired sign-in", key=yt("expired")),
    chk("youtube_irl", ok=False, note="HttpError 403 forbidden", key=yt("error")),
    chk("instagram", key={"kind": "instagram", "state": "ok", "user": "quickplaydaily", "expires_at": iso(T + 50 * DAY)}),
    chk("IG_TOKEN", found="expired seed", key={"kind": "instagram", "state": "expired seed"}),
    chk("IG_CLIPS_TOKEN", key={"kind": "instagram", "state": "ok", "user": "quickplayclips", "expires_at": iso(T + 8 * DAY)}),
    chk("FB_PAGE_TOKEN", key={"kind": "facebook", "state": "ok", "page": "Quickplay Daily", "expires_at": 0, "data_access_expires_at": int((T + 9 * DAY).timestamp())}),
    chk("FB_CLIPS_PAGE_TOKEN", key={"kind": "facebook", "state": "ok", "page": "Quickplay Clips", "expires_at": 0, "data_access_expires_at": int((T + 80 * DAY).timestamp())}),
    chk("tiktok", key={"kind": "tiktok", "state": "ok", "refresh_ends": iso(T + 300 * DAY), "mode": "off"}),
    chk("login_whop", key={"kind": "login", "saved": iso(T - 20 * DAY), "count": 12, "session_ends": iso(T + 5 * DAY)}),
    chk("login_vyro", key={"kind": "login", "saved": iso(T - 4 * DAY), "count": 9, "session_ends": None}))
get = getter({"mistral": R(401, {}), "sambanova": R(500, {}), "openrouter": R(200, {"data": {}}), "tokens/verify": cf_ok})
CALLS.clear()
rows = K.build(ID, dict(ENV, IG_TOKEN="ig-seed"), {}, T, get, [], {})
by = {r["id"]: r for r in rows}
st = lambda i: by[i]["status"]
assert st("youtube") == "ok" and st("youtube_clips") == "expiring" and by["youtube_clips"]["expires"] == "2026-10-26" and "Testing" in by["youtube_clips"]["detail"]
assert "Publish app" in " ".join(by["youtube_clips"]["fix"]), "a Testing sign-in's steps start with publishing the Google app"
assert st("youtube_gaming") == "failing" and "invalid_grant" in by["youtube_gaming"]["detail"] and any("youtube-callback" in s for s in by["youtube_gaming"]["fix"])
assert st("youtube_irl") == "failing" and "403" in by["youtube_irl"]["detail"]
assert st("instagram") == "ok" and by["instagram"]["expires"] == "2026-12-13" and st("IG_TOKEN") == "ok" and "expected" in by["IG_TOKEN"]["detail"]
assert st("IG_CLIPS_TOKEN") == "expiring" and "in 8 days" in by["IG_CLIPS_TOKEN"]["detail"] and st("IG_GAMING_TOKEN") == "missing"
assert st("FB_PAGE_TOKEN") == "expiring" and by["FB_PAGE_TOKEN"]["expires"] == "2026-11-02" and "data access" in by["FB_PAGE_TOKEN"]["detail"]
assert st("FB_CLIPS_PAGE_TOKEN") == "ok" and by["FB_CLIPS_PAGE_TOKEN"]["expires"] == "2027-01-12" and st("FB_IRL_PAGE_TOKEN") == "missing"
assert st("tiktok") == "ok" and by["tiktok"]["expires"] == str((T + 300 * DAY).date())
assert st("login_whop") == "expiring" and st("login_vyro") == "ok"
assert st("GEMINI_API_KEY") == "ok" and st("GROQ_API_KEY") == "ok" and st("CF_API_TOKEN") == "ok" and st("MISTRAL_API_KEY") == "failing"
assert "SAMBANOVA_API_KEY" not in by, "a server error with no earlier row says nothing: no row yet"
assert st("OPENROUTER_API_KEY") == "ok" and st("CLAUDE_CODE_OAUTH_TOKEN") == "ok"
assert [r["group"] for r in rows] == sorted((r["group"] for r in rows), key=K.GROUPS.index), "grouped in the hub's order"
assert all(r["fix"] and r["checked"] and r["what"] for r in rows), [r["id"] for r in rows if not r["fix"]]
assert by["instagram"]["checked"] == iso(T - dt.timedelta(minutes=40)) and by["MISTRAL_API_KEY"]["checked"] == iso(T)       # the audit's time, our own time
calls_each = {u: sum(1 for c in CALLS if c[0] == u) for u in {c[0] for c in CALLS}}
assert all(v == 1 for v in calls_each.values()) and len(CALLS) == 7, calls_each         # one call per probed key, none for the audit's keys
text = json.dumps(rows)
assert not any(s in text for s in ("g-key", "q-key", "cf-key", "m-key", "ig-seed", "claude-key")), "no secret is ever written"
print("3 rows from the audit's facts ok")

# 3b. the IG_TOKEN secret is the very key in use (the audit checks one key once): one row says so, it is never a second problem
tw = identity(chk("instagram", key={"kind": "instagram", "state": "expired", "expires_at": None}, found="expired key"))
rows2 = {r["id"]: r for r in K.build(tw, dict(ENV, IG_TOKEN="same"), {}, T, get, [], {})}
assert rows2["instagram"]["status"] == "failing" and rows2["IG_TOKEN"]["status"] == "ok" and "listed above" in rows2["IG_TOKEN"]["detail"], rows2["IG_TOKEN"]
print("3b twin ok")

# 4. a call that could not be made leaves the row as it was
prev = {r["id"]: r for r in rows}
unv = identity(chk("youtube", found="not checked this time", unverified=True), chk("instagram", found="not checked this time", unverified=True))
rows3 = {r["id"]: r for r in K.build(unv, ENV, prev, T + DAY, getter({"mistral": R(503, {}), "tokens/verify": cf_ok}), [], {})}
assert rows3["youtube"]["status"] == "ok" and "not checked this time" in rows3["youtube"]["detail"] and rows3["youtube"]["checked"] == prev["youtube"]["checked"]
assert rows3["instagram"]["expires"] == prev["instagram"]["expires"]
assert rows3["MISTRAL_API_KEY"]["status"] == "failing" and "503" in rows3["MISTRAL_API_KEY"]["detail"], rows3["MISTRAL_API_KEY"]         # the last verdict stands
assert rows3["youtube"]["detail"].count("not checked this time") == 1
again = {r["id"]: r for r in K.build(unv, ENV, rows3, T + 2 * DAY, getter({"mistral": R(503, {})}), [], {})}
assert again["youtube"]["detail"].count("not checked this time") == 1, "the note is replaced, not stacked"
print("4 unverified keeps the last row ok")

# 5. the campaign-site logins: age and the last submission found in clips/submit.csv decide, not a guess
camps = {"speed-expedia": {"platform": "Content Rewards, YouTube"}, "vyro-x": {"platform": "Vyro (YouTube)"}}
uk = lambda t: K.uk(t).strftime("%Y-%m-%d %H:%M")
sub = [{"campaign": "speed-expedia", "submitted": uk(T - 2 * DAY), "public_at_uk": uk(T - 2 * DAY)},
       {"campaign": "vyro-x", "submitted": uk(T - DAY), "public_at_uk": uk(T - DAY)},
       {"campaign": "vyro-x", "submitted": "failed: Vyro's daily limit for this account (5 posts a day): tomorrow", "public_at_uk": uk(T)},
       {"campaign": "speed-expedia", "submitted": "pulled", "public_at_uk": uk(T)},
       {"campaign": "speed-expedia", "submitted": "", "public_at_uk": "private (test)"}]
seen = K.submissions(sub, camps)
assert abs((seen["Content Rewards"]["success"] - (T - 2 * DAY)).total_seconds()) < 61 and abs((seen["Vyro"]["success"] - (T - DAY)).total_seconds()) < 61, seen
assert "failure" not in seen["Vyro"] and "failure" not in seen["Content Rewards"], seen      # a daily limit or a pulled row says nothing about the login
lg = lambda **k: chk("login_whop", key=dict({"kind": "login", "saved": iso(T - 10 * DAY), "count": 7, "session_ends": None}, **k))
r = K.login_row("login_whop", lg(), lg()["key"], T, "c", seen); assert r["status"] == "ok" and "saved 10 days ago" in r["detail"] and "last submission" in r["detail"], r
bad = K.submissions([{"campaign": "speed-expedia", "submitted": "failed: login expired", "public_at_uk": uk(T - dt.timedelta(hours=2))}], camps)
r = K.login_row("login_whop", lg(), lg()["key"], T, "c", bad); assert r["status"] == "failing" and "login page" in r["detail"], r
r = K.login_row("login_whop", lg(), lg(saved=iso(T - dt.timedelta(hours=1)))["key"], T, "c", bad)
assert r["status"] == "ok", "a login saved again after the failure is a new login"
both = K.submissions(sub + [{"campaign": "speed-expedia", "submitted": "failed: login expired", "public_at_uk": uk(T - 5 * DAY)}], camps)
assert K.login_row("login_whop", lg(), lg()["key"], T, "c", both)["status"] == "ok", "a later submission that worked beats an older failure"
r = K.login_row("login_whop", lg(session_ends=iso(T - DAY)), lg(session_ends=iso(T - DAY))["key"], T, "c", {"Content Rewards": {}}); assert r["status"] == "failing" and "ended" in r["detail"], r
r = K.login_row("login_whop", lg(), lg(session_ends=iso(T - 3 * DAY))["key"], T, "c", seen); assert r["status"] == "ok", "a submission after the cookie's end: another cookie carries it"
r = K.login_row("login_whop", chk("login_whop", ok=False, note="cookies for other sites: the wrong export"), {"count": 3}, T, "c", seen); assert r["status"] == "failing" and "wrong export" in r["detail"]
print("5 logins ok")

# 6. Claude: the secret's presence only, and the writer's own last answer when Claude refused the token
K.ROOT.joinpath("status", "claude_usage.json").write_text(json.dumps({"last": "ok", "last_at": "2026-10-24T11:14+00:00"}))
assert K.claude_row(ENV, T)["status"] == "ok" and "no allowance is used" in K.claude_row(ENV, T)["detail"]
assert K.claude_row({}, T)["status"] == "missing" and not K.problem(K.claude_row({}, T)), "an optional last resort is not an alarm"
K.ROOT.joinpath("status", "claude_usage.json").write_text(json.dumps({"last": "Invalid API key · Please run /login", "last_at": "2026-10-24T11:14+00:00"}))
assert K.claude_row(ENV, T)["status"] == "failing"
K.ROOT.joinpath("status", "claude_usage.json").write_text(json.dumps({"last": "Claude AI usage limit reached", "last_at": "2026-10-24T11:14+00:00"}))
assert K.claude_row(ENV, T)["status"] == "ok", "a spent allowance is not a bad token"
print("6 claude ok")


# 7. issues: one needs-charlie issue per problem, once; closed when fixed; a key Charlie closed without fixing waits a week
class GH:
    def __init__(self): self.open, self.log, self.n = {}, [], 100
    def open_issues(self): return dict(self.open)
    def raise_issue(self, title, body, labels=None, howto=None):
        self.log.append(("raise", title, tuple(labels or ()), body))
        if title not in self.open: self.n += 1; self.open[title] = self.n
        return self.open[title]
    def close_issue(self, number, comment):
        self.log.append(("close", number)); self.open = {t: n for t, n in self.open.items() if n != number}


def table(*specs):
    return [K.make(i, f"thing {i}", "AI models", s, "d", ["fix it"], e, False, T) for i, s, e in specs]


A = GH()
now_rows = table(("a", "failing", None), ("b", "ok", None), ("c", "expiring", None))
notes = K.announce(now_rows, {}, T, A)
assert [x[1] for x in A.log if x[0] == "raise"] == ["🔑 Fix needed: thing a", "🔑 Fix needed: thing c"] and all(x[2] == ("needs-charlie",) for x in A.log), A.log
assert now_rows[0]["issue"] == 101 and now_rows[2]["issue"] == 102 and "issue" not in now_rows[1] and "fix it" in A.log[0][3] and "1. fix it" in A.log[0][3], now_rows
assert len(notes) == 2
# three hours later: nothing new while the issue stays open
A.log.clear(); prev = {r["id"]: r for r in now_rows}
again = table(("a", "failing", None), ("b", "ok", None), ("c", "expiring", None))
K.announce(again, prev, T + dt.timedelta(hours=3), A); assert not A.log, A.log
assert again[0]["issue"] == 101 and again[0]["said_at"] == prev["a"]["said_at"]
# a changed state (a failing key now ends sooner, or an expiring one fails) is news
chg = table(("a", "failing", None), ("c", "failing", None)); K.announce(chg, {r["id"]: r for r in again}, T + dt.timedelta(hours=6), A)
assert [x[0] for x in A.log] == ["raise"] and A.log[0][1].endswith("thing c") and A.n == 102, A.log          # commented on the open issue, no new one
# fixed: the issue closes itself
A.log.clear(); fixed = table(("a", "ok", None), ("c", "ok", None)); K.announce(fixed, {r["id"]: r for r in chg}, T + dt.timedelta(hours=9), A)
assert sorted(x[1] for x in A.log if x[0] == "close") == [101, 102] and not A.open, A.log
# Charlie closes an issue without fixing the key: quiet for a week, then asked again
A = GH(); r1 = table(("a", "failing", None)); K.announce(r1, {}, T, A); assert A.open
A.open.clear(); A.log.clear()          # closed in the app
r2 = table(("a", "failing", None)); K.announce(r2, {r["id"]: r for r in r1}, T + 2 * DAY, A); assert not A.log and "issue" not in r2[0], A.log
r3 = table(("a", "failing", None)); K.announce(r3, {r["id"]: r for r in r2}, T + 6 * DAY, A); assert not A.log, "still quiet on day 6"
r4 = table(("a", "failing", None)); K.announce(r4, {r["id"]: r for r in r3}, T + 8 * DAY, A); assert A.log and A.log[0][0] == "raise", "asked again after a week"
# a missing key matters only when it is needed
need = [K.make("g", "g", "AI models", "missing", "", [], None, True, T), K.make("o", "o", "AI models", "missing", "", [], None, False, T)]
A = GH(); K.announce(need, {}, T, A); assert [x[1] for x in A.log] == ["🔑 Fix needed: g"], A.log
# keys that already had an issue of their own keep its title; the older combined issues are closed
A = GH(); A.open = {"🔑 A sign-in has expired: reconnect it": 7, "🔑 An Instagram or Facebook key needs renewing": 8}
fb = [K.make("FB_PAGE_TOKEN", "Facebook Page key", "Facebook", "expiring", "d", [], None, False, T), K.make("login_vyro", "Vyro login", "Campaign sites", "failing", "d", [], None, False, T)]
K.announce(fb, {}, T, A)
assert [x[1] for x in A.log if x[0] == "raise"] == ["⚠️ The Facebook key needs renewing", "⚠️ Clips: the Vyro login has expired"], A.log
assert sorted(x[1] for x in A.log if x[0] == "close") == [7, 8], "the old combined issues are replaced"
# GitHub did not answer: nothing is recorded as said, so the next run tries again (and never waits a week on a failed call)
class Dead(GH):
    def raise_issue(self, title, body, labels=None, howto=None): self.log.append(("raise", title)); return None
A = Dead(); rr = table(("a", "failing", None)); K.announce(rr, {}, T, A); assert "said" not in rr[0] and "issue" not in rr[0], rr
rr2 = table(("a", "failing", None)); K.announce(rr2, {r["id"]: r for r in rr}, T + dt.timedelta(hours=3), A); assert len(A.log) == 2, A.log
print("7 issues ok")

# 8. the whole run: reads status/identity.json, writes status/keys.json (names, dates and states only), raises through gh
K.IDENTITY.write_text(json.dumps(ID))
(K.ROOT / "clips" / "campaigns.json").write_text(json.dumps({"campaigns": camps}))
import mac_rows
(K.ROOT / "clips" / "submit.csv").write_text("clip,campaign,campaign_url,platform,video,public_at_uk,title,hashtags,submitted,channel\n")
mac_rows.SUBMIT = K.ROOT / "clips" / "submit.csv"
A = GH()
K.log = lambda *a: None          # the table is long; the checks below read the file
res = K.run(dict(ENV, IG_TOKEN="ig-seed"), T, get, A)
saved = json.loads(K.OUT.read_text())
assert saved["checked"] == iso(T) and saved["counts"] == {s: sum(1 for r in saved["keys"] if r["status"] == s) for s in ("ok", "expiring", "failing", "missing")}, saved["counts"]
assert saved["counts"]["failing"] >= 3 and saved["counts"]["expiring"] >= 4 and len(saved["keys"]) == len(res["keys"])
issued = {x[1] for x in A.log if x[0] == "raise"}
assert "🔑 Fix needed: YouTube sign-in: Quickplay Gaming Clips" in issued or any("youtube_gaming" in json.dumps(r) for r in saved["keys"]), issued
assert all(r.get("issue") for r in saved["keys"] if K.problem(r)) and not any(r.get("issue") for r in saved["keys"] if not K.problem(r))
assert not any(s in K.OUT.read_text() for s in ("g-key", "q-key", "cf-key", "m-key", "ig-seed", "claude-key"))
# the next run (3 hours later, nothing changed) says nothing more
A.log.clear(); K.run(dict(ENV, IG_TOKEN="ig-seed"), T + dt.timedelta(hours=3), get, A); assert not A.log, A.log
print("8 whole run ok")

# 9. what the identity audit records under "key" (the contract with this file): YouTube, Instagram, Facebook, TikTok, the logins
import requests
I.ROOT = SCRATCH / "root"
soc = types.ModuleType("social"); soc.load = lambda name: {"refresh_token": "r", "scope": "s", "saved": "2026-10-20T10:00+00:00", "expires_at": "2026-10-27T10:00+00:00"}
sys.modules["social"] = soc
os.environ.setdefault("YT_CLIENT_ID", "x"); os.environ.setdefault("YT_CLIENT_SECRET", "y")
g1 = types.ModuleType("google.oauth2.credentials"); g1.Credentials = lambda *a, **k: object()
g2 = types.ModuleType("googleapiclient.discovery")
class _List:
    def __init__(self, items): self.items = items
    def channels(self): return self
    def list(self, **k): return self
    def execute(self): return {"items": self.items}
g2.build = lambda *a, **k: _List([{"id": "UC1", "snippet": {"title": "Quickplay Clips", "customUrl": "@quickplayclips"}}])
for name, mod in (("google", types.ModuleType("google")), ("google.oauth2", types.ModuleType("google.oauth2")), ("google.oauth2.credentials", g1),
                  ("googleapiclient", types.ModuleType("googleapiclient")), ("googleapiclient.discovery", g2)): sys.modules[name] = mod
for f in list((I.ROOT / "tokens").glob("*.enc")): f.unlink()
(I.ROOT / "tokens" / "youtube_clips.enc").write_bytes(b"x")
c = I.youtube_checks()[0]
assert c["ok"] and c["key"] == {"kind": "youtube", "state": "ok", "channel": "Quickplay Clips", "saved": "2026-10-20T10:00+00:00", "expires_at": "2026-10-27T10:00+00:00"}, c
g2.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("('invalid_grant: Token has been expired or revoked.')"))
I.EXPIRED_SIGNINS.clear(); c = I.youtube_checks()[0]; assert c["ok"] and c["key"]["state"] == "expired", c
g2.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HttpError 403 forbidden"))
c = I.youtube_checks()[0]; assert not c["ok"] and c["key"]["state"] == "error", c
soc.load = lambda name: {}
c = I.youtube_checks()[0]; assert c["key"]["state"] == "empty", c
# Instagram and Facebook: the end dates come from the answers already given
(I.ROOT / "tokens" / "youtube_clips.enc").unlink()
soc.load = lambda name: {"token": "stored", "user": "9", "saved": "2026-10-20T10:00+00:00", "expires_in": 5184000} if name == "instagram" else {}
I.META.clear(); I.META["FB_PAGE_TOKEN"] = {"expires_at": 0, "data_access_expires_at": int((T + 30 * DAY).timestamp())}
FBC = []
def _get(url, params=None, **k):
    FBC.append(url)
    if "graph.instagram.com" in url: return R(200, {"username": "quickplaydaily", "user_id": "9"})
    if "debug_token" in url: return R(200, {"data": {"expires_at": 0, "data_access_expires_at": int((T + 40 * DAY).timestamp())}})
    return R(200, {"name": "Quickplay Daily", "id": "1"})
R.ok = property(lambda self: 200 <= self.status_code < 300)
requests.get = _get
for k in list(os.environ):
    if k.startswith(("IG_", "FB_")): del os.environ[k]
os.environ.update(FB_PAGE_TOKEN="fb1", FB_PAGE_ID="1", FB_CLIPS_PAGE_TOKEN="fb2", FB_CLIPS_PAGE_ID="2")
cs = {c["what"]: c for c in I.meta_checks()}
assert cs["instagram"]["key"]["state"] == "ok" and cs["instagram"]["key"]["user"] == "quickplaydaily" and cs["instagram"]["key"]["expires_at"].startswith("2026-12-19"), cs["instagram"]
assert cs["FB_PAGE_TOKEN"]["key"]["data_access_expires_at"] == int((T + 30 * DAY).timestamp()), "the refresh's answer is reused"
assert cs["FB_CLIPS_PAGE_TOKEN"]["key"]["data_access_expires_at"] == int((T + 40 * DAY).timestamp()) and sum("debug_token" in u for u in FBC) == 1, FBC
for k in ("FB_PAGE_TOKEN", "FB_PAGE_ID", "FB_CLIPS_PAGE_TOKEN", "FB_CLIPS_PAGE_ID"): os.environ.pop(k, None)
# the saved logins: how many cookies, when saved, and the LATEST end among the site's own session-like cookies
txt = (".contentrewards.com\tTRUE\t/\tTRUE\t1790000000\tsession\tabc\n.contentrewards.com\tTRUE\t/\tTRUE\t1780000000\t__stripe_sid\tz\n"
       ".contentrewards.com\tTRUE\t/\tTRUE\t1760000000\t_ga\tz\n")
c = I.login_checks({"login_whop": txt})[0]
assert c["ok"] and c["key"]["count"] == 3 and c["key"]["saved"] is None, c
assert dt.datetime.fromisoformat(c["key"]["session_ends"]) == dt.datetime.fromtimestamp(1790000000, dt.timezone.utc).replace(second=0), c["key"]      # not _ga, not the 30-minute-style stripe cookie
assert I.login_checks({"login_vyro": "app.vyro.com\tFALSE\t/\tFALSE\t0\tvyro_sid\t1\n"})[0]["key"]["session_ends"] is None, "a browser-session cookie has no end"
print("9 audit facts ok")

# 10. the health line a session reads first names a failing or ending key, and a key check that stopped running
import contextlib, io, health as H
FAKE = {"checked": iso(H.NOW - dt.timedelta(hours=1)), "keys": [
    {"id": "MISTRAL_API_KEY", "what": "Mistral API key (writing)", "status": "failing", "expires": ""},
    {"id": "IG_CLIPS_TOKEN", "what": "Instagram key: Quickplay Clips", "status": "expiring", "expires": "2026-11-01"},
    {"id": "FB_PAGE_TOKEN", "what": "Facebook Page key", "status": "expiring", "expires": "2026-11-02"},
    {"id": "CEREBRAS_API_KEY", "what": "Cerebras API key", "status": "missing", "expires": "", "needed": False},
    {"id": "GEMINI_API_KEY", "what": "Gemini API key", "status": "ok", "expires": ""}]}
real_load = H.load
H.load = lambda p, default=None: FAKE if p == "status/keys.json" else real_load(p, default)
def health_line():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): H.main()
    return buf.getvalue()
out = health_line()
assert "key Mistral API key (writing) is failing" in out and "key Instagram key: Quickplay Clips is expiring (ends 2026-11-01)" in out, out
assert "Cerebras" not in out and "Gemini" not in out and "Facebook Page key" not in out, "an optional missing key, a working key and the Facebook line's own key are not repeated"
FAKE["checked"] = iso(H.NOW - dt.timedelta(hours=30)); assert "key check last ran 30 hours ago" in health_line()
H.load = real_load
print("10 health line ok")
print("keys ok")
