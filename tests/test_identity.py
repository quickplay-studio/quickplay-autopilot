"""Offline test of the identity guard (pipeline/identity.py): the Quickplay name rule, the cookie-domain rule for the saved
campaign-site sign-ins, the secrets allowlist over workflow files, the tokens/ file rule, and the gate."""
import pathlib as _p, sys as _s, tempfile as _t, json, os
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
os.chdir(REPO_DIR); sys = _s; sys.path.insert(0, REPO_DIR + "/pipeline")
import identity as I

# 1. the name rule
assert I.studio_name("Quickplay Daily") and I.studio_name("quickplaydaily") and I.studio_name("Quickplay Gaming Clips") and I.studio_name("@QuickplayClips-x9b".lstrip("@"))
assert not I.studio_name("Charlie Page") and not I.studio_name("") and not I.studio_name("My Quickplay")
print("1 name rule ok")

# 2. saved sign-ins: own-site cookies pass, another site's cookies fail, an empty export fails
good = ".contentrewards.com\tTRUE\t/\tTRUE\t1790000000\tsession\tabc\n#HttpOnly_.whop.com\tTRUE\t/\tTRUE\t0\twhop_sid\txyz\n"
bad = good + ".google.com\tTRUE\t/\tTRUE\t1790000000\tSID\tzzz\n"
r = I.login_checks({"login_whop": good, "login_vyro": "app.vyro.com\tFALSE\t/\tFALSE\t1790000000\tvyro_sid\t123\n"})
assert all(c["ok"] for c in r), r
r = I.login_checks({"login_whop": bad}); assert not r[0]["ok"] and "google.com" in r[0]["found"], r
r = I.login_checks({"login_vyro": ""}); assert not r[0]["ok"], r
print("2 cookie domains ok")

# 3. secrets: the repository's own workflows are clean; a workflow with an unlisted secret or a full dump fails
r = I.secret_checks(); assert r and all(c["ok"] for c in r), [c for c in r if not c["ok"]]
wd = SCRATCH / "wf"; wd.mkdir()
(wd / "x.yml").write_text("env:\n  A: ${{ secrets.SOCIAL_KEY }}\n  B: ${{ secrets.PERSONAL_GMAIL_PASSWORD }}\n")
(wd / "y.yml").write_text("env:\n  ALL: ${{ toJSON(secrets) }}\n")
r = I.secret_checks(wd); assert not r[0]["ok"] and "PERSONAL_GMAIL_PASSWORD" in r[0]["note"] and not r[1]["ok"] and "every secret" in r[1]["note"], r
print("3 secrets allowlist ok")

# 4. tokens/: the real folder is clean; a stray file fails
assert all(c["ok"] for c in I.token_file_checks())
td = SCRATCH / "tokens"; td.mkdir(); (td / "youtube_gaming.enc").write_bytes(b"x"); (td / "charlie_personal.enc").write_bytes(b"x")
r = I.token_file_checks(td); assert [c["ok"] for c in r] == [False, True], r
print("4 token files ok")

# 5. the gate: no audit passes, a clean audit passes, a failed audit stops
I.OUT = SCRATCH / "identity.json"
assert I.gate() == 0
I.OUT.write_text(json.dumps({"checked": I.NOW.isoformat(), "ok": True, "problems": []})); assert I.gate() == 0
I.OUT.write_text(json.dumps({"checked": I.NOW.isoformat(), "ok": False, "problems": ["youtube_x: Charlie Page (not a Quickplay name)"]})); assert I.gate() == 1
print("5 gate ok")
print("identity ok")
