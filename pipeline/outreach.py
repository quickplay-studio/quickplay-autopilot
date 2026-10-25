"""The creator scout (Charlie, 25 October 2026): small creators who say, in their own words, that clips of their videos are allowed.

YouTube buried re-uploaded clips on 1 October 2026 (issue #37), and footage is only ours to clip with the creator's permission, so
this finds creators to ask. Once a week (the clips.yml scout run, 08:35 UTC) it makes at most 3 YouTube searches (search.list, 100
units each, and only when quota.allow says the day's uploads keep their share): each is a niche (gaming, IRL streamers, music,
football) with one phrase, the three combinations used longest ago. It then reads the full descriptions of the videos found
(videos.list) and the channels (channels.list: subscribers and the About text; 1 unit a call) and adds every channel under 50,000
subscribers whose channel description or recent video descriptions say "clips allowed", "clip this", "clipping permitted", "clip
and post", "use my clips" or "clippers welcome" (not "no clips allowed") to clips/outreach.csv:

  channel, url, subscribers, niche, evidence, found_on, status

evidence is the creator's own sentence and where it was said; found_on is the UK day it was found; status starts as "new" and is
Charlie's to change (new, asked, yes, no, skip); a channel already listed keeps its status and its row. Nothing is sent, ever:
Charlie reads the table on the hub's Clips tab, sends the message in docs/OUTREACH.md by hand if he wants to, and a "yes" is written
down before anything is clipped. A channel about gambling, crypto, adult content or politics is left out (the channel rules).

usage: python pipeline/outreach.py [--force]     (--force ignores the week; it never exits with an error, so the scout run is never held up)
"""
import csv, datetime as dt, json, pathlib, re, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
OUT = ROOT / "clips" / "outreach.csv"
STATE = ROOT / "clips" / "state" / "outreach.json"
FIELDS = ["channel", "url", "subscribers", "niche", "evidence", "found_on", "status"]
PHRASES = ["clips allowed", "clip this", "clipping permitted", "clip and post", "use my clips", "clippers welcome"]
NICHES = {"gaming": "gaming", "irl": "IRL stream", "music": "music", "football": "football"}      # niche: what goes into the search
CHANNEL_URL = "https://www.youtube.com/channel/"
VIDEO_URL = "https://www.youtube.com/watch?v="

PHRASE_RE = re.compile(r"\b(" + "|".join(r"\s+".join(re.escape(w) for w in p.split()) for p in PHRASES) + r")\b", re.I)
APOS = "['’]"
NEGATION = re.compile(r"\b(no|not|never|nobody|none|without|cannot|dont|\w+n" + APOS + r"t)\b", re.I)      # no, not, never, don't, can't, isn't ...
NEGATED_AFTER = re.compile(r"\s*(is |are |was |were )?(not|never)\b", re.I)
AVOID = re.compile(r"\b(casino\w*|gambl\w*|betting|sportsbook|poker|crypto\w*|forex|nsfw|18\+|adult|onlyfans|porn\w*|politic\w*|election\w*|"
                   r"trump|biden|brexit)\b", re.I)            # the channel rules: no politics, money or investing, adult content or gambling
DASHES = re.compile(r"\s*[" + chr(0x2013) + chr(0x2014) + r"]\s*")      # no em or en dashes anywhere (the channel rules), even in a quotation


def log(*a): print("outreach:", *a, flush=True)


def cfg():
    try: return json.loads((ROOT / "clips" / "campaigns.json").read_text())
    except Exception: return {}


def setting(key, default):
    try: return int(cfg().get(key, default))
    except (TypeError, ValueError): return int(default)


def evidence_in(text):
    """The creator's own sentence saying clips are allowed, a short quotation around the phrase ("" when the text does not say so,
    or says the opposite: "no clips allowed", "please do not clip this")."""
    t = " ".join(str(text or "").split())
    for m in PHRASE_RE.finditer(t):
        before = re.split(r"[.!?;:]", t[max(0, m.start() - 45):m.start()])[-1]
        if NEGATION.search(before) or NEGATED_AFTER.match(t[m.end():m.end() + 24]): continue
        lo, hi = max(0, m.start() - 70), min(len(t), m.end() + 90)
        snippet = t[lo:hi].strip()
        return DASHES.sub(" - ", ("..." if lo else "") + snippet + ("..." if hi < len(t) else "")).replace('"', "'")
    return ""


def combos():
    """Every (niche, phrase) pair, phrase by phrase, so the first runs of a cycle cover every niche."""
    return [(n, p) for p in PHRASES for n in NICHES]


def pick(state, n=3):
    """The n combinations searched longest ago (never searched first, in the order of combos())."""
    used, order = (state or {}).get("used") or {}, combos()
    ranked = sorted(range(len(order)), key=lambda i: (used.get(f"{order[i][0]}|{order[i][1]}", ""), i))
    return [order[i] for i in ranked[:max(0, n)]]


def load_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}


def due(state, today, force=False):
    """The scout runs once a week (outreach_every_days, 7)."""
    if force: return True
    try: return (today - dt.date.fromisoformat(str(state.get("last_run")))).days >= setting("outreach_every_days", 7)
    except ValueError: return True


def existing():
    """(rows, columns) of clips/outreach.csv; columns Charlie added by hand are kept."""
    if not OUT.exists(): return [], list(FIELDS)
    with OUT.open(newline="") as f:
        rd = csv.DictReader(f)
        rows = [dict(r) for r in rd]
        return rows, list(FIELDS) + [c for c in (rd.fieldnames or []) if c not in FIELDS]


def channel_id(url):
    m = re.search(r"/channel/([A-Za-z0-9_-]+)", str(url or ""))
    return m.group(1) if m else str(url or "")


def search(yt, niche, phrase, quota):
    """(channel id, video id) of the recent videos for a niche and a phrase; None when the allowance says no (the search bucket
    of its own, 100 a day shared by every workflow, and the day's uploads keep their share)."""
    if not quota.allow(100, "outreach search"): return None
    quota.spend(100, "outreach search")
    since = (NOW - dt.timedelta(days=setting("outreach_days", 90))).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = yt.search().list(part="snippet", q=f'"{phrase}" {NICHES[niche]}', type="video", order="date", publishedAfter=since,
                         maxResults=50, relevanceLanguage="en", safeSearch="strict").execute()
    return [((it.get("snippet") or {}).get("channelId"), (it.get("id") or {}).get("videoId")) for it in r.get("items", [])
            if (it.get("snippet") or {}).get("channelId") and (it.get("id") or {}).get("videoId")]


def read_all(yt, kind, part, ids, quota):
    """videos.list or channels.list for the ids, 50 a call, 1 unit a call, while the allowance allows."""
    out = []
    for i in range(0, len(ids), 50):
        if not quota.allow(1, "outreach read"): log("the YouTube allowance is kept for uploads; the rest waits for the next week"); break
        quota.spend(1, "outreach read")
        out += getattr(yt, kind)().list(part=part, id=",".join(ids[i:i + 50])).execute().get("items", [])
    return out


def candidates(hits, videos, channels, today):
    """New rows from what the searches found: channels under outreach_max_subscribers (50,000) and over outreach_min_subscribers
    (500; a count the creator hides is skipped), saying clips are allowed in the channel description or a recent video's
    description, and not about the topics the channel rules rule out. hits {channel id: niche}."""
    top, floor = setting("outreach_max_subscribers", 50000), setting("outreach_min_subscribers", 500)
    seen = {}
    for v in videos:                                    # the videos' own words, per channel
        sn = v.get("snippet") or {}
        seen.setdefault(sn.get("channelId"), []).append((v.get("id"), sn.get("title", ""), sn.get("description", "")))
    out = []
    for ch in channels:
        cid, sn, stats = ch.get("id"), ch.get("snippet") or {}, ch.get("statistics") or {}
        if cid not in hits or stats.get("hiddenSubscriberCount"): continue
        try: subs = int(stats.get("subscriberCount"))
        except (TypeError, ValueError): continue
        if not floor <= subs < top: continue
        words = " ".join([sn.get("title", ""), sn.get("description", "")] + [f"{t} {d}" for _, t, d in seen.get(cid, [])])
        if AVOID.search(words): continue
        proof = evidence_in(sn.get("description"))
        if proof: proof += " [channel description]"
        else:
            for vid, _, text in seen.get(cid, []):          # a video's description, never its title (a title is not a permission)
                proof = evidence_in(text)
                if proof: proof += f" [video {VIDEO_URL}{vid}]"; break
        if not proof: continue
        out.append({"channel": DASHES.sub(" - ", " ".join(str(sn.get("title") or cid).split())), "url": CHANNEL_URL + cid, "subscribers": subs,
                    "niche": hits[cid], "evidence": proof, "found_on": str(today), "status": "new"})
    return sorted(out, key=lambda r: (-r["subscribers"], r["channel"].lower()))


def merge(rows, cols, new, cap=40):
    """The file's rows with the new ones added at the end: a channel already listed keeps its row and status (only its subscriber
    count is refreshed); at most `cap` new channels a run. Returns (rows, the rows added)."""
    have = {channel_id(r.get("url")): r for r in rows}
    fresh = []
    for r in new:
        old = have.get(channel_id(r["url"]))
        if old is not None: old["subscribers"] = r["subscribers"]; continue
        if len(fresh) >= cap: continue
        row = {c: r.get(c, "") for c in cols}; rows.append(row); fresh.append(row); have[channel_id(r["url"])] = row
    return rows, fresh


def save(rows, cols):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", restval=""); w.writeheader(); w.writerows(rows)


def client():
    """A YouTube client for the read calls: the first clips channel with a sign-in (clips.py clips_client)."""
    import clips
    err = None
    for ch in ("clips", "gaming", "irl"):
        if not (ROOT / "tokens" / f"youtube_{ch}.enc").exists(): continue
        try: return clips.clips_client(ch)
        except Exception as e: err = e
    raise RuntimeError(f"no clips channel sign-in to search with ({str(err)[:100] if err else 'none stored'})")


def run(yt=None, force=False, quota=None, today=None):
    """One weekly scout. Returns the new rows added (a list, [] when nothing was due or found)."""
    if quota is None:
        import quota
    today = today or NOW.astimezone(UK).date()
    state = load_state()
    if not due(state, today, force):
        log(f"scouted on {state.get('last_run')}; next on {dt.date.fromisoformat(str(state['last_run'])) + dt.timedelta(days=setting('outreach_every_days', 7))}"); return []
    n_searches = max(0, min(3, setting("outreach_searches", 3)))        # 3 a run at most: 300 of the 10,000 units
    plan = pick(state, n_searches)
    if not plan: return []
    yt = yt or client()
    hits, vids, used = {}, [], dict(state.get("used") or {})
    for niche, phrase in plan:
        try: found = search(yt, niche, phrase, quota)
        except Exception as e: log(f"search for {phrase} ({niche}) failed: {type(e).__name__}: {str(e)[:120]}"); continue
        if found is None: log("stopped: the YouTube allowance is kept for uploads; the next run goes on"); break
        used[f"{niche}|{phrase}"] = str(today)
        log(f"{niche} / {phrase}: {len(found)} recent videos")
        for cid, vid in found:
            hits.setdefault(cid, niche)
            if vid not in vids: vids.append(vid)
    new = []
    if hits:
        videos = read_all(yt, "videos", "snippet", vids, quota)
        channels = read_all(yt, "channels", "snippet,statistics", list(hits), quota)
        new = candidates(hits, videos, channels, today)
    rows, cols = existing()
    rows, fresh = merge(rows, cols, new)
    save(rows, cols)
    if used != (state.get("used") or {}):                 # only a run that searched counts as the week's
        state.update(used=used, last_run=str(today))
        STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(state, indent=1))
    log(f"{len(new)} channels say clips are allowed, {len(fresh)} new in clips/outreach.csv ({len(rows)} listed)")
    return fresh


def main(argv=None, yt=None, quota=None):
    argv = sys.argv[1:] if argv is None else argv
    try: run(yt=yt, force="--force" in argv, quota=quota)
    except Exception as e: log(f"{type(e).__name__}: {str(e)[:200]}")      # never holds up the scout run it follows
    return 0


if __name__ == "__main__":
    sys.exit(main())
