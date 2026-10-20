"""The video behind every Short (Charlie, 19 October): 2 to 4 stock clips matched to the topic, softly blurred and darkened,
cross-fading under everything, with the photos of the subject sitting on top as cards (render3.py, template3.html).

How it flows
  board "background"   2 to 4 searches of 2 to 4 concrete words each, written by Gemini and checked by validate.py.
                       "nasa:earth from orbit" asks NASA's public-domain library instead. They are not shots, so they
                       never count towards the 1-in-5 stock limit.
  plan.py   -> pick()  one clip per search, chosen once per run with a shared `used` set, so no two Shorts in a run share
                       a clip and none came back within reuse_days (status/*.json "background"); handed to the render job.
  run_board -> fetch() downloads them (https, known hosts only), refuses anything under 720p or nearly black.
  render3   -> build() crops each to 9:16, blurs, darkens, cross-fades and writes JPEG frames the template plays.

Clips come from Pixabay (PIXABAY_API_KEY, a free key) and NASA; Pexels (PEXELS_API_KEY) is off in config.json since it
issues no new keys (Charlie, 21 October). A vertical clip is used as it is, any
other is cropped to the middle 9:16. With no key, or no clip found, the Short simply renders without a background (the
classic full-bleed look), so nothing waits on this layer.
Standard library at import time; requests, numpy and PIL load only inside the functions that need them.
"""
import datetime as dt, json, math, os, pathlib, re, subprocess, sys, urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
HOSTS = ("videos.pexels.com", "player.vimeo.com", "cdn.pixabay.com", "images-assets.nasa.gov")   # where a clip may come from
DASH = re.compile("[–—]")
WORD = re.compile(r"[^\W_][\w'-]*")
SEARCH = re.compile(r"(?:nasa:)?[^\W_][\w'-]*(?: [^\W_][\w'-]*){1,3}")      # what validate.py accepts: 2 to 4 plain words

DEFAULTS = {"enabled": False, "reuse_days": 7, "clip_seconds": [8, 15], "min_px": 720, "blur": 13, "target_luma": 0.27,
            "min_luma": 0.05, "max_gain": 2.0, "knee": 105, "fade": 0.6, "frame_w": 540, "frame_h": 960, "pexels": True, "pixabay": True, "nasa": True}

# used when a board lists fewer than 2 usable searches: the world of its category
FALLBACK = {
    "Gaming": ["neon gaming setup", "esports arena lights", "keyboard rgb glow"],
    "Film": ["cinema auditorium screen", "movie theatre seats", "film projector light"],
    "Music": ["concert stage lights", "crowd concert night", "dj mixer lights"],
    "Sport": ["football stadium night", "stadium crowd floodlights", "running track sunrise"],
    "Tech": ["circuit board closeup", "server room lights", "futuristic city night"],
    "Science": ["galaxy stars space", "nebula space clouds", "earth from orbit"],
    "Entertainment": ["red carpet lights", "city lights night", "theatre stage curtain"],
}

# ---------------- the board's searches ----------------
def settings(cfg):
    d = dict(DEFAULTS); d.update((cfg or {}).get("background") or {}); return d

def wanted(b, cfg):
    """A board's own bgvideo (true or false) wins; otherwise config.json background.enabled decides."""
    if isinstance(b.get("bgvideo"), bool): return b["bgvideo"]
    return bool(settings(cfg).get("enabled"))

def parse(q):
    """('nasa' or '', 'the words') for one search, or None when it is not a usable search (2 to 4 plain words)."""
    if not isinstance(q, str): return None
    s = DASH.sub(" ", q).strip()
    prov = ""
    if s.lower().startswith("nasa:"): prov, s = "nasa", s[5:].strip()
    if ":" in s: return None
    words = WORD.findall(s)
    if not 2 <= len(words) <= 4 or len(" ".join(words)) > 60: return None
    return prov, " ".join(words).lower()

def tidy(lst, keep=4):
    """The usable searches of a list as they are written back to a board: 'words' or 'nasa:words', no repeats, at most 4."""
    out, seen = [], set()
    for q in lst if isinstance(lst, list) else []:
        p = parse(q)
        if p is None or p[1] in seen: continue
        seen.add(p[1]); out.append(("nasa:" if p[0] else "") + p[1])
        if len(out) >= keep: break
    return out

def fallback(b):
    return list(FALLBACK.get((b or {}).get("category"), FALLBACK["Entertainment"]))

def fill(b):
    """Leave the board with 2 to 4 usable searches: its own, topped up from its category when it gave fewer than 2.
    Returns how many came from the category."""
    have = tidy(b.get("background")); added = 0
    if len(have) < 2:
        seen = {parse(q)[1] for q in have}
        for q in fallback(b):
            if len(have) >= 3: break
            if q not in seen: have.append(q); seen.add(q); added += 1
    b["background"] = have
    return added

# ---------------- what was used lately ----------------
def recent_used(root, days):
    """provider:id of every background clip rendered in the last `days` days (status/*.json "background")."""
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out = set()
    for f in pathlib.Path(root, "status").glob("*.json"):
        try:
            st = json.loads(f.read_text())
            when = dt.datetime.fromisoformat(str(st.get("rendered")).replace("Z", "+00:00"))
            if when.tzinfo is None: when = when.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        if when < cut: continue
        for c in st.get("background") or []:
            if isinstance(c, dict) and c.get("p") and c.get("id"): out.add(f"{c['p']}:{c['id']}")
    return out

# ---------------- searching ----------------
_cache = {}

def _words(s):
    return {w for w in re.findall(r"[a-z0-9]+", str(s).lower()) if len(w) > 2}

def _share(query, text):
    """Share of the query's words found in a clip's page name or tags."""
    want, have = _words(query), _words(text)
    have |= {h.rstrip("s") for h in have}
    return sum(w in have or w.rstrip("s") in have for w in want) / max(1, len(want))

def _score(c, query):
    share = _share(query, c.get("text", ""))
    d = c.get("d") or 0
    dur = 0.12 if 10 <= d <= 45 else 0.06 if d >= 8 else 0.0 if d >= 5 else -0.4
    return share + (0.2 if (c.get("h") or 0) > (c.get("w") or 1) else 0) + dur - c.get("rank", 0) * 0.01, share

def _strong(cands, query, min_share):
    """Clips whose name or tags hold enough of the query's words, best first."""
    keep = [(_score(c, query)[0], c) for c in cands if _score(c, query)[1] >= min_share]
    return [c for _, c in sorted(keep, key=lambda t: -t[0])]

def _weak(cands, query, min_share, top):
    """The provider's own first few results that fall short on words: a last resort when nothing matches better."""
    keep = [(_score(c, query)[0], c) for c in cands if _score(c, query)[1] < min_share and c.get("rank", 99) < top]
    return [c for _, c in sorted(keep, key=lambda t: -t[0])]

DEADLINE = 0        # plan.py sets a time (time.time() + seconds) after which no more searches are made
_dead = set()       # providers that refused us this run (a wrong key, or the rate limit): not asked again until the next run
NOTES = []          # what happened while one board's clips were picked: plan.py hands it to the render job, which writes it to
                    # status/<id>.json (the Actions logs cannot be read from outside, the status files can)

def note(msg):
    """Print a line about the search and keep it in NOTES. Never a key: any secret or key= in it is blanked first."""
    msg = re.sub(r"\s+", " ", str(msg)).strip()
    for env in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
        v = os.environ.get(env, "").strip()
        if len(v) > 6: msg = msg.replace(v, "***")
    msg = re.sub(r"(?i)\b(key|authorization)=[^&\s'\")]+", r"\1=***", msg)[:130]
    print(f"  background: {msg}", file=sys.stderr)
    if len(NOTES) < 16 and msg not in NOTES: NOTES.append(msg)

def _late():
    import time
    return bool(DEADLINE) and time.time() > DEADLINE

def _get(url, **kw):
    import requests
    if _late(): raise TimeoutError("the time allowed for background searches is used up")
    return requests.get(url, headers={**UA, **(kw.pop("headers", None) or {})}, timeout=20, **kw)

PEXELS_URLS = ("https://api.pexels.com/v1/videos/search", "https://api.pexels.com/videos/search")   # the documented path, then the older one

def pexels_search(words, st, orientation="portrait", page=1):
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key or not st.get("pexels", True) or "pexels" in _dead: return []
    ck = ("pexels", words, orientation, page)
    if ck not in _cache:
        out = []
        try:
            params = {"query": words, "orientation": orientation, "size": "small", "per_page": 40, "page": page}
            for url in PEXELS_URLS:
                r = _get(url, headers={"Authorization": key}, params=params)
                if r.status_code != 404: break
            if r.status_code != 200:
                bad = r.status_code in (401, 403, 429)
                note(f"Pexels answered {r.status_code} for '{words}'" + (" (not asking again this run" + ("; check the PEXELS_API_KEY secret)" if r.status_code != 429 else ")") if bad else ""))
                if bad: _dead.add("pexels")
            else:
                vids = r.json().get("videos") or []
                for rank, v in enumerate(vids):
                    files = [f for f in v.get("video_files") or [] if f.get("file_type") == "video/mp4" and f.get("link")
                             and min(f.get("width") or 0, f.get("height") or 0) >= st["min_px"]]
                    if not files: continue
                    f = min(files, key=lambda f: (f["width"] * f["height"], -(f.get("fps") or 0)))   # the smallest that is still 720p
                    pg = v.get("url") or ""
                    out.append({"p": "pexels", "id": str(v["id"]), "url": f["link"], "w": f["width"], "h": f["height"],
                                "d": v.get("duration") or 0, "by": (v.get("user") or {}).get("name") or "", "page": pg,
                                "text": pg.rstrip("/").rsplit("/", 1)[-1].replace("-", " "), "rank": rank})
                if not out: note(f"Pexels {orientation} '{words}': {len(vids)} results, none at 720p or better")
        except Exception as e:
            note(f"Pexels search '{words}' failed: {type(e).__name__}: {e}")
        _cache[ck] = out
    return _cache[ck]

def pixabay_search(words, st):
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key or not st.get("pixabay", True) or "pixabay" in _dead: return []
    ck = ("pixabay", words)
    if ck not in _cache:
        out = []
        try:
            from fetch_media import _junk           # green screens, AI pictures and animations look fake
            r = _get("https://pixabay.com/api/videos/", params={"key": key, "q": words[:100], "safesearch": "true", "per_page": 40})
            if r.status_code != 200:
                bad = r.status_code in (400, 401, 403, 429)
                note(f"Pixabay answered {r.status_code} for '{words}'" + (" (not asking again this run)" if bad else ""))
                if bad: _dead.add("pixabay")
            else:
                hits = r.json().get("hits") or []
                for rank, h in enumerate(hits):
                    vids = h.get("videos") or {}
                    files = [vids[k] for k in ("tiny", "small", "medium", "large") if (vids.get(k) or {}).get("url")
                             and min(vids[k].get("width") or 0, vids[k].get("height") or 0) >= st["min_px"]]
                    if not files or _junk(h, words): continue
                    f = min(files, key=lambda f: f["width"] * f["height"])
                    out.append({"p": "pixabay", "id": str(h["id"]), "url": f["url"], "w": f["width"], "h": f["height"],
                                "d": h.get("duration") or 0, "by": h.get("user") or "", "page": h.get("pageURL") or "",
                                "text": (h.get("tags") or "").replace(",", " "), "rank": rank})
                if not out: note(f"Pixabay '{words}': {len(hits)} results, none at 720p or better")
        except Exception as e:
            note(f"Pixabay search '{words}' failed: {type(e).__name__}: {e}")
        _cache[ck] = out
    return _cache[ck]

# NASA's library is full of news shows and produced packages (captions, lower thirds, titles). Blurred, their letters turn into
# smears behind a Short, so those are skipped by name and plain b-roll, animations and launch footage are ranked first.
NASA_SKIP = re.compile(r"this week|nasa edge|explorers|briefing|conference|interview|\blive\b|update|q ?& ?a|hangout|podcast|episode|"
                       r"webcast|panel|town hall|science casual|nasa now|\bpsa\b|highlights|weekly|recap|explain|lecture|speech|remarks|"
                       r"ceremony|award|promo|teaser|trailer|shareable|social|caption|subtitle|nasaweb|infographic|\bnews\b|report|"
                       r"\btv\b|\bshow\b|series|special|message|greeting|countdown|commentary|narrat|documentary|feature|story|"
                       r"\bpart \d|\bpsa|screen ?cast|presentation|tutorial|how to|what is", re.I)
NASA_BROLL = re.compile(r"b-?roll|footage|animation|visuali[sz]ation|flyover|fly-?over|time-?lapse|simulation|views? (?:of|from)|"
                        r"from (?:orbit|space|the iss|the space station)|launch|lift-?off|roll-?out|landing|rotating|spinning|"
                        r"orbit|flight|surface|hd video", re.I)

def nasa_search(words, used, want=3):
    """Up to `want` NASA clips (public domain) for the words, b-roll first. Their size is checked when they are downloaded."""
    from fetch_media import NASA, NOT_NASA, _fold, _stem
    ids = {k[5:] for k in used if k.startswith("nasa:")}
    r = _get(f"{NASA}/search", params={"q": words, "media_type": "video"})
    r.raise_for_status()
    items = ((r.json().get("collection") or {}).get("items") or [])[:40]
    wants = [_stem(w) for w in words.split() if len(w) > 3]
    ranked, skipped = [], 0
    for rank, it in enumerate(items):
        d = (it.get("data") or [{}])[0]; nid = d.get("nasa_id"); title = d.get("title") or ""
        if not nid or nid in ids or not it.get("href"): continue
        if NASA_SKIP.search(title + " " + nid) or NOT_NASA.search(" ".join(str(d.get(k, "")) for k in ("description", "photographer", "secondary_creator"))):
            skipped += 1; continue
        text = _fold(" ".join([title] + list(d.get("keywords") or [])))
        hit = sum(w in text for w in wants)
        if wants and hit < min(2, len(wants)): continue
        broll = bool(NASA_BROLL.search(title + " " + str(d.get("description", ""))[:300]))
        ranked.append((hit / max(1, len(wants)) + (0.4 if broll else 0) - rank * 0.01, it, d))
    out = []
    for _, it, d in sorted(ranked, key=lambda t: -t[0])[:want + 3]:
        if len(out) >= want or _late(): break
        try: hrefs = [h.replace("http://", "https://") for h in _get(it["href"]).json() if isinstance(h, str)]
        except Exception: continue
        url = next((h for suf in ("~large.mp4", "~orig.mp4") for h in hrefs if h.endswith(suf)), None)
        if not url: continue
        out.append({"p": "nasa", "id": d["nasa_id"], "url": url, "w": 0, "h": 0, "d": 0, "by": "NASA",
                    "page": f"https://images.nasa.gov/details/{urllib.parse.quote(d['nasa_id'])}",
                    "credit": f"Video: NASA ({d.get('center') or 'NASA'})", "text": words, "rank": len(out)})
    if not out: note(f"NASA '{words}': nothing usable ({len(items)} results, {skipped} news or captioned)")
    return out

def candidates(prov, words, st, used):
    """Clips for one search, best first, none already in `used`: a "nasa:" search asks NASA; otherwise Pexels (vertical
    first, then wider ones to crop), then Pixabay when Pexels has fewer than 2 good matches, and last of all the first
    results Pexels ranked highest even though their names share no words with the search."""
    free = lambda c: f"{c['p']}:{c['id']}" not in used
    if prov == "nasa" and st.get("nasa", True):
        try: out = [c for c in nasa_search(words, used) if free(c)]
        except Exception as e:
            out = []; note(f"NASA '{words}' failed: {type(e).__name__}: {e}")
        if out: return out
    pex = [c for c in pexels_search(words, st, "portrait") if free(c)]
    if len(_strong(pex, words, 0.3)) < 3:                    # wider clips are cropped to 9:16, so they widen the choice
        seen = {c["id"] for c in pex}
        pex += [c for c in pexels_search(words, st, "landscape") if free(c) and c["id"] not in seen]
    out = _strong(pex, words, 0.3)
    if len(out) < 2: out += [c for c in _strong(pixabay_search(words, st), words, 0.5) if free(c)]
    if len(out) < 2:                                          # a popular search can run out of fresh clips in a week: look one page deeper
        seen = {c["id"] for c in pex}
        deeper = [c for o in ("portrait", "landscape") for c in pexels_search(words, st, o, 2) if free(c) and c["id"] not in seen]
        out += _strong(deeper, words, 0.3)
    return out + _weak(pex, words, 0.3, 2)

def pick(b, used, cfg):
    """The clips for one board: a first choice for each of its searches (the best Pexels match, else Pixabay, else NASA
    for a "nasa:" search) and up to 4 spares in case a download is refused. Everything taken is added to `used`
    (provider:id), which plan.py shares across the whole run. [] when no key works or nothing matches."""
    st = settings(cfg)
    for env, name, on in (("PEXELS_API_KEY", "Pexels", st.get("pexels", True)), ("PIXABAY_API_KEY", "Pixabay", st.get("pixabay", True))):
        if on and not os.environ.get(env, "").strip(): note(f"{env} is not set, so {name} is skipped")
    have = [parse(q) for q in tidy(b.get("background"))]
    extra = [p for p in (parse(q) for q in fallback(b)) if p and p[1] not in {h[1] for h in have}]
    first, spares = [], []

    def take(prov, words, n=2):
        cs = candidates(prov, words, st, used)[:n]
        for c in cs: used.add(f"{c['p']}:{c['id']}")
        return [dict(c, q=words) for c in cs]

    for prov, words in have:
        cs = take(prov, words)
        if cs: first.append(cs[0]); spares += cs[1:]
    for prov, words in extra:                       # a search that found nothing is replaced by one from the category
        if len(first) >= max(2, len(have)): break
        cs = take(prov, words)
        if cs: first.append(cs[0]); spares += cs[1:]
    for prov, words in extra:
        if len(spares) >= 3: break
        spares += take(prov, words, 1)
    out = [dict(c, spare=False) for c in first[:4]] + [dict(c, spare=True) for c in spares[:4]]
    got = {}
    for c in out:
        if not c["spare"]: got[c["p"]] = got.get(c["p"], 0) + 1
    note("picked " + (", ".join(f"{p} {n}" for p, n in got.items()) or "nothing") + f" (+{sum(1 for c in out if c['spare'])} spares)")
    return out

# ---------------- downloading ----------------
def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out); s = j["streams"][0]; w, h = s["width"], s["height"]
    rot = (s.get("tags") or {}).get("rotate") or next((x.get("rotation") for x in s.get("side_data_list") or [] if "rotation" in x), 0)
    if abs(int(float(rot or 0))) % 180 == 90: w, h = h, w
    return w, h, float((j.get("format") or {}).get("duration") or 0)

def measure_luma(path, secs, ss=0.0):
    """Mean brightness 0 to 1 of `secs` seconds from `ss` (two frames a second)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{ss:.2f}", "-t", f"{secs:.2f}", "-i", str(path), "-vf", "fps=2,scale=48:-2,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8)
    return float(a.mean()) / 255 if a.size else 0.5

def _download(c, d, st):
    import requests
    url = c.get("url") or ""
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or not any((u.hostname or "") == h or (u.hostname or "").endswith("." + h) for h in HOSTS):
        raise RuntimeError("not an allowed video host")
    dest = d / (re.sub(r"[^\w.-]", "_", f"{c['p']}_{c['id']}")[:60] + ".mp4")
    if not dest.exists():
        got = 0
        with requests.get(url, headers=UA, timeout=120, stream=True) as r:
            r.raise_for_status()
            if int(r.headers.get("Content-Length") or 0) > 150_000_000: raise RuntimeError("file too large")
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    got += len(chunk)
                    if got > 150_000_000: raise RuntimeError("file too large")
                    f.write(chunk)
    w, h, dur = _probe(dest)
    if min(w, h) < st["min_px"]: raise RuntimeError(f"only {w}x{h}, needs 720p")
    if dur < 4: raise RuntimeError(f"only {dur:.1f}s long")
    ss = min(6.0, dur - 20) if c.get("p") == "nasa" and dur > 40 else 0.0
    luma = measure_luma(dest, min(dur - ss, 15), ss)
    if luma < float(st.get("min_luma", 0.05)): raise RuntimeError(f"nearly black (brightness {luma:.2f})")
    return dict(c, file=os.path.relpath(dest, HERE), w=w, h=h, d=round(dur, 2), ss=round(ss, 2), luma=round(luma, 3))

def fetch(clips, sid, cfg):
    """Download the planned clips: the first choices, and spares in place of any that fail. Returns (usable clips, notes)."""
    st = settings(cfg)
    d = HERE / "media" / sid / "bg"; d.mkdir(parents=True, exist_ok=True)
    first = [c for c in clips or [] if not c.get("spare")]; spare = [c for c in clips or [] if c.get("spare")]
    want = max(1, min(4, len(first))); got, notes = [], []
    for c in first + spare:
        if len(got) >= want: break
        try: got.append(_download(c, d, st))
        except Exception as e:
            notes.append(f"{c.get('p')}:{c.get('id')} skipped: {str(e)[:90]}")
            print(f"  background: {c.get('p')}:{c.get('id')} skipped: {e}", file=sys.stderr)
    return got, notes

# ---------------- building the layer ----------------
def clean_credit(s):
    return DASH.sub("-", re.sub(r"[\x00-\x1f]", " ", str(s or ""))).strip()[:120]

def credit_for(c):
    if c.get("credit"): return clean_credit(c["credit"])
    by = clean_credit(c.get("by")) or "unknown"
    return f"Video: {by} / {'Pexels' if c['p'] == 'pexels' else 'Pixabay' if c['p'] == 'pixabay' else c['p'].title()}"

def build(clips, T, dest, st, fps=25):
    """Blurred, darkened, cross-fading frames that cover T seconds, written as JPEGs to `dest`. Each clip plays 8 to 15
    seconds when there are enough of them (as many as there are, up to 4); a clip shorter than its turn loops.
    Returns (what the template plays, the clips used with their times) or (None, [])."""
    if not clips: return None, []
    W, H = int(st["frame_w"]), int(st["frame_h"])
    lo, hi = float(st["clip_seconds"][0]), float(st["clip_seconds"][1])
    # aim for about 12 seconds a clip (calm, not busy), never under `lo` or over `hi` while there are clips to share the time
    n = max(1, min(len(clips), 4, max(math.ceil(T / hi), min(int(T // lo), int(T / 12 + 0.5)))))
    clips = clips[:n]
    f = min(float(st["fade"]), T / (3 * n)) if n > 1 else 0.0
    L = (T + (n - 1) * f) / n                  # each clip's turn, overlapping its neighbour by the fade
    dest = pathlib.Path(dest); dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.jpg"): old.unlink()
    cmd, parts = ["ffmpeg", "-y", "-v", "error"], []
    k = int(st.get("knee") or 0)       # highlights above the knee are squeezed to 40%: a white moon or a lamp must not wash out the badge and captions
    knee = f"lutyuv=y='if(lt(val,{k}),val,{k}+(val-{k})*0.4)'," if k else ""
    for i, c in enumerate(clips):
        path = HERE / c["file"]
        gain = max(0.35, min(float(st.get("max_gain", 2.0)), float(st["target_luma"]) / max(0.03, float(c.get("luma") or 0.4))))
        ss = float(c.get("ss") or 0)
        if (c.get("d") or 0) - ss < L + 0.3: cmd += ["-stream_loop", "-1"]
        cmd += ["-ss", f"{ss:.2f}", "-t", f"{L + 0.3:.3f}", "-i", str(path)]
        parts.append(f"[{i}:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                     f"gblur=sigma={float(st['blur'])},lutyuv=y='clip(val*{gain:.3f},16,235)',{knee}eq=saturation=0.9,"
                     f"setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
    last = "v0"
    for i in range(1, n):
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={f:.3f}:offset={i * (L - f):.3f}[x{i}]"); last = f"x{i}"
    frames = int(T * fps) + 3
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-frames:v", str(frames), "-q:v", "3", "-pix_fmt", "yuvj420p",
            str(dest / "%05d.jpg")]
    subprocess.run(cmd, check=True)
    count = len(list(dest.glob("*.jpg")))
    if count < fps: raise RuntimeError(f"background video came out with {count} frames")
    used = []
    for i, c in enumerate(clips):
        used.append({"p": c["p"], "id": c["id"], "q": c.get("q", ""), "t0": round(i * (L - f), 2), "t1": round(min(T, i * (L - f) + L), 2),
                     "credit": credit_for(c), "source": c.get("page", "")})
    return {"dir": os.path.relpath(dest, HERE), "count": count, "fps": fps, "w": W, "h": H}, used
