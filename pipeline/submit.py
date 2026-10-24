"""Submissions (Charlie, 21 October): GitHub puts every public clip link into its campaign itself, the minute the batch
run starts (Reach wants a link within 30 minutes; Content Rewards counts views from the submission). It uses the studio
account's sign-ins for contentrewards.com (with whop.com) and app.vyro.com: Charlie exports each site's cookies.txt with
the "Get cookies.txt LOCALLY" extension, pastes it as the secret WHOP_COOKIES or VYRO_COOKIES and runs the logins
workflow, which keeps them encrypted in tokens/login_whop.enc and tokens/login_vyro.enc (SOCIAL_KEY), where this reads them.
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
ERROR = re.compile(r"\b(invalid|not (allowed|eligible|valid|found|public|submitted)|must be|private|could not|couldn't|cannot|can't|error|unsupported|does not match|doesn't match|past that window|has to be|have to be|rejected|failed)\b", re.I)
WINDOW = re.compile(r"within (the last )?\d+ minutes|past that window|freshly posted", re.I)
VYRO_LEFT = re.compile(r"can submit (\d+) posts? today", re.I)
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


def login_name(site):
    return "login_" + ("vyro" if site == "Vyro" else "whop")


def site_cookies(site):
    """The site's saved sign-in: tokens/login_<site>.enc (written by the logins workflow from the pasted export, read
    with SOCIAL_KEY), else the raw secret when a run still has it."""
    raw = ""
    if os.environ.get("SOCIAL_KEY"):
        try:
            import social as SO
            raw = (SO.load(login_name(site)) or {}).get("cookies", "")
        except Exception as e: log(f"{site}: saved sign-in unreadable: {str(e)[:80]}")
    raw = raw or os.environ.get(SITES[site]["secret"], "")
    cs = [c for c in cookies(raw) if any(h in c["domain"] for h in SITES[site]["hosts"])]
    if not cs: raise RuntimeError(f"no saved sign-in for {site}: export its cookies, paste them as {SITES[site]['secret']}, run the logins workflow")
    return cs


def import_logins():
    """The logins workflow: each pasted export (WHOP_COOKIES, VYRO_COOKIES) into tokens/login_<site>.enc."""
    import social as SO
    n = 0
    for site, spec in SITES.items():
        raw = os.environ.get(spec["secret"], "").strip()
        if not raw: log(f"{site}: {spec['secret']} is empty, nothing saved"); continue
        cs = [c for c in cookies(raw) if any(h in c["domain"] for h in spec["hosts"])]
        if not cs: log(f"{site}: {spec['secret']} holds no {'/'.join(spec['hosts'])} cookies, nothing saved"); continue
        SO.save(login_name(site), {"cookies": raw, "saved": NOW.isoformat(timespec="minutes"), "count": len(cs)})
        log(f"{site}: {len(cs)} cookies saved to tokens/{login_name(site)}.enc"); n += 1
    return n


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


SIGNED_IN = re.compile(r"^\s*(earnings|submissions|add posts|my campaigns|settings|account menu)\s*$", re.I)


def logged_out(page):
    """The login page, or a Log in button with none of the signed-in navigation (Earnings, Submissions, Add Posts): an
    onboarding card's Get started on a signed-in page is not a logout."""
    if re.search(r"/(login|log-in|sign-?in|auth|signup|sign-up)(/|\?|$)", page.url): return True
    try:
        if page.get_by_role("link", name=SIGNED_IN).count() or page.get_by_role("button", name=SIGNED_IN).count(): return False
    except Exception: pass
    return bool(visible(page, "button", LOGIN) or visible(page, "link", LOGIN))


def dismiss(page):
    """Closes an onboarding or notice card that covers the page (Skip, Got it, Close, Get started, Continue)."""
    for _ in range(3):
        if not dialog_open(page): return
        if not click(page, re.compile(r"^\s*(skip( for now)?|got it|close|dismiss|not now|maybe later|get started|continue|ok)\s*$", re.I), roles=("button", "link")): return
        page.wait_for_timeout(600)


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


def tick(page, pattern=None):
    """Ticks the dialog's consent checkbox (the one whose label matches, else the only one) when it is not ticked yet.
    Content Rewards' box is a hidden input under a styled label, so a plain click times out: the label text is clicked
    instead, then a forced click; the box is read back afterwards."""
    d = dialog(page)
    def checked(el):
        try:
            if el.get_attribute("aria-checked") == "true": return True
            return el.get_attribute("type") == "checkbox" and el.is_checked()
        except Exception: return False
    boxes = []
    for role_name in ((pattern,) if pattern else ()) + (None,):
        try: loc = d.get_by_role("checkbox", name=role_name) if role_name else d.get_by_role("checkbox")
        except Exception: continue
        for i in range(min(loc.count(), 6)):
            el = loc.nth(i)
            if el not in boxes: boxes.append(el)
        if boxes: break
    for el in boxes:
        if checked(el): return True
        for step in ("click", "label", "force"):
            try:
                if step == "click": el.click(timeout=3000)
                elif step == "label":
                    txt = d.get_by_text(pattern) if pattern else None
                    if txt is None or not txt.count(): raise RuntimeError("no label text")
                    txt.first.click(timeout=3000)
                else: el.click(force=True, timeout=3000)
                page.wait_for_timeout(500)
                if checked(el): return True
            except Exception: continue
    return bool(boxes) and checked(boxes[0])


CR_STATIC = re.compile(r"posted from one of your linked accounts|we match the clip's author[^.]*\.|not already submitted to any campaign|"
                       r"a clip can only earn once[^.]*\.(?:[^.]*\.)?|posted within the last 30 minutes|this campaign only accepts freshly posted clips[^.]*\.|"
                       r"submit clip link|post a clip link|i've read the requirements[^.]*\.", re.I)


# Content Rewards' three standing checks: the one whose row carries the Failed icon is the reason (24 October: the first
# real batch failed every Expedia clip with "Not already submitted to any campaign", and the log showed the campaign's
# title instead, because the standing labels were stripped before the reason was read)
CR_CHECKS = (("linked", re.compile(r"posted from one of your linked accounts", re.I)),
             ("already", re.compile(r"not already submitted to any campaign", re.I)),
             ("window", re.compile(r"posted within the last \d+ minutes", re.I)))


def failed_check(page):
    """Content Rewards marks the check that failed with a 'Failed' icon: the standing check in the icon's own row
    ("check: linked", "check: already", "check: window"), else the sentence beside it (the standing labels removed, so
    a refused window is never read as a duplicate)."""
    try:
        d = dialog(page)
        img = d.locator("img[alt='Failed'], [aria-label='Failed']")
        if not img.count() or not img.first.is_visible(): return None
        for k in range(1, 6):
            txt = re.sub(r"\s+", " ", img.first.locator(f"xpath=ancestor::*[{k}]").inner_text()).strip()
            hits = [name for name, rx in CR_CHECKS if rx.search(txt)]
            reason = CR_STATIC.sub(" ", txt); reason = re.sub(r"\s+", " ", reason).strip(" .")
            if len(reason) > 20: return reason[:200]          # a sentence of its own beside the icon
            if len(hits) == 1: return "check: " + hits[0]       # only the standing label: that check is the reason
        return "a check failed"
    except Exception: return None


def dialog_open(page):
    return dialog(page) is not page


def dialogs(page):
    """Every visible dialog on the page (Vyro opens the review step as a second one)."""
    out = []
    try:
        loc = page.get_by_role("dialog")
        for i in range(min(loc.count(), 6)):
            if loc.nth(i).is_visible(): out.append(loc.nth(i))
    except Exception: pass
    return out


def submit_cr(page, row, c, dry=False):
    """Content Rewards (22 October): the campaign page's Submit clip button opens a dialog with one url box, three checks
    (posted from a linked account, not already submitted, posted within 30 minutes), a consent checkbox and Submit clip.
    A failed check shows a Failed icon beside its reason and the dialog stays open; success closes it."""
    page.goto(row["campaign_url"], wait_until="domcontentloaded", timeout=60000); settle(page)
    if logged_out(page): raise Stale("Content Rewards")
    if dry: return "dry: logged in; buttons: " + ", ".join(names(page)[:15])
    if not click(page, OPEN): return "failed: no Submit button (buttons: %s)" % ", ".join(names(page)[:12])
    settle(page, 800)
    if logged_out(page): raise Stale("Content Rewards")
    if not dialog_open(page): return "failed: no dialog after Submit clip (buttons: %s)" % ", ".join(names(page)[:12])
    box = link_box(page)
    if box is None: return "failed: no link box after Submit (buttons: %s)" % ", ".join(names(page)[:12])
    box.fill(row["video"]); page.wait_for_timeout(1200)
    tick(page, re.compile(r"requirements|accept|agree|rules", re.I))
    if not click(page, CONFIRM, roles=("button",)): box.press("Enter")
    end = time.time() + 25
    while time.time() < end:
        why = failed_check(page)
        if why:
            if why == "check: already" or DUP.search(why): return "already"
            if why == "check: window" or WINDOW.search(why): return "failed: past the 30-minute window: " + why[:120]
            if why == "check: linked": return "failed: not from a linked account: link this clip's channel on Content Rewards (Settings)"
            return "failed: " + why[:140]
        if not dialog_open(page): return "submitted"
        for role, text in texts(page):
            if role in ("alert", "status") and SUCCESS.search(text) and not ERROR.search(text): return "submitted"
        page.wait_for_timeout(1000)
    return "failed: no answer from the page in 25s (buttons: %s)" % ", ".join(names(page)[:12])


def vyro_card(page, c):
    """The campaign's card on the Add Posts page, found by its card text (campaigns.json 'card'), then its name, then its
    subject; the card's own Submit post button is what opens the right dialog."""
    keys = [k for k in dict.fromkeys([c.get("card", ""), re.sub(r"\s*\(.*\)\s*$", "", c.get("name", "")), c.get("subject", "")]) if k]
    for key in keys:
        try: el = page.get_by_text(key[:60], exact=False).first
        except Exception: continue
        try:
            if not el.is_visible(): continue
        except Exception: continue
        for k in range(1, 9):
            card = el.locator(f"xpath=ancestor::*[{k}]")
            try:
                btn = card.get_by_role("button", name=re.compile(r"^\s*Submit post\s*$", re.I))
                if btn.count(): return card, btn.first
            except Exception: break
    return None, None


def vyro_option(page, pattern):
    """Picks the open listbox's option whose text matches (Radix: options are role option or plain rows)."""
    for role in ("option", "menuitem", "button"):
        els = [e for e in visible(page, role, pattern)]
        if els: els[0].click(); page.wait_for_timeout(700); return True
    try:
        el = page.get_by_text(pattern).last
        if el.is_visible(): el.click(); page.wait_for_timeout(700); return True
    except Exception: pass
    return False


def cookie_report(page, site):
    """Which cookies the context holds now, by name only: shows whether the site cleared the session it was given."""
    try:
        names = sorted({c["name"] for c in page.context.cookies() if any(h in c.get("domain", "") for h in SITES[site]["hosts"])})
        return ", ".join(names)[:300] or "none"
    except Exception as e: return f"unreadable: {str(e)[:60]}"


def submit_vyro(page, row, c, dry=False):
    """Vyro (22 October): the Add Posts page lists the joined campaigns as cards, each with its own Submit post button.
    The dialog: Campaign (preselected), Social account (a YouTube channel), recent posts or 'Use a link instead' (a Paste
    link box), 'This account can submit N posts today', the checkbox 'My post follows campaign rules', Continue; then
    'Review your post' with the checks and a final Submit post. 'Post not submitted: You have already submitted this post
    to a campaign' is the duplicate answer. An account may submit 5 posts a day."""
    page.goto(VYRO_ADD, wait_until="domcontentloaded", timeout=60000); settle(page)
    if logged_out(page): raise Stale("Vyro")
    if dry: return "dry: logged in; buttons: " + ", ".join(names(page)[:15])
    dismiss(page)
    for _ in range(6): page.mouse.wheel(0, 1800); page.wait_for_timeout(300)
    page.mouse.wheel(0, -20000); page.wait_for_timeout(500)
    card, btn = vyro_card(page, c)
    if btn is None: return "failed: campaign '%s' not found on the Add Posts page (cards: %s)" % (c.get("card") or c.get("subject"), ", ".join(names(page, "heading")[:12]))
    try:
        if re.search(r"locked for new posts", card.inner_text(), re.I): return "failed: campaign locked for new posts"
    except Exception: pass
    btn.scroll_into_view_if_needed(); btn.click(); page.wait_for_timeout(1500)
    if not dialog_open(page): return "failed: no dialog after Submit post"
    click(page, re.compile(r"use a link instead", re.I), roles=("button", "link"))
    box = link_box(page)
    if box is None: return "failed: no link box (buttons: %s)" % ", ".join(names(page)[:12])
    box.fill(row["video"]); page.wait_for_timeout(1500)
    d = dialog(page)
    try: dtext = re.sub(r"\s+", " ", d.inner_text())
    except Exception: dtext = ""
    if re.search(r"select social account", dtext, re.I):
        boxes = visible(page, "combobox", re.compile(r"select social account", re.I)) or visible(page, "combobox", re.compile(".*"))
        if boxes:
            boxes[-1].click(); page.wait_for_timeout(800)
            ch = (row.get("channel") or "clips").lower()
            want = {"gaming": r"gaming", "irl": r"irl", "clips": r"^(?!.*(gaming|irl)).*clips"}.get(ch, ch)
            if not vyro_option(page, re.compile(want + r".*youtube|youtube.*" + want, re.I | re.S)):
                vyro_option(page, re.compile(r"youtube", re.I))
            page.wait_for_timeout(800)
        try: dtext = re.sub(r"\s+", " ", dialog(page).inner_text())
        except Exception: pass
    m = VYRO_LEFT.search(dtext)
    if m and int(m.group(1)) == 0: return "failed: Vyro's daily limit for this account (5 posts a day): tomorrow"
    tick(page, re.compile(r"follows campaign rules", re.I))
    if not click(page, re.compile(r"^\s*continue\s*$", re.I), roles=("button",)): return "failed: Continue not clickable (dialog: %s)" % dtext[:160]
    page.wait_for_timeout(2500)
    end = time.time() + 20
    while time.time() < end:
        review = [v for v in dialogs(page) if re.search(r"review your post", v.inner_text(), re.I)]
        if review:
            fin = review[0].get_by_role("button", name=re.compile(r"^\s*Submit post\s*$", re.I))
            if fin.count() and fin.first.is_visible():
                if not fin.first.is_enabled():
                    page.wait_for_timeout(1000)
                    if not fin.first.is_enabled(): return "failed: review checks: " + re.sub(r"\s+", " ", review[0].inner_text())[:160]
                fin.first.click(); page.wait_for_timeout(2500); break
        page.wait_for_timeout(800)
    else:
        return "failed: no Review your post step (dialog: %s)" % re.sub(r"\s+", " ", dialog(page).inner_text() if dialog_open(page) else "")[:160]
    end = time.time() + 25
    while time.time() < end:
        for role, text in texts(page):
            if role == "body": continue
            if DUP.search(text): click(page, re.compile(r"^\s*ok\s*$", re.I), roles=("button",)); return "already"
            if re.search(r"post not submitted", text, re.I): click(page, re.compile(r"^\s*ok\s*$", re.I), roles=("button",)); return "failed: " + text[:140]
            if re.search(r"\b(submitted|pending|under review|success)\b", text, re.I) and not ERROR.search(text):
                click(page, re.compile(r"^\s*(ok|done|close)\s*$", re.I), roles=("button",)); return "submitted"
        if not dialog_open(page): return "submitted"
        page.wait_for_timeout(1000)
    return "failed: no answer after Submit post in 25s (buttons: %s)" % ", ".join(names(page)[:12])


SUBMITTERS = {"Content Rewards": submit_cr, "Vyro": submit_vyro}


def due(rows, public_ok=None):
    """Rows with a link, public already (UK time in the row), not yet submitted or failed last time, under 3 days old."""
    out = []
    for r in rows:
        when = r.get("public_at_uk", "")
        if when.startswith("private") or not r.get("video", "").startswith("http"): continue
        if r.get("submitted") and not r["submitted"].startswith("failed"): continue
        if r.get("submitted", "").startswith(("failed: past the", "failed: not from a linked")): continue      # over for good, or needs Charlie
        try: t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=UK)
        except ValueError: continue
        if t > NOW or NOW - t > dt.timedelta(days=3): continue
        if public_ok and r.get("platform", "youtube") == "youtube" and not public_ok(r["video"]): continue
        out.append(r)
    return out


PAUSE = tuple(float(x) for x in (os.environ.get("SUBMIT_PAUSE") or "120,300").split(","))     # seconds, Charlie: 2 to 5 minutes


def pause(row, site, dry=False):
    """Charlie (22 October): a different gap every time between a clip going public and its submission, 2 to 5 minutes,
    so submissions never land in one burst the second the batch goes live. Content Rewards closes its window 30 minutes
    after the post, so a gap there is cut to keep the submission inside 25 minutes of the public time."""
    if dry or PAUSE[1] <= 0: return 0
    import random
    wait = random.uniform(PAUSE[0], PAUSE[1])
    if site == "Content Rewards":
        try:
            t = dt.datetime.strptime(row.get("public_at_uk", ""), "%Y-%m-%d %H:%M").replace(tzinfo=UK)
            wait = min(wait, max(0.0, (t + dt.timedelta(minutes=25) - dt.datetime.now(dt.timezone.utc)).total_seconds()))
        except ValueError: pass
    if wait > 0:
        log(f"{row.get('clip')}: waiting {wait / 60:.1f} min before submitting"); time.sleep(wait)
    return wait


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
    done, stale, by_site = 0, set(), {"Content Rewards": [], "Vyro": []}
    for r in todo: by_site.setdefault(site_of(C.CFG["campaigns"].get(r["campaign"]) or {}), []).append(r)
    by_site = {s: sorted(rs, key=lambda r: r.get("public_at_uk", "")) for s, rs in by_site.items() if rs}
    by_mac = {s: rs for s, rs in by_site.items() if (C.CFG.get("submit_by") or {}).get(s) == "mac"}
    for s, rs in by_mac.items(): log(f"submit: {s}: {len(rs)} row(s) left for the Mac Chrome run (submit_by mac)")
    by_site = {s: rs for s, rs in by_site.items() if s not in by_mac}
    with sync_playwright() as play:
        for site, rs in by_site.items():
            try: b, ctx = context(play, site)
            except Exception as e: log(f"submit: {site}: {e}"); continue
            page = ctx.new_page()
            limited = set()
            for r in rs:
                c = C.CFG["campaigns"].get(r["campaign"]) or {}
                try:
                    if (site, r.get("channel") or "clips") in limited: res = "failed: Vyro's daily limit for this account (5 posts a day): tomorrow"
                    else:
                        pause(r, site, dry)
                        res = SUBMITTERS[site](page, r, c, dry)
                    if "daily limit" in res: limited.add((site, r.get("channel") or "clips"))
                except Stale:
                    res = "failed: login expired"; stale.add(site)
                    try: page.screenshot(path=str(ROOT / "status" / f"submit_{site.split()[0].lower()}.png"), full_page=False)
                    except Exception: pass
                    log(f"{r['clip']}: {site}: the login has expired ({page.url[:80]}; buttons: {', '.join(names(page)[:8])}; "
                        f"cookies given: {', '.join(sorted({x['name'] for x in site_cookies(site)}))[:300]}; cookies now: {cookie_report(page, site)})"); break
                except Exception as e:
                    res = f"failed: {type(e).__name__}: {str(e)[:100]}"
                if res.startswith("failed") and "daily limit" not in res:
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
    try: linked_alert(rows)
    except Exception as e: log("linked alert:", str(e)[:120])
    log(f"submit: {done} of {len(todo)} submitted")
    return done


def linked_alert(rows):
    """Content Rewards refused a clip as not posted from a linked account: Charlie links that channel (one issue, closed
    when the refusals stop)."""
    import alerts as A
    title = "🔗 Content Rewards: link a clips channel"
    chans = sorted({r.get("channel") or "clips" for r in rows if str(r.get("submitted", "")).startswith("failed: not from a linked")
                    and str(r.get("public_at_uk", ""))[:10] >= str((NOW - dt.timedelta(days=3)).date())})
    if chans:
        A.raise_issue(title, "Content Rewards refused clips from the " + ", ".join(chans) + " channel(s) as not posted from a linked "
                      "account. On the Mac, signed in to https://www.contentrewards.com as the studio account, open Settings, Connected "
                      "accounts, and connect that YouTube channel (the studio Google account's own channel). The refused rows are not "
                      "retried; the next day's clips are submitted once the channel is linked.", labels=["needs-charlie"])
    else: A.clear(title, "No clip has been refused for its channel in the last 3 days.")


def alerts(stale, by_site):
    import clips as C
    import alerts as A
    for site in SITES:
        title = f"⚠️ Clips: the {site} login has expired"
        secret = SITES[site]["secret"]
        if site in stale:
            A.raise_issue(title, f"GitHub could not submit today's {site} links: the saved login (secret {secret}) no longer works. "
                                 f"In Chrome on the Mac, signed in to {SITES[site]['home']} as the studio account, press the "
                                 f"\"Get cookies.txt LOCALLY\" extension, Export (current site), and paste the file's text into the "
                                 f"secret {secret}: https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions/{secret}, "
                                 f"then run the logins workflow (Run workflow): https://github.com/quickplay-studio/quickplay-autopilot/actions/workflows/logins.yml. "
                                 f"Until then the links are on the phone page: https://quickplay-studio.github.io/quickplay-autopilot/submit.html",
                          labels=["needs-charlie"])
        elif site in by_site: A.clear(title, "The login works again.")
        elif (C.CFG.get("submit_by") or {}).get(site) == "mac": A.clear(title, f"{site} links are submitted by the Mac Chrome run now (docs/CHROME_JOBS.md), not from GitHub.")




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


def cr_terms(text):
    """The money terms Content Rewards prints on a campaign page, read directly rather than by the model (which guessed
    "no minimum" for everything, 22 October): per platform the rate per 1,000 views, the minimum payout and the cap, plus
    any per-platform budget line ("YouTube $2,000 / $2,000" means YouTube's share is spent). The minimum views a clip
    needs is minimum payout / rate x 1,000."""
    t = re.sub(r"[\u2066-\u2069\u200b-\u200f\u202a-\u202e]", "", text or "")
    out = {}
    for plat in ("YouTube", "TikTok", "Instagram"):
        m = re.search(plat + r"\s+Per 1K views\s+\$([\d.,]+)\s+Min payout\s+\$([\d.,]+)\s+Max payout\s+\$([\d.,]+)", t)
        if m:
            rate, minp, cap = (float(x.replace(",", "")) for x in m.groups())
            out[plat] = {"rate_per_1k": rate, "min_payout": minp, "max_payout": cap,
                         "min_views": int(round(minp / rate * 1000)) if rate else None}
        b = re.search(r"(?m)^\s*" + plat + r"\s*\n\s*\$([\d,]+)\s*\n\s*/\s*\n\s*\$([\d,]+)", t)
        if b:
            used, total = (float(x.replace(",", "")) for x in b.groups())
            out.setdefault(plat, {})["budget_left"] = max(0.0, total - used)
    return out


HEAT_CACHE = {}


def heat(subject):
    """How hot a subject is right now, 0 to about 3, from free signals: Wikipedia page views of its article over the last
    7 days (Wikimedia REST, no key), its presence in today's Google Trends, Wikipedia top pages and YouTube charts
    (trends/latest.json), the searches that already bring the clips channel viewers (analytics/search_terms.csv), and how
    many YouTube search suggestions it has, and how often it is in today's top stream-clip posts on Reddit
    (r/LivestreamFail, r/Twitch, r/KickStreaming). The scout multiplies a campaign's money by (1 + heat)."""
    import requests, urllib.parse
    subject = (subject or "").strip()
    if not subject: return 0.0, []
    low, score, why = subject.lower(), 0.0, []
    try:
        end = (NOW - dt.timedelta(days=1)).strftime("%Y%m%d"); start = (NOW - dt.timedelta(days=8)).strftime("%Y%m%d")
        u = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/"
             f"{urllib.parse.quote(subject.replace(' ', '_'))}/daily/{start}/{end}")
        r = requests.get(u, headers={"User-Agent": "QuickplayClips/1.0 (quickplay-studio@users.noreply.github.com)"}, timeout=15)
        if r.ok:
            views = [x.get("views", 0) for x in r.json().get("items", [])]
            avg = sum(views) / max(1, len(views))
            pts = min(1.5, max(0.0, (avg ** 0.5) / 100))          # 10,000 a day: 1.0; 22,500: 1.5
            if pts: score += pts; why.append(f"Wikipedia {avg:,.0f} views a day")
    except Exception: pass
    try:
        t = json.loads((ROOT / "trends" / "latest.json").read_text())
        gt = " ".join(str(x.get("q", "")) + " " + " ".join(x.get("news") or []) for g in (t.get("google_trends") or {}).values() for x in (g if isinstance(g, list) else []))
        if low in gt.lower(): score += 0.7; why.append("in Google Trends today")
        if any(low in str(x.get("page", "")).lower() for x in t.get("wikipedia_top") or []): score += 0.5; why.append("a Wikipedia top page today")
        yc = json.dumps(t.get("youtube_charts") or {}).lower()
        if low in yc: score += 0.5; why.append("in the YouTube charts")
    except Exception: pass
    try:                                   # what stream clips are blowing up today (23 October: one more independent source)
        if "lsf" not in HEAT_CACHE:
            HEAT_CACHE["lsf"] = ""
            for sub in ("LivestreamFail", "Twitch", "KickStreaming"):
                x = requests.get(f"https://www.reddit.com/r/{sub}/top/.rss?t=day&limit=50", timeout=15,
                                 headers={"User-Agent": "QuickplayClips/1.0 (quickplay-studio@users.noreply.github.com)"})
                if x.ok: HEAT_CACHE["lsf"] += " " + " ".join(re.findall(r"<title>(.*?)</title>", x.text)).lower()
        hits = HEAT_CACHE["lsf"].count(low)
        if hits: score += min(0.8, 0.3 * hits); why.append(f"{hits} of today's top stream-clip posts on Reddit")
    except Exception: pass
    try:                                   # the watchlist (pipeline/watch.py): coming or surging events weigh more
        for it in json.loads((ROOT / "status" / "watch.json").read_text()).get("items") or []:
            if any(t.lower() in low or (len(low) >= 4 and low in t.lower()) for t in it.get("terms") or [it["name"]]):
                add = {"launch": 1.2, "surging": 1.0, "build-up": 0.5}.get(it.get("level"), 0.0)
                if add: score += add; why.append(f"watchlist: {it['name']} {it['level']}")
    except Exception: pass
    try:
        for r in csv.DictReader((ROOT / "analytics" / "search_terms.csv").open()):
            if low in str(r.get("term", "")).lower(): score += 0.4; why.append(f"our viewers search \"{r['term']}\""); break
    except Exception: pass
    try:
        import clips as C
        terms = C.searches(subject)
        if len(terms) >= 6: score += 0.3; why.append(f"{len(terms)} YouTube search suggestions")
    except Exception: pass
    return round(score, 2), why


def radar():
    """The viral streamers right now: every name in clips/streamers.json scored by heat(), written to status/streamers.md
    with whether we clip them already and where their programme lives. The hottest unjoined ones become Chrome jobs."""
    try: data = json.loads((ROOT / "clips" / "streamers.json").read_text())
    except Exception as e: log(f"radar: {e}"); return []
    rows = []
    for st in data.get("streamers") or []:
        h, why = heat(st.get("wikipedia") or st.get("name"))
        rows.append({**st, "heat": h, "heat_why": why})
    rows.sort(key=lambda r: -r["heat"])
    L = [f"# Viral streamers right now ({NOW.astimezone(UK):%A %d %B %H:%M} UK)", "",
         "Heat: Wikipedia page views over 7 days, Google Trends today, YouTube charts, our viewers' searches, today's top stream-clip posts on Reddit. Joined: the campaigns we already clip.", "",
         "| Heat | Streamer | Why | Programme | Joined | Off limits |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['heat']} | {r['name']} | {'; '.join(r.get('heat_why') or [])[:90]} | {r.get('programme') or ''} | {', '.join(r.get('campaigns') or [])} | {r.get('off') or ''} |")
    hot = [r for r in rows if not r.get("off") and not r.get("campaigns") and r["heat"] >= 0.8][:6]
    if hot:
        L += ["", "## Programmes to join next (hot, not clipped yet)"] + [f"- {r['name']} (heat {r['heat']}): {r.get('programme') or 'find the official programme'}" for r in hot]
    (ROOT / "status" / "streamers.md").write_text("\n".join(L) + "\n")
    log(f"radar: {len(rows)} streamers scored, hottest: " + ", ".join(f"{r['name']} {r['heat']}" for r in rows[:5]))
    return rows


def scout(limit=40):
    """Reads the Content Rewards discover pages (and Vyro's campaign list) with the saved logins, judges every campaign
    page with the model, and writes status/scout.md (a ranked shortlist with reasons) and clips/scout.json."""
    import clips as C, factpack
    try: radar()
    except Exception as e: log(f"radar: {type(e).__name__}: {str(e)[:120]}")
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
                terms = cr_terms(text); yt = terms.get("YouTube") or {}
                ans["terms"] = terms
                if yt.get("rate_per_1k"): ans.update(rate_per_1k=yt["rate_per_1k"], min_views=yt.get("min_views"), max_payout=yt.get("max_payout"))
                if terms and not yt.get("rate_per_1k"):
                    ans["fits"] = False; ans["why"] = "YouTube Shorts are not paid on this campaign. " + str(ans.get("why") or "")
                if yt.get("budget_left") == 0:
                    ans["fits"] = False; ans["why"] = "Its YouTube budget is spent. " + str(ans.get("why") or "")
                ans["heat"], ans["heat_why"] = heat(str(ans.get("subject") or ""))
                rows.append(ans); log(f"scout: {ans['name'][:50]}: {'fits' if ans.get('fits') else 'no'}, heat {ans['heat']}: {str(ans.get('why'))[:90]}")
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
    rows.sort(key=lambda r: -(float(r.get("rate_per_1k") or 0) * min(float(r.get("budget_remaining") or 500), 3000) * (1 + float(r.get("heat") or 0)) * (1 if r.get("fits") else 0.1)))
    (ROOT / "clips" / "scout.json").write_text(json.dumps({"updated": NOW.isoformat(timespec="minutes"), "campaigns": rows}, indent=1, ensure_ascii=False))
    L = [f"# Campaigns worth joining ({NOW.astimezone(UK):%A %d %B %H:%M} UK)", "",
         "Ranked by rate times budget times how hot the subject is right now (Wikipedia views, Google Trends, YouTube charts, our viewers' searches).", "",
         "Rate and minimum views are YouTube's, read from the page (minimum payout / rate). Footage and briefs are only visible after joining: the Mac run joins, reads the brief, and keeps a campaign only when it supplies footage and needs no manual proof per clip.", "",
         "| Fits | Campaign | Rate | Budget left | Min views | Heat | Footage | Why |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {'yes' if r.get('fits') else 'no'} | [{str(r.get('name'))[:60]}]({r['url']}) | ${r.get('rate_per_1k')}/1k | ${r.get('budget_remaining')} | {r.get('min_views')} | "
                 f"{r.get('heat')} ({'; '.join(r.get('heat_why') or [])[:80]}) | {str(r.get('footage'))[:50]} | {str(r.get('why'))[:120]} |")
    (ROOT / "status" / "scout.md").write_text("\n".join(L) + "\n")
    log(f"scout: {sum(1 for r in rows if r.get('fits'))} of {len(rows)} new campaigns fit")
    return rows


if __name__ == "__main__":
    if "import-logins" in sys.argv[1:]: import_logins()
    elif "scout" in sys.argv[1:]: scout()
    else: run(dry=bool(os.environ.get("SUBMIT_DRY")))
