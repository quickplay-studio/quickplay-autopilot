"""Turn a board's shot sources into local files and credits.

Shot "src" forms (anything else is treated as a local path under pipeline/):
  commons:File:Some_image.jpg     a Wikimedia Commons file (free licence; credit read from Commons)
  commons-search:<words>          best Commons image whose file name contains the name (capitalised words), no politicians
  pixabay:video:<words>           a Pixabay stock video (PIXABAY_API_KEY): best tag match, portrait preferred,
                                  near-black clips skipped unless the shot has "dark": true, no repeats within a Short
  pixabay:image:<words>           a Pixabay photo (fallback only: they are 1280 px wide)
  url:<https://...>               a direct file from an official press or media page; set "credit" and "source" on the shot

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

def commons_search(words):
    """Best Commons photo for the words. The file title must contain every capitalised word of the query (the name),
    so a search for a person never returns a building or someone else; photos with politicians are skipped."""
    q = {"action": "query", "generator": "search", "gsrsearch": f"{words} filetype:bitmap", "gsrnamespace": 6,
         "gsrlimit": 30, "prop": "imageinfo", "iiprop": "size", "format": "json"}
    pages = sorted(_get(COMMONS, params=q).json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    names = [_fold(w) for w in re.findall(r"[A-Z][\w'-]+", words)] or [_fold(w) for w in words.split()[:1]]
    ok = [p for p in pages if all(n in _fold(p["title"]) for n in names) and not POLITICAL.search(p["title"])]
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
    for beat in sb["beats"]:       # drop shots that could not be fetched; a beat keeps at least its first good shot
        good = [s for s in beat.get("shots") or [] if "_failed" not in s]
        if beat.get("shots") and not good: raise RuntimeError(f"no usable media for beat: {beat['say'][:40]}")
        if beat.get("shots"): beat["shots"] = good
    return sb

if __name__ == "__main__":
    sb = json.loads(pathlib.Path(sys.argv[1]).read_text())
    pathlib.Path(sys.argv[2]).write_text(json.dumps(resolve(sb), indent=1, ensure_ascii=False))
