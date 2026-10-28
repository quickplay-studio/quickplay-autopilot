"""Offline test of the hub going public-site-only (28 October 2026). The repository is private and GitHub's free plan serves
Pages only from public repositories, so pipeline/pages_sync.py copies an explicit allowlist (docs/*.html and the static files
they reference) into the public org-site repo, and the hub reads its data from the private repo in the browser with a
read-only token. Checks:
1. the allowlist never takes a Markdown, JSON, CSV, YAML, token, status, analytics or boards file, follows the references a
   page, style sheet and manifest make, and on the real docs/ holds the hub, the legal pages and the callbacks;
2. the real script against a local bare repo: copies, removes stray files, writes .nojekyll, commits as Quickplay Studio only
   when something changed, retries a refused push, exits 0 with no secret or no public repo, leaves other files alone;
3. the workflow file (name, triggers, secret, no way to dump secrets) and the secret on config.json's allowlist and in audit.yml;
4. the hub and its sister pages have no raw.githubusercontent.com read left, use the contents API with the token, wrap every
   storage access in try/catch;
5. keys.py: HUB_PUSH_TOKEN is probed with one GET on the public repo, its end date read from the GitHub header, missing shows
   without an issue, ending within 14 days raises the one needs-charlie issue;
6. in a browser (skipped where Playwright is missing): the token panel, Save, Forget, a refused token, files that are simply
   missing, the 14-day banner, and the clips and submit pages;
7. no em or en dash in the files this change touched.
GitHub is never contacted."""
import datetime as dt, json, os, pathlib, re, shutil, subprocess, sys, tempfile
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
import pages_sync as P
import keys as K
SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="qp-pages-"))
EM, EN = chr(0x2014), chr(0x2013)

# 1. the allowlist --------------------------------------------------------------------------------------------------
D = SCRATCH / "docs"
for rel, body in {
    "a.html": '<link rel="stylesheet" href="style.css"><img src="./pic.png"><script src="app.js"></script><a href="NOTES.md">n</a>'
              '<img src="status/leak.png"><img src="../outside.png"><img src="https://example.com/remote.png"><a href="b.html">b</a>',
    "b.html": '<link rel="manifest" href="site.webmanifest"><script>fetch("data.json"); const x = "stats.csv";</script>',
    "style.css": "body{background:url(fonts/f.woff2)} .x{background:url('img/bg.svg?v=2')}",
    "app.js": 'const icon = "icon.ico";',
    "site.webmanifest": json.dumps({"icons": [{"src": "m-192.png"}, {"src": "m-512.png"}], "start_url": "b.html"}),
    "pic.png": "png", "fonts/f.woff2": "f", "img/bg.svg": "<svg/>", "icon.ico": "i", "m-192.png": "1", "m-512.png": "2", "orphan.png": "not referenced by any page",
    "NOTES.md": "# notes", "data.json": "{}", "stats.csv": "a,b", "secret.txt": "keep out", "outside.png": "no",
    "status/leak.png": "no", "status/x.json": "{}", "analytics/y.csv": "a", "tokens/t.enc": "x", "boards/q.json": "{}",
    "sub/page.html": "<p>not top level</p>", ".hidden.png": "no",
    "tiktokABC123.txt": "tiktok-developers-site-verification=ABC123", "tiktokFAKE.txt": "just some text", "config.json": "{}",
}.items():
    f = D / rel; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(body)
(D / "a.html").write_text((D / "a.html").read_text() + '<img src="orphan-not-there.png">')
got = P.allowlist(D)
want = ["a.html", "app.js", "b.html", "fonts/f.woff2", "icon.ico", "img/bg.svg", "m-192.png", "m-512.png", "pic.png", "site.webmanifest", "style.css", "tiktokABC123.txt"]
assert got == want, (got, sorted(set(got) ^ set(want)))
for bad in ("NOTES.md", "data.json", "stats.csv", "secret.txt", "status/leak.png", "status/x.json", "analytics/y.csv", "tokens/t.enc", "boards/q.json",
            "sub/page.html", "outside.png", "orphan.png", ".hidden.png", "config.json", "tiktokFAKE.txt"):
    assert bad not in got, bad
for rel in ("x.md", "a/b.json", "c.csv", "d.yml", "e.py", "f.log", "status/a.png", "analytics/a.html", "tokens/a.html", "boards/a.png", "clips/a.png", "../a.png", ".env", "a/.git/x.png"):
    assert P.never(rel), rel
for rel in ("hub.html", "pic.png", "img/bg.svg", "submit.webmanifest", "tiktokABC.txt"):
    assert not P.never(rel), rel
try: P.sync(D, SCRATCH / "nowhere", ["NOTES.md"]); raise SystemExit("sync took a Markdown file")
except AssertionError: pass
real = P.allowlist(REPO / "docs")
for name in ("hub.html", "index.html", "privacy.html", "terms.html", "youtube-callback.html", "tiktok-callback.html", "clips.html", "submit.html",
             "submit.webmanifest", "submit-icon-180.png", "submit-icon-512.png"):
    assert name in real, (name, real)
assert all(not P.never(r) and not re.search(r"\.(md|json|csv|ya?ml|py|log|enc)$", r) and not re.match(r"(status|analytics|tokens|boards|clips)/", r) for r in real), real
assert all(r.endswith((".html", ".png", ".webmanifest")) or P.VERIFY.fullmatch(r) for r in real), real          # nothing else is in docs/ that a page uses
print("1 allowlist ok", len(real), "files")

# 2. the real script against a local bare repo --------------------------------------------------------------------
GIT = lambda *a, cwd=None: subprocess.run(["git", *a], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()
BARE = SCRATCH / "site.git"
GIT("init", "-q", "--bare", "-b", "main", str(BARE))
(BARE / "hooks" / "pre-receive").write_text('#!/bin/sh\n[ -f "$GIT_DIR/refuse" ] && { n=$(cat "$GIT_DIR/refuse"); [ "$n" -gt 0 ] && { echo $((n-1)) > "$GIT_DIR/refuse"; echo refused >&2; exit 1; }; }\nexit 0\n')
os.chmod(BARE / "hooks" / "pre-receive", 0o755)


def run(token="t0ken", docs=D, remote=None, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("HUB_PUSH_TOKEN",)}
    env.update(PAGES_DOCS=str(docs), PAGES_REMOTE=remote or BARE.as_uri(), PAGES_RETRY_PAUSE="0", **extra)
    if token is not None: env["HUB_PUSH_TOKEN"] = token
    return subprocess.run([sys.executable, str(REPO / "pipeline" / "pages_sync.py")], env=env, text=True, capture_output=True, cwd=SCRATCH)


def view():
    d = SCRATCH / "view"; shutil.rmtree(d, ignore_errors=True); GIT("clone", "-q", BARE.as_uri(), str(d))
    return d, sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and ".git/" not in p.as_posix())


r = run(token=None); assert r.returncode == 0 and "HUB_PUSH_TOKEN is not set" in r.stdout and r.stdout.strip().count("\n") == 0, (r.returncode, r.stdout, r.stderr)
r = run(token="  "); assert r.returncode == 0 and "HUB_PUSH_TOKEN is not set" in r.stdout
r = run(remote=(SCRATCH / "no-such-repo.git").as_uri()); assert r.returncode == 0 and "not there yet" in r.stdout and r.stdout.strip().count("\n") == 0, (r.returncode, r.stdout, r.stderr)
assert "t0ken" not in r.stdout + r.stderr

r = run()                                                   # an empty public repo: the first push makes main
assert r.returncode == 0 and "now holds 12 files" in r.stdout, (r.stdout, r.stderr)
view_dir, files = view()
assert files == sorted([".nojekyll"] + ["quickplay-autopilot/" + w for w in want]), files
assert (view_dir / ".nojekyll").read_text() == ""
assert (view_dir / "quickplay-autopilot" / "pic.png").read_text() == "png"
who = GIT("log", "-1", "--format=%an <%ae>|%cn <%ce>", cwd=view_dir)
assert who == "Quickplay Studio <quickplay-studio@users.noreply.github.com>|Quickplay Studio <quickplay-studio@users.noreply.github.com>", who
n_commits = int(GIT("rev-list", "--count", "HEAD", cwd=view_dir))

r = run(); assert r.returncode == 0 and "nothing to push" in r.stdout, r.stdout                     # nothing changed: no commit
assert int(GIT("rev-list", "--count", "HEAD", cwd=view(  )[0])) == n_commits

# a stray file in the folder, an old page that has left docs/, other files in the public repo, and a changed page
work = SCRATCH / "edit"; GIT("clone", "-q", BARE.as_uri(), str(work))
(work / "quickplay-autopilot" / "old.md").write_text("# stray"); (work / "quickplay-autopilot" / "status").mkdir(); (work / "quickplay-autopilot" / "status" / "x.json").write_text("{}")
(work / "README.md").write_text("the org site"); (work / "other").mkdir(); (work / "other" / "keep.html").write_text("keep")
GIT("add", "-A", cwd=work); GIT("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "stray", cwd=work); GIT("push", "-q", "origin", "HEAD:main", cwd=work)
(D / "b.html").unlink(); (D / "a.html").write_text("<p>changed</p>")
want2 = ["a.html", "tiktokABC123.txt"]
assert P.allowlist(D) == want2, P.allowlist(D)
r = run(); assert r.returncode == 0 and "now holds 2 files" in r.stdout, (r.stdout, r.stderr)
_, files = view()
assert files == sorted([".nojekyll", "README.md", "other/keep.html"] + ["quickplay-autopilot/" + w for w in want2]), files       # strays and old pages gone, the rest untouched

# a refused push is retried (pull, rebase, push), up to 3 times, then the run fails with one clear line
(D / "a.html").write_text("<p>changed again</p>"); (BARE / "refuse").write_text("1")
r = run(); assert r.returncode == 0 and "push 1 of 3 was refused" in r.stdout and "now holds" in r.stdout, (r.stdout, r.stderr)
assert (view()[0] / "quickplay-autopilot" / "a.html").read_text() == "<p>changed again</p>"
(D / "a.html").write_text("<p>and again</p>"); (BARE / "refuse").write_text("9")
r = run(); assert r.returncode == 1 and "push 3 of 3 was refused" in r.stdout and "could not push" in r.stdout, (r.returncode, r.stdout)
(BARE / "refuse").unlink()
print("2 sync ok")

# 3. the workflow file --------------------------------------------------------------------------------------------------
wf = (REPO / ".github" / "workflows" / "pages.yml").read_text()
assert wf.startswith("name: pages\n"), "the workflow keeps its name"
assert re.search(r"^on:\n  push:\n    branches: \[main\]\n    paths: \[[^\]]*'docs/\*\*'", wf, re.M) and "workflow_dispatch:" in wf, "push on docs/** and Run workflow"
cron = re.findall(r"^\s*-\s*cron:\s*'([^']+)'", wf, re.M); assert len(cron) == 1 and re.fullmatch(r"\d+ \d+ \* \* \*", cron[0]) and not cron[0].startswith(("0 ", "30 ")), cron
assert "secrets.HUB_PUSH_TOKEN" in wf and "pipeline/pages_sync.py" in wf and not re.search(r"toJSON\s*\(\s*secrets", wf)
assert "actions/deploy-pages" not in wf and "upload-pages-artifact" not in wf, "no Pages deployment from the private repo any more"
assert "pages: write" not in wf and "id-token" not in wf
cfg = json.loads((REPO / "config.json").read_text())
assert "HUB_PUSH_TOKEN" in cfg["accounts"]["secrets"], "identity.py: a secret not on the list stops the posting workflows"
import identity as I
bad = [c for c in I.secret_checks() if not c.get("ok")]
assert not bad, bad
assert "HUB_PUSH_TOKEN: ${{ secrets.HUB_PUSH_TOKEN }}" in (REPO / ".github" / "workflows" / "audit.yml").read_text(), "the key check gets the secret"
print("3 workflow ok")

# 4. the hub and the pages that read the repository --------------------------------------------------------------------
hub = (REPO / "docs" / "hub.html").read_text()
for name in ("hub.html", "clips.html", "submit.html", "index.html", "privacy.html", "terms.html", "tiktok.html", "youtube-callback.html", "tiktok-callback.html"):
    assert "raw.githubusercontent.com" not in (REPO / "docs" / name).read_text(), name + " still reads raw.githubusercontent.com"
assert "api.github.com/repos/quickplay-studio/quickplay-autopilot" in hub and "/contents/${path}?ref=main" in hub
assert '"application/vnd.github.raw"' in hub and 'cache: "no-store"' in hub and '"Bearer " + TOKEN' in hub and '"qp_hub_token"' in hub
assert "personal-access-tokens/new" in hub and 'type="password"' in hub and "Forget token" in hub and "github-authentication-token-expiration" in hub
for name in ("hub.html", "clips.html", "submit.html"):
    text = (REPO / "docs" / name).read_text()
    for line in text.splitlines():
        if re.search(r"localStorage\.", line): assert "try" in line, (name, line.strip()[:120])        # a private window or blocked storage never breaks the page
for name in ("clips.html", "submit.html"):
    text = (REPO / "docs" / name).read_text()
    assert "/contents/" in text and "?ref=main" in text and "Authorization" in text and "qp_hub_token" in text and "application/vnd.github.raw" in text, name
print("4 pages ok")

# 5. keys.py: HUB_PUSH_TOKEN ---------------------------------------------------------------------------------------------
T0 = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)
CALLS = []


class Resp:
    def __init__(self, code, headers=None, data=None): self.status_code, self.headers, self._d, self.text = code, headers or {}, data or {}, ""
    def json(self): return self._d


def getter2(code, hdr):
    def get(url, headers=None):
        CALLS.append((url, dict(headers or {}))); return Resp(code, hdr)
    return get


spec = K.PROBES["HUB_PUSH_TOKEN"]
assert spec["url"] == "https://api.github.com/repos/quickplay-studio/quickplay-studio.github.io" and spec["group"] == "Hub" and not spec.get("needed")
ENV = {"HUB_PUSH_TOKEN": "ghp-secret"}
ends_ok = "2027-06-01 10:00:00 UTC"
res = K.probe("HUB_PUSH_TOKEN", ENV, getter2(200, {"github-authentication-token-expiration": ends_ok}))
assert res["status"] == "ok" and res["ends"] == dt.datetime(2027, 6, 1, 10, 0, tzinfo=dt.timezone.utc), res
assert len(CALLS) == 1 and CALLS[0][0] == spec["url"] and CALLS[0][1]["Authorization"] == "Bearer ghp-secret", CALLS
n = len(CALLS); assert K.probe("HUB_PUSH_TOKEN", {}, getter2(200, {}))["status"] == "missing" and len(CALLS) == n, "a missing secret makes no call"
assert K.probe("HUB_PUSH_TOKEN", ENV, getter2(200, {}))["ends"] is None                                     # a token with no end date
assert K.probe("HUB_PUSH_TOKEN", ENV, getter2(401, {}))["status"] == "failing"
assert K.probe("HUB_PUSH_TOKEN", ENV, getter2(403, {}))["status"] == "failing"
r404 = K.probe("HUB_PUSH_TOKEN", ENV, getter2(404, {})); assert r404["status"] == "failing" and "cannot find the repo" in r404["detail"], r404      # the token cannot see the repo (or it is not made yet)
assert K.probe("HUB_PUSH_TOKEN", ENV, getter2(500, {}))["status"] == "unverified"
assert K.probe("MISTRAL_API_KEY", {"MISTRAL_API_KEY": "m"}, getter2(404, {}))["status"] == "unverified", "other keys keep their rule for a 404"
row = K.probe_row("HUB_PUSH_TOKEN", K.probe("HUB_PUSH_TOKEN", ENV, getter2(200, {"github-authentication-token-expiration": "2026-11-05 10:00:00 UTC"})), T0)
assert row["status"] == "expiring" and row["group"] == "Hub" and row["expires"] == "2026-11-05" and K.problem(row), row           # within 14 days: the one issue
assert any("HUB_PUSH_TOKEN" in s for s in row["fix"]) and any("quickplay-studio.github.io" in s for s in row["fix"]), row["fix"]
row = K.probe_row("HUB_PUSH_TOKEN", K.probe("HUB_PUSH_TOKEN", ENV, getter2(200, {"github-authentication-token-expiration": ends_ok})), T0)
assert row["status"] == "ok" and row["expires"] == "2027-06-01" and not K.problem(row)
rows = K.build({}, {}, {}, T0, get=getter2(200, {}))                                  # no secrets at all
miss = next(x for x in rows if x["id"] == "HUB_PUSH_TOKEN")
assert miss["status"] == "missing" and miss["group"] == "Hub" and not K.problem(miss) and miss["fix"], miss                  # shown on the hub, no issue
rows = K.build({}, ENV, {}, T0, get=getter2(200, {"github-authentication-token-expiration": "2026-11-02 00:00:00 UTC"}))
ok = next(x for x in rows if x["id"] == "HUB_PUSH_TOKEN"); assert ok["status"] == "expiring" and K.problem(ok), ok
assert K.gh_expiry("2026-11-20 10:00:00 UTC") == dt.datetime(2026, 11, 20, 10, 0, tzinfo=dt.timezone.utc) and K.gh_expiry("") is None and K.gh_expiry("soon") is None
print("5 keys ok")

# 6. in a browser --------------------------------------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
    print("6 browser: playwright missing, skipped")


def serve(state):
    """api.github.com as the browser sees it: the repo's files by the contents API, the two lists, or a refusal."""
    def route(route):
        req = route.request; url = req.url
        state["seen"].append((url, req.headers.get("authorization"), req.headers.get("accept")))
        if state.get("status") not in (None, 200): route.fulfill(status=state["status"], body='{"message": "x"}'); return
        if "/contents/" in url:
            rel = url.split("/contents/", 1)[-1].split("?")[0]
            f = REPO / rel
            if rel in state.get("missing", ()) or not f.is_file(): route.fulfill(status=404, body=""); return
            route.fulfill(status=200, body=f.read_bytes()); return
        route.fulfill(status=200, content_type="application/json", body="[]" if "/issues" in url else '{"workflow_runs": []}')
    return route


def page(pw_browser, state):
    ctx = pw_browser.new_context(viewport={"width": 390, "height": 844}); p = ctx.new_page(); errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.route("https://api.github.com/**", serve(state))
    for pat in ("https://fonts.**", "https://api.frankfurter.app/**", "https://open.er-api.com/**", "https://cdnjs.cloudflare.com/**"):
        p.route(pat, lambda r: r.abort())
    return p, errs


def settle(p, ms=2500): p.wait_for_timeout(ms)


def with_token(p, url, token="github_pat_abc", ends=None, ms=2500):
    p.goto(url); p.wait_for_timeout(300)
    p.evaluate("([t, e]) => { localStorage.setItem('qp_hub_token', t); if (e) localStorage.setItem('qp_hub_token_ends', e); }", [token, ends])
    p.reload(); settle(p, ms)


if sync_playwright:
    HUB = (REPO / "docs" / "hub.html").as_uri()
    today = dt.datetime.now(dt.timezone.utc).date()
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # no token: nothing is asked of GitHub, a panel says what to do, then Save stores it and reloads
        st = {"seen": []}; p, errs = page(b, st)
        p.goto(HUB); settle(p, 1200)
        assert st["seen"] == [], st["seen"]
        panel = p.inner_text("#auth")
        assert "needs a read-only GitHub token" in panel and "quickplay-autopilot" in panel and "Contents" in panel and "Issues" in panel and "Actions" in panel and "1 year" in panel, panel
        assert "Read-only" in panel and "quickplay-studio" in panel, panel
        assert p.get_attribute('#auth a[href^="https://github.com/settings/personal-access-tokens/new"]', "href") == "https://github.com/settings/personal-access-tokens/new"
        assert p.locator('#auth input[type="password"]').count() == 1 and p.locator("#auth button", has_text="Save").count() == 1
        assert p.is_hidden("#forget-line") and "Needs a token" in p.inner_text("#when")
        p.click("#auth button[type=submit]"); assert "Paste the token first" in p.inner_text("#auth") and st["seen"] == []
        p.fill('#auth input[name="token"]', "github_pat_abc"); p.click("#auth button[type=submit]"); settle(p)
        assert p.evaluate("() => localStorage.getItem('qp_hub_token')") == "github_pat_abc"
        assert st["seen"], "after Save the page reloads and reads"
        assert all(s[1] == "Bearer github_pat_abc" for s in st["seen"]), st["seen"][:3]
        contents = [s for s in st["seen"] if "/contents/" in s[0]]
        assert contents and all(re.fullmatch(r"https://api\.github\.com/repos/quickplay-studio/quickplay-autopilot/contents/[A-Za-z0-9_./-]+\?ref=main", s[0]) for s in contents), contents[:3]
        assert all(s[2] == "application/vnd.github.raw" for s in contents), contents[:3]
        assert not any("raw.githubusercontent.com" in s[0] for s in st["seen"])
        assert any("/issues?" in s[0] for s in st["seen"]) and any("/actions/runs" in s[0] for s in st["seen"])
        assert p.is_hidden("#auth") and p.is_visible("#forget-line"), "a token GitHub accepts shows no panel"
        # Forget token: the token and the lists kept from the private repo go
        p.click("#forget"); settle(p, 1200)
        keys = p.evaluate("() => Object.keys(localStorage)")
        assert "qp_hub_token" not in keys and not [k for k in keys if k.startswith("qp-api")], keys
        assert "needs a read-only GitHub token" in p.inner_text("#auth")
        assert not errs, errs
        p.context.close()

        # GitHub refuses the token (401, then 403): the panel says so and offers a new one
        for code in (401, 403):
            st = {"seen": [], "status": code}; p, errs = page(b, st)
            with_token(p, HUB)
            panel = p.inner_text("#auth")
            assert f"did not accept the saved token (HTTP {code})" in panel and p.locator('#auth input[type="password"]').count() == 1, panel
            assert p.is_visible("#forget-line") and not errs, errs
            p.context.close()
        # every file "not found" (a token without access to a private repo gets 404): the panel too
        st = {"seen": [], "status": 404}; p, errs = page(b, st)
        with_token(p, HUB); assert "cannot find the repository" in p.inner_text("#auth"), p.inner_text("#auth"); p.context.close()
        # one file simply missing while the rest works: no panel
        st = {"seen": [], "missing": {"clips/outreach.csv", "status/instagram.json"}}; p, errs = page(b, st)
        with_token(p, HUB); assert p.is_hidden("#auth") and not errs, (p.inner_text("#auth"), errs); p.context.close()

        # the 14-day banner (the date typed in when the token was saved; the header is not visible to pages on GitHub's CORS list)
        for days, want_text in ((5, "in 5 days"), (-1, "has ended"), (0, "within a day")):
            st = {"seen": []}; p, errs = page(b, st)
            with_token(p, HUB, ends=str(today + dt.timedelta(days=days)))
            panel = p.inner_text("#auth")
            if days < 0: assert "has ended" in panel, panel
            elif days == 0: assert "ends on" in panel and ("within a day" in panel or "in 0 day" in panel), panel
            else: assert "ends on" in panel and want_text in panel and "Make a new one before then" in panel, panel
            assert p.locator('#auth input[type="password"]').count() == 1 and not errs, errs
            p.context.close()
        st = {"seen": []}; p, errs = page(b, st)
        with_token(p, HUB, ends=str(today + dt.timedelta(days=200))); assert p.is_hidden("#auth"); p.context.close()
        # storage that throws never breaks the page
        st = {"seen": []}; p, errs = page(b, st)
        p.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});")
        p.goto(HUB); settle(p, 1200)
        assert "needs a read-only GitHub token" in p.inner_text("#auth") and not errs, (p.inner_text("#auth"), errs)
        p.fill('#auth input[name="token"]', "github_pat_abc"); p.click("#auth button[type=submit]")
        assert "would not keep it" in p.inner_text("#auth"), p.inner_text("#auth"); p.context.close()

        # the clips page and the phone page: the same token, the contents API, a pointer to the hub without it
        for name, box in (("clips.html", "#status"), ("submit.html", "#summary")):
            url = (REPO / "docs" / name).as_uri()
            st = {"seen": []}; p, errs = page(b, st)
            p.goto(url); settle(p, 1200)
            assert "read-only token" in p.inner_text(box) and p.locator(f'{box} a[href="hub.html"]').count() == 1, (name, p.inner_text(box))
            assert not [s for s in st["seen"] if "contents" in s[0]], "no token: no call"
            with_token(p, url, ms=1500)
            reads = [s for s in st["seen"] if "/contents/clips/" in s[0]]
            assert reads and all(s[1] == "Bearer github_pat_abc" and s[2] == "application/vnd.github.raw" and s[0].endswith("?ref=main") for s in reads), (name, st["seen"][:4])
            assert not any("raw.githubusercontent.com" in s[0] for s in st["seen"])
            assert "read-only token" not in p.inner_text(box), (name, p.inner_text(box))
            p.context.close()
            st = {"seen": [], "status": 404}; p, errs = page(b, st)
            with_token(p, url, ms=1500); assert "read-only token" in p.inner_text(box) and p.locator(f'{box} a[href="hub.html"]').count() == 1, (name, p.inner_text(box)); p.context.close()
        b.close()
    print("6 browser ok")

# 7. no em or en dash in what this change touched -----------------------------------------------------------------------
for rel in ("pipeline/pages_sync.py", ".github/workflows/pages.yml", ".github/workflows/audit.yml", "docs/hub.html", "docs/clips.html", "docs/submit.html",
            "pipeline/keys.py", "tests/test_pages.py", "tests/test_hub_api.py", "tests/test_hub_actions.py", "CLAUDE.md"):
    text = (REPO / rel).read_text()
    assert EM not in text and EN not in text, rel + " has an em or en dash"
print("7 dashes ok")
print("pages ok")
