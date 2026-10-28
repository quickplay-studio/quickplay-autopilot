"""Key health (Charlie, 24 October: "i need often project checks on api keys etc expiring so that the project is always
running"). status/keys.json holds one row per sign-in or key: what it is, its status (ok, expiring, failing or missing), the
day it runs out when that is known, when it was last checked, and the steps to fix it. The hub's Accounts tab lists them.

Run by .github/workflows/audit.yml every 3 hours, straight after the identity audit, whose calls it reuses instead of making
them again: status/identity.json carries, under each check's "key", what that one call showed (the YouTube refresh worked or
was refused, Instagram's and Facebook's answers and end dates, TikTok's refresh end, the saved logins' age). It makes one
cheap call only for the keys the audit does not use (Gemini, Groq, Cerebras, OpenRouter, Cloudflare, Mistral, SambaNova),
reads whether CLAUDE_CODE_OAUTH_TOKEN is set (never what it is), and weighs the campaign-site logins by their age and the last
submission found in clips/submit.csv.
The FreeLLMAPI router (27 October, pipeline/freellm.py): one row for the router itself, read from status/freellm.json (ok, or
failing with the reason; it opens an issue only after 3 failed starts in a row, and never more than one), and one optional
row per key it can use (Tavily, Exa, Firecrawl, Linkup, Ollama Cloud, LLM7) with the free sign-up link and the exact secret
to add. A missing optional key is "not set up" and never opens an issue; no call is made for them (the router's own status
says whether the platform is live).
A row that is failing, or ends within 14 days, becomes one needs-charlie issue with the exact steps, closed again once the
key is fixed. A key whose issue Charlie closed without fixing it is raised again after a week, not every 3 hours. A call that
could not be made (the network, a rate limit) leaves the row as it was.

  python pipeline/keys.py            in GitHub Actions: the real run; elsewhere the table from status/keys.json
  python pipeline/keys.py show       the table from status/keys.json
  python pipeline/keys.py now        the real run from anywhere (needs the keys in the environment)
Nothing secret is written: names, dates and states only.
"""
import datetime as dt, json, os, pathlib, re, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import freellm as FL
UK = ZoneInfo("Europe/London")
OUT = ROOT / "status" / "keys.json"
IDENTITY = ROOT / "status" / "identity.json"
FREELLM = FL.STATUS
REPO = "quickplay-studio/quickplay-autopilot"
SECRETS = f"https://github.com/{REPO}/settings/secrets/actions"
AUDIT = f"https://github.com/{REPO}/actions/workflows/audit.yml"
SOCIAL = f"https://github.com/{REPO}/actions/workflows/social.yml"
LOGINS = f"https://github.com/{REPO}/actions/workflows/logins.yml"
CALLBACK = "https://quickplay-studio.github.io/quickplay-autopilot/youtube-callback.html"
WARN_DAYS = 14          # a key that ends within this many days is "expiring"
REMIND_DAYS = 7         # an issue Charlie closed without fixing the key is raised again after this long
NEEDS = "needs-charlie"
GROUPS = ["YouTube", "Instagram", "Facebook", "TikTok", "AI models", "Claude", "Campaign sites"]
# The combined issues the audit raised before there was one per key (identity.expired_note, social.KEY_ISSUE): closed here.
LEGACY = ("🔑 A sign-in has expired: reconnect it", "🔑 An Instagram or Facebook key needs renewing")
# Keys that already had an issue of their own: the same title, so the old and the new path make one issue, not two.
TITLES = {"FB_PAGE_TOKEN": "⚠️ The Facebook key needs renewing",
          "login_whop": "⚠️ Clips: the Content Rewards login has expired", "login_vyro": "⚠️ Clips: the Vyro login has expired"}
AFTER = ("the next key check (within 3 hours) closes this issue; to see it at once press Run workflow on " + AUDIT)


def log(*a): print(*a, flush=True)


def now(): return dt.datetime.now(dt.timezone.utc)


def when(s):
    """An ISO time or unix seconds as an aware time; None for nothing, zero (Meta's "never") or anything unreadable."""
    if s in (None, "", 0, "0", False): return None
    try:
        if isinstance(s, (int, float)) or str(s).isdigit(): return dt.datetime.fromtimestamp(int(s), dt.timezone.utc)
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError): return None


def stamp(t): return t.isoformat(timespec="minutes")
def uk(t): return t.astimezone(UK)


def nice(d, ref=None):
    """Friday 28 October (UK); with the year when the day is more than 150 days from ref (now): Sunday 10 October 2027."""
    d = uk(d)
    far = ref is not None and abs((d - ref).days) > 150
    return f"{d:%A} {d.day} {d:%B}" + (f" {d.year}" if far else "")


def load(path, default=None):
    try: return json.loads(pathlib.Path(path).read_text())
    except Exception: return default


def http_get(url, headers=None):
    import requests
    return requests.get(url, headers=headers or {}, timeout=20)


# ---------- the rows ----------
def make(id, what, group, status, detail="", fix=(), ends=None, needed=False, t=None, checked=None, hard=False):
    r = {"id": id, "what": what, "group": group, "status": status, "expires": "", "checked": checked or (stamp(t) if t else None),
         "detail": detail, "needed": needed, "fix": list(fix)}
    if ends and t: weigh(r, ends, t, hard)
    return r


def weigh(r, ends, t, hard=False):
    """Sets the end date on a row and lets it decide the status: ending within WARN_DAYS is expiring. An end that has passed
    is failing when the end is what keeps the thing alive (hard: a refresh token, a cookie); a key that still answers
    just now has a stale record, so it stays ok with a note."""
    r["expires"] = f"{uk(ends):%Y-%m-%d}"
    if r["status"] != "ok": return r
    was = f"; {r['detail']}" if r["detail"] else ""
    if ends <= t:
        if hard: r.update(status="failing", detail=f"ended on {nice(ends, t)}{was}")
        else: r["detail"] = f"the recorded end date, {nice(ends, t)}, has passed but it still answers{was}"
    elif (ends - t).days <= WARN_DAYS:
        r.update(status="expiring", detail=f"ends on {nice(ends, t)}, {in_days(ends, t)}{was}")
    return r


def in_days(ends, t):
    n = (ends - t).days
    return "within a day" if n < 1 else f"in {n} day{'s' if n != 1 else ''}"


def secret_steps(name, where, how):
    return [f"Open {where} signed in as the studio Google account and {how}.",
            f"Copy it and paste it into the GitHub secret {name} (Update secret): {SECRETS}/{name}",
            AFTER[0].upper() + AFTER[1:] + "."]


# ---------- YouTube, Instagram, Facebook, TikTok, the logins: read from the audit's checks ----------
YT = {"youtube": ("Quickplay Daily", "main"), "youtube_clips": ("Quickplay Clips", "clips"),
      "youtube_gaming": ("Quickplay Gaming Clips", "gaming"), "youtube_irl": ("Quickplay IRL Clips", "irl"),
      "youtube_pt": ("Quickplay Portuguese", "pt"), "youtube_music": ("Quickplay Music", "music"),
      "youtube_es": ("Quickplay Diario", "es")}
IG = {"instagram": "Instagram key in use (Quickplay Daily)", "IG_TOKEN": "Instagram seed key (IG_TOKEN)",
      "IG_CLIPS_TOKEN": "Instagram key: Quickplay Clips (IG_CLIPS_TOKEN)", "IG_GAMING_TOKEN": "Instagram key: Quickplay Gaming Clips (IG_GAMING_TOKEN)",
      "IG_IRL_TOKEN": "Instagram key: Quickplay IRL Clips (IG_IRL_TOKEN)"}
FB = {"FB_PAGE_TOKEN": "Facebook Page key: Quickplay Daily (FB_PAGE_TOKEN)", "FB_CLIPS_PAGE_TOKEN": "Facebook Page key: Quickplay Clips (FB_CLIPS_PAGE_TOKEN)",
      "FB_GAMING_PAGE_TOKEN": "Facebook Page key: Quickplay Gaming Clips (FB_GAMING_PAGE_TOKEN)", "FB_IRL_PAGE_TOKEN": "Facebook Page key: Quickplay IRL Clips (FB_IRL_PAGE_TOKEN)"}
LOGINS_OF = {"login_whop": ("Content Rewards", "WHOP_COOKIES", "https://contentrewards.com/"),
             "login_vyro": ("Vyro", "VYRO_COOKIES", "https://app.vyro.com/campaigns")}
NAMES = {**IG, **FB, "tiktok": "TikTok sign-in (refresh token)", "login_whop": "Content Rewards login (saved cookies)", "login_vyro": "Vyro login (saved cookies)"}


def fix_youtube(title, arg, testing=False):
    steps = []
    if testing:
        steps.append("First publish the Google app, or the new sign-in ends after 7 days too: open https://console.cloud.google.com/auth/audience "
                     "(the project that holds the YouTube OAuth client), press Publish app and confirm.")
    steps += [f"Signed in to Google as the studio account only, open {CALLBACK} and press Sign in to YouTube.",
              f"When Google asks which channel, pick {title}. On the permissions page tick Select all, then Continue.",
              "Press Copy code on the page that opens.",
              f"Within 5 minutes open {SOCIAL}, press Run workflow, paste the code into \"YouTube address or code\", type {arg} as the channel, "
              "and press the green Run workflow.",
              AFTER[0].upper() + AFTER[1:] + "."]
    if not testing:
        steps.append("If this comes back about 7 days after each sign-in, Google's app is still in Testing: publish it at "
                     "https://console.cloud.google.com/auth/audience (Publish app) and sign in once more.")
    return steps


def yt_row(id, c, k, t, checked):
    title, arg = YT.get(id, (id, id.replace("youtube_", "") or "main"))
    ends = when(k.get("expires_at"))            # Google sets an end date only while its app is in Testing
    base = dict(id=id, what=f"YouTube sign-in: {k.get('channel') or title}", group="YouTube", needed=(id == "youtube"),
                fix=fix_youtube(title, arg, testing=bool(ends)), t=t, checked=checked)
    state = k.get("state")
    if state == "ok" and c.get("ok"):
        return make(status="ok", ends=ends, detail="the refresh works; " + ("Google's app is in Testing, so this sign-in ends after 7 days"
                    if ends else "Google set no 7-day Testing limit on it"), **base)
    if state == "empty": return make(status="missing", detail="no sign-in is saved for this channel", **base)
    if state == "expired": return make(status="failing", detail="Google says the sign-in is expired or revoked (invalid_grant)", **base)
    return make(status="failing", detail=(c.get("note") or "the sign-in does not work")[:160], **base)


def ig_row(id, c, k, t, checked):
    secret = "IG_TOKEN" if id == "instagram" else id
    fix = ["Open https://developers.facebook.com/apps and choose the Quickplay app, signed in as the studio account.",
           "Instagram, then API setup with Instagram login, then Generate token for the account this key belongs to.",
           f"Copy the token and paste it into the GitHub secret {secret} (Update secret): {SECRETS}/{secret}"]
    if id == "instagram":
        fix.append("The key in use is kept in tokens/instagram.enc and is only replaced when that file is removed: ask Claude (your pinned "
                   "Quickplay page) to remove it so the new IG_TOKEN seeds a fresh one.")
    fix.append(f"Press Run workflow on {AUDIT}: from then on the audit refreshes the key every week by itself.")
    base = dict(id=id, what=IG.get(id, id), group="Instagram", fix=fix, t=t, checked=checked)
    state, ends = k.get("state"), when(k.get("expires_at"))
    if state == "ok" and c.get("ok"):
        return make(status="ok", ends=ends, detail=f"answers as @{k.get('user')}" + ("" if ends else "; Meta has not given an end date yet (the weekly refresh records it)"), **base)
    if state == "expired seed":
        return make(status="ok", detail="the seed key has run out, which is expected: the key in use renews itself. Renew this only if "
                    "tokens/instagram.enc is ever lost", **base)
    if state == "expired": return make(status="failing", detail="Meta says the key has expired", **base)
    return make(status="failing", detail=(c.get("note") or "the key does not answer")[:160], **base)


def fb_row(id, c, k, t, checked, prev=None):
    page = k.get("page") or ""
    fix = ["Open https://developers.facebook.com/tools/explorer/ signed in as the studio account and choose the Quickplay app.",
           "Under Permissions add pages_manage_posts, pages_manage_engagement, pages_read_engagement, pages_read_user_content, "
           f"pages_show_list and read_insights, then press Generate Access Token and allow it for the {page or 'Quickplay'} Page.",
           f"Copy the token and paste it into the GitHub secret {id} (Update secret): {SECRETS}/{id}. A user key is fine: the automation "
           "swaps it for the Page's own key, which lasts as long.",
           AFTER[0].upper() + AFTER[1:] + "."]
    base = dict(id=id, what=FB.get(id, id), group="Facebook", fix=fix, t=t, checked=checked)
    state = k.get("state")
    if state == "ok" and c.get("ok"):
        exp, data = when(k.get("expires_at")), when(k.get("data_access_expires_at"))
        if "expires_at" in k or "data_access_expires_at" in k:
            said = ("the key never ends" if not exp else f"the key ends {nice(exp, t)}") + (f"; Meta's data access ends {nice(data, t)}" if data else "")
            ends = min([x for x in (exp, data) if x], default=None)
        else:       # Graph's debug_token gave nothing this time: the end noted last time still stands
            ends, said = when((prev or {}).get("expires")), "Meta gave no end date this time"
        return make(status="ok", ends=ends, detail=f"answers as the Page {page}; {said}", **base)
    if state == "expired": return make(status="failing", detail="Meta says the key has expired", **base)
    return make(status="failing", detail=(c.get("note") or "the key does not answer")[:160], **base)


def tt_row(id, c, k, t, checked):
    off = k.get("mode") == "off"
    fix = ["TikTok is off at the moment (docs/TIKTOK.md), so nothing is needed until you switch it back on.",
           "To reconnect: open https://quickplay-studio.github.io/quickplay-autopilot/tiktok.html, sign in to the Quickplay TikTok account and copy the code.",
           f"Open {SOCIAL}, press Run workflow, paste the code into \"TikTok code\" and press the green Run workflow."]
    base = dict(id=id, what=NAMES["tiktok"], group="TikTok", fix=fix, t=t, checked=checked)
    state, ends = k.get("state"), when(k.get("refresh_ends"))
    if state == "empty": return make(status="missing", detail="TikTok is not connected", **base)
    r = make(status="failing" if (state == "error" or not c.get("ok")) else "ok", ends=ends, hard=True,
             detail=("the access key does not answer right now (the social run refreshes it); " if state == "no answer" else "") +
                    (f"the refresh token ends {nice(ends, t)}" if ends else "TikTok has not said when the refresh token ends"), **base)
    if off and r["status"] in ("expiring", "failing"):
        r["status"], r["detail"] = "ok", r["detail"] + " (TikTok is off, so this can wait)"
    return r


def login_row(id, c, k, t, checked, seen):
    site, secret, home = LOGINS_OF[id]
    saved, ends = when(k.get("saved")), when(k.get("session_ends"))
    win, fail = (seen.get(site) or {}).get("success"), (seen.get(site) or {}).get("failure")
    if ends and win and win > ends: ends = None         # a submission after that cookie ended: another cookie carries the sign-in
    if fail and saved and saved > fail: fail = None     # the login was saved again after that failure: the failure is old news
    fix = [f"In Chrome on the Mac, signed in to {home} as the studio account, press the \"Get cookies.txt LOCALLY\" extension, then Export (current site).",
           f"Paste the file's text into the GitHub secret {secret} (Update secret): {SECRETS}/{secret}",
           f"Open {LOGINS}, press Run workflow, and wait for it to finish."]
    age = f"saved {(t - saved).days} days ago, {k.get('count', 0)} cookies" if saved else f"{k.get('count', 0)} cookies, saved date unknown"
    last = f"last submission {nice(win, t)}" if win else "no submission seen yet"
    base = dict(id=id, what=NAMES[id], group="Campaign sites", fix=fix, t=t, checked=checked)
    if not c.get("ok"): return make(status="failing", detail=(c.get("note") or "the saved export is wrong")[:160], **base)
    if fail and (not win or fail > win):
        return make(status="failing", detail=f"the site showed its login page and no submission has worked since; {age}; {last}", **base)
    return make(status="ok", ends=ends, hard=True, detail=f"{age}; {last}", **base)


def submissions(rows, camps):
    """Per campaign site, the newest submission that worked and the newest login failure in clips/submit.csv."""
    out = {"Content Rewards": {}, "Vyro": {}}
    for r in rows:
        site = "Vyro" if "vyro" in str((camps.get(r.get("campaign")) or {}).get("platform", "")).lower() else "Content Rewards"
        s = str(r.get("submitted") or "")
        pattern = r"failed: (login expired|no saved sign-in)" if site == "Content Rewards" else r"failed: .*(login|sign.?in|session)"
        try:        # the times in the file are UK times
            hit = dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M").replace(tzinfo=UK).astimezone(dt.timezone.utc)
            if hit > (out[site].get("success") or hit - dt.timedelta(seconds=1)): out[site]["success"] = hit
        except ValueError:
            if not re.match(pattern, s, re.I): continue
            try: bad = dt.datetime.strptime(str(r.get("public_at_uk") or "")[:16], "%Y-%m-%d %H:%M").replace(tzinfo=UK).astimezone(dt.timezone.utc)
            except ValueError: continue
            if bad > (out[site].get("failure") or bad - dt.timedelta(seconds=1)): out[site]["failure"] = bad
    return out


# ---------- the keys the audit does not use: one cheap call each ----------
def bearer(k): return {"Authorization": f"Bearer {k}"}


PROBES = {
    "GEMINI_API_KEY": dict(what="Gemini API key (writing, fact packs)", url="https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                           headers=lambda k: {"x-goog-api-key": k}, vendor="Google", needed=True, bad400=True,
                           where="https://aistudio.google.com/apikey", how="create an API key (or copy the one you have)"),
    "GROQ_API_KEY": dict(what="Groq API key (writing)", url="https://api.groq.com/openai/v1/models", headers=bearer, vendor="Groq",
                         where="https://console.groq.com/keys", how="press Create API Key"),
    "CEREBRAS_API_KEY": dict(what="Cerebras API key (writing)", url="https://api.cerebras.ai/v1/models", headers=bearer, vendor="Cerebras",
                             where="https://cloud.cerebras.ai/", how="open API Keys and generate one"),
    "OPENROUTER_API_KEY": dict(what="OpenRouter API key (writing)", url="https://openrouter.ai/api/v1/auth/key", headers=bearer, vendor="OpenRouter",
                               where="https://openrouter.ai/settings/keys", how="press Create Key"),
    "CF_API_TOKEN": dict(what="Cloudflare Workers AI token (writing)", vendor="Cloudflare",
                         where="https://dash.cloudflare.com/profile/api-tokens", how="press Create Token, use the Workers AI template, Continue to summary, Create Token"),
    "MISTRAL_API_KEY": dict(what="Mistral API key (writing)", url="https://api.mistral.ai/v1/models", headers=bearer, vendor="Mistral",
                            where="https://console.mistral.ai/api-keys", how="press Create new key"),
    "SAMBANOVA_API_KEY": dict(what="SambaNova API key (writing)", url="https://api.sambanova.ai/v1/models", headers=bearer, vendor="SambaNova",
                              where="https://cloud.sambanova.ai/apis", how="create an API key"),
    "APIFY_TOKEN": dict(what="Apify token (the morning trend feed)", url="https://api.apify.com/v2/users/me", headers=bearer, vendor="Apify",
                        where="https://console.apify.com/settings/integrations", how="copy the personal API token (free plan, $5 monthly credit)"),
    "ANTHROPIC_API_KEY": dict(what="Anthropic API key (Claude edits on the monthly API credits)", url="https://api.anthropic.com/v1/models?limit=1",
                              headers=lambda k: {"x-api-key": k, "anthropic-version": "2023-06-01"}, vendor="Anthropic",
                              where="https://platform.claude.com/settings/keys", how="claim the Max API credits in claude.ai Billing, then create a key"),
}


def probe(name, env=None, get=None):
    """One cheap call that proves an API key works: {"status": ok | failing | missing | unverified, "detail", "ends"}.
    unverified: the network, a rate limit or a server error (nothing is known, so nothing changes)."""
    env = os.environ if env is None else env
    spec, key = PROBES[name], (env.get(name) or "").strip()
    if not key: return {"status": "missing", "detail": f"{name} is not set", "ends": None}
    get = get or http_get
    if name == "CF_API_TOKEN": return probe_cloudflare(key, env, get)
    try: r = get(spec["url"], headers=spec["headers"](key))
    except Exception as e: return {"status": "unverified", "detail": f"could not be reached ({type(e).__name__})", "ends": None}
    code = r.status_code
    try: text = r.text or ""
    except Exception: text = ""
    if 200 <= code < 300:
        try: ends = when(((r.json() or {}).get("data") or {}).get("expires_at"))      # OpenRouter keys can carry an end date
        except Exception: ends = None
        return {"status": "ok", "detail": f"{spec['vendor']} accepts the key", "ends": ends}
    if code in (401, 403) or (code == 400 and spec.get("bad400") and re.search(r"API_KEY_INVALID|API key not valid|expired", text, re.I)):
        return {"status": "failing", "detail": f"{spec['vendor']} refuses the key (HTTP {code})", "ends": None}
    return {"status": "unverified", "detail": f"{spec['vendor']} answered HTTP {code}", "ends": None}


def probe_cloudflare(token, env, get):
    """Cloudflare's token verify (a user token's endpoint, then the account's own), and CF_ACCOUNT_ID set and shaped like an
    account id: both are needed before Workers AI answers."""
    acct = (env.get("CF_ACCOUNT_ID") or "").strip()
    seen = None
    for url in ["https://api.cloudflare.com/client/v4/user/tokens/verify"] + ([f"https://api.cloudflare.com/client/v4/accounts/{acct}/tokens/verify"] if acct else []):
        try: r = get(url, headers=bearer(token))
        except Exception as e: return {"status": "unverified", "detail": f"could not be reached ({type(e).__name__})", "ends": None}
        try: j = r.json() or {}
        except Exception: j = {}
        res = j.get("result") or {}
        if r.status_code == 200 and j.get("success") and res.get("status") == "active":
            if not acct: return {"status": "failing", "detail": "the token works but CF_ACCOUNT_ID is not set", "ends": None}
            if not re.fullmatch(r"[0-9a-fA-F]{32}", acct):
                return {"status": "failing", "detail": "the token works but CF_ACCOUNT_ID does not look like an account id (32 letters and digits)", "ends": None}
            return {"status": "ok", "detail": "Cloudflare accepts the token and CF_ACCOUNT_ID is set", "ends": when(res.get("expires_on"))}
        seen = (r.status_code, j.get("success"), res.get("status"))
    code, success, status = seen
    if code == 200 and success: return {"status": "failing", "detail": f"Cloudflare says the token is {status or 'not active'}", "ends": None}
    if code in (401, 403): return {"status": "failing", "detail": f"Cloudflare refuses the token (HTTP {code})", "ends": None}
    return {"status": "unverified", "detail": f"Cloudflare answered HTTP {code}", "ends": None}


def probe_row(name, res, t):
    spec = PROBES[name]
    fix = secret_steps(name, spec["where"], spec["how"])
    if name == "CF_API_TOKEN":
        fix.append(f"Also check the secret CF_ACCOUNT_ID holds the Account ID (the long code in the dashboard address): {SECRETS}/CF_ACCOUNT_ID")
    return make(name, spec["what"], "AI models", res["status"], res["detail"], fix, res.get("ends"), spec.get("needed", False), t)


AUTH_FAIL = re.compile(r"invalid api key|please run /login|oauth|authenticat|unauthori[sz]ed|\b401\b|token.{0,20}(expired|revoked|invalid)", re.I)


def claude_row(env, t):
    """CLAUDE_CODE_OAUTH_TOKEN: set or not, never what it is and never a call (each one spends Charlie's allowance). The
    writer's own last call (status/claude_usage.json) tells whether Claude refused the token."""
    ok = bool((env.get("CLAUDE_CODE_OAUTH_TOKEN") or "").strip())
    usage = load(ROOT / "status" / "claude_usage.json", {}) or {}
    last, at = usage.get("last"), usage.get("last_at")
    fix = ["On the Mac, open Terminal and run: claude setup-token (signed in to Claude with your subscription).",
           f"Copy the token it prints and paste it into the GitHub secret CLAUDE_CODE_OAUTH_TOKEN (Update secret): {SECRETS}/CLAUDE_CODE_OAUTH_TOKEN",
           "This turns green after the writer next calls Claude (a few times a day); it does not use your allowance to check."]
    what = "Claude token (the writer's last resort, your allowance)"
    if not ok: return make("CLAUDE_CODE_OAUTH_TOKEN", what, "Claude", "missing", "the secret is not set; the writer skips Claude", fix, None, False, t)
    if last and last not in ("ok", "timeout") and AUTH_FAIL.search(str(last)):
        return make("CLAUDE_CODE_OAUTH_TOKEN", what, "Claude", "failing", f"the secret is set but the writer's last call was refused ({str(last)[:90]})", fix, None, False, t)
    return make("CLAUDE_CODE_OAUTH_TOKEN", what, "Claude", "ok", "the secret is set (only its presence is checked, so no allowance is used)"
                + (f"; the writer's last call: {last} at {at}" if last and at else ""), fix, None, False, t)


# ---------- the FreeLLMAPI router: its own row and one optional row per key it can use ----------
ROUTER_FAILS = 3            # failed starts in a row before the router row opens its one issue
ROUTER_WHAT = "FreeLLMAPI router (more free models and web search for the writers and fact packs)"
WORKFLOWS = f"https://github.com/{REPO}/actions/workflows"
NAME_OF = {"tavily": "Tavily", "exa": "Exa", "firecrawl": "Firecrawl", "linkup": "Linkup", "ollama": "Ollama Cloud", "llm7": "LLM7"}


def router_row(st, t):
    """The router itself, from status/freellm.json: ok (what it serves), failing (why), or not run yet. Failing opens an issue
    only after ROUTER_FAILS starts in a row; before that the row is "quiet": on the hub, no issue."""
    base = dict(id="freellm", what=ROUTER_WHAT, group="AI models", t=t, needed=False)
    steps = ["Nothing is lost while it is down: the writers and fact packs use the other free models, as before it existed.",
             f"Open the newest run of trends or write ({WORKFLOWS}/write.yml) and read the step called FreeLLMAPI router: it prints the reason.",
             "If the reason is \"image digest changed\": read the release notes at https://github.com/tashfeenahmed/freellmapi/releases, then ask "
             "Claude (your pinned Quickplay page) to set freellm.digest in config.json.",
             "To switch it off for good, set \"on\": false under \"freellm\" in config.json."]
    if not st:
        r = make(status="missing", detail="it has not run yet: it starts with the next trends, write or evolve run",
                 fix=[f"Nothing to do: it starts by itself. To start one now press Run workflow on {WORKFLOWS}/trends.yml."], **base)
        r["for"] = "freellm"
        return r
    started = when(st.get("started"))
    if st.get("ok"):
        engines = ", ".join(st.get("search_engines") or []) or "none"
        calls = st.get("calls") or {}
        r = make(status="ok", checked=stamp(started) if started else None, fix=steps, **base,
                 detail=f"started {nice(started, t) if started else '?'} ({st.get('job') or 'a job'}): {st.get('models', 0)} chat models on "
                        f"{', '.join(st.get('chat_platforms') or []) or 'its free tiers'}; search on {engines}"
                        + (f"; served {sum(calls.values())} calls last run" if calls else ""))
    else:
        hist, run = [h for h in st.get("history") or [] if isinstance(h, dict)], 0
        for h in reversed(hist):
            if h.get("ok"): break
            run += 1
        r = make(status="failing", checked=stamp(started) if started else None, fix=steps, **base,
                 detail=f"the last start failed ({st.get('reason') or 'no reason recorded'}); {max(run, 1)} in a row")
        r["quiet"] = max(run, 1) < ROUTER_FAILS
    r["for"] = "freellm"
    return r


def router_key_rows(env, st, t):
    """One optional row per key the router can use. Set: ok, or (when the router started and did not list the platform) failing
    but quiet. Not set: "not set up", with the free sign-up page and the exact secret to add."""
    live = set((st or {}).get("chat_platforms") or []) | set((st or {}).get("search_engines") or [])
    rows = []
    for secret, (platform, what, signup, how) in FL.KEYS.items():
        name = f"{NAME_OF.get(platform, platform)} key ({what}, for the FreeLLMAPI router)"
        if (env.get(secret) or "").strip():
            lost = bool((st or {}).get("ok")) and platform not in live
            r = make(secret, name, "AI models", "failing" if lost else "ok", t=t,
                     detail=(f"the secret is set but the router did not list {platform} as live at its last start: check the key"
                             if lost else "the secret is set and goes to the router only" + (f"; the router lists {platform} as live" if platform in live else "")),
                     fix=[f"Open {signup} and {how}.", f"Paste the new key into the GitHub secret {secret} (Update secret): {SECRETS}/{secret}", AFTER[0].upper() + AFTER[1:] + "."])
            r["quiet"] = True
        else:
            r = make(secret, name, "AI models", "missing", f"optional, not set: adds {what} to the free router", t=t,
                     fix=[f"Open {signup} (free) and {how}.",
                          f"Create the GitHub secret named exactly {secret}, paste the key as its value and press Add secret: {SECRETS}/new",
                          "The next trends, write or evolve run starts the router with it; this row turns green at the next key check (within 3 hours)."])
        r["for"] = "freellm"
        rows.append(r)
    return rows


def missing_row(id, group, t, what=None, needed=False, fix=()):
    if id in YT: steps = fix_youtube(YT[id][0], YT[id][1])
    elif id in IG or id in FB: steps = [f"Add it as the GitHub secret {'IG_TOKEN' if id == 'instagram' else id}: {SECRETS}/new"]
    elif id in LOGINS_OF: steps = [f"Export the site's cookies and save them with the logins workflow: {LOGINS}"]
    else: steps = []
    name = what or (f"YouTube sign-in: {YT[id][0]}" if id in YT else NAMES.get(id, id))
    return make(id, name, group, "missing", "the secret is not set" if id in PROBES else "not set up", list(fix) or steps, None, needed or id == "youtube", t)


# ---------- putting the table together ----------
RANK = {id: i for i, id in enumerate(list(YT) + list(IG) + list(FB) + ["tiktok"] + list(PROBES) + ["freellm"] + list(FL.KEYS) + ["CLAUDE_CODE_OAUTH_TOKEN"] + list(LOGINS_OF))}


def build(identity, env, prev, t, get=None, rows=None, camps=None):
    """Every row of status/keys.json. identity: the audit's result (status/identity.json), prev: the last rows by id."""
    checks = {c.get("what"): c for c in (identity or {}).get("checks") or [] if isinstance(c, dict)}
    audited = when((identity or {}).get("checked")) or t
    checked = stamp(audited)
    seen = submissions(rows or [], camps or {})
    out = []

    def keep(id, why):                      # a call that could not be made leaves the row as it was
        if prev.get(id):
            q = dict(prev[id])
            q["detail"] = re.sub(r" \(not checked this time.*$", "", q.get("detail", "")) + f" (not checked this time: {why})"
            out.append(q)

    def present(id, group):
        if group in ("YouTube", "Campaign sites", "TikTok"): return (ROOT / "tokens" / f"{id}.enc").exists()
        return bool((env.get(id) or "").strip()) or (id == "instagram" and (ROOT / "tokens" / "instagram.enc").exists())

    yts = sorted({p.stem for p in (ROOT / "tokens").glob("youtube*.enc")} | {i for i in checks if i.startswith("youtube")} | {"youtube"})
    wanted = [(i, "YouTube") for i in yts] + [(i, "Instagram") for i in IG] + [(i, "Facebook") for i in FB] + [("tiktok", "TikTok")] + [(i, "Campaign sites") for i in LOGINS_OF]
    for id, group in wanted:
        c = checks.get(id)
        if c is None:
            twin = next((r for r in out if r["id"] == "instagram"), None)
            if id == "IG_TOKEN" and twin and present(id, group):    # the audit checks one key once: this secret is the very key in use
                out.append(make(id, IG[id], group, "ok", "the same key as the one in use (listed above)", twin["fix"], None, False, t, twin["checked"]))
            elif present(id, group): keep(id, "the audit has not looked at it yet")
            else: out.append(missing_row(id, group, t))
            continue
        if c.get("unverified"): keep(id, str(c.get("note") or "the audit could not reach it")[:100]); continue
        k = c.get("key") or {}
        make_row = {"youtube": yt_row, "instagram": ig_row, "facebook": fb_row, "tiktok": tt_row, "login": login_row}.get(k.get("kind"))
        if make_row is None: keep(id, "the audit gave no details"); continue
        try:
            extra = {"facebook": (prev.get(id),), "login": (seen,)}.get(k["kind"], ())
            out.append(make_row(id, c, k, t, checked, *extra))
        except Exception as e: log(f"keys: {id}: {type(e).__name__}: {str(e)[:100]}"); keep(id, "the row could not be read")
    for name in PROBES:     # the keys the audit does not use
        try:
            res = probe(name, env, get)
            if res["status"] == "unverified": keep(name, res["detail"])
            elif res["status"] == "missing":
                spec = PROBES[name]
                out.append(missing_row(name, "AI models", t, spec["what"], spec.get("needed", False), secret_steps(name, spec["where"], spec["how"])))
            else: out.append(probe_row(name, res, t))
        except Exception as e: log(f"keys: {name}: {type(e).__name__}: {str(e)[:100]}"); keep(name, "the check failed")
    try:
        st = load(FREELLM, {}) or {}
        out.append(router_row(st, t))
        out.extend(router_key_rows(env, st, t))
    except Exception as e: log(f"keys: freellm: {type(e).__name__}: {str(e)[:100]}")
    out.append(claude_row(env, t))
    order = {g: i for i, g in enumerate(GROUPS)}
    return sorted(out, key=lambda r: (order.get(r.get("group"), 99), RANK.get(r["id"], 99), r["id"]))


# ---------- the issues ----------
def issue_title(r): return TITLES.get(r["id"]) or f"🔑 Fix needed: {r['what']}"


def problem(r):
    """A row that needs an issue. A quiet row (the optional router rows, the router before its 3rd failed start) is shown on
    the hub but never raises one."""
    return not r.get("quiet") and (r["status"] in ("failing", "expiring") or (r["status"] == "missing" and r.get("needed")))


def issue_body(r, t):
    state = {"failing": "has stopped working", "expiring": "is about to stop working", "missing": "is not set up"}[r["status"]]
    ends = when(r.get("expires"))
    head = f"**{r['what']}** {state}: {r['detail']}"
    if r["status"] == "expiring" and ends: head += f"\n\nIt ends on {nice(ends, t)}, {in_days(ends, t)}. Fix it before then so nothing stops."
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(r.get("fix") or ["Ask Claude from your pinned Quickplay page."], 1))
    return f"{head}\n\nHow to fix it:\n{steps}\n\nThis issue closes by itself once a key check (every 3 hours) finds it working. Every key is listed on the hub's Accounts tab."


def announce(rows, prev, t, A=None, have=None):
    """One needs-charlie issue per row that is a problem, closed again once it is not. Each row records the issue's number and
    what was last said (status and end date), so the same news is not posted again every 3 hours."""
    if A is None: import alerts as A
    have = dict(A.open_issues() if have is None else have)
    notes = []
    for r in rows:
        title, p = issue_title(r), prev.get(r["id"]) or {}
        sig, n = f"{r['status']}|{r.get('expires') or ''}", have.get(title)
        if problem(r):
            said, at = p.get("said") or "", when(p.get("said_at"))
            if n and said == sig: r.update(issue=n, said=sig, said_at=p.get("said_at"))            # Charlie has been told
            elif not n and said == sig and at and (t - at).days < REMIND_DAYS: r.update(said=sig, said_at=p.get("said_at"))      # he closed it: quiet for a week
            else:
                num = A.raise_issue(title, issue_body(r, t), labels=[NEEDS], howto="If you get stuck, start a new Claude chat, use the quickplay skill and paste this issue's link.")
                if num: r.update(issue=num, said=sig, said_at=stamp(t))         # not recorded when GitHub did not answer: asked again next run
                notes.append(f"{r['id']}: {r['status']}, issue {'updated' if n else 'opened'}" + ("" if num else " (GitHub did not confirm)"))
        elif n:
            A.close_issue(n, f"Fixed: {r['what']} is {r['status']} again ({r['detail']}).")
            notes.append(f"{r['id']}: fixed, issue closed")
    for legacy in LEGACY:       # one issue per key replaces these two combined ones
        if legacy in have:
            A.close_issue(have[legacy], "Replaced by one issue per key (status/keys.json, the hub's Accounts tab).")
            notes.append(f"closed the old combined issue: {legacy}")
    return notes


def run(env=None, t=None, get=None, A=None, write=True):
    env = os.environ if env is None else env
    t = t or now()
    identity = load(IDENTITY, {}) or {}
    prev = {r.get("id"): r for r in ((load(OUT, {}) or {}).get("keys") or []) if isinstance(r, dict)}
    try:
        import mac_rows
        camps = (mac_rows.load_json(ROOT / "clips" / "campaigns.json", {}) or {}).get("campaigns") or {}
        rows = mac_rows.rows()
    except Exception as e: log("keys: submissions:", f"{type(e).__name__}: {str(e)[:80]}"); camps, rows = {}, []
    out = build(identity, env, prev, t, get, rows, camps)
    notes = []
    try: notes = announce(out, prev, t, A)
    except Exception as e: log("keys: issues:", f"{type(e).__name__}: {str(e)[:120]}")
    counts = {s: sum(1 for r in out if r["status"] == s) for s in ("ok", "expiring", "failing", "missing")}
    result = {"checked": stamp(t), "audit": identity.get("checked"), "counts": counts, "keys": out}
    if write:
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    for r in out: log(f"{r['status']:<9} {r['id']:<26} {r['expires'] or '-':<11} {r['detail'][:110]}")
    for n in notes: log("issues:", n)
    log(f"keys: {counts['ok']} ok, {counts['expiring']} expiring, {counts['failing']} failing, {counts['missing']} missing")
    return result


def show():
    d = load(OUT)
    if not d: print("no status/keys.json yet: the first audit run writes it"); return
    print(f"checked {d.get('checked')}: {d.get('counts')}")
    for r in d.get("keys") or []: print(f"{r['status']:<9} {r['id']:<26} {r.get('expires') or '-':<11} {r['detail'][:110]}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "show" in a or (os.environ.get("GITHUB_ACTIONS") != "true" and "now" not in a): show()
    else: run()
