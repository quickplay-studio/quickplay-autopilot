"""Submissions (Charlie, 21 October): GitHub puts every public clip link into its campaign itself, the minute the batch
run starts (Reach wants a link within 30 minutes; Content Rewards counts views from the submission). It uses the studio
account's saved logins: the repository secrets WHOP_COOKIES (contentrewards.com and whop.com) and VYRO_COOKIES
(app.vyro.com), the cookies.txt that the "Get cookies.txt LOCALLY" extension exports (Playwright's JSON works too).
A headless browser opens the campaign page, presses Submit clip (Content Rewards) or Submit post (Vyro), pastes the link,
confirms and reads the page's answer. Each row of clips/submit.csv gets the time it was submitted, or "failed: why"
(kept on the phone page and tried again next run, with a screenshot in status/submit_<site>.png and the page's buttons in
the log, so the steps can be fixed). An expired login raises a GitHub issue (alerts.py) and closes it once it works.
  python pipeline/submit.py            every row due        SUBMIT_DRY=1: open the pages and report, press nothing
"""
import csv, datetime as dt, json, os, pathlib, re, sys, time
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
SITES = {"Content Rewards": {"secret": "WHOP_COOKIES", "hosts": ("contentrewards.com", "whop.com"), "home": "https://contentrewards.com/"},
         "Vyro": {"secret": "VYRO_COOKIES", "hosts": ("vyro.com",), "home": "https://app.vyro.com/campaigns"}}
VYRO_ADD = "https://app.vyro.com/campaigns/add-clips"
SUCCESS = re.compile(r"\b(submitted|pending|under review|in review|success|received|thank you|thanks|added|tracking)\b", re.I)
DUP = re.compile(r"already (been )?(submitted|added|exists|tracked)|duplicate", re.I)
ERROR = re.compile(r"\b(invalid|not (allowed|eligible|valid|found|public)|must be|private|could not|couldn't|cannot|can't|error|unsupported|does not match|doesn't match)\b", re.I)
LOGIN = re.compile(r"^\s*(log ?in|sign ?in|continue with (google|email)|get started)\s*$", re.I)
OPEN = re.compile(r"^\s*(submit( a| your)?( clip| post| content| video)?|add (a )?(clip|post|video)|new submission)\s*$", re.I)
CONFIRM = re.compile(r"^\s*(submit( clip| post| link| now)?|confirm|continue|done|add( clip| post)?|save|send|next)\s*$", re.I)
PLATFORMS = {"youtube": re.compile(r"you ?tube|shorts", re.I), "instagram": re.compile(r"instagram|reels?", re.I),
             "facebook": re.compile(r"facebook", re.I), "tiktok": re.compile(r"tik ?tok", re.I)}


def log(*a): print(*a, flush=True)


class Stale(Exception):
    """The site shows its login page: the saved cookies have expired."""


def site_of(c):
    return "Vyro" if "vyro" in str(c.get("platform", "")).lower() else "Content Rewards"


def cookies(text):
    """Playwright cookies from a cookies.txt export (Netscape lines, #HttpOnly_ prefixes kept) or a JSON list."""
    text = (text or "").strip()
    if not text: return []
    if text[0] in "[{":
        data = json.loads(text); data = data.get("cookies", data) if isinstance(data, dict) else data
        same = {"lax": "Lax", "strict": "Strict", "none": "None", "no_restriction": "None", "unspecified": "Lax"}
        return [{"name": c["name"], "value": c["value"], "domain": c.get("domain") or "", "path": c.get("path") or "/",
                 "expires": float(c.get("expirationDate") or c.get("expires") or -1), "httpOnly": bool(c.get("httpOnly")),
                 "secure": bool(c.get("secure")), "sameSite": same.get(str(c.get("sameSite") or "lax").lower(), "Lax")} for c in data if c.get("name")]
    out = []
    for line in text.splitlines():
        http_only = line.startswith("#HttpOnly_")
        if http_only: line = line[len("#HttpOnly_"):]
        if not line.strip() or line.startswith("#"): continue
        f = line.rstrip("\n").split("\t")
        if len(f) < 7: continue
        domain, _, path, secure, expiry, name, value = f[:7]
        out.append({"name": name, "value": value, "domain": domain, "path": path or "/",
                    "expires": float(expiry) if expiry.strip().isdigit() and int(expiry) > 0 else -1,
                    "httpOnly": http_only, "secure": secure.strip().upper() == "TRUE", "sameSite": "Lax"})
    return out


def site_cookies(site):
    raw = os.environ.get(SITES[site]["secret"], "")
    cs = [c for c in cookies(raw) if any(h in c["domain"] for h in SITES[site]["hosts"])]
    if not cs: raise RuntimeError(f"no {SITES[site]['secret']} secret: export the {site} cookies first")
    return cs


def context(play, site):
    b = play.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, user_agent=UA, locale="en-GB")
    ctx.add_cookies(site_cookies(site))
    return b, ctx


def settle(page, ms=1500):
    try: page.wait_for_load_state("networkidle", timeout=20000)
    except Exception: pass
    page.wait_for_timeout(ms)


def dialog(page):
    """The open dialog, where the form lives once Submit is pressed; the page itself otherwise."""
    try:
        loc = page.get_by_role("dialog")
        for i in range(min(loc.count(), 5)):
            if loc.nth(i).is_visible(): return loc.nth(i)
    except Exception: pass
    return page


def visible(page, role, pattern):
    """Visible elements of a role whose accessible name matches, in page order; inside the open dialog when there is one
    (a page's own Submit clip button must not be pressed twice)."""
    try: loc = dialog(page).get_by_role(role, name=pattern)
    except Exception: return []
    out = []
    for i in range(min(loc.count(), 40)):
        el = loc.nth(i)
        try:
            if el.is_visible(): out.append(el)
        except Exception: pass
    return out


def names(page, role="button"):
    out = []
    try: loc = page.get_by_role(role)
    except Exception: return out
    for i in range(min(loc.count(), 60)):
        try:
            el = loc.nth(i)
            if el.is_visible(): out.append(re.sub(r"\s+", " ", el.inner_text())[:40])
        except Exception: pass
    return out


def logged_out(page):
    if re.search(r"/(login|log-in|sign-?in|auth|signup|sign-up)(/|\?|$)", page.url): return True
    return bool(visible(page, "button", LOGIN) or visible(page, "link", LOGIN))


def click(page, pattern, roles=("button", "link", "menuitem", "tab")):
    for role in roles:
        els = visible(page, role, pattern)
        if els: els[0].click(); page.wait_for_timeout(1200); return True
    try:
        el = dialog(page).get_by_text(pattern).first
        if el.is_visible(): el.click(); page.wait_for_timeout(1200); return True
    except Exception: pass
    return False


def pick_platform(page, platform):
    """A platform choice (YouTube, Instagram, ...) when the form shows one; nothing otherwise."""
    pat = PLATFORMS.get(platform)
    if not pat: return False
    for role in ("radio", "option", "button", "tab", "menuitem", "checkbox"):
        els = visible(page, role, pat)
        if els: els[0].click(); page.wait_for_timeout(600); return True
    for sel in ("select",):
        try:
            for i in range(dialog(page).locator(sel).count()):
                s = dialog(page).locator(sel).nth(i)
                if not s.is_visible(): continue
                for o in s.locator("option").all_inner_texts():
                    if pat.search(o): s.select_option(label=o); page.wait_for_timeout(600); return True
        except Exception: pass
    return False


def link_box(page):
    """The box for the link: a URL input, or a text box whose placeholder or label mentions a link, URL or http."""
    want = re.compile(r"http|link|url|paste|post", re.I)
    for sel in ("input[type=url]", "input[type=text]", "input:not([type])", "textarea", "input[type=search]"):
        try: loc = dialog(page).locator(sel)
        except Exception: continue
        boxes = []
        for i in range(min(loc.count(), 30)):
            el = loc.nth(i)
            try:
                if not el.is_visible() or not el.is_editable(): continue
                hint = " ".join(str(el.get_attribute(a) or "") for a in ("placeholder", "aria-label", "name", "id"))
                boxes.append((bool(want.search(hint)) or sel == "input[type=url]", el))
            except Exception: pass
        for good, el in boxes:
            if good: return el
        if boxes and sel != "input[type=search]": return boxes[-1][1]       # the last box opened (a dialog's)
    return None


def texts(page):
    """What the page is saying, nearest first: alerts and toasts, the open dialog, then the whole page."""
    out = []
    for role in ("alert", "status", "dialog"):
        try:
            loc = page.get_by_role(role)
            for i in range(min(loc.count(), 5)):
                el = loc.nth(i)
                if el.is_visible(): out.append((role, re.sub(r"\s+", " ", el.inner_text())))
        except Exception: pass
    try: out.append(("body", re.sub(r"\s+", " ", page.locator("body").inner_text())))
    except Exception: pass
    return out


def outcome(page, link, wait_s=25):
    """What the page says after the confirm: 'submitted', 'already', or 'failed: ...'. An error counts only in an alert,
    a toast or the dialog (the page itself quotes rules full of 'must' and 'cannot')."""
    end = time.time() + wait_s
    while time.time() < end:
        for role, text in texts(page):
            if DUP.search(text): return "already"
            m = ERROR.search(text) if role != "body" else None
            if m: return "failed: " + text[max(0, m.start() - 60): m.end() + 80].strip()[:120]
            if SUCCESS.search(text) and (role != "body" or not visible(page, "dialog", re.compile(".*"))): return "submitted"
        page.wait_for_timeout(1000)
    return "failed: no answer from the page in %ds (buttons: %s)" % (wait_s, ", ".join(names(page)[:12]))


def submit_cr(page, row, c, dry=False):
    page.goto(row["campaign_url"], wait_until="domcontentloaded", timeout=60000); settle(page)
    if logged_out(page): raise Stale("Content Rewards")
    if dry: return "dry: logged in; buttons: " + ", ".join(names(page)[:15])
    if not click(page, OPEN): return "failed: no Submit button (buttons: %s)" % ", ".join(names(page)[:12])
    settle(page, 800)
    if logged_out(page): raise Stale("Content Rewards")
    pick_platform(page, row.get("platform") or "youtube")
    box = link_box(page)
    if box is None: return "failed: no link box after Submit (buttons: %s)" % ", ".join(names(page)[:12])
    box.fill(row["video"]); page.wait_for_timeout(800)
    pick_platform(page, row.get("platform") or "youtube")
    if not click(page, CONFIRM, roles=("button",)): box.press("Enter")
    return outcome(page, row["video"])


def submit_vyro(page, row, c, dry=False):
    page.goto(VYRO_ADD, wait_until="domcontentloaded", timeout=60000); settle(page)
    if logged_out(page): raise Stale("Vyro")
    if dry: return "dry: logged in; buttons: " + ", ".join(names(page)[:15])
    keys = [re.compile(re.escape(k), re.I) for k in dict.fromkeys([c.get("name", ""), c.get("name", "")[:24], c.get("subject", "")]) if k]
    chosen = False
    for key in keys:
        for role in ("combobox", "button", "option", "radio", "link"):
            els = visible(page, role, key)
            if els: els[0].click(); page.wait_for_timeout(800); chosen = True; break
        if chosen: break
    if not chosen:
        boxes = visible(page, "combobox", re.compile(".*"))
        if boxes:
            boxes[0].click(); page.wait_for_timeout(800)
            for key in keys:
                opts = visible(page, "option", key)
                if opts: opts[0].click(); page.wait_for_timeout(800); chosen = True; break
    if not chosen:
        for key in keys:
            try:
                el = page.get_by_text(key).first
                if el.is_visible(): el.click(); page.wait_for_timeout(800); chosen = True; break
            except Exception: pass
    if not chosen: return "failed: campaign '%s' not found on the page (buttons: %s)" % (c.get("subject"), ", ".join(names(page)[:12]))
    click(page, OPEN)
    pick_platform(page, row.get("platform") or "youtube")
    box = link_box(page)
    if box is None: return "failed: no link box (buttons: %s)" % ", ".join(names(page)[:12])
    box.fill(row["video"]); page.wait_for_timeout(800)
    pick_platform(page, row.get("platform") or "youtube")
    if not click(page, CONFIRM, roles=("button",)): box.press("Enter")
    return outcome(page, row["video"])


SUBMITTERS = {"Content Rewards": submit_cr, "Vyro": submit_vyro}


def due(rows, public_ok=None):
    """Rows with a link, public already (UK time in the row), not yet submitted or failed last time, under 3 days old."""
    out = []
    for r in rows:
        when = r.get("public_at_uk", "")
        if when.startswith("private") or not r.get("video", "").startswith("http"): continue
        if r.get("submitted") and not r["submitted"].startswith("failed"): continue
        try: t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=UK)
        except ValueError: continue
        if t > NOW or NOW - t > dt.timedelta(days=3): continue
        if public_ok and r.get("platform", "youtube") == "youtube" and not public_ok(r["video"]): continue
        out.append(r)
    return out


def youtube_public():
    """A check that a YouTube link is public now (the API), or None when no YouTube sign-in is at hand."""
    try:
        import clips as C
        yt = C.clips_client("clips")
    except Exception: return None
    cache = {}
    def ok(url):
        vid = url.rstrip("/").split("/")[-1]
        if vid not in cache:
            try:
                items = yt.videos().list(part="status", id=vid).execute().get("items", [])
                cache[vid] = bool(items) and items[0]["status"].get("privacyStatus") == "public"
            except Exception as e: log("public check:", str(e)[:120]); cache[vid] = True
        return cache[vid]
    return ok


def run(dry=False):
    import clips as C
    p = ROOT / "clips" / "submit.csv"
    rows = list(csv.DictReader(p.open())) if p.exists() else []
    todo = due(rows, None if dry else youtube_public())
    if not todo: log("submit: nothing due"); return 0
    from playwright.sync_api import sync_playwright
    done, stale, by_site = 0, set(), {}
    for r in todo: by_site.setdefault(site_of(C.CFG["campaigns"].get(r["campaign"]) or {}), []).append(r)
    with sync_playwright() as play:
        for site, rs in by_site.items():
            try: b, ctx = context(play, site)
            except Exception as e: log(f"submit: {site}: {e}"); continue
            page = ctx.new_page()
            for r in rs:
                c = C.CFG["campaigns"].get(r["campaign"]) or {}
                try:
                    res = SUBMITTERS[site](page, r, c, dry)
                except Stale:
                    res = "failed: login expired"; stale.add(site)
                    log(f"{r['clip']}: {site}: the login has expired"); break
                except Exception as e:
                    res = f"failed: {type(e).__name__}: {str(e)[:100]}"
                if res.startswith("failed"):
                    try: page.screenshot(path=str(ROOT / "status" / f"submit_{site.split()[0].lower()}.png"), full_page=False)
                    except Exception: pass
                if res in ("submitted", "already"): done += 1; r["submitted"] = f"{NOW.astimezone(UK):%Y-%m-%d %H:%M}" + (" (already)" if res == "already" else "")
                elif res.startswith("dry"): pass
                else: r["submitted"] = res[:160]
                log(f"{r['clip']} ({r.get('platform', 'youtube')}, {site}): {res[:200]}")
            try: b.close()
            except Exception: pass
    if not dry:
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=C.SUBMIT_FIELDS, extrasaction="ignore"); w.writeheader()
            w.writerows([{k: r.get(k, "") for k in C.SUBMIT_FIELDS} for r in rows])
    try: alerts(stale, by_site)
    except Exception as e: log("submit alerts:", str(e)[:120])
    log(f"submit: {done} of {len(todo)} submitted")
    return done


def alerts(stale, by_site):
    import alerts as A
    for site in SITES:
        title = f"⚠️ Clips: the {site} login has expired"
        secret = SITES[site]["secret"]
        if site in stale:
            A.raise_issue(title, f"GitHub could not submit today's {site} links: the saved login (secret {secret}) no longer works. "
                                 f"In Chrome on the Mac, signed in to {SITES[site]['home']} as the studio account, press the "
                                 f"\"Get cookies.txt LOCALLY\" extension, Export (current site), and paste the file's text into the "
                                 f"secret {secret}: https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/{secret}. "
                                 f"Until then the links are on the phone page: https://quickplay-studio.github.io/quickplay-autopilot/submit.html")
        elif site in by_site: A.clear(title, "The login works again.")




# ---- the scout: campaigns worth joining (Charlie, 21 October: the maximum number of campaigns the upload limit allows) ----
DISCOVER = ["https://contentrewards.com/c/discover", "https://contentrewards.com/discover", "https://contentrewards.com/c/campaigns"]
JUDGE = """You judge a clipping campaign page for a family-friendly YouTube Shorts clipping channel (UK, anonymous, no politics,
crime, health claims, money or investing advice, adult content or gambling). The channel can only use footage the campaign
itself provides or points to (a Drive, Dropbox or Frame.io folder, a named stream or YouTube video of the creator); it
makes its own 9:16 clips with captions and a hook; it posts on YouTube Shorts (Instagram and Facebook later).
Page text:
{text}
Return JSON: {{"name": "", "subject": "the creator or brand the clips show", "type": "clipping or ugc or other",
"platforms": ["YouTube", ...], "youtube_allowed": true, "rate_per_1k": 0.0, "budget_remaining": 0.0, "min_views": 0,
"max_payout": 0.0, "footage": "where the footage comes from, or none", "needs_application": false, "status": "open, full, ended or application",
"family_friendly": true, "fits": true, "why": "one line: why it fits or not", "hashtags": ["#..."], "ends": "YYYY-MM-DD or empty",
"rules": {{"focus": "what the clips must show", "on_screen": "any on-screen text rule", "avoid": ["..."], "min_s": 15, "max_s": 60}}}}
fits is true only when: clipping (not UGC you must film), YouTube allowed, footage provided or named, family friendly, status open."""


def scout(limit=40):
    """Reads the Content Rewards discover pages (and Vyro's campaign list) with the saved logins, judges every campaign
    page with the model, and writes status/scout.md (a ranked shortlist with reasons) and clips/scout.json."""
    import clips as C, factpack
    known = {str(c.get("url", "")).rstrip("/").split("/")[-1] for c in C.CFG["campaigns"].values()}
    from playwright.sync_api import sync_playwright
    found, rows = {}, []
    with sync_playwright() as play:
        try: b, ctx = context(play, "Content Rewards")
        except Exception as e: log(f"scout: {e}"); return []
        page = ctx.new_page()
        for u in DISCOVER:
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=60000); settle(page)
                if logged_out(page): log(f"scout: {u}: not logged in"); continue
                for _ in range(12):
                    page.mouse.wheel(0, 2400); page.wait_for_timeout(700)
                for a in page.locator("a[href*='/c/campaigns/']").all():
                    href = a.get_attribute("href") or ""
                    m = re.search(r"/c/campaigns/([0-9a-f-]{20,})", href)
                    if m: found[m.group(1)] = "https://contentrewards.com" + href if href.startswith("/") else href
                log(f"scout: {u}: {len(found)} campaign links so far")
            except Exception as e: log(f"scout: {u}: {type(e).__name__}: {str(e)[:120]}")
        for cid, url in list(found.items())[:limit]:
            if cid in known: continue
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000); settle(page, 1000)
                text = re.sub(r"[⁦-⁩​-‏‪-‮]", "", page.locator("body").inner_text())
                text = re.sub(r"\n{2,}", "\n", text)[:7000]
                ans, model = factpack.gemini(JUDGE.format(text=text), None, timeout=90, temperature=0.1, lite=True)
                if isinstance(ans, list): ans = next((x for x in ans if isinstance(x, dict)), {})
                if not isinstance(ans, dict) or not ans.get("name"): log(f"scout: {url}: no answer"); continue
                ans.update(url=url, id=cid, platform="Content Rewards", judged=NOW.isoformat(timespec="minutes"), model=model)
                rows.append(ans); log(f"scout: {ans['name'][:50]}: {'fits' if ans.get('fits') else 'no'}: {str(ans.get('why'))[:90]}")
            except Exception as e: log(f"scout: {url}: {type(e).__name__}: {str(e)[:120]}")
        try: b.close()
        except Exception: pass
        if os.environ.get("VYRO_COOKIES", "").strip():
            try:
                b, ctx = context(play, "Vyro"); page = ctx.new_page()
                page.goto("https://app.vyro.com/campaigns", wait_until="domcontentloaded", timeout=60000); settle(page, 1500)
                if logged_out(page): log("scout: Vyro: not logged in")
                else:
                    for _ in range(8): page.mouse.wheel(0, 2400); page.wait_for_timeout(600)
                    text = re.sub(r"\n{2,}", "\n", page.locator("body").inner_text())[:12000]
                    (ROOT / "status" / "scout_vyro.txt").write_text(text)
                    log(f"scout: Vyro's campaign list saved to status/scout_vyro.txt ({len(text)} characters)")
                b.close()
            except Exception as e: log(f"scout: Vyro: {type(e).__name__}: {str(e)[:120]}")
    rows.sort(key=lambda r: -(float(r.get("rate_per_1k") or 0) * min(float(r.get("budget_remaining") or 500), 3000) * (1 if r.get("fits") else 0.1)))
    (ROOT / "clips" / "scout.json").write_text(json.dumps({"updated": NOW.isoformat(timespec="minutes"), "campaigns": rows}, indent=1, ensure_ascii=False))
    L = [f"# Campaigns worth joining ({NOW.astimezone(UK):%A %d %B %H:%M} UK)", "", "| Fits | Campaign | Rate | Budget left | Min views | Footage | Why |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {'yes' if r.get('fits') else 'no'} | [{str(r.get('name'))[:60]}]({r['url']}) | ${r.get('rate_per_1k')}/1k | ${r.get('budget_remaining')} | {r.get('min_views')} | {str(r.get('footage'))[:50]} | {str(r.get('why'))[:120]} |")
    (ROOT / "status" / "scout.md").write_text("\n".join(L) + "\n")
    log(f"scout: {sum(1 for r in rows if r.get('fits'))} of {len(rows)} new campaigns fit")
    return rows


if __name__ == "__main__":
    scout() if "scout" in sys.argv[1:] else run(dry=bool(os.environ.get("SUBMIT_DRY")))
