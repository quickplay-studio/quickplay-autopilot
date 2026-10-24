"""Offline test of pipeline/mac_rows.py (24 October): the Mac's evening run gets its Vyro rows in one small answer (newest
first, 5 a day per account minus today's, only open rows under 3 days old, never an "expired" one), the Content Rewards
rows still inside their 30 minutes, the occasional jobs due, and "NOTHING TO DO" when there is nothing; `done` marks a
row without the Mac opening clips/submit.csv."""
import pathlib as _p, tempfile as _t, sys, json, csv, datetime as dt
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
sys.path.insert(0, REPO_DIR + "/pipeline")
import mac_rows as M

ROOT = _p.Path(_t.mkdtemp(prefix="qp-mac-"))
for d in ("clips", "status", "docs"): (ROOT / d).mkdir()
M.ROOT, M.SUBMIT = ROOT, ROOT / "clips" / "submit.csv"
camps = {"min_active": 2, "submit_daily_limits": {"Vyro": 5}, "campaigns": {
    "v1": {"platform": "Vyro", "card": "Card One", "active": True, "source": {"kind": "gdrive"}},
    "v2": {"platform": "Vyro", "card": "Card Two", "active": True, "source": {"kind": "gdrive"}},
    "cr": {"platform": "Content Rewards (Reach)", "active": True, "source": {"kind": "gdrive"}}}}
(ROOT / "clips" / "campaigns.json").write_text(json.dumps(camps))
F = ["clip", "campaign", "campaign_url", "platform", "video", "public_at_uk", "title", "hashtags", "submitted", "channel"]
NOW = dt.datetime(2026, 10, 24, 19, 7, tzinfo=M.UK)


def write(rows):
    with M.SUBMIT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=F); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in F})


def row(clip, camp, when, ch="clips", sub="", plat="youtube"):
    return {"clip": clip, "campaign": camp, "campaign_url": "https://x/" + camp, "platform": plat, "video": f"https://youtube.com/shorts/{clip}",
            "public_at_uk": when, "submitted": sub, "channel": ch}


# 1. tonight's 7 clips on one account and 2 older ones: 5 newest of that account; done, expired, private and future rows never
rs = [row(f"t{i}", "v1", "2026-10-24 19:00") for i in range(7)] + [row("y1", "v2", "2026-10-23 19:00"), row("y2", "v2", "2026-10-23 19:00", ch="gaming")]
rs += [row("old", "v1", "2026-10-20 19:00"), row("exp", "v1", "2026-10-23 19:00", sub="expired: 31h old with 0 views"),
       row("sent", "v1", "2026-10-24 19:00", sub="2026-10-24 19:05"), row("priv", "v1", "private (test)"), row("fut", "v1", "2026-10-24 20:00"),
       row("ig", "v1", "2026-10-24 19:00", plat="instagram")]
write(rs)
cfg = json.loads((ROOT / "clips" / "campaigns.json").read_text())
due, left = M.vyro_due(M.rows(), cfg["campaigns"], NOW, 5)
ids = [r["clip"] for r in due]
assert left["clips"] == 4, left                       # "sent" used one of today's 5
assert ids[:4] == ["t0", "t1", "t2", "t3"] and "y2" in ids and "old" not in ids and "exp" not in ids and "priv" not in ids, ids
assert "fut" not in ids and "ig" not in ids and "sent" not in ids
assert sum(1 for r in due if (r["channel"] or "clips") == "clips") == 4
out = M.show(NOW, fetch_issues=False)
assert "Vyro: 5 to submit now" in out and "card: Card One" in out and "Quickplay Gaming Clips" in out and "NOTHING" not in out, out
print("vyro rows ok")

# 2. done: the row is marked (now -> the UK time), only open rows, never another platform's
assert M.mark("t0", "youtube", "now", NOW) == 1 and M.mark("t0", "youtube", "now", NOW) == 0
assert M.mark("y1", "youtube", "failed: card not found", NOW) == 1 and M.mark("y1", "youtube", "now (already)", NOW) == 1
got = {r["clip"]: r["submitted"] for r in M.rows()}
assert got["t0"] == "2026-10-24 19:07" and got["y1"] == "2026-10-24 19:07 (already)" and got["ig"] == "", got
print("done ok")

# 3. Content Rewards rescue: a sign-in failure inside the 30 minutes only
write([row("c1", "cr", "2026-10-24 19:00", sub="failed: login expired"), row("c2", "cr", "2026-10-24 18:00", sub="failed: login expired"),
       row("c3", "cr", "2026-10-24 19:00", sub="failed: past the 30 minutes")])
res = [r["clip"] for r in M.cr_rescue(M.rows(), cfg["campaigns"], NOW)]
assert res == ["c1"], res
print("rescue ok")

# 4. nothing open and no jobs: NOTHING TO DO; a Monday adds the related-video job; too few campaigns adds capacity
write([row("z", "v1", "2026-10-24 19:00", sub="2026-10-24 19:03")])
assert "NOTHING TO DO" in M.show(NOW, fetch_issues=False)
monday = dt.datetime(2026, 10, 26, 19, 7, tzinfo=M.UK)
assert "Related video" in M.show(monday, fetch_issues=False)
camps["min_active"] = 9; (ROOT / "clips" / "campaigns.json").write_text(json.dumps(camps))
assert "Capacity: 3 of 9" in M.show(NOW, fetch_issues=False)
camps["min_active"] = 2; (ROOT / "clips" / "campaigns.json").write_text(json.dumps(camps))
(ROOT / "docs" / "CHROME_LOG.md").write_text("## One-off jobs\n### open: Join X\n### waiting: Make Y (Charlie)\n")
o = M.show(NOW, fetch_issues=False)
assert "- Join X" in o and "Make Y" not in o and "NOTHING" not in o, o
print("jobs ok")
print("mac rows ok")
