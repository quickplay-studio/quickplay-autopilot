"""Release storage that only grows (audit L3, 24 October: 7.73 GB in 75 releases, clips-out adding about 0.6 GB a day, and
draft previews weeks old). Weekly (prune.yml), conservatively:
- a draft preview-<id> or social-<id> release older than 7 days goes when its Short no longer needs it: not waiting in
  boards/queue, ready or reserve, not held for approval or for room on YouTube, and public for over 7 days (Instagram,
  Facebook and TikTok only take a Short in its first 48 hours). A release whose Short has no status file is only
  removed past 30 days. The status file then loses the release's name, so nothing tries to download it again.
- a clips-out asset (the clip file the Instagram, Facebook and TikTok posts read) older than 14 days goes when its clip is
  public for over 7 days or was never used; one that no clip plan names goes past 30 days. The campaigns need the
  public link, never the file.
At most MAX deletions a run; each is listed in status/prune_log.txt.
  python pipeline/prune_releases.py [--dry]
"""
import datetime as dt, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = dt.datetime.now(dt.timezone.utc)
MAX = 150
PENDING_BOARDS = ("queue", "ready", "reserve")
PENDING_STATES = ("awaiting approval", "approved", "in reserve", "waiting")


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def when(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError): return None


def days_since(s):
    t = when(s)
    return (NOW - t).total_seconds() / 86400 if t else None


def load(p, d=None):
    try: return json.loads(p.read_text())
    except Exception: return d


def short_needs(sid):
    """Why the Short still needs its draft release, or '' when it doesn't."""
    for d in PENDING_BOARDS:
        if (ROOT / "boards" / d / f"{sid}.json").exists(): return f"its board is in boards/{d}"
    st = load(ROOT / "status" / f"{sid}.json")
    if not isinstance(st, dict): return "no status file"
    if str(st.get("state", "")).startswith(PENDING_STATES): return f"state: {st.get('state')}"
    pub = st.get("publish_at") or st.get("uploaded_at")
    age = days_since(pub)
    if age is None: return "not public yet"
    if age < 7: return f"public {age:.1f} days ago (cross-posts take a Short in its first 48 hours)"
    return ""


def drafts(log, dry):
    r = gh("release", "list", "--limit", "400", "--json", "tagName,isDraft,createdAt")
    try: rels = json.loads(r.stdout or "[]")
    except ValueError: rels = []
    gone = 0
    for rel in rels:
        tag = rel.get("tagName") or ""
        if not rel.get("isDraft") or not tag.startswith(("preview-", "social-")): continue
        age = days_since(rel.get("createdAt"))
        if age is None or age < 7: continue
        sid = tag.split("-", 1)[1]
        why = short_needs(sid)
        if why and not (why == "no status file" and age >= 30): continue
        if gone >= MAX: log.append(f"stopped at {MAX} deletions"); break
        if not dry: gh("release", "delete", tag, "-y")
        gone += 1; log.append(f"{'would delete' if dry else 'deleted'} draft {tag} ({age:.0f} days old{'; ' + why if why else ''})")
        st = load(ROOT / "status" / f"{sid}.json")
        if isinstance(st, dict) and not dry:
            changed = False
            for k in ("preview_release", "social_release"):
                if st.get(k) == tag: st.pop(k); changed = True
            if changed:
                st["release_pruned"] = NOW.isoformat(timespec="minutes")
                (ROOT / "status" / f"{sid}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
    return gone


def clip_uses():
    """{asset file name: the latest public time of the clip that uses it (or None while it isn't public yet)}."""
    out = {}
    for p in (ROOT / "clips" / "plans").glob("*.json"):
        if p.name.endswith(".words.json"): continue
        plan = load(p, {}) or {}
        for m in plan.get("moments") or []:
            f = m.get("file")
            if not f: continue
            pub = m.get("publish_at")
            out[f] = None if pub in (None, "", "private") else pub
    return out


def clips_out(log, dry, budget):
    r = gh("release", "view", "clips-out", "--json", "assets")
    try: assets = json.loads(r.stdout or "{}").get("assets") or []
    except ValueError: assets = []
    uses, gone = clip_uses(), 0
    for a in assets:
        name, age = a.get("name") or "", days_since(a.get("createdAt") or a.get("updatedAt"))
        if not name or age is None or age < 14: continue
        if name in uses:
            pub = uses[name]
            pub_age = days_since(pub) if pub else None
            if pub and (pub_age is None or pub_age < 7): continue          # public less than a week, or a time in the future
            if not pub and age < 30: continue                               # private or not scheduled: kept a while longer
        elif age < 30: continue                                             # no plan names it: only past 30 days
        if gone >= budget: log.append(f"stopped at {MAX} deletions"); break
        if not dry: gh("release", "delete-asset", "clips-out", name, "-y")
        gone += 1; log.append(f"{'would delete' if dry else 'deleted'} clips-out/{name} ({age:.0f} days old)")
    return gone


def main(dry=False):
    log = []
    n = drafts(log, dry)
    n += clips_out(log, dry, MAX - n)
    head = f"{NOW:%Y-%m-%d %H:%M} UTC: {'dry run, ' if dry else ''}{n} release(s) or asset(s) {'to remove' if dry else 'removed'}"
    print(head); [print(" ", l) for l in log]
    p = ROOT / "status" / "prune_log.txt"
    p.write_text(head + "\n" + "".join(f"  {l}\n" for l in log))
    return n, log


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
