"""Download the picture models at pinned versions and check every file's hash (supply chain rule, Black October).

usage: python get_pictures.py <models dir> [--only yunet|siglip2]

yunet    OpenCV's YuNet face detector, face_detection_yunet_2023mar.onnx (232,589 bytes, MIT licence), from the opencv_zoo
         repo. The file is stored in Git LFS, so media.githubusercontent.com serves the file itself (raw.githubusercontent.com
         serves only a pointer). SHA-256 pinned below, and equal to the LFS pointer's oid; a file with any other hash is deleted.
         faces.py uses it in render3.face_focus and clips.face_box; without it they keep the Haar cascade.
siglip2  google/siglip2-base-patch16-224 (Apache-2.0, not gated; safetensors, no code is run from it): the picture ranker of
         fetch_media.py (pictures.py). Files are downloaded with huggingface_hub, every file's SHA-256 is computed and kept in
         MANIFEST.json beside them, and pictures.py loads the model only when that manifest is there. A file with a pin in
         SIGLIP["pins"] must match it (else it is deleted); a file without one is trusted on first use, logged as "unpinned" and
         checked against the manifest on every later run. Without the model fetch_media keeps the search's own order.
Files go to <models dir>/yunet and <models dir>/siglip2; render.yml and clips.yml keep them in the Actions cache. Nothing here
ever fails the job: a failure prints a ::warning:: line and the feature stays off (exit 0).
"""
import argparse, hashlib, json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

YUNET = {
    "dir": "yunet",
    "file": "face_detection_yunet_2023mar.onnx",
    "size": 232589,
    "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    "urls": ["https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
             "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"],
}

SIGLIP = {
    "dir": "siglip2",
    "name": "siglip2-base-patch16-224",
    "repo": "google/siglip2-base-patch16-224",
    "revision": None,                    # a commit hash once known; None follows the repo's main branch (the hashes below still bind the files)
    "patterns": ["*.json", "*.safetensors", "tokenizer.model"],
    "need": ("config.json", "model.safetensors"),
    # file name -> SHA-256. Empty until the first GitHub run has printed the observed hashes (the sandbox this was written in
    # could not reach Hugging Face): copy them from the log line "siglip2: UNPINNED ..." or from status/<id>.json media.pic_model.
    "pins": {},
}

# the Actions cache keys (render.yml, clips.yml): change one whenever its model's pin changes; tests/test_pictures.py checks both files
CACHE_KEYS = {"yunet": "yunet-2023mar-8f2383e", "siglip2": "siglip2-b16-224-v1"}


def models_dir():
    """$QP_MODELS, else <repo>/models (git-ignored; the Actions cache restores models/yunet and models/siglip2 there)."""
    return pathlib.Path(os.environ.get("QP_MODELS") or ROOT / "models")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""): h.update(b)
    return h.hexdigest()


def warn(msg):
    print(f"::warning::{msg}", flush=True)


# ---------------- YuNet ----------------
def yunet_ok(path):
    """True when `path` is the pinned file (size, then SHA-256)."""
    try:
        p = pathlib.Path(path)
        return p.exists() and p.stat().st_size == YUNET["size"] and sha256_file(p) == YUNET["sha256"]
    except OSError: return False


def get_yunet(dest):
    import requests
    dest = pathlib.Path(dest) / YUNET["dir"]; dest.mkdir(parents=True, exist_ok=True)
    f = dest / YUNET["file"]
    if yunet_ok(f): print(f"yunet: {YUNET['file']} ok", flush=True); return True
    f.unlink(missing_ok=True)
    for url in YUNET["urls"]:
        try:
            r = requests.get(url, timeout=60); r.raise_for_status()
            data = r.content
        except Exception as e:
            print(f"yunet: {url} failed: {type(e).__name__}: {str(e)[:120]}", flush=True); continue
        part = f.with_suffix(".part"); part.write_bytes(data)
        if len(data) == YUNET["size"] and hashlib.sha256(data).hexdigest() == YUNET["sha256"]:
            part.replace(f); print(f"yunet: {YUNET['file']} downloaded, hash ok", flush=True); return True
        part.unlink(missing_ok=True)
        print(f"yunet: {url} gave {len(data)} bytes with another hash: deleted", flush=True)
    warn("yunet: model not downloaded; faces use the Haar cascade")
    return False


# ---------------- SigLIP 2 ----------------
def manifest_path(dest): return pathlib.Path(dest) / "MANIFEST.json"


def read_manifest(dest):
    try: return json.loads(manifest_path(dest).read_text())
    except Exception: return None


def check_manifest(dest, m, pins):
    """Names of the files that are missing, differ from the manifest, or break a pin."""
    bad = []
    for name, rec in (m.get("files") or {}).items():
        f = pathlib.Path(dest) / name
        try:
            if not f.exists() or f.stat().st_size != rec["size"] or sha256_file(f) != rec["sha256"]: bad.append(name)
            elif name in pins and pins[name] != rec["sha256"]: bad.append(name)
        except OSError: bad.append(name)
    return bad


def get_siglip(dest, download=None):
    """Fetch (or verify) the SigLIP 2 files into <dest>/siglip2 and write MANIFEST.json. `download(dest)` stands in for the
    Hugging Face download in tests. True when the model is complete and every pin holds."""
    d = pathlib.Path(dest) / SIGLIP["dir"]; d.mkdir(parents=True, exist_ok=True)
    pins = SIGLIP["pins"]
    m = read_manifest(d)
    if m is not None:
        bad = check_manifest(d, m, pins)
        if not bad: print(f"siglip2: {len(m['files'])} files ok (cached, hashes match the manifest)", flush=True); return True
        print(f"siglip2: {bad} differ from the manifest: downloading again", flush=True)
        manifest_path(d).unlink(missing_ok=True)
        for name in bad: (d / name).unlink(missing_ok=True)
    try:
        if download: download(d)
        else:
            from huggingface_hub import snapshot_download
            snapshot_download(SIGLIP["repo"], revision=SIGLIP["revision"], local_dir=str(d), allow_patterns=SIGLIP["patterns"])
    except Exception as e:
        warn(f"siglip2: download failed ({type(e).__name__}: {str(e)[:160]}); pictures keep the search's own order")
        return False
    files = {}
    for f in sorted(d.rglob("*")):
        rel = f.relative_to(d).as_posix()
        if not f.is_file() or rel.startswith(".cache/") or rel == "MANIFEST.json": continue
        files[rel] = {"size": f.stat().st_size, "sha256": sha256_file(f)}
    for name, rec in files.items():
        if name in pins and pins[name] != rec["sha256"]:
            (d / name).unlink(missing_ok=True)
            warn(f"siglip2: {name} hash {rec['sha256'][:16]}... breaks its pin; deleted. Pictures keep the search's own order")
            return False
    if any(n not in files for n in SIGLIP["need"]):
        warn(f"siglip2: missing {[n for n in SIGLIP['need'] if n not in files]} after the download; pictures keep the search's own order")
        return False
    for name, rec in files.items():
        if name not in pins and name.endswith((".safetensors", "config.json")):
            print(f"siglip2: UNPINNED {name} sha256 {rec['sha256']} ({rec['size']} bytes): pin it in get_pictures.SIGLIP['pins']", flush=True)
    manifest_path(d).write_text(json.dumps({"model": SIGLIP["name"], "repo": SIGLIP["repo"], "revision": SIGLIP["revision"] or "main",
                                            "commit": commit_of(d), "pinned": sorted(n for n in files if n in pins), "files": files}, indent=1))
    print(f"siglip2: {len(files)} files downloaded, manifest written", flush=True)
    return True


def commit_of(d):
    """The Hugging Face commit the files came from, when huggingface_hub left its metadata (local_dir/.cache/huggingface/download)."""
    try:
        meta = next((pathlib.Path(d) / ".cache" / "huggingface" / "download").glob("config.json.metadata"))
        return meta.read_text().splitlines()[0].strip()
    except Exception: return ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dest"); ap.add_argument("--only", choices=("yunet", "siglip2"))
    a = ap.parse_args()
    ok = {}
    if a.only in (None, "yunet"):
        try: ok["yunet"] = get_yunet(a.dest)
        except Exception as e: warn(f"yunet: {type(e).__name__}: {str(e)[:160]}"); ok["yunet"] = False
    if a.only in (None, "siglip2"):
        try: ok["siglip2"] = get_siglip(a.dest)
        except Exception as e: warn(f"siglip2: {type(e).__name__}: {str(e)[:160]}"); ok["siglip2"] = False
    print(json.dumps(ok), flush=True)


if __name__ == "__main__":
    main()
