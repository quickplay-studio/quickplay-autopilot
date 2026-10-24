"""Turn a board's shot sources into local files and credits.

Shot "src" forms (anything else is treated as a local path under pipeline/):
  commons:File:Some_image.jpg     a Wikimedia Commons file (free licence; credit read from Commons)
  commons-search:<words>          best Commons image whose file name contains the name (capitalised words), no politicians
  pixabay:video:<words>           a Pixabay stock video (PIXABAY_API_KEY): best tag match, portrait preferred,
                                  near-black clips skipped unless the shot has "dark": true, no repeats within a Short
  pixabay:image:<words>           a Pixabay photo (fallback only: they are 1280 px wide)
  url:<https://...>               a direct file from an official press or media page; set "credit" and "source" on the shot
  page:<https://...>              the share picture (og:image) of an official page: a publisher, studio, label, team or
                                  agency's own press image (news outlets' pages are refused: their photos are licensed)
  openverse:<words>               a Creative Commons photo via Openverse (Flickr and others) for people and events Commons
                                  lacks: only licences that allow commercial use and changes, the name must be in the title
  nasa:video:<words>              NASA's image and video library (public domain), for space: real launches, missions, crews
  nasa:image:<words>

A video shot with "cuts": "auto" gets scene-cut detection, so trailer clips never cross a cut (render3 scene_fit).
resolve() keeps each shot's own form in shot["from"], and extras() (the minimal style's fast pace, 24 October) adds more
photos of the same subject from the same Commons search, as shots marked "extra" and "of" the shot they belong to.

Relevance (24 October, pictures.py): a search no longer takes its first hit. Each search's first 8 candidates (Commons photos,
Pixabay photo and video thumbnails, Openverse, NASA) are scored by SigLIP 2 against the beat's text (the shot's words, its
label, the beat's "say" line, the board's subject), near-duplicates are dropped, and the best one is taken. The score stays on
the shot ("relevance", 0 to 1; shots from an explicit source such as commons:File: are scored too) and pictures_summary() hands
status/<id>.json the mean and the share of beats where a picture was found. With no model (or any failure) every search keeps
its own order, as it always did.
usage: python fetch_media.py <board.json> <resolved.json>
"""
import hashlib, html, json, os, pathlib, re, subprocess, sys, time, urllib.parse
import requests
import pictures as PX

HERE = pathlib.Path(__file__).resolve().parent
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
PX.HEADERS = UA
COMMONS = "https://commons.wikimedia.org/w/api.php"

def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=60, **kw); r.raise_for_status(); return r

def download(url, dest_dir, stem):
    ext = pathlib.Path(urllib.parse.urlparse(url).path).suffix.lower() or ".bin"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm", ".m4v"}: ext = ".jpg"
    dest = dest_dir / f"{stem}{ext}"
    if not dest.exists():
        with requests.get(url, headers=UA, timeout=300, stream=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(1 << 20): f.write(chunk)
    return dest

def _strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

def commons_file(title):
    q = {"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|extmetadata|size",
         "iiurlwidth": 2160, "format": "json"}
    page = next(iter(_get(COMMONS, params=q).json()["query"]["pages"].values()))
    ii = page["imageinfo"][0]; md = ii.get("extmetadata", {})
    artist = _strip(md.get("Artist", {}).get("value")) or "Unknown"
    lic = _strip(md.get("LicenseShortName", {}).get("value")) or "free licence"
    return ii.get("thumburl") or ii["url"], f"Photo: {artist}, {lic}, via Wikimedia Commons", ii["descriptionurl"]

POLITICAL = re.compile(r"white house|president|senator|congress|parliament|minister|campaign|rally|election|"
                       r"biden|harris|trump|obama|starmer|sunak|democrat|republican|labour party|conservative party", re.I)

def _fold(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()

def _stem(w):
    w = _fold(w)
    return w[:-1] if len(w) > 4 and w.endswith("s") else w

_CANDS = {}      # a Commons search's candidates, kept per search: the fast pace's extra photos cost no second search
_RANKED = set()  # the searches whose candidates pictures.py already ordered by relevance (their order is what _CANDS keeps)
PICK = {}        # resolve() tells the pick functions the beat's text for the ranker ("ctx") and they leave the chosen picture's scores ("info")

def commons_candidates(words):
    """Every Commons photo a search can use, best first. The file title must contain every capitalised word of the query (the
    name), so a search for a person never returns a building or someone else; photos with politicians are skipped. A query
    with no capitalised words ("octopus arm suckers") needs all its longer words in the title, or failing that any two of
    them, so a loose description still finds the subject without matching something unrelated. Pictures 1600 px wide or
    more come before those of 1000 to 1599 px. [] when nothing fits. Each page carries its 330 px thumbnail (imageinfo[0]
    ["thumburl"]) for the relevance ranking."""
    if words in _CANDS: return _CANDS[words]
    q = {"action": "query", "generator": "search", "gsrsearch": f"{words} filetype:bitmap", "gsrnamespace": 6,
         "gsrlimit": 30, "prop": "imageinfo", "iiprop": "size|url", "iiurlwidth": 330, "format": "json"}
    pages = sorted(_get(COMMONS, params=q).json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    pages = [p for p in pages if not POLITICAL.search(p["title"])]
    caps = [_fold(w) for w in re.findall(r"[A-Z][\w'-]+", words)]
    if caps: tiers = [(caps, len(caps))]
    else:
        ws = [_stem(w) for w in words.split() if len(w) > 3] or [_stem(w) for w in words.split()]
        tiers = [(ws, len(ws))] + ([(ws, 2)] if len(ws) >= 3 else [])
    out, seen = [], set()
    for names, need in tiers:
        ok = [p for p in pages if sum(n in _fold(p["title"]) for n in names) >= need]
        for min_w in (1600, 1000):
            for p in ok:
                if p["title"] not in seen and (p.get("imageinfo") or [{}])[0].get("width", 0) >= min_w:
                    seen.add(p["title"]); out.append(p)
    if out: _CANDS[words] = out
    return out

def _ranked(items, thumbs, bonus=None):
    """A source's candidates (its own order, `thumbs` their thumbnail urls) as [(item, scores)], most relevant to the beat first,
    near-duplicates left out, when pictures.py can rank them; None when it cannot (no model, no beat text, any failure): the
    caller then keeps the source's own order. The scores are what the shot keeps ("relevance")."""
    ctx = PICK.get("ctx")
    if not ctx or not items: return None
    try: order = PX.rank(thumbs, ctx, bonus)
    except Exception as e:
        print(f"  media: picture ranking skipped: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr); return None
    return None if order is None else [(items[i], info) for i, info in order]

def _rank_commons(words, c):
    """Commons candidates, best first by relevance to the beat (the first 8 by their thumbnails) when they can be ranked. The
    ranked list replaces the search's own in _CANDS, so extras() and later shots see it and c[0] is the picture taken."""
    if words in _RANKED:
        if c and c[0].get("_info"): PICK["info"] = c[0]["_info"]
        return c
    order = _ranked(c, [((p.get("imageinfo") or [{}])[0]).get("thumburl") for p in c])
    if order is None: return c
    for p, info in order:
        if info: p["_info"] = info
    ranked = [p for p, _ in order]
    _CANDS[words] = ranked
    _RANKED.add(words)
    PICK["info"] = order[0][1]
    return ranked

def commons_search(words):
    """The best Commons photo for the words (commons_candidates' first, or the most relevant of its first 8 when the beat's text
    can rank them: pictures.py)."""
    c = commons_candidates(words)
    if c:
        c = _rank_commons(words, c)
        return commons_file(c[0]["title"])
    raise RuntimeError(f"no Commons image named '{words}'")

def _brightness(url):
    """Mean brightness 0-255 of a small preview image; 128 if it can't be read."""
    try:
        import io
        from PIL import Image, ImageStat
        return ImageStat.Stat(Image.open(io.BytesIO(_get(url).content)).convert("L")).mean[0]
    except Exception:
        return 128

def _match(tags, words):
    """Share of the query words found in a stock item's tags (Pixabay ranks loosely; this keeps picks on topic)."""
    have = set()
    for t in (tags or "").lower().split(","):
        have.add(t.strip()); have.update(t.split())
    want = [w for w in re.findall(r"[a-z]+", words.lower()) if len(w) > 2]
    return sum(w in have or w.rstrip("s") in have for w in want) / max(1, len(want))

JUNK = ("green screen", "greenscreen", "chroma", "blue screen", "alpha channel", "ai generated", "ai-generated",
        "generated", "transparent background")

def _junk(h, words):
    """Green-screen plates, AI-generated pictures and (unless asked for) animations look fake on screen."""
    tags = (h.get("tags") or "").lower()
    if any(j in tags for j in JUNK): return True
    return h.get("type") == "animation" and "animat" not in words.lower()

def pixabay(kind, words, used, dark_ok=False):
    """Best on-topic Pixabay item: most query words in its tags, portrait preferred, never near-black, no repeats."""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key: raise RuntimeError("PIXABAY_API_KEY not set")
    if kind == "video":
        hits = _get("https://pixabay.com/api/videos/", params={"key": key, "q": words[:100], "safesearch": "true", "per_page": 40}).json()["hits"]
        cands = []
        for rank, h in enumerate(hits):
            v = h["videos"].get("large") or {}
            if not v.get("url") or v.get("width", 0) < 1280: v = h["videos"].get("medium") or {}
            if h["id"] in used or not v.get("url") or h.get("duration", 0) < 4 or _junk(h, words): continue
            score = _match(h.get("tags"), words) + (0.15 if v.get("height", 0) > v.get("width", 1) else 0) - rank * 0.005
            cands.append((score, h, v))
        top = sorted(cands, key=lambda c: -c[0])
        thumb_of = lambda c: c[2].get("thumbnail") or (c[1]["videos"].get("tiny") or {}).get("thumbnail")
        # the tag match picked the best 8 to look at; relevance to the beat orders them (a vertical clip edges ahead a little)
        pick = _ranked(top, [thumb_of(c) for c in top], [0.01 if c[2].get("height", 0) > c[2].get("width", 1) else 0.0 for c in top])
        for (score, h, v), info in (pick[:8] if pick else [(c, None) for c in top[:6]]):
            thumb = thumb_of((score, h, v))
            if not dark_ok and thumb and _brightness(thumb) < 38: continue
            used.add(h["id"]); PICK["info"] = info
            return v["url"], f"Video: {h['user']} / Pixabay", h["pageURL"]
    else:
        hits = _get("https://pixabay.com/api/", params={"key": key, "q": words[:100], "image_type": "photo", "safesearch": "true", "per_page": 40}).json()["hits"]
        cands = [(_match(h.get("tags"), words) + (0.15 if h.get("imageHeight", 0) > h.get("imageWidth", 1) else 0) - r * 0.005, h)
                 for r, h in enumerate(hits) if h["id"] not in used and not _junk(h, words)]
        top = sorted(cands, key=lambda c: -c[0])
        pick = _ranked(top, [c[1].get("webformatURL") for c in top])          # 640 px previews, for the relevance ranking
        for (score, h), info in (pick[:8] if pick else [(c, None) for c in top[:6]]):
            if not dark_ok and _brightness(h["previewURL"]) < 38: continue
            used.add(h["id"]); PICK["info"] = info
            return h["largeImageURL"], f"Photo: {h['user']} / Pixabay", h["pageURL"]
    raise RuntimeError(f"no usable Pixabay {kind} for '{words}'")

NASA = "https://images-api.nasa.gov"
NOT_NASA = re.compile(r"©|copyright|getty|reuters|ap photo|afp|spacex", re.I)

def nasa(kind, words, used):
    """NASA's image and video library (public domain): the best match whose title and keywords hold the query's longer
    words; anything credited to an agency or company outside NASA is skipped (it may be copyrighted)."""
    media = "video" if kind == "video" else "image"
    items = _get(f"{NASA}/search", params={"q": words, "media_type": media}).json().get("collection", {}).get("items", [])
    want = [_stem(w) for w in words.split() if len(w) > 3]
    cands = []
    for it in items[:30]:
        d = (it.get("data") or [{}])[0]; nid = d.get("nasa_id")
        text = _fold(" ".join([d.get("title", "")] + list(d.get("keywords") or [])))
        if not nid or nid in used or NOT_NASA.search(" ".join(str(d.get(k, "")) for k in ("description", "photographer", "secondary_creator"))):
            continue
        if want and sum(w in text for w in want) < min(2, len(want)): continue
        cands.append(it)
    prev = lambda it: next((l.get("href") for l in it.get("links") or [] if l.get("rel") == "preview" and l.get("href")), None)
    for it, info in _ranked(cands, [prev(c) for c in cands]) or [(c, None) for c in cands]:
        d = (it.get("data") or [{}])[0]; nid = d.get("nasa_id")
        hrefs = [h.replace("http://", "https://") for h in _get(it["href"]).json() if isinstance(h, str)]
        prefs = ("~large.mp4", "~medium.mp4", "~orig.mp4") if media == "video" else ("~large.jpg", "~orig.jpg", "~medium.jpg")
        pick = next((h for suf in prefs for h in hrefs if h.endswith(suf)), None)
        if not pick: continue
        used.add(nid); PICK["info"] = info
        return pick, f"{'Video' if media == 'video' else 'Photo'}: NASA ({d.get('center') or 'NASA'})", f"https://images.nasa.gov/details/{urllib.parse.quote(nid)}"
    raise RuntimeError(f"no NASA {media} for '{words}'")

def openverse(words, used):
    """A Creative Commons photo via Openverse for people and events Commons lacks. Only CC0, public domain, BY and BY-SA
    (commercial use and changes allowed); the title or tags must hold every capitalised word (the name); no politicians."""
    try:
        res = _get("https://api.openverse.org/v1/images/", params={"q": words, "license_type": "commercial,modification",
                   "page_size": 30, "mature": "false"}).json().get("results", [])
    except requests.HTTPError:          # Openverse now asks for a sign-in: Commons still covers most people
        return commons_search(words)
    caps = [_fold(w) for w in re.findall(r"[A-Z][\w'-]+", words)]
    ok = []
    for it in res:
        text = _fold(it.get("title", "")) + " " + " ".join(_fold(t.get("name", "")) for t in it.get("tags") or [])
        if it.get("id") in used or POLITICAL.search(text) or (it.get("width") or 0) < 1000: continue
        if caps and not all(c in text for c in caps): continue
        ok.append(it)
    pick = _ranked(ok, [x.get("thumbnail") for x in ok]) or [(x, None) for x in ok]
    if pick:
        it, info = pick[0]
        used.add(it["id"]); PICK["info"] = info
        lic = {"cc0": "CC0", "pdm": "public domain"}.get(it.get("license"), f"CC {str(it.get('license', '')).upper()} {it.get('license_version', '')}".strip())
        return it["url"], f"Photo: {it.get('creator') or 'Unknown'}, {lic}, via {str(it.get('source') or 'Openverse').title()}", \
            it.get("foreign_landing_url") or it["url"]
    return commons_search(words)

# news and media outlets: their pictures are agency or staff photos licensed to them, never ours to reuse
OUTLETS = ("bbc.co.uk", "bbc.com", "theguardian.com", "reuters.com", "apnews.com", "theverge.com", "ign.com", "eurogamer.net",
           "variety.com", "billboard.com", "espn.com", "espn.co.uk", "skysports.com", "sky.com", "techcrunch.com", "engadget.com",
           "arstechnica.com", "wired.com", "polygon.com", "pcgamer.com", "gamespot.com", "nme.com", "rollingstone.com",
           "hollywoodreporter.com", "deadline.com", "space.com", "independent.co.uk", "telegraph.co.uk", "standard.co.uk",
           "nytimes.com", "washingtonpost.com", "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com", "usatoday.com",
           "nature.com", "newscientist.com", "nationalgeographic.com", "premierleague.com", "uefa.com", "nfl.com", "spacex.com",
           "dailymail.co.uk", "mirror.co.uk", "thesun.co.uk", "metro.co.uk", "people.com", "tmz.com", "kotaku.com")

def page_image(url):
    """The share picture (og:image) of an official page, with the site's name as credit."""
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    if any(host == o or host.endswith("." + o) for o in OUTLETS):
        raise RuntimeError(f"{host} is a news outlet: its pictures are licensed, not ours to use")
    page = requests.get(url, headers={**UA, "User-Agent": "Mozilla/5.0 (compatible; QuickplayAutopilot/1.0)"}, timeout=60).text
    meta = dict((k.lower(), html.unescape(v)) for k, v in re.findall(
        r'<meta[^>]+?(?:property|name)=["\'](og:image|twitter:image|og:site_name)["\'][^>]+?content=["\']([^"\']+)', page, re.I))
    meta.update((k.lower(), html.unescape(v)) for v, k in re.findall(
        r'<meta[^>]+?content=["\']([^"\']+)["\'][^>]+?(?:property|name)=["\'](og:image|twitter:image|og:site_name)', page, re.I) if k.lower() not in meta)
    img = meta.get("og:image") or meta.get("twitter:image")
    if not img: raise RuntimeError("no share picture on the page")
    return urllib.parse.urljoin(url, img), f"Image: {meta.get('og:site_name') or host}", url

def scene_cuts(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", "scale=320:-2,select='gt(scene,0.12)',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    cuts = sorted({round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)})
    path.with_suffix(".cuts.json").write_text(json.dumps(cuts))
    return cuts

GAMEPLAY, _CLIPS = HERE / "media" / "gameplay", []
CLIP_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def gameplay_clip(sid, k):
    """Charlie's own gameplay recordings (video files attached to the repo's "gameplay" release: Minecraft parkour and the
    like, which Minecraft's rules allow in monetised videos): a clip chosen by the Short and the shot, and a start point
    in it. None while there are none, so the shot falls back to stock video of the same words."""
    if not _CLIPS:
        _CLIPS.append([])
        try:
            repo = os.environ.get("GITHUB_REPOSITORY") or "quickplay-studio/quickplay-autopilot"
            tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/gameplay", timeout=30,
                             headers={"Authorization": f"Bearer {tok}"} if tok else {})
            if r.ok: _CLIPS[0] = sorted((a["name"], a["browser_download_url"]) for a in r.json().get("assets", [])
                                        if a["name"].lower().endswith(CLIP_EXT))
        except Exception as e:
            print(f"  gameplay list: {e}", file=sys.stderr)
    if not _CLIPS[0]: return None
    h = int(hashlib.sha1(f"{sid}:{k}".encode()).hexdigest(), 16)
    name, url = _CLIPS[0][h % len(_CLIPS[0])]
    GAMEPLAY.mkdir(parents=True, exist_ok=True)
    f = GAMEPLAY / name
    if not f.exists():
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(f, "wb") as out:
                for chunk in r.iter_content(1 << 20): out.write(chunk)
    try: dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                    capture_output=True, text=True).stdout.strip())
    except ValueError: dur = 60.0
    return f, (h // 7) % max(1, int(dur) - 20)


def _words(kind, rest):
    """The search words of a shot's src, for the ranker's text ("pixabay:video:crowd cheering" -> "crowd cheering"; a Commons
    file name without File: and its extension; nothing for a url or a page, whose picture is named by its source alone)."""
    if kind in ("url", "page"): return ""
    if kind in ("pixabay", "nasa"): return rest.partition(":")[2] or rest
    if kind == "commons": return re.sub(r"\.\w{2,5}$", "", re.sub(r"^File:", "", rest, flags=re.I)).replace("_", " ")
    return rest


def _relevance(f):
    """{"relevance": 0.83} for the picture just downloaded: the score the ranking chose it by (PICK["info"]), else scored now
    when it is a still (a shot from an explicit source: no candidates to choose between). {} with no score. The picture is
    then "taken": a later candidate that repeats it goes behind the others."""
    try:
        info = PICK.get("info") or PX.score_file(f, PICK.get("ctx"))
        if not info: return {}
        PX.commit(info)
        return {"relevance": info["rel"]}
    except Exception as e:
        print(f"  media: relevance not kept for {f.name}: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
        return {}


def resolve(sb):
    sid = sb["id"]; d = HERE / "media" / sid; d.mkdir(parents=True, exist_ok=True)
    used, cache, n = set(), {}, 0
    _RANKED.clear()
    try: PX.begin(sb)                           # a new Short for the picture ranker: the board's subject and category, a clean slate
    except Exception as e: print(f"  media: picture ranking not started: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
    for beat in sb["beats"]:
        for shot in beat.get("shots") or []:
            src = shot["src"]
            shot["from"] = src                  # the form the board gave it, kept for extras()
            if src in cache:
                shot.update(cache[src]); continue
            kind, _, rest = src.partition(":")
            PICK.clear()
            try: PICK["ctx"] = PX.context(_words(kind, rest), beat.get("say"), shot.get("label"))      # the beat's text; None when it has none
            except Exception: PICK["ctx"] = None
            try:
                if kind == "commons": url, credit, source = commons_file(rest)
                elif kind == "commons-search": url, credit, source = commons_search(rest)
                elif kind == "pixabay": url, credit, source = pixabay(*rest.split(":", 1), used, dark_ok=bool(shot.get("dark")))
                elif kind == "url": url, credit, source = rest, shot.get("credit", sb.get("credit", "")), shot.get("source", rest)
                elif kind == "page": url, credit, source = page_image(rest)
                elif kind == "openverse": url, credit, source = openverse(rest, used)
                elif kind == "nasa": url, credit, source = nasa(*rest.split(":", 1), used)
                elif kind == "gameplay":     # our own recordings when there are any, else stock video of the words
                    g = gameplay_clip(sid, n)
                    if g:
                        n += 1; shot.update(src=os.path.relpath(g[0], HERE), credit="Quickplay Daily", source="own gameplay recording", start=g[1])
                        continue
                    url, credit, source = pixabay("video", rest or "parkour rooftop run", used)
                else: continue   # already local
                stem = f"{n:02d}_" + hashlib.sha1(url.encode()).hexdigest()[:8]; n += 1
                f = download(url, d, stem)
                if shot.get("cuts") == "auto" and f.suffix in {".mp4", ".mov", ".webm", ".m4v"}: scene_cuts(f)
                res = {"src": os.path.relpath(f, HERE), "credit": credit, "source": source, **_relevance(f)}
                if kind not in ("pixabay", "gameplay"): cache[src] = res   # same image reused on purpose; stock never repeats
                shot.update(res)
            except Exception as e:
                print(f"  media: {src} failed: {e}", file=sys.stderr)
                shot["_failed"] = str(e)
    # drop shots that could not be fetched. A beat left with none borrows the nearest beat's picture (with a different
    # move, so it doesn't look frozen) instead of failing the whole Short; run_board flags it so a person checks it.
    goods = [[s for s in beat.get("shots") or [] if "_failed" not in s] for beat in sb["beats"]]
    if not any(goods): raise RuntimeError("no usable media for any beat")
    asked = [bi for bi, beat in enumerate(sb["beats"]) if beat.get("shots")]
    sb["_pic_found"] = [sum(1 for bi in asked if goods[bi]), len(asked)]        # beats where a picture was found, of those that asked for one
    notes = []
    for bi, beat in enumerate(sb["beats"]):
        if not beat.get("shots"): continue
        if goods[bi]: beat["shots"] = goods[bi]; continue
        order = sorted((j for j in range(len(goods)) if goods[j] and j != bi), key=lambda j: (abs(j - bi), j > bi))
        donor = dict(goods[order[0]][-1 if order[0] < bi else 0])
        mine = beat["shots"][0]
        flip = {"in": "out", "out": "in", "left": "right", "right": "left", "up": "down", "down": "up"}
        donor.update(move=flip.get(donor.get("move"), "in"), focus=[0.42, 0.48] if (donor.get("focus") or [0.5])[0] >= 0.5 else [0.58, 0.48])
        for k in ("w", "at", "tin"):
            if k in mine: donor[k] = mine[k]
            else: donor.pop(k, None)
        donor.pop("label", None); donor.pop("relevance", None)      # its score was for another beat's words
        if donor.get("start") is not None: donor["start"] = float(donor["start"]) + 2.0
        beat["shots"] = [donor]
        notes.append(f"beat {bi + 1} reused a nearby picture ({mine.get('src', '?')}: {mine.get('_failed', 'not found')[:80]})")
    if notes: sb["_media_notes"] = notes
    return sb

def _ahash(path):
    """A 64-bit average hash of a picture: two files of one photo (a resize, another upload) differ in a few bits at most,
    two photos of the same subject in many."""
    import numpy as np
    from PIL import Image
    g = np.asarray(Image.open(path).convert("L").resize((8, 8)), dtype=np.float32).ravel()
    return sum(1 << i for i, v in enumerate(g >= g.mean()) if v)


EXTRA_CREDIT_ROOM = 3000      # characters the credit lines may take in a Short's description (YouTube cuts it at 4900)


def extras(sb, per=2, cap=18, seconds=80):
    """More photos of the same subject for the fast pace (the minimal style, templates/looks.json, 24 October): for each shot
    found by a name search (commons-search:) up to `per` more photos from the same Commons search, each added to its beat as
    a shot marked "extra" and "of" the shot it belongs to, with its own credit. render3's fast pace cuts to them; the other
    pace never sees them. At most `cap` photos and `seconds` of fetching, and only as many as the description has room for
    their credit lines (EXTRA_CREDIT_ROOM). A photo that is the same picture as one already in the Short is dropped. Never
    raises: what cannot be fetched is left out (the pace then cuts to the same photo with a new crop, render3.variant).
    Returns how many were added."""
    d = HERE / "media" / sb["id"]; d.mkdir(parents=True, exist_ok=True)
    stop, added, n, given = time.time() + seconds, 0, 0, {}
    lines = lambda c, src: len(f"{c} ({src})" if src else c) + 1
    room = EXTRA_CREDIT_ROOM - sum(lines(sh.get("credit", ""), sh.get("source", "")) for bt in sb["beats"] for sh in bt.get("shots") or []
                                   if sh.get("credit"))
    seen = []
    for bt in sb["beats"]:                                  # every picture already in the Short
        for sh in bt.get("shots") or []:
            f = HERE / str(sh.get("src", ""))
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and f.exists():
                try: seen.append(_ahash(f))
                except Exception: pass
    for bt in sb["beats"]:
        add = []
        for shot in list(bt.get("shots") or []):
            kind, _, words = str(shot.get("from", "")).partition(":")
            if kind != "commons-search" or shot.get("extra") or added >= cap or time.time() > stop: continue
            try: cands = commons_candidates(words)
            except Exception as e:
                print(f"  media: extra photos for {words} failed: {e}", file=sys.stderr); continue
            taken = given.setdefault(words, {c["title"] for c in cands[:1]})        # the first is the shot's own photo
            got = 0
            for c in cands:
                if got >= per or added >= cap or time.time() > stop: break
                if c["title"] in taken: continue
                taken.add(c["title"])
                try:
                    url, credit, source = commons_file(c["title"])
                    if lines(credit, source) > room: continue
                    f = download(url, d, f"x{n:02d}_" + hashlib.sha1(url.encode()).hexdigest()[:8]); n += 1
                    h = _ahash(f)
                    if any(bin(h ^ o).count("1") <= 6 for o in seen): f.unlink(); continue
                except Exception as e:
                    print(f"  media: extra photo {c['title']} failed: {e}", file=sys.stderr); continue
                seen.append(h); room -= lines(credit, source); got += 1; added += 1
                add.append({"src": os.path.relpath(f, HERE), "credit": credit, "source": source, "extra": True, "of": shot["src"],
                            **({"relevance": c["_info"]["rel"]} if c.get("_info") else {})})
        if add: bt["shots"] = list(bt.get("shots") or []) + add
    return added


def pictures_summary(sb):
    """What status/<id>.json keeps of the picture ranking (media.*, then shorts.csv by analytics.py): pic_relevance, the mean
    relevance (0 to 1) of the pictures used, extras included, and pic_found_share, the share of the beats that asked for a
    picture where one was found; "" when there was nothing to score (no model, or no stills). Plus the ranker's own counts
    (pictures.summary). Never raises: a Short is never held up by its own statistics."""
    out = {}
    try:
        found = sb.pop("_pic_found", None)
        if found and found[1]: out["pic_found_share"] = round(found[0] / found[1], 2)
        rel = [sh["relevance"] for bt in sb.get("beats") or [] for sh in bt.get("shots") or [] if isinstance(sh.get("relevance"), (int, float))]
        if rel: out["pic_relevance"] = round(sum(rel) / len(rel), 3)
        out.update(PX.summary())
    except Exception as e:
        print(f"  media: picture summary failed: {type(e).__name__}: {str(e)[:100]}", file=sys.stderr)
    return out

if __name__ == "__main__":
    sb = json.loads(pathlib.Path(sys.argv[1]).read_text())
    pathlib.Path(sys.argv[2]).write_text(json.dumps(resolve(sb), indent=1, ensure_ascii=False))
