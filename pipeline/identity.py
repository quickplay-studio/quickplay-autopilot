"""The identity guard (Charlie, 22 October): everything the automation signs in to must belong to the studio Google
account (studiosocialmedia123@gmail.com) and the accounts hanging off it, all named Quickplay. Nothing else, ever.

  python pipeline/identity.py audit    every sign-in the automation holds is resolved live and checked against config.json
                                       "accounts" (ids and the Quickplay name rule), every secret a workflow reads is checked
                                       against the allowlist, the saved campaign-site sign-ins may hold cookies for their own
                                       sites only, tokens/ may hold only the expected files. Result: status/identity.json;
                                       a mismatch opens the GitHub issue "🔒 Security: a sign-in outside the studio account"
                                       (which closes itself once clean) and the posting workflows stop until it is.
  python pipeline/identity.py gate     the first step of every workflow that posts: exits 1 while the last audit found a
                                       sign-in outside the studio, so nothing is uploaded, posted, commented or submitted.
Nothing secret is written anywhere: ids, names and handles only.
"""
import datetime as dt, glob, json, os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
NOW = dt.datetime.now(dt.timezone.utc)
OUT = ROOT / "status" / "identity.json"
TITLE = "🔒 Security: a sign-in outside the studio account"
CFG = json.loads((ROOT / "config.json").read_text())
ACC = CFG.get("accounts") or {}
TOKEN_FILES = re.compile(r"^(youtube(_[a-z]+)?|instagram(_[a-z]+)?|facebook(_[a-z]+)?|tiktok(_[a-z]+)?|login_whop|login_vyro)\.enc$")


def log(*a): print(*a, flush=True)


def studio_name(name):
    """The name rule: every channel, page and profile of the studio is called Quickplay something."""
    prefix = re.sub(r"\s+", "", str(ACC.get("name_prefix") or "quickplay")).lower()
    return re.sub(r"[\s_\-.]+", "", str(name or "")).lower().startswith(prefix)


def check(what, found, ok, expected="", note=""):
    return {"what": what, "found": found, "ok": bool(ok), "expected": expected, "note": note}


# Failures that say nothing about whose account a sign-in is: the network, a rate or quota limit, a server error. Until
# 24 October each of them failed the audit, which stopped every posting workflow for at least 6 hours (a Meta 500, a
# YouTube quotaExceeded, a timeout). Now the sign-in is "not checked this time" and keeps the last audit's verdict.
TRANSIENT = re.compile(r"quotaExceeded|rateLimitExceeded|backendError|internalError|HttpError (?:429|5\d\d)|TransportError"
                       r"|ServerNotFound|ConnectionError|ConnectTimeout|ReadTimeout|Timeout|timed out|RemoteDisconnected"
                       r"|Connection (?:aborted|reset|refused)|Max retries exceeded|Temporary failure in name resolution|SSLError", re.I)


def transient(e):
    return bool(TRANSIENT.search(f"{type(e).__name__}: {e}"))


def unverified(what, why):
    c = check(what, "not checked this time", True, note=f"could not be checked now ({why}); the last audit's verdict stands")
    c["unverified"] = True
    return c


def meta_failure(r):
    """What a Graph API refusal means: "expired" (code 190: the key no longer works, so it reaches no account), "transient"
    (a server error or a rate limit), or "" (a refusal the audit cannot explain: it fails, as before)."""
    try: err = (r.json() or {}).get("error") or {}
    except Exception: err = {}
    code = err.get("code")
    if r.status_code == 429 or r.status_code >= 500 or err.get("is_transient") or code in (1, 2, 4, 17, 32, 341, 613) \
            or (isinstance(code, int) and 80000 <= code < 80100):
        return "transient"
    if code == 190: return "expired"
    return ""


# ---------- the live sign-ins ----------
def youtube_checks():
    out = []
    try: import social
    except Exception as e: return [check("youtube", "", False, note=f"social.py: {e}")]
    for p in sorted((ROOT / "tokens").glob("youtube*.enc")):
        name = p.stem
        try:
            t = social.load(name)
            if not t.get("refresh_token"): out.append(check(name, "no sign-in", True, note="empty")); continue
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials(None, refresh_token=t["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
                                client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"], scopes=(t.get("scope") or "").split())
            yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
            items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
            if not items: out.append(check(name, "no channel", False, note="the sign-in reaches no channel")); continue
            cid, title, handle = items[0]["id"], items[0]["snippet"].get("title", ""), items[0]["snippet"].get("customUrl", "")
            known = (ACC.get("youtube") or {})
            ok = cid in known or studio_name(title)
            out.append(check(name, f"{title} ({handle or cid})", ok, expected="a Quickplay channel of the studio account",
                             note="" if ok else "neither a listed channel id nor a Quickplay name"))
        except (Exception, SystemExit) as e:
            if EXPIRED.search(str(e)):      # an expired or revoked sign-in reaches no account at all: not a security problem,
                out.append(check(name, "expired sign-in", True, note="reconnect it (the hub's Accounts tab or the social workflow)"))
                EXPIRED_SIGNINS.append(name); continue      # so posting is not stopped for it; expired() raises its own issue
            if transient(e): out.append(unverified(name, f"{type(e).__name__}: {str(e)[:80]}")); continue
            out.append(check(name, "", False, note=f"{type(e).__name__}: {str(e)[:120]}"))
    return out


EXPIRED = re.compile(r"invalid_grant|expired or revoked|Token has been expired", re.I)
EXPIRED_SIGNINS = []


def expired_note():
    """One issue listing the sign-ins that have expired (closed again once they work)."""
    try:
        import alerts as A
        title = "🔑 A sign-in has expired: reconnect it"
        if EXPIRED_SIGNINS:
            A.raise_issue(title, "These sign-ins no longer work (Google or Meta says expired or revoked), so their posts stop until "
                          "they are reconnected: " + ", ".join(EXPIRED_SIGNINS) + ". YouTube: reconnect from the social workflow "
                          "(channel name). An IG_ or FB_ name: paste a new key into that GitHub secret. Or ask Claude from your "
                          "Quickplay page. Nothing outside the studio account is involved, so posting elsewhere continues.",
                          labels=["needs-charlie"])
        else: A.clear(title, "Every sign-in works again.")
    except Exception as e: log("expired alert:", str(e)[:120])


def meta_checks():
    out = []
    try:
        import requests, social
    except Exception as e: return [check("meta", "", False, note=f"{e}")]
    # Instagram: the saved sign-in and every IG_*_TOKEN a workflow passes
    seen = set()
    igs = []
    try:
        t = social.load("instagram")
        if t.get("token"): igs.append(("instagram", t["token"]))
    except (Exception, SystemExit) as e: out.append(check("instagram", "", False, note=f"{type(e).__name__}: {str(e)[:80]}"))
    for k, v in os.environ.items():
        if re.fullmatch(r"IG(_[A-Z]+)?_TOKEN", k) and v.strip(): igs.append((k, v.strip()))
    for label, tok in igs:
        if tok in seen: continue
        seen.add(tok)
        try:
            r = requests.get("https://graph.instagram.com/me", params={"fields": "user_id,username,account_type", "access_token": tok}, timeout=30)
            if not r.ok: out.append(meta_refusal(label, r)); continue
            me = r.json(); user = me.get("username", "")
            ok = user in (ACC.get("instagram") or []) or studio_name(user)
            out.append(check(label, f"@{user} ({me.get('user_id')})", ok, expected="a Quickplay Instagram account", note="" if ok else "not a Quickplay name"))
        except Exception as e:
            out.append(unverified(label, type(e).__name__) if transient(e) else check(label, "", False, note=f"{type(e).__name__}: {str(e)[:80]}"))
    # Facebook: every FB_*_PAGE_TOKEN with its FB_*_PAGE_ID
    api = "https://graph.facebook.com/" + CFG.get("facebook_api_version", "v25.0")
    for k, v in os.environ.items():
        m = re.fullmatch(r"FB(_[A-Z]+)?_PAGE_TOKEN", k)
        if not m or not v.strip(): continue
        page = os.environ.get(f"FB{m.group(1) or ''}_PAGE_ID", "").strip()
        try:
            r = requests.get(f"{api}/{page or 'me'}", params={"fields": "id,name", "access_token": v.strip()}, timeout=30)
            if not r.ok: out.append(meta_refusal(k, r)); continue
            j = r.json(); name = j.get("name", "")
            ok = name in (ACC.get("facebook") or []) or studio_name(name)
            out.append(check(k, f"{name} ({j.get('id')})", ok, expected="a Quickplay Facebook Page", note="" if ok else "not a Quickplay name"))
        except Exception as e:
            out.append(unverified(k, type(e).__name__) if transient(e) else check(k, "", False, note=f"{type(e).__name__}: {str(e)[:80]}"))
    return out


def meta_refusal(label, r):
    """An Instagram or Facebook key the Graph API refused: an expired key (a 60-day Instagram key in a GitHub secret runs out
    by itself) is a reconnect alert like an expired YouTube sign-in; a server error or rate limit is "not checked this time";
    anything else fails the audit, as before."""
    why = meta_failure(r)
    if why == "expired":
        EXPIRED_SIGNINS.append(label)
        return check(label, "expired key", True, note="Meta says the key has expired: paste a new one into the GitHub secret "
                     "(it reaches no account, so nothing else stops)")
    if why == "transient": return unverified(label, f"HTTP {r.status_code}")
    return check(label, f"HTTP {r.status_code}", False, note="the key does not answer")


def tiktok_checks():
    out = []
    try: import requests, social
    except Exception as e: return [check("tiktok", "", False, note=f"{e}")]
    for p in sorted((ROOT / "tokens").glob("tiktok*.enc")):
        name = p.stem
        try:
            t = social.load(name)
            if not t.get("access_token"): out.append(check(name, "no sign-in", True, note="empty")); continue
            # username needs the user.info.profile scope, which new sign-ins no longer ask for (social.TT_SCOPES, 24 October):
            # without it the display name is what the allowlist (config accounts.tiktok) and the Quickplay name rule check
            fields = "open_id,display_name" + (",username" if "user.info.profile" in str(t.get("scope") or "") else "")
            r = requests.get("https://open.tiktokapis.com/v2/user/info/", params={"fields": fields},
                             headers={"Authorization": f"Bearer {t['access_token']}"}, timeout=30)
            u = (r.json().get("data") or {}).get("user") or {} if r.ok else {}
            if not u: out.append(check(name, f"HTTP {r.status_code}", True, note="the key does not answer (expired keys are refreshed by the social run)")); continue
            who = u.get("username") or u.get("display_name") or ""
            ok = who in (ACC.get("tiktok") or []) or studio_name(who) or studio_name(u.get("display_name"))
            out.append(check(name, f"@{who}", ok, expected="a Quickplay TikTok account", note="" if ok else "not a Quickplay name"))
        except (Exception, SystemExit) as e:
            out.append(unverified(name, type(e).__name__) if transient(e) else check(name, "", False, note=f"{type(e).__name__}: {str(e)[:80]}"))
    return out


def login_checks(cookie_texts=None):
    """The saved campaign-site sign-ins may hold cookies for their own sites only: an export of another site or of a whole
    profile (google.com, github.com, a bank) is the wrong file and is refused."""
    out = []
    hosts = {"login_whop": ("contentrewards.com", "whop.com"), "login_vyro": ("vyro.com",)}
    texts = cookie_texts
    if texts is None:
        texts = {}
        try:
            import social
            for name in hosts:
                if (ROOT / "tokens" / f"{name}.enc").exists(): texts[name] = (social.load(name) or {}).get("cookies", "")
        except (Exception, SystemExit) as e: return [check("logins", "", False, note=f"{type(e).__name__}: {str(e)[:80]}")]
    import submit
    for name, text in texts.items():
        cs = submit.cookies(text)
        foreign = sorted({c["domain"].lstrip(".") for c in cs if not any(h in c["domain"] for h in hosts.get(name, ()))})
        ok = bool(cs) and not foreign
        out.append(check(name, f"{len(cs)} cookies" + (f", foreign: {', '.join(foreign[:6])}" if foreign else ""), ok,
                         expected="cookies for " + " and ".join(hosts.get(name, ())), note="" if ok else ("no cookies" if not cs else "cookies for other sites: the wrong export")))
    return out


# ---------- the repository itself ----------
def secret_checks(workflow_dir=None):
    out = []
    allowed = set(ACC.get("secrets") or [])
    for p in sorted(pathlib.Path(workflow_dir or ROOT / ".github" / "workflows").glob("*.yml")):
        text = p.read_text()
        names = sorted(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text)))
        dump = bool(re.search(r"toJSON\s*\(\s*secrets\s*\)", text))
        unknown = [n for n in names if n not in allowed]
        ok = not dump and not unknown
        out.append(check(f"workflow {p.name}", ", ".join(names) or "no secrets", ok, expected="listed secrets only",
                         note=("passes every secret at once; " if dump else "") + (f"not on the allowlist: {', '.join(unknown)}" if unknown else "")))
    return out


def token_file_checks(token_dir=None):
    out = []
    for p in sorted(pathlib.Path(token_dir or ROOT / "tokens").glob("*")):
        ok = bool(TOKEN_FILES.match(p.name))
        out.append(check(f"tokens/{p.name}", "expected" if ok else "unexpected file", ok, expected="youtube_*, instagram*, facebook*, tiktok*, login_whop, login_vyro"))
    return out


# ---------- audit and gate ----------
def keep_failures(checks):
    """A sign-in that could not be checked this time keeps the last audit's verdict: one the last audit found outside the
    studio stays a failure until a check succeeds, so a network error can never reopen the gate for it."""
    try: last = {c.get("what"): c for c in json.loads(OUT.read_text()).get("checks") or []}
    except Exception: last = {}
    for c in checks:
        p = last.get(c["what"]) or {}
        if c.get("unverified") and p and not p.get("ok"):
            c.update(ok=False, found=p.get("found", ""), note=f"not checked this time; the last audit found it outside the studio ({p.get('note', '')})"[:240])


def audit(live=True):
    checks = secret_checks() + token_file_checks()
    if live and len(os.environ.get("SOCIAL_KEY", "")) < 20:
        checks.append(check("SOCIAL_KEY", "missing", False, note="the saved sign-ins cannot be read, so they cannot be checked"))
    elif live:
        checks += login_checks() + youtube_checks() + meta_checks() + tiktok_checks()
        expired_note()
    keep_failures(checks)
    bad = [c for c in checks if not c["ok"]]
    result = {"checked": NOW.isoformat(timespec="seconds"), "ok": not bad, "studio": ACC.get("google", ""),
              "checks": checks, "problems": [f"{c['what']}: {c['found']} ({c['note']})" for c in bad]}
    OUT.parent.mkdir(exist_ok=True); OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    for c in checks: log(("ok   " if c["ok"] else "FAIL ") + f"{c['what']}: {c['found']}" + (f" ({c['note']})" if c["note"] else ""))
    skipped = sum(1 for c in checks if c.get("unverified") and c["ok"])
    log(f"identity: {'clean' if not bad else str(len(bad)) + ' problem(s)'}: {len(checks)} checks"
        + (f", {skipped} not checked this time (network or rate limit)" if skipped else ""))
    try:
        import alerts as A
        if bad:
            A.raise_issue(TITLE, "The automation holds a sign-in, key or file that is not the studio's (" + (ACC.get("google") or "the studio Google account") + "). "
                          "Every workflow that posts is stopped until this is clean.\n\n" + "\n".join("- " + p for p in result["problems"]) +
                          "\n\nFix: remove or replace it (GitHub secrets, tokens/ or the workflow file), then run the audit workflow: "
                          "https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/audit.yml",
                          labels=["needs-charlie"])
        else: A.clear(TITLE, "Clean: every sign-in belongs to the studio account.")
    except Exception as e: log("identity alert:", str(e)[:120])
    return result


def gate():
    """Exit 1 while the last audit found something outside the studio; a missing or stale audit is a warning only."""
    if not OUT.exists(): log("identity gate: no audit yet, continuing"); return 0
    try: r = json.loads(OUT.read_text())
    except Exception: log("identity gate: unreadable audit, continuing"); return 0
    try: age_h = (NOW - dt.datetime.fromisoformat(r["checked"])).total_seconds() / 3600
    except Exception: age_h = 0
    if not r.get("ok"):
        log("identity gate: STOP, the last audit found a sign-in outside the studio account:")
        for p in r.get("problems", []): log("  -", p)
        return 1
    log(f"identity gate: clean ({age_h:.0f} h ago)" + (" but stale, run the audit" if age_h > 48 else ""))
    return 0


if __name__ == "__main__":
    if "gate" in sys.argv[1:]: sys.exit(gate())
    r = audit(live="offline" not in sys.argv[1:])
    sys.exit(0 if r["ok"] else 1)
