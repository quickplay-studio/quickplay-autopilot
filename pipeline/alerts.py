"""Alerts (Charlie, 19 October): a GitHub issue when something needs a look, so the GitHub app on his phone tells him,
and nothing otherwise. Run by .github/workflows/alerts.yml:
- after a main job fails (a runner starts only for failures since 24 October): two failures in a row open an issue for
  that job; every 2 hours recovered() closes it once the job's latest run has succeeded;
- each evening (21:30 UTC): an issue if under 70% of the day's Shorts went public on YouTube, and one if the Facebook
  key runs out within 14 days; each closes again once things are fine;
- retention falling (trend_alert, 26 October) and a recipe that has not refreshed (recipe_stale_check, also 2-hourly).
Issues carry the label "alert", one per problem, updated rather than repeated.
  python pipeline/alerts.py         (EVENT=workflow_run with RUN_NAME, RUN_CONCLUSION and RUN_URL, or the evening check)
"""
import datetime as dt, json, os, pathlib, re, subprocess
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


# Labels an issue can carry besides "alert". "needs-charlie" (24 October): only Charlie can do it (a key, a login, a
# sign-in outside the studio); the hub's Overview lists those issues under "Your actions this week".
LABELS = {"needs-charlie": ("FBCA04", "Only Charlie can do this: the hub lists it under Your actions this week")}


def raise_issue(title, body, labels=None, howto=None):
    """Opens the issue (or comments on the open one with this title). Returns its number, None when GitHub didn't say.
    howto: the footer of a new issue (default HOWTO; "" for none)."""
    have = open_issues()
    extra = [l for l in (labels or []) if l]
    for l in extra:                     # creating a label that exists already fails quietly, as it does for "alert"
        color, about = LABELS.get(l, ("BFD4F2", "Quickplay automation"))
        gh("label", "create", l, "--color", color, "--description", about)
    if title in have:
        gh("issue", "comment", str(have[title]), "--body", body)
        for l in extra: gh("issue", "edit", str(have[title]), "--add-label", l)
        print("updated:", title); return have[title]
    gh("label", "create", "alert", "--color", "B60205", "--description", "Automatic alert from the Quickplay automation")
    foot = HOWTO if howto is None else howto
    r = gh("issue", "create", "--title", title, "--body", body + (("\n\n" + foot) if foot else ""), "--label", "alert",
           *[x for l in extra for x in ("--label", l)])
    print("opened:", title, (r.stdout or r.stderr).strip())
    m = re.search(r"/issues/(\d+)", r.stdout or "")
    return int(m.group(1)) if m else None


def clear(title, body):
    have = open_issues()
    if title in have:
        gh("issue", "close", str(have[title]), "--comment", body); print("closed:", title)


# Helpers for the live action list and the key health (pipeline/actions.py, pipeline/keys.py; 24 October). They talk to
# GitHub only through gh(), so a test stubs that one function.
def issue_info(number):
    """{"state": "OPEN" or "CLOSED", "closed_at", "reason", "url"} for an issue, or None when GitHub can't say (the
    network, a bad token, an issue that is gone): callers then change nothing."""
    r = gh("issue", "view", str(number), "--json", "state,closedAt,stateReason,url")
    try: j = json.loads(r.stdout or "")
    except ValueError: return None
    if not isinstance(j, dict) or j.get("state") not in ("OPEN", "CLOSED"): return None
    return {"state": j["state"], "closed_at": j.get("closedAt") or "", "reason": j.get("stateReason") or "", "url": j.get("url") or ""}


def close_issue(number, comment):
    gh("issue", "close", str(number), "--comment", comment)


def issues_with(label):
    """The open issues carrying a label: [{"number", "title", "body"}]. None when GitHub can't say (so a caller never takes
    "could not read" for "there are none")."""
    r = gh("issue", "list", "--label", label, "--state", "open", "--json", "number,title,body", "--limit", "100")
    if getattr(r, "returncode", 0): return None
    try: out = json.loads(r.stdout or "[]")
    except ValueError: return None
    return [i for i in out if isinstance(i, dict) and "number" in i] if isinstance(out, list) else None


def after_run():
    name, concl, url = os.environ.get("RUN_NAME", ""), os.environ.get("RUN_CONCLUSION", ""), os.environ.get("RUN_URL", "")
    if name not in WHAT: return
    title = f"⚠️ {name} is failing ({WHAT[name]})"
    if concl == "success": clear(title, f"Working again: {url}"); return
    if concl not in FAILED: return
    r = gh("run", "list", "--workflow", f"{name}.yml", "--status", "completed", "--limit", "2", "--json", "conclusion,url")
    try: last = json.loads(r.stdout or "[]")
    except ValueError: last = []
    if len(last) >= 2 and all(x.get("conclusion") in FAILED for x in last[:2]):
        raise_issue(title, f"The {name} job ({WHAT[name]}) failed twice in a row. Latest run: {url}")


FAILED = ("failure", "timed_out", "startup_failure")
RECOVERY_CRON = "40 */2 * * *"


def recovered():
    """Every 2 hours (alerts.yml): each open "is failing" issue whose job's latest finished run succeeded is closed. Since
    24 October a successful run no longer starts this workflow (a runner only for failures), so the success that closes
    an issue is looked up here instead of arriving as an event."""
    for title in list(open_issues()):
        m = re.match(r"⚠️ (\S+) is failing \(", title)
        if not m or m.group(1) not in WHAT: continue
        r = gh("run", "list", "--workflow", f"{m.group(1)}.yml", "--status", "completed", "--limit", "1", "--json", "conclusion,url")
        try: last = (json.loads(r.stdout or "[]") or [None])[0]
        except ValueError: continue
        if last and last.get("conclusion") == "success": clear(title, f"Working again: {last.get('url', '')}")


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
                               f"before and paste it into the FB_PAGE_TOKEN secret: {REPO}/settings/secrets/actions",
                        labels=["needs-charlie"])
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


def reach_alert():
    """Clips that YouTube shows to nobody (clips/reach.json, from the nightly clip stats): one issue naming the channels where
    8 or more clips a day old have 70% with no views or under 5 views a clip, or where YouTube rejected, blocked or
    age-restricted clips,
    with what to look at in Studio. Closed again once every channel is seen. (24 October: 34 clips, 11 views.)"""
    try: r = json.loads((ROOT / "clips" / "reach.json").read_text())
    except Exception: return
    title = "📉 YouTube is showing the clips to almost nobody"
    bad = {ch: c for ch, c in (r.get("channels") or {}).items()
           if c.get("unseen") or c.get("rejected") or c.get("blocked") or c.get("age_restricted") or c.get("for_kids")}
    if not bad: clear(title, f"Clips are being seen again ({r.get('as_of')})."); return
    lines = []
    for ch, c in bad.items():
        why = [f"{c[k]} {label}" for k, label in (("rejected", "rejected by YouTube"), ("blocked", "blocked in some countries (usually a copyright claim)"),
                                                   ("age_restricted", "age restricted"), ("for_kids", "marked made for kids")) if c.get(k)]
        lines.append(f"- {ch}: {c['no_views']} of {c['public_a_day_old']} clips a day old have no views ({c['views']} views in all)"
                     + (f"; {', '.join(why)}" if why else ""))
    raise_issue(title, "From the nightly clip stats (clips/reach.json):\n" + "\n".join(lines) + "\n\nWhat to look at (2 minutes): "
                "open https://studio.youtube.com, switch to the channel (your picture, top right > Switch account), Content > Shorts, "
                "and read the Restrictions column: Copyright means a claim (the campaign footage is matched; the campaign's "
                "permission letter or its own upload settles it), Reused content means YouTube sees no change from the original "
                "(the spoken take started on 24 October to answer that). Nothing listed and still no views usually means a brand-new "
                "channel posting many clips at once; fewer clips spread through the day is the change to test.")


RECIPE_STALE_HOURS = 16     # the full analytics run comes with the three trends runs a day (08:10, 12:47, 18:23 UTC)


def recipe_stale_check():
    """The recipe (analytics/insights.md, drivers.csv, looks.json: the full analytics run inside trends.yml) has not refreshed
    for RECIPE_STALE_HOURS. trends.yml carries on when analytics.py fails ("analytics failed" in its log), so the writer would
    keep following yesterday's data with no other sign. One issue, closed once a full run lands (summary.json full_updated)."""
    title = f"⚠️ The recipe has not refreshed for over {RECIPE_STALE_HOURS} hours (the full analytics run inside trends)"
    try: s = json.loads((ROOT / "analytics" / "summary.json").read_text())
    except Exception: return
    at = s.get("full_updated") or s.get("updated")
    try: when = dt.datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except (TypeError, ValueError): return
    if when.tzinfo is None: when = when.replace(tzinfo=dt.timezone.utc)
    age = (NOW - when).total_seconds() / 3600
    if age > RECIPE_STALE_HOURS:
        raise_issue(title, f"analytics/summary.json says the last full analytics run was {at} ({age:.0f} hours ago). The trends "
                           "workflow runs `python pipeline/analytics.py` three times a day and carries on when it fails, so read the "
                           "analytics step in the latest trends run's log. Until a full run lands, the writer follows the last recipe it had.")
    else: clear(title, f"A full analytics run landed at {at}.")


def trend_alert():
    """Retention falling (26 October): the drivers judge each choice against the Shorts around it, so a change that sinks every
    Short alike (a render or voice change on every Short, a YouTube shift) never shows there. trend.falling compares the last
    3 days' Shorts with the 7 days before them on the share viewed and engaged views; a fall of 15% or more opens one issue
    with the numbers and the ledger's changes of the last 10 days as the suspects, for the weekly review and Charlie's phone.
    Nothing is reverted by itself (a topic lull can look the same for a day or two); the issue closes when retention recovers."""
    import trend
    title = "📉 Retention is falling: viewers leave the Shorts sooner than last week"
    fell = trend.falling(trend.load_rows(), NOW)
    if not fell: clear(title, "Retention is back level with the week before."); return
    lines = [f"- {label}: {a} over the last {n} Shorts ({trend.RECENT_DAYS} days), {b} over the {m} Shorts of the 7 days before"
             for label, a, b, n, m in fell]
    sus = trend.recent_changes(now=NOW)
    body = ("From analytics/shorts.csv (Shorts public 24 hours or more):\n" + "\n".join(lines)
            + "\n\nChanges of the last 10 days (analytics/changes.csv), the suspects:\n"
            + ("\n".join(f"- {r.get('id')} {r.get('date')} {r.get('area')}: {str(r.get('change'))[:140]}" for r in sus) if sus else "- none recorded")
            + "\n\nWhat happens next: the weekly review compares the Shorts since each change with the ones before and reverts what "
              "hurt (REVIEW.md step 2). A fall that lasts needs that look; one that closes by itself was the topics of the day.")
    raise_issue(title, body, howto="")


if __name__ == "__main__":
    if os.environ.get("EVENT") == "workflow_run": after_run()
    elif os.environ.get("SCHEDULE") == RECOVERY_CRON:
        recovered()
        try: recipe_stale_check()
        except Exception as e: print("recipe:", str(e)[:160])
    else:
        evening()
        try: trend_alert()
        except Exception as e: print("trend:", str(e)[:160])
        try: recipe_stale_check()
        except Exception as e: print("recipe:", str(e)[:160])
        try: funnel_check()
        except Exception as e: print("funnel:", str(e)[:160])
        try: stale_check()
        except Exception as e: print("stale:", str(e)[:160])
        try: money()
        except Exception as e: print("money:", str(e)[:120])
        try: reach_alert()
        except Exception as e: print("reach:", str(e)[:120])
