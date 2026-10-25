"""Offline test of the Spanish mirror (25 October): Quickplay Diario posts a Spanish version of the main channel's Shorts. No model,
network or sign-in is used; the translation model is a stand-in that answers from a table.
1. validate.py: a Spanish board (id QD-###-es, language es, mirror_of): the id and channel rules, a Spanish narration runs longer,
   Spanish banned and negative-framing words, and the English patterns are not run on Spanish text;
2. freshness.py: a Spanish Short's day is counted in New York with Spanish day words;
3. plan.py: the American-evening slot grid, and the render job (language es, channel es, no English voice model to fetch);
4. mirror.py: the words of a board, the checks on a translation (numbers, names, length, dashes, title), the board that comes out,
   a second try with what was wrong, who is mirrored (and who is not), the day's room per run, failed boards left after two tries,
   and nothing at all while the es channel is not signed in;
5. run_board.py: the Spanish voice and its fall back, the description in Spanish, the upload language;
6. tts_cb.py: the multilingual engine (language_id es, no English pronunciation list, no English speech check, a pace check,
   the built-in voice until the Kokoro reference exists) and make_voices.py's Spanish voices;
7. get_model.py --multilingual and render.yml: only a Spanish Short fetches the model, a failed fetch never fails the job;
8. writer.py and write.yml: the mirror runs after the main boards and its log is committed; on-screen name, label and call to action."""
import pathlib as _p, tempfile as _t
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
SCRATCH = _p.Path(_t.mkdtemp(prefix="qp-test-"))
import contextlib, copy, csv, datetime as dt, io, json, os, re, subprocess, sys, types
os.chdir(REPO_DIR)
sys.path.insert(0, REPO_DIR + "/pipeline")
for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "SAMBANOVA_API_KEY", "LLAMA_SERVER", "CLAUDE_CODE_OAUTH_TOKEN", "GEMINI_API_KEY"):
    os.environ.pop(k, None)
import numpy as np
import validate as V, freshness as FR, mirror as M, factpack

UK = FR.UK
TODAY = dt.datetime.now(UK).date()
day = lambda n=0: str(TODAY - dt.timedelta(days=n))


def shot(t, s):
    return {"src": f"commons-search:{t}", "move": "in", "label": {"t": t, "s": s}}


def beat(say, visual=None, shots=None):
    return {"say": say, "visual": visual or {"type": "none"}, "shots": shots or [shot("Olivia Rodrigo", "singer-songwriter")]}


EN = {
    "id": "QD-901", "created": day(), "format": "one_detail", "category": "Music", "music": {"mood": "pop"}, "appeal": "everyone",
    "kind": "evergreen", "source": "chart", "writer": "gemini:flash", "franchise": "Quickplay Music", "follows": "QD-800", "look": {"voice": "lewis"},
    "background": ["neon music club", "city night lights", "studio recording"],
    "test": {"length": "35 to 44 s", "title_emoji": "emoji", "hook_type": "statement", "fx_energy": "calm", "series": "named"},
    "beats": [
        beat("Olivia Rodrigo's new album has spent 12 weeks at number one on the American chart, and nobody saw it coming.",
             {"type": "title", "kicker": "NUMBER ONE", "lines": ["12 WEEKS", "AT THE TOP"], "highlight": [0]}),
        beat("Her second record sold 302,000 copies in its first week, the biggest debut of the year so far.",
             {"type": "stat", "value": "302,000", "label": "copies in week one", "sub": "the biggest debut of the year"}),
        beat("The title track was written in just 1 afternoon, then rebuilt with a full band in a London studio."),
        beat("Fans noticed that the cover photo shows the same jacket she wore at her first concert in Los Angeles."),
        beat("Critics from Rolling Stone and the BBC both gave the album four stars out of five."),
        beat("So which song is your favourite? Tell us in the comments."),
    ],
    "meta": {"title": "Olivia Rodrigo's album: 12 weeks at number one 🎵", "alt_title": "Her new album tops the chart 🎶",
             "summary": "Olivia Rodrigo's new album has spent 12 weeks at number one on the American chart after selling 302,000 copies in a week.",
             "hashtags": ["#OliviaRodrigo", "#Music", "#Pop", "#Album", "#Trending", "#NumberOne", "#NewMusic", "#Chart"],
             "tags": ["olivia rodrigo", "new album", "number one album", "pop music", "chart news"], "comment": "Which song is your favourite?",
             "sources": [["Billboard, the chart", "https://www.billboard.com/charts"], ["BBC, the album", "https://www.bbc.co.uk/news/album"]],
             "facts": [["Olivia Rodrigo's album has spent 12 weeks at number one.", [1, 2]]],
             "translations": {"es": {"title": "x", "summary": "y"}}},
}
ES = {
    "b0.say": "El nuevo álbum de Olivia Rodrigo lleva 12 semanas en el primer puesto de la lista estadounidense, y nadie lo vio venir.",
    "b0.v.kicker": "NÚMERO UNO", "b0.v.lines.0": "12 SEMANAS", "b0.v.lines.1": "EN LO MÁS ALTO", "b0.s0.role": "cantautora",
    "b1.say": "Su segundo disco vendió 302,000 copias en la primera semana, el mayor debut del año hasta ahora.",
    "b1.v.label": "copias en la primera semana", "b1.v.sub": "el mayor debut del año", "b1.s0.role": "cantautora",
    "b2.say": "La canción que da título al álbum se escribió en 1 sola tarde y luego se rehízo con una banda completa en un estudio de Londres.",
    "b2.s0.role": "cantautora",
    "b3.say": "Los fans notaron que la portada muestra la misma chaqueta que llevó en su primer concierto en Los Angeles.", "b3.s0.role": "cantautora",
    "b4.say": "Los críticos de Rolling Stone y de la BBC le dieron al álbum cuatro estrellas de cinco.", "b4.s0.role": "cantautora",
    "b5.say": "¿Y cuál es tu canción favorita? Cuéntanos en los comentarios.", "b5.s0.role": "cantautora",
    "meta.title": "Olivia Rodrigo: 12 semanas en el número 1 🎵", "meta.alt_title": "Su nuevo álbum lidera la lista 🎶",
    "meta.summary": "El nuevo álbum de Olivia Rodrigo lleva 12 semanas en el número uno de la lista estadounidense tras vender 302,000 copias en una semana.",
    "meta.comment": "¿Cuál es tu canción favorita?",
    "meta.tags.1": "nuevo álbum", "meta.tags.2": "álbum número uno", "meta.tags.3": "música pop", "meta.tags.4": "noticias de las listas",
    "meta.hashtags.0": "#OliviaRodrigo", "meta.hashtags.1": "#Música", "meta.hashtags.2": "#Pop", "meta.hashtags.3": "#Álbum",
    "meta.hashtags.4": "#Tendencia", "meta.hashtags.5": "#NumeroUno", "meta.hashtags.6": "#NuevaMúsica", "meta.hashtags.7": "#Ranking",
}
assert V.check(EN) == ([], []) or not V.check(EN)[0], V.check(EN)

# ---------- 1. validate.py ----------
def es_board(**over):
    b, slots = copy.deepcopy(EN), None
    fields, slots = M.collect(b)
    M.build(b, ES, slots, "fake", TODAY, "es", M.CFG["shorts_channels"]["es"])
    b.update(over)
    return b
good = es_board()
errs, warns = V.check(good)
assert errs == [], errs
assert good["id"] == "QD-901-es" and good["language"] == "es" and good["channel"] == "es" and good["mirror_of"] == "QD-901"
e = V.check(dict(good, id="QD-902-es"))[0]
assert any("Spanish mirror" in x for x in e), e                                              # QD-902-es cannot be the mirror of QD-901
e = V.check({**good, "language": None, "mirror_of": None})[0]
assert any(x.startswith("id:") and "Spanish mirror" in x for x in e), e                      # QD-901-es is only for a Spanish mirror
e = V.check({**good, "id": "QD-901", "channel": "es"})[0]
assert any(x.startswith("id:") and "Spanish mirror" in x for x in e), e                      # and a Spanish board is only QD-###-es
e = V.check({**good, "channel": "music"})[0]
assert any("a Spanish board is for the es channel" in x for x in e), e
# the narration runs longer in Spanish: 170 words is outside the English range (135) and inside the Spanish one (175)
long_es = copy.deepcopy(good)
for bt in long_es["beats"][1:]: bt["say"] += " " + " ".join(["palabra"] * 10)
n = sum(len(bt["say"].split()) for bt in long_es["beats"])
assert 135 < n <= 175, n
assert not [x for x in V.check(long_es)[0] if x.startswith("narration")], V.check(long_es)[0]
long_en = copy.deepcopy(EN)
for bt in long_en["beats"][1:]: bt["say"] += " " + " ".join(["word"] * 10)
assert [x for x in V.check(long_en)[0] if x.startswith("narration")]
# banned and negative words in Spanish; the English patterns are not run on Spanish text ("exposición" is not "expose")
bad = copy.deepcopy(good); bad["beats"][0]["say"] = "El cantante admite que se equivocó con 12 semanas en la lista."
assert any("negative framing" in x and "admite" in x for x in V.check(bad)[0]), V.check(bad)[0]
bad = copy.deepcopy(good); bad["beats"][4]["say"] += " Hay apuestas sobre el próximo disco."
assert any("excluded topic" in x and "apuestas" in x for x in V.check(bad)[0]), V.check(bad)[0]
ok = copy.deepcopy(good); ok["beats"][0]["say"] = "La exposición del álbum de Olivia Rodrigo lleva 12 semanas abierta, y nadie lo vio venir."
assert V.check(ok)[0] == [], V.check(ok)[0]
assert V.NEGATIVE.search("exposición") and not V.NEGATIVE_ES.search("exposición")           # why the English list is not used
fic = copy.deepcopy(bad); fic["beats"][4]["say"] = good["beats"][4]["say"]; fic["kind"] = "fiction"
fic["beats"][0]["say"] = "El detective admite que miente."
assert not [x for x in V.check(fic)[0] if "negative framing" in x]                           # fiction may
slow = copy.deepcopy(good); slow["beats"][0]["say"] = "Descubre cómo el álbum de Olivia Rodrigo llegó a 12 semanas en el primer puesto."
assert any(x.startswith("beat 0: a slow intro") for x in V.check(slow)[0]), V.check(slow)[0]
assert V.check(dict(good, id="QD-901-es", mirror_of="QD-901"))[0] == []
assert any("numbers start at" in x for x in V.check(dict(good, id="QD-028-es", mirror_of="QD-028"))[0])      # the first_id rule reads a -es id
print("1 validate ok")

# ---------- 2. freshness.py ----------
assert FR.zone_of(good).key == "America/New_York" and FR.zone_of(EN).key == "Europe/London"
news = copy.deepcopy(good); news["kind"] = "news"; news["created"] = "2026-10-27"
news_en = copy.deepcopy(EN); news_en["kind"] = "news"; news_en["created"] = "2026-10-27"
class NoNet:
    ok = False; text = ""
    def json(self): return []
get = lambda *a, **k: NoNet()
FR.in_trends = lambda phrase: False
late_slot = dt.datetime(2026, 10, 28, 3, 0, tzinfo=dt.timezone.utc)                         # 03:00 UTC the 28th: 23:00 on the 27th in New York, the 28th in London
assert FR.check(news, late_slot, get, record=False) is None, "a Spanish Short in the American evening of its day is on time"
out = FR.check(news_en, late_slot, get, record=False)
assert out and out["alive"] is False and out["days_late"] == 1, out                         # the same Short in English would be a day late
early = dt.datetime(2026, 10, 27, 23, 30, tzinfo=dt.timezone.utc)
assert FR.check(news, early, get, record=False) is None
next_day = dt.datetime(2026, 10, 28, 23, 30, tzinfo=dt.timezone.utc)                        # a day later still
out = FR.check(news, next_day, get, record=False)
assert out and out["days_late"] == 1 and out["alive"] is False, out
spoken = copy.deepcopy(news); spoken["beats"][0]["say"] = "Hoy sale el nuevo álbum de Olivia Rodrigo con 12 canciones."
assert FR.words_wrong(spoken, dt.date(2026, 10, 27), dt.date(2026, 10, 28)).startswith('its words say "Hoy"')
assert FR.words_wrong(spoken, dt.date(2026, 10, 27), dt.date(2026, 10, 27)) is None
assert FR.words_wrong(news, dt.date(2026, 10, 27), dt.date(2026, 10, 28)) is None
weeky = copy.deepcopy(news); weeky["beats"][0]["say"] = "Esta semana sale el nuevo álbum de Olivia Rodrigo con 12 canciones."
assert FR.words_wrong(weeky, dt.date(2026, 10, 5), dt.date(2026, 10, 28)) and FR.words_wrong(weeky, dt.date(2026, 10, 27), dt.date(2026, 10, 28)) is None
print("2 freshness ok")

# ---------- 3. plan.py ----------
import plan as P, background
americas = P.americas_slots(dt.date(2026, 10, 27), 6)
assert [t.strftime("%d %H:%M") for t in americas] == ["27 23:00", "28 00:00", "28 00:45", "28 01:30", "28 02:15", "28 03:00"], americas
assert P.channel_slots(dt.date(2026, 10, 27), "es") == americas and P.day_slots(dt.date(2026, 10, 27), "es") == americas
assert P.americas_slots(dt.date(2026, 10, 27), 1) == americas[:1] and len(P.americas_slots(dt.date(2026, 10, 27), 3)) == 3
assert P.channel_slots(dt.date(2026, 10, 27), "music")[0].astimezone(P.UK).strftime("%H:%M") == "07:30"        # the music channel's grid is unchanged
P.ROOT = SCRATCH / "plan"; (P.ROOT / "status").mkdir(parents=True); Q = P.ROOT / "boards" / "queue"; Q.mkdir(parents=True)
P.learned_slots = lambda n: None
P.LEAD = dt.timedelta(hours=1); P.LIMIT = 5
V.check = lambda b, p=None: ([], [])
background.wanted = lambda b, cfg: False
P.schedule_state = lambda now, yt=None, channel="main": (set(), 0, True)
(Q / "QD-901-es.json").write_text(json.dumps({**good, "created": str(TODAY + dt.timedelta(days=1))}))
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()): P.main()
jobs = json.loads(buf.getvalue().strip().split("boards=", 1)[1])
assert len(jobs) == 1, jobs
job = jobs[0]
assert job["id"] == "QD-901-es" and job["channel"] == "es" and job["language"] == "es" and job["mode"] == "schedule", job
assert job["look"]["voice"] == "george", job["look"]                     # no English voice model is fetched for it (render.yml); run_board.py reads it in Spanish
when = dt.datetime.fromisoformat(job["slot"].replace("Z", "+00:00"))
assert (when.hour, when.minute) in {(23, 0), (0, 0), (0, 45), (1, 30), (2, 15), (3, 0)}, job["slot"]       # the American evening
print("3 plan ok")

# ---------- 4. mirror.py ----------
M.ROOT = SCRATCH / "mir"
for d in M.FOLDERS: (M.ROOT / "boards" / d).mkdir(parents=True)
(M.ROOT / "analytics").mkdir()
M.LOG = M.ROOT / "analytics" / "mirror_log.csv"
fields, slots = M.collect(copy.deepcopy(EN))
assert set(fields) == set(ES), (sorted(set(fields) ^ set(ES)))
assert "b1.v.value" not in fields and "meta.tags.0" not in fields and "b0.v.highlight" not in fields       # a bare number and the story's own name are not translated
assert fields["b0.v.lines.1"] == "AT THE TOP" and fields["b0.s0.role"] == "singer-songwriter"
assert M.numbers("Sold 1,200 and 1.200 and 1.5 or 1,5 in 2026") == M.numbers("1200 1200 15 15 2026") and M.numbers("12 and 12")["12"] == 2
assert M.names("Olivia Rodrigo's new album. Then Taylor Swift, BBC and the English fans in Los Angeles on Monday") == {"rodrigo", "taylor", "swift", "los", "angeles"}

def problems(**change):
    return M.problems_with(fields, {**ES, **change})
assert problems() == []
assert any("b1.say: the numbers" in p and "302000" in p for p in problems(**{"b1.say": ES["b1.say"].replace("302,000", "320,000")}))
assert problems(**{"b1.say": ES["b1.say"].replace("302,000", "302.000")}) == []                       # the same number written the Spanish way
assert any("numbers" in p for p in problems(**{"b2.say": ES["b2.say"].replace("1 sola", "una sola")}))   # a number turned into a word is a number lost
assert any("dash" in p for p in problems(**{"b4.say": ES["b4.say"].replace(" y ", " \u2014 ")}))
assert any("keys are missing" in p for p in M.problems_with(fields, {k: v for k, v in ES.items() if k != "b5.say"}))
assert any("not in the English" in p for p in problems(**{"b9.say": "x"}))
assert any("at most 35% more" in p for p in problems(**{"b5.say": ES["b5.say"] + " " + " ".join(["palabra"] * 70)}))
assert any("names must stay" in p for p in problems(**{"b0.say": "El nuevo disco de la cantante lleva 12 semanas arriba, y nadie lo vio venir.",
                                                       "b3.say": "Los fans notaron la misma chaqueta del primer concierto.",
                                                       "b4.say": "Los críticos le dieron al álbum cuatro estrellas de cinco.",
                                                       "b2.say": ES["b2.say"].replace("Londres", "la capital")}))
assert any("meta.title is" in p for p in problems(**{"meta.title": "Olivia Rodrigo: 12 semanas seguidas en el número 1 de la lista 🎵"}))
assert M.problems_with(fields, ["not", "a", "dict"]) == ["the answer must be one JSON object"]
assert M.fix_emoji("Title 🎵", "Título") == "Título 🎵" and M.fix_emoji("Title 🎵", "Título 🎶") == "Título 🎶" and M.fix_emoji("Title", "Título") == "Título"
assert M.clean_answer({"b0.say": "uno \u2014 dos \u2013 tres", "meta.title": "Título"}, {"meta.title": "Title 🎵"}) == {"b0.say": "uno, dos, tres", "meta.title": "Título 🎵"}

calls = []
def asker(*answers):
    """A stand-in for factpack.gemini: the answers in turn (a string is a refusal to answer), every prompt kept."""
    it = iter(answers)
    def ask(prompt, schema=None, **kw):
        calls.append((prompt, kw))
        a = next(it)
        if isinstance(a, Exception): raise a
        return a, "fake-model"
    return ask
CH = M.CFG["shorts_channels"]["es"]

calls.clear()
es, model, why = M.translate(EN, "es", CH, TODAY, asker(ES))
assert es and why == "" and model == "fake-model" and len(calls) == 1, why
assert calls[0][1]["lite"] is True and "neutral Latin American Spanish" in calls[0][0] and '"b1.say"' in calls[0][0] and "REFUSED" not in calls[0][0]
assert es["id"] == "QD-901-es" and es["language"] == "es" and es["channel"] == "es" and es["mirror_of"] == "QD-901"
assert es["mirrored"] == str(TODAY) and es["writer"] == "mirror:fake-model" and es["created"] == EN["created"]
assert es["test"] == {"length": "35 to 44 s", "title_emoji": "emoji", "hook_type": "statement", "mirror": "yes"}          # only the arms the board is written to
assert not any(k in es for k in M.DROP), es.keys()
assert es["kind"] == "evergreen" and es["category"] == "Music" and es["music"] == EN["music"] and es["background"] == EN["background"]
assert es["meta"]["sources"] == EN["meta"]["sources"] and es["meta"]["facts"] == EN["meta"]["facts"]              # the same fact pack
assert "translations" not in es["meta"] and es["meta"]["tags"][0] == "olivia rodrigo" and es["meta"]["tags"][1] == "nuevo álbum"
assert es["beats"][0]["say"] == ES["b0.say"] and es["beats"][0]["say_en"] == EN["beats"][0]["say"]
assert [bt["shots"][0]["src"] for bt in es["beats"]] == [bt["shots"][0]["src"] for bt in EN["beats"]]            # the same pictures
assert es["beats"][0]["shots"][0]["label"] == {"t": "Olivia Rodrigo", "s": "cantautora"}                          # the name stays, the role is translated
assert es["beats"][0]["visual"]["kicker"] == "NÚMERO UNO" and es["beats"][0]["visual"]["lines"] == ["12 SEMANAS", "EN LO MÁS ALTO"]
assert es["beats"][0]["visual"]["highlight"] == [0] and es["beats"][1]["visual"]["value"] == "302,000"
assert es["chip_label"] == "Música" and es["handle"] == "@quickplaydiario" and es["cta_lines"] == ["Sigue para", "la tendencia", "de mañana"]
assert EN["id"] == "QD-901" and EN["beats"][0]["say"].startswith("Olivia") and "look" in EN, "the English board is untouched"
import importlib; V.check = importlib.reload(V).check          # (section 3 put a stand-in checker in place: the real one from here)
assert V.check(es)[0] == [], V.check(es)[0]
assert not re.search("[\u2014\u2013]", json.dumps(es, ensure_ascii=False)) and "UK" not in json.dumps(es["meta"])

calls.clear()                        # a wrong number: asked again with what was wrong
bad = {**ES, "b1.say": ES["b1.say"].replace("302,000", "320,000")}
es, model, why = M.translate(EN, "es", CH, TODAY, asker(bad, ES))
assert es and len(calls) == 2 and "REFUSED" in calls[1][0] and "b1.say: the numbers must be the same" in calls[1][0] and "REFUSED" not in calls[0][0]
calls.clear()                        # wrong twice: dropped, with the reason
es, model, why = M.translate(EN, "es", CH, TODAY, asker(bad, bad))
assert es is None and len(calls) == 2 and "numbers" in why, why
calls.clear()                        # dashes and a dropped title emoji are put right without a second call
sloppy = {**ES, "b4.say": ES["b4.say"].replace(" y ", " \u2014 "), "meta.title": "Olivia Rodrigo: 12 semanas en el número 1"}
es, model, why = M.translate(EN, "es", CH, TODAY, asker(sloppy))
assert es and len(calls) == 1 and ", " in es["beats"][4]["say"] and "\u2014" not in es["beats"][4]["say"] and es["meta"]["title"].endswith("🎵")
calls.clear()                        # the board rules: a negative word about a real person is refused, twice
neg = {**ES, "b0.say": ES["b0.say"].replace("nadie lo vio venir", "ella admite que nadie lo vio venir")}
es, model, why = M.translate(EN, "es", CH, TODAY, asker(neg, neg))
assert es is None and "negative framing" in why and "board rules" in why and len(calls) == 2, why
calls.clear()
dupes = {**ES, "meta.hashtags.7": "#Pop"}
es, model, why = M.translate(EN, "es", CH, TODAY, asker(dupes, ES))
assert es and len(calls) == 2 and "meta.hashtags: duplicates" in calls[1][0]
calls.clear()
es, model, why = M.translate(EN, "es", CH, TODAY, asker(RuntimeError("every model is out of quota")))
assert es is None and why.startswith("no model answered: every model is out of quota"), why
es, model, why = M.translate({**EN, "beats": []}, "es", CH, TODAY, asker())
assert es is None and why == "no narration to translate"
print("4a translate ok")

# who is mirrored, and how many per run
def put(folder, sid, **over):
    b = copy.deepcopy(EN); b.update({"id": sid, "created": day(), **over})
    (M.ROOT / "boards" / folder / f"{sid}.json").write_text(json.dumps(b))
    return b
put("queue", "QD-902", kind="news")                                  # time-sensitive, today: first
put("queue", "QD-903", kind="news", created=day(2))                  # time-sensitive and two days old: left
put("queue", "QD-904", channel="music")                              # another channel's board: left
put("queue", "QD-905")                                               # already has its mirror: left
(M.ROOT / "boards" / "failed" / "QD-905-es.json").write_text(json.dumps({"id": "QD-905-es", "channel": "es", "mirrored": day()}))
put("queue", "QD-906", mode="dry")                                   # a test run: left
put("queue", "QD-907", language="es")                                # not a main board: left
put("done", "QD-908", created=day(5))                                # an old evergreen that did well: second
put("queue", "QD-909")                                               # unmeasured evergreen, today: third
put("queue", "QD-910", created=day(9))                               # over a week old: left
put("queue", "QD-911", mode="private")
put("done", "QD-916", created=day(6))                                # a Short the audience passed over (0.1x typical): a dead Short is not remade
(M.ROOT / "boards" / "queue" / "TEST-1.json").write_text(json.dumps({**EN, "id": "TEST-1"}))
(M.ROOT / "analytics" / "shorts.csv").write_text("short,views_vs_typical\nQD-908,3.2\nQD-909,\nQD-902,0.5\nQD-916,0.1\n")
assert [b["id"] for b in M.candidates(TODAY)] == ["QD-902", "QD-908", "QD-909"], [b["id"] for b in M.candidates(TODAY)]

M.signed_in = lambda ch: False
assert M.mirror_channels() == {} and M.mirror_boards(TODAY, "morning", ask=asker()) == []               # dormant: nothing asked, nothing written
assert not M.LOG.exists() and not list((M.ROOT / "boards" / "queue").glob("*-es.json"))
M.signed_in = lambda ch: ch == "es"
assert list(M.mirror_channels()) == ["es"]
assert [M.room("es", CH, TODAY, r) for r in ("morning", "afternoon", "evening", "")] == [3, 5, 6, 6]         # the day's 6 spread like the main channel's runs
M.factpack.STATE.clear()
calls.clear()
wrote = M.mirror_boards(TODAY, "morning", ask=asker(ES, ES, ES))
assert [b["id"] for b in wrote] == ["QD-902-es", "QD-908-es", "QD-909-es"], [b["id"] for b in wrote]
assert all((M.ROOT / "boards" / "queue" / f"{b['id']}.json").exists() for b in wrote) and len(calls) == 3
rows = list(csv.DictReader(M.LOG.open()))
assert [(r["id"], r["result"], r["model"]) for r in rows] == [(b["id"], "made", "fake-model") for b in wrote] and rows[0]["why"] == ES["meta.title"]
assert V.check(json.loads((M.ROOT / "boards" / "queue" / "QD-902-es.json").read_text()), M.ROOT / "boards" / "queue" / "QD-902-es.json")[0] == []
calls.clear()
assert M.room("es", CH, TODAY, "morning") == 0 and M.mirror_boards(TODAY, "morning", ask=asker()) == [] and not calls     # the run's share is made
put("queue", "QD-912"); put("queue", "QD-913"); put("queue", "QD-914"); put("queue", "QD-915")
wrote = M.mirror_boards(TODAY, "afternoon", ask=asker(ES, ES, ES))
assert len(wrote) == 2 and len(calls) == 2, (len(wrote), len(calls))                                    # 5 for the morning and afternoon together
wrote = M.mirror_boards(TODAY, "evening", ask=asker(ES, ES, ES))
assert len(wrote) == 1 and M.room("es", CH, TODAY, "evening") == 0                                      # 6 in the day, however many main boards
assert len(list((M.ROOT / "boards" / "queue").glob("*-es.json"))) == 6
assert M.room("es", CH, TODAY + dt.timedelta(days=1), "morning") == 3                                  # the next day starts again
# a board whose translation keeps failing is tried twice in all, then left
put("queue", "QD-920")
M.factpack.STATE.clear()
M.mirror_boards(TODAY + dt.timedelta(days=1), "morning", ask=asker(*[{}] * 4))
M.mirror_boards(TODAY + dt.timedelta(days=1), "afternoon", ask=asker(*[{}] * 4))
fails = [r for r in csv.DictReader(M.LOG.open()) if r["result"] == "failed" and r["id"] == "QD-920-es"]
assert len(fails) == 2 and "keys are missing" in fails[0]["why"] and "QD-920" not in [b["id"] for b in M.candidates(TODAY + dt.timedelta(days=1))]
# the models being spent or the time being up stops the run
put("queue", "QD-921")
M.factpack.STATE["spent"] = True
n = len(calls)
assert M.mirror_boards(TODAY + dt.timedelta(days=2), "morning", ask=asker(ES)) == [] and len(calls) == n
M.factpack.STATE.clear()
assert M.mirror_boards(TODAY + dt.timedelta(days=2), "morning", late=lambda: True, ask=asker(ES)) == []
print("4b mirror runs ok")

# ---------- 5. run_board.py ----------
import looks as LK, run_board as RB
track = {"title": "Sunny Day", "artist": "Kevin MacLeod", "source": "YouTube Audio Library"}
credits = [{"credit": "Photo by Ann", "source": "Wikimedia Commons"}]
d_es = RB.description(good, credits, track)
assert d_es.startswith(good["meta"]["summary"]) and "Fuentes:\nBillboard, the chart: https://www.billboard.com/charts" in d_es
assert "Imágenes:\nPhoto by Ann (Wikimedia Commons)" in d_es and "Música: Sunny Day de Kevin MacLeod (YouTube Audio Library)" in d_es
assert "Canal independiente, sin relación con las empresas ni las personas que aparecen." in d_es and d_es.rstrip().endswith("#Shorts")
d_en = RB.description(EN, credits, track)
assert "Sources:" in d_en and "Visuals:" in d_en and "Music: Sunny Day by Kevin MacLeod" in d_en and "Independent channel, not affiliated" in d_en and "Fuentes" not in d_en
assert RB.localize(good["meta"], d_es) == {}                       # the mirror carries no translations of its own
src = open("pipeline/run_board.py").read()
assert '**({"language": "es"} if es else {})' in src and '"localizations": {} if es else localize(meta, desc' in src

module = lambda name, **attrs: sys.modules.__setitem__(name, types.ModuleType(name)) or sys.modules[name].__dict__.update(attrs)
repo = SCRATCH / "repo"
(repo / "pipeline").mkdir(parents=True); (repo / "boards" / "queue").mkdir(parents=True)
(repo / "config.json").write_text(json.dumps({"approval": "none", "shorts_channels": {"es": {"voice": "ES", "wps": 2.8, "handle": "@quickplaydiario"},
                                                                                      "music": {"handle": "@quickplaymusic"}}}))
(repo / "boards" / "queue" / "QD-901-es.json").write_text(json.dumps(good))
(repo / "boards" / "queue" / "QD-901.json").write_text(json.dumps({**EN, "channel": "music", "id": "QD-901"}))
RB.ROOT, RB.P = repo, repo / "pipeline"
module("fetch_media", resolve=lambda sb: sb, extras=lambda sb: 0)
module("background", wanted=lambda sb, cfg: False, fetch=lambda *a: ([], []), settings=lambda cfg: {})
RB.pick_music, RB.pick_social_music = (lambda sb: {"slug": "calm"}), (lambda sb: None)
cat = copy.deepcopy(LK.catalogue())

def drive(board_id, channel, recall=None, crash=(), look_voice="lewis"):
    """The voices asked of tts_cb.py in order (with their pace), the resolved board it was given, and the status file."""
    asked, boards = [], []
    def fake_sh(*cmd, cwd=None):
        if str(cmd[1]) == "render3.py": raise RuntimeError("stop after the narration")
        voice = cmd[cmd.index("--voice") + 1]; asked.append((voice, cmd[cmd.index("--target-wps") + 1]))
        boards.append(json.loads(_p.Path(cmd[2]).read_text()))
        if voice in crash: raise subprocess.CalledProcessError(3, [str(c) for c in cmd])
        d = _p.Path(cmd[3]); d.mkdir(parents=True, exist_ok=True)
        beats = [{"beat": i, "file": f"cb_b{i:02d}.wav", "dur": 2.0, "recall": (recall or {}).get(voice, 0.9), "text": "x"} for i in range(6)]
        (d / "cb_manifest.json").write_text(json.dumps({"sr": 24000, "voice": voice, "tempo": 1.0, "wps": 3.0, "beats": beats}))
    RB.sh = fake_sh
    look = LK.choose(board_id, [], {}, cat); look["voice"] = look_voice
    os.environ["JOB_JSON"] = json.dumps({"board": f"boards/queue/{board_id}.json", "id": board_id, "slot": "", "mode": "none", "look": look,
                                         **({"channel": channel} if channel else {})})
    sys.argv = ["run_board.py"]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()): RB.main()
    return asked, boards, json.loads((repo / "result" / board_id / "status.json").read_text())

asked, boards, st = drive("QD-901-es", "es")
assert asked == [("ES", "2.8")] and st["look"]["voice"] == "es" and "look_note" not in st and st["channel"] == "es", (asked, st)       # the Spanish voice at the Spanish pace, whatever look was drawn
assert boards[0]["handle"] == "@quickplaydiario" and boards[0]["language"] == "es" and boards[0]["voice_engine"] == "chatterbox"
assert st["state"] == "failed" and "stop after the narration" in st["error"]
asked, boards, st = drive("QD-901-es", "es", recall={"ES": 0.1})                  # unclear: the Spanish voice again, slower (never the English house voice)
assert asked[:2] == [("ES", "2.8"), ("ES", "2.38")] and {a for a in asked[2:]} <= {("ES", "2.52")} and st["look"]["voice"] == "es", asked       # (then the stubborn beats are read as two sentences, as always)
asked, boards, st = drive("QD-901-es", "es", crash=("ES",))                      # the Spanish voice failing is a real failure, as the house voice is
assert asked == [("ES", "2.8")] and st["error"].startswith("CalledProcessError"), (asked, st)
asked, boards, st = drive("QD-901", "music")                                      # a music Short: the English voice as before, and its own name on screen
assert asked == [("LW", "3.0")] and st["look"]["voice"] == "lewis" and boards[0]["handle"] == "@quickplaymusic", (asked, boards[0].get("handle"))
asked, boards, st = drive("QD-901", "music", recall={"LW": 0.1})
assert asked == [("LW", "3.0"), ("F2", "3.0")] and st["look_note"] == "voice LW was less clear, used george"
print("5 run_board ok")

# ---------- 6. tts_cb.py and make_voices.py ----------
try: import torch
except ImportError: sys.modules["torch"] = types.SimpleNamespace(set_num_threads=lambda n: None, manual_seed=lambda s: None)
class Wave:
    def __init__(self, a): self.a = a
    def squeeze(self, dim): return Wave(self.a[0])
    def numpy(self): return self.a
loaded = []
class MtlModel:
    sr = 24000
    def __init__(self, conds): self.conds, self.cond, self.made = conds, [], []; self.secs = lambda text: len(text.split()) / 3.0
    def prepare_conditionals(self, wav, **kw): self.cond.append((wav, kw)); self.conds = object()
    def generate(self, text, **kw):
        self.made.append((text, kw)); return Wave(np.full((1, int(24000 * self.secs(text))), 0.2, np.float32))
state = {"conds": object(), "secs": None}
def from_local(ckpt, device):
    m = MtlModel(state["conds"])
    if state["secs"]: m.secs = state["secs"]
    loaded.append((str(ckpt), device, m)); return m
module("chatterbox", __path__=[])
module("chatterbox.mtl_tts", ChatterboxMultilingualTTS=type("ChatterboxMultilingualTTS", (), {"from_local": staticmethod(from_local)}))
asr = []
module("qa_asr", hear=lambda p: asr.append(p) or "", recall=lambda script, said: (1.0, []))
import tts_cb as T
T.MTL_CKPT = SCRATCH / "mtl"; (SCRATCH / "mtl").mkdir()
for name in T.MTL_FILES: (SCRATCH / "mtl" / name).write_bytes(b"x")
board = SCRATCH / "board.json"
first = next(iter(T.PRONOUNCE))
board.write_text(json.dumps({"id": "QD-901-es", "beats": [{"say": f"uno dos tres {first} cinco seis"}, {"say": "siete ocho nueve diez"}, {"say": "once doce"}]}))
def read(voice, out, wps="3.0"):
    sys.argv = ["tts_cb.py", str(board), str(out), "--voice", voice, "--target-wps", wps]
    loaded.clear(); del asr[:]
    with contextlib.redirect_stdout(io.StringIO()) as log: T.main()
    return json.loads((out / "cb_manifest.json").read_text()), log.getvalue()

assert T.VOICES["ES"]["engine"] == "mtl" and T.VOICES["ES"]["language"] == "es" and T.VOICES["ESF"]["language"] == "es"
assert not any(v.get("engine") for k, v in T.VOICES.items() if k not in ("T2", "ES", "ESF")), "the English voices are read as before"
man, log = read("ES", SCRATCH / "o1")
(ckpt, device, m), = loaded
assert (ckpt, device) == (str(SCRATCH / "mtl"), "cpu") and "(Chatterbox Multilingual)" in log and "built-in voice reads" in log      # no reference yet: the model's own voice
assert m.cond == [] and not asr, "the English speech check is never used for Spanish"
assert [kw for _, kw in m.made] == [{"language_id": "es", "exaggeration": 0.5, "cfg_weight": 0.5}] * 3
assert m.made[0][0] == f"uno dos tres {first} cinco seis", "the English pronunciation list is not applied to Spanish"
assert man["voice"] == "ES" and len(man["beats"]) == 3 and all(b["recall"] == 1.0 for b in man["beats"]) and man["wps"] == 3.0
ref = SCRATCH / "ref.wav"; ref.write_bytes(b"x")
T.VOICES["ES2"] = {**T.VOICES["ES"], "ref": str(ref)}                                         # the Kokoro reference made: it is the voice
man, log = read("ES2", SCRATCH / "o2")
(ckpt, device, m), = loaded
assert m.cond == [(str(ref), {"exaggeration": 0.5})] and "built-in" not in log
state["conds"] = None                                                                          # no reference and no built-in voice: say what to do
try: read("ES", SCRATCH / "o3"); raise AssertionError("a voice with nothing to read in must not start")
except SystemExit as e: assert "make_voices.py refs" in str(e) and "conds.pt" in str(e), str(e)
state["conds"] = object()
state["secs"] = lambda text: 40.0                                                              # babble: 4 words in 40 s is not speech
man, log = read("ES", SCRATCH / "o4", wps="0.1")
assert man["beats"][0]["recall"] == 0.2 and man["beats"][1]["recall"] == 0.2 and man["beats"][2]["recall"] == 1.0       # (two words is too short to judge)
assert len(loaded[0][2].made) == 3 + 3 + 1, len(loaded[0][2].made)
state["secs"] = lambda text: len(text.split()) / 9.0                                           # cut short: 9 words a second
man, log = read("ES", SCRATCH / "o5", wps="0.1")
assert man["beats"][0]["recall"] == 0.2
(SCRATCH / "mtl" / "s3gen.pt").unlink()
try: read("ES", SCRATCH / "o6"); raise AssertionError("missing model files must stop the run")
except SystemExit as e: assert "s3gen.pt" in str(e) and "--multilingual" in str(e)
import make_voices as MV
assert [(n, kv, lang, pid) for n, kv, lang, pid, *_ in MV.BANK_ES] == [("es_alex", "em_alex", "e", "ES"), ("es_dora", "ef_dora", "e", "ESF")]
assert T.VOICES["ES"]["ref"] == f"voices/{MV.BANK_ES[0][0]}_ref.wav" and T.VOICES["ESF"]["ref"] == f"voices/{MV.BANK_ES[1][0]}_ref.wav"
assert "Quédate" in MV.REF_TEXT_ES and not {"ES", "ESF"} & {x[3] for x in MV.BANK}      # the English looks never draw a Spanish voice
print("6 tts_cb and make_voices ok")

# ---------- 7. get_model.py and render.yml ----------
import hashlib
fetched = []
def hf_hub_download(repo, name, revision=None, local_dir=None):
    fetched.append((repo, name, revision)); (_p.Path(local_dir) / name).write_bytes(b"w-" + name.encode())
module("huggingface_hub", hf_hub_download=hf_hub_download)
import get_model as GM
assert set(T.MTL_FILES) < set(GM.MTL_FILES) and set(GM.MTL_FILES) - set(T.MTL_FILES) == {"conds.pt"}      # everything the loader reads, and the built-in voice
assert GM.MTL_REPO == GM.REPO and all(v is None for v in GM.MTL_FILES.values())                        # (not pinned yet: the first run prints what to pin)
sys.argv = ["get_model.py", str(SCRATCH / "m1"), "--multilingual"]
import runpy
with contextlib.redirect_stdout(io.StringIO()) as log: runpy.run_path("pipeline/get_model.py", run_name="__main__")
assert [(r, n, v) for r, n, v in fetched] == [(GM.MTL_REPO, n, "main") for n in GM.MTL_FILES], fetched          # no Hugging Face API here: downloaded as main
assert "could not resolve" in log.getvalue() and "not pinned" in log.getvalue() and hashlib.sha256(b"w-ve.pt").hexdigest() in log.getvalue()
fetched.clear()
sha = "a" * 40
module("huggingface_hub", hf_hub_download=hf_hub_download, HfApi=lambda: types.SimpleNamespace(model_info=lambda repo, revision=None: types.SimpleNamespace(sha=sha)))
sys.argv = ["get_model.py", str(SCRATCH / "m2"), "--multilingual"]
with contextlib.redirect_stdout(io.StringIO()) as log: runpy.run_path("pipeline/get_model.py", run_name="__main__")
assert {v for _, _, v in fetched} == {sha} and f"is commit {sha}" in log.getvalue(), (fetched[:2], log.getvalue()[:200])      # main is resolved to its commit and downloaded at that
yml = open(".github/workflows/render.yml").read()
only = "matrix.job.mode != 'reject' && matrix.job.language == 'es'"
steps = yml.split("\n      - ")
fetch = [s for s in steps if "get_model.py models/chatterbox-mtl --multilingual" in s]
assert len(fetch) == 1 and only in fetch[0] and "continue-on-error: true" in fetch[0]            # a failed fetch costs a Spanish Short, never the main channel's
restore = [s for s in steps if "path: models/chatterbox-mtl" in s and "cache/restore" in s]
save = [s for s in steps if "path: models/chatterbox-mtl" in s and "cache/save" in s]
assert len(restore) == 1 and only in restore[0] and len(save) == 1 and only in save[0] and "hashFiles('models/chatterbox-mtl/conds.pt') != ''" in save[0]
assert "CB_MTL_CKPT: ${{ github.workspace }}/models/chatterbox-mtl" in yml
assert yml.count("matrix.job.language == 'es'") == 3                                              # restore, fetch, save: nothing else changes for the main channel
print("7 get_model and render.yml ok")

# ---------- 8. writer.py, write.yml, the screen ----------
w = open("pipeline/writer.py").read()
assert "mirror.mirror_boards(day, run, late)" in w and w.index("extra_channel_boards(day, run") < w.index("mirror.mirror_boards(day, run, late)")
assert all(k in w.split("BOOKKEEPING += ")[1].split("\n")[0] for k in ("mirror_of", "mirrored", "chip_label", "handle"))
import writer as W
assert not W.main_board(good) and W.main_board(EN)                                                # the main channel's counters never count a mirror
wy = open(".github/workflows/write.yml").read()
assert "git add analytics/mirror_log.csv" in wy
r3, tpl = open("pipeline/render3.py").read(), open("pipeline/template3.html").read()
assert '"category": sb.get("chip_label") or sb["category"]' in r3 and '"handle": sb.get("handle") or "@quickplaydaily"' in r3 and '"cta": sb.get("cta_lines") or None' in r3
assert "esc(D.handle || '@quickplaydaily')" in tpl and "D.cta || ['Follow for', \"tomorrow's\", 'trend']" in tpl
assert tpl.count("@quickplaydaily") == 2           # only the defaults are left in the page
fm = open("pipeline/fetch_media.py").read()
assert 'beat.get("say_en") or beat.get("say")' in fm
acts = json.load(open("status/actions.json"))
steps_es = " ".join(next(a for a in acts if a["id"] == "channel-diario")["steps"])
assert "@quickplaydiario" in steps_es and "@quickplaymusic" in " ".join(next(a for a in acts if a["id"] == "channel-music")["steps"])
print("8 writer, write.yml and screen ok")
print("mirror ok")
