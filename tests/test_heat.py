"""Offline test of pipeline/heat.py (27 October): topic heat from the trend archive and Wikipedia reads, the cache, the
within-day effect, and how drivers, changes, trend and the insights allow for it, so a Short riding a trending story is not
credited (or blamed) on a change. No live file is read; HTTP is stubbed."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import datetime as dt, json, math, os, sys, types
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import heat as H

UTC = dt.timezone.utc
ARCH = SCRATCH / "arch"
ARCH.mkdir()
(ARCH / "2026-10-27.json").write_text(json.dumps({
    "google_trends": {"GB": [{"query": "Ballon d’Or 2026", "url": "https://example.com/ballon-dor"}]},
    "wikipedia_top": [{"article": "Ballon d'Or", "views": 400000}],
    "google_news_uk": [{"title": "Rain on Tuesday"}]}))


class R:
    def __init__(self, data=None, ok=True): self.ok, self.data = ok, data
    def json(self): return self.data


# 1. bands, names and terms
assert H.band(None) == "" and H.band("") == "" and H.band(1.6) == "hot" and H.band(0.6) == "warm" and H.band(0.1) == "cold"
assert H.names_in("Peyton Manning joins Golden State Warriors") == "Peyton Manning|Golden State Warriors"
assert H.names_in("a quiet day") == ""
assert H.terms(None, "Ballon d’Or") == ["ballon d'or"]                 # curly apostrophe matched as straight
assert H.terms("Lego (company)", "") == ["lego"] and H.terms(None, "Music") == []

# 2. the archive: Google Trends and Wikipedia top pages named it that day (0.7 + 0.5)
h, a, w, cov, why, subj = H.score(None, "Ballon d'Or", "2026-10-27", None, arch_dir=ARCH)
assert (h, a, w, cov) == (1.2, 1.2, 0.0, True), (h, a, w, cov)
assert "Google Trends" in why and "Wikipedia top pages" in why and subj == "Ballon d'Or"
assert H.score(None, "Ballon d'Or", "2026-10-28", None, arch_dir=ARCH)[:4] == (1.2, 1.2, 0.0, True)   # the day before counts too
assert H.score(None, "Ballon d'Or", "2026-09-01", None, arch_dir=ARCH)[3] is False                 # no archive: not covered
assert H.score(None, "Taylor Swift", "2026-10-27", None, arch_dir=ARCH)[:4] == (0.0, 0.0, 0.0, True)
assert H.score(None, "Ballon", "2026-10-27", None, arch_dir=ARCH)[0] == 1.2                         # whole words only
assert H.score(None, "Ballo", "2026-10-27", None, arch_dir=ARCH)[0] == 0.0

# 3. Wikipedia reads: 20,000 a day, then 400,000 on the day (level capped at 1.5, surge capped at 0.8)
asked = []
def wiki_get(u, params=None, headers=None, timeout=None):
    asked.append(u)
    items = []
    for k in range(16, -1, -1):
        d = dt.date(2026, 10, 27) - dt.timedelta(days=k)
        items.append({"timestamp": f"{d:%Y%m%d}00", "views": 400000 if k == 0 else 20000})
    return R({"items": items})
h, a, w, cov, why, _ = H.score("Ballon d'Or", "Ballon d'Or", "2026-10-27", wiki_get, arch_dir=ARCH, today=dt.date(2026, 10, 29))
assert w == 2.3 and h == 3.5 and 'Wikipedia "Ballon d\'Or"' in why and "20.0x its usual" in why, (h, w, why)
assert "Ballon_d%27Or/daily/20261011/20261027" in asked[-1]
assert H.wiki_part({}, "2026-10-27") == (0.0, "")
assert H.reads("Ballon d'Or", "2026-10-27", wiki_get, today=dt.date(2026, 10, 1)) == {}          # nothing to read yet

# 4. attach: measures, caches, reuses; a row whose day moved gets nothing
def no_get(u, params=None, headers=None, timeout=None): return R({}, ok=False)
CACHE = SCRATCH / "heat.csv"
rows = [{"short": "QD-1", "posted": "2026-10-27T12:00:00+00:00", "title": "Who won tonight", "_phrase": "Ballon d'Or"},
        {"short": "QD-2", "posted": "2026-10-27T15:00:00+00:00", "title": "Lego Batman set lands"},
        {"short": "", "posted": "2026-10-27T15:00:00+00:00", "title": "No key"}]
assert H.attach(rows, get=no_get, now=dt.datetime(2026, 10, 27, 20, tzinfo=UTC), path=CACHE, arch_dir=ARCH) == 2
assert (rows[0]["heat"], rows[0]["heat_band"], rows[0]["heat_covered"]) == (1.2, "warm", "yes"), rows[0]
assert (rows[1]["heat"], rows[1]["heat_band"], rows[1]["heat_covered"]) == (0.0, "cold", "yes"), rows[1]
assert (rows[2]["heat"], rows[2]["heat_band"]) == ("", "")
assert CACHE.exists() and "QD-1" in CACHE.read_text()
again = [dict(r, heat="") for r in rows[:2]]
assert H.attach(again, fetch=False, path=CACHE) == 0 and again[0]["heat"] == 1.2
moved = [dict(rows[0], posted="2026-10-20T12:00:00+00:00")]
H.attach(moved, fetch=False, path=CACHE)
assert moved[0]["heat"] == "" and moved[0]["heat_band"] == ""
later = dt.datetime(2026, 10, 30, 9, tzinfo=UTC)
assert H.attach([dict(r) for r in rows[:2]], get=no_get, now=later, path=CACHE, arch_dir=ARCH) == 2   # not final yet: measured again
assert H.attach([dict(r) for r in rows[:2]], get=no_get, now=later, path=CACHE, arch_dir=ARCH) == 0   # final now: kept

# 5. the effect of heat within a channel's day: y = 0.5 x heat, plus a little noise
def synth(b=0.5, days=10, per=4, channel="main"):
    out = []
    for d in range(days):
        for i in range(per):
            hh = (i + d) % per * 0.6
            y = b * hh + 0.03 * (((d * per + i) * 7) % 5 - 2)
            out.append({"short": f"S{channel}{d}-{i}", "channel": channel, "posted": f"2026-10-{d + 1:02d}T12:00:00+00:00",
                        "heat": hh, "heat_covered": "yes", "y": y, "views_24h": round(100 * math.exp(y), 3), "rel": math.exp(y)})
    return out
S = synth()
e = H.effect(S, lambda r: r["y"])
assert e and abs(e["b"] - 0.5) < 0.05 and e["clear"] and e["n"] == 40 and e["groups"] == 10, e
assert H.effect(S[:8], lambda r: r["y"]) is None                                   # under MIN_N
assert H.effect([dict(r, heat=1.0) for r in S], lambda r: r["y"]) is None          # no spread of heat
assert H.effect(S, lambda r: None) is None
flat = H.effect(synth(b=0.0), lambda r: r["y"])
assert flat and not flat["clear"], flat
two = synth() + synth(channel="clips")                                              # channels never share a group
assert H.effect(two, lambda r: r["y"])["groups"] == 20
assert H.note(e).startswith("each point of topic heat came with +65% views") and "(40 Shorts, clear)" in H.note(e)
assert H.note(None) == ""

# 6. centred and shift
C = H.centred(S[:4] + [{"short": "alone", "channel": "solo", "posted": "2026-10-01T12:00:00+00:00", "heat": 2.0},
                       {"short": "unknown", "posted": "2026-10-01T12:00:00+00:00", "heat": ""}])
vals = [S[i]["heat"] for i in range(4)]
assert abs(C[id(S[0])] - (S[0]["heat"] - sum(vals) / 4)) < 1e-9
assert list(C.values())[-2:] == [0.0, 0.0]
A3 = [{"heat": 0.5, "heat_covered": "yes"}] * 3; B3 = [{"heat": 1.5, "heat_covered": "yes"}] * 3
assert H.shift(A3, B3) == 1.0 and H.shift(A3, B3[:2]) is None
assert H.shift(A3, [{"heat": 1.5, "heat_covered": "no"}] * 3) is None             # an uncovered day is not a cold one

# 7. drivers: a push that only held because its Shorts had hotter topics than the day's others becomes an early sign
import drivers as D
eff = {"b": 0.8, "se": 0.1, "n": 40, "groups": 10, "clear": True}
grp = [{"short": f"G{i}", "posted": f"2026-10-{1 + i // 2:02d}T{10 + i % 2}:00:00+00:00", "rel": 2.2 + 0.05 * (i % 3)} for i in range(8)]
lift = math.exp(sum(D._logrel(r) for r in grp) / (len(grp) + D.SHRINK))
cut = D.split_time(grp)
assert D.gate(grp, lift, cut)[0] == "push", D.gate(grp, lift, cut)
hot = {id(r): 1.0 for r in grp}
v, why = D.heat_check(grp, "push", "", eff, hot, cut, "hook_type")
assert v == "early sign" and "equally hot topics" in why, (v, why)
assert D.heat_check(grp, "push", "", eff, hot, cut, "category") == ("push", "")       # a topic choice is meant to ride heat
assert D.heat_check(grp, "push", "", dict(eff, clear=False), hot, cut, "hook_type") == ("push", "")
assert D.heat_check(grp, "push", "", eff, {id(r): 0.1 for r in grp}, cut, "hook_type") == ("push", "")
assert D.heat_check(grp, "about typical", "", eff, hot, cut, "hook_type") == ("about typical", "")
assert "heat_band" in D.SELECTION and "viral" in D.SELECTION
measured = [dict(r, heat=1.5) for r in grp]
assert D.heat_of(measured, {id(r): 1.0 for r in measured}) == 1.0
assert D.heat_of(measured[:2], {id(r): 1.0 for r in measured}) is None and D.heat_of(grp, hot) is None   # unmeasured rows skipped

# 8. changes: the heat factor between a before and an after window
import changes as CH
Dn = types.SimpleNamespace(all_shorts=S)
before = [dict(r, heat=0.0) for r in S[:6]]; after = [dict(r, heat=1.0) for r in S[6:12]]
f, words = CH.heat_factor(Dn, "views_24h", before, after)
assert f and abs(f - math.exp(e["b"])) < 0.05 and "hotter by 1.0 heat" in words, (f, words)
assert CH.heat_factor(Dn, "views_24h", before, before) == (None, "")
assert CH.heat_factor(types.SimpleNamespace(all_shorts=synth(b=0.0)), "views_24h", before, after) == (None, "")

# 9. trend: the week's topics ran hotter, and what a point of heat is worth
import trend as T
hs = T.heat_shift(before, after, every=S)
assert hs and hs["shift"] == 1.0 and abs(hs["per_point"] - round(math.exp(e["b"]) - 1, 2)) < 0.03, hs
assert T.heat_shift(before, [dict(r, heat=0.1) for r in before], every=S) is None   # under HEAT_SHIFT
txt = T.heat_words(hs)
assert "ran hotter (by 1.0 heat" in txt and "part of any rise may be the topics" in txt, txt
assert "ran colder" in T.heat_words({"shift": -0.6}) and T.heat_words(None) == ""

# 10. the insights' Topic heat section
import analytics as AN
now = dt.datetime(2026, 10, 11, 9, tzinfo=UTC)
week = [dict(r, heat_band=H.band(r["heat"])) for r in S] + [dict(S[-1], short="V1", viral="yes", viral_angle="why", heat_band="hot")]
L = AN.heat_lines(week, now=now)
assert L[0].startswith("## Topic heat") and "+6" in L[1] and "same day's other Shorts" in L[1], L
assert any(x.startswith("- Last 7 days:") for x in L) and any("Viral topic pushes" in x and "why" in x for x in L), L
assert "Too few measured Shorts" in AN.heat_lines(S[:3], now=now)[1]

# 11. no dashes in anything a reader sees
for s in [H.note(e), why, words, txt] + L:
    assert "\u2013" not in s and "\u2014" not in s, s
print("heat ok")
