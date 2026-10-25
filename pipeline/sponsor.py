"""Sponsored Shorts (Charlie, 25 October): campaigns that pay per 1,000 views for Shorts that carry a sound or a brand hashtag,
paid on Quickplay Daily's own views. No footage is needed and no Partner Programme either (Daily does about 1,300 views a day).

A campaign with "daily": true in clips/campaigns.json is one of them. It has no "source" and no "rules", so the clips line
(clips.campaigns()) never makes clips for it. Its entry:
  daily true, active true, name, card (as the site lists it), platform ("Content Rewards" or "Vyro"), url (the campaign page),
  pay_per_1k, min_views, max_payout, ends (YYYY-MM-DD, the last day it counts), subject, hashtags ["#Brand", ...],
  sound_url (an https link to the sound file the campaign provides for use, optional), sound_title and sound_artist (optional,
  for the description's Music line), submit {"where": "the add-clips page"} when Vyro.

While one is active, config daily_sponsor_share (0.3) of the Shorts carry it, drawn by board id (a series by its first part):
  writer.py        records test.sponsor on the board: the campaign id or "none" (drivers.py measures it like any test field)
  run_board.py     fetches the sound and mixes it as the music track (render3.py, the same gain), starts the description with
                   "#ad" and the campaign hashtags, writes upload.json "paid": true, keeps status "sponsor"
  upload.py, publish.py   pass paid promotion to YouTube; social.py puts #ad and the hashtags on the cross-posts' captions
  python pipeline/sponsor.py rows     (hourly, engage.yml) a clips/submit.csv row for each carrier that is uploaded and scheduled
                   (platform youtube, channel daily): the Mac's Vyro job or GitHub's Content Rewards job submits it as clips are
Dormant: with no active daily campaign nothing here changes a board, a render, an upload or a caption.
Standard library only (requests is imported when a sound is fetched), so it runs in the engage job as it is.
"""
import csv, datetime as dt, hashlib, json, os, pathlib, re, subprocess, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
CHANNEL = "daily"                      # the submit rows' channel column: the Mac picks this social account on the site
SUBMIT_FIELDS = ["clip", "campaign", "campaign_url", "platform", "video", "public_at_uk", "title", "hashtags", "submitted", "channel"]
GENERIC = {"#shorts", "#fyp", "#foryou", "#foryoupage", "#viral", "#trending", "#ad", "#sponsored", "#paid", "#youtubeshorts", "#shortsvideo"}
MAX_SOUND_MB = 25
# a story that is sad or serious is not the place for a brand's sound or an advert (the board keeps its arm "none")
SOMBRE = re.compile(r"\b(dies|died|dead|death|deaths|killed|killing|murder\w*|funeral|tribute|memorial|tragedy|tragic|obituary|"
                    r"passed away|lost (?:his|her|their) life|crash(?:ed|es)?|disaster|attack(?:ed|s)?|shooting|war|cancer|"
                    r"illness|diagnos\w+|suicide|abuse|assault|missing child|bereave\w+)\b", re.I)


def load(path, default):
    try: return json.loads(pathlib.Path(path).read_text())
    except Exception: return default


def uk_now(now=None):
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(UK)


# ---------- which campaigns, which Shorts ----------
def active(now=None, camps=None, root=None):
    """{id: campaign} of the daily campaigns live today: "daily" and "active" true, not past "ends" (that day still counts),
    with something to carry (a sound link or hashtags)."""
    if camps is None: camps = (load((root or ROOT) / "clips" / "campaigns.json", {}) or {}).get("campaigns") or {}
    today = uk_now(now).date().isoformat()
    out = {}
    for cid, c in camps.items():
        if not isinstance(c, dict) or not c.get("daily") or not c.get("active") or c.get("why_off"): continue
        if c.get("ends") and today > str(c["ends"]): continue
        if not (c.get("sound_url") or hashtags(c)): continue
        out[cid] = c
    return out


def share(cfg=None, root=None):
    """The share of Shorts that carry a campaign while one is live (config daily_sponsor_share, 0.3)."""
    if cfg is None: cfg = load((root or ROOT) / "config.json", {}) or {}
    try: return min(1.0, max(0.0, float(cfg.get("daily_sponsor_share", 0.3))))
    except (TypeError, ValueError): return 0.3


def draw(sid):
    """Two numbers fixed by the board id: where it falls in the share (0 to 1) and which campaign it takes."""
    h = hashlib.sha256(f"sponsor:{sid}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2 ** 32, int.from_bytes(h[4:8], "big")


def pick(sid, cs=None, frac=None):
    """The campaign id a board carries, "none" for the rest, None while no campaign is live (the board is left alone)."""
    cs = active() if cs is None else cs
    if not cs: return None
    frac = share() if frac is None else frac
    u, k = draw(sid)
    return sorted(cs)[k % len(cs)] if u < frac else "none"


def sombre(b):
    """A sad or serious story: it never carries a campaign."""
    m = (b or {}).get("meta") or {}
    beats = (b or {}).get("beats") or []
    text = " ".join([str(m.get("title", "")), str(m.get("summary", "")), str((beats[0] if beats else {}).get("say", ""))])
    return bool(SOMBRE.search(text))


def carrier(sb, camps=None, now=None):
    """(id, campaign) when the board's test.sponsor names a campaign that is still live, else (None, None)."""
    cid = str(((sb or {}).get("test") or {}).get("sponsor") or "")
    if not cid or cid == "none": return None, None
    c = active(now, camps).get(cid)
    return (cid, c) if c else (None, None)


# ---------- what the Short carries ----------
def hashtags(c):
    """The campaign's hashtags as "#Tag", unique, without the generic ones (#ad is added on its own), at most 8."""
    out, seen = [], set()
    for h in (c or {}).get("hashtags") or []:
        h = "#" + re.sub(r"[^\w]", "", str(h)).lstrip("#") if str(h).strip() else ""
        if len(h) < 2 or h.lower() in seen or h.lower() in GENERIC: continue
        seen.add(h.lower()); out.append(h)
    return out[:8]


def label(c):
    """The campaign as the site names it, short enough for a description."""
    t = re.sub(r"\s*\([^)]*\)\s*$", "", str((c or {}).get("card") or (c or {}).get("name") or "a campaign")).strip()
    return (t[:77] + "...") if len(t) > 80 else t


def ad_line(c):
    """The first line of a sponsored Short's description (UK advertising rules: #ad up front)."""
    return f"#ad Paid promotion: we are paid per view by this campaign: {label(c)}."


def with_hashtags(meta, c):
    """The board's meta with #ad and the campaign's hashtags first (YouTube shows the first three above the title)."""
    meta = dict(meta or {})
    head = ["#ad"] + hashtags(c)
    seen = {h.lower() for h in head}
    meta["hashtags"] = head + [h for h in meta.get("hashtags") or [] if str(h).lower() not in seen]
    return meta


def track(c):
    """The sound as the description's Music line names it."""
    return {"title": str(c.get("sound_title") or label(c)), "artist": str(c.get("sound_artist") or c.get("subject") or "the campaign"),
            "source": "supplied by the campaign"}


def applied(st):
    """The Short's status says it carries a campaign (run_board.py wrote status "sponsor" with applied true)."""
    s = (st or {}).get("sponsor")
    return isinstance(s, dict) and bool(s.get("applied"))


def caption_board(st, board):
    """The board with the campaign's first two hashtags leading meta.hashtags, so a platform's own hashtag cap (Instagram 5,
    Facebook 3) trims the board's tags and keeps the campaign's."""
    if not applied(st): return board
    lead = [str(h) for h in st["sponsor"].get("hashtags") or []][:2]
    low = {h.lower() for h in lead}
    b = dict(board or {}); m = dict(b.get("meta") or {})
    m["hashtags"] = lead + [h for h in m.get("hashtags") or [] if str(h).lower() not in low]
    b["meta"] = m
    return b


def caption(st, text):
    """A sponsored Short's cross-post caption (Instagram, Facebook, TikTok) starts with #ad, up front where it is seen (UK
    advertising rules); the campaign's hashtags come from caption_board."""
    return "#ad " + str(text).lstrip() if applied(st) else text


# ---------- the sound ----------
def direct_url(url):
    """A share link as a direct download: Google Drive and Dropbox links; any other https link as it is."""
    u = str(url).strip()
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", u) or re.search(r"drive\.google\.com/(?:open|uc)\?[^#]*\bid=([\w-]+)", u)
    if m: return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if "dropbox.com" in u:
        return re.sub(r"([?&])dl=0", r"\1dl=1", u) if "dl=" in u else u + ("&" if "?" in u else "?") + "dl=1"
    return u


def duration(path):
    """Seconds of audio in a file (ffprobe), 0.0 for a file with no audio, None when ffprobe is not there."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "format=duration:stream=codec_type",
                            "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
        j = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError): return None
    if not j.get("streams"): return 0.0
    try: return float((j.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError): return 0.0


def _get(url, timeout=90):
    import requests
    return requests.get(url, timeout=timeout, headers={"User-Agent": "QuickplayDaily/1.0 (quickplay-studio@users.noreply.github.com)"})


def fetch_sound(c, dest_dir, sid, get=None):
    """Downloads the campaign's sound (sound_url) to dest_dir/<sid>.sound. Returns (path, "") or (None, why): the Short is then
    made without the campaign, because a sound campaign needs its sound in the Short."""
    url = str(c.get("sound_url") or "").strip()
    if not url.lower().startswith("https://"): return None, "sound_url is not an https link"
    try: r = (get or _get)(direct_url(url), timeout=90)
    except Exception as e: return None, f"download failed: {type(e).__name__}: {str(e)[:80]}"
    if getattr(r, "status_code", 200) != 200: return None, f"the link answered {r.status_code}"
    data = r.content or b""
    ctype = str((getattr(r, "headers", None) or {}).get("content-type", "")).lower()
    if ctype.startswith("text/html") or data[:15].lower().startswith((b"<!doctype html", b"<html")):
        return None, "the link gave a web page, not a sound file (a share page?)"
    if len(data) < 5_000: return None, "the file is too small to be a sound"
    if len(data) > MAX_SOUND_MB * 1_000_000: return None, f"the file is over {MAX_SOUND_MB} MB"
    dest_dir = pathlib.Path(dest_dir); dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{sid}.sound"
    path.write_bytes(data)
    secs = duration(path)
    if secs is not None and secs < 3:
        path.unlink(missing_ok=True)
        return None, "no sound in the file" if not secs else f"only {secs:.1f} seconds of sound"
    return path, ""


# ---------- submission rows ----------
def utc(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError: return None


def rows(root=None, now=None, write=True):
    """One clips/submit.csv row for each sponsored Short that is uploaded and scheduled (status "sponsor" applied, a video and a
    publish time) and not yet there: platform youtube, channel daily, public_at_uk the slot in UK time. submit.py (Content
    Rewards, from GitHub) and the Mac's Vyro job (mac_rows.py) take it from there once it is public. Returns the new rows."""
    root = pathlib.Path(root or ROOT)
    now = now or dt.datetime.now(dt.timezone.utc)
    camps = (load(root / "clips" / "campaigns.json", {}) or {}).get("campaigns") or {}
    sp = root / "clips" / "submit.csv"
    old = []
    if sp.exists():
        with sp.open() as f: old = list(csv.DictReader(f))
    have = {(r.get("clip"), r.get("platform") or "youtube") for r in old}
    new = []
    for p in sorted((root / "status").glob("QD-*.json")):
        st = load(p, {})
        s = st.get("sponsor") if isinstance(st, dict) else None
        if not (isinstance(s, dict) and s.get("applied") and st.get("video") and st.get("publish_at") and st.get("id")): continue
        c = camps.get(s.get("campaign")) or {}
        t = utc(st["publish_at"])
        if not c.get("active") or t is None or (st["id"], "youtube") in have: continue
        if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
        if now - t > dt.timedelta(days=3): continue                       # long gone: nothing to submit
        where = re.search(r"https://[^\s,]+", str((c.get("submit") or {}).get("where", "")))
        new.append({"clip": st["id"], "campaign": s["campaign"], "campaign_url": where.group(0) if where else c.get("url", ""),
                    "platform": "youtube", "video": st.get("url") or f"https://youtube.com/shorts/{st['video']}",
                    "public_at_uk": t.astimezone(UK).strftime("%Y-%m-%d %H:%M"), "title": str(st.get("title") or "")[:100],
                    "hashtags": " ".join(hashtags(c)), "submitted": "", "channel": CHANNEL})
    if new and write:
        for r in old: r.setdefault("platform", "youtube")
        fields = list(SUBMIT_FIELDS)
        if sp.exists():                                    # keep the file's own columns (clips.SUBMIT_FIELDS), then any of ours it lacks
            with sp.open() as f: head = [h for h in next(csv.reader(f), []) if h]
            fields = head + [h for h in SUBMIT_FIELDS if h not in head]
        sp.parent.mkdir(parents=True, exist_ok=True)
        with sp.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
            w.writerows([{k: r.get(k, "") for k in fields} for r in old + new])
    return new


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "rows":
        new = rows()
        print(f"sponsor: {len(new)} submission row(s) added" + (": " + ", ".join(r["clip"] for r in new) if new else ""))
    else:
        cs = active()
        print(f"sponsor: {len(cs)} daily campaign(s) live, {share():.0%} of Shorts carry one" + ("; " + ", ".join(sorted(cs)) if cs else " (dormant)"))


if __name__ == "__main__":
    main(sys.argv[1:])
