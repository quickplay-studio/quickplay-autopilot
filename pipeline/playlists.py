"""One YouTube playlist per series, and every uploaded Short of the series added to it (Charlie, 25 October 2026).

usage: engage.py calls run(yt) after its comments (engage.yml, hourly at :50), with the second YouTube sign-in
(yt_connect.py, youtube.force-ssl, which playlist calls need) as `yt`.

- ensure(): the series' playlist, created the first time a Short of the series needs it (playlists.insert, 50 units, public)
  and kept in status/playlists.json (engage.yml's Save step commits status/). A playlist with the same title that already
  exists is reused, so a run that died between the insert and the save never makes a second one. config.json "series"
  entries may carry a "playlist" id of their own, which wins.
- add(): playlistItems.insert (50 units). Every call goes through quota.allow first and quota.spend after, like the
  comments and the category playlists, so the Shorts' own allowance is never touched; a refused call just waits for
  the next run.
- run(): for each public Short (a video id in status/<id>.json whose publish_at has passed) whose board is in a series,
  oldest series number first so the playlist order is the numbering: the playlist, the add, and (once, for a Short rendered
  before its playlist existed) a line in the video's description linking it when the render missed it (videos.list, then
  videos.update, 50 units). Recorded in the status file under engage.series_playlist, so nothing is added twice; a passing
  YouTube error gets up to 3 tries, one per run.
- url_for(): the playlist's link for the creator comment (engage.py), creating the playlist when it is missing.

Shorts are added once public, like engage.py's category playlists: a private Short in a public playlist shows viewers a
"[Private video]" row. The Short's description names the series and the link when the playlist already existed at render
time (run_board.description); otherwise the link is added here.
"""
import datetime as dt, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import series as SER

COST = 50                    # playlists.insert, playlistItems.insert and videos.update are 50 units each
PER_RUN = 12                 # adds a run (50 units each), the rest wait for the next hour
TRANSIENT = re.compile(r"HttpError (409|500|502|503|504) |aborted|backendError|[Tt]imeout|timed out|[Cc]onnection")
STATE = SER.PLAYLISTS


def load(path=None):
    try: d = json.loads(pathlib.Path(path or STATE).read_text())
    except Exception: d = {}
    if not isinstance(d, dict): d = {}
    d.setdefault("playlists", {})
    return d


def save(d, path=None):
    p = pathlib.Path(path or STATE)
    p.parent.mkdir(parents=True, exist_ok=True)
    d["updated"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False))


def spec_for(b, cfg=None, playbooks=None):
    """{"key", "title", "description", "kind"} of the playlist a board's series needs, or None for a Short in no series.
    `playbooks`: status/playbooks.json (its plan names an event's playlist)."""
    key = b.get("series_key") or b.get("series_name")
    if not key or not b.get("series_no"): return None
    if b.get("series_kind") == "playbook":
        plan = SER.plan_of(key, playbooks) or {}
        return {"key": key, "kind": "playbook", "title": plan.get("playlist_title") or f"{key} | Quickplay Daily",
                "description": f"{plan.get('about') or key} New Shorts every day from Quickplay Daily."}
    for spec in SER.registry(cfg).values():
        if spec["name"] == key:
            return {"key": key, "kind": "evergreen", "title": SER.playlist_title(spec),
                    "description": f"{spec.get('about') or key} New Shorts every day from Quickplay Daily."}
    return None


def mine(yt):
    """{title: id} of the channel's own playlists (1 unit a page)."""
    out, tok = {}, None
    while True:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=tok).execute()
        out.update({p["snippet"]["title"]: p["id"] for p in r.get("items", [])})
        tok = r.get("nextPageToken")
        if not tok: return out


def ensure(yt, spec, path=None, cfg=None):
    """The playlist id for a series, creating the playlist when there is none and the allowance has room ("" otherwise)."""
    pid = SER.playlist_id(spec["key"], cfg, path or STATE)
    if pid: return pid
    import quota
    if not quota.allow(COST, "series playlist"): return ""
    pid = mine(yt).get(spec["title"]) or ""
    if not pid:
        r = yt.playlists().insert(part="snippet,status", body={"snippet": {"title": spec["title"], "description": spec["description"][:5000],
                                  "defaultLanguage": "en-GB"}, "status": {"privacyStatus": "public"}}).execute()
        pid = r["id"]
        quota.spend(COST, "series playlist")
    d = load(path)
    d["playlists"][spec["key"]] = {"id": pid, "title": spec["title"], "kind": spec["kind"],
                                   "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")}
    save(d, path)
    print(f"series playlist: {spec['title']}: {pid}")
    return pid


def url_for(yt, b, path=None, cfg=None, playbooks=None):
    """The playlist link for a Short's creator comment ("" when the Short is in no series or the playlist can't be made yet).
    `path`: status/playlists.json."""
    spec = spec_for(b, cfg, playbooks)
    if not spec: return ""
    pid = ensure(yt, spec, path, cfg)
    return f"https://www.youtube.com/playlist?list={pid}" if pid else ""


def add(yt, pid, video, check=False):
    """playlistItems.insert; with `check` (a retry: an "aborted" insert may have gone through) never adds a Short twice."""
    if check and yt.playlistItems().list(part="id", playlistId=pid, videoId=video).execute().get("items"): return "present"
    yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid, "resourceId": {"kind": "youtube#video", "videoId": video}}}).execute()
    return "added"


def link_description(yt, video, url, label):
    """Adds "More in the series: <url>" to a video's description (a Short rendered before its playlist existed)."""
    v = yt.videos().list(part="snippet", id=video).execute()["items"][0]["snippet"]
    if url in str(v.get("description") or ""): return False
    body = {"id": video, "snippet": {k: v[k] for k in ("title", "description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage") if k in v}}
    line = f"{label}. More in the series: {url}"
    body["snippet"]["description"] = (str(v.get("description") or "").rstrip() + "\n\n" + line)[:4900]
    yt.videos().update(part="snippet", body=body).execute()
    return True


def board_of(sid, root=None):
    for d in ("done", "ready", "queue", "hold"):
        p = pathlib.Path(root or ROOT) / "boards" / d / f"{sid}.json"
        if p.exists():
            try: return json.loads(p.read_text())
            except Exception: return None
    return None


def tries(e, key):
    """Tries so far, or None when no more should be made (a passing error gets 3 tries, any other error is final)."""
    err = str(e.get(f"{key}_error") or "")
    if not err: return 0
    n = e.get(f"{key}_tries", 1)
    return n if n < 3 and TRANSIENT.search(err) else None


def public(st, now=None):
    """True once a Short's scheduled time has passed (status publish_at; a private Short has none): a private video in a public
    playlist shows viewers a "[Private video]" row, so none is added before it is public (engage.py's category playlists wait too)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    try: return dt.datetime.fromisoformat(str(st.get("publish_at") or "").replace("Z", "+00:00")) <= now
    except (TypeError, ValueError): return False


def waiting(root=None, now=None):
    """[(status path, status, board)] for the public Shorts of a series with no playlist add recorded yet, in series order."""
    root = pathlib.Path(root or ROOT)
    out = []
    for sp in sorted((root / "status").glob("QD-*.json")):
        try: st = json.loads(sp.read_text())
        except Exception: continue
        if not isinstance(st, dict) or not st.get("video") or (st.get("engage") or {}).get("series_playlist") or not public(st, now): continue
        b = board_of(st.get("id"), root)
        if b and b.get("series_name") and b.get("series_no"): out.append((sp, st, b))
    out.sort(key=lambda t: (str(t[2].get("series_key") or t[2].get("series_name")), int(t[2].get("series_no") or 0)))
    return out


def run(yt, root=None, path=None, cfg=None, limit=PER_RUN, now=None, playbooks=None):
    """Adds the waiting Shorts to their series' playlists. Returns how many were added. `path`: status/playlists.json,
    `playbooks`: status/playbooks.json (both default to the repo's; a test points them at a scratch folder)."""
    import quota
    added = 0
    for sp, st, b in waiting(root, now):
        if added >= limit: break
        e = st.setdefault("engage", {})
        n = tries(e, "series_playlist")
        if n is None: continue
        spec = spec_for(b, cfg, playbooks)
        if not spec: continue
        try:
            pid = ensure(yt, spec, path, cfg)
            if not pid: break                                   # no room in the allowance: the next run
            if not quota.allow(COST, "series playlist add"): break
            how = add(yt, pid, st["video"], check=n > 0)
            if how == "added": quota.spend(COST, "series playlist add")
            e["series_playlist"] = pid
            e.pop("series_playlist_error", None); e.pop("series_playlist_tries", None)
            added += how == "added"
            if not e.get("series_description") and quota.allow(COST, "series description"):      # once: a Short rendered before its playlist existed has no link
                try:
                    if link_description(yt, st["video"], f"https://www.youtube.com/playlist?list={pid}", SER.label(b)): quota.spend(COST, "series description")
                    e["series_description"] = "linked"
                except Exception as ex:           # the add stands; the description is not tried again
                    e["series_description"] = f"failed: {type(ex).__name__}"[:60]
        except Exception as ex:
            e["series_playlist_error"], e["series_playlist_tries"] = f"{type(ex).__name__}: {ex}"[:200], n + 1
        pathlib.Path(sp).write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(st.get("id"), "series playlist:", e.get("series_playlist") or e.get("series_playlist_error"))
    return added
