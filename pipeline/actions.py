"""The live action list (Charlie, 24 October: "how do we have a live to do list, so when i action an item github checks it and
updates the hub automatically without me needing to come back to this chat"). status/actions.json is the list the hub shows
under "Your actions this week"; this script keeps it true. Run by .github/workflows/audit.yml every 3 hours, on a push of
status/actions.json, and within a minute of Charlie closing or reopening one of its issues:

 - An item with a "check" (a name from CHECKS below, "secret_works:MISTRAL_API_KEY") is run: when it passes the item is marked
   done ("done_by": "check"), when it stops passing it is open again. A check that cannot reach its answer (the network, a
   rate limit) changes nothing.
 - An item with no check gets one GitHub issue (label needs-charlie), once, linked from the item ("issue"). Closing that issue
   in the GitHub app marks the item done ("done_by": "issue"); reopening it opens the item again. The issue carries a marker
   (<!-- qp-action:ID -->), so a lost link is found again instead of a second issue being made.
 - An item marked done any other way (a check, or by hand) has its open issue closed; an open issue of a removed item too.
 - The hub hides done items and lists the ones done this week in a "Done this week" line.

Item fields (all but the first group are optional): id, title, why, steps, links, added, due, done (the first group is
required by the hub); short (a few words for the done line), repeat (a daily or weekly chore), check; written here: done_at,
done_by, issue, note (what the check last said).

  python pipeline/actions.py            in GitHub Actions: the real run; elsewhere the list
  python pipeline/actions.py list       the list and where each item stands
  python pipeline/actions.py now        the real run from anywhere (needs GH_TOKEN and the keys in the environment)
"""
import datetime as dt, json, os, pathlib, re, sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
import keys as K
import mac_rows as M

OUT = ROOT / "status" / "actions.json"
NEEDS = "needs-charlie"
MARK = "<!-- qp-action:{} -->"
MARKED = re.compile(r"<!-- qp-action:([A-Za-z0-9_.-]+) -->")
MAX_NEW = 5                         # issues made in one run: a runaway can never flood Charlie's phone
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
DEL = object()                      # a patch value that removes the field
HOWTO = ("Close this issue when it is done: the hub's list updates by itself within a minute or so. If you get stuck, start a "
         "new Claude chat, use the quickplay skill and paste this issue's link.")


def log(*a): print(*a, flush=True)


# ---------- the checks: each returns (True | False | None, a short note for the hub, when it became true or None) ----------
CHECKS = {}


def check(name):
    def deco(fn): CHECKS[name] = fn; return fn
    return deco


@check("secret_works")
def secret_works(arg, ctx):
    """A GitHub secret exists and its service accepts it: one cheap call (keys.probe: Mistral and SambaNova list their models,
    Cloudflare verifies the token and needs CF_ACCOUNT_ID too)."""
    if arg not in K.PROBES: return None, f"no probe is written for {arg}", None
    res = K.probe(arg, ctx.env, ctx.get)
    if res["status"] == "ok": return True, res["detail"], None
    if res["status"] == "unverified": return None, res["detail"], None
    return False, res["detail"] + ("" if res["status"] == "failing" else " yet"), None


@check("pages_workflow")
def pages_workflow(arg, ctx):
    """The hub's site builds from GitHub Actions (Settings, Pages, Source), not from a branch: the Pages API says so."""
    r = ctx.A.gh("api", f"repos/{K.REPO}/pages")
    try: j = json.loads(r.stdout or "")
    except ValueError: j = None
    if getattr(r, "returncode", 0) == 0 and isinstance(j, dict) and j.get("build_type"):
        if j["build_type"] == "workflow": return True, "GitHub Pages builds from GitHub Actions", None
        src = j.get("source") or {}
        return False, f"GitHub Pages still builds from a branch ({src.get('branch', 'main')}, {src.get('path', '/docs')})", None
    return None, "GitHub did not say how Pages builds", None


@check("vyro_today")
def vyro_today(arg, ctx):
    """Vyro takes links only from the Mac's Chrome (docs/CHROME_JOBS.md). Done for the day once every Vyro YouTube row that
    goes public today (UK) and is still alive carries a submitted time, within the places each account has a day (5);
    open while one waits; None while no Vyro clip is due today."""
    cfg, camps = ctx.cfg, ctx.cfg.get("campaigns") or {}
    limit = int((cfg.get("submit_daily_limits") or {}).get("Vyro") or 5)
    today = ctx.now.astimezone(M.UK).date()
    day = f"{K.nice(ctx.now)}"
    done, waiting, last = {}, {}, None
    for r in ctx.rows:
        if not M.on_vyro(camps.get(r.get("campaign"))) or (r.get("platform") or "youtube") != "youtube": continue
        t = M.public_at(r)
        if t is None or t.date() != today: continue
        ch, s = r.get("channel") or "clips", str(r.get("submitted") or "")
        if STAMP.match(s):
            done[ch] = done.get(ch, 0) + 1
            try: at = dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M").replace(tzinfo=M.UK).astimezone(dt.timezone.utc)
            except ValueError: at = None
            if at and (last is None or at > last): last = at
        elif M.is_open(r): waiting[ch] = waiting.get(ch, 0) + 1          # pulled, expired or too late: nothing left for the Mac
    if not done and not waiting: return None, f"{day}: no Vyro clip is due today", None
    need = sum(min(waiting.get(ch, 0), max(0, limit - done.get(ch, 0))) for ch in set(done) | set(waiting))
    n = sum(done.values())
    if need == 0:
        return True, f"{day}: {n} Vyro clip{'s' if n != 1 else ''} submitted" + (f", the last at {last.astimezone(M.UK):%H:%M} UK" if last else ""), last
    return False, f"{day}: {need} Vyro clip{'s' if need != 1 else ''} still wait for the Mac ({n} submitted so far)", None


def run_check(spec, ctx):
    name, _, arg = str(spec).partition(":")
    fn = CHECKS.get(name)
    if fn is None: return None, f"no check is written called {name}", None
    try: return fn(arg, ctx)
    except Exception as e: return None, f"{type(e).__name__}: {str(e)[:100]}", None


# ---------- what one item needs ----------
def by_check(it, res, note, when_true, now):
    """The patch for a check item: done when it passes, open again when it stops passing, nothing when unknown."""
    p = {}
    if note and res is not None and it.get("note") != note: p["note"] = note          # an unknown answer says nothing new
    if res is True:
        if not it.get("done"): p.update(done=True, done_at=K.stamp(when_true or now), done_by="check")
        elif it.get("done_by") != "check": p["done_by"] = "check"             # done by hand, and now proven
    elif res is False and it.get("done"):
        p.update(done=False, done_at=DEL, done_by=DEL)
    return p


def reopen(): return {"done": False, "done_at": DEL, "done_by": DEL}


def issue_body(it):
    out = [it.get("why") or it.get("title")]
    if it.get("steps"): out.append("Steps:\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(it["steps"], 1)))
    if it.get("links"): out.append("Links:\n" + "\n".join(f"- {l.get('label')}: {l.get('url')}" for l in it["links"] if isinstance(l, dict)))
    due = K.when(it.get("due"))
    out.append(f"Due {K.nice(due)}." if due else f"Repeats: {it['repeat']}." if it.get("repeat") else "No deadline: this one is optional.")
    out.append(MARK.format(it["id"]))
    return "\n\n".join(out)


def marker_of(issue):
    """The item id an issue was made for (its marker), or None."""
    m = MARKED.search(issue.get("body") or "")
    return m.group(1) if m else None


def close_mine(id, n, scan, A):
    """Closes the open issues made for an item (by its marker, or the number it links)."""
    notes = []
    for i in scan:
        if marker_of(i) == id or (n and i["number"] == n):
            A.close_issue(i["number"], "Done: this item is marked done in the action list, so this issue is closed.")
            notes.append(f"{id}: marked done elsewhere, closed issue {i['number']}")
    return notes


def by_issue(it, scan, ctx, budget):
    """The patch for an item with no check, from its GitHub issue. scan: the open needs-charlie issues, None if GitHub
    could not be read (then nothing is made or closed). budget: [issues the run may still make]. Returns (patch, notes)."""
    A = ctx.A
    if scan is None: return {}, []
    id, n = it["id"], it.get("issue")
    open_nums = {i["number"] for i in scan}
    if it.get("done"):
        if str(it.get("done_by") or "").startswith("issue"):
            if n in open_nums: return reopen(), [f"{id}: issue {n} reopened, item open again"]
            return {}, []
        return {}, close_mine(id, n, scan, A)
    if n:
        if n in open_nums: return {}, []
        info = A.issue_info(n)
        if info is None or info["state"] != "CLOSED": return {}, []
        why = "issue" + (" (closed as not planned)" if str(info["reason"]).upper() == "NOT_PLANNED" else "")
        return {"done": True, "done_at": K.stamp(K.when(info["closed_at"]) or ctx.now), "done_by": why}, [f"{id}: issue {n} closed, item done"]
    mine = [i for i in scan if marker_of(i) == id]
    if mine: return {"issue": mine[0]["number"]}, [f"{id}: linked to issue {mine[0]['number']}"]      # a lost link: find it, never make a second
    if budget[0] <= 0: return {}, []
    budget[0] -= 1
    num = A.raise_issue(it["title"], issue_body(it), labels=[NEEDS], howto=HOWTO)
    return ({"issue": num} if num else {}), [f"{id}: issue {num or '?'} opened"]


def apply(it, patch):
    for k, v in patch.items():
        if v is DEL: it.pop(k, None)
        else: it[k] = v


def read(path):
    try:
        d = json.loads(pathlib.Path(path).read_text())
        return d if isinstance(d, list) else None
    except Exception: return None


def save(path, patches):
    """Applies the patches to the file as it is now (it may have been edited while the checks ran) and writes it only when
    something changed. Returns whether it wrote."""
    cur = read(path)
    if cur is None: return False
    before = json.dumps(cur, ensure_ascii=False)
    for it in cur:
        if isinstance(it, dict) and it.get("id") in patches: apply(it, patches[it["id"]])
    if json.dumps(cur, ensure_ascii=False) == before: return False
    pathlib.Path(path).write_text(json.dumps(cur, indent=1, ensure_ascii=False) + "\n")
    return True


def orphans(items, scan, A):
    """Open issues this script made for an item that is gone from the list."""
    notes, ids = [], {it.get("id") for it in items if isinstance(it, dict)}
    for i in scan or []:
        gone = marker_of(i)
        if gone and gone not in ids:
            A.close_issue(i["number"], "This item is no longer in the action list, so the issue is closed.")
            notes.append(f"closed issue {i['number']}: item {gone} is gone")
    return notes


def run(now=None, env=None, get=None, A=None, path=None, write=True, rows=None, cfg=None):
    path = path or OUT
    now = now or K.now()
    if A is None: import alerts as A
    items = read(path)
    if items is None: log("actions: status/actions.json is missing or not a list"); return None
    if rows is None: rows = M.rows()
    if cfg is None: cfg = M.load_json(ROOT / "clips" / "campaigns.json", {}) or {}
    ctx = SimpleNamespace(now=now, env=os.environ if env is None else env, get=get, A=A, rows=rows, cfg=cfg)
    scan = A.issues_with(NEEDS)
    patches, notes, budget = {}, [], [MAX_NEW]
    for it in items:
        if not isinstance(it, dict) or not it.get("id"): continue
        try:
            if it.get("check"):
                res, note, when_true = run_check(it["check"], ctx)
                p = by_check(it, res, note, when_true, now)
                if p.get("done") is True: notes.append(f"{it['id']}: the check passed, done")
                elif p.get("done") is False: notes.append(f"{it['id']}: the check no longer passes, open again")
                if scan and (p["done"] if "done" in p else it.get("done")):
                    notes += close_mine(it["id"], it.get("issue"), scan, A)       # done, so an issue it still has is closed
            else:
                p, more = by_issue(it, scan, ctx, budget); notes += more
        except Exception as e:
            log(f"actions: {it.get('id')}: {type(e).__name__}: {str(e)[:100]}"); continue
        if p: patches[it["id"]] = p
    try: notes += orphans(items, scan, A)
    except Exception as e: log("actions: orphans:", f"{type(e).__name__}: {str(e)[:100]}")
    wrote = save(path, patches) if write else False
    for n in notes: log("actions:", n)
    log(f"actions: {len(items)} items, {sum(1 for it in items if it.get('check'))} with a check, {len(patches)} changed" + (", file written" if wrote else ""))
    return {"notes": notes, "patches": patches, "wrote": wrote}


def show():
    items = read(OUT)
    if items is None: print("no status/actions.json"); return
    for it in items:
        how = it.get("check") or (f"issue {it['issue']}" if it.get("issue") else "no issue yet")
        state = f"done {str(it.get('done_at') or '')[:16]} by {it.get('done_by') or 'hand'}" if it.get("done") else "open"
        print(f"{it.get('id', '?'):<22} {state:<40} {how}" + (f" | {it['note'][:70]}" if it.get("note") else ""))


if __name__ == "__main__":
    a = sys.argv[1:]
    if "list" in a or (os.environ.get("GITHUB_ACTIONS") != "true" and "now" not in a): show()
    else: run()
