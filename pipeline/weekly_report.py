"""The weekly report (Charlie, 21 October): every Monday morning, what changed, what the data says works, whether the
optimisation is working as more is posted, what was stopped, and the clips channel's money. Written to analytics/weekly.md
and opened as a GitHub issue (label "weekly"), which the GitHub app shows on Charlie's phone.
  python pipeline/weekly_report.py          (REPORT_ISSUE=0: the file only)
Sources: analytics/shorts.csv, hourly.csv, daily.csv, drivers.csv, decisions.csv, changes.csv, summary.json; clips/stats.csv,
campaigns.json, submit.csv, insights.json; the dated headings of docs/NEXT.md and docs/CLIPS.md (what was built).
"""
import csv, datetime as dt, json, os, pathlib, re, statistics, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
UK = ZoneInfo("Europe/London")
NOW = dt.datetime.now(dt.timezone.utc)
WEEK = dt.timedelta(days=7)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
PAGES = "https://quickplay-studio.github.io/quickplay-autopilot/"
REPO = "https://github.com/quickplay-studio/quickplay-autopilot"


def f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def rows_of(path):
    p = ROOT / path
    return list(csv.DictReader(p.open())) if p.exists() else []


def when(r, key="posted"):
    try: return dt.datetime.fromisoformat(str(r.get(key)).replace("Z", "+00:00"))
    except (TypeError, ValueError): return None


def uk_day(d):
    return d.astimezone(UK).strftime("%A %-d %B")


def n(x): return f"{round(x):,}"


def med(vals):
    v = [x for x in vals if x is not None]
    return statistics.median(v) if v else None


def week_views(hourly, start, end):
    """YouTube views gained between two times, from the hourly totals (the latest total inside the window minus the
    latest before it)."""
    pts = [(when(r, "hour_utc"), f(r.get("yt_total"))) for r in hourly]
    pts = [(t, v) for t, v in pts if t and v is not None]
    before = [v for t, v in pts if t < start]; inside = [v for t, v in pts if start <= t <= end]
    if not inside: return None
    return inside[-1] - (before[-1] if before else inside[0])


def verdicts():
    out = {}
    for r in rows_of("analytics/drivers.csv"):
        out.setdefault(r.get("feature"), {})[r.get("value")] = r.get("verdict")
    return out


def followed(r, v):
    """Whether a Short's choices follow the data: at least one "push" choice and no "cut back" or "stop" one (trend.followed,
    the same measure insights.md counts every day since 26 October)."""
    import trend
    return trend.followed(r, v)


def built(start, end):
    """Dated headings of the build logs inside the week: what was changed in the design."""
    out = []
    for name in ("docs/NEXT.md", "docs/CLIPS.md"):
        p = ROOT / name
        if not p.exists(): continue
        for line in p.read_text().splitlines():
            m = re.match(r"^##+\s+(?:.*?\b)?(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December)\b(.*)$", line)
            if not m: continue
            try: d = dt.datetime(NOW.year, MONTHS[m.group(2).lower()], int(m.group(1)), 12, tzinfo=dt.timezone.utc)
            except ValueError: continue
            if start - dt.timedelta(hours=12) <= d <= end:
                title = re.sub(r"^[\s:,]+", "", m.group(3)).strip() or line.lstrip("# ").strip()
                out.append(f"{m.group(1)} {m.group(2)}: {title}")
    return out


def ledger_lines(start, end):
    """The change ledger's verdicts that came due this week, the open trade-offs, and how often the automatic recipe's
    calls held up (pipeline/changes.py)."""
    try:
        import changes as C
        rows = C.load()
    except Exception as e:
        return [f"- The change ledger could not be read ({type(e).__name__})."]
    mine, auto = C.due(start.date(), end.date(), rows)
    out = [f"- {r['id']} ({r['date']}, {r['area']}): {r['change']}: **{r.get('verdict') or 'not checked yet'}**. {r.get('result', '')}".rstrip()
           for r in mine] or ["- No change came due for its check this week."]
    trade = C.open_tradeoffs(rows)
    if trade: out.append("- Open trade-offs (keep or revert each: python pipeline/changes.py set <id> --status kept): "
                         + "; ".join(f"{r['id']} {r['change'][:60]}" for r in trade) + ".")
    right, wrong, level = C.calls_record(auto)
    if right or wrong or level:
        out.append(f"- The writer's automatic recipe: {right + wrong + level} of its calls came due; {right} held up, {wrong} faded or "
                   f"recovered (the data was chasing noise), {level} were level." + (f" Right {right / (right + wrong):.0%} of the time." if right + wrong else ""))
    waiting = [r for r in rows if r.get("status") == "live" and r.get("by") != C.AUTO]
    if waiting:
        nxt = min(r.get("check_on", "") for r in waiting)
        out.append(f"- {len(waiting)} changes still waiting for their after-week; the next check is on {nxt}.")
    return out


def main():
    import drivers
    end = NOW; start = end - WEEK; prev = start - WEEK
    shorts = [r for r in rows_of("analytics/shorts.csv") if (r.get("channel") or "main") == "main"]      # the main channel's week
    hourly = rows_of("analytics/hourly.csv")
    v = verdicts()
    this = [r for r in shorts if when(r) and start <= when(r) <= end]
    last = [r for r in shorts if when(r) and prev <= when(r) < start]
    views = lambda rs: [f(r.get("views_24h")) if f(r.get("views_24h")) is not None else f(r.get("yt_views")) for r in rs
                        if when(r) and when(r) <= end - dt.timedelta(hours=24)]        # a day old at least, so the figure is fair
    try: summ = json.loads((ROOT / "analytics" / "summary.json").read_text())
    except Exception: summ = {}
    yt = summ.get("youtube") or {}; ypp = summ.get("ypp") or {}
    L = [f"# Quickplay weekly: {uk_day(start)} to {uk_day(end)}", ""]
    gained, gained_prev = week_views(hourly, start, end), week_views(hourly, prev, start)
    L += ["## The week in numbers",
          f"- Shorts posted: {len(this)} (the week before: {len(last)}).",
          f"- YouTube views gained: {n(gained) if gained is not None else 'no hourly data'}" + (f" (the week before: {n(gained_prev)})." if gained_prev is not None else "."),
          f"- Median views per Short, 24 hours after posting: {n(med(views(this))) if med(views(this)) is not None else 'none measured'}"
          + (f" (the week before: {n(med(views(last)))})." if med(views(last)) is not None else "."),
          f"- Subscribers: {yt.get('subscribers', '?')} of 1,000. YPP: {n(f(yt.get('views_last_90_days')) or 0)} of 10,000,000 Shorts views in 90 days, "
          f"about {n(f(ypp.get('views_needed_per_day') or ypp.get('needed_per_day') or (rows_of('analytics/progress.csv') or [{}])[-1].get('needed_per_day')) or 0)} a day needed from now, "
          f"apply before {ypp.get('apply_before', '2027-02-01')} ({ypp.get('days_left', '?')} days)."]
    for ch, c in sorted((summ.get("channels") or {}).items()):         # the Daily line's other channels (25 October), apart from the figures above
        L.append(f"- Channel {ch}: {c.get('public_shorts', 0)} Shorts public, {n(c.get('views_all_time') or 0)} views in all, "
                 f"{c.get('subscribers') if c.get('subscribers') is not None else '?'} subscribers (analytics/shorts.csv channel column).")
    best = sorted(this, key=lambda r: -(f(r.get("yt_views")) or 0))[:3]
    if best:
        L.append("- Best this week: " + "; ".join(f"{r.get('short') or 'Short'} \"{r.get('title', '')}\" {n(f(r.get('yt_views')) or 0)} views ({r.get('category')}, {r.get('format')}, {r.get('hook_type') or drivers.hook_type(r.get('hook'))} hook)" for r in best) + ".")
    # is the optimisation working
    L += ["", "## Is the optimisation working"]
    fol = [r for r in this if followed(r, v)]; rest = [r for r in this if r not in fol]
    fol_prev = [r for r in last if followed(r, v)]
    if fol and rest and med(views(fol)) is not None and med(views(rest)) is not None:
        ratio = med(views(fol)) / med(views(rest)) if med(views(rest)) else None
        L.append(f"- Shorts that followed the data's rulings: {len(fol)} of {len(this)} this week ({len(fol_prev)} of {len(last)} the week before); "
                 f"their median views {n(med(views(fol)))} against {n(med(views(rest)))} for the rest" + (f" ({ratio:.1f}x)." if ratio else "."))
    else:
        L.append(f"- Shorts that followed the data's rulings: {len(fol)} of {len(this)}; not enough of both kinds yet to compare.")
    counts = {k: sum(1 for feat in v.values() for x in feat.values() if x == k) for k in ("push", "cut back", "pause", "stop", "retest")}
    L.append(f"- Rulings in force: {counts['push']} push, {counts['cut back']} cut back, {counts['pause'] + counts['stop']} paused, "
             f"{counts['retest']} being retested (analytics/drivers.csv).")
    dec = [r for r in rows_of("analytics/decisions.csv") if r.get("date") and start.date() <= dt.date.fromisoformat(r["date"]) <= end.date()]
    L += ["", "## What changed this week"]
    moves = [r for r in dec if not r["change"].startswith("Back to normal")]
    quiet = len(dec) - len(moves)
    L += [f"- {r['date']}: {r['change']} ({r['why']})." for r in moves[:20]] or ["- No ruling changed from the data this week."]
    if len(moves) > 20: L.append(f"- and {len(moves) - 20} more in analytics/decisions.csv.")
    if quiet: L.append(f"- {quiet} earlier rulings went back to normal as more Shorts came in (a choice is only kept while the data still says so).")
    b = built(start, end)
    L += [f"- Built: {x}" for x in b] or ["- No design change this week (docs/NEXT.md, docs/CLIPS.md)."]
    L += ["", "## Did the changes work (analytics/changes.csv)"] + ledger_lines(start, end)
    # stopped
    stops = [r for r in rows_of("analytics/drivers.csv") if r.get("verdict") in ("pause", "stop", "retest")]
    dead = drivers.dead(shorts)
    L += ["", "## Paused (little to no views a week on: left out for 14 days, then retested)"]
    L += [f"- {r['feature_label']} \"{r['value']}\" ({r['verdict']}): {r['why']}." for r in stops] or ["- No choice has failed outright yet."]
    if dead: L.append("- Dead Shorts (not followed up, remade or posted about again): " + "; ".join(f"{r['short']} \"{r.get('title', '')}\" {n(f(r.get('yt_views')) or 0)} views" for r in dead[:12]) + ("…" if len(dead) > 12 else "") + ".")
    floor = drivers.dead_floor(shorts)
    L.append(f"- The floor: {n(floor)} views a week after posting." if floor else "- The floor is set once 5 Shorts are a week old.")
    # what is measured
    L += ["", "## What every Short is measured on",
          "- Choices recorded per Short: " + ", ".join(label.lower() for _, label in drivers.FEATURES) + ".",
          "- Results: views at 1, 3, 6, 12, 24, 48 and 72 hours, views against the Shorts posted around the same time, still watching at 3 seconds, "
          "average viewed, engaged views, likes, shares and subscribers per 1,000 views, traffic sources and search terms, countries, the retention curve's worst beat.",
          "- Clips: layout, captions, punch-in, length, title, campaign; views, likes and comments per clip, estimated money per campaign."]
    # clips
    cst = rows_of("clips/stats.csv")
    try: camp = json.loads((ROOT / "clips" / "campaigns.json").read_text()).get("campaigns") or {}
    except Exception: camp = {}
    pub = [r for r in cst if r.get("privacy") == "public"]
    money, money_rows = 0.0, []
    for cid, c in camp.items():
        rs = [r for r in pub if r.get("campaign") == cid]
        if not rs: continue
        vv = sum(f(r.get("views")) or 0 for r in rs)
        earned = sum((f(r.get("views")) or 0) / 1000 * f(c.get("pay_per_1k") or 0) for r in rs if (f(r.get("views")) or 0) >= f(c.get("min_views") or 0))
        if f(c.get("max_payout")): earned = min(earned, f(c.get("max_payout")))
        money += earned; money_rows.append(f"{c.get('subject', cid)} {len(rs)} clips, {n(vv)} views, ${earned:,.2f}")
    subs = [r for r in rows_of("clips/submit.csv") if r.get("submitted") and not r["submitted"].startswith(("failed", "expired")) and r["submitted"] != "pulled"]
    try: cins = json.loads((ROOT / "clips" / "insights.json").read_text()).get("tests") or {}
    except Exception: cins = {}
    bests = {t: x.get("best") for t, x in cins.items() if x.get("best")}
    L += ["", "## Quickplay Clips",
          f"- {len(pub)} clips public, {n(sum(f(r.get('views')) or 0 for r in pub))} views, about ${money:,.2f} earned so far (estimate), "
          f"{len(subs)} submissions made, {sum(1 for c in camp.values() if c.get('active'))} campaigns active.",
          ("- By campaign: " + "; ".join(money_rows) + ".") if money_rows else "- No public clips yet.",
          ("- Winning forms: " + ", ".join(f"{t} {a}" for t, a in bests.items()) + ".") if bests else "- No form has won yet (3 clips an arm, a day old, 10% ahead)."]
    L += ["", f"Pages: [clips dashboard]({PAGES}clips.html), [what's working]({REPO}/blob/main/analytics/insights.md), "
          f"[every ruling]({REPO}/blob/main/analytics/decisions.csv), [what drives views]({REPO}/blob/main/analytics/drivers.csv)."]
    text = "\n".join(L) + "\n"
    pathlib.Path(os.environ.get("REPORT_OUT") or ROOT / "analytics" / "weekly.md").write_text(text)
    print(text)
    if os.environ.get("REPORT_ISSUE", "1") != "0": issue(f"📊 Weekly: {uk_day(start)} to {uk_day(end)}", text)


def issue(title, body):
    import alerts
    r = alerts.gh("issue", "list", "--label", "weekly", "--state", "open", "--json", "number,title", "--limit", "20")
    try: have = {i["title"]: i["number"] for i in json.loads(r.stdout or "[]")}
    except ValueError: have = {}
    if title in have:
        alerts.gh("issue", "comment", str(have[title]), "--body", body); print("updated:", title); return
    for num in have.values(): alerts.gh("issue", "close", str(num), "--comment", "Replaced by this week's report.")
    alerts.gh("label", "create", "weekly", "--color", "0E8A16", "--description", "The Monday report from the Quickplay automation")
    r = alerts.gh("issue", "create", "--title", title, "--body", body, "--label", "weekly")
    print("opened:", title, (r.stdout or r.stderr).strip())


if __name__ == "__main__":
    main()
