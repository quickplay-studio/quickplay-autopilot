"""Offline test of the channels' Instagram and Facebook keys (24 October, audit M8): the identity audit refreshes each
IG_<CHANNEL>_TOKEN weekly into tokens/instagram_<channel>.enc and the refreshed key replaces the secret it grew from; a
secret Charlie replaces starts again from itself; a key near its end that could not be refreshed (or a channel's Facebook
Page key whose data access ends soon) raises one needs-charlie issue, cleared once all is fresh."""
import pathlib as _p, sys, datetime as dt
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO_DIR + "/pipeline")
import social as S
import alerts as A

STORE, ISSUES, CALLS = {}, [], []
S.load = lambda name: dict(STORE.get(name) or {})
S.save = lambda name, data: STORE.__setitem__(name, dict(data))
A.raise_issue = lambda title, body, labels=None: ISSUES.append(("raise", title, body, tuple(labels or ())))
A.clear = lambda title, body: ISSUES.append(("clear", title))
NOW = dt.datetime(2026, 10, 24, 12, 0, tzinfo=dt.timezone.utc)
STATE = {"refresh": "ok", "fb_data_end": NOW + dt.timedelta(days=60)}


class R:
    def __init__(self, code, data): self.status_code, self._d, self.ok, self.content = code, data, 200 <= code < 300, b"x"
    def json(self): return self._d


def get(url, params=None, **kw):
    CALLS.append(url)
    if "refresh_access_token" in url:
        if STATE["refresh"] == "ok": return R(200, {"access_token": "fresh-" + params["access_token"], "token_type": "bearer", "expires_in": 5184000})
        return R(400, {"error": {"message": "Error validating access token", "code": 190}})
    if "debug_token" in url:
        return R(200, {"data": {"expires_at": 0, "data_access_expires_at": int(STATE["fb_data_end"].timestamp())}})
    return R(404, {})


env = {"IG_CLIPS_TOKEN": "seed1", "IG_CLIPS_USER_ID": "9", "IG_TOKEN": "main", "FB_CLIPS_PAGE_TOKEN": "fbk", "FB_PAGE_TOKEN": "mainfb"}

# 1. first audit: the channel key is refreshed and kept; the main keys (IG_TOKEN, FB_PAGE_TOKEN) are left to their own code
notes = S.refresh_meta_keys(env, get, NOW)
s = STORE["instagram_clips"]
assert s["token"] == "fresh-seed1" and s["seed"] == S._seed("seed1") and s["expires_at"].startswith("2026-12-23"), (s, notes)
assert not any("instagram_main" in k or k == "instagram" for k in STORE), STORE
assert sum("refresh_access_token" in c for c in CALLS) == 1 and sum("debug_token" in c for c in CALLS) == 1      # FB_CLIPS only
assert ISSUES[-1][0] == "clear"
# the refreshed key replaces the secret; refreshing again in the same run (the key already swapped in) changes nothing
env2 = dict(env); assert S.apply_stored_keys(env2) == ["IG_CLIPS_TOKEN"] and env2["IG_CLIPS_TOKEN"] == "fresh-seed1"
CALLS.clear(); S.refresh_meta_keys(env2, get, NOW + dt.timedelta(hours=6))
assert STORE["instagram_clips"]["seed"] == S._seed("seed1") and not any("refresh_access_token" in c for c in CALLS)
print("refresh and apply ok")

# 2. a week on, refreshed again from the stored key (not from the old secret)
CALLS.clear(); S.refresh_meta_keys(env, get, NOW + dt.timedelta(days=7, hours=1))
assert STORE["instagram_clips"]["token"] == "fresh-fresh-seed1", STORE["instagram_clips"]
# 3. Charlie pastes a new secret: a new line starts from it
env3 = dict(env, IG_CLIPS_TOKEN="seed2"); S.refresh_meta_keys(env3, get, NOW + dt.timedelta(days=8))
assert STORE["instagram_clips"]["token"] == "fresh-seed2" and STORE["instagram_clips"]["seed"] == S._seed("seed2")
assert S.apply_stored_keys(dict(env3))                                   # applies to the new secret
assert not S.apply_stored_keys(dict(env))                                # the old secret is not swapped for the new line's key
print("weekly and new secret ok")

# 4. refusals: nothing raised while the key has time; within 10 days of its end, one needs-charlie issue naming it
STORE.clear(); ISSUES.clear(); STATE["refresh"] = "refused"
S.refresh_meta_keys(env, get, NOW)
assert ISSUES[-1][0] == "clear" and STORE["instagram_clips"]["error"].startswith("refresh refused (400)")
S.refresh_meta_keys(env, get, NOW + dt.timedelta(days=55))              # never refreshed: 60 days from first seen
kind, title, body, labels = ISSUES[-1]
assert kind == "raise" and title == S.KEY_ISSUE and "IG_CLIPS_TOKEN (Instagram)" in body and labels == ("needs-charlie",), ISSUES[-1]
print("renewal issue ok")

# 5. a channel's Facebook Page key whose data access ends within 10 days is named too; once fresh, the issue clears
STORE.clear(); ISSUES.clear(); STATE.update(refresh="ok", fb_data_end=NOW + dt.timedelta(days=5))
S.refresh_meta_keys(env, get, NOW)
assert ISSUES[-1][0] == "raise" and "FB_CLIPS_PAGE_TOKEN (Facebook)" in ISSUES[-1][2] and "IG_CLIPS" not in ISSUES[-1][2], ISSUES[-1]
STATE["fb_data_end"] = NOW + dt.timedelta(days=80); S.refresh_meta_keys(env, get, NOW + dt.timedelta(days=1))
assert ISSUES[-1] == ("clear", S.KEY_ISSUE)
print("facebook ok")

# 6. the identity audit: the IG_TOKEN secret that only seeds tokens/instagram.enc may run out without a renewal alert,
#    while the stored key it seeded is checked as "instagram"; a refreshed channel key is what gets checked
import os, requests
import identity as I
STORE.clear(); STORE["instagram"] = {"token": "stored-main"}
def iget(url, params=None, **kw):
    tok = (params or {}).get("access_token")
    if "graph.instagram.com/me" in url:
        return R(400, {"error": {"code": 190, "message": "Session has expired"}}) if tok == "main" else R(200, {"username": "quickplaydaily", "user_id": "1"})
    return R(200, {"name": "Quickplay Daily", "id": "1"})
requests.get = iget
old = {k: os.environ.get(k) for k in ("IG_TOKEN", "IG_CLIPS_TOKEN", "FB_PAGE_TOKEN", "FB_PAGE_ID")}
os.environ.update(IG_TOKEN="main", IG_CLIPS_TOKEN="fresh-x"); os.environ.pop("FB_PAGE_TOKEN", None)
I.EXPIRED_SIGNINS.clear()
got = {c["what"]: c for c in I.meta_checks()}
assert got["instagram"]["ok"] and got["IG_TOKEN"]["ok"] and got["IG_TOKEN"]["found"] == "expired seed" and not I.EXPIRED_SIGNINS, (got, I.EXPIRED_SIGNINS)
assert got["IG_CLIPS_TOKEN"]["ok"]
for k, v in old.items():
    if v is None: os.environ.pop(k, None)
    else: os.environ[k] = v
print("identity seed ok")
print("meta keys ok")
