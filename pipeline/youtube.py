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
            "Entertainment": "24", "News": "25", "Education": "27", "Animals": "15", "Food": "26", "Cars": "2", "History": "27"}

class LimitReached(Exception): pass

MANAGE = "https://www.googleapis.com/auth/youtube.force-ssl"     # change videos, comment: in the second sign-in

def _newer_signin(full=False):
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
    return t if full else t["refresh_token"]

def available():
    return bool(os.environ.get("YT_CLIENT_ID") and os.environ.get("YT_CLIENT_SECRET")
                and (os.environ.get("YT_REFRESH_TOKEN") or _newer_signin()))

def creds():
    make = lambda rt, sc=SCOPES: Credentials(None, refresh_token=rt, token_uri="https://oauth2.googleapis.com/token", scopes=sc,
                                             client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"])
    t = _newer_signin(full=True) or {}
    newer, original = t.get("refresh_token"), os.environ.get("YT_REFRESH_TOKEN")
    if newer and newer != original:
        c = make(newer, SCOPES + ([MANAGE] if MANAGE in (t.get("scope") or "").split() else []))
        try:
            from google.auth.transport.requests import Request
            c.refresh(Request()); return c
        except Exception as ex:
            print(f"newer YouTube sign-in failed ({type(ex).__name__}), using the original", file=sys.stderr)
    return make(original)

def client():
    return build("youtube", "v3", credentials=creds(), cache_discovery=False)


# ---- the Daily line's other channels (25 October): music, es (config.json shorts_channels) ----
# Each has its own sign-in, tokens/youtube_<channel>.enc, made by yt_connect.py (the social workflow with the channel's name).
# Nothing about a channel runs until that file exists.
ROOT = pathlib.Path(__file__).resolve().parent.parent


def connected(channel="main"):
    """Whether Shorts can go to this channel at all. main: always (its sign-in is the original secret, checked by available()).
    Any other channel: only once Charlie has made it in YouTube Studio and signed it in, which is the encrypted file the
    social workflow saves. The file is looked for, not opened, so the writer and the tests can ask without the sign-in key."""
    if not channel or channel == "main": return True
    try:
        f = ROOT / "tokens" / f"youtube_{channel}.enc"
        return f.is_file() and f.stat().st_size > 0
    except OSError: return False


def creds_for(channel="main"):
    """The credentials of one channel: main's as ever (creds()), another channel's from its own saved sign-in (the same
    Google client, so the 10,000 units and the 100 uploads a day are shared). RuntimeError when it is not signed in."""
    if not channel or channel == "main": return creds()
    import social
    t = social.load(f"youtube_{channel}")
    if not t.get("refresh_token"): raise RuntimeError(f"the {channel} channel is not signed in (social workflow, channel {channel})")
    return Credentials(None, refresh_token=t["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
                       client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                       scopes=(t.get("scope") or "").split())


def client_for(channel="main"):
    """A YouTube client for a channel of the line: client() for main, else a client from the channel's own sign-in."""
    if not channel or channel == "main": return client()
    return build("youtube", "v3", credentials=creds_for(channel), cache_discovery=False)

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

def upload(yt, path, title, description, tags, category="Entertainment", publish_at=None, localizations=None, paid=False, language=None):
    """Uploads as private (scheduled when publish_at is given). localizations ({lang: {title, description}}) let the Short
    be found in searches in other languages; if YouTube refuses them, the upload is retried without. `language`: the
    video's own language when it is not British English (the Spanish channel: "es")."""
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}
    if publish_at: status["publishAt"] = publish_at
    body = {"snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:15],
                        "categoryId": CATEGORY.get(category, "24"),
                        "defaultLanguage": language or "en-GB", "defaultAudioLanguage": language or "en-GB"},
            "status": status}
    if localizations: body["localizations"] = localizations
    if paid: body["paidProductPlacementDetails"] = {"hasPaidProductPlacement": True}     # paid promotion (campaign clips)
    path = named_copy(path, title)
    try:
        vid = _send(yt, path, body)
    except HttpError as e:
        if e.resp.status != 400 or not (localizations or paid): raise
        print("upload: YouTube refused part of the details, uploading with the core ones:", str(e)[:200])
        body.pop("localizations", None)
        if body.pop("paidProductPlacementDetails", None): body["snippet"]["description"] = body["snippet"]["description"][:4900]
        vid = _send(yt, path, body)
    _quota("upload")
    return vid


def named_copy(path, title):
    """The video under a file name made of its title's words ("why-is-minecraft-still-everywhere.mp4"): YouTube reads
    the uploaded file's name, so it should describe the video, not say "video.mp4" (23 October, from Charlie's upload
    checklist video). A hard link, so nothing is copied; the original path when that fails."""
    import os, pathlib, re, tempfile
    slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")[:70] or "video"
    p = pathlib.Path(path)
    named = pathlib.Path(tempfile.mkdtemp(prefix="qp-up-")) / f"{slug}{p.suffix or '.mp4'}"
    try: os.link(p, named); return named
    except Exception:
        try:
            import shutil; shutil.copyfile(p, named); return named
        except Exception: return p


def _quota(event):
    """Tells the allowance guard (quota.py) about an upload, a refusal for quota (only uploads stop), or an upload the
    channel's own limit refused (still a call in the day's 100-upload bucket, which all four channels share)."""
    try:
        import quota
        if event == "exhausted": quota.exhausted("upload")
        elif event == "refused":
            if quota.MODE == "buckets": quota.spend(quota.COST["upload"], "upload refused")
        else: quota.spend(quota.COST["upload"], "upload")
    except Exception as e:
        print("quota record:", str(e)[:120])


def _send(yt, path, body):
    part = "snippet,status" + (",localizations" if body.get("localizations") else "") + (
        ",paidProductPlacementDetails" if body.get("paidProductPlacementDetails") else "")
    req = yt.videos().insert(part=part, body=body, media_body=MediaFileUpload(str(path), chunksize=8 << 20, resumable=True))
    resp, tries = None, 0
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except HttpError as e:
            reason = str(e)
            if "quotaExceeded" in reason: _quota("exhausted")
            if "uploadLimitExceeded" in reason: _quota("refused")
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
