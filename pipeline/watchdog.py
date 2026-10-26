"""Missed-run watchdog (26 October): GitHub drops or delays scheduled runs under load (the 12:47 UTC trends run on
26 October never started, so the afternoon's Shorts were never written). watchdog.yml runs this every hour: a watched
workflow with no run since its last slot (SLOTS, plus GRACE minutes) or for longer than its gap (GAPS) is started by hand,
once, through `gh workflow run`. Read only: it never commits. publish.yml is left out on purpose (a manual dispatch there
defaults to "approve all"), and so is clips.yml while clipping is paused.

python pipeline/watchdog.py          start what is overdue
python pipeline/watchdog.py --dry    say what would be started"""
import datetime as dt, json, os, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = os.environ.get("GITHUB_REPOSITORY", "quickplay-studio/quickplay-autopilot")
GRACE = 50                       # minutes after a slot before a missing run counts as dropped (GitHub starts crons up to 60 late)
SLOTS = {"trends.yml": ["08:10", "12:47", "18:23"]}       # the three main runs (the breaking checks are only a top-up)
GAPS = {"render.yml": 240, "analytics.yml": 180, "social.yml": 120, "engage.yml": 180, "evolve.yml": 1560}   # minutes


def _t(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def last_slot(now, slots):
    """The latest of the day's UTC slots ("HH:MM") at or before now, looking back into yesterday."""
    best = None
    for day in (now.date(), now.date() - dt.timedelta(days=1)):
        for s in slots:
            h, m = map(int, s.split(":"))
            t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=dt.timezone.utc)
            if t <= now and (best is None or t > best): best = t
    return best


def overdue(wf, now, runs):
    """A reason to start `wf` now, or "" when it is fine. `runs`: [{createdAt, status}] newest first, any event."""
    if any(r.get("status") in ("queued", "in_progress", "waiting", "pending", "requested") for r in runs): return ""
    newest = max((_t(r["createdAt"]) for r in runs if r.get("createdAt")), default=None)
    if wf in SLOTS:
        s = last_slot(now, SLOTS[wf])
        if s and (now - s).total_seconds() >= GRACE * 60 and (newest is None or newest < s - dt.timedelta(minutes=10)):
            return f"no run since the {s:%H:%M} UTC slot"
        return ""
    gap = GAPS.get(wf)
    if gap and (newest is None or (now - newest).total_seconds() > gap * 60):
        return f"no run for {gap // 60} hours" if newest else "no run yet"
    return ""


def _gh(*args):
    return subprocess.run(["gh", *args, "-R", REPO], capture_output=True, text=True, timeout=60)


def main(dry=False):
    now = dt.datetime.now(dt.timezone.utc)
    started, listed = 0, 0
    for wf in [*SLOTS, *GAPS]:
        if not (ROOT / ".github" / "workflows" / wf).exists(): continue
        p = _gh("run", "list", "-w", wf, "-L", "5", "--json", "createdAt,status")
        if p.returncode: print(f"{wf}: cannot list runs: {p.stderr.strip()[:150]}"); continue
        listed += 1
        why = overdue(wf, now, json.loads(p.stdout or "[]"))
        if not why: print(f"{wf}: fine"); continue
        if dry: print(f"{wf}: would start ({why})"); continue
        q = _gh("workflow", "run", wf, "--ref", "main")
        print(f"{wf}: started ({why})" if q.returncode == 0 else f"{wf}: could not start: {q.stderr.strip()[:150]}")
        started += q.returncode == 0
    print(f"watchdog: {started} started")
    if not listed: raise SystemExit("watchdog: could not list any workflow's runs")     # fail the run, so it shows on GitHub


if __name__ == "__main__":
    main(dry="--dry" in sys.argv)
