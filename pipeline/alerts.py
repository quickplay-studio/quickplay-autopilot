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
        "analytics": "the stats and what works", "weekly": "the weekly long video", "clips": "the clips line",
        "policy": "the rule and law watch", "audit": "the identity guard"}
# How long each job may go without a successful run before it counts as silently stopped (a cron typo, a disabled
# schedule, a job that never finishes): the 23 October clips finding was a step that never ran for days.
STALE_HOURS = {"trends": 14, "write": 14, "render": 14, "publish": 4, "analytics": 6, "clips": 26, "policy": 50, "audit": 14,
               "engage": 14, "social": 26, "weekly": 200}
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
    try: import quota; chosen = quota.target()      # the chosen number a day (15 from 24 October), not the ceiling
    except Exception: chosen = load(ROOT / "config.json", {}).get("daily_limit", 24)
    want = int(load(ROOT / "status" / "targets.json", {}).get(str(today)) or chosen)
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
        try: ig = int(float(r.get("ig_views") or 0))
        except ValueError: ig = 0
        for v in (views, ig):              # each platform's post is submitted and paid on its own (YouTube, the Instagram Reel)
            if not rate or not v or v < minimum: continue
            earned = v / 1000 * rate
            if cap: earned = min(earned, cap)
            by[r["campaign"]] = round(by.get(r["campaign"], 0.0) + earned, 2)
    return round(sum(by.values()), 2), by


def usd_gbp():
    """Today's dollar to pound rate (European Central Bank via frankfurter, no key; open.er-api.com as the fallback),
    kept in status/fx.json for the hub. The campaigns pay in US dollars (Charlie, 23 October: show pounds too)."""
    import urllib.request
    p = ROOT / "status" / "fx.json"
    for url, pick in (("https://api.frankfurter.app/latest?from=USD&to=GBP", lambda d: d["rates"]["GBP"]),
                      ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["GBP"])):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Quickplay/1.0"}), timeout=20) as r:
                rate = float(pick(json.loads(r.read().decode())))
            if 0.3 < rate < 2:
                p.write_text(json.dumps({"usd_gbp": rate, "at": NOW.isoformat(timespec="minutes"), "source": url.split("/")[2]}))
                return rate
        except Exception: continue
    try: return float(json.loads(p.read_text())["usd_gbp"])
    except Exception: return None


def money():
    """Charlie (22 October): tell him when money is made. The clips' estimate (above) is noted in one issue, updated whenever it
    has risen by a dollar or more since the last note; the YouTube Partner Programme thresholds get their own note."""
    st = ROOT / "status" / "money.json"
    prev = json.loads(st.read_text()) if st.exists() else {}
    total, by = clips_money()
    rate = usd_gbp()
    title = "💰 Money: the clips have earned about ${:,.2f} so far (estimate)"
    gbp = lambda usd: f" (about £{usd * rate:,.2f})" if rate else ""
    noted = float(prev.get("clips_noted") or 0)
    if total >= noted + 1:
        old_title = prev.get("clips_title")
        lines = [f"- {cid}: ${amt:,.2f}{gbp(amt)}" for cid, amt in sorted(by.items(), key=lambda x: -x[1])]
        body = (f"Estimated from views over each campaign's minimum at its rate (up ${total - noted:,.2f}{gbp(total - noted)} since the last "
                f"note; {('$1 = £' + format(rate, '.4f') + ' today') if rate else 'no exchange rate today'}). The platforms' "
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


def stale_check():
    """An issue for every job with no successful run inside its STALE_HOURS (closed again once it runs)."""
    for name, hours in STALE_HOURS.items():
        r = gh("run", "list", "--workflow", f"{name}.yml", "--status", "success", "--limit", "1", "--json", "createdAt,url")
        try: last = (json.loads(r.stdout or "[]") or [None])[0]
        except ValueError: continue
        title = f"⚠️ {name} has not run successfully for over {hours} hours ({WHAT.get(name, name)})"
        when = dt.datetime.fromisoformat(last["createdAt"].replace("Z", "+00:00")) if last else None
        if when is None or (NOW - when).total_seconds() > hours * 3600:
            raise_issue(title, f"Last successful {name} run: {last['url'] + ' at ' + last['createdAt'] if last else 'none found'}. "
                               "Its schedule may have stopped or every run is failing.")
        else: clear(title, f"Ran successfully at {last['createdAt']}.")


def funnel_check():
    """The day's funnel (pipeline/funnel.py): an issue naming any stage that got nothing while the one before it had work."""
    import funnel
    f = funnel.run()
    title = "⚠️ A pipeline stage is stuck"
    if f["stuck"]:
        lost = "; ".join(f"{k} ({v})" for k, v in (f.get("lost") or {}).items())
        raise_issue(title, f"{f['day']}: " + "; ".join(f["stuck"]) + ". Stage counts: " +
                    ", ".join(f"{k} {v}" for k, v in f["stages"].items() if k not in ("day", "stuck")) + (f". Lost: {lost}." if lost else "")
                    + " The hub's Overview shows the funnel.")
    else: clear(title, f"{f['day']}: every stage moved.")


if __name__ == "__main__":
    if os.environ.get("EVENT") == "workflow_run": after_run()
    else:
        evening()
        try: funnel_check()
        except Exception as e: print("funnel:", str(e)[:160])
        try: stale_check()
        except Exception as e: print("stale:", str(e)[:160])
        try: money()
        except Exception as e: print("money:", str(e)[:120])
