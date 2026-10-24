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

# 6. an expired or revoked YouTube sign-in is a reconnect alert, not a security problem that stops all posting
import types
os.environ.setdefault("YT_CLIENT_ID", "x"); os.environ.setdefault("YT_CLIENT_SECRET", "y")
soc = types.ModuleType("social"); soc.load = lambda name: {"refresh_token": "r", "scope": "s"}; sys.modules["social"] = soc
g1 = types.ModuleType("google.oauth2.credentials"); g1.Credentials = lambda *a, **k: object()
g2 = types.ModuleType("googleapiclient.discovery")
def boom(*a, **k): raise RuntimeError("('invalid_grant: Token has been expired or revoked.', {'error': 'invalid_grant'})")
g2.build = boom
for name, mod in (("google", types.ModuleType("google")), ("google.oauth2", types.ModuleType("google.oauth2")), ("google.oauth2.credentials", g1),
                  ("googleapiclient", types.ModuleType("googleapiclient")), ("googleapiclient.discovery", g2)):
    sys.modules[name] = mod
old_root = I.ROOT; I.ROOT = SCRATCH / "exp"; (I.ROOT / "tokens").mkdir(parents=True); (I.ROOT / "tokens" / "youtube.enc").write_bytes(b"x")
r = I.youtube_checks()
assert r[0]["ok"] and r[0]["found"] == "expired sign-in" and I.EXPIRED_SIGNINS == ["youtube"], r
g2.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HttpError 403 forbidden"))      # any other failure still fails
I.EXPIRED_SIGNINS.clear(); r = I.youtube_checks(); assert not r[0]["ok"], r
I.ROOT = old_root
print("6 expired sign-in ok")

# 7. a failure that says nothing about whose account it is (network, rate or quota limit, server error, an expired Meta
# key) never stops posting; a foreign account still does, and a network error right after one keeps the gate shut
import requests
I.ROOT = SCRATCH / "exp"
class _R:
    def __init__(self, code, data): self.status_code, self._d, self.ok = code, data, 200 <= code < 300
    def json(self): return self._d
CASE = {}
def _get(url, **k):
    v = CASE.get("fb" if "facebook" in url else "ig")
    if isinstance(v, Exception): raise v
    return v or (_R(200, {"name": "Quickplay Daily", "id": "1"}) if "facebook" in url else _R(200, {"username": "quickplaydaily", "user_id": "1"}))
requests.get = _get
soc.load = lambda name: {"refresh_token": "r", "scope": "s"}       # no saved Instagram key: only the secrets below are checked
os.environ.update(IG_TOKEN="ig", FB_PAGE_TOKEN="fb", FB_PAGE_ID="1")
for code, data in ((500, {"error": {"code": 2, "is_transient": True}}), (403, {"error": {"code": 4}}), (429, {}),
                   (400, {"error": {"code": 190, "type": "OAuthException", "message": "Session has expired"}})):
    CASE.clear(); CASE["fb"] = _R(code, data); I.EXPIRED_SIGNINS.clear()
    fb = [c for c in I.meta_checks() if c["what"] == "FB_PAGE_TOKEN"][0]
    assert fb["ok"], (code, fb)
    assert (I.EXPIRED_SIGNINS == ["FB_PAGE_TOKEN"]) == (code == 400), (code, I.EXPIRED_SIGNINS)
CASE.clear(); CASE["ig"] = requests.exceptions.ConnectionError("Connection aborted")
assert all(c["ok"] for c in I.meta_checks())
CASE.clear(); CASE["fb"] = _R(400, {"error": {"code": 100, "message": "Unsupported get request"}})     # unexplained: fails as before
assert not [c for c in I.meta_checks() if c["what"] == "FB_PAGE_TOKEN"][0]["ok"]
g2.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("<HttpError 503 when requesting x returned \"backendError\">"))
assert I.youtube_checks()[0]["ok"] and I.youtube_checks()[0].get("unverified")
I.OUT = SCRATCH / "identity7.json"; I.login_checks = lambda *a, **k: []; I.tiktok_checks = lambda: []
import alerts as _A
_A.raise_issue = _A.clear = lambda *a, **k: None                                 # never a real GitHub issue from a test
_key = os.environ.get("SOCIAL_KEY"); os.environ["SOCIAL_KEY"] = "k" * 32
I.youtube_checks = lambda: [I.check("youtube", "Some Other Channel", False, note="not a Quickplay name")]
CASE.clear(); assert not I.audit()["ok"] and I.gate() == 1                       # a foreign channel stops posting
I.youtube_checks = lambda: [I.unverified("youtube", "TransportError")]
assert not I.audit()["ok"] and I.gate() == 1                                     # a network error does not reopen the gate
I.youtube_checks = lambda: [I.check("youtube", "Quickplay Daily", True)]
assert I.audit()["ok"] and I.gate() == 0                                         # a clean check does
for k in ("IG_TOKEN", "FB_PAGE_TOKEN", "FB_PAGE_ID"): os.environ.pop(k, None)
if _key is None: os.environ.pop("SOCIAL_KEY", None)
else: os.environ["SOCIAL_KEY"] = _key
I.ROOT = old_root
print("7 transient failures ok")
