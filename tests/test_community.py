"""Offline test of the daily community poll (25 October; Charlie: a poll each day, a reason for viewers to subscribe):
1. options: the engage question's own "A or B" options, Yes / No / Not sure for a yes or no question, a reaction poll for an open one;
   no em or en dashes
2. the Short: today's best by views at 3 hours that has an engage question and is not a sad story, a politics or crime question, a
   Short that carries a campaign or a repeat; the file is made once a day from community_hour_utc, final for the day, and rolled into
   its history the next day
3. the Mac: pipeline/mac_rows.py lists the poll while it is dated today and not posted (so "NOTHING TO DO" does not hide it);
   `posted` clears it; `unavailable` (no Community tab) pauses polls for 7 days, then they come back
Stubs only: temp folders, no network, no key."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, csv, datetime as dt, io, json, os, sys
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
import community as C
import mac_rows as M

DASHES = chr(0x2013) + chr(0x2014)

# 1. options -------------------------------------------------------------------------------------------------------------------
want = {
    "Did you think the Moon didn't spin?": ["Yes", "No", "Not sure"],
    "Will you be clearing space on your console for 5 November?": ["Yes", "No", "Not sure"],
    "Can anyone stop LOUD next year?": ["Yes", "No", "Not sure"],
    "Did you know how golf balls evolved?": ["I knew that", "News to me"],
    "Hearts, blood or arms: which surprised you most?": ["Hearts", "Blood", "Arms"],
    "Too long for radio, or perfect as it is?": ["Too long for radio", "Perfect as it is"],
    "Whose verse wins: Olivia's or Chappell's?": ["Olivia's", "Chappell's"],
    "Ugly 1-0 wins: title form or warning sign?": ["Title form", "Warning sign"],
    "Fairy or mermaid: which Zara look wins?": ["Fairy", "Mermaid"],
    "Would you rather fly or be invisible?": ["Fly", "Be invisible"],
    "Who could ever break 9.58?": None,                                                   # open: no options can be read off it
    "What was the first text you ever sent?": None,
    "Which moon in our solar system is your favourite?": None,
    "Best casting in the Street Fighter movie?": None,
    "Is 5.55 minutes too long for a song, or is it just right?": None,                    # a yes or no that asks for more than yes or no
}
for q, opts in want.items(): assert C.options(q) == opts, (q, C.options(q))
assert C.options("Which one: red, green, blue, yellow or purple?") is None               # more than 4 options is not a short poll
assert C.options("A very long first choice that goes on and on past forty characters or B?") is None
assert C.options("") is None and C.options(None) is None
p = C.poll_for("Hearts, blood or arms: which surprised you most?")
assert p == {"question": "Hearts, blood or arms: which surprised you most?", "options": ["Hearts", "Blood", "Arms"], "kind": "question"}, p
p = C.poll_for("Who could ever break 9.58?")
assert p["kind"] == "reaction" and p["options"] == ["Loved it", "Liked it", "Not for me"] and p["question"].endswith("?"), p
p = C.poll_for("Is it good" + chr(0x2014) + "or bad?")
assert not any(ch in json.dumps(p, ensure_ascii=False) for ch in DASHES), p
assert not any(ch in C.post_line("A title " + chr(0x2013) + " with a dash", "https://youtube.com/shorts/x") for ch in DASHES)
line = C.post_line("T" * 300, "https://youtube.com/shorts/abc")
assert line.startswith("Most watched Short today: ") and line.endswith(" https://youtube.com/shorts/abc") and len(line) < 190 and "\n" not in line, line
for q, opts in want.items():
    for o in opts or []: assert 2 <= len(o) <= 40 and o[0].isupper(), o
print("1 options ok")

# 2. the Short and the file ----------------------------------------------------------------------------------------------------
R = SCRATCH / "repo"
for d in ("analytics", "boards/done", "status"): (R / d).mkdir(parents=True)
(R / "config.json").write_text(json.dumps({"community_hour_utc": 12}))
NOW = dt.datetime(2026, 10, 25, 14, 0, tzinfo=dt.timezone.utc)                 # GMT: the clocks went back that morning
SHORTS = [  # id, posted, views at 3 hours, yt views, question, title (a board's title), status extras
    ("QD-701", "2026-10-25T03:00+00:00", "50", "90", "Which song is your favourite?", "Raye hits a billion streams", {}),
    ("QD-702", "2026-10-25T05:00+00:00", "200", "310", "Will you play it on day one?", "GTA 6 price: the physical edition surprise", {}),
    ("QD-703", "2026-10-25T06:00+00:00", "900", "950", "Did you know him?", "Famous singer dies at 70", {}),
    ("QD-704", "2026-10-25T07:00+00:00", "800", "820", "Which beat is better?", "Spring beat Short", {"sponsor": {"campaign": "spring", "applied": True}}),
    ("QD-705", "2026-10-25T08:00+00:00", "700", "720", "", "A Short with no question", {}),
    ("QD-706", "2026-10-25T09:00+00:00", "600", "650", "Who should win the election?", "Election night special", {}),
    ("QD-707", "2026-10-24T12:00+00:00", "5000", "9000", "Was that goal offside?", "Yesterday's big one", {}),
    ("QD-708", "2026-10-25T12:30+00:00", "", "4", "Will it last?", "Too new to have 3 hour views", {}),
]
def write_shorts(rows):
    with (R / "analytics" / "shorts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["short", "title", "posted", "posted_day", "youtube_url", "yt_views", "views_3h"]); w.writeheader()
        for sid, posted, v3, yv, q, title, extra in rows:
            w.writerow({"short": sid, "title": title, "posted": posted, "posted_day": posted[:10], "youtube_url": f"https://youtube.com/shorts/{sid.lower()}",
                        "yt_views": yv, "views_3h": v3})
for sid, posted, v3, yv, q, title, extra in SHORTS:
    meta = {"title": title, "summary": "A summary."}
    if q: meta["comment"] = q
    (R / "boards" / "done" / f"{sid}.json").write_text(json.dumps({"id": sid, "meta": meta, "beats": [{"say": "A line."}]}))
    (R / "status" / f"{sid}.json").write_text(json.dumps({"id": sid, "video": sid.lower(), **extra}))
write_shorts(SHORTS)

out = R / "status" / "community.json"
assert C.refresh(NOW - dt.timedelta(hours=3), R) == {} and not out.exists()             # 11:00 UTC: before community_hour_utc
s = C.refresh(NOW, R)
assert s["short"] == "QD-702" and s["views_3h"] == 200 and s["date"] == "2026-10-25", s    # not the sad story, the campaign carrier, the election, yesterday's
assert s["poll"] == {"question": "Will you play it on day one?", "options": ["Yes", "No", "Not sure"], "kind": "question"}, s["poll"]
assert s["post"] == "Most watched Short today: GTA 6 price: the physical edition surprise https://youtube.com/shorts/qd-702", s["post"]
assert s["posted"] == "" and s["unavailable"] == "" and json.loads(out.read_text()) == s
# final for the day: a better Short appearing later changes nothing
better = SHORTS + [("QD-709", "2026-10-25T10:00+00:00", "5000", "5000", "Will you watch?", "Better", {})]
(R / "boards" / "done" / "QD-709.json").write_text(json.dumps({"id": "QD-709", "meta": {"title": "Better", "comment": "Will you watch?"}, "beats": []}))
write_shorts(better)
assert C.refresh(NOW + dt.timedelta(hours=2), R)["short"] == "QD-702"
print("2a the day's best Short, made once ok")

# no Short qualifies yet: nothing is written, the next hour tries again
R2 = SCRATCH / "repo2"
for d in ("analytics", "boards/done", "status"): (R2 / d).mkdir(parents=True)
with (R2 / "analytics" / "shorts.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["short", "title", "posted", "posted_day", "youtube_url", "yt_views", "views_3h"]); w.writeheader()
assert C.refresh(NOW, R2) == {} and not (R2 / "status" / "community.json").exists()
assert C.refresh(NOW, SCRATCH / "no-such-folder") == {}                                   # no analytics at all: quiet
# an open question gets the reaction poll; with no Short today the last 24 hours are looked at
(R2 / "boards" / "done" / "QD-801.json").write_text(json.dumps({"id": "QD-801", "meta": {"title": "Last night's one", "comment": "Which moon is your favourite?"}, "beats": []}))
with (R2 / "analytics" / "shorts.csv").open("a", newline="") as f:
    csv.writer(f).writerow(["QD-801", "Last night's one", "2026-10-24T20:00+00:00", "2026-10-24", "https://youtube.com/shorts/qd801", "30", "12"])
s2 = C.refresh(NOW, R2)
assert s2["short"] == "QD-801" and s2["poll"]["kind"] == "reaction" and s2["poll"]["options"] == ["Loved it", "Liked it", "Not for me"], s2
print("2b nothing yet, last 24 hours, reaction poll ok")

# the next day: the old poll goes into the history, and the Short with a poll is not picked again
T2 = dt.datetime(2026, 10, 27, 13, 0, tzinfo=dt.timezone.utc)                  # a Tuesday: no weekly Mac job is due
nxt = [("QD-710", "2026-10-27T04:00+00:00", "40", "60", "Fairy or mermaid: which look wins?", "A fairy look", {})] + SHORTS + [("QD-709", "2026-10-25T10:00+00:00", "5000", "5000", "x?", "Better", {})]
(R / "boards" / "done" / "QD-710.json").write_text(json.dumps({"id": "QD-710", "meta": {"title": "A fairy look", "comment": "Fairy or mermaid: which look wins?"}, "beats": []}))
write_shorts(nxt)
s3 = C.refresh(T2, R)
assert s3["date"] == "2026-10-27" and s3["short"] == "QD-710" and s3["poll"]["options"] == ["Fairy", "Mermaid"], s3
assert s3["history"] == [{"date": "2026-10-25", "short": "QD-702", "kind": "question", "posted": "", "unavailable": ""}], s3["history"]
assert "posted" in s3 and s3["posted"] == ""                                                   # a clean sheet for the new day
print("2c rolled into the history ok")

# 3. the Mac -------------------------------------------------------------------------------------------------------------------
lines = C.due(T2, R)
assert len(lines) == 2 and lines[0] == "- Text post: Most watched Short today: A fairy look https://youtube.com/shorts/qd-710", lines
assert lines[1] == "- Poll: Fairy or mermaid: which look wins? Options: Fairy | Mermaid", lines
assert C.due(T2 + dt.timedelta(days=1), R) == [] and C.due(T2 - dt.timedelta(days=1), R) == []        # dated today only
M.ROOT = R; M.SUBMIT = R / "clips" / "submit.csv"
(R / "clips").mkdir(); (R / "docs").mkdir()
(R / "clips" / "campaigns.json").write_text(json.dumps({"min_active": 1, "campaigns": {"c1": {"platform": "Vyro", "card": "One", "active": True, "source": {"kind": "gdrive"}, "ends": "2027-01-01"}}}))
tue = dt.datetime(2026, 10, 27, 19, 7, tzinfo=M.UK)
shown = M.show(tue, fetch_issues=False)
assert "Community poll for Quickplay Daily" in shown and "Options: Fairy | Mermaid" in shown and "NOTHING TO DO" not in shown, shown
assert "Community poll" not in M.show(dt.datetime(2026, 10, 28, 19, 7, tzinfo=M.UK), fetch_issues=False)       # Wednesday: yesterday's is not shown
# the Mac's own commands, at 19:10 on Tuesday
C.ROOT = R
C.utcnow = lambda: dt.datetime(2026, 10, 27, 19, 10, tzinfo=dt.timezone.utc)
buf = io.StringIO()
with contextlib.redirect_stdout(buf): C.main(["show"])
assert "- Text post: Most watched Short today: A fairy look" in buf.getvalue(), buf.getvalue()
buf = io.StringIO()
with contextlib.redirect_stdout(buf): C.main(["posted"])
assert "marked posted (QD-710)" in buf.getvalue(), buf.getvalue()
st = json.loads(out.read_text())
assert st["posted"] == "2026-10-27 19:10" and st["short"] == "QD-710", st
assert C.due(T2, R) == []
shown = M.show(tue, fetch_issues=False)
assert "Community poll" not in shown and "NOTHING TO DO" in shown, shown                       # posted: gone from the list, nothing left to do
buf = io.StringIO()
with contextlib.redirect_stdout(buf): C.main(["show"])
assert "no poll to post today" in buf.getvalue(), buf.getvalue()
# a posted poll is final: the hourly run leaves it alone, and says where it stands
assert C.refresh(T2 + dt.timedelta(hours=1), R)["posted"] == "2026-10-27 19:10"
buf = io.StringIO()
with contextlib.redirect_stdout(buf): C.main([])
assert "QD-710" in buf.getvalue() and "posted 2026-10-27 19:10" in buf.getvalue(), buf.getvalue()
print("3a the Mac lists it and clears it ok")

# the channel has no Community tab: no poll for 7 days, then it asks again
R3 = SCRATCH / "repo3"
for d in ("analytics", "boards/done", "status"): (R3 / d).mkdir(parents=True)
(R3 / "boards" / "done" / "QD-702.json").write_text(json.dumps({"id": "QD-702", "meta": {"title": "T", "comment": "Will you play it?"}, "beats": []}))
(R3 / "boards" / "done" / "QD-720.json").write_text(json.dumps({"id": "QD-720", "meta": {"title": "T2", "comment": "Will you watch it?"}, "beats": []}))
def short_rows(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["short", "title", "posted", "posted_day", "youtube_url", "yt_views", "views_3h"]); w.writeheader()
        for r in rows: w.writerow(r)
mk = lambda sid, day: {"short": sid, "title": sid, "posted": f"{day}T05:00+00:00", "posted_day": day, "youtube_url": f"https://youtube.com/shorts/{sid}", "yt_views": "9", "views_3h": "9"}
short_rows(R3 / "analytics" / "shorts.csv", [mk("QD-702", "2026-10-25")])
s = C.refresh(NOW, R3)
assert s["short"] == "QD-702"
msg = C.mark("unavailable", "Studio shows no Community tab", now=NOW, root=R3)
assert "no poll until after 2026-11-01" in msg, msg
s = json.loads((R3 / "status" / "community.json").read_text())
assert s["unavailable"] == "Studio shows no Community tab" and s["paused_until"] == "2026-11-01"
assert C.due(NOW, R3) == []                                                                      # not shown to the Mac again today
for days in (1, 5, 7):                                                                           # paused through 1 November: a file with no poll
    short_rows(R3 / "analytics" / "shorts.csv", [mk("QD-702", "2026-10-25"), mk("QD-720", (NOW + dt.timedelta(days=days)).date().isoformat())])
    s = C.refresh(NOW + dt.timedelta(days=days), R3)
    assert s.get("date") == (NOW + dt.timedelta(days=days)).date().isoformat() and not s.get("poll") and s["paused_until"] == "2026-11-01", (days, s)
    assert C.due(NOW + dt.timedelta(days=days), R3) == []
short_rows(R3 / "analytics" / "shorts.csv", [mk("QD-702", "2026-10-25"), mk("QD-720", "2026-11-02")])
s = C.refresh(NOW + dt.timedelta(days=8), R3)                                                    # 2 November: asks again
assert s["short"] == "QD-720" and s["paused_until"] == "" and s["history"][-1]["short"] == "QD-702" and s["history"][-1]["unavailable"], s
assert C.mark("posted", now=NOW + dt.timedelta(days=30), root=R3).startswith("community: no poll is dated today")      # nothing to mark
print("3b no Community tab: paused 7 days, then back ok")
print("community ok")
