"""Engagement on our own public Shorts, using the second YouTube sign-in (yt_connect.py, youtube.force-ssl):
- a creator comment with the board's question (meta.comment) once the Short is public (YouTube's API can't pin comments)
- the Short added to its category playlist ("Quickplay Daily: Gaming" and so on, created when missing)
- 24 to 72 hours after going public, a Short getting under half the typical views an hour switches to its alternative
  title (meta.alt_title), once
Everything is recorded in status/<id>.json under "engage". usage: python pipeline/engage.py
"""
import datetime as dt, json, os, pathlib, re, statistics, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import social, yt_connect
import youtube as Y

PLAYLIST = "Quickplay Daily: {}"
ABOUT = {"Gaming": "Game news and reveals people are searching for today.", "Film": "Film news, trailers and releases.",
         "Music": "Music news: artists, records and tours.", "Sport": "Sport stories everyone is talking about.",
         "Tech": "Gadgets, apps and tech launches.", "Science": "Space and science stories in under a minute.",
         "Entertainment": "TV, anime, celebrities and pop culture."}

def client():
    t = social.load("youtube")
    if not t.get("refresh_token"): return None
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(None, refresh_token=t["refresh_token"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"], scopes=yt_connect.SCOPES)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)

TRANSIENT = re.compile(r"HttpError (409|500|502|503|504) |aborted|backendError|[Tt]imeout|timed out|[Cc]onnection")

def tries(e, key):
    """Tries so far, or None when no more should be made: a passing YouTube error (409 "The operation was aborted.",
    a 5xx, a timeout) gets up to 3 tries, one per run; any other error is final."""
    err = str(e.get(f"{key}_error") or "")
    if not err: return 0
    n = e.get(f"{key}_tries", 1)
    return n if n < 3 and TRANSIENT.search(err) else None

def my_playlists(yt):
    out, tok = {}, None
    while True:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=tok).execute()
        out.update({p["snippet"]["title"]: p["id"] for p in r.get("items", [])})
        tok = r.get("nextPageToken")
        if not tok: return out

def main():
    yt = client()
    if yt is None:
        print("no engagement sign-in yet (run the YouTube connect step)"); return
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for sp in sorted((ROOT / "status").glob("QD-*.json")):
        st = json.loads(sp.read_text())
        pub = Y.utc(st.get("publish_at"))
        if st.get("video") and pub and pub <= now: rows.append((sp, st, pub))
    if not rows:
        print("no public Shorts of ours yet"); return
    views = {}
    ids = [st["video"] for _, st, _ in rows]
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part="statistics", id=",".join(ids[i:i + 50])).execute().get("items", []):
            views[v["id"]] = int(v.get("statistics", {}).get("viewCount", 0))
    rates = [views.get(st["video"], 0) / max(1.0, (now - pub).total_seconds() / 3600) for _, st, pub in rows
             if (now - pub) >= dt.timedelta(hours=24)]
    typical = statistics.median(rates) if len(rates) >= 5 else None
    playlists = None
    for sp, st, pub in rows:
        b = social.board_for(st) or {}
        m, e, changed = b.get("meta", {}), st.setdefault("engage", {}), False
        if m.get("comment") and not e.get("comment") and not e.get("comment_error"):
            try:
                r = yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": st["video"], "topLevelComment": {
                    "snippet": {"textOriginal": str(m["comment"])[:500]}}}}).execute()
                e["comment"] = r["id"]
            except Exception as ex: e["comment_error"] = f"{type(ex).__name__}: {ex}"[:200]
            changed = True
        cat, n = b.get("category"), tries(e, "playlist")
        if cat and not e.get("playlist") and n is not None:
            try:
                if playlists is None: playlists = my_playlists(yt)
                title = PLAYLIST.format(cat)
                if title not in playlists:
                    p = yt.playlists().insert(part="snippet,status", body={"snippet": {"title": title, "description": ABOUT.get(cat, ""),
                        "defaultLanguage": "en-GB"}, "status": {"privacyStatus": "public"}}).execute()
                    playlists[title] = p["id"]
                # on a retry, an "aborted" insert may have gone through after all: never add the Short twice
                if not (n and yt.playlistItems().list(part="id", playlistId=playlists[title], videoId=st["video"]).execute().get("items")):
                    yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": playlists[title],
                        "resourceId": {"kind": "youtube#video", "videoId": st["video"]}}}).execute()
                e["playlist"] = title; e.pop("playlist_error", None); e.pop("playlist_tries", None)
            except Exception as ex: e["playlist_error"], e["playlist_tries"] = f"{type(ex).__name__}: {ex}"[:200], n + 1
            changed = True
        age = now - pub
        if m.get("alt_title") and typical and not e.get("title") and dt.timedelta(hours=24) <= age <= dt.timedelta(hours=72):
            rate = views.get(st["video"], 0) / max(1.0, age.total_seconds() / 3600)
            if rate < 0.5 * typical:
                try:
                    v = yt.videos().list(part="snippet", id=st["video"]).execute()["items"][0]["snippet"]
                    body = {"id": st["video"], "snippet": {k: v[k] for k in ("title", "description", "tags", "categoryId",
                                                                          "defaultLanguage", "defaultAudioLanguage") if k in v}}
                    old = body["snippet"]["title"]; body["snippet"]["title"] = str(m["alt_title"])[:100]
                    yt.videos().update(part="snippet", body=body).execute()
                    e["title"] = {"swapped_from": old, "to": body["snippet"]["title"], "at": now.isoformat(timespec="minutes"),
                                  "views_an_hour": round(rate, 1), "typical": round(typical, 1)}
                    st["title"] = body["snippet"]["title"]
                except Exception as ex: e["title"] = {"error": f"{type(ex).__name__}: {ex}"[:200]}
            else:
                e["title"] = {"kept": f"{rate:.1f} views an hour against a typical {typical:.1f}"}
            changed = True
        if changed:
            if not e: st.pop("engage", None)
            sp.write_text(json.dumps(st, indent=1, ensure_ascii=False)); print(st["id"], json.dumps(e)[:200])

if __name__ == "__main__":
    main()
