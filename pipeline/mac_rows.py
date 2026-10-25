"""The Mac's evening Chrome run, in one small answer (24 October: the run used to read an 18 KB card and the whole
clips/submit.csv, and a late pass failed on Charlie's usage limit). Standard library only, so it runs on the Mac as it is.

  python3 pipeline/mac_rows.py                  what to do now: the Vyro rows to submit (newest first, the places left
                                                today per account), Content Rewards rows to rescue, today's community poll
                                                (pipeline/community.py), occasional jobs due, open one-off jobs;
                                                "NOTHING TO DO" when there is nothing (stop, no commit)
  python3 pipeline/mac_rows.py top              the 10 most viewed Shorts of the last 7 days (Monday's related-video job)
  python3 pipeline/mac_rows.py done CLIP [youtube|instagram] VALUE
                                                writes VALUE ("now", "now (already)" or "failed: why") into that row's
                                                submitted column, so the Mac never opens clips/submit.csv

Rules kept from docs/CHROME_JOBS.md: Vyro takes links only from the Mac (it drops sessions from GitHub); 5 posts a day
per connected account; a row is open while its submitted column is empty or "failed" (GitHub writes "expired: ..." into
rows over 30 hours old without the views to justify it, so those never show here); rows over 3 days old never do.
"""
import csv, datetime as dt, json, os, pathlib, re, sys, urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
SUBMIT = ROOT / "clips" / "submit.csv"
HANDLES = {"clips": "Quickplay Clips (@quickplayclips-x9b)", "gaming": "Quickplay Gaming Clips", "irl": "Quickplay IRL Clips",
           "daily": "Quickplay Daily (@quickplaydaily)"}
ISSUES = "https://api.github.com/repos/quickplay-studio/quickplay-autopilot/issues?state=open&per_page=50"
FOR_THE_MAC = re.compile(r"Security: a sign-in outside|login has expired", re.I)


def now_uk():
    return dt.datetime.now(UK)


def load_json(p, default):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return default


def rows():
    try: return list(csv.DictReader(SUBMIT.open()))
    except FileNotFoundError: return []


def is_open(r):
    s = str(r.get("submitted") or "")
    return (not s or s.startswith("failed")) and not s.startswith("failed: past the")


def public_at(r):
    try: return dt.datetime.strptime(str(r.get("public_at_uk") or ""), "%Y-%m-%d %H:%M").replace(tzinfo=UK)
    except ValueError: return None


def on_vyro(c):
    return "vyro" in str((c or {}).get("platform", "")).lower()


def vyro_due(rs, camps, now, limit):
    """Vyro YouTube rows to submit now: public already, under 3 days old, open; newest first, at most the places each
    account has left today (5 a day, minus what it already submitted today)."""
    today = f"{now:%Y-%m-%d}"
    used = {}
    for r in rs:
        if on_vyro(camps.get(r.get("campaign"))) and str(r.get("submitted") or "").startswith(today):
            used[r.get("channel") or "clips"] = used.get(r.get("channel") or "clips", 0) + 1
    cand = []
    for r in rs:
        t = public_at(r)
        if not (on_vyro(camps.get(r.get("campaign"))) and (r.get("platform") or "youtube") == "youtube" and is_open(r)): continue
        if not str(r.get("video") or "").startswith("http") or t is None or t > now or now - t > dt.timedelta(days=3): continue
        cand.append((t, r))
    cand.sort(key=lambda x: x[0], reverse=True)
    left = {}
    out = []
    for t, r in cand:
        ch = r.get("channel") or "clips"
        left.setdefault(ch, max(0, limit - used.get(ch, 0)))
        if left[ch] <= 0: continue
        left[ch] -= 1; out.append(r)
    return out, {ch: max(0, limit - used.get(ch, 0)) for ch in sorted({r.get("channel") or "clips" for _, r in cand} | set(used))}


def cr_rescue(rs, camps, now):
    """Content Rewards rows GitHub could not submit for a sign-in problem, still inside the site's 30 minutes."""
    out = []
    for r in rs:
        s, t = str(r.get("submitted") or ""), public_at(r)
        if on_vyro(camps.get(r.get("campaign"))) or t is None: continue
        if re.match(r"failed: (login expired|no saved sign-in)", s) and dt.timedelta(0) <= now - t <= dt.timedelta(minutes=30):
            out.append(r)
    return out


def daily_candidates(camps_cfg, now):
    """New sound or hashtag campaigns the scout found for Quickplay Daily's own Shorts (clips/scout.json "daily", pipeline/sponsor.py),
    while fewer than daily_min_active (2) are live and the Mac has not joined them already (any entry of campaigns.json, ended or not)."""
    camps = camps_cfg.get("campaigns") or {}
    live = [k for k, c in camps.items() if c.get("daily") and c.get("active") and str(c.get("ends") or "9999") >= f"{now:%Y-%m-%d}"]
    if len(live) >= int(camps_cfg.get("daily_min_active") or 2): return live, []
    last = lambda u: str(u or "").rstrip("/").rsplit("/", 1)[-1].lower()
    known = set()
    for c in camps.values():
        known |= {str(c.get(k) or "").lower() for k in ("card", "name")} | {last(c.get("url"))}
    out = []
    for d in load_json(ROOT / "clips" / "scout.json", {}).get("daily") or []:
        ids = {str(d.get(k) or "").lower() for k in ("card", "name", "id")} | {last(d.get("url"))}
        if not (ids - {""}) & known: out.append(d)
    return live, out


def occasional(now, camps_cfg):
    """Occasional jobs due today (steps in docs/CHROME_OCCASIONAL.md)."""
    jobs = []
    camps = camps_cfg.get("campaigns") or {}
    soon = (now + dt.timedelta(days=3)).date().isoformat()
    live = [k for k, c in camps.items() if c.get("active") and (c.get("source") or {}) and str(c.get("ends") or "9999") > soon]
    need = int(camps_cfg.get("min_active") or 6)
    if len(live) < need: jobs.append(f"Capacity: {len(live)} of {need} campaigns are live: join more")
    daily_live, daily_new = daily_candidates(camps_cfg, now)
    if daily_new:
        jobs.append(f"Daily sound campaigns: {len(daily_live)} live; join one more from status/scout.md (\"For Quickplay Daily's own views\"): "
                    + ", ".join(f"{str(d.get('name'))[:40]} (${d.get('rate_per_1k') or '?'}/1k, {d.get('platform')})" for d in daily_new[:3]))
    twice_weekly = now.weekday() in (0, 3)            # Monday and Thursday: the searches that cost the most browsing
    if now.weekday() == 0: jobs.append("Related video: link the week's 10 best Shorts to the newest weekly long video")
    if twice_weekly:
        w = [i["name"] for i in (load_json(ROOT / "status" / "watch.json", {}).get("items") or [])
             if i.get("level") in ("surging", "launch")]
        if w: jobs.append("Watchlist campaigns: search Vyro and Content Rewards for " + ", ".join(w[:6]))
        try:
            md = (ROOT / "status" / "streamers.md").read_text()
            names = re.findall(r"^- (.+?) \(heat", md.split("Programmes to join next", 1)[1], re.M) if "Programmes to join next" in md else []
            if names: jobs.append("Streamer programmes: find and join " + ", ".join(names[:4]))
        except FileNotFoundError: pass
    try:
        log = (ROOT / "status" / "clips_log.txt").read_text()[-20000:]
        bad = sorted(set(re.findall(r"^([a-z0-9-]+): .*(?:no footage|download failed|frameio|gdrive)", log, re.M | re.I)))
        if bad: jobs.append("Footage: re-read the footage link for " + ", ".join(bad[:5]))
    except FileNotFoundError: pass
    return jobs


def one_offs():
    try: text = (ROOT / "docs" / "CHROME_LOG.md").read_text()
    except FileNotFoundError: return []
    return re.findall(r"^### open: (.+)$", text, re.M)


def community_lines(now):
    """Today's community poll (pipeline/community.py) while it is made and not yet posted: the lines the Mac posts."""
    try:
        import community
        return community.due(now, ROOT)
    except Exception: return []


def issues_for_the_mac():
    """Open GitHub issues the Mac acts on (security, expired site logins). None when GitHub can't be read."""
    try:
        with urllib.request.urlopen(urllib.request.Request(ISSUES, headers={"User-Agent": "quickplay-mac"}), timeout=15) as r:
            return [i["title"] for i in json.loads(r.read()) if not i.get("pull_request") and FOR_THE_MAC.search(i.get("title", ""))]
    except Exception: return None


def show(now=None, fetch_issues=True):
    now = now or now_uk()
    cfg = load_json(ROOT / "clips" / "campaigns.json", {})
    camps = cfg.get("campaigns") or {}
    limit = int((cfg.get("submit_daily_limits") or {}).get("Vyro") or 5)
    rs = rows()
    due, left = vyro_due(rs, camps, now, limit)
    rescue = cr_rescue(rs, camps, now)
    jobs, offs = occasional(now, cfg), one_offs()
    comm = community_lines(now)
    iss = issues_for_the_mac() if fetch_issues else []
    out = [f"Mac run {now:%A %d %B %H:%M} UK"]
    if iss is None: out.append("Issues: GitHub could not be read; open https://github.com/quickplay-studio/quickplay-autopilot/issues")
    elif iss: out += ["Issues to act on first:"] + [f"- {t}" for t in iss]
    if due:
        out.append(f"Vyro: {len(due)} to submit now (places left today: " + ", ".join(f"{k} {v}" for k, v in left.items()) + ")")
        for n, r in enumerate(due, 1):
            card = (camps.get(r.get("campaign")) or {}).get("card") or r.get("campaign")
            out.append(f"{n}. {r['clip']} | {HANDLES.get(r.get('channel') or 'clips', r.get('channel'))} | card: {card} | {r['video']}")
    if rescue:
        out.append(f"Content Rewards rescue ({len(rescue)}; their 30 minutes run out at the times shown):")
        for r in rescue:
            t = public_at(r) + dt.timedelta(minutes=30)
            out.append(f"- {r['clip']} | {r.get('campaign_url')} | {r['video']} | by {t:%H:%M}")
    if comm: out += ["Community poll for Quickplay Daily (card step 6; then `python3 pipeline/community.py posted`):"] + comm
    if jobs: out += ["Occasional jobs (steps: docs/CHROME_OCCASIONAL.md):"] + [f"- {j}" for j in jobs]
    if offs: out += ["One-off jobs open (docs/CHROME_LOG.md):"] + [f"- {o}" for o in offs]
    if not (due or rescue or jobs or offs or iss or comm):
        out.append("NOTHING TO DO: stop here (no commit).")
    return "\n".join(out)


def top(now=None, n=10):
    """The week's best Shorts for the Monday related-video job: the n most viewed of the last 7 days (analytics/shorts.csv)."""
    now = now or now_uk()
    cut = (now - dt.timedelta(days=7)).date().isoformat()
    try: rs = [r for r in csv.DictReader((ROOT / "analytics" / "shorts.csv").open()) if str(r.get("posted_day") or "") >= cut]
    except FileNotFoundError: return "analytics/shorts.csv is missing"
    def views(r):
        try: return float(r.get("yt_views") or 0)
        except ValueError: return 0.0
    rs.sort(key=views, reverse=True)
    return "\n".join(f"{views(r):.0f} | {r.get('short')} | {r.get('youtube_url')} | {r.get('title')}" for r in rs[:n]) or "no Shorts in the last 7 days"


def mark(clip, platform, value, now=None):
    """Writes value into the submitted column of the open row(s) of `clip` on `platform`. Returns how many changed."""
    now = now or now_uk()
    if value.startswith("now"): value = f"{now:%Y-%m-%d %H:%M}" + value[3:]
    with SUBMIT.open() as f:
        rd = csv.DictReader(f); fields = rd.fieldnames; rs = list(rd)
    n = 0
    for r in rs:
        if r.get("clip") == clip and (r.get("platform") or "youtube") == platform and is_open(r):
            r["submitted"] = value; n += 1
    if n:
        with SUBMIT.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rs)
    return n


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "top": print(top())
    elif a and a[0] == "done":
        if len(a) < 3: sys.exit("usage: mac_rows.py done CLIP [youtube|instagram] VALUE")
        clip, plat, value = (a[1], a[2], " ".join(a[3:])) if len(a) >= 4 and a[2] in ("youtube", "instagram", "facebook") else (a[1], "youtube", " ".join(a[2:]))
        print(f"marked {mark(clip, plat, value)} row(s)")
    else:
        print(show())
