"""Post Shorts to TikTok and Instagram once they are public on YouTube, and keep the sign-ins fresh.

usage:
  python pipeline/social.py post             post every Short that is public on YouTube and not yet on TikTok/Instagram
  python pipeline/social.py tiktok-connect   swap the one-time TikTok code (env TIKTOK_CODE) for tokens
  python pipeline/social.py refresh          refresh the Instagram and TikTok tokens
  python pipeline/social.py check            check both sign-ins, write status/social.json
  python pipeline/social.py ig-dry-run       prove Instagram can take a video from a release, without posting

Sign-ins live in tokens/*.enc, encrypted with SOCIAL_KEY (a GitHub secret); IG_TOKEN and IG_USER_ID seed Instagram.
The TikTok/Instagram version of each Short (platform-safe music) waits in a draft GitHub release named social-<id>.
Nothing here prints a token.
"""
import base64, datetime as dt, hashlib, json, os, pathlib, subprocess, sys, time
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOK = ROOT / "tokens"
CFG = json.loads((ROOT / "config.json").read_text())
REPO = os.environ.get("GITHUB_REPOSITORY", "quickplay-studio/quickplay-autopilot")
IG_API = "https://graph.instagram.com/" + CFG.get("instagram_api_version", "v23.0")
TT_API = "https://open.tiktokapis.com/v2"
TT_REDIRECT = "https://quickplay-studio.github.io/quickplay-autopilot/tiktok-callback.html"
NOW = lambda: dt.datetime.now(dt.timezone.utc)

# ---------- encrypted token store ----------
def _fernet():
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    key = os.environ.get("SOCIAL_KEY", "")
    if len(key) < 20: raise SystemExit("SOCIAL_KEY secret missing or too short")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"quickplay-social-v1", iterations=300_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(key.encode())))

def load(name):
    p = TOK / f"{name}.enc"
    if p.exists(): return json.loads(_fernet().decrypt(p.read_bytes()))
    return {}

def save(name, data):
    TOK.mkdir(exist_ok=True)
    (TOK / f"{name}.enc").write_bytes(_fernet().encrypt(json.dumps(data).encode()))

# ---------- Instagram ----------
def ig_tokens():
    t = load("instagram")
    if not t and os.environ.get("IG_TOKEN"):
        t = {"token": os.environ["IG_TOKEN"], "user": os.environ.get("IG_USER_ID", ""), "saved": NOW().isoformat()}
        save("instagram", t)
    return t

def ig_refresh(t):
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": t["token"]}, timeout=30)
    if r.ok:
        t.update(token=r.json()["access_token"], saved=NOW().isoformat(), expires_in=r.json().get("expires_in"))
        save("instagram", t); return "instagram token refreshed"
    return f"instagram refresh failed ({r.status_code})"

def ig_post(t, video_url, caption):
    """Reel from a public video URL: create a container, wait until Instagram has processed it, publish."""
    user = t.get("user") or os.environ.get("IG_USER_ID")
    r = requests.post(f"{IG_API}/{user}/media", data={"media_type": "REELS", "video_url": video_url, "caption": caption,
                                                       "share_to_feed": "true", "access_token": t["token"]}, timeout=60)
    if not r.ok: raise RuntimeError(f"instagram container: {r.status_code} {r.text[:300]}")
    cid = r.json()["id"]
    for _ in range(60):
        s = requests.get(f"{IG_API}/{cid}", params={"fields": "status_code,status", "access_token": t["token"]}, timeout=30).json()
        if s.get("status_code") == "FINISHED": break
        if s.get("status_code") in ("ERROR", "EXPIRED"): raise RuntimeError(f"instagram processing: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("instagram processing took too long")
    r = requests.post(f"{IG_API}/{user}/media_publish", data={"creation_id": cid, "access_token": t["token"]}, timeout=60)
    if not r.ok: raise RuntimeError(f"instagram publish: {r.status_code} {r.text[:300]}")
    return r.json()["id"]

# ---------- TikTok ----------
def tt_connect():
    code = os.environ.get("TIKTOK_CODE", "").strip()
    if not code: raise SystemExit("no TikTok code given")
    r = requests.post(f"{TT_API}/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "code": code, "grant_type": "authorization_code", "redirect_uri": TT_REDIRECT})
    j = r.json()
    note = ROOT / "status" / "tiktok_connect.json"; note.parent.mkdir(exist_ok=True)
    if "access_token" not in j:   # keep TikTok's reason where Charlie and Claude can see it (no keys or codes in it)
        note.write_text(json.dumps({"at": NOW().isoformat(timespec="seconds"), "ok": False, "error": j.get("error"),
                                    "description": str(j.get("error_description", ""))[:300]}, indent=1))
        print("TikTok refused the code:", j.get("error"), j.get("error_description", "")); return
    note.write_text(json.dumps({"at": NOW().isoformat(timespec="seconds"), "ok": True, "scopes": j.get("scope")}, indent=1))
    save("tiktok", {k: j.get(k) for k in ("access_token", "refresh_token", "open_id", "scope", "expires_in", "refresh_expires_in")}
         | {"saved": NOW().isoformat()})
    print("tiktok connected, scopes:", j.get("scope"))

def tt_refresh(t):
    r = requests.post(f"{TT_API}/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
    j = r.json()
    if "access_token" not in j: return f"tiktok refresh failed: {j.get('error')}"
    t.update({k: j.get(k) for k in ("access_token", "refresh_token", "expires_in", "refresh_expires_in")}, saved=NOW().isoformat())
    save("tiktok", t); return "tiktok token refreshed"

def tt_post(t, path, caption, mode):
    """mode "inbox": the video lands in the TikTok inbox to finish in the app (works before TikTok's audit).
    mode "direct": posts straight away (public only once TikTok has audited the app)."""
    h = {"Authorization": f"Bearer {t['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
    size = path.stat().st_size
    src = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    if mode == "direct":
        info = requests.post(f"{TT_API}/post/publish/creator_info/query/", headers=h, timeout=30).json().get("data", {})
        opts = info.get("privacy_level_options") or ["SELF_ONLY"]
        body = {"post_info": {"title": caption[:2200], "privacy_level": "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in opts else opts[0],
                              "disable_comment": False, "disable_duet": False, "disable_stitch": False,
                              "video_cover_timestamp_ms": 1000, "is_aigc": True}, "source_info": src}
        url = f"{TT_API}/post/publish/video/init/"
    else:
        body, url = {"source_info": src}, f"{TT_API}/post/publish/inbox/video/init/"
    r = requests.post(url, headers=h, json=body, timeout=60).json()
    if r.get("error", {}).get("code") not in (None, "ok"): raise RuntimeError(f"tiktok init: {r['error']}")
    d = r["data"]
    up = requests.put(d["upload_url"], data=path.read_bytes(), timeout=300,
                      headers={"Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if up.status_code not in (200, 201): raise RuntimeError(f"tiktok upload: {up.status_code} {up.text[:200]}")
    return d["publish_id"]

# ---------- what to post ----------
def caption(st, board, platform="instagram"):
    """Title, summary and hashtags, most relevant first: Instagram allows 5 hashtags per Reel; TikTok gets 7 plus #fyp."""
    m = (board or {}).get("meta", {})
    tags, seen = [], set()
    for h in m.get("hashtags", []):
        if h.lower() in seen or h.lower() == "#shorts": continue
        seen.add(h.lower()); tags.append(h)
    tags = tags[:5] if platform == "instagram" else tags[:7] + ["#fyp"]
    return "\n\n".join(x for x in (st.get("title") or m.get("title", ""), m.get("summary", ""), " ".join(tags)) if x)

def board_for(st):
    for d in ("done", "ready", "queue", "hold"):
        p = ROOT / "boards" / d / f"{st['id']}.json"
        if p.exists(): return json.loads(p.read_text())
    return None

def gh(*args, check=True):
    return subprocess.run(["gh", *args, "-R", REPO], capture_output=True, text=True, check=check)

def _age_h(t):
    try: return (NOW() - dt.datetime.fromisoformat(t["saved"])).total_seconds() / 3600
    except Exception: return 1e9

def post():
    ig, tt = ig_tokens(), load("tiktok")
    if ig and _age_h(ig) > 24 * 7: print(ig_refresh(ig))            # long-lived Instagram token: refresh weekly
    if tt.get("refresh_token") and _age_h(tt) > 20: print(tt_refresh(tt))   # TikTok access tokens last 24 hours
    mode = CFG.get("tiktok_mode", "inbox")
    tt_max_age = float(CFG.get("tiktok_max_age_hours", 24))   # trends go stale: skip TikTok for Shorts public longer than this
    tt_blocked = False                                           # TikTok said "too many drafts waiting": try again next hour
    done_any = False
    for sp in sorted((ROOT / "status").glob("QD-*.json")):
        st = json.loads(sp.read_text())
        if not st.get("video") or not st.get("social_release") or not st.get("publish_at"): continue
        public_at = dt.datetime.fromisoformat(st["publish_at"].replace("Z", "+00:00"))
        public = public_at <= NOW()
        # TikTok drafts go out as soon as the Short is scheduled (config tiktok_when "uploaded"), so Charlie can post them
        # in one go with the captions from the morning message; or when it goes public on YouTube ("public").
        tt_now = public or CFG.get("tiktok_when", "uploaded") == "uploaded"
        if not (public or tt_now): continue
        since = public_at if CFG.get("tiktok_when", "uploaded") == "public" else \
            dt.datetime.fromisoformat((st.get("uploaded_at") or st["publish_at"]).replace("Z", "+00:00"))
        fresh = (NOW() - since).total_seconds() / 3600 <= tt_max_age
        b = board_for(st)
        picked = (b or {}).get("tiktok", True)       # the writer marks the 5 Shorts a day most likely to do well on TikTok
        want_ig = bool(ig) and public and not st.get("instagram")
        manual = mode == "manual"                    # Charlie uploads TikTok himself on desktop from the morning package
        want_tt = bool(tt) and not manual and tt_now and picked and not st.get("tiktok") and not tt_blocked and fresh and not st.get("tiktok_skipped")
        if not (want_ig or want_tt): continue
        rel = st["social_release"]; work = ROOT / "social_tmp"; work.mkdir(exist_ok=True)
        if gh("release", "download", rel, "-p", "social.mp4", "-D", str(work), "--clobber", check=False).returncode:
            st["social_error"] = "release missing"; sp.write_text(json.dumps(st, indent=1, ensure_ascii=False)); continue
        mp4 = work / "social.mp4"
        if want_tt:
            try:
                cap = caption(st, b, "tiktok")
                st["tiktok"] = {"publish_id": tt_post(tt, mp4, cap, mode), "mode": mode, "at": NOW().isoformat(timespec="seconds")}
                if mode == "inbox": st["tiktok"]["caption"] = cap     # drafts can't carry a caption: Charlie pastes this one
                st.pop("tiktok_error", None)
            except Exception as e:
                st["tiktok_error"] = f"{NOW():%Y-%m-%d %H:%M} {e}"[:300]
                if "too_many_pending" in str(e) or "rate_limit" in str(e): tt_blocked = True
        if want_ig:
            try:
                gh("release", "edit", rel, "--draft=false")
                url = f"https://github.com/{REPO}/releases/download/{rel}/social.mp4"
                st["instagram"] = {"media": ig_post(ig, url, caption(st, b, "instagram")), "at": NOW().isoformat(timespec="seconds")}
                st.pop("instagram_error", None)
            except Exception as e: st["instagram_error"] = f"{NOW():%Y-%m-%d %H:%M} {e}"[:300]
        if tt and not fresh and not st.get("tiktok"): st["tiktok_skipped"] = f"over {tt_max_age:g} hours old before TikTok could take it"
        if tt and not picked and not st.get("tiktok"): st["tiktok_skipped"] = "not one of the day's 5 TikTok picks"
        if tt and manual and not st.get("tiktok"): st["tiktok_skipped"] = "uploaded by hand on desktop" if picked else "not a TikTok pick"
        if (st.get("tiktok") or st.get("tiktok_skipped") or not tt) and (st.get("instagram") or not ig):
            gh("release", "delete", rel, "--cleanup-tag", "-y", check=False); st.pop("social_release", None)
        else:
            gh("release", "edit", rel, "--draft=true", check=False)
        mp4.unlink(missing_ok=True)
        sp.write_text(json.dumps(st, indent=1, ensure_ascii=False)); done_any = True
        print(st["id"], "tiktok:", bool(st.get("tiktok")), "instagram:", bool(st.get("instagram")))
    if not done_any: print("nothing to post")

def check():
    """Confirm the sign-ins work without posting anything; writes status/social.json (no tokens in it)."""
    out = {"checked": NOW().isoformat(timespec="seconds")}
    ig = ig_tokens()
    if not ig:
        out["instagram"] = {"ok": False, "error": "not connected (IG_TOKEN secret missing)"}
    else:
        r = requests.get(f"{IG_API}/me", params={"fields": "user_id,username,account_type", "access_token": ig["token"]}, timeout=30)
        if r.ok:
            me = r.json()
            out["instagram"] = {"ok": True, "username": me.get("username"), "account_type": me.get("account_type"),
                                "user_id": me.get("user_id"), "secret_user_id_matches": str(me.get("user_id")) == str(ig.get("user"))}
            if me.get("user_id") and not ig.get("user"):
                ig["user"] = str(me["user_id"]); save("instagram", ig)
            q = requests.get(f"{IG_API}/{ig.get('user') or me.get('user_id')}/content_publishing_limit",
                             params={"fields": "config,quota_usage", "access_token": ig["token"]}, timeout=30)
            out["instagram"]["publishing_limit"] = q.json().get("data") if q.ok else f"{q.status_code} {q.text[:200]}"
        else:
            out["instagram"] = {"ok": False, "error": f"{r.status_code} {r.text[:300]}"}
    tt = load("tiktok")
    if not tt.get("refresh_token"):
        ck = os.environ.get("TIKTOK_CLIENT_KEY", "")
        out["tiktok"] = {"ok": False, "error": "not connected yet" if ck else "not connected (TIKTOK_CLIENT_KEY secret missing)"}
        if ck:   # the client key is public by design (it is part of every sign-in link)
            q = {"client_key": ck, "scope": "user.info.basic,user.info.profile,user.info.stats,video.list,video.upload,video.publish", "response_type": "code",
                 "redirect_uri": TT_REDIRECT, "state": hashlib.sha1(ck.encode()).hexdigest()[:12]}
            out["tiktok"]["connect_url"] = "https://www.tiktok.com/v2/auth/authorize/?" + requests.compat.urlencode(q)
    else:
        h = {"Authorization": f"Bearer {tt['access_token']}"}
        r = requests.get(f"{TT_API}/user/info/", params={"fields": "open_id,display_name,username"}, headers=h, timeout=30)
        j = r.json() if r.content else {}
        out["tiktok"] = {"ok": r.ok and j.get("error", {}).get("code") in (None, "ok"), "user": (j.get("data") or {}).get("user"),
                         "scopes": tt.get("scope"), "mode": CFG.get("tiktok_mode", "inbox")}
    (ROOT / "status").mkdir(exist_ok=True)
    sj = ROOT / "status" / "social.json"
    old = json.loads(sj.read_text()) if sj.exists() else {}
    stable = lambda d: json.dumps({k: v for k, v in d.items() if k not in ("checked", "instagram_dry_run")}, sort_keys=True, default=str)
    age = (NOW() - dt.datetime.fromisoformat(old["checked"])).total_seconds() / 3600 if old.get("checked") else 1e9
    # hourly runs only rewrite the file when something changed (or once a day), so the repo doesn't fill with check commits
    if stable(old) != stable(out) or age > 24 or os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        if old.get("instagram_dry_run"): out["instagram_dry_run"] = old["instagram_dry_run"]
        sj.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1))

def ig_dry_run():
    """Proves Instagram can fetch and process a video from a GitHub release, without posting anything:
    a 5-second blank test clip goes up as a release, Instagram builds a Reel container from it, the container is never
    published (Instagram discards it after 24 hours) and the release is deleted straight away."""
    ig = ig_tokens(); res = {"at": NOW().isoformat(timespec="seconds")}
    work = ROOT / "social_tmp"; work.mkdir(exist_ok=True); mp4 = work / "social.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x1d1d1f:s=1080x1920:r=30:d=5",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    tag = f"ig-test-{NOW():%Y%m%d%H%M%S}"
    r = gh("release", "create", tag, str(mp4), "--title", tag, "--notes", "Instagram test file, deleted straight after.", check=False)
    if r.returncode: res["error"] = f"release: {r.stderr.strip()[:200]}"
    else:
        try:
            url = f"https://github.com/{REPO}/releases/download/{tag}/social.mp4"
            user = ig.get("user") or os.environ.get("IG_USER_ID")
            c = requests.post(f"{IG_API}/{user}/media", data={"media_type": "REELS", "video_url": url, "caption": "test",
                                                                "access_token": ig["token"]}, timeout=60)
            if not c.ok: res["error"] = f"container: {c.status_code} {c.text[:300]}"
            else:
                cid = c.json()["id"]; res["container"] = "created"
                for _ in range(36):
                    st = requests.get(f"{IG_API}/{cid}", params={"fields": "status_code,status", "access_token": ig["token"]}, timeout=30).json()
                    res["status_code"], res["status"] = st.get("status_code"), st.get("status")
                    if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"): break
                    time.sleep(5)
                res["ok"] = res.get("status_code") == "FINISHED"
                res["note"] = "never published; Instagram discards unpublished containers after 24 hours"
        finally:
            gh("release", "delete", tag, "--cleanup-tag", "-y", check=False)
    mp4.unlink(missing_ok=True)
    sj = ROOT / "status" / "social.json"
    out = json.loads(sj.read_text()) if sj.exists() else {}
    out["instagram_dry_run"] = res
    sj.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(res))

def tt_test():
    """Sends one test Short to the TikTok inbox as a draft, only when Charlie has asked for it (requests/social-check.txt
    says "tiktok-test <id>"). The Short comes from that id's private preview release, which is deleted afterwards."""
    sid = os.environ.get("TT_TEST_ID", "").strip(); tt = load("tiktok")
    out = {"at": NOW().isoformat(timespec="seconds"), "id": sid}
    work = ROOT / "social_tmp"; work.mkdir(exist_ok=True); rel = f"preview-{sid}"
    if not tt.get("access_token"): out["error"] = "TikTok not connected"
    elif gh("release", "download", rel, "-p", "social.mp4", "-D", str(work), "--clobber", check=False).returncode:
        out["error"] = f"no preview release {rel}"
    else:
        try:
            pid = tt_post(tt, work / "social.mp4", "test", "inbox"); out.update(ok=True, publish_id_set=bool(pid))
            h = {"Authorization": f"Bearer {tt['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
            for _ in range(12):
                time.sleep(10)
                r = requests.post(f"{TT_API}/post/publish/status/fetch/", headers=h, json={"publish_id": pid}, timeout=30).json()
                out["status"] = (r.get("data") or {}).get("status"); out["fail_reason"] = (r.get("data") or {}).get("fail_reason")
                if out["status"] and out["status"] not in ("PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD"): break
        except Exception as e:
            out.update(ok=False, error=str(e)[:300])
        gh("release", "delete", rel, "-y", check=False)
    (work / "social.mp4").unlink(missing_ok=True)
    (ROOT / "status" / "tiktok_test.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))

def refresh():
    ig, tt = ig_tokens(), load("tiktok")
    if ig: print(ig_refresh(ig))
    if tt.get("refresh_token"): print(tt_refresh(tt))

if __name__ == "__main__":
    {"post": post, "tiktok-connect": tt_connect, "refresh": refresh, "check": check, "ig-dry-run": ig_dry_run, "tiktok-test": tt_test}[sys.argv[1]]()
