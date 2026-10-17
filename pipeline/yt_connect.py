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
REDIRECT = "http://localhost"     # Desktop-app sign-in: the browser lands on an address that holds the code
OUT = ROOT / "status" / "youtube_connect.json"

def write(d):
    OUT.parent.mkdir(exist_ok=True)
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if {k: v for k, v in old.items() if k != "at"} != {k: v for k, v in d.items() if k != "at"}:
        OUT.write_text(json.dumps(d, indent=1, ensure_ascii=False))

def link():
    if social.load("youtube").get("refresh_token"):
        write({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ok": True, "connected": True}); return
    q = {"client_id": os.environ["YT_CLIENT_ID"], "redirect_uri": REDIRECT, "response_type": "code", "scope": " ".join(SCOPES),
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": "quickplay"}
    write({"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "ok": False, "connected": False,
           "connect_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)})

def exchange():
    raw = os.environ.get("YT_CODE", "").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [raw])[0] if "code=" in raw else raw
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}).json()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not r.get("refresh_token"):
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps({"at": now, "ok": False, "error": r.get("error"),
                                   "description": str(r.get("error_description", ""))[:300]}, indent=1)); return
    social.save("youtube", {"refresh_token": r["refresh_token"], "scope": r.get("scope"), "saved": now})
    OUT.write_text(json.dumps({"at": now, "ok": True, "connected": True, "scopes": r.get("scope")}, indent=1))

if __name__ == "__main__":
    {"link": link, "exchange": exchange}[sys.argv[1]]()
