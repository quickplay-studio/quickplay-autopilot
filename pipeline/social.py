"""Post Shorts to TikTok and Instagram once they are public on YouTube, and keep the sign-ins fresh.

usage:
  python pipeline/social.py post             post every Short that is public on YouTube and not yet on TikTok/Instagram
  python pipeline/social.py tiktok-connect   swap the one-time TikTok code (env TIKTOK_CODE) for tokens
  python pipeline/social.py refresh          refresh the Instagram and TikTok tokens
  python pipeline/social.py check            check both sign-ins, write status/social.json
  python pipeline/social.py ig-dry-run       prove Instagram can take a video from a release, without posting
  python pipeline/social.py ig-state         Instagram's own numbers -> status/instagram.json and the Instagram section of
                                             analytics/insights.md (analytics.py does this itself after every full run)
  python pipeline/social.py tiktok-stats     our TikTok posts' numbers (read-only) -> analytics/tiktok.csv

Sign-ins live in tokens/*.enc, encrypted with SOCIAL_KEY (a GitHub secret); IG_TOKEN and IG_USER_ID seed Instagram.
The TikTok/Instagram version of each Short (platform-safe music) waits in a draft GitHub release named social-<id>.
Nothing here prints a token.
"""
import base64, datetime as dt, hashlib, json, os, pathlib, re, subprocess, sys, time
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOK = ROOT / "tokens"
CFG = json.loads((ROOT / "config.json").read_text())
REPO = os.environ.get("GITHUB_REPOSITORY", "quickplay-studio/quickplay-autopilot")
IG_API = "https://graph.instagram.com/" + CFG.get("instagram_api_version", "v23.0")
TT_API = "https://open.tiktokapis.com/v2"
FB_API = "https://graph.facebook.com/" + CFG.get("facebook_api_version", "v25.0")
TT_REDIRECT = "https://quickplay-studio.github.io/quickplay-autopilot/tiktok-callback.html"
TT_SCOPES = "user.info.basic,user.info.stats,video.list,video.upload"    # no video.publish: no automatic public posting
NOW = lambda: dt.datetime.now(dt.timezone.utc)

# ---------- encrypted token store ----------
def _fernet():
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    key = os.environ.get("SOCIAL_KEY", "")
    if len(key) < 20: raise SystemExit("SOCIAL_KEY secret missing or too short")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"quickplay-social-v1", iterations=300_000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(key.encode())))

def load(name):
    p = TOK / f"{name}.enc"
    if p.exists(): return json.loads(_fernet().decrypt(p.read_bytes()))
    return {}

def save(name, data):
    TOK.mkdir(exist_ok=True)
    (TOK / f"{name}.enc").write_bytes(_fernet().encrypt(json.dumps(data).encode()))

# ---------- Instagram ----------
def ig_tokens():
    t = load("instagram")
    if not t and os.environ.get("IG_TOKEN"):
        t = {"token": os.environ["IG_TOKEN"], "user": os.environ.get("IG_USER_ID", ""), "saved": NOW().isoformat()}
        save("instagram", t)
    return t

def ig_refresh(t):
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": t["token"]}, timeout=30)
    if r.ok:
        t.update(token=r.json()["access_token"], saved=NOW().isoformat(), expires_in=r.json().get("expires_in"))
        save("instagram", t); return "instagram token refreshed"
    return f"instagram refresh failed ({r.status_code})"

# ---------- the channels' own Instagram and Facebook keys (24 October, audit M8) ----------
# IG_<CHANNEL>_TOKEN keys live only in GitHub secrets, which a workflow cannot rewrite, so left alone each stops 60 days
# after Charlie made it. The identity audit (every 3 hours, it holds every key) refreshes each one weekly with Instagram's
# refresh_access_token and keeps the new key encrypted in tokens/instagram_<channel>.enc; apply_stored_keys() then puts the
# refreshed key in place of the secret it grew from, for the clips runs and for the audit's own checks. A secret Charlie
# replaces starts a new line from itself. A key (Instagram or a channel's Facebook Page key) within 10 days of its end
# that could not be refreshed raises a needs-charlie issue.
IG_CHANNEL_KEY = re.compile(r"IG_([A-Z]+)_TOKEN")
FB_CHANNEL_KEY = re.compile(r"FB_([A-Z]+)_PAGE_TOKEN")
KEY_ISSUE = "🔑 An Instagram or Facebook key needs renewing"


def _seed(tok):
    return hashlib.sha256(tok.encode()).hexdigest()[:16]


def _when(s):
    try: return dt.datetime.fromisoformat(str(s))
    except (TypeError, ValueError): return None


def apply_stored_keys(env=None):
    """Each IG_<CHANNEL>_TOKEN in env whose stored key grew from the same secret is replaced by the stored (refreshed)
    key. Returns the names replaced. Needs SOCIAL_KEY; without it nothing changes."""
    env = os.environ if env is None else env
    done = []
    for name, v in list(env.items()):
        m, v = IG_CHANNEL_KEY.fullmatch(name), (v or "").strip()
        if not m or not v: continue
        try: s = load(f"instagram_{m.group(1).lower()}")
        except (Exception, SystemExit): continue
        if s.get("token") and s.get("seed") == _seed(v) and s["token"] != v:
            env[name] = s["token"]; done.append(name)
    return done


def refresh_meta_keys(env=None, get=None, now=None, every_days=7, warn_days=10, report=None, issues=True):
    """Refreshes every IG_<CHANNEL>_TOKEN weekly into tokens/instagram_<channel>.enc, checks every FB_<CHANNEL>_PAGE_TOKEN's
    expiry, and raises (or clears) the needs-charlie issue for keys close to their end. Returns notes for the log.
    report (a dict): each channel Facebook key's end as Graph's debug_token gave it, for the audit's key table
    (identity.py, keys.py) so the answer is asked once. issues=False: pipeline/keys.py owns the issues (one per key)."""
    env = os.environ if env is None else env
    get = get or requests.get
    now = now or NOW()
    notes, due = [], []
    for name, v in sorted(env.items()):
        m, v = IG_CHANNEL_KEY.fullmatch(name), (v or "").strip()
        if not m or not v: continue
        store = f"instagram_{m.group(1).lower()}"
        try: s = load(store)
        except (Exception, SystemExit) as e:
            notes.append(f"{name}: its store can't be read ({type(e).__name__})"); continue
        if s.get("seed") != _seed(v) and s.get("token") != v:      # first sight of this secret, or Charlie pasted a new one
            s = {"token": v, "seed": _seed(v), "user": env.get(f"IG_{m.group(1)}_USER_ID", ""), "first_seen": now.isoformat(timespec="minutes")}
        last = _when(s.get("refreshed")) or _when(s.get("tried"))
        if not last or (now - last).days >= every_days or not s.get("expires_at"):
            try:
                r = get("https://graph.instagram.com/refresh_access_token",
                        params={"grant_type": "ig_refresh_token", "access_token": s["token"]}, timeout=30)
                j = r.json() if r.content else {}
            except Exception as e:
                r, j = None, {"error": {"message": f"{type(e).__name__}"}}
            s["tried"] = now.isoformat(timespec="minutes")
            if r is not None and r.ok and j.get("access_token"):
                exp = now + dt.timedelta(seconds=int(j.get("expires_in") or 5184000))
                s.update(token=j["access_token"], refreshed=now.isoformat(timespec="minutes"), expires_at=exp.isoformat(timespec="minutes"), error="")
                notes.append(f"{name}: refreshed, good until {exp:%d %B}")
            else:
                s["error"] = f"refresh refused ({getattr(r, 'status_code', 'no answer')}): {str((j.get('error') or {}).get('message', ''))[:120]}"
                notes.append(f"{name}: {s['error']}")
        try: save(store, s)
        except (Exception, SystemExit) as e: notes.append(f"{name}: not saved ({type(e).__name__})")
        # its end: known after a refresh; for a secret never refreshed, 60 days from when it was first seen (the latest
        # it can run, since Charlie made it before then)
        end = _when(s.get("expires_at")) or ((_when(s.get("first_seen")) or now) + dt.timedelta(days=60))
        if s.get("error") and end - now < dt.timedelta(days=warn_days): due.append((name, end, "Instagram"))
    for name, v in sorted(env.items()):
        m, v = FB_CHANNEL_KEY.fullmatch(name), (v or "").strip()
        if not m or not v: continue
        try: d = (get(f"{FB_API}/debug_token", params={"input_token": v, "access_token": v}, timeout=30).json() or {}).get("data") or {}
        except Exception: continue                              # unreadable this time: the next audit asks again
        if report is not None and d: report[name] = {"expires_at": int(d.get("expires_at") or 0), "data_access_expires_at": int(d.get("data_access_expires_at") or 0)}
        for k in ("expires_at", "data_access_expires_at"):
            ts = int(d.get(k) or 0)
            if ts and dt.datetime.fromtimestamp(ts, dt.timezone.utc) - now < dt.timedelta(days=warn_days):
                due.append((name, dt.datetime.fromtimestamp(ts, dt.timezone.utc), "Facebook")); break
    try:
        import alerts as A
        if not issues: pass
        elif due:
            A.raise_issue(KEY_ISSUE, "These keys stop working soon and could not be refreshed automatically:\n" + "\n".join(
                f"- {n} ({kind}): ends {when:%A %d %B}" for n, when, kind in due) +
                "\n\nInstagram (IG_<NAME>_TOKEN): make a new long-lived key for that account in the Meta app "
                "(https://developers.facebook.com/apps, Instagram, API setup with Instagram login, Generate token) and paste it "
                "into the secret at https://github.com/quickplay-studio/quickplay-autopilot/settings/secrets/actions. Facebook "
                "(FB_<NAME>_PAGE_TOKEN): a new Page key from https://developers.facebook.com/tools/explorer/ (the studio account), "
                "pasted the same way. The audit refreshes Instagram keys by itself after that.", labels=["needs-charlie"])
            notes.append(f"renewal issue raised for {', '.join(n for n, _, _ in due)}")
        else: A.clear(KEY_ISSUE, "Every channel key is fresh again.")
    except Exception as e: notes.append(f"key issue: {type(e).__name__}: {str(e)[:100]}")
    return notes


def ig_post(t, video_url, caption, extra=None):
    """Reel from a public video URL: create a container, wait until Instagram has processed it, publish. `extra`: more
    container parameters (trial_params, thumb_offset: ig_publish)."""
    user = t.get("user") or os.environ.get("IG_USER_ID")
    r = requests.post(f"{IG_API}/{user}/media", data={"media_type": "REELS", "video_url": video_url, "caption": caption,
                                                       "share_to_feed": "true", **(extra or {}), "access_token": t["token"]}, timeout=60)
    if not r.ok: raise RuntimeError(f"instagram container: {r.status_code} {r.text[:300]}")
    cid = r.json()["id"]
    for _ in range(60):
        s = requests.get(f"{IG_API}/{cid}", params={"fields": "status_code,status", "access_token": t["token"]}, timeout=30).json()
        if s.get("status_code") == "FINISHED": break
        if s.get("status_code") in ("ERROR", "EXPIRED"): raise RuntimeError(f"instagram processing: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("instagram processing took too long")
    r = requests.post(f"{IG_API}/{user}/media_publish", data={"creation_id": cid, "access_token": t["token"]}, timeout=60)
    if not r.ok: raise RuntimeError(f"instagram publish: {r.status_code} {r.text[:300]}")
    return r.json()["id"]

# ---------- Instagram's own tests (24 October) ----------
# Instagram gets about 90 views a Reel from an account with 1 follower and 4.4 s average watch; the data report found it
# favours Gaming and Sport (relative to YouTube), that earlier-morning posts look better (small n) and that YouTube's views
# at 3 hours don't predict Instagram's (rank correlation 0.10). So Instagram picks its own Reels and tests its own levers,
# each fixed per Short by its id and recorded on the post (status/<id>.json "instagram"), so analytics scores it against
# Instagram views (drivers.analyse_instagram) and a proven arm takes most posts here (ig_share), never all:
# - which Reels: by category fit on Instagram (ig_category_scores), 1 in 4 an exploration pick from any category. From 25
#   October Instagram goes first (config instagram_first): a Short in a favoured category (ig_favoured: Instagram's own
#   median views for the category are above typical; Gaming and Sport until 15 Reels are measured) is posted at the first run
#   after it is public, newest first, whatever its YouTube views (nothing here reads them: the data says 3-hour YouTube
#   views don't predict Instagram), inside the hour test's rules;
# - when: half held to the UK morning (instagram_morning_hours), half as soon as they are public, each with its own share
#   of the day's cap so neither starves the other;
# - trial reels for half (shown first to non-followers; graduated by Meta when they do well, SS_PERFORMANCE). Meta added
#   trial_params to the Content Publishing API on 3 December 2025, for Instagram Login and Facebook Login apps alike
#   (developers.facebook.com/docs/instagram-platform/changelog; reference: .../instagram-graph-api/reference/ig-user/media:
#   "trial_params ... graduation_strategy: MANUAL or SS_PERFORMANCE", media_type REELS only);
# - a short caption (the spoken hook and the category's own hashtags, config instagram_hashtags) for half against the full
#   one (title, summary, YouTube line, the board's 5);
# - the cover frame (thumb_offset, ms) inside the opening beat, where the hook is on screen (the reference: "Location, in
#   milliseconds, of the video or reel frame to be used as the cover thumbnail image", default 0). Each post records
#   whether Instagram accepted it ("thumb": accepted, refused or off); ig_cover_check tallies that into status/social.json.
# Captions allow 2,200 characters, 30 hashtags and 20 @ tags (the same reference); we use 5 or 3 hashtags.
def ig_arm(sid, salt, share, a, b):
    """Arm `a` for a `share` of Shorts, else `b`, fixed by the Short's id and the test's salt (a re-run gives the same)."""
    h = int(hashlib.sha256(f"{salt}:{sid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return a if h < share else b


def ig_share(feature, a, b, default=0.5):
    """The share of posts for arm `a` of an Instagram test (arm `b` gets the rest): `default` until drivers.csv proves an
    arm against Instagram views (a push for `a` or a cut back for `b`: 0.8; the reverse: 0.2), never 0 or 1, so the
    test keeps measuring."""
    import csv
    try:
        v = {r.get("value"): r.get("verdict") for r in csv.DictReader((ROOT / "analytics" / "drivers.csv").open()) if r.get("feature") == feature}
    except (FileNotFoundError, csv.Error): return default
    if v.get(a) == "push" or v.get(b) == "cut back": return 0.8
    if v.get(b) == "push" or v.get(a) == "cut back": return 0.2
    return default


IG_MIN_REELS = 15           # measured Reels before Instagram's own medians replace instagram_category_order
IG_ARMS = (("trial", "ig_trial", "yes", "no", "Trial reel", "instagram_trial", "instagram_trial_share"),
           ("caption", "ig_caption", "short", "full", "Caption", "instagram_caption_test", "instagram_caption_share"),
           ("hour", "ig_hour", "morning", "any", "Posting hour", "instagram_hour_test", "instagram_hour_share"))


def ig_reels(now=None):
    """Instagram's measured Reels, from analytics/shorts.csv (the file the picker reads): those a day old or more with an
    Instagram view count, as {"category", "views", "at" (when it went to Instagram: ig_posted, else the YouTube time), "arms"
    (ig_trial, ig_caption, ig_hour, ig_pick)}."""
    import csv
    now, out = now or NOW(), []
    try:
        for r in csv.DictReader((ROOT / "analytics" / "shorts.csv").open()):
            try: v = float(r.get("ig_views"))
            except (TypeError, ValueError): continue
            cat, at = r.get("category"), r.get("ig_posted") or r.get("posted")
            if v != v or not cat or not at: continue
            try: t = dt.datetime.fromisoformat(str(at).replace("Z", "+00:00"))
            except ValueError: continue
            if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
            if (now - t).total_seconds() >= 86400:
                out.append({"category": cat, "views": v, "at": t, "arms": {k: r.get(k) or "" for k in ("ig_trial", "ig_caption", "ig_hour", "ig_pick")}})
    except (FileNotFoundError, csv.Error): pass
    return out


def ig_category_scores(min_reels=IG_MIN_REELS):
    """How each category does on Instagram, {category: score} with 1.0 typical: the median views of its Reels a day old or
    more over the median of all of them, shrunk towards 1 by 5 Reels' worth (on the log scale). Under `min_reels`
    measured Reels: instagram_category_order (the data report: Gaming and Sport) at 1.5, the rest 1.0."""
    import math, statistics
    vals = {}
    for r in ig_reels(): vals.setdefault(r["category"], []).append(r["views"])
    every = [x for v in vals.values() for x in v]
    base = statistics.median(every) if every else 0
    if len(every) < min_reels or base <= 0:
        return {c: 1.5 for c in CFG.get("instagram_category_order", ["Gaming", "Sport"])}
    return {c: round(math.exp(math.log(max(0.05, statistics.median(v) / base)) * len(v) / (len(v) + 5)), 3) for c, v in vals.items()}


def ig_favoured(scores=None):
    """The categories Instagram favours, from its own numbers: a score of instagram_favour_min (1.05) or more in
    ig_category_scores. A category in instagram_category_order that Instagram has no numbers for yet stays favoured (the
    prior stands until the data speaks), so with under 15 measured Reels it is the order itself (Gaming and Sport)."""
    scores = ig_category_scores() if scores is None else scores
    lo = float(CFG.get("instagram_favour_min", 1.05))
    return {c for c, v in scores.items() if v >= lo} | {c for c in CFG.get("instagram_category_order", ["Gaming", "Sport"]) if c not in scores}


def ig_choose(statuses, cap, now=None, category_of=None):
    """The Shorts Instagram takes this run and how: {id: {"pick": "category" | "explore", "hour": "morning" | "any",
    "favoured": bool}}. Eligible: public on YouTube within crosspost_max_age_hours, a social release, not posted or skipped
    yet, and for the morning arm only inside instagram_morning_hours (UK). The day's cap (ramp_cap) is shared between the
    hour arms by their shares, counted over the last 24 hours, so the morning Reels always have room; at most
    instagram_max_per_run a run (no bursts).
    Instagram first (config instagram_first, 25 October): a Short in a favoured category (ig_favoured) and an exploration
    pick share the top tier, newest first, so a Short Instagram favours goes out at the first run after it is public and
    is not held behind an older one; the rest follow by category score, newest first. Nothing here reads the Short's
    YouTube views: on 24 October our 96 Shorts with both numbers showed views at 3 hours do not predict Instagram's
    (rank correlation 0.10), so a favoured Short with few views is posted just the same."""
    from zoneinfo import ZoneInfo
    now = now or NOW()
    category_of = category_of or (lambda s: (board_for(s) or {}).get("category", ""))
    fresh_h = float(CFG.get("crosspost_max_age_hours", 48))
    lo, hi = (CFG.get("instagram_morning_hours") or [6, 10])[:2]
    in_morning = int(lo) <= now.astimezone(ZoneInfo("Europe/London")).hour < int(hi)
    share_m = ig_share("ig_hour", "morning", "any", float(CFG.get("instagram_hour_share", 0.5))) if CFG.get("instagram_hour_test", True) else 0.0
    recent = {"morning": 0, "any": 0}
    for s in statuses:
        ig = s.get("instagram") if isinstance(s.get("instagram"), dict) else None
        if not ig: continue
        try: at = dt.datetime.fromisoformat(str(ig.get("at")).replace("Z", "+00:00"))
        except ValueError: continue
        if now - at <= dt.timedelta(hours=24): recent["morning" if ig.get("hour") == "morning" else "any"] += 1
    cap_m = round(cap * share_m)
    room = {"morning": max(0, cap_m - recent["morning"]), "any": max(0, cap - cap_m - recent["any"])}
    scores = ig_category_scores()
    top = max(list(scores.values()) + [1.0])
    first = bool(CFG.get("instagram_first", True))
    favoured = ig_favoured(scores) if first else set()
    exp_share = float(CFG.get("instagram_explore_share", 0.25))
    elig = []
    for s in statuses:
        if not (s.get("id") and s.get("video") and s.get("social_release") and s.get("publish_at")): continue
        if s.get("instagram") or s.get("instagram_skipped"): continue
        try: pa = dt.datetime.fromisoformat(str(s["publish_at"]).replace("Z", "+00:00"))
        except ValueError: continue
        if not 0 <= (now - pa).total_seconds() / 3600 <= fresh_h: continue
        hour = ig_arm(s["id"], "ig-hour", share_m, "morning", "any") if share_m > 0 else "any"
        if hour == "morning" and not in_morning: continue
        pick = ig_arm(s["id"], "ig-explore", exp_share, "explore", "category")
        cat = category_of(s)
        fav = cat in favoured
        score = top if pick == "explore" else scores.get(cat, 1.0)
        # the top tier (favoured category or exploration pick) goes newest first; the rest by score, then newest first
        rank = (0, -pa.timestamp()) if first and (fav or pick == "explore") else (1, -score, -pa.timestamp())
        elig.append((rank, s["id"], pick, hour, fav))
    out, per_run = {}, int(CFG.get("instagram_max_per_run", 2))
    for _, sid, pick, hour, fav in sorted(elig):
        if len(out) >= per_run: break
        if room[hour] <= 0: continue
        room[hour] -= 1; out[sid] = {"pick": pick, "hour": hour, "favoured": fav}
    return out


def ig_hook_ms(st):
    """The cover frame (thumb_offset, ms): inside the opening beat, where the hook is on screen (the middle of beat 0, at
    most 1.2 s in, from status "timeline"); 1,000 ms without one."""
    try:
        t0, t1 = float(st["timeline"][0][0]), float(st["timeline"][0][1])
        return int(1000 * min(t0 + 1.2, (t0 + t1) / 2))
    except (KeyError, IndexError, TypeError, ValueError): return 1000


def ig_trial_ok():
    """Trial reels are asked for unless Meta refused one in the last 14 days (status/instagram_trial.json)."""
    try: s = json.loads((ROOT / "status" / "instagram_trial.json").read_text())
    except Exception: return True
    try: return NOW() - dt.datetime.fromisoformat(s["refused"]) > dt.timedelta(days=14)
    except Exception: return True


def ig_cover_until():
    """When the cover frame may be asked for again, or None: Meta refused it less than instagram_cover_pause_days (3) days
    ago (status/instagram_cover.json)."""
    try:
        s = json.loads((ROOT / "status" / "instagram_cover.json").read_text())
        until = dt.datetime.fromisoformat(s["refused"]) + dt.timedelta(days=float(CFG.get("instagram_cover_pause_days", 3)))
    except Exception: return None
    return until if NOW() < until else None


def ig_cover_ok():
    """The cover frame is asked for unless Meta refused one in the last instagram_cover_pause_days days."""
    return ig_cover_until() is None


def ig_transient(msg):
    """Whether a refused container call is Meta failing for a moment (a 5xx answer, 429, or "is_transient"), not a setting
    it will not take: the Reel is tried again at the next run with all its settings, nothing is remembered as refused."""
    m = re.match(r"instagram container: (\d+)", msg)
    return bool((m and (int(m.group(1)) >= 500 or int(m.group(1)) == 429)) or re.search(r'"is_transient"\s*:\s*true', msg))


def _refused(name, error):
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / name).write_text(json.dumps({"refused": NOW().isoformat(timespec="minutes"), "error": (error or "")[:300]}, indent=1))


def ig_publish(t, video_url, cap, trial=False, thumb_ms=None):
    """ig_post with this Reel's test settings. Meta can refuse the container over either one, so they are tried in turn,
    the most wanted first: both, the cover frame alone, the trial alone, neither. A refused trial is remembered for 14 days
    (status/instagram_trial.json) and a refused cover frame for instagram_cover_pause_days (status/instagram_cover.json), so
    the next Reels don't ask. A failure after the container (processing, publishing) is not about the settings and is
    raised as it is, and so is a container failure that is Meta failing for a moment (ig_transient).
    Returns (media id, {"trial": "yes" | "no" | "refused", "thumb_ms": ms or None, "thumb": "accepted" | "refused" | "off"}):
    "thumb" is the check that Instagram took the cover frame ("off": none was asked for)."""
    asked = {}
    if trial: asked["trial_params"] = json.dumps({"graduation_strategy": CFG.get("instagram_trial_strategy", "SS_PERFORMANCE")})
    if thumb_ms is not None: asked["thumb_offset"] = str(int(thumb_ms))
    tries = [asked]
    if len(asked) == 2: tries += [{"thumb_offset": asked["thumb_offset"]}, {"trial_params": asked["trial_params"]}]
    if asked: tries.append({})
    first = None
    for ex in tries:
        try: mid = ig_post(t, video_url, cap, ex or None)
        except RuntimeError as e:
            if not str(e).startswith("instagram container") or ig_transient(str(e)): raise
            first = first or str(e); continue
        used = {"trial": "yes" if "trial_params" in ex else ("refused" if trial else "no"),
                "thumb_ms": int(ex["thumb_offset"]) if "thumb_offset" in ex else None,
                "thumb": "accepted" if "thumb_offset" in ex else ("refused" if thumb_ms is not None else "off")}
        if used["trial"] == "refused": _refused("instagram_trial.json", first)
        if used["thumb"] == "refused": _refused("instagram_cover.json", first)
        return mid, used
    raise RuntimeError(first or "instagram container: refused")


def ig_cover_check(statuses=None, now=None, days=14):
    """The check that Instagram accepted the cover frame (thumb_offset at the hook frame), from the posts of the last `days`
    days (status/<id>.json instagram.thumb; a post from before that field counts as accepted when it kept thumb_ms):
    {"asked", "accepted", "refused", "last" (the newest post's answer), "last_at", "ok" (the newest was accepted; None when
    none has been asked yet), "paused_until" (when Meta's refusal stops it being asked for)}."""
    now = now or NOW()
    out, last = {"asked": 0, "accepted": 0, "refused": 0}, None
    for s in (_statuses() if statuses is None else statuses):
        ig = s.get("instagram") if isinstance(s.get("instagram"), dict) else None
        if not ig: continue
        try: at = dt.datetime.fromisoformat(str(ig.get("at")).replace("Z", "+00:00"))
        except ValueError: continue
        if at.tzinfo is None: at = at.replace(tzinfo=dt.timezone.utc)
        if now - at > dt.timedelta(days=days): continue
        answer = ig.get("thumb") or ("accepted" if ig.get("thumb_ms") is not None else None)
        if answer not in ("accepted", "refused"): continue
        out["asked"] += 1; out[answer] += 1
        key = (at, str(s.get("id") or ""))                  # the newest post's answer; the later id on a tie
        if last is None or key > last[0]: last = (key, answer)
    until = ig_cover_until()
    out.update(last=last[1] if last else None, last_at=last[0][0].isoformat(timespec="minutes") if last else None,
               ok=None if not last else last[1] == "accepted", paused_until=until.isoformat(timespec="minutes") if until else None)
    return out


# ---------- Instagram's own numbers, for insights.md and the hub (25 October) ----------
def _rows(rel):
    import csv
    try: return list(csv.DictReader((ROOT / rel).open()))
    except (FileNotFoundError, csv.Error): return []


def ig_state(followers=None, now=None):
    """Instagram's own numbers in one place: the category medians the picker reads (ig_category_scores) and the categories
    it posts first (ig_favoured), the three tests' arms (Reels measured, median Instagram views, the share of new Reels each
    arm gets, drivers.csv's verdict), the followers now and a week ago, the last 7 days against the 7 before, and the cover
    frame check. The Instagram section of analytics/insights.md (ig_lines) and the hub's Instagram card (status/instagram.json)
    both say exactly this."""
    import statistics
    now = now or NOW()
    reels = ig_reels(now)
    every = [r["views"] for r in reels]
    base = statistics.median(every) if every else None
    scores, by = ig_category_scores(), {}
    favoured = ig_favoured(scores)
    for r in reels: by.setdefault(r["category"], []).append(r["views"])
    cats = [{"category": c, "median": statistics.median(by[c]) if c in by else None, "n": len(by.get(c, [])), "score": scores.get(c),
             "favoured": c in favoured} for c in set(by) | favoured]
    cats.sort(key=lambda c: (-(c["score"] if c["score"] is not None else 1.0), -(c["median"] or 0), c["category"]))
    drv = {(r.get("feature"), r.get("value")): r for r in _rows("analytics/drivers.csv") if str(r.get("feature", "")).startswith("ig_")}
    tests = {}
    for key, feat, a, b, label, flag, share_key in IG_ARMS:
        share_a = ig_share(feat, a, b, float(CFG.get(share_key, 0.5)))
        arms = {}
        for arm, share in ((a, share_a), (b, 1 - share_a)):
            v = [r["views"] for r in reels if r["arms"].get(feat) == arm]
            d = drv.get((feat, arm)) or {}
            arms[arm] = {"n": len(v), "median": statistics.median(v) if v else None, "share": round(share, 2),
                         "verdict": d.get("verdict") or "", "lift": d.get("lift") or ""}
        tests[key] = {"label": label, "feature": feat, "on": bool(CFG.get(flag, True)), "arms": arms,
                      "paused": key == "trial" and bool(CFG.get(flag, True)) and not ig_trial_ok()}
    if followers is None:
        try: followers = ((json.loads((ROOT / "analytics" / "summary.json").read_text())).get("instagram") or {}).get("followers")
        except Exception: followers = None
    before, cut = None, f"{now - dt.timedelta(days=7):%Y-%m-%d}"
    for r in sorted((r for r in _rows("analytics/daily.csv") if r.get("source") == "snapshot" and str(r.get("ig_followers", "")).strip() != ""),
                    key=lambda r: r.get("day", "")):
        try:
            if r["day"] <= cut: before = int(float(r["ig_followers"]))
        except (KeyError, ValueError): pass
    wk = [r["views"] for r in reels if now - r["at"] <= dt.timedelta(days=7)]
    prev = [r["views"] for r in reels if dt.timedelta(days=7) < now - r["at"] <= dt.timedelta(days=14)]
    return {"updated": now.isoformat(timespec="minutes"), "followers": followers, "followers_week_ago": before,
            "reels": len(every), "median_views": base, "own_medians": len(every) >= IG_MIN_REELS and bool(base), "min_reels": IG_MIN_REELS,
            "first": bool(CFG.get("instagram_first", True)), "favour_min": float(CFG.get("instagram_favour_min", 1.05)),
            "favoured": sorted(favoured), "categories": cats, "tests": tests,
            "week": {"reels": len(wk), "median": statistics.median(wk) if wk else None,
                     "before_reels": len(prev), "before_median": statistics.median(prev) if prev else None},
            "cover": ig_cover_check(now=now)}


def ig_lines(s):
    """The Instagram section of analytics/insights.md, as lines, from ig_state's numbers (no em or en dashes, UK English).
    It sits after the Recipe, so the writer is never shown it (writer.recipe reads the Recipe section only)."""
    n = lambda x: "none yet" if x is None else f"{x:,.0f}"
    L = ["## Instagram (its own numbers, never shown to the writer)"]
    have = sorted((c for c in s["categories"] if c["median"] is not None), key=lambda c: -c["median"])
    basis = "Instagram's own medians" if s["own_medians"] else f"the configured order until {s['min_reels']} Reels are measured"
    first = (f"Posted first, as soon as they are public: {', '.join(s['favoured']) or 'none'} ({basis}; a weight of {s['favour_min']:g} or more)."
             if s["first"] else "Instagram first is off: the order is by category weight.")
    L.append((f"- Category medians, Instagram views per Reel a day old or more ({s['reels']} Reels, typical {n(s['median_views'])}): "
              + ", ".join(f"{c['category']} {n(c['median'])} ({c['n']})" for c in have) + ". ") if have
             else "- Category medians: no Reel has a full day of numbers yet. ")
    L[-1] += first
    parts = []
    for t in s["tests"].values():
        if not t["on"]: parts.append(f"{t['label'].lower()} off"); continue
        (ka, a), (kb, b) = list(t["arms"].items())
        arm = lambda k, x: f"{k} {x['n']}" + (f" at {n(x['median'])} views" if x["n"] else "") + (f", {x['verdict']}" if x["verdict"] in ("push", "cut back") else "")
        parts.append(f"{t['label'].lower()} {arm(ka, a)} against {arm(kb, b)} ({round(100 * a['share'])}/{round(100 * b['share'])})"
                     + (", paused after Meta refused one" if t["paused"] else ""))
    L.append("- Tests, every Reel takes an arm of each (Reels measured, median views, the share of new Reels each arm gets): " + "; ".join(parts) + ".")
    f, w, c = s["followers"], s["week"], s["cover"]
    L.append(f"- Followers: {n(f) if f is not None else 'not read this time'}"
             + (f" ({s['followers_week_ago']:,} a week ago)" if s["followers_week_ago"] is not None else "")
             + f". Last 7 days: {w['reels']} Reels measured" + (f", median {n(w['median'])} views" if w["reels"] else "")
             + f"; the 7 days before: {w['before_reels']}" + (f", median {n(w['before_median'])}" if w["before_reels"] else "") + ".")
    L.append("- Cover frame at the hook: " + (f"accepted on {c['accepted']} of {c['asked']} Reels asked in 14 days"
                                             + (f", refused on {c['refused']}" if c["refused"] else "") if c["asked"] else "not asked yet")
             + (f"; not asked again until {c['paused_until'][:10]}" if c.get("paused_until") else "") + ".")
    return L


def ig_write_insights(lines, path=None):
    """Puts `lines` at the end of analytics/insights.md as its Instagram section, replacing the last one (a rerun is the
    same file). False when there is no insights.md yet."""
    p = path or ROOT / "analytics" / "insights.md"
    try: text = p.read_text()
    except FileNotFoundError: return False
    text = re.sub(r"\n## Instagram\b.*?(?=\n## |\Z)", "", text, flags=re.S).rstrip("\n")
    p.write_text(text + "\n\n" + "\n".join(lines) + "\n")
    return True


def ig_report(followers=None):
    """status/instagram.json (the hub's Instagram card) and the Instagram section of analytics/insights.md, from the same
    ig_state. analytics.py calls this after it writes insights.md on every full run; python pipeline/social.py ig-state does
    it by hand. Returns the state."""
    s = ig_state(followers)
    (ROOT / "status").mkdir(exist_ok=True)
    (ROOT / "status" / "instagram.json").write_text(json.dumps(s, indent=1, ensure_ascii=False))
    ig_write_insights(ig_lines(s))
    return s


# ---------- TikTok ----------
def tt_connect():
    code = os.environ.get("TIKTOK_CODE", "").strip()
    if not code: raise SystemExit("no TikTok code given")
    r = requests.post(f"{TT_API}/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "code": code, "grant_type": "authorization_code", "redirect_uri": TT_REDIRECT})
    j = r.json()
    note = ROOT / "status" / "tiktok_connect.json"; note.parent.mkdir(exist_ok=True)
    if "access_token" not in j:   # keep TikTok's reason where Charlie and Claude can see it (no keys or codes in it)
        note.write_text(json.dumps({"at": NOW().isoformat(timespec="seconds"), "ok": False, "error": j.get("error"),
                                    "description": str(j.get("error_description", ""))[:300]}, indent=1))
        print("TikTok refused the code:", j.get("error"), j.get("error_description", "")); return
    note.write_text(json.dumps({"at": NOW().isoformat(timespec="seconds"), "ok": True, "scopes": j.get("scope")}, indent=1))
    save("tiktok", {k: j.get(k) for k in ("access_token", "refresh_token", "open_id", "scope", "expires_in", "refresh_expires_in")}
         | {"saved": NOW().isoformat()})
    print("tiktok connected, scopes:", j.get("scope"))

def tt_refresh(t):
    r = requests.post(f"{TT_API}/oauth/token/", headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30, data={
        "client_key": os.environ["TIKTOK_CLIENT_KEY"], "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
    j = r.json()
    if "access_token" not in j: return f"tiktok refresh failed: {j.get('error')}"
    t.update({k: j.get(k) for k in ("access_token", "refresh_token", "expires_in", "refresh_expires_in")}, saved=NOW().isoformat())
    save("tiktok", t); return "tiktok token refreshed"

class TikTokStop(RuntimeError):
    """TikTok says the account is posting too much or is banned from posting (a spam_risk code): TikTok stops until Charlie
    has looked (status/tiktok_safety.json and an issue)."""


TT_STOP_CODES = ("spam_risk_user_banned_from_posting", "spam_risk_too_many_posts")
TT_WAIT_CODES = ("spam_risk_too_many_pending_share", "rate_limit_exceeded", "reached_active_user_cap")


def tt_error(where, err):
    """The exception for a TikTok error object: TikTokStop for the account-level spam codes, RuntimeError otherwise."""
    code = str((err or {}).get("code") or "")
    msg = f"tiktok {where}: {code} {str((err or {}).get('message') or '')[:160]}".strip()
    return TikTokStop(msg) if code in TT_STOP_CODES else RuntimeError(msg)


def tt_privacy(info):
    """The privacy for a direct post (24 October, TikTok's Content Sharing Guidelines): never chosen as public by us.
    config tiktok_privacy (Charlie's choice) when creator_info offers it, else SELF_ONLY (only me); refused otherwise."""
    opts = list(info.get("privacy_level_options") or [])
    want = str(CFG.get("tiktok_privacy") or "SELF_ONLY")
    if want in opts: return want
    raise RuntimeError(f"tiktok privacy: {want} is not one of the account's options ({', '.join(opts) or 'none'})")


def tt_post(t, path, caption, mode, seconds=None):
    """mode "inbox": the video lands in the TikTok inbox as a draft for Charlie to finish and post in the app (no audit
    needed; TikTok allows 5 pending drafts in 24 hours). mode "direct": posts at once with the privacy tt_privacy() picks,
    which is never public unless Charlie set tiktok_privacy (an unaudited app may only post SELF_ONLY, and TikTok's audit
    is not open to tools that post to their owner's own account). Returns the publish_id; tt_status() tells whether it
    landed."""
    h = {"Authorization": f"Bearer {t['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
    size = path.stat().st_size
    src = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    if mode == "direct":
        q = requests.post(f"{TT_API}/post/publish/creator_info/query/", headers=h, timeout=30).json()
        if (q.get("error") or {}).get("code") not in (None, "ok"): raise tt_error("creator info", q["error"])
        info = q.get("data") or {}
        top = info.get("max_video_post_duration_sec")
        if seconds and top and float(seconds) > float(top):
            raise RuntimeError(f"tiktok: the video runs {float(seconds):.0f} s, over the account's {top} s")
        body = {"post_info": {"title": caption[:2200], "privacy_level": tt_privacy(info),
                              "disable_comment": bool(info.get("comment_disabled")), "disable_duet": bool(info.get("duet_disabled")),
                              "disable_stitch": bool(info.get("stitch_disabled")), "video_cover_timestamp_ms": 1000,
                              "brand_content_toggle": False, "brand_organic_toggle": False, "is_aigc": True}, "source_info": src}
        url = f"{TT_API}/post/publish/video/init/"
    else:
        body, url = {"source_info": src}, f"{TT_API}/post/publish/inbox/video/init/"
    r = requests.post(url, headers=h, json=body, timeout=60).json()
    if (r.get("error") or {}).get("code") not in (None, "ok"): raise tt_error("init", r["error"])
    d = r["data"]
    up = requests.put(d["upload_url"], data=path.read_bytes(), timeout=300,
                      headers={"Content-Type": "video/mp4", "Content-Length": str(size), "Content-Range": f"bytes 0-{size - 1}/{size}"})
    if up.status_code not in (200, 201): raise RuntimeError(f"tiktok upload: {up.status_code} {up.text[:200]}")
    return d["publish_id"]

TT_LANDED = ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE")


def tt_status(t, publish_id, tries=1, wait=10):
    """TikTok's word on an upload (Get Post Status): {"status", "fail_reason", "post_ids"}; status SEND_TO_USER_INBOX (a
    draft waits in the app) or PUBLISH_COMPLETE (posted) means it landed, FAILED that it did not, PROCESSING_* that it is
    still going (asked again next run)."""
    h = {"Authorization": f"Bearer {t['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
    out = {"status": "", "fail_reason": None, "post_ids": []}
    for i in range(max(1, tries)):
        if i: time.sleep(wait)
        r = requests.post(f"{TT_API}/post/publish/status/fetch/", headers=h, json={"publish_id": publish_id}, timeout=30).json()
        if (r.get("error") or {}).get("code") not in (None, "ok"): raise tt_error("status", r["error"])
        d = r.get("data") or {}
        out = {"status": d.get("status") or "", "fail_reason": d.get("fail_reason"),
               "post_ids": d.get("publicaly_available_post_id") or d.get("publicly_available_post_id") or []}
        if out["status"] and not out["status"].startswith("PROCESSING"): break
    return out


def tt_settle(t, st):
    """Moves a pending TikTok upload to "tiktok" once TikTok confirms it landed, to tiktok_error when it failed; leaves it
    pending while TikTok is still processing. True when st changed."""
    p = st.get("tiktok_pending")
    if not p: return False
    s = tt_status(t, p["publish_id"])
    if s["status"] in TT_LANDED:
        st["tiktok"] = {**p, "status": s["status"], **({"post_ids": s["post_ids"]} if s["post_ids"] else {})}
        st.pop("tiktok_pending", None); st.pop("tiktok_error", None)
    elif s["status"] == "FAILED":
        st["tiktok_error"] = f"{NOW():%Y-%m-%d %H:%M} failed: {s['fail_reason']}"[:300]; st.pop("tiktok_pending", None)
    elif s["status"]:
        p["last_status"] = s["status"]
        if NOW() - dt.datetime.fromisoformat(p["at"]) > dt.timedelta(hours=24):      # never confirmed: count it as failed
            st["tiktok_error"] = f"{NOW():%Y-%m-%d %H:%M} still {s['status']} after 24 hours"; st.pop("tiktok_pending", None)
    return True


def tt_sent_24h(statuses=None):
    """TikTok uploads (landed or pending) in the last 24 hours: TikTok allows 5 pending drafts in any 24 hours, and a young
    account posting in a burst is what its spam checks look for (the 19 October block)."""
    n = 0
    for st in statuses if statuses is not None else _statuses():
        for k in ("tiktok", "tiktok_pending"):
            try: at = dt.datetime.fromisoformat(str((st.get(k) or {}).get("at") or "").replace("Z", "+00:00"))
            except (ValueError, AttributeError): continue
            if NOW() - at <= dt.timedelta(hours=24): n += 1
    return n


def tt_cap(mode):
    """TikTok uploads allowed in 24 hours: config tiktok_per_day (2 to start, the 24 October plan), never over TikTok's 5
    pending drafts for the inbox."""
    n = int(CFG.get("tiktok_per_day", 2))
    return min(n, 5) if mode == "inbox" else n


def tt_safety():
    """The TikTok stop (status/tiktok_safety.json): set when TikTok answered with an account-level spam code; posting stays
    off until Charlie deletes the file (or sets "cleared") after checking the app's Account status page."""
    try: s = json.loads((ROOT / "status" / "tiktok_safety.json").read_text())
    except Exception: return {}
    return {} if s.get("cleared") else s


def tt_stop(why):
    p = ROOT / "status" / "tiktok_safety.json"; p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({"stopped": NOW().isoformat(timespec="minutes"), "why": str(why)[:300],
                             "what_to_do": "Open the TikTok app: Settings and privacy, Account, Account status. When it is clear, "
                                           "delete status/tiktok_safety.json (or set \"cleared\": true)."}, indent=1))
    try:
        import alerts as A
        A.raise_issue("⛔ TikTok stopped posting: the account was flagged", f"TikTok answered: {str(why)[:200]}. Nothing more goes "
                      "to TikTok until you have checked the app (Settings and privacy, Account, Account status) and the file "
                      "status/tiktok_safety.json is deleted. Never open a new account to get round it.")
    except Exception as e: print("tiktok stop issue:", str(e)[:120])


def _statuses():
    out = []
    for sp in (ROOT / "status").glob("QD-*.json"):
        try: out.append(json.loads(sp.read_text()))
        except Exception: pass
    return out


TT_FIELDS = ["video", "created", "duration", "title", "url", "views", "likes", "comments", "shares", "short", "as_of"]


def tt_stats():
    """Our own TikTok numbers, read-only (Display API, scope video.list): every public post's views, likes, comments and
    shares to analytics/tiktok.csv, matched to its Short where it can be (the post id TikTok gave the upload, else the
    caption's words and the draft's time), plus followers to status/tiktok_account.json. Dormant until a TikTok sign-in
    exists. TikTok shows SELF_ONLY posts to nobody, so they never appear here."""
    try: tt = load("tiktok")
    except SystemExit: tt = {}
    if not tt.get("access_token"): print("tiktok stats: not connected"); return 0
    if tt.get("refresh_token") and _age_h(tt) > 20 and os.environ.get("TIKTOK_CLIENT_KEY"): print(tt_refresh(tt)); tt = load("tiktok")
    h = {"Authorization": f"Bearer {tt['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
    fields = "id,create_time,duration,title,video_description,share_url,view_count,like_count,comment_count,share_count"
    vids, cursor = [], None
    for _ in range(10):                                          # 20 a page, newest first: the last 200 posts
        body = {"max_count": 20, **({"cursor": cursor} if cursor else {})}
        r = requests.post(f"{TT_API}/video/list/", params={"fields": fields}, headers=h, json=body, timeout=30)
        j = r.json() if r.content else {}
        if not r.ok or (j.get("error") or {}).get("code") not in (None, "ok"):
            print("tiktok stats:", r.status_code, str(j.get("error"))[:160]); break
        d = j.get("data") or {}; vids += d.get("videos") or []
        if not d.get("has_more"): break
        cursor = d.get("cursor")
    sts = [s for s in _statuses() if s.get("tiktok") or s.get("tiktok_pending")]
    words = lambda x: set(re.findall(r"[a-z0-9']{4,}", str(x or "").lower()))
    rows, now = [], NOW().isoformat(timespec="minutes")
    for v in vids:
        made = dt.datetime.fromtimestamp(int(v.get("create_time") or 0), dt.timezone.utc)
        short = next((s["id"] for s in sts if str(v.get("id")) in [str(x) for x in (s.get("tiktok") or {}).get("post_ids") or []]), "")
        if not short:          # a draft Charlie posted: the Short whose caption shares the most words, sent before the post
            best, score = "", 0
            for s in sts:
                t0 = (s.get("tiktok") or s.get("tiktok_pending") or {}).get("at")
                try: sent = dt.datetime.fromisoformat(str(t0).replace("Z", "+00:00"))
                except ValueError: continue
                if not (sent <= made <= sent + dt.timedelta(days=3)): continue
                cap = (s.get("tiktok") or {}).get("caption") or s.get("title") or ""
                k = len(words(cap) & (words(v.get("title")) | words(v.get("video_description"))))
                if k > score: best, score = s["id"], k
            short = best if score >= 3 else ""
        rows.append({"video": v.get("id"), "created": made.isoformat(timespec="minutes"), "duration": v.get("duration"),
                     "title": str(v.get("title") or v.get("video_description") or "")[:120], "url": v.get("share_url", ""),
                     "views": v.get("view_count", 0), "likes": v.get("like_count", 0), "comments": v.get("comment_count", 0),
                     "shares": v.get("share_count", 0), "short": short, "as_of": now})
    import csv
    p = ROOT / "analytics" / "tiktok.csv"; p.parent.mkdir(exist_ok=True)
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TT_FIELDS); w.writeheader(); w.writerows(rows)
    try:
        u = requests.get(f"{TT_API}/user/info/", params={"fields": "open_id,display_name,follower_count,likes_count,video_count"},
                         headers=h, timeout=30).json()
        user = (u.get("data") or {}).get("user") or {}
        if user: (ROOT / "status" / "tiktok_account.json").write_text(json.dumps(
            {"as_of": now, **{k: user.get(k) for k in ("display_name", "follower_count", "likes_count", "video_count")}}, indent=1))
    except Exception as e: print("tiktok account:", str(e)[:120])
    print(f"tiktok stats: {len(rows)} posts, {sum(1 for r in rows if r['short'])} matched to Shorts")
    return len(rows)

# ---------- Facebook Page Reels ----------
_FB = {}
def fb_tokens():
    """The Page key and Page id from GitHub secrets (FB_PAGE_TOKEN, FB_PAGE_ID); None until both exist. Posting needs the
    Page's own key: given a user key instead (Meta's Explorer hands out both), it is swapped here for the Page key, which
    lasts as long as the user key does. Asked once per run."""
    tok, page = os.environ.get("FB_PAGE_TOKEN", "").strip(), os.environ.get("FB_PAGE_ID", "").strip()
    if not (tok and page): return None
    if not _FB:
        _FB.update(token=tok, page=page, swapped=False)
        try:
            r = requests.get(f"{FB_API}/{page}", params={"fields": "access_token", "access_token": tok}, timeout=30).json()
            if r.get("access_token") and r["access_token"] != tok: _FB.update(token=r["access_token"], swapped=True)
        except Exception: pass
    return dict(_FB)

def fb_post(fb, path, cap):
    """Publish a Reel on the Facebook Page (Meta's Reels Publishing API): open an upload session, send the file to
    rupload.facebook.com, then publish it with the caption. Returns the video id."""
    r = requests.post(f"{FB_API}/{fb['page']}/video_reels", data={"upload_phase": "start", "access_token": fb["token"]}, timeout=60).json()
    if "video_id" not in r: raise RuntimeError(f"facebook start: {str(r.get('error', r))[:240]}")
    vid, size = r["video_id"], path.stat().st_size
    up = requests.post(f"https://rupload.facebook.com/video-upload/{FB_API.rsplit('/', 1)[-1]}/{vid}", data=path.read_bytes(), timeout=600,
                       headers={"Authorization": f"OAuth {fb['token']}", "offset": "0", "file_size": str(size),
                                "Content-Type": "application/octet-stream"})
    if not up.ok or not (up.json() if up.content else {}).get("success"):
        raise RuntimeError(f"facebook upload: {up.status_code} {up.text[:240]}")
    last = None
    for phase in ("finish", "complete"):          # Meta's docs show both names for the last phase
        fin = requests.post(f"{FB_API}/{fb['page']}/video_reels", timeout=60, data={
            "upload_phase": phase, "video_id": vid, "video_state": "PUBLISHED", "description": cap[:2200], "access_token": fb["token"]})
        j = fin.json() if fin.content else {}
        if fin.ok and j.get("success"): return vid
        last = f"{fin.status_code} {str(j)[:240]}"
        if "upload_phase" not in last: break
    raise RuntimeError(f"facebook publish: {last}")

def ramp_cap(platform):
    """How many posts this platform may take in 24 hours today: <platform>_per_day to start, rising by
    <platform>_ramp_per_day for each day since its first post, up to <platform>_target. Back to the starting number
    for 3 days after an error that sounds like Meta pushing back (spam, block, restriction, limit). Facebook on a probe
    (fb_probe) stays at the starting number until the probe clears, and then ramps from the day it cleared."""
    start = int(CFG.get(f"{platform}_per_day", 6)); target = int(CFG.get(f"{platform}_target", start))
    step = int(CFG.get(f"{platform}_ramp_per_day", 0)); firsts, trouble = [], False
    for sp in (ROOT / "status").glob("QD-*.json"):
        try: st = json.loads(sp.read_text())
        except Exception: continue
        at = (st.get(platform) or {}).get("at") if isinstance(st.get(platform), dict) else None
        if at: firsts.append(at)
        err = str(st.get(f"{platform}_error") or "")
        try:
            when = dt.datetime.strptime(err[:16], "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
            if NOW() - when < dt.timedelta(hours=72) and re.search(r"spam|block|restrict|limit|temporar", err, re.I): trouble = True
        except ValueError: pass
    since = min(firsts).replace("Z", "+00:00") if firsts else None
    if platform == "facebook" and CFG.get("facebook_probe"):
        probe = fb_probe()
        if not probe.get("cleared"): return start                        # the probe: facebook_per_day until a week shows plays
        since = max(since or probe["cleared"], probe["cleared"])           # then the ramp counts from the day it cleared
    if trouble or not since: return start
    days = (NOW() - dt.datetime.fromisoformat(since)).days
    return min(target, start + step * max(0, days))


def fb_plays_week():
    """Facebook plays of the Reels posted 1 to 8 days ago (analytics/shorts.csv fb_views, by Short id)."""
    import csv
    ids = set()
    for st in _statuses():
        try: at = dt.datetime.fromisoformat(str((st.get("facebook") or {}).get("at") or "").replace("Z", "+00:00"))
        except (ValueError, AttributeError): continue
        if dt.timedelta(days=1) <= NOW() - at <= dt.timedelta(days=8): ids.add(st.get("id"))
    plays = []
    try:
        for r in csv.DictReader((ROOT / "analytics" / "shorts.csv").open()):
            if r.get("short") in ids and str(r.get("fb_views", "")).strip() not in ("", "None"):
                try: plays.append(float(r["fb_views"]))
                except ValueError: pass
    except FileNotFoundError: pass
    return plays


def fb_probe():
    """Facebook on a probe (Charlie's data, 24 October: 54 Reels had 1 play between them and Meta set a spam limit on 23
    October, so posting more only adds to whatever Meta holds against the Page). While config facebook_probe is on, the Page
    takes facebook_per_day Reels a day (1) with a short caption (caption(..., "facebook")). It clears by itself once the
    probe has run a week and the Reels posted 1 to 8 days ago number facebook_probe_min_reels (5) or more with median plays
    of facebook_probe_min_plays (10) or more; the ramp then resumes from that day. The state is status/facebook_probe.json,
    written when it starts, once a day while it runs, and when it clears (a line in analytics/decisions.csv)."""
    import statistics
    p = ROOT / "status" / "facebook_probe.json"
    try: s = json.loads(p.read_text())
    except Exception: s = {}
    if s.get("cleared") or not CFG.get("facebook_probe"): return s
    today, changed = f"{NOW():%Y-%m-%d}", False
    if not s.get("started"): s, changed = {"started": NOW().isoformat(timespec="minutes")}, True
    if s.get("checked") != today:
        plays = fb_plays_week()
        med = statistics.median(plays) if plays else 0
        s.update(checked=today, reels_measured=len(plays), median_plays=med); changed = True
        ran = (NOW() - dt.datetime.fromisoformat(s["started"])).days
        if ran >= 7 and len(plays) >= int(CFG.get("facebook_probe_min_reels", 5)) and med >= float(CFG.get("facebook_probe_min_plays", 10)):
            s["cleared"] = NOW().isoformat(timespec="minutes")
            _decide("Facebook", "Facebook probe cleared: the Page ramps up again from facebook_per_day",
                    f"{len(plays)} Reels from the last week had a median of {med:g} plays", "status/facebook_probe.json")
    if changed:
        p.parent.mkdir(exist_ok=True); p.write_text(json.dumps(s, indent=1))
    return s


def _decide(area, change, why, evidence):
    """One line in analytics/decisions.csv (the record of every change made from the data)."""
    import csv
    p = ROOT / "analytics" / "decisions.csv"; p.parent.mkdir(exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["date", "area", "change", "why", "evidence", "check_on", "by"])
        w.writerow([f"{NOW():%Y-%m-%d}", area, change, why, evidence, f"{NOW() + dt.timedelta(days=7):%Y-%m-%d}", "social.py (automatic)"])

# ---------- what to post ----------
def ig_hashtags(st, board):
    """Instagram's own hashtags for the Short's category (config instagram_hashtags: 3 to 5 family-friendly UK English tags a
    category), or [] for a category with no set. Only well-formed tags (letters, numbers and _ after one #), no repeats."""
    cat = str((board or {}).get("category") or (st or {}).get("category") or "")
    out, seen = [], set()
    for h in (CFG.get("instagram_hashtags") or {}).get(cat) or []:
        h = str(h).strip()
        if re.fullmatch(r"#\w+", h) and h.lower() not in seen:
            seen.add(h.lower()); out.append(h)
    return out[:5]


def caption(st, board, platform="instagram", arm="full"):
    """Title, summary and hashtags, most relevant first: Instagram allows 5 hashtags per Reel; TikTok gets 7 plus #fyp.
    Facebook (24 October: Meta's spam rules of April 2025 name captions stuffed with hashtags, and the Page was limited on
    23 October) gets the title line and at most facebook_hashtags (3) hashtags, no summary and no other platform's name.
    Instagram's "short" arm (the caption test, 24 October): the spoken hook line and the category's own hashtags
    (ig_hashtags, 25 October; the board's first 3 for a category with no set). The "full" arm keeps the board's hashtags."""
    m = (board or {}).get("meta", {})
    tags, seen = [], set()
    for h in m.get("hashtags", []):
        if h.lower() in seen or h.lower() == "#shorts": continue
        seen.add(h.lower()); tags.append(h)
    if platform == "facebook":
        return "\n\n".join(x for x in (st.get("title") or m.get("title", ""), " ".join(tags[:int(CFG.get("facebook_hashtags", 3))])) if x)
    if platform == "instagram" and arm == "short":
        hook = str((((board or {}).get("beats") or [{}])[0] or {}).get("say") or st.get("title") or m.get("title", "")).strip()
        return "\n\n".join(x for x in (hook, " ".join(ig_hashtags(st, board) or tags[:3])) if x)
    tags = tags[:5] if platform == "instagram" else tags[:7] + ["#fyp"]
    yt = CFG.get("crosspost_youtube_line", "") if platform == "instagram" else ""     # YouTube first: point viewers there
    return "\n\n".join(x for x in (st.get("title") or m.get("title", ""), m.get("summary", ""), yt, " ".join(tags)) if x)

_plain_caption = caption
def caption(st, board, platform="instagram", arm="full"):
    """A Short that carries a daily campaign (status "sponsor", pipeline/sponsor.py) is paid promotion wherever it is posted: its
    caption starts with #ad and leads with the campaign's hashtags (inside the platform's cap). Every other caption is as above."""
    try:
        import sponsor
        if sponsor.applied(st): return sponsor.caption(st, _plain_caption(st, sponsor.caption_board(st, board), platform, arm))
    except Exception: pass
    return _plain_caption(st, board, platform, arm)

def board_for(st):
    for d in ("done", "ready", "queue", "hold"):
        p = ROOT / "boards" / d / f"{st['id']}.json"
        if p.exists(): return json.loads(p.read_text())
    return None

def gh(*args, check=True):
    return subprocess.run(["gh", *args, "-R", REPO], capture_output=True, text=True, check=check)

def _age_h(t):
    try: return (NOW() - dt.datetime.fromisoformat(t["saved"])).total_seconds() / 3600
    except Exception: return 1e9

def views_3h():
    """YouTube views at 3 hours per Short id (analytics/shorts.csv: yt_views_3h when the analytics has it, else views_3h)."""
    import csv
    out = {}
    try:
        for r in csv.DictReader((ROOT / "analytics" / "shorts.csv").open()):
            v = r.get("yt_views_3h") if r.get("yt_views_3h") not in (None, "") else r.get("views_3h")
            try: out[r["short"]] = float(v)
            except (TypeError, ValueError, KeyError): pass
    except FileNotFoundError: pass
    return out


def post():
    mode = CFG.get("tiktok_mode", "inbox")                       # "off" since 19 Oct 2026: TikTok blocked every post as spam
    safety = tt_safety()
    if safety and mode != "off": print("tiktok: stopped since", safety.get("stopped"), "|", safety.get("why")); mode = "off"
    ig, tt = ig_tokens(), ({} if mode == "off" else load("tiktok"))
    if ig and _age_h(ig) > 24 * 7: print(ig_refresh(ig))            # long-lived Instagram token: refresh weekly
    if tt.get("refresh_token") and _age_h(tt) > 20: print(tt_refresh(tt))   # TikTok access tokens last 24 hours
    tt_max_age = float(CFG.get("tiktok_max_age_hours", 24))   # trends go stale: skip TikTok for Shorts public longer than this
    tt_blocked = False                                           # TikTok said "too many drafts waiting": try again next hour
    if tt.get("access_token"):                                   # uploads TikTok had not confirmed yet: ask again
        for sp in (ROOT / "status").glob("QD-*.json"):
            try: s0 = json.loads(sp.read_text())
            except Exception: continue
            if not s0.get("tiktok_pending"): continue
            try:
                if tt_settle(tt, s0): sp.write_text(json.dumps(s0, indent=1, ensure_ascii=False))
            except TikTokStop as e: tt_stop(e); tt_blocked = True; break
            except Exception as e: print(s0.get("id"), "tiktok status:", str(e)[:120])
    tt_room = (tt_cap(mode) - tt_sent_24h()) if tt.get("access_token") else 0
    fb = fb_tokens()
    done_any, ig_recent, fb_recent, fb_last = False, 0, 0, None
    for sp in (ROOT / "status").glob("QD-*.json"):
        try: s0 = json.loads(sp.read_text())
        except Exception: continue
        for key in ("instagram", "facebook"):
            try: at = dt.datetime.fromisoformat(((s0.get(key) or {}).get("at") or "").replace("Z", "+00:00"))
            except Exception: continue
            if key == "facebook": fb_last = max(fb_last or at, at)
            if NOW() - at <= dt.timedelta(hours=24):
                if key == "instagram": ig_recent += 1
                else: fb_recent += 1
    ig_cap, fb_cap = ramp_cap("instagram"), ramp_cap("facebook")
    fresh_h = float(CFG.get("crosspost_max_age_hours", 48))     # Instagram and Facebook never get a backlog of old Shorts
    # Facebook takes one Reel a run at most, at least facebook_min_gap_minutes after the last, newest Short first: a burst of
    # posts from a new Page is what Meta's spam checks look for, and the newest Short is the most timely
    fb_gap = dt.timedelta(minutes=float(CFG.get("facebook_min_gap_minutes", 30)))
    fb_pick = None
    if fb and fb_recent < fb_cap and (fb_last is None or NOW() - fb_last >= fb_gap):
        cands = []
        for sp in (ROOT / "status").glob("QD-*.json"):
            try: s1 = json.loads(sp.read_text())
            except Exception: continue
            if not (s1.get("video") and s1.get("social_release") and s1.get("publish_at")) or s1.get("facebook") or s1.get("facebook_skipped"): continue
            pa = dt.datetime.fromisoformat(s1["publish_at"].replace("Z", "+00:00"))
            if pa <= NOW() and (NOW() - pa).total_seconds() / 3600 <= fresh_h: cands.append((pa, s1.get("id")))
        fb_pick = max(cands)[1] if cands else None
    # Instagram by YouTube views at 3 hours (config instagram_pick_by "views_3h"): a Short waits until it has been public for
    # instagram_pick_wait_hours, and the day's room goes to the most watched first. Off by default ("order": the day's
    # picks first, then by publish time): on 24 October our 96 Shorts with both numbers showed views at 3 hours do not
    # predict Instagram views (rank correlation 0.10; the top half by 3-hour views had a median of 71 Instagram views,
    # the bottom half 90), so it waits for data that says otherwise.
    v3 = views_3h() if ig and CFG.get("instagram_pick_by", "category") == "views_3h" else {}
    ig_allowed, ig_plan = None, {}
    if ig and CFG.get("instagram_pick_by", "category") == "category":     # 24 October: Instagram picks its own (ig_choose)
        ig_plan = ig_choose(_statuses(), ig_cap)
        ig_allowed = set(ig_plan)
    if v3:
        wait_h, elig = float(CFG.get("instagram_pick_wait_hours", 3)), []
        for s1 in _statuses():
            if not (s1.get("video") and s1.get("social_release") and s1.get("publish_at")) or s1.get("instagram") or s1.get("instagram_skipped"): continue
            age = (NOW() - dt.datetime.fromisoformat(s1["publish_at"].replace("Z", "+00:00"))).total_seconds() / 3600
            if wait_h <= age <= fresh_h: elig.append((s1["id"] not in v3, -v3.get(s1["id"], 0.0), s1["publish_at"], s1["id"]))
        ig_allowed = {x[-1] for x in sorted(elig)[:max(0, ig_cap - ig_recent)]}
    def order(sp):          # the day's picks first, then the rest by publish time
        try: st0 = json.loads(sp.read_text())
        except Exception: return (2, "")
        return (0 if (board_for(st0) or {}).get("tiktok") else 1, st0.get("publish_at") or "") if st0.get("id") else (2, "")
    for sp in sorted((ROOT / "status").glob("QD-*.json"), key=order):
        st = json.loads(sp.read_text())
        if not st.get("video") or not st.get("social_release") or not st.get("publish_at"): continue
        public_at = dt.datetime.fromisoformat(st["publish_at"].replace("Z", "+00:00"))
        public = public_at <= NOW()
        # TikTok drafts go out as soon as the Short is scheduled (config tiktok_when "uploaded"), so Charlie can post them
        # in one go with the captions from the morning message; or when it goes public on YouTube ("public").
        tt_now = public or CFG.get("tiktok_when", "uploaded") == "uploaded"
        if not (public or tt_now): continue
        since = public_at if CFG.get("tiktok_when", "uploaded") == "public" else \
            dt.datetime.fromisoformat((st.get("uploaded_at") or st["publish_at"]).replace("Z", "+00:00"))
        fresh = (NOW() - since).total_seconds() / 3600 <= tt_max_age
        b = board_for(st)
        picked = (b or {}).get("tiktok", True)       # the writer marks the 5 Shorts a day most likely to do well on TikTok
        # Instagram takes the day's picks only (config instagram_mode "picks"), at most instagram_per_day Reels in 24 hours:
        # 20 Reels a day from one account reads as spam to Meta
        ig_pick = picked if CFG.get("instagram_mode", "picks") == "picks" else True
        recent_public = public and (NOW() - public_at).total_seconds() / 3600 <= fresh_h
        if ig and public and not st.get("instagram") and not ig_pick and not st.get("instagram_skipped"):
            st["instagram_skipped"] = "not one of the day's picks"
        if ig and public and not recent_public and not st.get("instagram") and not st.get("instagram_skipped"):
            st["instagram_skipped"] = f"public over {fresh_h:g} hours before Instagram had room"
        want_ig = bool(ig) and recent_public and not st.get("instagram") and ig_pick and ig_recent < ig_cap and not st.get("instagram_skipped") \
            and (ig_allowed is None or st.get("id") in ig_allowed)
        if fb and public and not recent_public and not st.get("facebook") and not st.get("facebook_skipped"):
            st["facebook_skipped"] = f"public over {fresh_h:g} hours before Facebook had room"
        want_fb = bool(fb) and recent_public and not st.get("facebook") and fb_recent < fb_cap and not st.get("facebook_skipped") \
            and st.get("id") == fb_pick
        manual = mode == "manual"                    # Charlie uploads TikTok himself on desktop from the morning package
        want_tt = bool(tt) and not manual and tt_now and picked and not st.get("tiktok") and not st.get("tiktok_pending") \
            and not tt_blocked and tt_room > 0 and fresh and not st.get("tiktok_skipped")
        if not (want_ig or want_tt or want_fb):
            if st.get("instagram_skipped") or st.get("facebook_skipped"): sp.write_text(json.dumps(st, indent=1, ensure_ascii=False))
            continue
        rel = st["social_release"]; work = ROOT / "social_tmp"; work.mkdir(exist_ok=True)
        if gh("release", "download", rel, "-p", "social.mp4", "-D", str(work), "--clobber", check=False).returncode:
            st["social_error"] = "release missing"; sp.write_text(json.dumps(st, indent=1, ensure_ascii=False)); continue
        mp4 = work / "social.mp4"
        if want_tt:
            try:
                cap = caption(st, b, "tiktok")
                pend = {"publish_id": tt_post(tt, mp4, cap, mode, seconds=(st.get("qa") or {}).get("duration")), "mode": mode,
                        "at": NOW().isoformat(timespec="seconds")}
                if mode == "inbox": pend["caption"] = cap     # drafts can't carry a caption: Charlie pastes this one
                tt_room -= 1; st["tiktok_pending"] = pend; st.pop("tiktok_error", None)
                tt_settle(tt, st)                            # posted only once TikTok confirms it landed (else asked next run)
            except TikTokStop as e:
                st["tiktok_error"] = f"{NOW():%Y-%m-%d %H:%M} {e}"[:300]; tt_stop(e); tt_blocked = True
            except Exception as e:
                st["tiktok_error"] = f"{NOW():%Y-%m-%d %H:%M} {e}"[:300]
                if any(c in str(e) for c in TT_WAIT_CODES): tt_blocked = True
        if want_ig:
            try:
                gh("release", "edit", rel, "--draft=false")
                url = f"https://github.com/{REPO}/releases/download/{rel}/social.mp4"
                arm = ig_arm(st["id"], "ig-caption", ig_share("ig_caption", "short", "full", float(CFG.get("instagram_caption_share", 0.5))),
                             "short", "full") if CFG.get("instagram_caption_test", True) else "full"
                trial = bool(CFG.get("instagram_trial", True)) and ig_trial_ok() and ig_arm(
                    st["id"], "ig-trial", ig_share("ig_trial", "yes", "no", float(CFG.get("instagram_trial_share", 0.5))), True, False)
                thumb = ig_hook_ms(st) if CFG.get("instagram_thumb_at_hook", True) and ig_cover_ok() else None
                mid, used = ig_publish(ig, url, caption(st, b, "instagram", arm), trial, thumb)
                how = ig_plan.get(st["id"]) or {"pick": CFG.get("instagram_pick_by", "category"), "hour": "any"}
                from zoneinfo import ZoneInfo
                st["instagram"] = {"media": mid, "at": NOW().isoformat(timespec="seconds"), "caption": arm, "trial": used["trial"],
                                   "thumb_ms": used["thumb_ms"], "thumb": used["thumb"], "pick": how["pick"], "hour": how["hour"],
                                   "favoured": bool(how.get("favoured")), "hour_uk": NOW().astimezone(ZoneInfo("Europe/London")).hour}
                st.pop("instagram_error", None)
            except Exception as e: st["instagram_error"] = f"{NOW():%Y-%m-%d %H:%M} {e}"[:300]
        if want_fb:
            try:
                st["facebook"] = {"video": fb_post(fb, mp4, caption(st, b, "facebook")), "at": NOW().isoformat(timespec="seconds")}
                st.pop("facebook_error", None); fb_recent += 1
            except Exception as e: st["facebook_error"] = f"{NOW():%Y-%m-%d %H:%M} {e}"[:300]
        done_tt = st.get("tiktok") or st.get("tiktok_pending")
        if tt and not fresh and not done_tt: st["tiktok_skipped"] = f"over {tt_max_age:g} hours old before TikTok could take it"
        if tt and not picked and not done_tt: st["tiktok_skipped"] = "not one of the day's 5 TikTok picks"
        if tt and manual and not done_tt: st["tiktok_skipped"] = "uploaded by hand on desktop" if picked else "not a TikTok pick"
        if st.get("instagram") and want_ig: ig_recent += 1
        if (done_tt or st.get("tiktok_skipped") or not tt) and (st.get("instagram") or st.get("instagram_skipped") or not ig) \
                and (st.get("facebook") or st.get("facebook_skipped") or not fb):
            gh("release", "delete", rel, "--cleanup-tag", "-y", check=False); st.pop("social_release", None)
        else:
            gh("release", "edit", rel, "--draft=true", check=False)
        mp4.unlink(missing_ok=True)
        sp.write_text(json.dumps(st, indent=1, ensure_ascii=False)); done_any = True
        print(st["id"], "tiktok:", bool(st.get("tiktok")), "instagram:", bool(st.get("instagram")), "facebook:", bool(st.get("facebook")))
    if not done_any: print("nothing to post")

def check():
    """Confirm the sign-ins work without posting anything; writes status/social.json (no tokens in it)."""
    out = {"checked": NOW().isoformat(timespec="seconds")}
    ig = ig_tokens()
    sj0 = ROOT / "status" / "social.json"
    prev = json.loads(sj0.read_text()) if sj0.exists() else {}
    try: prev_age = (NOW() - dt.datetime.fromisoformat(prev["instagram_checked"])).total_seconds() / 3600
    except Exception: prev_age = 1e9
    if not ig:
        out["instagram"] = {"ok": False, "error": "not connected (IG_TOKEN secret missing)"}
    elif os.environ.get("GITHUB_EVENT_NAME") == "schedule" and prev_age < 3 and prev.get("instagram"):
        out["instagram"] = prev["instagram"]; out["instagram_checked"] = prev["instagram_checked"]   # gentle on Meta: every 3 hours
    else:
        out["instagram_checked"] = NOW().isoformat(timespec="seconds")
        r = requests.get(f"{IG_API}/me", params={"fields": "user_id,username,account_type", "access_token": ig["token"]}, timeout=30)
        if r.ok:
            me = r.json()
            out["instagram"] = {"ok": True, "username": me.get("username"), "account_type": me.get("account_type"),
                                "user_id": me.get("user_id"), "secret_user_id_matches": str(me.get("user_id")) == str(ig.get("user"))}
            if me.get("user_id") and not ig.get("user"):
                ig["user"] = str(me["user_id"]); save("instagram", ig)
            q = requests.get(f"{IG_API}/{ig.get('user') or me.get('user_id')}/content_publishing_limit",
                             params={"fields": "config,quota_usage", "access_token": ig["token"]}, timeout=30)
            out["instagram"]["publishing_limit"] = q.json().get("data") if q.ok else f"{q.status_code} {q.text[:200]}"
        else:
            out["instagram"] = {"ok": False, "error": f"{r.status_code} {r.text[:300]}"}
    fb = fb_tokens()
    if not fb:
        out["facebook"] = {"ok": False, "error": "not connected (FB_PAGE_TOKEN and FB_PAGE_ID secrets missing)"}
    else:
        r = requests.get(f"{FB_API}/{fb['page']}", params={"fields": "name,followers_count,fan_count", "access_token": fb["token"]}, timeout=30)
        out["facebook"] = ({"ok": True, "page": r.json().get("name"), "followers": r.json().get("followers_count", r.json().get("fan_count")),
                            "today_cap": ramp_cap("facebook")} if r.ok else {"ok": False, "error": f"{r.status_code} {r.text[:300]}"})
        if r.ok:            # what the key is (a Page key that never expires) and what it may do; never the key itself
            try:
                d = requests.get(f"{FB_API}/debug_token", params={"input_token": fb["token"], "access_token": fb["token"]}, timeout=30).json()
                d = d.get("data") or {}
                if d: out["facebook"].update(key_type=d.get("type"), key_from_user_key=fb.get("swapped"),
                                             key_expires="never" if d.get("expires_at") == 0 else d.get("expires_at"),
                                             key_valid=d.get("is_valid"), scopes=sorted(d.get("scopes") or []),
                                             data_access_expires=d.get("data_access_expires_at"))
            except Exception: pass
    if ig:
        out.setdefault("instagram", {})["today_cap"] = ramp_cap("instagram")
        out["instagram"]["cover"] = ig_cover_check()          # did Instagram accept the cover frame at the hook (25 October)
    tt = load("tiktok")
    if CFG.get("tiktok_mode") == "off":
        out["tiktok"] = {"ok": True, "mode": "off"}
    elif not tt.get("refresh_token"):
        ck = os.environ.get("TIKTOK_CLIENT_KEY", "")
        out["tiktok"] = {"ok": False, "error": "not connected yet" if ck else "not connected (TIKTOK_CLIENT_KEY secret missing)"}
        if ck:   # the client key is public by design (it is part of every sign-in link)
            # only what is used (24 October): who the account is, its numbers, our posts' numbers, and drafts to the inbox
            q = {"client_key": ck, "scope": TT_SCOPES, "response_type": "code",
                 "redirect_uri": TT_REDIRECT, "state": hashlib.sha1(ck.encode()).hexdigest()[:12]}
            out["tiktok"]["connect_url"] = "https://www.tiktok.com/v2/auth/authorize/?" + requests.compat.urlencode(q)
    else:
        h = {"Authorization": f"Bearer {tt['access_token']}"}
        fields = "open_id,display_name" + (",username" if "user.info.profile" in str(tt.get("scope") or "") else "")
        r = requests.get(f"{TT_API}/user/info/", params={"fields": fields}, headers=h, timeout=30)
        j = r.json() if r.content else {}
        out["tiktok"] = {"ok": r.ok and j.get("error", {}).get("code") in (None, "ok"), "user": (j.get("data") or {}).get("user"),
                         "scopes": tt.get("scope"), "mode": CFG.get("tiktok_mode", "inbox")}
    (ROOT / "status").mkdir(exist_ok=True)
    sj = ROOT / "status" / "social.json"
    old = json.loads(sj.read_text()) if sj.exists() else {}
    stable = lambda d: json.dumps({k: v for k, v in d.items() if k not in ("checked", "instagram_dry_run", "instagram_checked")}, sort_keys=True, default=str)
    age = (NOW() - dt.datetime.fromisoformat(old["checked"])).total_seconds() / 3600 if old.get("checked") else 1e9
    # hourly runs only rewrite the file when something changed (or once a day), so the repo doesn't fill with check commits
    if stable(old) != stable(out) or age > 24 or os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        if old.get("instagram_dry_run"): out["instagram_dry_run"] = old["instagram_dry_run"]
        sj.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(out, indent=1))

def ig_dry_run():
    """Proves Instagram can fetch and process a video from a GitHub release, without posting anything:
    a 5-second blank test clip goes up as a release, Instagram builds a Reel container from it, the container is never
    published (Instagram discards it after 24 hours) and the release is deleted straight away."""
    ig = ig_tokens(); res = {"at": NOW().isoformat(timespec="seconds")}
    work = ROOT / "social_tmp"; work.mkdir(exist_ok=True); mp4 = work / "social.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x1d1d1f:s=1080x1920:r=30:d=5",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    tag = f"ig-test-{NOW():%Y%m%d%H%M%S}"
    r = gh("release", "create", tag, str(mp4), "--title", tag, "--notes", "Instagram test file, deleted straight after.", check=False)
    if r.returncode: res["error"] = f"release: {r.stderr.strip()[:200]}"
    else:
        try:
            url = f"https://github.com/{REPO}/releases/download/{tag}/social.mp4"
            user = ig.get("user") or os.environ.get("IG_USER_ID")
            c = requests.post(f"{IG_API}/{user}/media", data={"media_type": "REELS", "video_url": url, "caption": "test",
                                                                "access_token": ig["token"]}, timeout=60)
            if not c.ok: res["error"] = f"container: {c.status_code} {c.text[:300]}"
            else:
                cid = c.json()["id"]; res["container"] = "created"
                for _ in range(36):
                    st = requests.get(f"{IG_API}/{cid}", params={"fields": "status_code,status", "access_token": ig["token"]}, timeout=30).json()
                    res["status_code"], res["status"] = st.get("status_code"), st.get("status")
                    if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"): break
                    time.sleep(5)
                res["ok"] = res.get("status_code") == "FINISHED"
                res["note"] = "never published; Instagram discards unpublished containers after 24 hours"
        finally:
            gh("release", "delete", tag, "--cleanup-tag", "-y", check=False)
    mp4.unlink(missing_ok=True)
    sj = ROOT / "status" / "social.json"
    out = json.loads(sj.read_text()) if sj.exists() else {}
    out["instagram_dry_run"] = res
    sj.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps(res))

def tt_test():
    """Sends one test Short to the TikTok inbox as a draft, only when Charlie has asked for it (requests/social-check.txt
    says "tiktok-test <id>"). The Short comes from that id's private preview release, which is deleted afterwards."""
    sid = os.environ.get("TT_TEST_ID", "").strip(); tt = load("tiktok")
    out = {"at": NOW().isoformat(timespec="seconds"), "id": sid}
    work = ROOT / "social_tmp"; work.mkdir(exist_ok=True); rel = f"preview-{sid}"
    if not tt.get("access_token"): out["error"] = "TikTok not connected"
    elif gh("release", "download", rel, "-p", "social.mp4", "-D", str(work), "--clobber", check=False).returncode:
        out["error"] = f"no preview release {rel}"
    else:
        try:
            pid = tt_post(tt, work / "social.mp4", "test", "inbox"); out.update(ok=True, publish_id_set=bool(pid))
            h = {"Authorization": f"Bearer {tt['access_token']}", "Content-Type": "application/json; charset=UTF-8"}
            for _ in range(12):
                time.sleep(10)
                r = requests.post(f"{TT_API}/post/publish/status/fetch/", headers=h, json={"publish_id": pid}, timeout=30).json()
                out["status"] = (r.get("data") or {}).get("status"); out["fail_reason"] = (r.get("data") or {}).get("fail_reason")
                if out["status"] and out["status"] not in ("PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD"): break
        except Exception as e:
            out.update(ok=False, error=str(e)[:300])
        gh("release", "delete", rel, "-y", check=False)
    (work / "social.mp4").unlink(missing_ok=True)
    (ROOT / "status" / "tiktok_test.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out))

def refresh():
    ig, tt = ig_tokens(), load("tiktok")
    if ig: print(ig_refresh(ig))
    if tt.get("refresh_token"): print(tt_refresh(tt))

def ig_state_cmd():
    print(json.dumps(ig_report(), indent=1, ensure_ascii=False))

if __name__ == "__main__":
    {"post": post, "tiktok-connect": tt_connect, "refresh": refresh, "check": check, "ig-dry-run": ig_dry_run, "tiktok-test": tt_test,
     "tiktok-stats": tt_stats, "ig-state": ig_state_cmd}[sys.argv[1]]()
