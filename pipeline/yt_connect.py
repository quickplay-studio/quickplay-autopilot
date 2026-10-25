"""A second YouTube sign-in with the youtube.force-ssl permission, for comments, playlists and title fixes (engage.py).
Uploads keep using the original sign-in (the YT_REFRESH_TOKEN secret); this one is stored encrypted in tokens/youtube.enc.

  python pipeline/yt_connect.py link       writes the sign-in link to status/youtube_connect.json (the client id is public)
  python pipeline/yt_connect.py exchange [main|pt|clips|music|es]   swaps the code Charlie pasted (YT_CODE: the code, or the whole address) for a
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
MAIN = "UC-75vkMtOxgFFkXwBNfBOeg"     # Quickplay Daily, the original channel
# The other channels, by the words in their YouTube titles (most specific first): the sign-in is saved under the matching
# name as tokens/youtube_<name>.enc. New niche channels (Charlie, 22 October) just need a title with their word in it.
TITLES = {"gaming": ("gaming",), "irl": ("irl", "creators"), "pt": ("portugu",), "clips": ("clips",),
          "music": ("music",), "es": ("diario", "español", "espanol")}     # music and es: the Daily line's extra channels (25 October)
CHANNELS = ("main",) + tuple(TITLES)

def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def write(d, out=OUT):
    """Writes the status, keeping the last code swap's result (so an error isn't wiped by the hourly link refresh)."""
    out.parent.mkdir(exist_ok=True)
    old = json.loads(out.read_text()) if out.exists() else {}
    if "last_exchange" not in d and old.get("last_exchange"): d["last_exchange"] = old["last_exchange"]
    if {k: v for k, v in old.items() if k != "at"} != d:
        out.write_text(json.dumps({"at": now(), **d}, indent=1, ensure_ascii=False))

def connected(t):
    d = {"ok": True, "connected": True, "scopes": t.get("scope"), "saved": t.get("saved")}
    if t.get("expires_at"):         # Google only sets an expiry while the app is in Testing
        d["expires_at"] = t["expires_at"]
        d["warning"] = "Google app is in Testing, so this sign-in expires after 7 days: publish the app (Audience, Publish app) and sign in again"
    return d

def link():
    """The sign-in link is always published (the client id is public): the same link signs in any channel of the account
    (main, pt, clips); Google asks which channel when the account has several. Each channel's status file says whether
    its own sign-in exists."""
    q = {"client_id": os.environ["YT_CLIENT_ID"], "redirect_uri": REDIRECT, "response_type": "code", "scope": " ".join(SCOPES),
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": "quickplay"}
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(q)
    t = social.load("youtube")
    write({**(connected(t) if t.get("refresh_token") else {"ok": False, "connected": False}), "connect_url": url})
    for ch in [c for c in CHANNELS if c != "main"]:
        out = OUT.with_name(f"youtube_connect_{ch}.json")
        tc = social.load(f"youtube_{ch}")
        if tc.get("refresh_token"): write({**connected(tc), "connect_url": url}, out)
        elif not out.exists(): write({"ok": False, "connected": False, "connect_url": url, "how": f"open connect_url while using the {ch} channel, "
                                     "copy the code, run the social workflow with it and channel " + ch}, out)

def exchange(ch="main"):
    """ch: main, the Portuguese channel (pt), the clips channels, or the Daily line's music and es (Spanish) channels, whose
    sign-in is saved as tokens/youtube_<ch>.enc."""
    name, out = ("youtube", OUT) if ch == "main" else (f"youtube_{ch}", OUT.with_name(f"youtube_connect_{ch}.json"))
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
        write({"ok": False, "connected": False, "last_exchange": res}, out); return
    tok = {"refresh_token": r["refresh_token"], "scope": r.get("scope"), "saved": now()}
    try:        # the channel Charlie picked (Google asks which one when the account has several)
        c = requests.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"}, timeout=30,
                         headers={"Authorization": f"Bearer {r.get('access_token')}"}).json()["items"][0]
        tok["channel"] = {"id": c["id"], "title": c["snippet"]["title"]}
    except Exception as e:
        tok["channel"] = {"error": str(e)[:150]}
    is_main = tok["channel"].get("id") == MAIN or tok["channel"].get("title") == "Quickplay Daily"
    title = str(tok["channel"].get("title") or "").lower()
    found = "main" if is_main else next((c for c, words in TITLES.items() if any(w in title for w in words)), None)
    if found and found != ch:         # the sign-in says which channel it is: saved under that name, whatever the dropdown said
        print(f"YouTube sign-in is for the {found} channel ({tok['channel'].get('title')}), not {ch}: saving it as {found}")
        ch = found
        name, out = ("youtube", OUT) if ch == "main" else (f"youtube_{ch}", OUT.with_name(f"youtube_connect_{ch}.json"))
    if is_main != (ch == "main"):     # one channel's sign-in never replaces another's
        res = {"at": now(), "ok": False, "error": f"this sign-in is for {tok['channel'].get('title') or 'an unknown channel'}, not the "
               f"{ch} channel: sign in again and pick the right channel"}
        print("YouTube sign-in refused:", json.dumps(res, ensure_ascii=False))
        write({"ok": False, "connected": False, "last_exchange": res}, out); return
    if r.get("refresh_token_expires_in"):
        tok["expires_at"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(r["refresh_token_expires_in"]))).isoformat(timespec="minutes")
    social.save(name, tok)
    print("YouTube sign-in saved; scopes:", r.get("scope"), "; expires:", tok.get("expires_at", "no"))
    write({**connected(tok), "channel": tok["channel"], "last_exchange": {"at": tok["saved"], "ok": True}}, out)

if __name__ == "__main__":
    {"link": link, "exchange": exchange}[sys.argv[1]](*sys.argv[2:3])
