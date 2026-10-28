"""Offline test of the frozen control group (pipeline/control.py and its hooks, 28 October): the seeded draw (independent of every
other draw, about 10%), who can be a control Short, what one is written with (the frozen tests, style line, Recipe, look; no round
arm, gene or exploration), the freeze, a whole writer run, the first free posting slot, the verdicts leaving control Shorts out,
and the loop-against-control maths in trend.py (paired by channel and UK day, heat allowed for, the 90% interval, "too few to
tell"). No network, no model; the live boards are untouched (a test run's boards are removed again)."""
import pathlib as _p, sys, os, json, csv, math, random, datetime as dt, tempfile, collections
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(tempfile.mkdtemp(prefix="qp-control-"))
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
os.environ["WRITE_DRY"] = "1"
import control as CT
import writer as W, factpack as F, validate as V
import drivers as D, trend as T, evolve as EV
W.CFG["shorts_channels"] = {}
DASHES = (chr(0x2013), chr(0x2014))
CFG = {"control": {"on": True, "share": 0.1}}

# 1. the draw: board number k, its own seed, about 10%, independent of every other draw and of the run's state
hits = [k for k in range(1, 5001) if CT.drawn(k, CFG)]
assert 0.085 < len(hits) / 5000 < 0.115, len(hits)
assert all(CT.drawn(k, CFG) == (random.Random(f"control:{k}").random() < 0.1) for k in range(1, 400))
random.seed(1); a = [CT.drawn(k, CFG) for k in range(300)]
random.seed(999); [random.random() for _ in range(100)]; b = [CT.drawn(k, CFG) for k in range(300)]
assert a == b                                                         # not the global random state
for mod in (2, 4, 8):                                                 # the replies arm (k % 2), the title arms ((k // 2) % 2, (k // 4) % 2)
    share = sum(1 for k in hits if (k // (mod // 2 or 1)) % 2 == 0) / len(hits)
    assert 0.4 < share < 0.6, (mod, share)
arms = collections.Counter()
for k in range(1, 5001):                                              # the round's arm draws (writer.test_plan) and the explore draw
    arm = random.Random(f"round 1:hook_type:{k}").choice(["statement", "number"])
    arms[(arm, CT.drawn(k, CFG))] += 1
for arm in ("statement", "number"):
    r = arms[(arm, True)] / (arms[(arm, True)] + arms[(arm, False)])
    assert 0.07 < r < 0.13, (arm, r)
assert CT.drawn(5, {"control": {"on": False, "share": 1.0}}) is False and CT.drawn(5, {}) is False
assert all(CT.drawn(k, {"control": {"on": True, "share": 1.0}}) for k in range(50)) and not any(CT.drawn(k, {"control": {"on": True, "share": 0.0}}) for k in range(50))
print("1 draw ok")

# 2. who can be a control Short: a normal quota Short of the main channel, nothing else
assert CT.eligible("news") and CT.eligible("evergreen")
for kw in ({"reserve": True}, {"mega": True}, {"explore": True}, {"follow": True}, {"part": True}, {"channel": "music"}):
    assert not CT.eligible("news", **kw), kw
for kind in ("follow-up", "breaking", "remake", "top list", "true story", "fiction"):
    assert not CT.eligible(kind), kind
SNAP = {"frozen": "2026-10-28", "winners": {"length": "25 to 34 s", "gene:g001": "b", "round": "x"}, "paused": {}, "genes": {"hooks": "Frozen gene text."},
        "recipe": "(frozen) - Hook style: FROZEN_RECIPE_LINE", "dropoff": ["frozen note"], "title": {"title_emoji": "emoji", "title_answer": "stated"},
        "sub_push": "none", "looks": {"captions": {"low": 1.0}, "style": {"minimal": 1.0}, "voice": {"lewis": 0.4, "daniel": 0.4, "george": 0.2}}}
(SCRATCH / "snap.json").write_text(json.dumps(SNAP))
CT.SNAP = SCRATCH / "snap.json"
assert CT.load()["frozen"] == "2026-10-28" and CT.is_control(next(iter(hits)), "news", CFG)
assert not CT.is_control(next(iter(hits)), "news", CFG, mega=True)
CT.SNAP = SCRATCH / "missing.json"
assert CT.load() == {} and not CT.is_control(next(iter(hits)), "news", CFG)          # nothing frozen yet: nobody is a control Short
CT.SNAP = SCRATCH / "snap.json"
print("2 eligible ok")

# 3. what a control Short is written with
t = CT.tests(7, ["length", "hook_type", "series"], no_title=("title_answer",))
assert t == {"length": "25 to 34 s", "title_emoji": "emoji", "sub_push": "none", "replies": "off", "explore": "no"}, t         # frozen winner only; no round, no gene
assert CT.tests(8, ["length"])["replies"] == "on" and CT.tests(8, ["length"])["title_answer"] == "stated"
lk = CT.look(5)
assert lk["captions"] == "low" and lk["style"] == "minimal" and lk["voice"] in ("lewis", "daniel") and lk == CT.look(5), lk      # seeded, from the spread
assert {CT.look(k)["voice"] for k in range(60)} == {"lewis", "daniel"}      # george is retired in the catalogue: never drawn
assert W.style_note({"length": "25 to 34 s"}, control=True).count("Frozen gene text.") == 1 and "FROZEN" not in W.style_note({"length": "25 to 34 s"})
assert W.style_note({"length": "25 to 34 s"}, control=True).startswith("STYLE FOR THIS SHORT")
print("3 recipe ok")

# 4. the freeze: today's recipe copied once, never overwritten by accident
CT.SNAP = SCRATCH / "frozen.json"
snap = CT.freeze(dt.date(2026, 10, 28), W)
assert snap["frozen"] == "2026-10-28" and set(snap) >= {"winners", "paused", "genes", "champions", "recipe", "dropoff", "title", "sub_push", "looks"}, set(snap)
assert snap["title"]["title_emoji"] in W.TITLE_TESTS["title_emoji"] and snap["title"]["title_answer"] in W.TITLE_TESTS["title_answer"]
assert snap["sub_push"] in ("spoken", "none") and CT.load() == snap
try: CT.freeze(dt.date(2026, 10, 29), W); raise AssertionError("overwrote a frozen recipe")
except SystemExit: pass
CT.SNAP = SCRATCH / "snap.json"
live = json.loads(open("analytics/control_recipe.json").read())
assert live["frozen"] == "2026-10-28" == json.loads(open("config.json").read())["control"]["frozen"], live["frozen"]
assert not any(c in open("analytics/control_recipe.json", encoding="utf-8").read() for c in DASHES)
print("4 freeze ok")

# 5. a whole writer run with every normal Short a control Short: marked, frozen, looked up, left alone by the arms and the editor
import series as SER
SER.suggest = lambda *a, **k: []
ex = json.loads(W.example())
SENT = ["Minecraft is the best-selling video game of all time with over 300 million copies sold.",
        "Grand Theft Auto V is second with more than 210 million copies sold.",
        "Tetris has sold around 100 million copies in its paid mobile versions alone.",
        "Wii Sports sold 82.9 million copies, mostly bundled with the Wii.",
        "PUBG: Battlegrounds has sold 75 million copies on PC and consoles.",
        "Mario Kart 8 and its Deluxe version together sold over 75 million copies."]
TEXT = (" ".join(SENT) + " ") * 3
prompts = []


def fake(prompt, schema=None, timeout=100, temperature=0.1, lite=False, **kw):
    kind = ("plan" if prompt.startswith("You plan evergreen") else "facts" if prompt.startswith("You check facts for a family-friendly Shorts channel. The Short is about")
            else "translate" if prompt.startswith("Translate") else "check" if prompt.startswith("You check a YouTube Short") else "write")
    if kind == "plan":
        return {"items": [{"kind": "top list", "idea": "Top 10 best-selling video games", "category": "Gaming", "wikipedia": "List of best-selling video games"},
                          {"kind": "true story", "idea": "How Tetris escaped the Soviet Union", "category": "Gaming", "wikipedia": "Tetris"},
                          {"kind": "question", "idea": "Why is Minecraft so popular", "category": "Gaming", "wikipedia": "Minecraft"},
                          {"kind": "question", "idea": "Why is Wii Sports so popular", "category": "Gaming", "wikipedia": "Wii Sports"},
                          {"kind": "question", "idea": "Why is Mario Kart so popular", "category": "Gaming", "wikipedia": "Mario Kart 8"}]}, "f"
    if kind == "facts":
        return {"what_is_new": "", "hooks": ["Number 1 sold 300 million"], "facts": [{"claim": s, "evidence": [{"source": 1, "quote": s}]} for s in SENT]}, "f"
    if kind in ("translate", "check"): return ({} if kind == "translate" else {"ok": True}), "f"
    prompts.append(prompt)
    b = json.loads(json.dumps(ex)); b["meta"]["title"] = f"Test {len(prompts)} \U0001F3AE"
    return b, "f"


F.gemini = fake
F.page_text = lambda url, wiki=False: (TEXT, "")
d = json.loads(F.OUT.read_text()); d["mode"] = "full"; d["topics"] = []
F.OUT = _p.Path(SCRATCH / "facts_full.json"); F.OUT.write_text(json.dumps(d))
W.reserve_count = lambda: 9
W.recent = lambda days=14: []
W.pick_kinds = lambda n: (["evergreen", "top list", "evergreen", "true story", "evergreen", "evergreen"] * 3)[:n]
W.plan = lambda breaking=False, hint="": ("morning", dt.date(2026, 10, 21), 6)
W.SM.write_outputs = lambda *a, **k: []                      # the run's sameness files are not the test's business
W.CFG["sameness"] = {"on": True, "max_pair": 5.0}            # the stub writes one script every time: record its sameness, drop nothing
W.CFG["control"] = {"on": True, "share": 1.0}
W.claude_edit = lambda b, p, kind, note: (_ for _ in ()).throw(AssertionError("a control Short is never edited by Claude"))
before = {p.name for p in _p.Path("boards/queue").glob("QD-*.json")}


def run():
    prompts.clear()
    W.main()
    new = sorted(p for p in _p.Path("boards/queue").glob("QD-*.json") if p.name not in before)
    got = [json.loads(p.read_text()) for p in new]
    for p in new: p.unlink()
    return got


try:
    got = run()
    ctl, rest = [b for b in got if b.get("control")], [b for b in got if not b.get("control")]
    assert ctl and rest, [(b["id"], b["kind"], b.get("control")) for b in got]
    assert all(b["kind"] in ("news", "evergreen") and not b.get("reserve") for b in ctl), [(b["kind"], b.get("control")) for b in got]
    assert all(b["kind"] not in ("news", "evergreen") or b.get("reserve") for b in rest), [(b["kind"], b.get("reserve"), b.get("control")) for b in got]      # the reserve is never one
    for b in ctl:
        t = b["test"]
        assert b["control"] == 1 and t["explore"] == "no" and t["length"] == "25 to 34 s" and t["sub_push"] == "none" and t["title_emoji"] == "emoji", t
        assert "round" not in t and not any(k.startswith("gene:") for k in t) and not any(k in t for k in ("hook_type", "first_frame", "fx_energy", "fx_slot", "angles")), t
        assert b["look"]["captions"] == "low" and b["look"]["style"] == "minimal", b.get("look")
        assert not [e for e in V.check(b)[0] if e.startswith("look")], V.check(b)[0]
        assert "sameness" in b and "sameness_recipe_share" in b and b["writer"].startswith("gemini:"), b
    assert any("round" in b["test"] for b in rest)                                                   # everyone else is in the round
    assert not any("look" in b for b in rest) and not any("control" in b for b in rest)
    mine = [pr for pr in prompts if "FROZEN_RECIPE_LINE" in pr]
    assert len(mine) >= len(ctl) and all("Frozen gene text." in pr and "frozen note" in pr for pr in mine), len(mine)      # the frozen head
    assert all("FROZEN_RECIPE_LINE" not in pr for pr in prompts if "Frozen gene text." not in pr)
    print("5 a control run ok:", [(b["id"], b["kind"]) for b in ctl])
    W.CFG["control"] = {"on": True, "share": 0.0}
    got = run()
    assert got and not any(b.get("control") or "look" in b for b in got) and any("round" in b["test"] for b in got if b["kind"] in ("news", "evergreen"))
    W.CFG["control"] = {"on": False, "share": 1.0}
    assert not any(b.get("control") for b in run())
finally:
    for p in _p.Path("boards/queue").glob("QD-*.json"):
        if p.name not in before: p.unlink()
print("5 share 0 and off ok")

# 6. the first free posting slot, not the learned best quarter
import plan as P
P.ROOT = SCRATCH
(SCRATCH / "analytics").mkdir(exist_ok=True)
P.learned_slots = lambda n: [f"{h:02d}:00" for h in range(24)]
P.LEAD = dt.timedelta(hours=1)
(SCRATCH / "analytics" / "slots.json").write_text(json.dumps({"bands": {"Music": {"00-06": {"n": 8, "score": 4.5}, "06-12": {"n": 4, "score": 1.2},
                                                                                  "12-18": {"n": 11, "score": 1.0}, "18-24": {"n": 3, "score": 1.0}}}}))
now = dt.datetime(2026, 10, 24, 13, 10, tzinfo=P.UK).astimezone(dt.timezone.utc)
learned = [P.slot_picker(now, set())("2026-10-24", "Music", "evergreen", f"QD-{i}").astimezone(P.UK).hour for i in range(40)]
plain = {P.slot_picker(now, set())("2026-10-24", "Music", "evergreen", f"QD-{i}", plain=True).astimezone(P.UK).hour for i in range(40)}
assert plain == {15} and 0 in learned, (plain, set(learned))
print("6 slot ok")

# 7. the verdicts leave control Shorts out: drivers, the round, channel drivers, subscriber drivers, evolve's examples, look scores
now = dt.datetime.now(dt.timezone.utc)
rng = random.Random(3)


def drow(i, cat, rel, ctl=False, **kw):
    posted = now - dt.timedelta(hours=30 + i * 5)
    return {"short": f"T-{i:03d}", "posted": posted.isoformat(timespec="minutes"), "posted_day": str(posted.date()), "yt_views": "1000", "rel": rel,
            "category": cat, "format": "one_detail", "hook": "A hook here", "seconds": "30", "slot_uk": "09:00", "title": "t",
            "yt_subs_gained": str(rng.choice([0, 1, 2])), "arm_hook_type": "number" if i % 2 else "statement", "channel": "main",
            "control_arm": "1" if ctl else "", **kw}


normal = [drow(i, "Music" if i % 3 == 0 else "Film", round(math.exp(rng.gauss(1.0 if i % 3 == 0 else -0.3, 0.4)), 3)) for i in range(60)]
ctrl = [drow(100 + i, "Gaming", 9.0, ctl=True, arm_hook_type="number", yt_subs_gained="40") for i in range(25)]
t_with, _ = D.analyse(normal + ctrl, {}, "2026-10-28")
t_without, _ = D.analyse(normal, {}, "2026-10-28")
assert t_with == t_without and not any(r["value"] == "Gaming" for r in t_with), "control Shorts changed a verdict"
cat = {r["value"]: r["verdict"] for r in t_with if r["feature"] == "category"}
assert cat.get("Music") == "push", cat
assert D.channel_table(normal + ctrl, t_with) == D.channel_table(normal, t_with)
rf, st = {"hook_type": ["statement", "number"]}, "2026-10-01"
assert D.round_verdicts(normal + ctrl, rf, st, 70, "round 1") == D.round_verdicts(normal, rf, st, 70, "round 1")
assert D.analyse_subscribers(normal + ctrl, now) == D.analyse_subscribers(normal, now) and D.subs_summary(normal + ctrl, now) == D.subs_summary(normal, now)
EV.ROOT = SCRATCH
(SCRATCH / "analytics").mkdir(exist_ok=True)
with (SCRATCH / "analytics" / "shorts.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["short", "posted_day", "hook", "views_vs_typical", "control_arm", "title", "yt_engaged_pct"]); w.writeheader()
    for i, r in enumerate(normal[:5] + ctrl[:5]):
        w.writerow({"short": f"QD-{i}", "posted_day": str(now.date()), "hook": "h", "views_vs_typical": r["rel"], "control_arm": r["control_arm"], "title": "t", "yt_engaged_pct": 30})
top, low = EV.recent_shorts(str(now.date()), 14, 8)
assert top and not any(r.get("control_arm") == "1" for _, r in top + low), top
import analytics as AN
lrows = [{"short": f"QD-{900 + i}", "posted": (AN.NOW - dt.timedelta(days=3, hours=i)).isoformat(), "yt_views": 100, "yt_engaged_pct": 30, "yt_avg_viewed_pct": 50,
          "views_per_hour": 5, "control_arm": "", "writer": "gemini:m", "channel": "main", "slot_uk": "10:00", "views_vs_typical": 1.0, "category": "Film"} for i in range(10)] \
    + [{"short": f"QD-{950 + i}", "posted": (AN.NOW - dt.timedelta(days=3, hours=i)).isoformat(), "yt_views": 100, "yt_engaged_pct": 95, "yt_avg_viewed_pct": 95,
        "views_per_hour": 90, "control_arm": "1", "writer": "gemini:m", "channel": "main", "slot_uk": "10:00", "views_vs_typical": 9.0, "category": "Film"} for i in range(10)]
AN.look_scores(lrows)
assert all(r["look_score"] == 1.0 for r in lrows[:10]) and all(r["look_score"] == "" for r in lrows[10:]), [r["look_score"] for r in lrows]   # no score, and no peer for the others
assert AN.our_shorts is not None and "control_arm" in open("pipeline/analytics.py").read().split("def our_shorts")[1].split("def youtube")[0]
print("7 learning exclusion ok")

# 8. the loop against the frozen control: paired by channel and UK day, a ratio with a 90% interval, heat allowed for
NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)


def lrow(day, i, ctl, logv, eng=30.0, subs=1, views=1000, heat="", **kw):
    posted = dt.datetime(2026, 10, day, 8 + i % 8, 0, tzinfo=dt.timezone.utc)
    return {"short": f"QD-{day}-{i}-{int(ctl)}", "posted": posted.isoformat(), "channel": "main", "kind": "news", "control_arm": "1" if ctl else "", "mega": "", "viral": "",
            "views_24h": f"{math.exp(logv):.1f}", "yt_engaged_pct": f"{eng:.1f}", "yt_views": str(views), "yt_subs_gained": str(subs), "heat": heat, "heat_covered": "yes" if heat != "" else "", **kw}


rng = random.Random(11)
rows = []
for day in range(10, 20):                                                        # 10 days, 4 loop Shorts and 2 control Shorts each
    u = rng.gauss(5.0, 0.5)                                                      # the day's own luck, shared by both kinds
    for i in range(4): rows.append(lrow(day, i, False, u + 0.4 + rng.gauss(0, 0.2), eng=30 + rng.gauss(0, 2), subs=rng.choice([1, 2, 3, 3])))
    for i in range(2): rows.append(lrow(day, i, True, u + rng.gauss(0, 0.2), eng=30 + rng.gauss(0, 2), subs=rng.choice([0, 1, 1, 2])))
rows.append(lrow(20, 0, False, 9.0))                                             # a day with no control Short: not paired
rows += [lrow(14, 5, False, 12.0, mega="yes"), lrow(14, 6, False, 12.0, viral="yes"), lrow(14, 7, False, 12.0, kind="top list"), lrow(14, 3, False, 12.0, channel="music")]
res = T.loop_vs_control(rows, NOW)
v = res["metrics"]["views_24h"]
assert res["n_control"] == 20 and res["days"] == 10 and res["verdict"] != "too few to tell (20)", res
assert 1.25 < v["ratio"] < 1.8 and v["lo"] < v["ratio"] < v["hi"] and v["lo"] > 1 and v["verdict"] == "loop ahead" and v["adjusted"] is False, v     # e^0.4 = 1.49
e = res["metrics"]["yt_engaged_pct"]
assert 0.9 < e["ratio"] < 1.1 and e["lo"] <= 1 <= e["hi"] and e["verdict"] == "no clear difference", e                                           # nothing there
s = res["metrics"]["subs_per_1k"]
assert 1.2 < s["ratio"] < 3.0 and s["lo"] < s["ratio"] < s["hi"], s                                                                               # about 2.4 per Short against 1.0
assert res["verdict"] == "loop ahead on views at 24 hours" or res["verdict"].startswith("loop ahead on"), res["verdict"]
assert "90% interval" in res["summary"] and "10 days" in res["summary"] and not any(c in res["summary"] for c in DASHES), res["summary"]
assert T.loop_vs_control(rows, NOW) == res                                                                                                        # seeded: the same each run
five = [r for r in rows if r["control_arm"] == "1"][:5]
few = T.loop_vs_control([r for r in rows if r["control_arm"] != "1"] + five, NOW)
assert few["verdict"] == "too few to tell (5)" and few["metrics"] == {} and "3 days or more" in few["summary"], few
one_day = [r for r in rows if r["control_arm"] != "1" or r["short"].startswith("QD-10-")]       # enough Shorts (2), but too few days
assert T.loop_vs_control(one_day, NOW)["verdict"].startswith("too few to tell")
three = [r for r in rows if r["control_arm"] != "1"] + [r for r in rows if r["control_arm"] == "1"][:3]
assert T.loop_vs_control(three, NOW)["verdict"] == "too few to tell (3)"
assert T.loop_vs_control([], NOW)["verdict"] == "too few to tell (0)"
young = [dict(r, posted=(NOW - dt.timedelta(hours=5)).isoformat()) for r in rows]
assert T.loop_vs_control(young, NOW)["verdict"] == "too few to tell (0)"                                                                          # under 24 hours: not counted
# topic heat: the loop's topics ran 1.0 hotter and heat moves views (0.5 a point), nothing else differs
hrows = []
for day in range(10, 20):
    u = rng.gauss(5.0, 0.4)
    for ctl in (False, True):
        for i in range(6):
            h = rng.gauss(1.0, 0.5) + (1.0 if not ctl else 0.0)
            hrows.append(lrow(day, i, ctl, u + 0.5 * h + rng.gauss(0, 0.1), heat=f"{h:.2f}"))
hr = T.loop_vs_control(hrows, NOW)
hv = hr["metrics"]["views_24h"]
assert hv["raw"]["ratio"] > 1.4 and hv["raw"]["lo"] > 1, hv                                                      # raw: the loop looks 1.6x ahead
assert hv["adjusted"] is True and 0.8 < hv["ratio"] < 1.25 and hv["verdict"] != "loop ahead", hv                  # on equally hot topics it is level
tr = T.trend(rows, NOW)
assert tr["control"]["verdict"] == res["verdict"]
text = "\n".join(T.lines(tr))
assert "Loop vs frozen control: " in text and not any(c in text for c in DASHES), text
for name, content in (("shorts.csv", rows), ("daily.csv", []), ("changes.csv", []), ("decisions.csv", [])):
    (SCRATCH / "analytics" / name).write_text("")
with (SCRATCH / "analytics" / "shorts.csv").open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
path = T.write_history(NOW, src=SCRATCH / "analytics")
imp = json.loads(path.read_text())
assert imp["control"]["n_control"] == 20 and imp["control"]["metrics"]["views_24h"]["verdict"] == "loop ahead", imp["control"].get("summary")
few_json = T.loop_vs_control(rows[:8], NOW)
assert few_json["verdict"].startswith("too few to tell")
print("8 loop vs control ok:", res["summary"][:160])

# 9. the hub's line, and the ledger's view: a control Short is no part of a change's window
import hub_md as H
(SCRATCH / "config.json").write_text(json.dumps({"sameness": {"alert": 0.2, "window_days": 14, "recipe_share_max": 0.35}}))
(SCRATCH / "analytics" / "sameness.csv").write_text("channel,day,score,top_recipe,share,boards\nmain,2026-10-27,0.071,a|b||,0.1,100\nmain,2026-10-28,0.065,a|b||,0.05,110\n")
(SCRATCH / "analytics" / "improvement.json").write_text(json.dumps({"control": res}))
extra = H.better_extra(SCRATCH, H.jd(SCRATCH, "analytics/improvement.json"))
assert len(extra) == 2 and extra[0].startswith("Loop vs frozen control: ") and "0.07" in extra[1] and "alert at 0.2" in extra[1] and "limit 35%" in extra[1], extra
(SCRATCH / "analytics" / "sameness.md").write_text("x"); (SCRATCH / "analytics" / "joint.md").write_text("y")
page = H.build(SCRATCH)
assert "(analytics/sameness.md)" in page and "(analytics/joint.md)" in page and not any(c in page for c in DASHES)
(SCRATCH / "analytics" / "joint.md").unlink()
assert "joint.md" not in H.build(SCRATCH)                                                                         # missing: left out, no failure
import changes as CH
D2 = CH.Data.__new__(CH.Data)
D2.shorts = [{"_day": dt.date(2026, 10, 20), "control_arm": ""}, {"_day": dt.date(2026, 10, 20), "control_arm": "1"}]
assert len(D2.shorts_in(dt.date(2026, 10, 19), dt.date(2026, 10, 21))) == 1 and CH.shorts_per_day(D2)[dt.date(2026, 10, 20)] == 2   # judged without it, counted as a post
print("9 hub and ledger ok")
print("control tests ok")
