"""Alerts (Charlie, 19 October): a GitHub issue when something needs a look, so the GitHub app on his phone tells him,
and nothing otherwise. Run by .github/workflows/alerts.yml:
- after a main job finishes: two failures in a row open an issue for that job; its next success closes it;
- each evening (21:30 UTC): an issue if under 70% of the day's Shorts went public on YouTube, and one if the Facebook
  key runs out within 14 days; each closes again once things are fine.
Issues carry the label "alert", one per problem, updated rather than repeated.
  python pipeline/alerts.py         (EVENT=workflow_run with RUN_NAME, RUN_CONCLUSION and RUN_URL, or the evening check)
"""
import datetime as dt, json, os, pathlib, subprocess
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
REPO = "https://github.com/quickplay-studio/quickplay-autopilot"
WHAT = {"trends": "finding topics and building fact packs", "write": "writing the Shorts with Gemini",
        "render": "making the videos", "publish": "uploading and scheduling on YouTube",
        "social": "posting to Instagram and Facebook", "engage": "comments, playlists and second titles",
        "analytics": "the stats and what works", "weekly": "the weekly long video"}
HOWTO = ("Nothing to do if this closes by itself within a few hours. If it stays open, start a new Claude chat, use the "
         "quickplay skill and paste this issue's link.")


def gh(*a):
    return subprocess.run(["gh", *a], capture_output=True, text=True)


def open_issues():
    r = gh("issue", "list", "--label", "alert", "--state", "open", "--json", "number,title", "--limit", "50")
    try: return {i["title"]: i["number"] for i in json.loads(r.stdout or "[]")}
    except ValueError: return {}


def raise_issue(title, body):
    have = open_issues()
    if title in have:
        gh("issue", "comment", str(have[title]), "--body", body); print("updated:", title); return
    gh("label", "create", "alert", "--color", "B60205", "--description", "Automatic alert from the Quickplay automation")
    r = gh("issue", "create", "--title", title, "--body", body + "\n\n" + HOWTO, "--label", "alert")
    print("opened:", title, (r.stdout or r.stderr).strip())


def clear(title, body):
    have = open_issues()
    if title in have:
        gh("issue", "close", str(have[title]), "--comment", body); print("closed:", title)


def after_run():
    name, concl, url = os.environ.get("RUN_NAME", ""), os.environ.get("RUN_CONCLUSION", ""), os.environ.get("RUN_URL", "")
    if name not in WHAT: return
    title = f"⚠️ {name} is failing ({WHAT[name]})"
    if concl == "success": clear(title, f"Working again: {url}"); return
    if concl != "failure": return
    r = gh("run", "list", "--workflow", f"{name}.yml", "--status", "completed", "--limit", "2", "--json", "conclusion,url")
    try: last = json.loads(r.stdout or "[]")
    except ValueError: last = []
    if len(last) >= 2 and all(x.get("conclusion") == "failure" for x in last[:2]):
        raise_issue(title, f"The {name} job ({WHAT[name]}) failed twice in a row. Latest run: {url}")


def evening():
    today = NOW.astimezone(UK).date()
    load = lambda p, d: json.loads(p.read_text()) if p.exists() else d
    want = int(load(ROOT / "status" / "targets.json", {}).get(str(today))
               or load(ROOT / "config.json", {}).get("daily_limit", 24))
    went = 0
    for p in (ROOT / "status").glob("QD-*.json"):
        try: st = json.loads(p.read_text())
        except Exception: continue
        t = st.get("publish_at")
        if st.get("video") and t:
            when = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
            if when <= NOW and when.astimezone(UK).date() == today: went += 1
    day, title = f"{today:%A} {today.day} {today:%B}", "⚠️ Fewer Shorts went out than planned"
    if went < 0.7 * want:
        raise_issue(title, f"{day}: {went} of {want} Shorts went public on YouTube. Posts by day on the dashboard shows the "
                           f"detail: {REPO}/blob/main/review/README.md")
    else: clear(title, f"{day}: {went} of {want} went out.")
    fb = (load(ROOT / "status" / "social.json", {}) or {}).get("facebook") or {}
    exp, title = fb.get("data_access_expires"), "⚠️ The Facebook key needs renewing"
    if exp and str(exp).isdigit():
        left = (dt.datetime.fromtimestamp(int(exp), dt.timezone.utc) - NOW).days
        if left < 15:
            raise_issue(title, f"Facebook's key stops working in {max(left, 0)} days. Make a new one in the Graph API Explorer as "
                               f"before and paste it into the FB_PAGE_TOKEN secret: {REPO}/settings/secrets/actions")
        else: clear(title, "Renewed.")


def clips_money(root=None):
    """The clips' estimated earnings so far, the money page's sum: for each public clip over its campaign's minimum views,
    views / 1000 times the campaign's rate, each clip capped at the campaign's maximum; by campaign and in total."""
    import csv
    root = root or ROOT
    try: cfg = json.loads((root / "clips" / "campaigns.json").read_text()).get("campaigns") or {}
    except Exception: return 0.0, {}
    p = root / "clips" / "stats.csv"
    if not p.exists(): return 0.0, {}
    by, latest = {}, {}
    for r in csv.DictReader(p.open()):
        if r.get("privacy", "public") != "public": continue
        key = (r.get("clip"), r.get("video"))
        if key in latest and latest[key].get("as_of", "") > r.get("as_of", ""): continue
        latest[key] = r
    for r in latest.values():
        c = cfg.get(r.get("campaign") or "") or {}
        try: views = int(float(r.get("views") or 0))
        except ValueError: views = 0
        rate, minimum, cap = float(c.get("pay_per_1k") or 0), int(c.get("min_views") or 0), float(c.get("max_payout") or 0)
        if not rate or views < minimum: continue
        earned = views / 1000 * rate
        if cap: earned = min(earned, cap)
        by[r["campaign"]] = round(by.get(r["campaign"], 0.0) + earned, 2)
    return round(sum(by.values()), 2), by


def money():
    """Charlie (22 October): tell him when money is made. The clips' estimate (above) is noted in one issue, updated whenever it
    has risen by a dollar or more since the last note; the YouTube Partner Programme thresholds get their own note."""
    st = ROOT / "status" / "money.json"
    prev = json.loads(st.read_text()) if st.exists() else {}
    total, by = clips_money()
    title = "💰 Money: the clips have earned about ${:,.2f} so far (estimate)"
    noted = float(prev.get("clips_noted") or 0)
    if total >= noted + 1:
        old_title = prev.get("clips_title")
        lines = [f"- {cid}: ${amt:,.2f}" for cid, amt in sorted(by.items(), key=lambda x: -x[1])]
        body = (f"Estimated from views over each campaign's minimum at its rate (up ${total - noted:,.2f} since the last note). The platforms' "
                f"own figures are the truth: https://contentrewards.com/c/earnings and https://app.vyro.com/earnings; the page: "
                f"https://quickplay-studio.github.io/quickplay-autopilot/clips.html\n\n" + "\n".join(lines))
        have = open_issues()
        if old_title and old_title in have and old_title != title.format(total):
            gh("issue", "edit", str(have[old_title]), "--title", title.format(total)); gh("issue", "comment", str(have[old_title]), "--body", body)
            print("updated:", title.format(total))
        else: raise_issue(title.format(total), body)
        prev.update(clips_noted=total, clips_title=title.format(total), clips_by=by, noted_at=NOW.isoformat(timespec="minutes"))
    try: ypp = (json.loads((ROOT / "analytics" / "summary.json").read_text()).get("ypp") or {})
    except Exception: ypp = {}
    subs_ok, views_ok = float(ypp.get("subscribers_pct") or 0) >= 100, float(ypp.get("views_pct") or 0) >= 100
    if subs_ok and not prev.get("subs_noted"):
        raise_issue("🎉 1,000 subscribers: the first Partner Programme threshold", "Quickplay Daily has passed 1,000 subscribers. "
                    f"Shorts views in 90 days: {ypp.get('views_pct')}% of the 10 million needed."); prev["subs_noted"] = NOW.isoformat(timespec="minutes")
    if subs_ok and views_ok and not prev.get("ypp_noted"):
        raise_issue("🎉 Both Partner Programme thresholds reached: apply now", "1,000 subscribers and 10 million Shorts views in 90 days: "
                    "apply at https://studio.youtube.com (Earn). Before 1 February 2027 the view threshold is still 10 million."); prev["ypp_noted"] = NOW.isoformat(timespec="minutes")
    st.parent.mkdir(exist_ok=True); st.write_text(json.dumps(prev, indent=1))
    print(f"money: clips about ${total:,.2f} (noted ${noted:,.2f}); subscribers {ypp.get('subscribers_pct')}%, views {ypp.get('views_pct')}%")


if __name__ == "__main__":
    if os.environ.get("EVENT") == "workflow_run": after_run()
    else:
        evening()
        try: money()
        except Exception as e: print("money:", str(e)[:120])
