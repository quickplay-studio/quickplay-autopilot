"""Turn a board's shot sources into local files and credits.

Shot "src" forms (anything else is treated as a local path under pipeline/):
  commons:File:Some_image.jpg     a Wikimedia Commons file (free licence; credit read from Commons)
  commons-search:<words>          best Commons image for the words (width >= 1600)
  pixabay:video:<words>           a Pixabay stock video (PIXABAY_API_KEY), no repeats within a Short
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

def commons_search(words):
    q = {"action": "query", "generator": "search", "gsrsearch": f"{words} filetype:bitmap", "gsrnamespace": 6,
         "gsrlimit": 15, "prop": "imageinfo", "iiprop": "size", "format": "json"}
    pages = sorted(_get(COMMONS, params=q).json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("width", 0) >= 1600: return commons_file(p["title"])
    raise RuntimeError(f"no Commons image for '{words}'")

def pixabay(kind, words, used):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key: raise RuntimeError("PIXABAY_API_KEY not set")
    if kind == "video":
        hits = _get("https://pixabay.com/api/videos/", params={"key": key, "q": words[:100], "safesearch": "true", "per_page": 30}).json()["hits"]
        for h in hits:
            v = h["videos"].get("large") or {}
            if not v.get("url") or v.get("width", 0) < 1280: v = h["videos"].get("medium") or {}
            if h["id"] in used or not v.get("url") or h.get("duration", 0) < 4: continue
            used.add(h["id"])
            return v["url"], f"Video: {h['user']} / Pixabay", h["pageURL"]
    else:
        hits = _get("https://pixabay.com/api/", params={"key": key, "q": words[:100], "image_type": "photo", "safesearch": "true", "per_page": 30}).json()["hits"]
        for h in hits:
            if h["id"] in used: continue
            used.add(h["id"])
            return h["largeImageURL"], f"Photo: {h['user']} / Pixabay", h["pageURL"]
    raise RuntimeError(f"no Pixabay {kind} for '{words}'")

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
                elif kind == "pixabay": url, credit, source = pixabay(*rest.split(":", 1), used)
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
