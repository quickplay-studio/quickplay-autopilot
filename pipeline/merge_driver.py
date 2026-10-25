"""A git merge driver for the files several workflows write at once (audit M3, 24 October).

Every Save step rebases its commit on the latest main with `git pull --rebase -X theirs`. On a conflicting hunk, -X theirs
keeps this run's lines and drops the other run's, so two runs that each add a key to the same status file lose one of
them: social.py's "instagram" key lost means the Reel is posted again; engage.py's "engage" key lost means a second
creator comment. The Mac task's submitted times in clips/submit.csv and an hour's rows in analytics/hourly.csv can go
the same way.

This driver merges those files by key instead of by line, so both sides' changes survive:
- status/QD-*.json and status/TEST-*.json: key by key (nested objects too). A key only one side changed takes that
  side's value. When both changed it, this run wins (as -X theirs did). A key one side deleted and the other changed is
  kept.
- clips/submit.csv: row by row (clip, platform), field by field. For "submitted", a submitted time beats "pulled", which
  beats anything else, so the Mac's submission is never overwritten by an "expired" or "failed" from GitHub.
- analytics/hourly.csv: row by row (hour_utc), sorted by hour.
- status/actions.json (24 October): the action list, an array of items with an id. Item by item, field by field: pipeline/
  actions.py marks an item done or adds its issue number while a Claude session adds an item or edits one, so both survive.
- Anything else, or a file it cannot read as expected, falls back to git's own line merge favouring this run (exactly
  what -X theirs did), so the driver can never make a Save step fail where it would have passed before.

In a rebase, %A is the latest main (the other runs' work) and %B is this run's commit being replayed. The result goes
to %A. Exit 0 means merged.

Set in each Save step (.gitattributes names the paths):
  git config merge.qp.driver "python3 pipeline/merge_driver.py %O %A %B %P"
Where the driver is not configured (Charlie's Mac), git ignores the attribute and merges as before.
"""
import csv, io, json, re, subprocess, sys

MISSING = object()
CSV_KEYS = {"clips/submit.csv": (("clip", "platform"), False), "analytics/hourly.csv": (("hour_utc",), True)}


def merge3(o, a, b):
    """Three-way merge of JSON values: o the base (MISSING when absent), a the latest main, b this run."""
    if a == b: return a
    if o == a: return b                      # only this run changed it
    if o == b: return a                      # only the other side changed it
    if isinstance(a, dict) and isinstance(b, dict):
        base = o if isinstance(o, dict) else {}
        out = {}
        for k in list(a) + [k for k in b if k not in a]:
            ov, av, bv = base.get(k, MISSING), a.get(k, MISSING), b.get(k, MISSING)
            if bv is MISSING and av is not MISSING and av != ov: r = av          # deleted here, changed there: kept
            elif av is MISSING and bv is not MISSING and bv != ov: r = bv
            else: r = merge3(ov, av, bv)
            if r is not MISSING: out[k] = r
        return out
    return b                                 # both changed it differently: this run wins, as -X theirs did


def submitted_rank(v):
    v = v or ""
    return 3 if re.match(r"\d{4}-\d\d-\d\d", v) else 2 if v == "pulled" else 1 if v else 0


def merge_field(col, o, a, b):
    if a == b: return a
    if o == a: return b
    if o == b: return a
    if col == "submitted": return a if submitted_rank(a) > submitted_rank(b) else b
    return b


def read_csv(text):
    rows = list(csv.DictReader(io.StringIO(text))) if text.strip() else []
    head = next(csv.reader(io.StringIO(text)), []) if text.strip() else []
    return head, rows


def merge_csv(o_text, a_text, b_text, key, sort):
    ho, ro = read_csv(o_text); ha, ra = read_csv(a_text); hb, rb = read_csv(b_text)
    if not ha or not hb or any(k not in ha or k not in hb for k in key): raise ValueError("key columns missing")
    kf = lambda r: tuple(r.get(k) or "" for k in key)
    def index(rows):
        d = {}
        for r in rows:
            if kf(r) in d: raise ValueError(f"duplicate key {kf(r)}")
            d[kf(r)] = r
        return d
    io_, ia, ib = index(ro), index(ra), index(rb)
    cols = ha + [c for c in hb if c not in ha]
    out = []
    for k in list(ia) + [k for k in ib if k not in ia]:
        o, a, b = io_.get(k), ia.get(k), ib.get(k)
        if a is not None and b is not None:
            out.append({c: merge_field(c, (o or {}).get(c, ""), a.get(c, ""), b.get(c, "")) for c in cols})
        elif a is not None:                  # not in this run's file: added by the other side, or deleted here
            if o is None or o != a: out.append({c: a.get(c, "") for c in cols})
        else:                                # not in main: added by this run, or deleted there
            if o is None or o != b: out.append({c: b.get(c, "") for c in cols})
    if sort: out.sort(key=kf)
    nl = "\r\n" if "\r\n" in a_text or "\r\n" in b_text else "\n"
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator=nl, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    return buf.getvalue()


def merge_json(o_text, a_text, b_text):
    o = json.loads(o_text) if o_text.strip() else MISSING
    a, b = json.loads(a_text), json.loads(b_text)
    if not isinstance(a, dict) or not isinstance(b, dict): raise ValueError("not an object")
    m = merge3(o, a, b)
    return json.dumps(m, indent=1, ensure_ascii=False) + ("\n" if a_text.endswith("\n") else "")


def merge_list(o_text, a_text, b_text, key="id"):
    """A JSON array of objects with a unique key (status/actions.json): item by item, each merged field by field like the
    status files. An item only the other side added is kept; one only this run added is kept; one a side deleted and the
    other left alone is deleted. Main's order is kept, this run's new items follow."""
    o = json.loads(o_text) if o_text.strip() else []
    a, b = json.loads(a_text), json.loads(b_text)
    if not all(isinstance(x, list) for x in (o, a, b)): raise ValueError("not an array")
    def index(items):
        d = {}
        for it in items:
            if not isinstance(it, dict) or key not in it or it[key] in d: raise ValueError(f"items need a unique {key}")
            d[it[key]] = it
        return d
    io_, ia, ib = index(o), index(a), index(b)
    out = []
    for k in list(ia) + [k for k in ib if k not in ia]:
        ov, av, bv = io_.get(k, MISSING), ia.get(k, MISSING), ib.get(k, MISSING)
        if av is not MISSING and bv is not MISSING: out.append(merge3(ov, av, bv))
        elif av is not MISSING:              # not in this run's file: added on main, or deleted here
            if ov is MISSING or ov != av: out.append(av)
        elif ov is MISSING or ov != bv: out.append(bv)      # not on main: added by this run, or deleted there
    return json.dumps(out, indent=1, ensure_ascii=False) + ("\n" if a_text.endswith("\n") else "")


def kind(path):
    p = str(path).replace("\\", "/")
    if re.search(r"(^|/)status/(QD|TEST)-[^/]*\.json$", p): return "json"
    if re.search(r"(^|/)status/actions\.json$", p): return "list"
    for k in CSV_KEYS:
        if p == k or p.endswith("/" + k): return k
    return None


def line_merge(o, a, b):
    """git's own three-way line merge favouring this run (what -X theirs did)."""
    return subprocess.run(["git", "merge-file", "--theirs", "-q", a, o, b]).returncode == 0


def main(o, a, b, path):
    k = kind(path)
    try:
        if not k: return 0 if line_merge(o, a, b) else 1
        ot, at, bt = (open(x, encoding="utf-8", newline="").read() for x in (o, a, b))     # newline="": keep CRLF as written
        merged = merge_json(ot, at, bt) if k == "json" else merge_list(ot, at, bt) if k == "list" else merge_csv(ot, at, bt, *CSV_KEYS[k])
        with open(a, "w", encoding="utf-8", newline="") as f: f.write(merged)
        return 0
    except Exception as e:
        print(f"merge_driver: {path}: {type(e).__name__}: {e}; line merge instead", file=sys.stderr)
        return 0 if line_merge(o, a, b) else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
