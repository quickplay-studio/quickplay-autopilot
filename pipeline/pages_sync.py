"""Copies the hub's public pages from this private repository to the public org-site repository (28 October 2026).

The repository is private and GitHub's free plan serves Pages only from public repositories, so the hub and its pages
(docs/*.html) are published from quickplay-studio/quickplay-studio.github.io, folder quickplay-autopilot/. The files there
serve at the same addresses as before (https://quickplay-studio.github.io/quickplay-autopilot/hub.html and the rest).

Only an explicit allowlist ever leaves this repository: docs/*.html, the static assets those pages reference by a relative
path inside docs/ (images, styles, scripts, the web app manifest), and TikTok's site verification file. Never a Markdown,
JSON, CSV, YAML or log file, and never anything under status/, analytics/, tokens/, boards/ or clips/. The hub reads its data
from the private repository in the browser with a read-only token that only Charlie holds (docs/hub.html).

Run by .github/workflows/pages.yml with HUB_PUSH_TOKEN (a fine-grained token: Contents read and write on the public repo
only). With no token, or no public repo yet, it prints one line and exits 0, so no other workflow is ever affected.

PAGES_DOCS, PAGES_REMOTE and PAGES_RETRY_PAUSE exist for the offline test (tests/test_pages.py)."""
import base64, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = pathlib.Path(os.environ.get("PAGES_DOCS") or ROOT / "docs")
SITE_REPO = "quickplay-studio/quickplay-studio.github.io"
REMOTE = os.environ.get("PAGES_REMOTE") or f"https://github.com/{SITE_REPO}.git"
FOLDER = "quickplay-autopilot"           # where the files live in the public repo, so every old link keeps working
IDENTITY = ("Quickplay Studio", "quickplay-studio@users.noreply.github.com")

STATIC = r"png|jpe?g|gif|svg|webp|ico|css|m?js|webmanifest|woff2?|ttf|otf"
# a quoted or bracketed relative file name ending in a static extension (src, href, url(), manifest icons, strings in scripts)
REF = re.compile(r"""[\s"'(=](?:\./)*([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:%s))(?:[?#][^"')\s>]*)?(?=[\s"')>;,])""" % STATIC, re.I)
VERIFY = re.compile(r"tiktok[A-Za-z0-9]+\.txt")                 # TikTok's site verification file (public by design)
VERIFY_BODY = "tiktok-developers-site-verification="
NEVER_EXT = {".md", ".json", ".csv", ".yml", ".yaml", ".py", ".log", ".enc", ".env", ".sh", ".sql", ".db", ".pem", ".key", ".tsv", ".xml"}
NEVER_DIRS = {"status", "analytics", "tokens", "boards", "clips", "logs", "trends", "review", "requests", "pipeline", "tests", "templates", "config"}


def log(*a): print(*a, flush=True)


def never(rel):
    """True for anything that must not leave the private repository, whatever else says it should."""
    p = pathlib.PurePosixPath(rel)
    return (p.suffix.lower() in NEVER_EXT or any(s in NEVER_DIRS or s.startswith(".") for s in p.parts) or ".." in p.parts
            or p.name.lower() in {"config.json", "package.json"})


def referenced(text, base):
    """Static files a page, style sheet or manifest names by a relative path (relative to the folder `base`, as POSIX text)."""
    out = set()
    for m in REF.finditer(text):
        ref = m.group(1)
        if "://" in ref or ref.startswith("/") or ".." in ref.split("/"): continue
        out.add((pathlib.PurePosixPath(base) / ref).as_posix() if base not in ("", ".") else ref)
    return out


def allowlist(docs=None):
    """Sorted paths (POSIX, relative to docs/) of the files that may be published. Pure: reads docs/, writes nothing."""
    docs = pathlib.Path(docs or DOCS)
    found = {p.name for p in docs.glob("*.html") if p.is_file()}
    found |= {p.name for p in docs.glob("*.txt") if p.is_file() and VERIFY.fullmatch(p.name)
              and p.read_text(errors="ignore").startswith(VERIFY_BODY)}
    work, seen = sorted(found), set()
    while work:
        rel = work.pop()
        if rel in seen: continue
        seen.add(rel)
        f = docs / rel
        if not f.is_file(): continue
        suffix = f.suffix.lower()
        if suffix not in (".html", ".css", ".webmanifest", ".js", ".mjs"): continue       # only text that can name other files
        try: text = f.read_text(errors="ignore")
        except OSError: continue
        base = pathlib.PurePosixPath(rel).parent.as_posix()
        for ref in referenced(text, base):
            g = docs / ref
            if g.is_file() and ref not in found and not never(ref):
                found.add(ref); work.append(ref)
    return sorted(r for r in found if not never(r))


def sync(docs, site, files, folder=FOLDER):
    """Makes <site>/<folder>/ hold exactly `files` (copied from docs) and <site>/.nojekyll exist. Returns (copied, removed)."""
    docs, dest, wanted = pathlib.Path(docs), pathlib.Path(site) / folder, set(files)
    assert not any(never(f) for f in wanted), "refusing to copy a file outside the allowlist"
    removed = []
    if dest.exists():
        for p in sorted(dest.rglob("*"), reverse=True):
            rel = p.relative_to(dest).as_posix()
            if p.is_file() and rel not in wanted: p.unlink(); removed.append(rel)
            elif p.is_dir() and not any(p.iterdir()): p.rmdir()
    copied = []
    for rel in sorted(wanted):
        src, dst = docs / rel, dest / rel
        if dst.is_file() and dst.read_bytes() == src.read_bytes(): continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst); copied.append(rel)
    nj = pathlib.Path(site) / ".nojekyll"
    if not nj.exists(): nj.write_text("")
    return copied, removed


def git_env(token):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="true")
    if token and REMOTE.startswith("https://"):                # the same header actions/checkout sets; never on a command line
        b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        print(f"::add-mask::{b64}", flush=True)
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.https://github.com/.extraheader", GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {b64}")
    return env


def git(args, cwd, env, check=True):
    cmd = ["git", "-c", f"user.name={IDENTITY[0]}", "-c", f"user.email={IDENTITY[1]}", *args]
    r = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True)
    if check and r.returncode: raise RuntimeError(f"git {args[0]} failed: " + ((r.stderr or r.stdout).strip().splitlines() or [""])[-1])
    return r


def push(site, env, tries=3, pause=None):
    """Pushes HEAD to main; when the push is refused (someone else pushed first), pulls with a rebase and tries again."""
    pause = float(os.environ.get("PAGES_RETRY_PAUSE", "3")) if pause is None else pause
    for n in range(1, tries + 1):
        if git(["push", "-q", "origin", "HEAD:refs/heads/main"], site, env, check=False).returncode == 0: return True
        log(f"pages: push {n} of {tries} was refused; pulling and trying again")
        git(["pull", "-q", "--rebase", "origin", "main"], site, env, check=False)
        if n < tries: time.sleep(pause)
    return False


def main():
    token = (os.environ.get("HUB_PUSH_TOKEN") or "").strip()
    if not token:
        log(f"pages: HUB_PUSH_TOKEN is not set, so the hub is not copied to {SITE_REPO} yet (nothing else is affected)")
        return 0
    files = allowlist()
    if not files:
        log("pages: no pages found in docs/, nothing to copy"); return 0
    env = git_env(token)
    work = pathlib.Path(tempfile.mkdtemp(prefix="pages-"))
    site = work / "site"
    r = subprocess.run(["git", "clone", "-q", "--depth", "1", REMOTE, str(site)], env=env, text=True, capture_output=True)
    if r.returncode:
        log(f"pages: {SITE_REPO} is not there yet, or HUB_PUSH_TOKEN cannot see it: create the public repo (Pages from main, root), "
            f"then run this workflow again. Nothing was copied.")
        return 0
    if git(["rev-parse", "--verify", "-q", "HEAD"], site, env, check=False).returncode:     # an empty repository: start main
        git(["checkout", "-q", "-B", "main"], site, env)
    copied, removed = sync(DOCS, site, files)
    git(["add", "-A", "--", FOLDER, ".nojekyll"], site, env)
    if not git(["status", "--porcelain"], site, env).stdout.strip():
        log(f"pages: {len(files)} files already up to date in {SITE_REPO}/{FOLDER}/, nothing to push")
        return 0
    short = (os.environ.get("GITHUB_SHA") or "")[:7]
    git(["commit", "-q", "-m", "Hub pages" + (f" from {short}" if short else "")], site, env)
    if not push(site, env):
        log(f"pages: could not push to {SITE_REPO}: check that HUB_PUSH_TOKEN has Contents read and write on it")
        return 1
    log(f"pages: {SITE_REPO}/{FOLDER}/ now holds {len(files)} files ({len(copied)} copied, {len(removed)} removed)")
    for f in files: log("  " + f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
