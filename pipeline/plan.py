"""Pick queued boards for this run and give each a posting slot. Prints `boards=<json>` for the GitHub matrix.

Rules (numbers live in config.json)
- At most upload_limit_24h uploads in any 24 hours (default daily_limit), counting every upload on the channel
  (including ones made by hand). YouTube may enforce a lower limit; then the extra boards wait in the queue and the next
  run tries again. daily_limit is how many Shorts a day the writer makes; slots_per_day caps how many go public a day.
- A board whose "created" date is a later day (the 20:50 evening run writes the first part of tomorrow) gets that day's
  slots, never tonight's.
- Slots: slots_per_day a day (or the learned ceiling, quota.daily_limit), covering all 24 hours from slot_first (UK): a
  third of the audience is American and a fifth Asian, so the UK night counts. Until 30 Shorts have results: every
  slot_every_minutes (at most 1440 / n); then the times learned from results (analytics/slots.json, learned_slots, any
  hour of the day). A slot already taken is never reused.
- A Short goes to the first free slot at least lead_hours away (time to render and process), or, when its category
  clearly does better in another quarter of the UK day (analytics/slots.json "bands"), the first free slot there within
  18 hours (6 for news).
- A board may fix its slot with "publish_at": "YYYY-MM-DD HH:MM" (UK time), or set "mode": "private"
  (test upload, not scheduled), "mode": "none" (render only) or "mode": "dry" (rendered and held for approval like a real
  Short, but never uploaded: tests the approval path).
- A board that fails pipeline/validate.py is not rendered: it goes to boards/failed with the reasons.
- Approval (config "approval"): "all" = every Short waits for Charlie's OK after rendering; "flagged" = only Shorts with a
  reason to look (the writer's "flag", validator warnings, or render checks) wait; "none" = nothing waits.
  Waiting Shorts are rendered but not uploaded, so they don't use the daily upload limit; pipeline/publish.py uploads
  them once approved.
"""
import datetime as dt, json, os, pathlib, sys, time
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
CFG = json.loads((ROOT / "config.json").read_text())
import quota
LIMIT = int(os.environ.get("DAILY_LIMIT") or max(quota.daily_limit(), int(CFG.get("upload_limit_24h", CFG.get("daily_limit", 10)))))
LEAD = dt.timedelta(hours=float(CFG.get("lead_hours", 3)))

def _mins(hm):
    h, m = map(int, hm.split(":")); return h * 60 + m


def _apart(a, b):
    """Minutes between two times of day, the short way round midnight."""
    d = abs(_mins(a) - _mins(b)); return min(d, 1440 - d)

def learned_slots(n):
    """The day's posting times learned from results (analytics/slots.json, refreshed once a day so a day's times stay
    fixed): each half hour from 07:00 to 22:30 scores by how Shorts posted at or near it did against Shorts posted
    around the same days; the best n are kept at least 75 minutes apart. Times with little data get a small bonus so
    they're still tried. None until 30 Shorts have results."""
    try: stats = json.loads((ROOT / "analytics" / "slots.json").read_text()).get("slots") or {}
    except Exception: return None
    if sum(v.get("n", 0) for v in stats.values()) < 30: return None
    def score(c):
        num = den = 0.0
        for k, v in stats.items():
            d = _apart(k, c)
            if d <= 60:
                w = v.get("n", 0) * (1.0 if d == 0 else 0.5 if d <= 30 else 0.25)
                num += w * v.get("score", 1.0); den += w
        sc = (num + 3.0) / (den + 3.0)
        return max(sc, 1.03) if den < 2 else sc
    mins = (0, 30) if n <= 40 else (0, 15, 30, 45)     # more than 40 a day needs quarter hours
    ranked = sorted((f"{h:02d}:{m:02d}" for h in range(24) for m in mins), key=lambda c: (-score(c), c))   # all 24 hours: the
    for gap in (75, 60, 45, 30, 20, 15):      # audience is a third American and a fifth Asian, so the UK night counts
        picked = []
        for c in ranked:
            if all(_apart(c, q) >= gap for q in picked): picked.append(c)
            if len(picked) == n: return sorted(picked)
    return None

def day_slots(day):
    n = quota.target() if CFG.get("shorts_per_day") or quota.VOLUME_P.exists() else \
        max(int(CFG.get("slots_per_day", 10)), quota.daily_limit())       # a slot for every Short, at the day's best times
    times = learned_slots(n)
    if times:
        return [dt.datetime(day.year, day.month, day.day, *map(int, t.split(":")), tzinfo=UK).astimezone(dt.timezone.utc)
                for t in times]
    h, m = map(int, CFG.get("slot_first", "09:00").split(":"))
    first = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=UK)
    every = min(int(CFG.get("slot_every_minutes", 90)), max(8, 1440 // n))     # the day's slots cover all 24 hours from slot_first
    step = dt.timedelta(minutes=every)
    return [(first + step * i).astimezone(dt.timezone.utc) for i in range(n)]

def schedule_state(now, yt=None):
    """(taken slots, uploads in the last 24 hours, YouTube reachable). Our uploads come from status files (exact upload
    time). YouTube only gives a reliable upload time for videos that are still private (once public, the playlist date
    becomes the publish time), so other private uploads are added from the channel; anything else is caught by YouTube's
    own limit error."""
    import youtube as Y
    taken, recent, online = set(), 0, Y.available()
    statuses = []
    for f in (ROOT / "status").glob("*.json"):
        if f.name == "channel.json": continue
        try: st = json.loads(f.read_text())
        except Exception: continue
        if isinstance(st, dict): statuses.append(st)
    ours = {st.get("video") for st in statuses if st.get("video")}
    for st in statuses:
        if st.get("publish_at"): taken.add(Y.utc(st["publish_at"]))
        up = Y.utc(st.get("uploaded_at"))
        if up and now - up < dt.timedelta(hours=24): recent += 1
    if online:
        for v in Y.recent_videos(yt or Y.client()):
            if v["publish_at"]: taken.add(Y.utc(v["publish_at"]))
            up = Y.utc(v["uploaded"])
            if v["id"] not in ours and v["privacy"] != "public" and up and now - up < dt.timedelta(hours=24): recent += 1
    return taken, recent, online

BANDS = ("00-06", "06-12", "12-18", "18-24")         # UK hours: 00-06 is the American evening, 06-12 Asia and the US night
FRESH = {"news", "breaking", "follow-up", "remake"}    # news can't wait long for a better hour


def band(t):
    return BANDS[t.astimezone(UK).hour // 6]


def band_scores():
    """{category: {band: score}} from analytics/slots.json "bands": each category's Shorts by the UK quarter of the day they
    went out, views against typical, shrunk towards that band's overall score (4 Shorts' worth) so a lucky one can't
    decide. Empty until a category has 12 measured Shorts."""
    try: bands = json.loads((ROOT / "analytics" / "slots.json").read_text()).get("bands") or {}
    except Exception: return {}
    allb, out = bands.get("_all") or {}, {}
    for cat, bs in bands.items():
        if cat == "_all" or sum(v.get("n", 0) for v in bs.values()) < 12: continue
        out[cat] = {}
        for b in BANDS:
            base = (allb.get(b) or {}).get("score", 1.0)
            v = bs.get(b) or {}
            out[cat][b] = (v.get("n", 0) * v.get("score", base) + 4 * base) / (v.get("n", 0) + 4)
    return out


def slot_picker(now, taken):
    scores = band_scores()

    def free(created):
        day = (now + LEAD).astimezone(UK).date() - dt.timedelta(days=1)      # yesterday's list runs on past midnight
        try:
            want = dt.date.fromisoformat(str(created)[:10]) if created else None
            if want and want > day: day = want
        except ValueError: pass
        for _ in range(60):
            for t in day_slots(day):
                if t >= now + LEAD and t not in taken: yield t
            day += dt.timedelta(days=1)

    def next_slot(created=None, category=None, kind=None, sid="", explore=False):
        """The first free slot at least lead_hours away, on or after the board's "created" day (UK); when the data shows
        the board's category does clearly better in another quarter of the day (band_scores, at least 15% better), the
        first free slot in that quarter within the next 18 hours (6 for news). 1 board in 5 keeps the first slot so
        every hour stays measured (Charlie, 23 October: post music when the Americans watch). An exploration Short
        (writer.py, test "explore") takes a quarter of the day drawn evenly from those within the window instead."""
        import random
        first = next(free(created), None)
        if first is None: raise RuntimeError("no free slot in the next 60 days")
        pick, sc = first, scores.get(category or "")
        window = dt.timedelta(hours=6 if kind in FRESH else 18)
        def within():
            out = []
            for t in free(created):
                if t > first + window: break
                out.append(t)
            return out
        if explore:
            cands = within()
            bands = sorted({band(t) for t in cands})
            b = random.Random(f"explore-slot:{sid}").choice(bands)
            pick = next(t for t in cands if band(t) == b)
        elif sc and random.Random(f"slot:{sid}").random() >= 0.2:
            cands = within()
            best = max(cands, key=lambda t: (sc[band(t)], -t.timestamp()))
            if sc[band(best)] >= 1.15 * sc[band(first)]: pick = best
        taken.add(pick); return pick
    return next_slot

def hold_reasons(b, warnings):
    """Why this Short should wait for Charlie's approval (empty list: it can go out on its own)."""
    mode = CFG.get("approval", "flagged")
    if b.get("reserve"):            # evergreen spare: waits in boards/reserve (publish.py), however approval is set
        return ["reserve: waits in boards/reserve to fill slots the day's writer runs leave empty"] + \
               ([f"writer: {b['flag']}"] if b.get("flag") else []) + [f"check: {w}" for w in warnings]
    if mode == "none": return []
    out = ["approval is on for every Short (config.json)"] if mode == "all" else []
    if b.get("flag"): out.append(f"writer: {b['flag']}")
    out += [f"check: {w}" for w in warnings]
    return out

def main():
    queue = sorted((ROOT / "boards" / "queue").glob("*.json"))
    if not queue:
        print("boards=[]"); return
    import validate as V
    import freshness as FR
    now = dt.datetime.now(dt.timezone.utc)
    taken, recent, online = schedule_state(now)
    capacity = max(0, LIMIT - recent)
    uk_today = now.astimezone(UK).date()
    if uk_today.weekday() == 6:      # Sunday: keep one upload for the weekly long video (weekly.py) until it's up
        wk = ROOT / "status" / f"weekly-{uk_today}.json"
        try: done_wk = bool(json.loads(wk.read_text()).get("video"))
        except Exception: done_wk = False
        if not done_wk: capacity = max(0, capacity - 1)
    next_slot = slot_picker(now, taken)

    import looks as LK         # each new Short's look: caption style, voice, energy, grade (templates/looks.json)
    stats, seen = LK.load_stats(), []
    for sp in (ROOT / "status").glob("QD-*.json"):
        try: st = json.loads(sp.read_text())
        except Exception: continue
        if st.get("look"): seen.append((st.get("rendered", ""), st["look"]))
    recent_looks = [lk for _, lk in sorted(seen, key=lambda x: x[0])][-20:]     # 20: looks.choose caps an option at 70% of them

    import background as BG    # the video behind each Short: one clip per search, never one used in the last reuse_days
    bg_used, bg_cfg = None, BG.settings(CFG)
    BG.DEADLINE = time.time() + 240        # searching must never hold the run up: past this, Shorts render without a background

    jobs, uploads = [], 0
    for p in queue:
        try: b = json.loads(p.read_text())
        except Exception: b = {"id": p.stem}
        errs, warns = V.check(b, p) if "beats" in b else (["not a valid board"], [])
        if errs:
            jobs.append({"board": str(p.relative_to(ROOT)), "id": b.get("id", p.stem), "slot": "", "mode": "reject",
                         "errors": "; ".join(errs)[:900]})
            continue
        mode = b.get("mode", "schedule")
        if mode in ("schedule", "private") and not online: mode = "none"
        warns = [x for x in warns if not x.startswith("background:")]     # a board without searches gets its category's: never held for it
        hold = hold_reasons(b, warns) if mode != "none" else []
        if mode == "dry" and not hold: hold = ["dry run: always waits for approval, never uploaded"]
        counted = False
        if mode != "none" and not hold:
            if uploads >= capacity: continue
            uploads += 1; counted = True
        explore = (b.get("test") or {}).get("explore") == "yes"      # an exploration Short (writer.py): look and hour drawn evenly
        slot, slot_t = "", None
        if mode == "schedule" and not hold:
            t = None
            if b.get("publish_at"):
                t = dt.datetime.strptime(b["publish_at"], "%Y-%m-%d %H:%M").replace(tzinfo=UK).astimezone(dt.timezone.utc)
                if t < now + dt.timedelta(minutes=45): t = None
                else: taken.add(t)
            slot_t = t or next_slot(b.get("created"), b.get("category"), b.get("kind"), b.get("id", ""), explore=explore)
            slot = slot_t.isoformat().replace("+00:00", "Z")
        # Charlie (24 October): a news Short that would go public after its day needs the data to say its story is still
        # alive, or it expires (freshness.py: boards/expired, analytics/late_uploads.csv)
        late = FR.safe_check(b, slot_t or now, where="render", record=False) if mode == "schedule" else None
        if late and not late["alive"]:
            if slot_t: taken.discard(slot_t)
            if counted: uploads -= 1
            print(f"expired: {b['id']}: {late['evidence']}", file=sys.stderr)
            jobs.append({"board": str(p.relative_to(ROOT)), "id": b["id"], "slot": "", "mode": "reject", "expired": True,
                         "errors": late["evidence"][:900], "late": late})
            continue
        look = b.get("look") if isinstance(b.get("look"), dict) else LK.choose(b["id"], recent_looks, stats, explore=explore)
        recent_looks.append(look)
        job = {"board": str(p.relative_to(ROOT)), "id": b["id"], "slot": slot, "mode": mode, "hold": hold, "look": look}
        if late: job["late"] = late                 # late but alive: the evidence lands in status/<id>.json
        if BG.wanted(b, CFG):
            BG.NOTES.clear()
            try:
                if bg_used is None: bg_used = BG.recent_used(ROOT, int(bg_cfg["reuse_days"]))
                clips = BG.pick(b, bg_used, CFG)
                if clips: job["bg"] = clips
                else: print(f"background: no clips for {b['id']} (no key, or nothing matched): it renders without", file=sys.stderr)
            except Exception as e:
                BG.note(f"picking clips failed: {type(e).__name__}: {e}")
            if BG.NOTES: job["bg_notes"] = list(BG.NOTES)      # lands in status/<id>.json: the Actions logs are not readable from outside
        jobs.append(job)
    print(f"online={online} limit={LIMIT} capacity={capacity} recent_uploads={recent} queued={len(queue)} running={len(jobs)}",
          file=sys.stderr)
    print("boards=" + json.dumps(jobs, ensure_ascii=False))

if __name__ == "__main__":
    main()
