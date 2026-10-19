"""Write review/README.md: one page to check every Short from a phone (GitHub shows it when you open the review folder).
Built from status/<id>.json (what the pipeline did), status/channel.json (what YouTube shows) and review/<id>.jpg.
usage: python pipeline/review_page.py
"""
import datetime as dt, json, pathlib
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")

def uk(ts):
    if not ts: return ""
    t = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UK)
    return t.strftime("%a %d %b %H:%M").replace(" 0", " ")

def load(p):
    try: return json.loads(p.read_text())
    except Exception: return None

def posts_by_day(statuses, now):
    """One row a day (tomorrow back to 6 days ago, UK dates): Shorts going public on YouTube that day, Reels posted to
    Instagram and Facebook, against the day's target (daily_limit as it stood that morning, kept in status/targets.json,
    one fewer on Sundays for the weekly video)."""
    cfg = load(ROOT / "config.json") or {}
    today = now.astimezone(UK).date()
    aim = lambda d: int(cfg.get("daily_limit", 24)) - (1 if d.weekday() == 6 else 0)
    tp = ROOT / "status" / "targets.json"
    targets = load(tp) or {}
    if str(today) not in targets:
        targets[str(today)] = aim(today)
        tp.write_text(json.dumps(dict(sorted(targets.items())[-60:]), indent=0))
    def ukday(ts):
        try: return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(UK).date()
        except ValueError: return None
    pub, sch, ig, fb = {}, {}, {}, {}
    add = lambda d, k: d.__setitem__(k, d.get(k, 0) + 1)
    for s in statuses:
        if s.get("video") and s.get("publish_at"):
            live = dt.datetime.fromisoformat(s["publish_at"].replace("Z", "+00:00")) <= now
            add(pub if live else sch, ukday(s["publish_at"]))
        for k, d in (("instagram", ig), ("facebook", fb)):
            if isinstance(s.get(k), dict) and s[k].get("at"): add(d, ukday(s[k]["at"]))
    rows = ["## Posts by day", "", "YouTube counts Shorts by the day they go public. Instagram and Facebook build up to the "
            "same number over time.", "", "| Day | YouTube | Instagram | Facebook | Target met? |", "|---|---|---|---|---|"]
    for day in [today + dt.timedelta(days=k) for k in range(1, -7, -1)]:
        p, s = pub.get(day, 0), sch.get(day, 0)
        t = targets.get(str(day)) or (aim(day) if day > today else None)
        if not t: note = "no target then"
        elif day > today: note = f"⏳ {s} of {t} scheduled"
        elif day == today: note = "✅ done" if p >= t else f"⏳ {p} of {t} so far" + (f", {s} more scheduled" if s else "")
        else: note = "✅ all out" if p >= t else f"⚠️ {p} of {t}"
        yt = f"{p} public" + (f", {s} scheduled" if s else "")
        rows.append(f"| {day:%a} {day.day} {day:%b} | {yt} | {ig.get(day, 0)} | {fb.get(day, 0)} | {note} |")
    return rows + [""]


def main():
    statuses = [s for s in (load(p) for p in sorted((ROOT / "status").glob("*.json")) if p.name != "channel.json") if s and s.get("id")]
    social = load(ROOT / "status" / "social.json") or {}
    channel = load(ROOT / "status" / "channel.json") or {}
    by_video = {s.get("video"): s for s in statuses if s.get("video")}
    now = dt.datetime.now(dt.timezone.utc)
    lines = ["# Quickplay Daily review", ""]
    prog = ROOT / "analytics" / "progress.csv"      # the stats, so Charlie needs no Claude run to see them
    if prog.exists():
        import csv
        rows = list(csv.DictReader(prog.open()))
        if rows:
            p = rows[-1]
            def n(k):
                try: return f"{int(float(p.get(k) or '')):,}"
                except ValueError: return "?"
            lines += [f"**Progress** ({p.get('as_of_uk', '')}): {n('subscribers')} of 1,000 subscribers · {n('engaged_views_90d')} of "
                      f"10 million Shorts views in 90 days · {n('views_last_24h')} views in the last 24 hours (about "
                      f"{n('needed_per_day')} a day needed, {p.get('days_left', '?')} days left) · Instagram {n('ig_followers')} and "
                      f"Facebook {n('fb_followers')} followers.", ""]
    if channel:
        lines += [f"YouTube checked {uk(channel['checked'])} (UK): {channel['scheduled']} scheduled, {channel['public']} public, "
                  f"{channel['uploads_last_24h']} uploads in the last 24 hours.", ""]
    if social:
        ig, fb = social.get("instagram") or {}, social.get("facebook") or {}
        lines += [f"Instagram: {'connected as ' + str(ig.get('username')) if ig.get('ok') else ig.get('error', 'not connected')} · "
                  f"Facebook: {'connected to ' + str(fb.get('page')) if fb.get('ok') else fb.get('error', 'not connected')} (checked {uk(social['checked'])}).", ""]
        exp = fb.get("data_access_expires")         # Meta wants the key renewed about every 90 days
        if exp and str(exp).isdigit():
            left = (dt.datetime.fromtimestamp(int(exp), dt.timezone.utc) - now).days
            if left < 15:
                lines += [f"**Facebook's key runs out in {max(left, 0)} days**: make a new one in the Graph API Explorer as before "
                          "and paste it into the FB_PAGE_TOKEN secret.", ""]

    lines += posts_by_day(statuses, now)
    problems = [s for s in statuses if ("fail" in s.get("state", "") or "not scheduled" in s.get("state", ""))
                and not s["id"].startswith("TEST-") and s.get("mode") not in ("dry", "none")]     # test renders never need a look
    flagged = channel.get("flagged", [])
    if problems or flagged or any(s.get(k) for s in statuses for k in ("instagram_error", "facebook_error", "social_error")):
        lines += ["## Needs a look", "", "Nothing here needs approving (approval is off): a failed Short is skipped and the next one "
                  "takes its slot. Only Instagram or Facebook errors that keep coming back need fixing, in a Claude chat with the "
                  "quickplay skill.", ""]
        for s in problems:
            lines.append(f"- **{s['id']}** {s.get('title') or ''}: {s['state']}. {s.get('error', '')}".rstrip())
        for s in statuses:
            for k in ("instagram_error", "facebook_error", "social_error"):
                if s.get(k): lines.append(f"- **{s['id']}** {s.get('title') or ''}: {k.split('_')[0]} {s[k]}")
        for r in flagged:
            lines.append(f"- [{r['title']}](https://youtube.com/shorts/{r['video']}): {r['flag']}")
        lines.append("")

    ready = sorted((ROOT / "boards" / "ready").glob("*.json"))
    if ready:
        lines += ["## Waiting for your approval", "",
                  "Reply to the daily message (\"approve all\", \"approve all except QD-032\", \"reject QD-032\"), or on GitHub: "
                  "Actions, publish, Run workflow, and type the same.", ""]
        by_id = {s["id"]: s for s in statuses}
        for p in ready:
            b = load(p) or {}; s = by_id.get(b.get("id"), {})
            bits = [s.get("state", "rendering")]
            if s.get("qa", {}).get("duration"): bits.append(f"{s['qa']['duration']:.0f} s")
            if s.get("preview_url"): bits.append(f"[watch preview]({s['preview_url']})")
            lines += [f"### {b.get('id', p.stem)} · {b.get('meta', {}).get('title', '')}", " · ".join(bits)]
            for f in s.get("flags", []): lines.append(f"- {f}")
            lines.append("")
            if (ROOT / "review" / f"{b.get('id')}.jpg").exists(): lines += [f"![{b.get('id')}]({b.get('id')}.jpg)", ""]

    queued = sorted((ROOT / "boards" / "queue").glob("*.json"))
    waiting = {s["id"]: s for s in statuses if s.get("state", "").startswith("waiting")}
    if queued:
        lines += ["## In the queue", ""]
        for p in queued:
            b = load(p) or {}
            note = "waiting for YouTube's daily limit" if b.get("id") in waiting else "rendering next"
            lines.append(f"- **{b.get('id', p.stem)}** {b.get('meta', {}).get('title', '')} ({note})")
        lines.append("")

    vids = sorted(channel.get("videos", []), key=lambda r: r.get("publish_at") or r.get("uploaded") or "", reverse=True)[:40]
    if vids:
        lines += ["## On the channel (latest first)", ""]
        for r in vids:
            s = by_video.get(r["video"], {})
            when = r.get("publish_at") or r.get("uploaded")
            live = r["privacy"] == "public" or (r.get("publish_at") and dt.datetime.fromisoformat(r["publish_at"].replace("Z", "+00:00")) <= now)
            state = "public" if r["privacy"] == "public" else ("scheduled" if r.get("publish_at") and not live else r["privacy"])
            bits = [state]
            if r.get("views") and r["privacy"] == "public": bits.append(f"{r['views']:,} views")
            if s.get("qa", {}).get("duration"): bits.append(f"{s['qa']['duration']:.0f} s")
            if s.get("music"): bits.append(f"music: {s['music']}")
            if s.get("instagram"): bits.append("on Instagram")
            if s.get("facebook"): bits.append("on Facebook")
            if s.get("board"): bits.append(f"[script](../{s['board'].replace('queue/', 'done/')})")
            lines += [f"### {uk(when)} · {r['title']}", " · ".join(bits) + f" · [YouTube](https://youtube.com/shorts/{r['video']})", ""]
            if s.get("id") and (ROOT / "review" / f"{s['id']}.jpg").exists():
                lines += [f"![{s['id']}]({s['id']}.jpg)", ""]
    else:
        done = sorted(statuses, key=lambda s: s.get("rendered", ""), reverse=True)[:40]
        if done:
            lines += ["## Latest renders", ""]
            for s in done:
                lines += [f"### {s['id']} · {s.get('title') or ''}", s.get("state", ""), ""]
                if (ROOT / "review" / f"{s['id']}.jpg").exists(): lines += [f"![{s['id']}]({s['id']}.jpg)", ""]
    (ROOT / "review").mkdir(exist_ok=True)
    (ROOT / "review" / "README.md").write_text("\n".join(lines).rstrip() + "\n")
    print("review page:", len(lines), "lines")

if __name__ == "__main__":
    main()
