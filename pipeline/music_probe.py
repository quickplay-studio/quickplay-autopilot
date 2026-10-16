"""One-off: can a GitHub runner read Pixabay Music pages and their audio files? Writes status/music_probe.json."""
import json, re, requests, pathlib
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
MP3 = re.compile(r'https:(?:\\?/){2}cdn\.pixabay\.com(?:\\?/)(?:download(?:\\?/))?audio(?:\\?/)[^"\'\s<>]+?\.mp3')
out = []
for u in ["https://pixabay.com/music/search/epic/", "https://pixabay.com/music/search/genre/rock/", "https://pixabay.com/music/search/mood/epic/"]:
    row = {"url": u}
    try:
        r = requests.get(u, headers=H, timeout=30); t = r.text
        mp3 = [m.replace("\\/", "/") for m in MP3.findall(t)]
        pages = re.findall(r'href="(/music/[a-z0-9\-]+-\d{4,}/)"', t)
        row.update(status=r.status_code, length=len(t), server=r.headers.get("server"),
                   challenge=any(k in t for k in ("Just a moment", "cf-chl", "challenge-platform")),
                   title=(re.search(r"<title>(.*?)</title>", t, re.S).group(1).strip() if "<title>" in t else None),
                   n_mp3=len(set(mp3)), mp3=list(dict.fromkeys(mp3))[:6], n_pages=len(set(pages)), pages=list(dict.fromkeys(pages))[:6])
        i = t.find("cdn.pixabay.com"); j = t.find("audio_")
        row["context"] = t[max(0, j - 700): j + 300] if j > 0 else t[max(0, i - 300): i + 300]
        if mp3:
            h = requests.get(mp3[0], headers=H | {"Range": "bytes=0-1023"}, timeout=30)
            row["mp3_fetch"] = {"status": h.status_code, "type": h.headers.get("content-type"), "bytes": len(h.content)}
        if pages:
            p = requests.get("https://pixabay.com" + pages[0], headers=H, timeout=30); pt = p.text
            k = pt.lower().find("content id")
            row["track_page"] = {"status": p.status_code, "length": len(pt), "content_id_context": pt[max(0, k - 200): k + 200] if k >= 0 else None,
                                 "n_mp3": len(set(MP3.findall(pt))), "ld_json": bool(re.search(r'application/ld\+json', pt))}
    except Exception as e:
        row["error"] = str(e)[:200]
    out.append(row)
pathlib.Path("status").mkdir(exist_ok=True)
pathlib.Path("status/music_probe.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
