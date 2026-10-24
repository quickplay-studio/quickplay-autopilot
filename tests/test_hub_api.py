"""Offline test of the hub's GitHub API use (24 October, audit L1): without a key GitHub allows 60 calls an hour per
connection, and mobile networks share one. The runs and issues answers are kept 10 minutes in the browser (a reload asks
nothing), trimmed to the fields shown; a 403 shows a note, keeps the last lists on screen and stops calls until GitHub's
reset time; the Mac panel reads docs/CHROME_LOG.md. Uses the preinstalled Chromium; skipped where Playwright is missing."""
import json, pathlib, sys, time
REPO = pathlib.Path(__file__).resolve().parent.parent
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("hub api: playwright missing, skipped"); sys.exit(0)

state = {"calls": 0, "mode": "ok"}


def raw(route):
    rel = route.request.url.split("/main/", 1)[-1].split("?")[0]
    f = REPO / rel
    if f.is_file(): route.fulfill(status=200, body=f.read_bytes())
    else: route.fulfill(status=404, body="")


def api(route):
    state["calls"] += 1
    if state["mode"] == "limit":
        route.fulfill(status=403, headers={"x-ratelimit-reset": str(int(time.time()) + 1800), "access-control-expose-headers": "x-ratelimit-reset"},
                      body='{"message": "API rate limit exceeded"}'); return
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if "/actions/runs" in route.request.url:
        body = {"workflow_runs": [{"name": "render", "html_url": "https://x", "status": "completed", "conclusion": "success",
                                   "run_started_at": now, "event": "schedule", "extra": "x" * 5000}]}
    else:
        body = [{"number": 5, "title": "Test issue", "html_url": "https://x/5", "created_at": now, "updated_at": now,
                 "labels": [{"name": "alert"}], "body": "y" * 5000}]
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


with sync_playwright() as pw:
    b = pw.chromium.launch(); p = b.new_context(viewport={"width": 390, "height": 844}).new_page(); errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.route("https://raw.githubusercontent.com/**", raw)
    p.route("https://api.github.com/**", api)
    for pat in ("https://fonts.**", "https://api.frankfurter.app/**", "https://open.er-api.com/**", "https://cdnjs.cloudflare.com/**"):
        p.route(pat, lambda r: r.abort())
    p.goto((REPO / "docs" / "hub.html").as_uri()); p.wait_for_timeout(2500)
    first = state["calls"]
    p.reload(); p.wait_for_timeout(2500)
    assert first == 2 and state["calls"] == 2, (first, state)               # a reload within 10 minutes asks nothing
    kept = p.evaluate("() => localStorage.getItem('qp-api:/actions/runs?per_page=60') || ''")
    assert '"name":"render"' in kept and "extra" not in kept and len(kept) < 400, kept[:200]
    state["mode"] = "limit"
    p.click("#refresh"); p.wait_for_timeout(2500)
    assert state["calls"] == 4, state                                        # Refresh asks again, both refused
    p.click("#refresh"); p.wait_for_timeout(2000)
    assert state["calls"] == 4, state                                        # nothing more until the reset time
    ov = p.inner_text("#overview")
    assert "allowance for this connection is used up" in ov and "render" in ov, ov[:500]
    p.click('#tabs [data-tab="accounts"]'); p.wait_for_timeout(300)
    acc = p.inner_text("#accounts")
    assert "waiting on you" in acc, acc[:400]
    assert not errs, errs
    b.close()
print("hub api ok")
