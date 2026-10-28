"""Offline browser test of the hub's live action list and Keys panel (24 October): Overview "Your actions this week" hides done
items, lists the ones done in the last 7 days in a "Done this week" line, shows what a check last said and the issue to close,
and does not list an issue twice when an item already links to it; the Accounts tab lists every key from status/keys.json
(problems first, their steps open) and nothing new is kept in localStorage. Uses the preinstalled Chromium; skipped where
Playwright is missing."""
import datetime as dt, json, pathlib, sys, time
REPO = pathlib.Path(__file__).resolve().parent.parent
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("hub actions: playwright missing, skipped"); sys.exit(0)

now = dt.datetime.now(dt.timezone.utc)
iso = lambda d: d.isoformat(timespec="minutes")
today = now.astimezone(dt.timezone(dt.timedelta(0))).date()


def item(id, **kw):
    d = {"id": id, "title": f"Title of {id}", "why": f"Why {id}", "steps": [f"Step one of {id} at https://example.com/{id}"], "links": [], "added": "2026-10-24", "due": "", "done": False}
    d.update(kw); return d


ACTIONS = [
    item("open-check", title="Optional, free: a Mistral key (one more writing model)", check="secret_works:MISTRAL_API_KEY", note="MISTRAL_API_KEY is not set yet", short="Mistral key"),
    item("open-issue", title="Check the Facebook Page", due=str(today + dt.timedelta(days=2)), issue=41),
    item("daily", title="Leave the Mac awake", repeat="every day", check="vyro_today", done=True, done_at=iso(now), done_by="check", short="Mac awake for Vyro"),
    item("done-check", title="Optional, free: a Cloudflare Workers AI key (one more writing model)", short="Cloudflare key", check="secret_works:CF_API_TOKEN", done=True, done_at=iso(now - dt.timedelta(days=2)), done_by="check"),
    item("done-issue", title="Find out why TikTok restricted the account", short="TikTok status", done=True, done_at=iso(now - dt.timedelta(days=1)), done_by="issue", issue=43),
    item("done-old", title="An old finished thing", short="Old thing", done=True, done_at=iso(now - dt.timedelta(days=12)), done_by="check"),
    item("later", title="Renew something far off", due=str(today + dt.timedelta(days=40)), issue=44),
]
ISSUES = [
    {"number": 41, "title": "Check the Facebook Page", "html_url": "https://github.com/x/41", "created_at": iso(now), "updated_at": iso(now), "labels": [{"name": "alert"}, {"name": "needs-charlie"}]},
    {"number": 50, "title": "Fix needed: YouTube sign-in: Quickplay Gaming Clips", "html_url": "https://github.com/x/50", "created_at": iso(now), "updated_at": iso(now), "labels": [{"name": "alert"}, {"name": "needs-charlie"}]},
    {"number": 51, "title": "An ordinary alert", "html_url": "https://github.com/x/51", "created_at": iso(now), "updated_at": iso(now), "labels": [{"name": "alert"}]},
]
KEYS = {"checked": iso(now), "audit": iso(now), "counts": {"ok": 2, "expiring": 1, "failing": 1, "missing": 1}, "keys": [
    {"id": "youtube", "what": "YouTube sign-in: Quickplay Daily", "group": "YouTube", "status": "ok", "expires": "", "checked": iso(now), "detail": "the refresh works", "needed": True, "fix": ["Sign in again at https://example.com/yt"]},
    {"id": "youtube_gaming", "what": "YouTube sign-in: Quickplay Gaming Clips", "group": "YouTube", "status": "failing", "expires": "", "checked": iso(now), "detail": "Google says the sign-in is expired or revoked",
     "needed": False, "fix": ["Open https://example.com/callback and press Sign in", "Copy the code"], "issue": 50},
    {"id": "IG_CLIPS_TOKEN", "what": "Instagram key: Quickplay Clips", "group": "Instagram", "status": "expiring", "expires": str(today + dt.timedelta(days=8)), "checked": iso(now), "detail": "answers as @quickplayclips", "needed": False, "fix": ["Generate a token"]},
    {"id": "FB_PAGE_TOKEN", "what": "Facebook Page key: Quickplay Daily", "group": "Facebook", "status": "ok", "expires": "2027-01-12", "checked": iso(now), "detail": "the key never ends", "needed": False, "fix": ["Make a key"]},
    {"id": "CEREBRAS_API_KEY", "what": "Cerebras API key (writing)", "group": "AI models", "status": "missing", "expires": "", "checked": iso(now), "detail": "the secret is not set", "needed": False, "fix": ["Create a key"]}]}
OVERRIDE = {"status/actions.json": json.dumps(ACTIONS), "status/keys.json": json.dumps(KEYS)}


def raw(route):
    rel = route.request.url.split("/contents/", 1)[-1].split("?")[0]
    if rel in OVERRIDE: route.fulfill(status=200, body=OVERRIDE[rel]); return
    f = REPO / rel
    if f.is_file(): route.fulfill(status=200, body=f.read_bytes())
    else: route.fulfill(status=404, body="")


def api(route):
    if "/contents/" in route.request.url: raw(route); return
    if "/actions/runs" in route.request.url: route.fulfill(status=200, content_type="application/json", body=json.dumps({"workflow_runs": []}))
    else: route.fulfill(status=200, content_type="application/json", body=json.dumps(ISSUES))


with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={"width": 390, "height": 844}); p = ctx.new_page(); errs = []
    ctx.add_init_script("try { localStorage.setItem('qp_hub_token', 'github_pat_test'); } catch (e) {}")      # the read-only token (28 October)
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.route("https://api.github.com/**", api)
    for pat in ("https://fonts.**", "https://api.frankfurter.app/**", "https://open.er-api.com/**", "https://cdnjs.cloudflare.com/**"):
        p.route(pat, lambda r: r.abort())
    p.goto((REPO / "docs" / "hub.html").as_uri()); p.wait_for_timeout(2500)
    ov = p.inner_text("#overview")
    # the open list: unfinished items, the issue Charlie has not been given an item for, the check's last words, the issue to close
    assert "Check the Facebook Page" in ov and "Fix needed: YouTube sign-in: Quickplay Gaming Clips" in ov, ov[:900]
    assert ov.count("Check the Facebook Page") == 1, "the issue an item links to is not listed a second time"
    p.evaluate("() => document.querySelectorAll('#overview details').forEach(d => d.open = true)")
    ov = p.inner_text("#overview")
    assert "Last check: MISTRAL_API_KEY is not set yet" in ov and "checks this by itself every 3 hours" in ov, ov[:1500]
    assert "close issue #41 in the GitHub app" in ov and "close issue #44 in the GitHub app" in ov, ov[:1500]
    # done items leave the list; the last 7 days show in one line
    assert "Done this week:" in ov
    line = ov.split("Done this week:")[1].strip().splitlines()[0]
    assert "Mac awake for Vyro (today)" in line and "Cloudflare key" in line and "TikTok status" in line, line
    assert "Old thing" not in ov and "Title of done-check" not in ov and "Leave the Mac awake" not in ov.split("Done this week:")[0], ov[:1500]
    # the Keys panel on the Accounts tab
    p.click('#tabs [data-tab="accounts"]'); p.wait_for_timeout(300)
    acc = p.inner_text("#accounts")
    assert "Keys" in acc and "1 failing" in acc and "1 ending soon" in acc and "2 ok" in acc and "1 not set up" in acc, acc[:700]
    order = [acc.index(s) for s in ("Quickplay Gaming Clips", "Instagram key: Quickplay Clips", "YouTube sign-in: Quickplay Daily", "Cerebras API key")]
    assert order == sorted(order), "failing first, then ending soon, then ok, then optional keys not set up"
    steps = p.locator("#accounts details[open] li").all_inner_texts()
    assert any("Sign in" in s for s in steps) and any("Generate a token" in s for s in steps), steps
    assert not any("Sign in again at" in s for s in steps), "an ok key shows no steps"
    assert p.locator('#accounts a[href$="/issues/50"]').count() == 1
    assert "Every 3 hours GitHub signs in" in acc
    stored = p.evaluate("() => Object.keys(localStorage)")
    assert all(k.startswith(("qp-api:", "qp-hub-", "qp-api-reset", "qp_hub_token")) for k in stored), stored      # caches, the token and the remembered tab and theme only
    assert not errs, errs
    # nothing to do and nothing done: the empty states read well
    OVERRIDE["status/actions.json"] = json.dumps([item("x", done=True, done_at=iso(now - dt.timedelta(days=30)), done_by="check")]); OVERRIDE["status/keys.json"] = "null"
    ISSUES.clear()
    p.evaluate("() => localStorage.clear()")           # the issues list is kept 10 minutes in the browser
    p.reload(); p.wait_for_timeout(2500)
    p.click('#tabs [data-tab="overview"]'); p.wait_for_timeout(200)
    ov = p.inner_text("#overview")
    assert "Nothing needs you this week" in ov and "Done this week" not in ov, ov[:600]
    p.click('#tabs [data-tab="accounts"]'); p.wait_for_timeout(300)
    assert "The key list is not there yet" in p.inner_text("#accounts"), p.inner_text("#accounts")[:300]
    assert not errs, errs
    b.close()
print("hub actions ok")
