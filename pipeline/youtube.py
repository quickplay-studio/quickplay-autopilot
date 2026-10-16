"""YouTube Data API helpers: sign in from GitHub secrets, list what's scheduled, upload."""
import datetime as dt, os, time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
CATEGORY = {"Gaming": "20", "Film": "1", "Music": "10", "Sport": "17", "Tech": "28", "Science": "28",
            "Entertainment": "24", "News": "25", "Education": "27"}

class LimitReached(Exception): pass

def available():
    return all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))

def creds():
    return Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                       client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"], scopes=SCOPES)

def client():
    return build("youtube", "v3", credentials=creds(), cache_discovery=False)

def recent_videos(yt, limit=100):
    """[{id, title, uploaded (UTC), publish_at (UTC or None), privacy}] newest first."""
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
        for v in yt.videos().list(part="status,snippet", id=",".join(ids)).execute()["items"]:
            out.append({"id": v["id"], "title": v["snippet"]["title"], "uploaded": up.get(v["id"]),
                        "publish_at": v["status"].get("publishAt"), "privacy": v["status"]["privacyStatus"]})
    return out

def upload(yt, path, title, description, tags, category="Entertainment", publish_at=None):
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}
    if publish_at: status["publishAt"] = publish_at
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:15],
                        "categoryId": CATEGORY.get(category, "24"), "defaultLanguage": "en-GB", "defaultAudioLanguage": "en-GB"},
            "status": status}
    req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(path), chunksize=8 << 20, resumable=True))
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

def utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
