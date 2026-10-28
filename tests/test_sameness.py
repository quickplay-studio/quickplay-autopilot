"""Offline test of the sameness guard (pipeline/sameness.py and its writer hooks, 28 October): the similarity scores, the
calibration, the pair check with its rewrite-then-drop, the recipe cap (mega trend and reserve exempt, the pair check never),
the channel score and recipe share files, the alert, the ledger metric, and no en or em dash in anything it writes. No network, no
model, no live board is changed."""
import pathlib as _p, sys, os, json, csv, datetime as dt, tempfile, random
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
os.environ["WRITE_DRY"] = "1"
import sameness as SM
import writer as W
W.CFG["shorts_channels"] = {}
DASHES = (chr(0x2013), chr(0x2014))      # en and em dash, written as code points


def board(i, title, says, fmt="one_detail", day="2026-10-28", ch=None, hook_type="statement", look=None, series="", writer="gemini:m"):
    b = {"id": f"QD-{i:03d}", "created": day, "format": fmt, "category": "Film", "writer": writer,
         "meta": {"title": title, "alt_title": title}, "test": {"hook_type": hook_type, "first_frame": "cover"},
         "beats": [{"say": s, "visual": {"type": "none"}, "shots": []} for s in says]}
    if ch: b["channel"] = ch
    if series: b["series_name"] = series
    if look: b["look"] = look
    return b


A = board(1, "Walter Koenig: the audition secret you never knew",
          ["Only two actors auditioned for Chekov in the original Star Trek.",
           "Walter Koenig got the part against one other actor, a shorter queue than a coffee run.",
           "He became a favourite for generations of fans and George Takei's best man.",
           "He passed away on 25 October 2026 aged 90."])
B = board(2, "Walter Koenig: the audition secret you missed",             # the same story told again in nearly the same shape
          ["Only two actors auditioned for Chekov on the original Star Trek.",
           "Walter Koenig won the part against one other actor, a shorter list than a coffee queue.",
           "He became a favourite for generations of fans and was George Takei's best man.",
           "He passed away on 25 October 2026 aged 90."])
C = board(3, "Rocket Lab reuses a booster for the first time",
          ["A rocket booster flew twice this week and nobody lost a thing.",
           "Rocket Lab caught it by helicopter over the Pacific, then fired it again.",
           "That halves the cost of reaching orbit for small satellites.",
           "Your next phone signal may ride on a used rocket."], fmt="real_reason", hook_type="number")
T1 = board(4, "Beyonce: the 2003 detail you missed",                      # same script pattern as T2, different subject
           ["Beyonce released an album in 2003 that sold 317000 copies.", "Critics in London called it a landmark.",
            "The singer then toured for 5 months."], fmt="story")
T2 = board(5, "Adele: the 2011 detail you missed",
           ["Adele released an album in 2011 that sold 208000 copies.", "Critics in Paris called it a landmark.",
            "The singer then toured for 7 months."], fmt="story")
P = {k: SM.profile(v) for k, v in dict(A=A, B=B, C=C, T1=T1, T2=T2).items()}

# 1. scores: a near-duplicate far above an unrelated board, symmetric, 1 for itself, a template pair above the unrelated pair
s_ab, s_ac, s_t, s_tc = SM.score(P["A"], P["B"]), SM.score(P["A"], P["C"]), SM.score(P["T1"], P["T2"]), SM.score(P["T1"], P["C"])
assert s_ab > 0.5 and s_ac < 0.2 and s_ab > 3 * s_ac, (s_ab, s_ac)
assert abs(SM.score(P["A"], P["B"]) - SM.score(P["B"], P["A"])) < 1e-9
assert SM.score(P["A"], P["A"]) > 0.95, SM.score(P["A"], P["A"])
assert s_t > s_tc + 0.2, (s_t, s_tc)                                            # names and numbers masked: the pattern is the same
assert 0 <= s_ab <= 1 and 0 <= s_ac <= 1
pt = SM.parts(P["T1"], P["T2"])
assert pt["title"] > 0.5 and pt["look"] is None, pt          # no look yet: left out, not zero
lk = {"captions": "low", "voice": "george", "style": "minimal"}
with_look = SM.parts(SM.profile(A, lk), SM.profile(B, {**lk, "voice": "emma"}))
assert abs(with_look["look"] - 2 / 3) < 1e-9, with_look
w = SM.DEFAULTS["weights"]
assert abs(SM.combine({"narration": 1.0, "title": None, "opening": None, "look": None, "structure": None}, w) - 1.0) < 1e-9   # weights scaled up
assert SM.mask_tokens("Walter Koenig scored 3 goals") == ["NAME", "scored", "NUM", "goals"], SM.mask_tokens("Walter Koenig scored 3 goals")
assert SM.strip_title("Film Facts #3: Wildwood \U0001F3AC") == "Wildwood"
best = SM.check(P["B"], [P["C"], P["A"], P["T1"]])
assert best["with"] == "QD-001" and best["max"] == round(SM.score(P["B"], P["A"]), 3) and "audition" in best["matched"] or "narration" in best["matched"], best
assert SM.check(P["A"], [P["A"]])["max"] == 0.0 and SM.check(P["A"], [])["with"] == ""          # never compared with itself
print("1 scores ok")

# 2. calibration: percentiles, and the best-to-recent distribution a threshold comes from
assert abs(SM.percentile(list(range(1, 101)), 0.97) - 97.03) < 1e-9 and SM.percentile([], 0.5) is None
rng = random.Random(5)
VOCAB = ["".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(6)) for _ in range(400)]
corpus = []
for i in range(60):
    says = [" ".join(rng.sample(VOCAB, 12)) for _ in range(5)]
    corpus.append(board(100 + i, " ".join(rng.sample(VOCAB, 4)), says, fmt=rng.choice(["one_detail", "story", "timeline"]),
                        hook_type=rng.choice(["statement", "number"]), day=f"2026-10-{10 + i // 5:02d}"))
clone = json.loads(json.dumps(corpus[10])); clone["id"] = "QD-199"; clone["created"] = "2026-10-22"
by = {"main": [SM.profile(b) for b in corpus + [clone]]}
by["main"].sort(key=lambda p: (p["day"], p["id"]))
cal = SM.calibrate(by)["main"]
assert cal["boards"] == 61 and cal["pairs"] > 500 and cal["pair"]["p97"] >= cal["pair"]["p50"], cal
assert cal["best"]["p97"] >= cal["best"]["p50"] and cal["shares"]["p50"] < 0.35, cal              # six recipes among varied boards: none runs away
base = [p for p in by["main"] if p["id"] != "QD-199"]
varied = SM.calibrate({"main": base})["main"]["best"]["p97"]
assert SM.score(SM.profile(clone), SM.profile(corpus[10])) > varied + 0.3, varied                 # a clone is far over the varied boards' p97
cfg_live = json.loads(open("config.json").read())["sameness"]
assert 0.2 <= cfg_live["max_pair"] <= 0.45 and cfg_live["recipe_share_max"] == 0.35, cfg_live     # calibrated on the live boards (28 October)
print("2 calibration ok")

# 3. the channel score and the commonest recipe, per channel and UK day, in analytics/sameness.csv and .md
tmp = _p.Path(tempfile.mkdtemp(prefix="qp-same-"))
(tmp / "analytics").mkdir()
rows = SM.write_outputs(tmp, dt.date(2026, 10, 28), None, by_channel=by)
got = list(csv.DictReader((tmp / "analytics" / "sameness.csv").open()))
assert got and set(got[0]) == set(SM.FIELDS) and all(r["channel"] == "main" for r in got), got[:1]
last = got[-1]
assert last["day"] == "2026-10-28" and 0 < float(last["score"]) < 0.3 and int(last["boards"]) >= 30, last
win = SM.in_window(by["main"], dt.date(2026, 10, 28), 14)
assert int(last["boards"]) == len(win) and last["top_recipe"] == SM.top_recipe(win)[0], (last, SM.top_recipe(win))      # the window's own commonest recipe
assert abs(float(last["share"]) - SM.top_recipe(win)[1]) < 1e-3
md = (tmp / "analytics" / "sameness.md").read_text()
assert "main: score" in md and "alert" in md and not any(c in md for c in DASHES), md[:300]
before = len(got)
SM.write_outputs(tmp, dt.date(2026, 10, 28), None, by_channel=by)                                     # run again: rows replaced, not doubled
assert len(list(csv.DictReader((tmp / "analytics" / "sameness.csv").open()))) == before
# the recipe: format + hook type + look + series; a draft's look is unknown
q = SM.profile(board(7, "t", ["one two three four"], fmt="story", hook_type="number", series="Film Facts"), {"style": "minimal", "captions": "low"})
assert SM.recipe_key(q) == "story|number|minimal+low|Film Facts" and SM.recipe_key(q, with_look=False) == "story|number||Film Facts"
same = [SM.profile(board(10 + i, f"t{i}", [f"alpha {i} beta gamma delta"], fmt="one_detail")) for i in range(8)]
oth = [SM.profile(board(30 + i, f"u{i}", [f"alpha {i} beta gamma delta"], fmt="story")) for i in range(2)]
key, share = SM.top_recipe(same + oth)
assert key.startswith("one_detail") and abs(share - 0.8) < 1e-9
assert SM.over_recipe(same + oth) and SM.over_recipe(same[:3] + oth) is None and SM.over_recipe(same[:2]) is None    # under 10 boards: never
print("3 channel score ok")

# 4. the pair check in the writer: over the limit -> one rewrite by the same model naming the overlap -> accepted, or dropped
W.same_init(dt.date(2026, 10, 28))
W.SAME["by"] = {"main": [SM.profile(A)]}
W.SAME["cfg"] = SM.conf({"sameness": {"max_pair": 0.30}})
W.CFG["sameness"] = {"max_pair": 0.30, "on": True}
calls = []
fresh = board(9, "Rocket booster flies twice in a week", ["A used booster flew again.", "Rocket Lab caught it by helicopter.", "Small satellites get cheaper."],
              writer="groq:llama")
dup = json.loads(json.dumps(B)); dup["id"] = "QD-009"; dup["writer"] = "gemini:flash"
def fake_write(rewrites):
    def f(p, sid, day, head, extra="", kind="news", tests=None, force=None):
        calls.append({"extra": extra, "force": force})
        r = rewrites.pop(0)
        return (json.loads(json.dumps(r)) if r else None), "rewrite"
    return f
W.write_board = fake_write([fresh])
b, note = W.sameness_gate(json.loads(json.dumps(dup)), {"topic": "x"}, "QD-009", "2026-10-28", "HEAD", "EXTRA", "news", {}, "gemini:flash, 0 warnings")
assert b and b["meta"]["title"] == fresh["meta"]["title"] and "after a rewrite" in note and W.SAME["rewrites"] == 1 and W.SAME["drops"] == 0, note
assert len(calls) == 1 and calls[0]["force"] == "gemini:flash", calls                                # the same model
assert "QD-001" in calls[0]["extra"] and "Walter Koenig: the audition secret you never knew" in calls[0]["extra"] and "What matched" in calls[0]["extra"]
assert "EXTRA" in calls[0]["extra"] and "SAMENESS CHECK" in calls[0]["extra"]
W.write_board = fake_write([dup])                                                                    # still over: dropped, with the reason
b, note = W.sameness_gate(json.loads(json.dumps(dup)), {"topic": "x"}, "QD-009", "2026-10-28", "HEAD", "", "news", {}, "n")
assert b is None and note.startswith("dropped for sameness") and "QD-001" in note and "after one rewrite" in note and W.SAME["drops"] == 1, note
W.write_board = fake_write([None])                                                                   # the rewrite failed its checks: dropped
b, note = W.sameness_gate(json.loads(json.dumps(dup)), {"topic": "x"}, "QD-009", "2026-10-28", "HEAD", "", "news", {}, "n")
assert b is None and W.SAME["drops"] == 2
W.write_board = fake_write([fresh])                                                                  # under the limit: no rewrite at all
n_before = len(calls)
b, note = W.sameness_gate(json.loads(json.dumps(C)), {"topic": "x"}, "QD-010", "2026-10-28", "HEAD", "", "news", {}, "n")
assert b is not None and len(calls) == n_before and "sameness 0." in note and "after a rewrite" not in note, note
mega = json.loads(json.dumps(dup)); mega["mega"] = "yes"; mega["reserve"] = True                      # a mega trend's or reserve board: no exemption
W.write_board = fake_write([dup])
b, note = W.sameness_gate(mega, {"topic": "x"}, "QD-011", "2026-10-28", "HEAD", "", "news", {}, "n")
assert b is None, note
W.write_board = fake_write([dup])                                                                    # the earlier parts of its own series are no repeat
b, note = W.sameness_gate(json.loads(json.dumps(dup)), {"topic": "x"}, "QD-009", "2026-10-28", "HEAD", "", "news", {}, "n", skip={"QD-001"})
assert b is not None and "rewrite" not in note, note
off = W.CFG["sameness"]; W.CFG["sameness"] = {"on": False}                                           # switched off: a board passes untouched
assert W.sameness_gate(json.loads(json.dumps(dup)), {}, "QD-009", "2026-10-28", "H", "", "news", {}, "n")[1] == "n"
W.CFG["sameness"] = off
# the record on the board
rec = json.loads(json.dumps(C)); W.SAME["by"] = {"main": [SM.profile(A), SM.profile(B)]}
W.same_record(rec, "main")
assert rec["sameness"] < 0.3 and 0 < rec["sameness_recipe_share"] <= 1 and rec["sameness_with"] in ("QD-001", "QD-002"), rec
assert len(W.SAME["by"]["main"]) == 3                                                                # it joins the window for the Shorts after it
print("4 rewrite then drop ok")

# 5. the recipe cap: a recipe over its share of the window -> another format; mega, the reserve and a control Short exempt
W.SAME["by"] = {"main": [SM.profile(board(200 + i, f"t{i}", [f"alpha {i} beta gamma delta epsilon"], fmt="one_detail")) for i in range(12)]
                + [SM.profile(board(300 + i, f"u{i}", [f"zeta {i} eta theta iota kappa"], fmt="story", hook_type="number")) for i in range(2)]}
W.SAME["cfg"] = SM.conf(None)
capped, note = W.recipe_cap_for(77)
assert capped == "one_detail" and "RECIPE CAP" in note and "one_detail" not in note.split("Use the ")[1].split(" format")[0], (capped, note)
other = note.split("Use the ")[1].split(" format")[0]
assert other in {x["id"] for x in json.loads(open("templates/formats.json").read())["formats"]}, other
assert W.recipe_cap_for(77) == (capped, note)                                                        # drawn on a seed of k: the same each time
assert W.recipe_cap_for(77, mega=True) == ("", "") and W.recipe_cap_for(77, reserve=True) == ("", "") and W.recipe_cap_for(77, control=True) == ("", "")
W.SAME["by"]["main"] = W.SAME["by"]["main"][5:]                                                      # 7 + 2 boards: under the 10 needed, no cap
assert W.recipe_cap_for(77) == ("", "")
W.SAME["by"] = {"main": [SM.profile(board(400 + 10 * j + i, f"t{j}{i}", [f"alpha{j} {i} beta gamma delta epsilon"], fmt=f))
                         for j, f in enumerate(("one_detail", "story", "timeline")) for i in range(4)]}
assert W.recipe_cap_for(77) == ("", "")                                                              # three recipes at 33% each: none over 35%
print("5 recipe cap ok")

# 6. the alert: one issue (not needs-charlie) when a channel's score is over sameness.alert on 2 days running; closed when not
import alerts as A
sent = []
A.raise_issue = lambda title, body, labels=None, howto=None: sent.append((title, body, labels, howto)) or 1
closed = []
A.clear = lambda title, body: closed.append(title)
mk = lambda ch, day, sc: {"channel": ch, "day": day, "score": str(sc), "top_recipe": "one_detail|statement|clean|", "share": "0.4", "boards": "30"}
assert A.sameness_alert([mk("main", "2026-10-26", 0.3), mk("main", "2026-10-27", 0.31), mk("clips", "2026-10-27", 0.1), mk("clips", "2026-10-26", 0.5)]) == ["main"]
assert len(sent) == 1 and sent[0][2] is None and "main" in sent[0][1] and "40%" in sent[0][1] and not any(c in sent[0][1] for c in DASHES), sent
assert A.sameness_alert([mk("main", "2026-10-26", 0.1), mk("main", "2026-10-27", 0.31)]) == [] and closed       # one day over is not two
assert A.sameness_alert([mk("main", "2026-10-24", 0.3), mk("main", "2026-10-27", 0.31)]) == []                  # not on days running
assert A.sameness_alert([mk("main", "2026-10-26", 0.3)]) == []                                                   # one row: not enough
print("6 alert ok")

# 7. the ledger: "sameness" is a metric (lower is better) and a default guardrail of every change
import changes as CH
assert CH.METRICS["sameness"][1] == "lower"
r = CH.add("writer", "a change", "it helps", "yt_views_24h", "uploads_day", rows=[])
assert "sameness" in r["guardrails"].split(";") and "uploads_day" in r["guardrails"], r
r = CH.add("writer", "the guard", "it varies", "sameness", "uploads_day;yt_views_day", rows=[])
assert r["target"] == "sameness" and "sameness" not in r["guardrails"].split(";"), r                            # a target is not its own guardrail
print("7 ledger ok")

# 8. nothing this change writes holds an en or em dash
for f in ("pipeline/sameness.py", "pipeline/control.py", "analytics/sameness.md", "analytics/control_recipe.json", "tests/test_sameness.py"):
    text = open(f, encoding="utf-8").read()
    assert not any(c in text for c in DASHES), f
cfg = json.dumps(json.loads(open("config.json").read()).get("sameness_note", "")) + json.dumps(json.loads(open("config.json").read()).get("control_note", ""))
assert not any(c in cfg for c in DASHES)
assert not any(c in W.recipe_cap_for.__doc__ + W.sameness_gate.__doc__ for c in DASHES)
print("8 no dashes ok")
print("sameness tests ok")
