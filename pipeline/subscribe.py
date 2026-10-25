"""The subscriber push (Charlie, 25 October 2026: "a subscriber push strategy baked into everything").

Why: 15 subscribers from 26,500 views (about 0.5 per 1,000 views) and the Partner Programme needs 1,000. Measured, not assumed:
two arms, each drawn 50/50 and independent of every other arm, scored on subscribers gained per 1,000 views against Shorts
posted the same UK day (drivers.analyse_subscribers, analytics/subs.csv, feature "subs:<name>"), with views as the guardrail
(drivers.csv scores the same arms on views):
- test.sub_push "spoken" or "none" (writer.py, every Short but an exploration Short): the spoken Short ends with one short line
  giving a concrete reason to subscribe, tied to its series or category ("Song Secrets is here every day; subscribe so you
  don't miss the next one"); never a bare "like and subscribe". The old ending arm "follow line" is folded into it.
- look closing "chip" or "none" (templates/looks.json "closing", looks.py, render3.py, template3.html): a small line in the
  last 1.5 seconds, low in the safe area ("Subscribe for Game Explained #13"), inside the minimal style's text rules.
Always on, no arm: the creator comment's first line (series.comment_text, engage.comment_for), the description's subscribe link
(run_board.description), the Instagram caption's last line (social.caption) and an invitation ending a reply (engage.replies).

This module is the text and the choices only, with no network and no model, so the tests run offline. config.json "sub_push"
holds the handle, the share of Shorts that get the spoken line, and the rhythm of a series where it really is fixed.
"""
import csv, json, pathlib, random, re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text())
SUBS = ROOT / "analytics" / "subs.csv"
DRIVERS = ROOT / "analytics" / "drivers.csv"
CHANNEL = ROOT / "status" / "channel.json"
ARMS = ("spoken", "none")
ARM_PAIRS = {"sub_push": ARMS, "look_closing": ("chip", "none")}      # the two arms of each test of the push
RETEST = 5                       # a proven arm still loses 1 Short in 5 to the other (writer.RETEST), so new data can overturn it
CUT = ("cut back", "pause", "stop")
DEFAULTS = {"on": True, "handle": "@quickplaydaily", "spoken_share": 0.5, "cadence": {}, "times": {}}
NUMBERED = re.compile(r"^(.+?)\s+#(\d+)\s*$")          # "Song Secrets #12": a named series and its number


def conf(cfg=None):
    return {**DEFAULTS, **((CFG if cfg is None else cfg).get("sub_push") or {})}


def _read(path):
    try: return list(csv.DictReader(pathlib.Path(path).open()))
    except Exception: return []


# ---------------- who and where ----------------
def channel_of(b): return (b or {}).get("channel") or "main"


def handle(b=None, cfg=None, channel_json=None):
    """The channel's handle with its @ ("@quickplaydaily"): another channel's own (config shorts_channels), else for the main
    channel what status/channel.json says, else config sub_push.handle; "" when unknown."""
    c = CFG if cfg is None else cfg
    ch = channel_of(b)
    if ch != "main":
        h = str(((c.get("shorts_channels") or {}).get(ch) or {}).get("handle") or "").strip()
        return ("@" + h.lstrip("@")) if h else ""
    try: j = json.loads(pathlib.Path(channel_json or CHANNEL).read_text())
    except Exception: j = {}
    h = str((j if isinstance(j, dict) else {}).get("handle") or conf(c).get("handle") or "").strip()
    return ("@" + h.lstrip("@")) if h else ""


def channel_id(cfg=None, channel_json=None):
    """The main channel's id (status/channel.json, else config accounts.youtube), or ''."""
    c = CFG if cfg is None else cfg
    try: j = json.loads(pathlib.Path(channel_json or CHANNEL).read_text())
    except Exception: j = {}
    cid = str((j if isinstance(j, dict) else {}).get("channel_id") or "").strip()
    if cid: return cid
    ids = list(((c.get("accounts") or {}).get("youtube") or {}))
    return ids[0] if ids else ""


def sub_url(b=None, cfg=None, channel_json=None):
    """The link that asks a viewer to subscribe in one tap: the handle's page with sub_confirmation=1, else (main channel
    only) the channel id's, else ''."""
    h = handle(b, cfg, channel_json)
    if h: return f"https://www.youtube.com/{h}?sub_confirmation=1"
    cid = channel_id(cfg, channel_json) if channel_of(b) == "main" else ""
    return f"https://www.youtube.com/channel/{cid}?sub_confirmation=1" if cid else ""


def ig_handle(cfg=None):
    c = CFG if cfg is None else cfg
    ig = (c.get("accounts") or {}).get("instagram") or []
    return str(ig[0]).lstrip("@") if ig else ""


# ---------------- the series a board belongs to ----------------
def series_of(b):
    """(name, number, of, kind) of the series a board is in: the numbered series (series_name, series_no: series.py), else
    the named series of the franchise test ("Song Secrets #12"), else a channel series; ("", 0, 0, "") for none."""
    b = b or {}
    if b.get("series_name"):
        try: no = int(b.get("series_no") or 0)
        except (TypeError, ValueError): no = 0
        try: of = int(b.get("series_of") or 0)
        except (TypeError, ValueError): of = 0
        return str(b["series_name"]), no, of, str(b.get("series_kind") or "evergreen")
    for k in ("franchise", "channel_series"):
        m = NUMBERED.match(str(b.get(k) or ""))
        if m: return m.group(1), int(m.group(2)), 0, "franchise"
    return "", 0, 0, ""


def next_number(b):
    """The number of the next Short in the board's series, or 0 when there is none to promise (no series, or the last of a
    playbook's five)."""
    name, no, of, kind = series_of(b)
    if not name or not no: return 0
    return 0 if of and no >= of else no + 1


def label(b):
    """"Science Explained #12" or "Ballon d'Or #2 of 5" (series.label), or ''."""
    name, no, of, _ = series_of(b)
    if not name: return ""
    return name + (f" #{no}" if no else "") + (f" of {of}" if of and no else "")


# ---------------- the spoken line (writer.py) ----------------
def cadence(name, category, cfg=None):
    """How often a series or category comes, to name in the spoken line: config sub_push.cadence where Charlie has set one for
    a series (we never promise a rhythm we do not keep); a category is "every day" (every category has a daily floor)."""
    cad = conf(cfg).get("cadence") or {}
    if name: return str(cad.get(name) or "")
    return str(cad.get(category) or ("every day" if category else ""))


def at_time(name, category, cfg=None):
    """A posting hour to name ("two"), only where config sub_push.times sets one for the series or category."""
    t = conf(cfg).get("times") or {}
    return str(t.get(name) or t.get(category) or "") if (name or category) else ""


def spoken_note(name, category, cfg=None):
    """The writer's instruction for the "spoken" arm: one short line with a concrete, true reason tied to the series (or the
    category) and, where it is fixed, how often and when it comes."""
    when, hour = cadence(name, category, cfg), at_time(name, category, cfg)
    tie = f'our "{name}" series' if name else (f"our {category} Shorts" if category else "Quickplay Daily")
    rhythm = f"{when}" + (f" at {hour}" if hour else "") if when else ""
    if name and when: ex = f"{name} is here {rhythm}; subscribe so you don't miss the next one"
    elif name: ex = f"That was {name}; subscribe so you don't miss the next one"
    elif when: ex = f"A new {category} Short lands {rhythm}; subscribe so you never miss one"
    else: ex = "Subscribe to Quickplay Daily so you don't miss the next one"
    truth = (f"It may say it comes {rhythm}." if when else "Do not promise a day or a time.")
    return ("SUBSCRIBE LINE (this Short tests a spoken reason to subscribe): in the last beat, after the payoff and before any "
            "closing question or looping line, say ONE short line of 16 words or fewer that gives a concrete reason to subscribe, "
            f"tied to {tie}. {truth} The shape, not to be copied word for word: \"{ex}\". Never a bare \"like and subscribe\", "
            "never \"smash the button\", never a plea. The line counts in the narration's word total and needs no graphic.")


NONE_NOTE = ("SUBSCRIBE LINE (this Short tests having none): do not ask viewers to subscribe, follow or like anywhere in the "
             "narration.")


def note(arm, name="", category="", cfg=None):
    """The prompt text for an arm of the test ('' for anything else)."""
    return spoken_note(name, category, cfg) if arm == "spoken" else NONE_NOTE if arm == "none" else ""


def winner(feature, rows=None, views_rows=None):
    """The arm of `feature` ("sub_push", "look_closing") that analytics/subs.csv proves better for subscribers per 1,000 views
    (verdict "push", lift above 1; or the other arm's "cut back"), unless the views test (drivers.csv, the same feature) has cut
    it back or paused it: the subscriber push must not cost views. '' while nothing is proven."""
    rows = _read(SUBS) if rows is None else rows
    pair, best = ARM_PAIRS.get(feature, ()), ""
    for r in rows:
        if r.get("feature") != f"subs:{feature}": continue
        try: lift = float(r.get("lift") or 0)
        except ValueError: continue
        if r.get("verdict") == "push" and lift > 1: best = r.get("value") or ""
        elif r.get("verdict") == "cut back" and lift < 1 and not best and len(pair) == 2:
            best = next((a for a in pair if a != r.get("value")), "")
    if not best: return ""
    views_rows = _read(DRIVERS) if views_rows is None else views_rows
    if any(r.get("feature") == feature and r.get("value") == best and r.get("verdict") in CUT for r in views_rows): return ""
    return best


def arm(k, cfg=None, rows=None, views_rows=None):
    """Short number k's arm: 'spoken' or 'none', drawn 50/50 (config sub_push.spoken_share) on its own seed, so it is independent
    of every other arm; once the data proves one for subscribers (winner) that arm, with every RETEST-th Short trying the other.
    '' while sub_push is off."""
    c = conf(cfg)
    if not c.get("on", True): return ""
    won = winner("sub_push", rows, views_rows)
    if won in ARMS: return won if k % RETEST else next(a for a in ARMS if a != won)
    return "spoken" if random.Random(f"sub_push:{k}").random() < float(c.get("spoken_share", 0.5)) else "none"


# ---------------- the closing chip (render3.py) ----------------
def chip_text(b, cfg=None):
    """The words of the closing chip, short enough for one small line: 'Subscribe for Game Explained #13' for a Short in a
    numbered series, 'Subscribe for more Song Secrets', else 'Subscribe for more Gaming'. Spanish for the Spanish channel."""
    b = b or {}
    if b.get("language") == "es":
        cat = str(b.get("chip_label") or "").strip()
        return f"Suscríbete para más {cat}".strip() if cat else "Suscríbete para no perderte el siguiente"
    name, no, of, kind = series_of(b)
    nxt = next_number(b)
    for t in ((f"Subscribe for {name} #{nxt}" if name and nxt else ""), (f"Subscribe for more {name}" if name else ""),
              (f"Subscribe for more {b['category']}" if b.get("category") else ""), "Subscribe for the next one"):
        if t and len(t) <= 40: return t
    return "Subscribe for the next one"


# ---------------- always on ----------------
def comment_first_line(b, playlist_url="", cfg=None):
    """The creator comment's first line: it names the series (or, for a Short in none, the category) and asks to subscribe, with
    the series' playlist link when it has one, else the channel's one-tap subscribe link."""
    name, _, _, _ = series_of(b)
    if name:
        line = f"{label(b)}: subscribe so you never miss the next one."
        if playlist_url: return f"{line} The whole series: {playlist_url}"
        link = sub_url(b, cfg)
        return f"{line} {link}" if link else line
    cat = str((b or {}).get("category") or "").strip()
    link = sub_url(b, cfg)
    return (f"A new {cat} Short every day: subscribe so you never miss one." if cat else "New Shorts every day: subscribe so you never miss one.") \
        + (f" {link}" if link else "")


def description_lines(b, cfg=None):
    """Lines for the YouTube description, straight after the summary: the subscribe link, then a blank line. [] when the
    channel's link is unknown."""
    url = sub_url(b, cfg)
    if not url: return []
    name, _, _, _ = series_of(b)
    if (b or {}).get("language") == "es": return [f"Suscríbete para no perderte el siguiente: {url}", ""]
    return [(f"Subscribe for the next {name}: {url}" if name else f"Subscribe so you never miss the next one: {url}"), ""]


def ig_line(b, cfg=None):
    """The Instagram caption's last line: follow for the series (or the category)."""
    h = ig_handle(cfg)
    if not h: return ""
    name, _, _, _ = series_of(b)
    cat = str((b or {}).get("category") or "").strip()
    if name: return f"Follow @{h} for the next {name}."
    return f"Follow @{h} for a new {cat} Short every day." if cat else f"Follow @{h} for a new Short every day."


def reply_invite(b, cfg=None):
    """The short invitation that ends a reply to a comment (no link: replies carry none)."""
    name, _, _, _ = series_of(b)
    cat = str((b or {}).get("category") or "").strip()
    if name: return f"Subscribe for the next {name}."
    return f"Subscribe for a new {cat} Short every day." if cat else "Subscribe for a new Short every day."


def invite_reply(text, b, cfg=None, limit=300):
    """`text` with the invitation after it, once: a reply that already asks to subscribe is left as it is, and a long reply
    is cut at a word to leave room for the invitation."""
    text = str(text or "").strip()
    if not text or "subscribe" in text.lower(): return text[:limit]
    inv = reply_invite(b, cfg)
    room = limit - len(inv) - 1
    if len(text) > room: text = text[:room].rsplit(" ", 1)[0].rstrip(",;: ")
    return f"{text} {inv}"
