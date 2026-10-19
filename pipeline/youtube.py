"""YouTube Data API helpers: sign in from GitHub secrets, list what's scheduled, upload."""
import datetime as dt, os, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
CATEGORY = {"Gaming": "20", "Film": "1", "Music": "10", "Sport": "17", "Tech": "28", "Science": "28",
            "Entertainment": "24", "News": "25", "Education": "27"}

class LimitReached(Exception): pass

def _newer_signin():
    """The refresh token from the second sign-in (yt_connect.py, tokens/youtube.enc) when it covers SCOPES and isn't about
    to expire. It replaces the original YT_REFRESH_TOKEN, which dies after 7 days if it was made while the app was in Testing."""
    try:
        if not os.environ.get("SOCIAL_KEY"): return None
        import social
        t = social.load("youtube")
    except BaseException: return None
    if not t.get("refresh_token") or not all(s in (t.get("scope") or "").split() for s in SCOPES): return None
    if t.get("expires_at") and dt.datetime.fromisoformat(t["expires_at"]) < dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2):
        return None
    return t["refresh_token"]

def available():
    return bool(os.environ.get("YT_CLIENT_ID") and os.environ.get("YT_CLIENT_SECRET")
                and (os.environ.get("YT_REFRESH_TOKEN") or _newer_signin()))

def creds():
    make = lambda rt: Credentials(None, refresh_token=rt, token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES,
                                  client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"])
    newer, original = _newer_signin(), os.environ.get("YT_REFRESH_TOKEN")
    if newer and newer != original:
        c = make(newer)
        try:
            from google.auth.transport.requests import Request
            c.refresh(Request()); return c
        except Exception as ex:
            print(f"newer YouTube sign-in failed ({type(ex).__name__}), using the original", file=sys.stderr)
    return make(original)

def client():
    return build("youtube", "v3", credentials=creds(), cache_discovery=False)

def recent_videos(yt, limit=100):
    """[{id, title, uploaded (UTC), publish_at (UTC or None), privacy, views}] newest first."""
    pl = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items, tok = [], None
    while len(items) < limit:
        r = yt.playlistItems().list(part="snippet", playlistId=pl, maxResults=50, pageToken=tok).execute()
        items += r["items"]; tok = r.get("nextPageToken")
        if not tok: break
    out = []
    for i in range(0, len(items), 50):
        ids = [it["snippet"]["resourceId"]["videoId"] for it in items[i:i + 50]]
        up = {it["snippet"]["resourceId"]["videoId"]: it["snippet"]["publishedAt"] for it in items[i:i + 50]}
        for v in yt.videos().list(part="status,snippet,statistics", id=",".join(ids)).execute()["items"]:
            out.append({"id": v["id"], "title": v["snippet"]["title"], "uploaded": up.get(v["id"]),
                        "publish_at": v["status"].get("publishAt"), "privacy": v["status"]["privacyStatus"],
                        "views": int(v.get("statistics", {}).get("viewCount", 0))})
    return out

def upload(yt, path, title, description, tags, category="Entertainment", publish_at=None, localizations=None):
    """Uploads as private (scheduled when publish_at is given). localizations ({lang: {title, description}}) let the Short
    be found in searches in other languages; if YouTube refuses them, the upload is retried without."""
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}
    if publish_at: status["publishAt"] = publish_at
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:15],
                        "categoryId": CATEGORY.get(category, "24"), "defaultLanguage": "en-GB", "defaultAudioLanguage": "en-GB"},
            "status": status}
    if localizations: body["localizations"] = localizations
    try:
        return _send(yt, path, body)
    except HttpError as e:
        if not localizations or e.resp.status != 400: raise
        print("upload: YouTube refused the translated titles, uploading without them:", str(e)[:200])
        body.pop("localizations", None)
        return _send(yt, path, body)


def _send(yt, path, body):
    part = "snippet,status" + (",localizations" if body.get("localizations") else "")
    req = yt.videos().insert(part=part, body=body, media_body=MediaFileUpload(str(path), chunksize=8 << 20, resumable=True))
    resp, tries = None, 0
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except HttpError as e:
            reason = str(e)
            if "uploadLimitExceeded" in reason or "quotaExceeded" in reason: raise LimitReached(reason)
            if e.resp.status in (500, 502, 503, 504) and tries < 5:
                tries += 1; time.sleep(5 * tries); continue
            raise
    return resp["id"]

def video_status(yt, vid):
    """What YouTube kept after an upload: privacy and scheduled time (a missing publishAt means it won't go public)."""
    items = yt.videos().list(part="status", id=vid).execute().get("items", [])
    st = items[0]["status"] if items else {}
    return {"privacy": st.get("privacyStatus"), "publish_at": st.get("publishAt"), "upload_status": st.get("uploadStatus")}

def utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
