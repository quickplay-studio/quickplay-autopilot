"""The day's pipeline funnel, stage by stage, for both lines (Charlie, 23 October: measure everything, so when something goes
wrong the data says where and why). A stage that gets nothing while the stage before it had work is "stuck": the 23
October finding that no clip had ever been posted to Instagram or submitted (a schedule typo) would have shown here on
day one.

usage: python pipeline/funnel.py [YYYY-MM-DD]     (alerts.py runs it every evening; the hub shows status/funnel.json)

Writes status/funnel.json (today, with stuck stages and the main reasons things were lost) and appends one row a day to
analytics/funnel.csv (the history, for the weekly look at where Shorts and clips are lost).
"""
import collections, csv, datetime as dt, json, pathlib, re, sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
UK = ZoneInfo("Europe/London")
FIELDS = ["day", "packs", "written", "rendered", "render_failed", "uploaded", "public", "target",
          "clips_planned", "clips_made", "clips_uploaded", "clips_refused", "clips_instagram", "clips_submitted", "clips_views",
          "stuck"]


def load(p, default=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return default


def uk_day(s):
    try: return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(UK).date()
    except Exception: return None


def main_line(day):
    """Daily Shorts: fact packs, boards written for the day, rendered, failed renders (and why), uploaded, gone public."""
    out, why = collections.Counter(), collections.Counter()
    facts = load(ROOT / "trends" / "facts.json", {}) or {}
    if uk_day(facts.get("built")) == day: out["packs"] = len(facts.get("topics") or [])
    for d in ("queue", "ready", "done", "failed", "reserve"):
        for p in (ROOT / "boards" / d).glob("QD-*.json"):
            b = load(p, {}) or {}
            if b.get("created") == str(day) and not b.get("reserve") and b.get("mode") != "dry": out["written"] += 1
    for p in (ROOT / "status").glob("QD-*.json"):
        st = load(p, {}) or {}
        if st.get("mode") == "dry": continue
        if uk_day(st.get("rendered")) == day:
            if st.get("state") == "failed":
                out["render_failed"] += 1; why[re.sub(r"\d+", "N", str(st.get("error") or "unknown"))[:60]] += 1
            else: out["rendered"] += 1
        if uk_day(st.get("uploaded_at")) == day: out["uploaded"] += 1
        if st.get("video") and uk_day(st.get("publish_at")) == day: out["public"] += 1
    return out, why


def clips_line(day):
    """Clips: moments planned, made, uploaded, refused by YouTube, posted to Instagram, submitted to a campaign; views so far."""
    out, why = collections.Counter(), collections.Counter()
    for p in (ROOT / "clips" / "plans").glob("*.json"):
        if p.name.endswith(".words.json"): continue
        for m in (load(p, {}) or {}).get("moments") or []:
            if uk_day(m.get("planned")) == day: out["clips_planned"] += 1
            if uk_day(m.get("made")) == day: out["clips_made"] += 1
            if uk_day(m.get("uploaded")) == day: out["clips_uploaded"] += 1
            if uk_day((m.get("instagram") or {}).get("at")) == day: out["clips_instagram"] += 1
            if m.get("skipped"): why["clip skipped: " + str(m["skipped"]).split(":")[0][:40]] += 1 if uk_day(m.get("planned")) == day else 0
    sub = ROOT / "clips" / "submit.csv"
    if sub.exists():
        for r in csv.DictReader(sub.open()):
            s = str(r.get("submitted") or "")
            if re.match(r"\d{4}-\d\d-\d\d", s) and s[:10] == str(day): out["clips_submitted"] += 1
            elif s.startswith("failed") and str(r.get("public_at_uk", ""))[:10] == str(day): why["submission " + s[:50]] += 1
    log = ROOT / "status" / "clips_log.txt"
    if log.exists():
        out["clips_refused"] = sum(1 for l in log.read_text(errors="ignore").splitlines() if "upload failed" in l and "LimitReached" in l)
    stats = ROOT / "clips" / "stats.csv"
    if stats.exists():
        latest = {}
        for r in csv.DictReader(stats.open()): latest[r.get("clip")] = r
        out["clips_views"] = int(sum(float(r.get("views") or 0) for r in latest.values()))
    return out, why


def target():
    try:
        sys.path.insert(0, str(ROOT / "pipeline")); import quota
        return quota.target()
    except Exception: return int((load(ROOT / "config.json", {}) or {}).get("daily_limit", 15))


def stuck(row):
    """Stages that got nothing while the stage before them had work (the day's chain breaks there)."""
    chain = [("packs", "written", "the writer wrote nothing from the day's fact packs"),
             ("written", "rendered", "nothing rendered from the boards written"),
             ("clips_made", "clips_uploaded", "clips were made but none uploaded"),
             ("clips_uploaded", "clips_instagram", "clips went up on YouTube but none to Instagram"),
             ("clips_uploaded", "clips_submitted", "clips went up but none were submitted to a campaign")]
    out = [msg for a, b, msg in chain if row.get(a, 0) > 0 and row.get(b, 0) == 0]
    if row.get("written", 0) and row.get("render_failed", 0) > row.get("written", 0) / 3: out.append("over a third of the renders failed")
    if row.get("target") and row.get("written", 0) < row["target"] / 2: out.append(f"the writer filled under half of the {row['target']} places")
    return out


def run(day=None):
    day = day or dt.datetime.now(UK).date()
    a, wa = main_line(day)
    b, wb = clips_line(day)
    row = {"day": str(day), **{k: 0 for k in FIELDS if k not in ("day", "stuck")}, **a, **b, "target": target()}
    row["stuck"] = "; ".join(stuck(row))
    out = {"day": str(day), "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "stages": row,
           "stuck": stuck(row), "lost": dict((wa + wb).most_common(8))}
    (ROOT / "status" / "funnel.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    p = ROOT / "analytics" / "funnel.csv"
    rows = [r for r in csv.DictReader(p.open())] if p.exists() else []
    rows = [r for r in rows if r.get("day") != str(day)] + [{k: row.get(k, "") for k in FIELDS}]
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(sorted(rows, key=lambda r: r["day"])[-120:])
    print("funnel:", json.dumps(out, ensure_ascii=False))
    return out


if __name__ == "__main__":
    run(dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)
