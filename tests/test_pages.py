"""Offline test of the public hub (30 October 2026). The repository is public again, so GitHub Pages serves docs/ straight from
this repo and the hub, the clips page and the phone page read their data from raw.githubusercontent.com with no token. Checks:
1. pages.yml publishes docs/ and nothing else (sparse checkout and upload path are docs, no secret, no data file in docs/),
   and the private-repo copy (pipeline/pages_sync.py, HUB_PUSH_TOKEN) is gone from the workflow, config.json, keys.py and the
   audit; identity.py still passes on the secrets the workflows read;
2. the pages read raw.githubusercontent.com, never the contents API; an OPTIONAL token (localStorage qp_hub_token) is sent to
   api.github.com only; every storage access is in a try/catch;
3. in a browser (skipped where Playwright is missing), with the repo root served by http.server, raw.githubusercontent.com routed
   to the local files and api.github.com stubbed: with no token every tab renders with no console error and nothing asks for a
   token; the upgrades show real numbers from the repo files (loop vs frozen control, sameness, the test round's luck check and
   confirming winners, the joint model, subscribers a day, views at 7 days, feed share, the FreeLLMAPI router and its optional
   keys); a missing file shows "Not available yet" and breaks nothing; a saved token goes on api.github.com calls only, a refused
   token is dropped, a rate limit shows a one-line note; the clips page and the phone page load the same way;
4. no em or en dash in what this change touched.
GitHub is never contacted."""
import csv, functools, http.server, json, pathlib, re, sys, threading
REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
EM, EN = chr(0x2014), chr(0x2013)
RAWBASE = "https://raw.githubusercontent.com/quickplay-studio/quickplay-autopilot/main/"

# 1. the workflow and the private-repo leftovers ----------------------------------------------------------------------------
wf = (REPO / ".github" / "workflows" / "pages.yml").read_text()
assert wf.startswith("name: pages\n"), "the workflow keeps its name"
assert re.search(r"paths: \['docs/\*\*'\]", wf) and "workflow_dispatch:" in wf and "schedule:" not in wf, "a push on docs/** or Run workflow"
assert re.search(r"sparse-checkout: docs\b", wf) and re.search(r"upload-pages-artifact@v\d+\n\s+with: \{ path: docs \}", wf), "only docs/ is checked out and uploaded"
assert "actions/deploy-pages" in wf and "build_type" in wf, "deploys only when Pages is set to GitHub Actions"
assert "secrets." not in wf and "pages_sync" not in wf and "HUB_PUSH_TOKEN" not in wf, "no secret and no copy to another repo"
assert not (REPO / "pipeline" / "pages_sync.py").exists(), "pages_sync.py is gone"
for rel in ("config.json", "pipeline/keys.py", ".github/workflows/audit.yml", ".github/workflows/pages.yml", "docs/hub.html", "docs/clips.html", "docs/submit.html"):
    assert "HUB_PUSH_TOKEN" not in (REPO / rel).read_text(), rel + " still mentions HUB_PUSH_TOKEN"
data = [p.name for p in (REPO / "docs").iterdir() if p.suffix.lower() in (".csv", ".json", ".yml", ".yaml", ".env", ".pem", ".key")]
assert not data, "docs/ is published whole, so it holds no data file: " + ", ".join(data)
import identity as I
bad = [c for c in I.secret_checks() if not c.get("ok")]
assert not bad, bad
print("1 workflow ok")

# 2. the pages' source ------------------------------------------------------------------------------------------------------
hub = (REPO / "docs" / "hub.html").read_text()
assert 'const RAW = "https://raw.githubusercontent.com/quickplay-studio/quickplay-autopilot/main/"' in hub and "/contents/" not in hub
assert "personal-access-tokens" not in hub and 'type="password"' not in hub and "Forget token" not in hub, "no token panel"
assert hub.count("Authorization") == 1 and '"Authorization": "Bearer " + TOKEN' in hub, "the token has one place to go"
assert 'fetch(RAW + path' in hub and "fetch(API + path, {headers: apiHeaders(" in hub, "files from raw, the lists from the API with the optional token"
for name in ("hub.html", "clips.html", "submit.html"):
    text = (REPO / "docs" / name).read_text()
    assert "raw.githubusercontent.com" in text, name
    if name != "hub.html": assert "Authorization" not in text and "qp_hub_token" not in text and "/contents/" not in text, name
    for line in text.splitlines():
        if re.search(r"localStorage\.", line): assert "try" in line, (name, line.strip()[:120])        # a private window or blocked storage never breaks the page
print("2 pages ok")

# 3. in a browser -----------------------------------------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
    print("3 browser: playwright missing, skipped")


def rows(rel): return list(csv.DictReader(open(REPO / rel, newline="")))
def fnum(x): return f"{round(float(x)):,}"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


def serve_repo():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(REPO)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def new_page(browser, state, init=None):
    """A phone-sized page: raw.githubusercontent.com is the local files (state["override"] replaces a file, state["missing"] hides one),
    api.github.com is the two lists (state["api"] picks the answer), everything else is answered quietly."""
    ctx = browser.new_context(viewport={"width": 390, "height": 844}); p = ctx.new_page(); errs = []
    if init: ctx.add_init_script(init)
    p.on("pageerror", lambda e: errs.append("pageerror " + str(e)))
    p.on("console", lambda m: errs.append("console " + m.text) if m.type == "error" else None)

    def raw(route):
        req = route.request; state["raw"].append((req.url, req.headers.get("authorization")))
        rel = req.url.split("/main/", 1)[-1].split("?")[0]
        if rel in state["override"]: route.fulfill(status=200, body=state["override"][rel]); return
        f = REPO / rel
        if rel in state["missing"] or not f.is_file(): route.fulfill(status=404, body=""); return
        route.fulfill(status=200, body=f.read_bytes())

    def api(route):
        req = route.request; auth = req.headers.get("authorization"); state["api"].append((req.url, auth))
        mode = state["mode"]
        if mode == "limit": route.fulfill(status=403, headers={"x-ratelimit-reset": "4102444800", "x-ratelimit-remaining": "0", "access-control-expose-headers": "x-ratelimit-reset, x-ratelimit-remaining"}, body='{"message": "API rate limit exceeded"}'); return
        if mode == "refuse" and auth: route.fulfill(status=401, body='{"message": "Bad credentials"}'); return
        route.fulfill(status=200, content_type="application/json", body="[]" if "/issues" in req.url else '{"workflow_runs": []}')
    p.route(RAWBASE + "**", raw); p.route("https://api.github.com/**", api)
    p.route("https://api.frankfurter.app/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"rates": {"GBP": 0.75}}'))
    p.route("https://fonts.**", lambda r: r.fulfill(status=200, content_type="text/css", body=""))
    p.route("https://cdnjs.cloudflare.com/**", lambda r: r.fulfill(status=200, content_type="application/javascript", body=""))
    p.route("**/favicon.ico", lambda r: r.fulfill(status=204, body=""))
    return p, errs


def fresh(**kw): return {"raw": [], "api": [], "override": {}, "missing": set(), "mode": "ok", **kw}


TABS = ["overview", "insights", "shorts", "learning", "clips", "scout", "accounts", "export"]


def load_hub(p, url):
    p.goto(url); p.wait_for_function("document.getElementById('when').textContent.startsWith('Updated')", timeout=20000)


def tab(p, name):
    p.click(f'#tabs [data-tab="{name}"]'); p.wait_for_timeout(120)
    return p.inner_text(f"#{name}")


if sync_playwright:
    srv, base = serve_repo(); HUB = base + "/docs/hub.html"
    shorts = rows("analytics/shorts.csv"); tests = json.loads((REPO / "analytics/tests.json").read_text())
    imp = json.loads((REPO / "analytics/improvement.json").read_text()); ctl = imp["control"]
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        # no token: everything loads, every tab renders, nothing asks for a token
        st = fresh(); p, errs = new_page(b, st); load_hub(p, HUB)
        text = {}
        for t in TABS:
            text[t] = tab(p, t)
            assert len(text[t]) > 60 and "undefined" not in text[t] and "[object" not in text[t] and "NaN" not in text[t], (t, text[t][:300])
        assert not errs, errs
        body = p.inner_text("body")
        assert p.locator("#auth, input[type=password], #forget-line").count() == 0 and not re.search(r"needs a (read-only )?(github )?token|read-only token", body, re.I), "nothing asks for a token"
        assert p.inner_text("#when").startswith("Updated"), p.inner_text("#when")
        assert st["raw"] and all(a is None for _, a in st["raw"]) and all(a is None for _, a in st["api"]), "no token: no Authorization anywhere"
        assert not [u for u, _ in st["api"] if "/contents/" in u] and {u.split("/main/")[-1].split("?")[0] for u, _ in st["raw"]} >= {"analytics/summary.json", "analytics/joint.csv", "analytics/sameness.csv", "analytics/subs_daily.csv", "analytics/subs_model.md", "analytics/improvement.json", "config.json"}

        # Overview: loop vs frozen control and sameness
        ov = text["overview"]
        assert "Loop vs frozen control" in ov and f"{ctl['n_loop']} loop Shorts against {ctl['n_control']} control Shorts ({ctl['min_n']} needed)" in ov and ctl["verdict"] in ov, ov[ov.find("Loop vs"):][:400]
        sm = rows("analytics/sameness.csv"); last = {}
        for r in sm: last[r["channel"]] = max(last.get(r["channel"], r), r, key=lambda x: x["day"])
        sc = p.inner_text("#sameness-card")
        assert "alert at 0.20" in sc and "cap 35%" in sc and "analytics/sameness.md" in sc, sc[:300]
        for r in last.values(): assert f"{float(r['score']):.3f}" in sc and f"{float(r['share']) * 100:.1f}%" in sc, (r, sc)
        assert p.locator('#sameness-card a[href$="/analytics/sameness.md"]').count() == 1

        # Insights: the round's luck check, the joint model, subscribers a day
        ins = text["insights"]
        for f, x in tests["factors"].items():
            if x.get("p") not in ("", None): assert f"p {x['p']}, q {x['q']}" in ins, (f, x["p"], x["q"])
        assert "Joint model" in ins and "analytics/joint.md" in ins and p.locator('#insights a[href$="/analytics/joint.md"]').count() == 1
        main = [r for r in rows("analytics/joint.csv") if r["kind"] == "main"]; best = {}
        for r in main:
            k = (r["factor"], r["outcome"])
            if k not in best or float(r["effect"]) > float(best[k]["effect"]): best[k] = r
        top = sorted(best.values(), key=lambda r: -float(r["effect"]))[:8]
        jtab = p.locator("#insights table").filter(has_text="Better arm").first; jt = jtab.inner_text()
        assert f"{float(top[0]['effect']):.2f}x" in jt and top[0]["level"] in jt and top[0]["factor"].replace("_", " ") in jt and jtab.locator("tbody tr").count() == len(top) == 8, jt
        assert "Gaming: held back" in ins and "fails" in ins, "a clear interaction that fails the luck check says so"
        sd = rows("analytics/subs_daily.csv"); lastday = max(r["day"] for r in sd)
        import datetime as dt
        first = (dt.date.fromisoformat(lastday) - dt.timedelta(days=13)).isoformat()
        gained = sum(int(r["subs_gained"]) for r in sd if first <= r["day"] <= lastday)
        sub = ins[ins.find("Subscribers a day, by channel"):ins.find("Tests being run")]
        assert f"Subscribers gained\n{gained}" in sub.replace("\n\n", "\n") or str(gained) in sub, (gained, sub[:300])
        model = (REPO / "analytics/subs_model.md").read_text()
        if "Not enough yet" in model:
            used = re.search(r"Channel-days used: (\d+)", model).group(1)
            assert "Needs 20 channel-days" in sub and "has " + used in sub, sub[:500]
        assert p.locator('#insights a[href$="/analytics/subs_model.md"]').count() == 1

        # Daily Shorts: views at 7 days
        newest = sorted(shorts, key=lambda r: r["posted"], reverse=True)[:40]; v7 = [r for r in newest if r["views_7d"] != ""]
        assert "7 days" in text["shorts"] and (not v7 or any(fnum(r["views_7d"]) in text["shorts"] for r in v7)), "views at 7 days"

        # Accounts: the router and its optional keys with their add-secret links
        acc = text["accounts"]
        assert "FreeLLMAPI router" in acc
        for k in ("TAVILY_API_KEY", "EXA_API_KEY", "FIRECRAWL_API_KEY", "LINKUP_API_KEY", "OLLAMA_API_KEY", "LLM7_API_KEY"):
            assert p.locator("#accounts").evaluate("(el, k) => el.innerHTML.includes(k)", k), k
        assert p.locator('#accounts a[href$="/settings/secrets/actions/new"]').count() >= 6
        ex = p.locator("#export-list").text_content()
        assert "analytics/sameness.md" in ex and "analytics/joint.md" in ex and "analytics/subs_model.md" in ex, "the export for Claude carries the new files"
        p.context.close()

        # the luck check, a confirming winner and the feed share, which the repo's files do not hold today
        t2 = json.loads(json.dumps(tests)); fs = list(t2["factors"])
        t2["factors"][fs[0]].update(verdict="running", luck="yes", effect=1.8, low=1.1, high=2.9, halves="agree", leaning="b", p=0.012, q=0.31, why="x")
        t2["factors"][fs[1]].update(verdict="confirming", confirm="question", why="3 of 20 Shorts on the smaller arm; question runs on most Shorts, the previous choice on the rest", effect=1.2, low=0.9, high=1.5)
        t2["factors"][fs[2]].update(verdict="confirmed", winner="loop", confirm="loop", why="loop is not worse than the previous choice beyond 15%", effect="", low="", high="")
        drv = (REPO / "analytics/drivers.csv").read_text().rstrip("\n") + "\ncategory,Category,Music,35,1.63,1.4,push,,,,,,74,0.01,0.05\n"
        st = fresh(override={"analytics/tests.json": json.dumps(t2), "analytics/drivers.csv": drv}); p, errs = new_page(b, st); load_hub(p, HUB)
        ins = tab(p, "insights"); card = p.inner_text("#tests-card")
        assert "running (luck check)" in card and "p 0.012, q 0.31" in card and "cannot win yet" in card, card[:600]
        assert "confirming question" in card and "3 of 20 Shorts on the smaller arm" in card and "confirmed loop" in card, card[:900]
        assert "feed 74%" in ins, "the drivers' feed share"
        assert not errs, errs; p.context.close()

        # a missing file shows "Not available yet" and breaks no tab
        gone = {"analytics/sameness.csv", "analytics/joint.csv", "analytics/subs_daily.csv", "analytics/subs_model.md", "analytics/round.csv", "config.json"}
        st = fresh(missing=gone, override={"analytics/improvement.json": json.dumps({k: v for k, v in imp.items() if k != "control"})}); p, errs = new_page(b, st); load_hub(p, HUB)
        ov, ins = tab(p, "overview"), tab(p, "insights")
        assert ov.count("Not available yet") >= 2 and ins.count("Not available yet") >= 2, (ov.count("Not available yet"), ins.count("Not available yet"))
        for t in TABS: assert len(tab(p, t)) > 60, t
        assert all(e.startswith("console Failed to load resource") and "404" in e for e in errs), errs          # the browser logs each missing file, nothing else
        p.context.close()

        # an optional token: on api.github.com calls only
        TOK = "github_pat_test"
        init = f"try {{ localStorage.setItem('qp_hub_token', '{TOK}'); }} catch (e) {{}}"
        st = fresh(); p, errs = new_page(b, st, init); load_hub(p, HUB)
        assert st["api"] and all(a == "Bearer " + TOK for _, a in st["api"]), st["api"]
        assert st["raw"] and all(a is None for _, a in st["raw"]), "the token never goes to the raw files"
        assert len(tab(p, "overview")) > 400 and not errs and p.locator("#auth").count() == 0; p.context.close()
        # a token GitHub refuses is dropped: the lists still come, nothing is blocked
        st = fresh(mode="refuse"); p, errs = new_page(b, st, init); load_hub(p, HUB)
        assert any(a for _, a in st["api"]) and any(a is None for _, a in st["api"]), "tried with the token, then without it"
        assert not [e for e in errs if e.startswith("pageerror")] and len(tab(p, "overview")) > 400 and "No alerts" in p.inner_text("#overview"), errs        # the browser logs GitHub's 401 itself
        p.context.close()
        # the 60-an-hour limit: one line, the page still works
        st = fresh(mode="limit"); p, errs = new_page(b, st); load_hub(p, HUB)
        ov = tab(p, "overview")
        assert "allowance for this connection is used up" in ov and ov.count("allowance for this connection is used up") <= 2 and len(ov) > 400, ov[:300]
        assert not [e for e in errs if e.startswith("pageerror")], errs
        p.context.close()
        # storage that throws never breaks the page
        st = fresh(); p, errs = new_page(b, st, "Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});"); load_hub(p, HUB)
        assert len(tab(p, "overview")) > 400 and not [e for e in errs if e.startswith("pageerror")], errs; p.context.close()

        # the clips page and the phone page
        st = fresh(); p, errs = new_page(b, st); p.goto(base + "/docs/clips.html"); p.wait_for_function("document.getElementById('status').textContent.startsWith('Updated')", timeout=15000)
        assert p.locator("#clips tbody tr").count() == len([r for r in rows("clips/stats.csv") if r["privacy"] == "public"]) and "token" not in p.inner_text("body").lower() and not errs, errs
        assert all(a is None for _, a in st["raw"]) and {u.split("/main/")[-1].split("?")[0] for u, _ in st["raw"]} >= {"clips/stats.csv", "clips/campaigns.json", "clips/submit.csv"}
        p.context.close()
        st = fresh(); p, errs = new_page(b, st); p.goto(base + "/docs/submit.html"); p.wait_for_function("!document.getElementById('summary').textContent.startsWith('Loading')", timeout=15000)
        summ = p.inner_text("#summary")
        assert ("link" in summ or "All done" in summ) and "token" not in p.inner_text("body").lower() and "Couldn't load" not in summ and not errs, (summ, errs)
        assert all(a is None for _, a in st["raw"]) and any(u.endswith("clips/submit.csv") or "clips/submit.csv?" in u for u, _ in st["raw"]); p.context.close()
        b.close()
    srv.shutdown()
    print("3 browser ok")

# 4. no em or en dash in what this change touched -----------------------------------------------------------------------------
for rel in (".github/workflows/pages.yml", ".github/workflows/audit.yml", "docs/hub.html", "docs/clips.html", "docs/submit.html", "pipeline/keys.py",
            "tests/test_pages.py", "tests/test_hub_api.py", "tests/test_hub_actions.py", "CLAUDE.md"):
    text = (REPO / rel).read_text()
    assert EM not in text and EN not in text, rel + " has an em or en dash"
print("4 dashes ok")
print("pages ok")
