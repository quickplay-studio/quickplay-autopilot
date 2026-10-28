"""The hub inside GitHub (Charlie, 28 October: "see my hub inside GitHub itself, repo private, nothing external").
Writes README.md, the repo's front page, which GitHub renders natively (GitHub shows .html as source, so docs/hub.html cannot be
read there). It reads the same files docs/hub.html reads and keeps to one screen or two:
actions, YPP progress, is it getting better (a mermaid line), tests and changes, keys, channels, links.
Rebuilt by analytics.yml every hour (its commit adds README.md) and by audit.yml after the key check.

  python pipeline/hub_md.py          write README.md
  python pipeline/hub_md.py -        print it instead

Rules: every section fails soft (a missing or malformed file gives one "Not available yet." line); nothing secret is ever
printed (only names, states and dates from status/keys.json, never a value; any token-looking string is hidden); no em or en
dashes; open needs-charlie issues are read with `gh` only when GH_TOKEN is set (analytics.yml and audit.yml set it)."""
import csv, collections, datetime as dt, json, math, os, pathlib, re, shutil, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from digest import load, UK          # digest.load: a JSON file, or {} when it is missing or broken

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO = "quickplay-studio/quickplay-autopilot"
GH = f"https://github.com/{REPO}"
NEW_SECRET = f"{GH}/settings/secrets/actions/new"
NA = "Not available yet."
DASH = re.compile("\\s*[\\u2013\\u2014]\\s*")
DASH_NUM = re.compile("(?<=\\d)[\\u2013\\u2014](?=\\d)")
# anything shaped like a key: a known vendor prefix, or 32+ characters mixing letters and digits
SECRETISH = re.compile(r"\b(?:sk-|ghp_|gho_|ghs_|github_pat_|xox[bap]-|AIza|gsk_|ya29\.)[A-Za-z0-9_\-.]{8,}"
                       r"|(?<![A-Za-z0-9_\-])(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{32,}(?![A-Za-z0-9_\-])")
URL = re.compile(r"https?://[^\s<>)\"']+")


# ---------- small helpers ----------
def jd(root, rel):
    d = load(root / rel); return d if isinstance(d, dict) else {}


def jl(root, rel):
    return load(root / rel)


def rows(root, rel):
    try:
        with (root / rel).open(newline="", encoding="utf-8") as f: return list(csv.DictReader(f))
    except Exception: return []


def num(v, d=None):
    try: return float(str(v).replace(",", "")) if str(v).strip() != "" else d
    except Exception: return d


def fmt(v): return "n/a" if v is None else f"{int(round(v)):,}"


def pct(a, b):
    if a is None or not b: return "n/a"
    p = 100 * a / b
    return f"{p:.2f}%" if p < 10 else f"{p:.0f}%"


def scrub(s): return SECRETISH.sub("[hidden]", s)


def dashes(s): return DASH.sub(" - ", DASH_NUM.sub("-", s))


def clean(s, k=0):
    """One safe line of table or list text."""
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    s = dashes(scrub(s)).replace("|", "/").replace("`", "'").replace("*", "\\*").replace("[", "(").replace("]", ")")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    return s if not k or len(s) <= k else s[:k - 3].rsplit(" ", 1)[0] + "..."


def day(s):
    try: d = dt.date.fromisoformat(str(s)[:10]); return f"{d:%a} {d.day} {d:%b}"
    except Exception: return ""


def stamp(s, now):
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo is None: t = t.replace(tzinfo=dt.timezone.utc)
        t = t.astimezone(UK); return f"{t:%a} {t.day} {t:%b}, {t:%H:%M} UK"
    except Exception: return ""


def link(text, url): return f"[{text}]({url})"


def last_value(vals, back=7):
    """(latest non-null value, the value `back` entries earlier or None) of a list that ends in nulls while YouTube catches up."""
    idx = [i for i, v in enumerate(vals or []) if v is not None]
    if not idx: return None, None, None
    i = idx[-1]; return vals[i], (vals[i - back] if i >= back else None), i


# ---------- sections: each returns a list of lines, or None for "not available yet" ----------
def sec_actions(root, now, issues, facts):
    raw = jl(root, "status/actions.json")
    items = raw if isinstance(raw, list) else (raw.get("items") if isinstance(raw, dict) else None)
    if items is None and issues is None: return None
    items = [a for a in (items or []) if isinstance(a, dict)]
    today = now.astimezone(UK).date(); week = today + dt.timedelta(days=7)
    linked = {int(a["issue"]) for a in items if str(a.get("issue", "")).isdigit()}
    out, later = [], []
    for i in issues or []:
        try:
            if int(i["number"]) in linked: continue
            out.append(f"- [ ] **{clean(i['title'], 90)}** (alert, opened {day(i.get('createdAt'))}): {link('issue #' + str(i['number']), i['url'])}")
        except Exception: continue
    def key(a): return "0" if a.get("repeat") else (a.get("due") or "9999")
    for a in sorted((a for a in items if not a.get("done")), key=key):
        due = str(a.get("due") or "")
        try: d = dt.date.fromisoformat(due)
        except Exception: d = None
        when = (f"repeats {clean(a['repeat'])}" if a.get("repeat") else "optional" if not d else
                f"overdue, was due {day(due)}" if d < today else f"due {day(due)}")
        url = f"{GH}/issues/{int(a['issue'])}" if str(a.get("issue", "")).isdigit() else next(
            (l.get("url") for l in (a.get("links") or []) if isinstance(l, dict) and l.get("url")), f"{GH}/issues")
        text = link(f"issue #{a['issue']}" if str(a.get("issue", "")).isdigit() else "open", url)
        line = f"- [ ] **{clean(a.get('title'), 90)}** ({when}): {text}"
        (out if (a.get("repeat") or (d and d <= week)) else later).append(line)
    facts["actions"] = len(out)
    lines = out[:10] or ["- [x] Nothing needs you this week."]
    if len(out) > 10: lines.append(f"- and {len(out) - 10} more: {link('open issues', GH + '/issues?q=is%3Aopen+label%3Aneeds-charlie')}")
    if later: lines += ["", f"<details><summary>Coming up and optional ({len(later)})</summary>", ""] + later[:12] + ["", "</details>"]
    return lines


def sec_ypp(root, now, facts):
    prog = (rows(root, "analytics/progress.csv") or [{}])[-1]
    summ, im = jd(root, "analytics/summary.json"), jd(root, "analytics/improvement.json")
    yt, goal = summ.get("youtube") or {}, im.get("goal") or {}
    subs = num(prog.get("subscribers"), num(yt.get("subscribers")))
    v90 = num(prog.get("engaged_views_90d"), num(yt.get("views_last_90_days_estimate")))
    if subs is None and v90 is None: return None
    facts.update(subs=subs, v90=v90)
    tiers = [("Expanded, open now", goal.get("subs") or 500, goal.get("views") or 3_000_000),
             ("Full, from 1 February 2027", goal.get("subs_2027") or 1000, goal.get("shorts_pool_2027") or 10_000_000)]
    need = lambda g: fmt(math.ceil(max(g - v90, 0) / 90)) if v90 is not None else "n/a"
    out = ["| Tier | Subscribers | Shorts views, 90 days | Views a day needed |", "|---|---|---|---|"]
    for name, s, v in tiers:
        out.append(f"| {name} | {fmt(subs)} of {fmt(s)} ({pct(subs, s)}) | {fmt(v90)} of {fmt(v)} ({pct(v90, v)}) | {need(v)} |")
    facts["exp_pct"] = pct(v90, tiers[0][2])
    ed = [(d, v) for d, v in zip(im.get("days") or [], (im.get("channel") or {}).get("engaged_day") or []) if v is not None][-7:]
    ch = jd(root, "status/channel.json")
    left = (dt.date(2027, 2, 1) - now.astimezone(UK).date()).days
    out += ["", "| Engaged views, last 7 reported days | Views, last 24 hours | Uploads, last 24 hours | Days to 1 Feb 2027 |", "|---|---|---|---|",
            f"| {fmt(sum(v for _, v in ed)) if ed else 'n/a'}{' (to ' + day(ed[-1][0]) + ')' if ed else ''} | {fmt(num(prog.get('views_last_24h')))} | "
            f"{fmt(num(ch.get('uploads_last_24h')))} | {left} |",
            "", "The full tier also accepts 20M Shorts views in 90 days. YouTube reports engaged views about 3 days late."]
    return out


def better_extra(root, im):
    """Two lines for "Is it getting better" (28 October): the loop against the frozen control group (trend.loop_vs_control, in
    improvement.json) and the channel's sameness score with its alert level (analytics/sameness.csv, config.json sameness)."""
    out = []
    ctl = im.get("control") or {}
    if ctl.get("summary"):
        out.append("Loop vs frozen control: " + clean(ctl["summary"]) + ".")
    cfg = jd(root, "config.json").get("sameness") or {}
    mine = [r for r in rows(root, "analytics/sameness.csv") if (r.get("channel") or "main") == "main" and num(r.get("score")) is not None]
    if mine:
        r = sorted(mine, key=lambda r: r.get("day") or "")[-1]
        sc, share = num(r.get("score")), num(r.get("share"))
        out.append(f"Sameness, how alike the channel's Shorts are (0 to 1, lower is better): **{sc:.2f}** over {cfg.get('window_days', 14)} days to {day(r['day'])}, "
                   f"alert at {cfg.get('alert', 0.2):g}" + (f"; the commonest recipe is {100 * share:.0f}% of them (limit {100 * cfg.get('recipe_share_max', 0.35):.0f}%)." if share is not None else "."))
    return out


def sec_better(root):
    im = jd(root, "analytics/improvement.json")
    extra = better_extra(root, im)
    c = im.get("channel") or {}
    pts = [(d, v) for d, v in list(zip(im.get("days") or [], c.get("engaged_day") or []))[-14:] if v is not None]
    if not pts: return extra or None
    out = []
    cur, prev, _ = last_value(c.get("engaged_day_7d"))
    if cur is not None:
        out.append(f"Engaged views a day, 7-day average: **{fmt(cur)}**" + (f", {'up' if cur >= prev else 'down'} from {fmt(prev)} a week earlier." if prev is not None else "."))
    cur, prev, _ = last_value((((im.get("shorts") or {}).get("main") or {}).get("engaged_pct") or {}).get("week"))
    if cur is not None:
        out.append(f"Engaged share (Shorts that hold viewers past the opening, 7-day median): **{cur:g}%**" + (f", was {prev:g}% a week earlier." if prev is not None else "."))
    out += extra
    if out: out.append("")
    if len(pts) < 2: return out + ["Too few reported days for a line yet."]
    top = max(v for _, v in pts); step = 10 ** max(int(math.log10(top)) - 1, 0) if top > 0 else 1
    out += ["```mermaid", "xychart-beta", '    title "Engaged views a day, Quickplay Daily"',
            "    x-axis [" + ", ".join('"' + (day(d).split(" ", 1)[1]) + '"' for d, _ in pts) + "]",
            f'    y-axis "Views" 0 --> {int(math.ceil(top / step) * step)}',
            "    line [" + ", ".join(str(int(round(v))) for _, v in pts) + "]", "```",
            f"Days YouTube has reported, to {day(pts[-1][0])}. More: {link('analytics/insights.md', 'analytics/insights.md')}."]
    return out


def sec_tests(root):
    t, ev, led = jd(root, "analytics/tests.json"), jd(root, "analytics/evolve.json"), rows(root, "analytics/changes.csv")
    facts = t.get("factors") or {}
    if not facts and not led: return None
    out = []
    if facts:
        def rank(kv):
            f = kv[1]; return (0 if (f.get("leaning") or f.get("winner")) else 1 if f.get("verdict") != "too few to tell" else 2, num(f.get("days_left"), 99))
        live = sorted(facts.items(), key=rank)
        decided = sum(1 for f in facts.values() if f.get("leaning") or f.get("winner") or f.get("verdict") not in ("too few to tell", None))
        out += [f"**{len(facts)} contests live, {decided} with a lean or a verdict.** Evolve has {len(ev.get('champions') or {})} champions, "
                f"{len(ev.get('adopted') or {})} adopted genes and has tried {len(ev.get('genes') or {})} genes ({link('summary', 'analytics/evolve.md')}).", "",
                "| Contest | Arms (Shorts so far) | Verdict | Days left |", "|---|---|---|---|"]
        for k, f in live[:8]:
            arms = ", ".join(f"{clean(a, 24)} {fmt(num((v or {}).get('n'), 0))}" for a, v in list((f.get("arms") or {}).items())[:2])
            verdict = clean(f.get("verdict")) + (f", leaning {clean(f['leaning'])}" if f.get("leaning") else "") + (f", winner {clean(f['winner'])}" if f.get("winner") else "")
            out.append(f"| {clean(f.get('label') or k, 46)} | {arms} | {verdict} | {fmt(num(f.get('days_left')))} |")
    if led:
        rid = lambda r: int(re.sub(r"\D", "", r.get("id") or "0") or 0)
        done = sorted((r for r in led if r.get("verdict")), key=lambda r: (r.get("check_on") or "", rid(r)), reverse=True)[:8]     # the latest verdicts
        wait = sorted((r for r in led if not r.get("verdict") and "automatic" not in (r.get("by") or "")), key=rid, reverse=True)[:6]
        tally = collections.Counter(r["verdict"] for r in led if r.get("verdict"))
        out += ["", f"**Change ledger:** {len(led)} changes, {sum(1 for r in led if r.get('status') == 'live')} live; verdicts so far: "
                + (", ".join(f"{n} {v}" for v, n in tally.most_common()) or "none") + ".", "",
                "| Change | Date | What | Target | Verdict |", "|---|---|---|---|---|"]
        for r in done:
            out.append(f"| {clean(r.get('id'))} | {day(r.get('date'))} | {clean(r.get('change'), 80)} | {clean(r.get('target'))} | {clean(r.get('verdict'))} |")
        if wait: out += ["", "Waiting for a verdict (check day): " + ", ".join(f"{clean(r.get('id'))} ({day(r.get('check_on')) or 'soon'})" for r in wait) + f". All of them: {link('analytics/changes.csv', 'analytics/changes.csv')}."]
    return out


def fix_links(r, label):
    urls = [u.rstrip(".,;:") for s in (r.get("fix") or []) for u in URL.findall(str(s))]
    signup = next((u for u in urls if "/settings/secrets/" not in u), "")
    out = [link(label, signup)] if signup else []
    if any("/settings/secrets/" in u for u in urls) or re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", str(r.get("id"))): out.append(link("add secret", NEW_SECRET))
    return " / ".join(out) or link("audit", f"{GH}/actions/workflows/audit.yml")


def sec_keys(root, now, facts):
    k = jd(root, "status/keys.json")
    rs = [r for r in k.get("keys") or [] if isinstance(r, dict)]
    fl = jd(root, "status/freellm.json")
    if not rs and not fl: return None
    needs = lambda r: r.get("status") in ("failing", "expiring") or (r.get("status") == "missing" and r.get("needed"))
    bad = [r for r in rs if needs(r)]
    count = collections.Counter(r.get("status") for r in rs)
    facts["keys_bad"] = len(bad)
    out = [("**" + (f"{len(bad)} need fixing." if bad else "Nothing needs fixing.") + "**" + f" {count['ok']} ok, {count['expiring']} ending soon, {count['failing']} failing, "
            f"{count['missing']} not set up" + (f"; checked {stamp(k.get('checked'), now)}." if k.get("checked") else ".")), "",
           "| Key | State | Ends | Fix |", "|---|---|---|---|"]
    show = bad + [r for r in rs if r not in bad and r.get("status") == "ok" and r.get("expires") and r.get("id") != "freellm"]
    for r in show:
        st = r.get("status")
        end = clean(str(r.get("expires") or "")[:10]); end = (day(end) + f" {end[:4]}") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", end) else "none"
        out.append(f"| {clean(r.get('what'), 60)} | {clean(st)} | {end} | {'' if st == 'ok' else fix_links(r, 'fix' if st != 'missing' else 'sign up')} |")
    row = next((r for r in rs if r.get("id") == "freellm"), {})
    if fl or row:
        ok = bool(fl.get("ok")) if fl else row.get("status") == "ok"
        note = (f"{fmt(num(fl.get('models')))} models on {clean(', '.join(map(str, fl.get('chat_platforms') or [])) or 'no platform')}; search: {clean(', '.join(map(str, fl.get('search_engines') or [])) or 'none')}"
                if ok else clean(fl.get("reason") or row.get("detail") or "last start failed", 70) + " " + link("freellm check", f"{GH}/actions/workflows/freellm.yml"))
        out.append(f"| FreeLLMAPI router: {note} | {'live' if ok else 'failing'} | none | |")
    rest = [r for r in rs if r.get("status") == "ok" and r not in show and r.get("id") != "freellm"]
    if rest: out += ["", f"Also ok ({len(rest)}): " + ", ".join(clean(r.get("id")) for r in rest) + "."]
    opt = [r for r in rs if r.get("status") == "missing" and not needs(r)]
    if opt:
        groups = collections.OrderedDict()
        for r in opt: groups.setdefault(clean(r.get("group") or "Other"), []).append(r)
        out += ["", f"<details><summary>Optional keys not set up ({len(opt)})</summary>", ""]
        for g, lst in groups.items():
            out.append(f"- **{g}:** " + ", ".join(clean(r.get("id")) + (f" ({link('sign up', u)})" if (u := next((x.rstrip(".,;:") for x in URL.findall(" ".join(map(str, r.get("fix") or []))) if "/settings/secrets/" not in x), "")) else "") for r in lst))
        out += ["", f"Add any of them as an Actions secret: {link('new secret', NEW_SECRET)}.", "", "</details>"]
    return out


def sec_channels(root, now):
    cfg, keys = jd(root, "config.json"), jd(root, "status/keys.json")
    chans = collections.OrderedDict([("main", {"name": "Quickplay Daily", "per_day": num(jd(root, "status/volume.json").get("per_day"), num(cfg.get("shorts_per_day")))})])
    for k, v in (cfg.get("shorts_channels") or {}).items():
        if isinstance(v, dict): chans[k] = {"name": v.get("name") or k, "per_day": num(v.get("per_day"))}
    today = str(now.astimezone(UK).date())
    done = collections.Counter(r.get("channel") or "main" for r in rows(root, "analytics/shorts.csv") if r.get("posted_day") == today)
    state = {r.get("id"): r.get("status") for r in keys.get("keys") or [] if isinstance(r, dict)}
    words = {"ok": "sign-in ok", "failing": "sign-in failing", "expiring": "sign-in ending soon", "missing": "sign-in not set up"}
    out = []
    for k, v in chans.items():
        sid = "youtube" if k == "main" else f"youtube_{k}"
        s = state.get(sid) or (state.get("youtube") if k == "es" else None)
        of = f" of {fmt(v['per_day'])}" if v.get("per_day") else ""
        out.append(f"- **{clean(v['name'])}**: {done.get(k, 0)}{of} posted today, {words.get(s, 'no sign-in yet')}")
    if cfg.get("clips_paused"): out.append(f"- Clipping paused since {day(cfg['clips_paused'])}: the clip channels post original Shorts.")
    return out if keys or cfg else None


# ---------- the page ----------
def build(root=ROOT, now=None, issues=None):
    root = pathlib.Path(root); now = now or dt.datetime.now(dt.timezone.utc); facts = {}
    parts = []
    for title, fn, args in (("Your actions", sec_actions, (root, now, issues, facts)), ("YPP progress", sec_ypp, (root, now, facts)),
                            ("Is it getting better", sec_better, (root,)), ("Tests and changes", sec_tests, (root,)),
                            ("Keys", sec_keys, (root, now, facts)), ("Channels", sec_channels, (root, now))):
        try: body = fn(*args)
        except Exception: body = None
        parts += [f"## {title}", ""] + (body or [NA]) + [""]
    t = now.astimezone(UK)
    head = [f"Updated {t:%A} {t.day} {t:%B}, {t:%H:%M} UK."]
    bits = []
    if facts.get("subs") is not None: bits.append(f"{fmt(facts['subs'])} subscribers")
    if facts.get("v90") is not None: bits.append(f"{fmt(facts['v90'])} engaged Shorts views in 90 days ({facts.get('exp_pct', 'n/a')} of the 3M expanded tier)")
    if "actions" in facts: bits.append(f"{facts['actions']} to do")
    if "keys_bad" in facts: bits.append(f"{facts['keys_bad']} keys need fixing")
    if bits: head += ["", "**" + ", ".join(bits) + ".**"]
    foot = ["---", " \u00b7 ".join([link("How it works", "docs/HOW_IT_WORKS.md"), link("Actions", GH + "/actions"), link("Issues", GH + "/issues"),
                              link("Insights", "analytics/insights.md"), link("Weekly review", "analytics/weekly.md")]
                             + [link(n, f"analytics/{f}") for n, f in (("Sameness", "sameness.md"), ("Joint", "joint.md")) if (root / "analytics" / f).is_file()])]
    text = "\n".join(["# Quickplay hub", ""] + head + [""] + parts + foot) + "\n"
    return dashes(scrub(text))


def fetch_issues():
    """Open needs-charlie issues through gh, only where a token is set; None otherwise (the actions section skips that part)."""
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")) or not shutil.which("gh"): return None
    try:
        r = subprocess.run(["gh", "issue", "list", "--repo", REPO, "--label", "needs-charlie", "--state", "open", "--limit", "30",
                            "--json", "number,title,url,createdAt"], capture_output=True, text=True, timeout=40)
        d = json.loads(r.stdout) if r.returncode == 0 else None
        return d if isinstance(d, list) else None
    except Exception: return None


def main():
    text = build(ROOT, issues=fetch_issues())
    if sys.argv[1:] == ["-"]: print(text, end=""); return
    tmp = ROOT / "README.md.tmp"
    tmp.write_text(text, encoding="utf-8"); tmp.replace(ROOT / "README.md")
    print(f"README.md written: {len(text.splitlines())} lines")


if __name__ == "__main__":
    main()
