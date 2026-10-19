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
usage: python fetch_media.py <board.json> <resolved.json>
"""
import hashlib, html, json, os, pathlib, re, subprocess, sys, urllib.parse
import requests

HERE = pathlib.Path(__file__).resolve().parent
UA = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}
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

def commons_search(words):
    """Best Commons photo for the words. The file title must contain every capitalised word of the query (the name),
    so a search for a person never returns a building or someone else; photos with politicians are skipped.
    A query with no capitalised words ("octopus arm suckers") needs all its longer words in the title, or failing
    that any two of them, so a loose description still finds the subject without matching something unrelated."""
    q = {"action": "query", "generator": "search", "gsrsearch": f"{words} filetype:bitmap", "gsrnamespace": 6,
         "gsrlimit": 30, "prop": "imageinfo", "iiprop": "size", "format": "json"}
    pages = sorted(_get(COMMONS, params=q).json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    pages = [p for p in pages if not POLITICAL.search(p["title"])]
    caps = [_fold(w) for w in re.findall(r"[A-Z][\w'-]+", words)]
    if caps: tiers = [(caps, len(caps))]
    else:
        ws = [_stem(w) for w in words.split() if len(w) > 3] or [_stem(w) for w in words.split()]
        tiers = [(ws, len(ws))] + ([(ws, 2)] if len(ws) >= 3 else [])
    for names, need in tiers:
        ok = [p for p in pages if sum(n in _fold(p["title"]) for n in names) >= need]
        for min_w in (1600, 1000):
            for p in ok:
                if (p.get("imageinfo") or [{}])[0].get("width", 0) >= min_w: return commons_file(p["title"])
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
        for score, h, v in sorted(cands, key=lambda c: -c[0])[:6]:
            thumb = v.get("thumbnail") or (h["videos"].get("tiny") or {}).get("thumbnail")
            if not dark_ok and thumb and _brightness(thumb) < 38: continue
            used.add(h["id"])
            return v["url"], f"Video: {h['user']} / Pixabay", h["pageURL"]
    else:
        hits = _get("https://pixabay.com/api/", params={"key": key, "q": words[:100], "image_type": "photo", "safesearch": "true", "per_page": 40}).json()["hits"]
        cands = [(_match(h.get("tags"), words) + (0.15 if h.get("imageHeight", 0) > h.get("imageWidth", 1) else 0) - r * 0.005, h)
                 for r, h in enumerate(hits) if h["id"] not in used and not _junk(h, words)]
        for score, h in sorted(cands, key=lambda c: -c[0])[:6]:
            if not dark_ok and _brightness(h["previewURL"]) < 38: continue
            used.add(h["id"])
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
    for it in items[:30]:
        d = (it.get("data") or [{}])[0]; nid = d.get("nasa_id")
        text = _fold(" ".join([d.get("title", "")] + list(d.get("keywords") or [])))
        if not nid or nid in used or NOT_NASA.search(" ".join(str(d.get(k, "")) for k in ("description", "photographer", "secondary_creator"))):
            continue
        if want and sum(w in text for w in want) < min(2, len(want)): continue
        hrefs = [h.replace("http://", "https://") for h in _get(it["href"]).json() if isinstance(h, str)]
        prefs = ("~large.mp4", "~medium.mp4", "~orig.mp4") if media == "video" else ("~large.jpg", "~orig.jpg", "~medium.jpg")
        pick = next((h for suf in prefs for h in hrefs if h.endswith(suf)), None)
        if not pick: continue
        used.add(nid)
        return pick, f"{'Video' if media == 'video' else 'Photo'}: NASA ({d.get('center') or 'NASA'})", f"https://images.nasa.gov/details/{urllib.parse.quote(nid)}"
    raise RuntimeError(f"no NASA {media} for '{words}'")

def openverse(words, used):
    """A Creative Commons photo via Openverse for people and events Commons lacks. Only CC0, public domain, BY and BY-SA
    (commercial use and changes allowed); the title or tags must hold every capitalised word (the name); no politicians."""
    res = _get("https://api.openverse.org/v1/images/", params={"q": words, "license_type": "commercial,modification",
               "page_size": 30, "mature": "false"}).json().get("results", [])
    caps = [_fold(w) for w in re.findall(r"[A-Z][\w'-]+", words)]
    for it in res:
        text = _fold(it.get("title", "")) + " " + " ".join(_fold(t.get("name", "")) for t in it.get("tags") or [])
        if it.get("id") in used or POLITICAL.search(text) or (it.get("width") or 0) < 1000: continue
        if caps and not all(c in text for c in caps): continue
        used.add(it["id"])
        lic = {"cc0": "CC0", "pdm": "public domain"}.get(it.get("license"), f"CC {str(it.get('license', '')).upper()} {it.get('license_version', '')}".strip())
        return it["url"], f"Photo: {it.get('creator') or 'Unknown'}, {lic}, via {str(it.get('source') or 'Openverse').title()}", \
            it.get("foreign_landing_url") or it["url"]
    raise RuntimeError(f"no Openverse photo named '{words}'")

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

def resolve(sb):
    sid = sb["id"]; d = HERE / "media" / sid; d.mkdir(parents=True, exist_ok=True)
    used, cache, n = set(), {}, 0
    for beat in sb["beats"]:
        for shot in beat.get("shots") or []:
            src = shot["src"]
            if src in cache:
                shot.update(cache[src]); continue
            kind, _, rest = src.partition(":")
            try:
                if kind == "commons": url, credit, source = commons_file(rest)
                elif kind == "commons-search": url, credit, source = commons_search(rest)
                elif kind == "pixabay": url, credit, source = pixabay(*rest.split(":", 1), used, dark_ok=bool(shot.get("dark")))
                elif kind == "url": url, credit, source = rest, shot.get("credit", sb.get("credit", "")), shot.get("source", rest)
                elif kind == "page": url, credit, source = page_image(rest)
                elif kind == "openverse": url, credit, source = openverse(rest, used)
                elif kind == "nasa": url, credit, source = nasa(*rest.split(":", 1), used)
                else: continue   # already local
                stem = f"{n:02d}_" + hashlib.sha1(url.encode()).hexdigest()[:8]; n += 1
                f = download(url, d, stem)
                if shot.get("cuts") == "auto" and f.suffix in {".mp4", ".mov", ".webm", ".m4v"}: scene_cuts(f)
                res = {"src": os.path.relpath(f, HERE), "credit": credit, "source": source}
                if not src.startswith("pixabay:"): cache[src] = res   # same image reused on purpose; stock never repeats
                shot.update(res)
            except Exception as e:
                print(f"  media: {src} failed: {e}", file=sys.stderr)
                shot["_failed"] = str(e)
    # drop shots that could not be fetched. A beat left with none borrows the nearest beat's picture (with a different
    # move, so it doesn't look frozen) instead of failing the whole Short; run_board flags it so a person checks it.
    goods = [[s for s in beat.get("shots") or [] if "_failed" not in s] for beat in sb["beats"]]
    if not any(goods): raise RuntimeError("no usable media for any beat")
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
        donor.pop("label", None)
        if donor.get("start") is not None: donor["start"] = float(donor["start"]) + 2.0
        beat["shots"] = [donor]
        notes.append(f"beat {bi + 1} reused a nearby picture ({mine.get('src', '?')}: {mine.get('_failed', 'not found')[:80]})")
    if notes: sb["_media_notes"] = notes
    return sb

if __name__ == "__main__":
    sb = json.loads(pathlib.Path(sys.argv[1]).read_text())
    pathlib.Path(sys.argv[2]).write_text(json.dumps(resolve(sb), indent=1, ensure_ascii=False))
