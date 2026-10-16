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

def main():
    statuses = [s for s in (load(p) for p in sorted((ROOT / "status").glob("*.json")) if p.name != "channel.json") if s and s.get("id")]
    social = load(ROOT / "status" / "social.json") or {}
    channel = load(ROOT / "status" / "channel.json") or {}
    by_video = {s.get("video"): s for s in statuses if s.get("video")}
    now = dt.datetime.now(dt.timezone.utc)
    lines = ["# Quickplay Daily review", ""]
    if channel:
        lines += [f"YouTube checked {uk(channel['checked'])} (UK): {channel['scheduled']} scheduled, {channel['public']} public, "
                  f"{channel['uploads_last_24h']} uploads in the last 24 hours.", ""]
    if social:
        ig, tt = social.get("instagram") or {}, social.get("tiktok") or {}
        lines += [f"Instagram: {'connected as ' + str(ig.get('username')) if ig.get('ok') else ig.get('error', 'not connected')} · "
                  f"TikTok: {'connected' if tt.get('ok') else tt.get('error', 'not connected')} (checked {uk(social['checked'])}).", ""]

    problems = [s for s in statuses if "fail" in s.get("state", "") or "not scheduled" in s.get("state", "")]
    flagged = channel.get("flagged", [])
    if problems or flagged or any(s.get(k) for s in statuses for k in ("instagram_error", "tiktok_error", "social_error")):
        lines += ["## Needs a look", ""]
        for s in problems:
            lines.append(f"- **{s['id']}** {s.get('title') or ''}: {s['state']}. {s.get('error', '')}".rstrip())
        for s in statuses:
            for k in ("instagram_error", "tiktok_error", "social_error"):
                if s.get(k): lines.append(f"- **{s['id']}** {s.get('title') or ''}: {k.split('_')[0]} {s[k]}")
        for r in flagged:
            lines.append(f"- [{r['title']}](https://youtube.com/shorts/{r['video']}): {r['flag']}")
        lines.append("")

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
            if s.get("tiktok"): bits.append("on TikTok" if s["tiktok"].get("mode") == "direct" else "in TikTok drafts")
            elif s.get("tiktok_skipped"): bits.append("not sent to TikTok (too old)")
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
