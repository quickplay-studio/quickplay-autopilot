"""A second YouTube sign-in with the youtube.force-ssl permission, for comments, playlists and title fixes (engage.py).
Uploads keep using the original sign-in (the YT_REFRESH_TOKEN secret); this one is stored encrypted in tokens/youtube.enc.

  python pipeline/yt_connect.py link       writes the sign-in link to status/youtube_connect.json (the client id is public)
  python pipeline/yt_connect.py exchange   swaps the code Charlie pasted (YT_CODE: the code, or the whole address) for a
                                           refresh token and saves it; the result goes to status/youtube_connect.json
"""
import datetime as dt, json, os, pathlib, sys, urllib.parse
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import social

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl", "https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly"]
REDIRECT = "https://quickplay-studio.github.io/quickplay-autopilot/youtube-callback.html"   # must be an authorised redirect URI
# on the OAuth client (Google Cloud, Clients); the page shows the one-time code to paste into the social workflow
OUT = ROOT / "status" / "youtube_connect.json"

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def write(d):
    """Writes the status, keeping the last code swap's result (so an error isn't wiped by the hourly link refresh)."""
    OUT.parent.mkdir(exist_ok=True)
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if "last_exchange" not in d and old.get("last_exchange"): d["last_exchange"] = old["last_exchange"]
    if {k: v for k, v in old.items() if k != "at"} != d:
        OUT.write_text(json.dumps({"at": now(), **d}, indent=1, ensure_ascii=False))

def connected(t):
    d = {"ok": True, "connected": True, "scopes": t.get("scope"), "saved": t.get("saved")}
    if t.get("expires_at"):         # Google only sets an expiry while the app is in Testing
        d["expires_at"] = t["expires_at"]
        d["warning"] = "Google app is in Testing, so this sign-in expires after 7 days: publish the app (Audience, Publish app) and sign in again"
    return d

def link():
    t = social.load("youtube")
    if t.get("refresh_token"):
        write(connected(t)); return
    q = {"client_id": os.environ["YT_CLIENT_ID"], "redirect_uri": REDIRECT, "response_type": "code", "scope": " ".join(SCOPES),
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": "quickplay"}
    write({"ok": False, "connected": False, "connect_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)})

def exchange():
    raw = os.environ.get("YT_CODE", "").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [raw])[0] if "code=" in raw else raw
    resp = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
    try: r = resp.json()
    except ValueError: r = {"error": f"HTTP {resp.status_code}", "error_description": resp.text[:200]}
    if not r.get("refresh_token"):
        res = {"at": now(), "ok": False, "http": resp.status_code, "error": r.get("error") or "no refresh token in the reply",
               "description": str(r.get("error_description", ""))[:300], "code_chars": len(code)}
        print("YouTube sign-in failed:", json.dumps(res))
        write({"ok": False, "connected": False, "last_exchange": res}); return
    tok = {"refresh_token": r["refresh_token"], "scope": r.get("scope"), "saved": now()}
    if r.get("refresh_token_expires_in"):
        tok["expires_at"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(r["refresh_token_expires_in"]))).isoformat(timespec="minutes")
    social.save("youtube", tok)
    print("YouTube sign-in saved; scopes:", r.get("scope"), "; expires:", tok.get("expires_at", "no"))
    write({**connected(tok), "last_exchange": {"at": tok["saved"], "ok": True}})

if __name__ == "__main__":
    {"link": link, "exchange": exchange}[sys.argv[1]]()
