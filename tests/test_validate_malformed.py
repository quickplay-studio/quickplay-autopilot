"""Offline test: validate.check never raises, whatever shape a board has. plan.py checks every queued board before the
render matrix, so until 24 October one malformed board (a beat that is a string, a title that is a number) stopped every
queued Short from rendering. Such a board is now an error like any other: plan.py rejects it to boards/failed and the
writer's fixing round sees the reason."""
import copy, json, os, pathlib as _p, sys
REPO_DIR = str(_p.Path(__file__).resolve().parent.parent)
os.chdir(REPO_DIR); sys.path.insert(0, REPO_DIR + "/pipeline")
import validate as V

fmt = json.loads((_p.Path(REPO_DIR) / "templates" / "formats.json").read_text())["formats"][0]["id"]
beat = lambda say: {"say": say, "visual": {"type": "none"}, "shots": [{"src": "commons-search:Ada Lovelace", "move": "in"}]}
BASE = {"id": "TEST-MALFORMED-1", "created": "2026-10-24", "format": fmt, "category": "Science", "music": {"mood": "x"},
        "beats": [beat("Ada Lovelace wrote the first computer program in 1843."), beat("It ran on a machine never built."),
                  beat("Her notes were longer than the paper she translated."), beat("A language is named after her.")],
        "meta": {"title": "Ada Lovelace wrote code in 1843 💡", "hashtags": ["#AdaLovelace"], "tags": ["ada lovelace"],
                 "sources": [["Ada Lovelace", "https://en.wikipedia.org/wiki/Ada_Lovelace"]], "facts": [["first program", [1]]]}}
errs, warns = V.check(BASE)
assert isinstance(errs, list) and isinstance(warns, list)

def bad(change):
    b = copy.deepcopy(BASE); change(b); return b

CASES = {
    "beats is a dict": bad(lambda b: b.__setitem__("beats", {"a": 1})),
    "a beat is a string": bad(lambda b: b["beats"].__setitem__(0, "hello")),
    "a beat is null": bad(lambda b: b["beats"].__setitem__(0, None)),
    "say is a list": bad(lambda b: b["beats"][0].__setitem__("say", ["a", "b"])),
    "say is null": bad(lambda b: b["beats"][1].__setitem__("say", None)),
    "visual is a string": bad(lambda b: b["beats"][0].__setitem__("visual", "title")),
    "shots is a string": bad(lambda b: b["beats"][0].__setitem__("shots", "commons-search:X")),
    "a shot is null": bad(lambda b: b["beats"][0].__setitem__("shots", [None])),
    "title is a number": bad(lambda b: b["meta"].__setitem__("title", 123)),
    "music is a string": bad(lambda b: b.__setitem__("music", "upbeat")),
    "format is a dict": bad(lambda b: b.__setitem__("format", {"x": 1})),
    "meta is a list": bad(lambda b: b.__setitem__("meta", [])),
    "empty board": {},
}
for name, b in CASES.items():
    errs, warns = V.check(b)                       # must never raise
    assert errs, (name, "a malformed board must fail")
for thing in ([1, 2], "beats", None, 7):           # not a board at all
    assert V.check(thing)[0] == ["not a board: a JSON object is expected"], thing
print(f"validate malformed ok ({len(CASES)} shapes)")
