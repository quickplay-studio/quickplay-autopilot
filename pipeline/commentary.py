"""Commentary Shorts for the clips line (25 October 2026).

Charlie: "we need to push the clips better, they are still getting no traction". 93 public clips, 69 with no views, and YouTube
reports every one processed, none rejected, blocked or restricted: it is simply not putting them in the Shorts feed. Since
1 October 2026 YouTube does not recommend re-uploaded clips "without significant changes", and ours were a 34 second cut of
the streamer's footage with a 6 to 14 word spoken intro and outro. So a clip becomes a commentary Short, made by the Daily
pipeline: our own argument and checked context fill most of the runtime, and the permitted footage is only the evidence.

  hook          our take, the subject's name in the first four words (12 words or fewer)
  context x1-2  a checked fact about the streamer or the game (Wikipedia, checked word for word like the Daily's evergreen packs)
  evidence      our line (22 words or fewer), then the footage plays on its own with its own sound ("let it play": up to 6 seconds,
                no captions, no voice of ours, the music bed hushed); before that the streamer's sound is ducked under our voice
  payoff        lands the argument, then a question for the comments

5 to 7 beats, 90 to 120 words, 35 to 50 seconds; the footage is at most 40% of the runtime and never more than 15 seconds in one
piece. The model writes the words (factpack.gemini, the free chain, never Claude); the shots, the let-it-play window, the sources
and the sound are ours. clips.py cuts the evidence from the campaign's footage (a "clip:" shot, fetch_media.py), renders the board
with run_board.py (the Daily render: house voice, music, captions) and uploads the result as any clip.

  commentary.punchline(m, words)        the window of the moment that plays with its own sound
  commentary.wiki_pack(cid, c)          checked facts about the campaign's subject (Wikipedia), cached for two weeks
  commentary.write(ctx, pack, said)     the board: written, validated, fact-checked, fixed (twice at most)
  commentary.render(board, path, sid)   run_board.py: the mp4 and what the render measured
"""
import datetime as dt, json, os, pathlib, re, shutil, subprocess, sys, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))

KIND = "clip commentary"                 # the board kind validate.py lets use clip: shots
WPS = 2.9                                # words a second the house voice reads at (the look says 3.0; pauses cost the rest)
GAP, TAIL = 0.1, 0.6                     # run_board.fill_defaults: the pause after a beat and the tail of the Short
BEATS, WORDS, SECONDS = (5, 7), (90, 120), (35, 50)
HOOK_WORDS, EVIDENCE_WORDS = 12, 22
PLAY = (2.5, 6.0)                        # the let-it-play window: at least 2.5 s (else no punchline), at most 6 s
FOOTAGE_MAX, PIECE_MAX, SAFE_SHARE = 0.40, 15.0, 0.36      # the rules, and the share we aim under so the voice's pace cannot break them
LEAD = 10.0                              # seconds of footage kept before the punchline: our evidence line plays over them, ducked
DUCK = 0.18                              # the streamer's sound under our voice (a share of its level)
MOODS = {"Gaming": "action", "Entertainment": "playful"}
CATEGORY = {"gaming": "Gaming", "irl": "Entertainment", "clips": "Entertainment"}      # a clips channel's category (campaigns.json channel_categories)
FILLER_TAGS = ["#Streamer", "#Clips", "#Commentary", "#Trending", "#Funny", "#Reaction", "#Highlights"]
HANDLES = {"clips": "Quickplay Clips", "gaming": "Quickplay Gaming Clips", "irl": "Quickplay IRL Clips"}     # the name on screen (template3.html)
NARRATES = re.compile(r"^\s*(watch|look|see|here\b|this is the moment|check (this|out))|\bwatch (what|him|her|them|as|how)\b"
                      r"|\b(here (he|she|they) (goes|go|is|are))\b", re.I)
STATE = ROOT / "clips" / "state"
TTL_DAYS = 14                            # a campaign's Wikipedia pack is rebuilt every two weeks


def log(*a): print(*a, flush=True)


def words_of(s): return len(str(s or "").split())


def undash(s):
    import factpack
    return factpack.undash(str(s or "")).strip()


# ----- the format a campaign's clips are made in ------------------------------------------------------------------------------
def format_of(c, cfg, m=None):
    """"commentary" or "cut" for a campaign's moment. campaigns.json "format" on the campaign wins, then clips_format on the file
    (CLIPS_FORMAT in the environment beats both: tests, a manual run); "cut" is the old way and stays as the control. A series
    (whole episodes in order, nothing left out) and a campaign that avoids AI-made video stay cuts, whatever is asked."""
    want = (os.environ.get("CLIPS_FORMAT") or c.get("format") or (cfg or {}).get("clips_format") or "cut").strip().lower()
    if want != "commentary": return "cut"
    r = c.get("rules") or {}
    if r.get("series") or (m or {}).get("episode"): return "cut"
    if any(re.search(r"\bAI\b", str(x)) for x in r.get("avoid") or []): return "cut"
    return "commentary"


def outside_pictures(c):
    """True when pictures from outside the campaign's footage may be used (Commons photos of the subject). A campaign whose rules
    avoid "footage not from this campaign" gets stills of its own footage only."""
    return not any("not from this campaign" in str(x).lower() for x in (c.get("rules") or {}).get("avoid") or [])


def ready(deadline=None, now=None, need_min=9):
    """(True, "") when a commentary Short can be made now: the house voice is installed on this runner (CB_CKPT, the 12:00 UTC
    clips job installs Chatterbox), ffmpeg is here, and there are at least `need_min` minutes before the run's deadline (a
    commentary Short takes 4 to 8 minutes to write and render; the cut that stands in for it takes one)."""
    import time
    if not os.environ.get("CB_CKPT"): return False, "no house voice on this runner (CB_CKPT)"
    if not shutil.which("ffmpeg"): return False, "no ffmpeg"
    if deadline is not None and deadline - (now if now is not None else time.time()) < need_min * 60:
        return False, f"under {need_min} minutes left in this run"
    return True, ""


# ----- the moment: where the footage plays with its own sound ------------------------------------------------------------------
def punchline(m, words):
    """(play_at, play_len), in the segment's own seconds, for a moment: the window the footage plays with its own sound. It opens
    at the start of the sentence the planner's peak is in (at most 4 seconds back), runs to the end of that sentence and
    half a second more, and is 2.5 to 6 seconds long and inside the moment. None when the moment leaves no room for 2.5 s."""
    a, b = float(m["start"]), float(m["end"])
    pk = m.get("peak")
    pk = float(pk) if pk is not None and a < float(pk) < b else a + 0.6 * (b - a)
    inside = [w for w in words if a <= float(w["s"]) <= b]
    start = pk
    prior = [w for w in inside if float(w["s"]) <= pk]
    if prior:
        i = len(prior) - 1
        while (i > 0 and pk - float(prior[i - 1]["s"]) < 4.0 and float(prior[i]["s"]) - float(prior[i - 1]["e"]) < 0.7
               and not str(prior[i - 1]["w"]).strip().endswith((".", "?", "!"))):
            i -= 1
        start = float(prior[i]["s"])
    p = max(a, start - 0.3)
    end = next((float(w["e"]) for w in inside if float(w["e"]) >= pk and str(w["w"]).strip().endswith((".", "?", "!"))), None)
    ln = (end - p + 0.5) if end is not None else 4.0
    ln = min(PLAY[1], max(3.5, ln), b - p)
    if ln < PLAY[0]: return None
    return round(p, 2), round(ln, 2)


# ----- the checked facts: a Wikipedia pack for the campaign's subject -----------------------------------------------------------
def search_titles(subject):
    """English Wikipedia article titles for a name (opensearch), keeping those that hold every word of 3 letters or more of the
    subject, so "Kevin Langue" never gives "Kevin Lang". [] when nothing fits or Wikipedia is out of reach."""
    import requests, factpack
    try:
        r = requests.get("https://en.wikipedia.org/w/api.php", headers=factpack.WIKI_UA, timeout=20,
                         params={"action": "opensearch", "search": subject, "limit": 4, "namespace": 0, "format": "json"})
        titles = r.json()[1] if r.ok else []
    except Exception:
        return []
    want = [w for w in re.findall(r"[a-z0-9]+", subject.lower()) if len(w) >= 3]
    return [t for t in titles if want and all(w in re.sub(r"[^a-z0-9 ]", " ", t.lower()) for w in want)][:2]


def wiki_candidates(c):
    w = c.get("wikipedia")
    if isinstance(w, str): w = [w]
    return [str(x) for x in w] if w else search_titles(str(c.get("subject") or ""))


def wiki_pack(cid, c, cache=None, today=None):
    """Checked facts about the campaign's subject, built the way writer.py builds an evergreen pack from a Wikipedia article:
    the article's text, a Lite model's facts each with a quote, and only the facts whose quote is in the article word for word
    and whose numbers match (factpack.verify) are kept. The campaign names its articles ("wikipedia": [...]); without, the
    subject is searched. Cached in clips/state/wiki/<campaign>.json for two weeks. None when no article gives 3 facts."""
    import factpack
    today = today or dt.date.today()
    path = (cache or STATE / "wiki") / f"{cid}.json"
    try:
        old = json.loads(path.read_text())
        if (today - dt.date.fromisoformat(old["built"])).days < TTL_DAYS and old.get("subject") == c.get("subject") and old.get("one_source"):
            return old
    except Exception: pass
    import writer as W
    subject = str(c.get("subject") or cid)
    q = f"{subject}: who they are and what makes them worth watching"
    for title in wiki_candidates(c):
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        try:
            txt, img = factpack.page_text(url, wiki=True)
            if len(txt) < 800: continue
            got, _, single, _ = factpack.facts_from(W.EVERGREEN_FACTS.format(q=q, how=W.HOW["evergreen"], title=title, url=url, text=txt),
                                                    {1: factpack.norm(txt)}, {1: "wikipedia"}, want=W.MIN_FACTS["evergreen"])
        except Exception as e:
            log(f"{cid}: wikipedia {title}: {str(e)[:120]}"); continue
        if len(single) < W.MIN_FACTS["evergreen"]: log(f"{cid}: wikipedia {title}: only {len(single)} checked facts"); continue
        pack = {"topic": subject, "kind": "evergreen", "signal": "clip commentary", "category": "", "what_is_new": "", "hooks": [],
                "sources": [[title, url, "Wikipedia", ""]], "verified": [], "one_source": single[:10], "images": [],
                "subject": subject, "built": str(today)}
        try: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(pack, indent=1, ensure_ascii=False))
        except OSError as e: log(f"{cid}: wikipedia pack not cached: {e}")
        return pack
    return None


def with_moment(pack, c, m, said):
    """The pack for one moment: the Wikipedia facts, plus the footage as the last source and what is said in it as its one fact (the
    only thing a commentary may claim about the footage). Returns (pack, the footage's source number)."""
    p = dict(pack)
    p["sources"] = [list(s) for s in pack["sources"]] + [[str(c.get("name") or c.get("subject")), str(c.get("url") or "https://app.vyro.com/campaigns"),
                                                          "the campaign's footage", ""]]
    n = len(p["sources"])
    p["one_source"] = list(pack.get("one_source") or []) + [
        {"claim": f"In the footage, as said: \"{said[:520]}\"", "sources": [n]},
        *([{"claim": f"What the moment is: {m['why']}", "sources": [n]}] if m.get("why") else [])]
    return p, n


# ----- the words --------------------------------------------------------------------------------------------------------------
PROMPT = """You write a commentary Short (one JSON script) for {channel}, a family-friendly UK clips channel. YouTube no longer
recommends re-uploaded clips, so this Short is OUR commentary: our argument and checked context fill most of the runtime and the
footage is only the evidence for our point. Every rule below must hold.

THE CAMPAIGN AND ITS RULES (the clip's own rules still apply)
- Subject: {subject}. Footage: {label}.
- {focus}
- {on_screen}
- Avoid: {avoid}

THE MOMENT (the only thing you may say about the footage; say nothing else about what happens in it)
- What is said in it: "{said}"
- Why it was picked: {why}. The planner's hook: "{hook}".
- After the evidence beat the footage plays by itself with its own sound for {play} seconds: that is the punchline.

THE PACK (checked facts; state them plainly, never name the source, never use a fact that is not here)
{pack}

Write {nlo} to {nhi} beats in this order:
1. role "hook" ({hw} words or fewer): our take on the moment as a plain statement, the subject's name inside its first four words
   ({subject}). Not a question, never "Did you know", "Watch", "Look" or a greeting.
2. one or two "context" beats: a fact about {subject} or the game from the pack, told so it matters for the take (what it says
   about them, what most people would do). One or two sentences each.
3. exactly one "evidence" beat ({ew} words or fewer): the line that sets up what to listen for, in terms of our argument. The
   footage then plays on its own, so end on the line that leads into it. Never narrate the picture ("Watch what happens", "Here
   he...", "Look at...").
4. a final "payoff" beat: lands the argument in one sentence of our own (a verdict or comparison built from the pack and the
   moment), then a short question the viewers can answer in the comments.
Narration in all: {wlo} to {whi} words (count them). One or two sentences a beat. Open each context beat on a new fact, not on
the last beat's words.

Rules: UK English (colour, favourite, "Tuesday 20 October"), never an en or em dash. Nothing invented: only the pack and the moment.
Our own point: set two facts side by side, or a fact against the moment, and say what follows. Family friendly. Never politics, crime,
health claims, money or investing advice, adult content or gambling. Never negative about a real person (no admits, betrays, slams,
feuds, backlash, mocked, exposed, blamed, fails, flops, quits, drama), however the footage looks; praise what they did, made or won,
and keep the take warm or curious. Never say "viral", "views" or "subscribers". No swearing.
title: under 50 characters, {subject} first, a plain promise (never a question), ending with ONE emoji. alt_title: another angle, same
rules. summary: one or two sentences. hashtags: 8 to 12, exact names first, each "#Word" with letters and numbers only. tags: 5 to 10
search phrases. comment: one question under 100 characters, no links. facts: every claim in the narration as [claim, [source
numbers from the pack]]; the footage is source {foot}.
Return only JSON: {{"beats": [{{"role": "hook", "say": "...", "pic": ""}}, ...], "title": "...", "alt_title": "...", "summary": "...",
"hashtags": ["#..."], "tags": ["..."], "comment": "...", "facts": [["claim", [1]]]}}. "pic": for a context beat, the full name of a
person, game or place worth a photo from Wikimedia Commons (2 to 4 words), else empty."""

CHECK_NOTE = "\n\nIt fails these checks. Fix every one and return the whole corrected JSON:\n- "


def pack_text(pack):
    import writer as W
    return W.pack_text(pack)


def prompt_for(ctx, pack, said):
    c = ctx["campaign"]; r = c.get("rules") or {}
    return PROMPT.format(channel=ctx["handle"], subject=c["subject"], label=(c.get("source") or {}).get("label", c["subject"]),
                         focus=r.get("focus", ""), on_screen=r.get("on_screen", ""), avoid="; ".join(r.get("avoid") or []) or "nothing special",
                         said=said[:520], why=ctx["moment"].get("why") or "the funniest or biggest moment", hook=ctx["moment"].get("hook", ""),
                         play=f"{ctx['play_len']:.0f}", pack=pack_text(pack), nlo=BEATS[0], nhi=BEATS[1], hw=HOOK_WORDS, ew=EVIDENCE_WORDS,
                         wlo=WORDS[0], whi=WORDS[1], foot=ctx["foot"])


def ask(prompt, temperature):
    import factpack
    ans, model = factpack.gemini(prompt, None, timeout=150, temperature=temperature, writing=True, lite=True)     # the free chain, never Claude
    if isinstance(ans, list): ans = next((x for x in ans if isinstance(x, dict)), {})
    return (ans if isinstance(ans, dict) else {}), model


# ----- the board: shots, sound and sources are ours ---------------------------------------------------------------------------
MOVES = ["in", "left", "out", "right", "up", "down"]


def hashtags(c, model_tags, category):
    """The campaign's hashtags first, then the model's, then fillers up to 8; at most 15, #Word only, no duplicates, no #Shorts."""
    out, seen = [], set()
    for h in list((c.get("rules") or {}).get("hashtags") or []) + list(model_tags or []) + ["#" + category] + FILLER_TAGS:
        h = "#" + re.sub(r"[^A-Za-z0-9_]", "", str(h)).lstrip("#")
        if not re.fullmatch(r"#\w{2,40}", h) or h.lower() in seen or h.lower() == "#shorts": continue
        seen.add(h.lower()); out.append(h)
    return out[:15]


def assemble(ans, ctx, model):
    """The board for a model's answer. The model's words become the beats; everything else is ours: the shots (stills of the
    footage, a Commons photo where the campaign allows pictures from outside, the evidence as the one clip: shot), the
    let-it-play window (as long as the punchline and the 40% rule allow), the sources, the hashtags, the music."""
    c, m = ctx["campaign"], ctx["moment"]
    raw = [x for x in ans.get("beats") or [] if isinstance(x, dict) and str(x.get("say") or "").strip()]
    beats = []
    for i, x in enumerate(raw):
        role = str(x.get("role") or "").strip().lower()
        if role not in ("hook", "context", "evidence", "payoff"): role = "hook" if i == 0 else "payoff" if i == len(raw) - 1 else "context"
        beats.append({"role": role, "say": undash(x.get("say")), "pic": undash(x.get("pic"))[:40]})
    pool, credit, source = list(ctx["stills"]), ctx["credit"], ctx["source_url"]
    out, k = [], 0

    def still():
        """The next still of the footage in turn (the first is the hook's), framed with the next camera move."""
        nonlocal k
        s = {"src": pool[k % len(pool)], "move": MOVES[k % len(MOVES)], "credit": credit, "source": source}; k += 1
        return s
    play = float(ctx["play_len"])
    ev_i = next((i for i, x in enumerate(beats) if x["role"] == "evidence"), None)
    if ev_i is not None:       # the let-it-play window: the punchline's length, within what keeps the footage under SAFE_SHARE of the runtime
        n_words = sum(words_of(x["say"]) for x in beats)
        rest = (n_words - words_of(beats[ev_i]["say"])) / WPS + GAP * (len(beats) - 1) + TAIL + 0.06
        e = words_of(beats[ev_i]["say"]) / WPS + GAP
        play = round(max(0.0, min(play, PLAY[1], SAFE_SHARE / (1 - SAFE_SHARE) * rest - e)), 2)
    for i, x in enumerate(beats):
        bt = {"say": x["say"], "visual": {"type": "none"}}
        shots = []
        if x["role"] == "evidence":
            p_in = round(ctx["play_at"] - ctx["ev_lo"], 2)
            bt["letplay"] = play
            shots = [{"src": f"clip:{ctx['ev_path']}:{max(0.0, p_in - 6.0):.2f}:{p_in + play:.2f}", "move": "still", "zoom": 1.0,
                      "sound": {"duck": DUCK}, "play_at": p_in, "credit": credit, "source": source}]
        else:
            if x["role"] == "context" and x["pic"] and ctx["outside"]:        # a Commons photo first, where the campaign allows pictures from outside
                shots.append({"src": f"commons-search:{x['pic']}", "move": MOVES[k % len(MOVES)]}); k += 1
            shots += [still() for _ in range(1 if x["role"] == "hook" or shots else 2)]      # the footage's stills: a beat always has one that cannot fail
            if x["role"] == "hook": shots[0]["label"] = {"t": c["subject"], "s": ctx["role"]}
            if x["role"] in ("hook", "payoff"): bt["impact"] = True
        bt["shots"] = shots
        out.append(bt)
    meta_sources = [[s[0], s[1]] for s in ctx["sources"]]
    facts = []
    for f in ans.get("facts") or []:
        if isinstance(f, (list, tuple)) and len(f) == 2 and isinstance(f[1], list):
            nums = [int(n) for n in f[1] if str(n).isdigit() and 1 <= int(n) <= len(meta_sources)]
            if str(f[0]).strip() and nums: facts.append([undash(f[0]), nums])
    title, alt = undash(ans.get("title"))[:70], undash(ans.get("alt_title"))[:70]
    b = {"id": ctx["id"], "created": ctx["day"], "format": "one_detail", "category": ctx["category"], "kind": KIND, "source": f"clips:{ctx['cid']}",
         "appeal": "fans", "music": {"mood": MOODS.get(ctx["category"], "playful")}, "beats": out,
         "meta": {"title": title, "alt_title": alt, "summary": undash(ans.get("summary")),
                  "hashtags": hashtags(c, ans.get("hashtags"), ctx["category"]),
                  "tags": [undash(t) for t in (ans.get("tags") or []) if str(t).strip()][:12], "comment": undash(ans.get("comment"))[:99],
                  "sources": meta_sources, "facts": facts},
         "bgvideo": False, "handle": ctx["handle"], "writer": model,
         "test": {"clip_campaign": ctx["cid"], "clip_moment": m["id"]},
         "clip": {"campaign": ctx["cid"], "moment": m["id"], "evidence": ctx["ev_path"], "play_at": ctx["play_at"], "play_len": play, "roles": [x["role"] for x in beats]}}
    import background as BG
    BG.fill(b)
    return b


# ----- the rules, checked ------------------------------------------------------------------------------------------------------
def timing(b):
    """Estimated runtime of a commentary board: {seconds, footage (seconds of the beats that play footage), share, piece (the
    longest run of footage beats)}. A beat lasts its words at WPS, the pause after it, and its let-it-play window."""
    total, foot, piece, run = 0.06, 0.0, 0.0, 0.0
    for bt in b.get("beats") or []:
        d = words_of(bt.get("say")) / WPS + GAP + float(bt.get("letplay") or 0)
        total += d
        if any(footage_shot(s) for s in bt.get("shots") or []): foot += d; run += d; piece = max(piece, run)
        else: run = 0.0
    total += TAIL
    return {"seconds": round(total, 1), "footage": round(foot, 1), "share": round(foot / total, 3) if total else 0.0, "piece": round(piece, 1)}


def footage_shot(s):
    """True for a clip: shot that plays footage (it has a start and a different end); a freeze frame or a still picture does not."""
    src = str((s or {}).get("src", ""))
    m = re.search(r":(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$", src)
    return src.startswith("clip:") and bool(m) and abs(float(m.group(2)) - float(m.group(1))) >= 0.05


def subject_in(subject, text, first=4):
    """The subject's name (any word of 3 letters or more, 's dropped) is among the first `first` words of the text."""
    head = [re.sub(r"['’]s$", "", w).strip(".,:;!?").lower() for w in str(text).split()[:first]]
    return any(w in head for w in (re.sub(r"[^a-z0-9]", "", x.lower()) for x in re.findall(r"[\w'’]+", subject)) if len(w) >= 3)


def check(b, ctx):
    """(errors, warnings) for a commentary board: validate.py's rules, then the commentary's own: 5 to 7 beats of the right roles
    in order, 90 to 120 words, a hook of 12 words or fewer that names the subject in its first four words, an evidence line
    of 22 words or fewer, a let-it-play window of 2.5 to 6 seconds, the footage at most 40% of the runtime and 15 seconds in one
    piece, no narrating of the picture, nothing negative about anyone anywhere in the script, and every fact sourced."""
    import validate
    e, w = validate.check(b)
    beats, c = b.get("beats") or [], ctx["campaign"]
    roles = (b.get("clip") or {}).get("roles") or []
    if not BEATS[0] <= len(beats) <= BEATS[1]: e.append(f"beats: {BEATS[0]} to {BEATS[1]} beats ({len(beats)} given)")
    if roles and (roles[0] != "hook" or roles[-1] != "payoff" or roles.count("evidence") != 1 or not 1 <= roles.count("context") <= 2
                  or [r for r in roles if r not in ("hook", "context", "evidence", "payoff")]):
        e.append("roles: a hook first, one or two context beats, exactly one evidence beat, a payoff last")
    n = sum(words_of(x.get("say")) for x in beats)
    if not WORDS[0] <= n <= WORDS[1]: e.append(f"narration: {n} words, needs {WORDS[0]} to {WORDS[1]}")
    if beats and words_of(beats[0].get("say")) > HOOK_WORDS: e.append(f"hook: {words_of(beats[0].get('say'))} words, {HOOK_WORDS} or fewer")
    if beats and not subject_in(c["subject"], beats[0].get("say", "")): e.append(f"hook: name {c['subject']} in the first four words")
    ev = [x for x, r in zip(beats, roles) if r == "evidence"]
    if ev and words_of(ev[0].get("say")) > EVIDENCE_WORDS: e.append(f"evidence beat: {words_of(ev[0].get('say'))} words, {EVIDENCE_WORDS} or fewer")
    if ev and not PLAY[0] <= float(ev[0].get("letplay") or 0) <= PLAY[1]:
        e.append(f"evidence beat: the footage must play {PLAY[0]} to {PLAY[1]} seconds by itself, which only fits under the 40% rule with more words in the other beats (up to {WORDS[1]} in all) or a shorter evidence line")
    t = timing(b)
    if t["share"] > FOOTAGE_MAX: e.append(f"footage: {t['share']:.0%} of the runtime, at most {FOOTAGE_MAX:.0%}: make the other beats longer or the evidence line shorter")
    if t["piece"] > PIECE_MAX: e.append(f"footage: {t['piece']:.0f} seconds in one piece, at most {PIECE_MAX:.0f}")
    if not SECONDS[0] <= t["seconds"] <= SECONDS[1] + 3: w.append(f"runtime: about {t['seconds']:.0f} seconds, best {SECONDS[0]} to {SECONDS[1]}")
    text = " ".join([x.get("say", "") for x in beats] + [b["meta"].get("title", ""), b["meta"].get("summary", ""), b["meta"].get("alt_title", "")])
    neg = sorted({h.lower() for h in validate.NEGATIVE.findall(text)})
    if neg: e.append(f"negative framing of a real person anywhere in the script: {neg}")
    for x, r in zip(beats, roles):
        if r != "evidence" and NARRATES.search(x.get("say", "")): e.append(f"narrates the picture: {x['say'][:50]!r}: make an argument instead")
    prof, uns = ctx.get("profane"), ctx.get("unsafe")
    if prof and prof.search(text): e.append("strong language in the script")
    if uns and uns.search(text): e.append("not brand safe: " + (uns.search(text).group(0)))
    if len(b["meta"].get("facts") or []) < 2: e.append("meta.facts: at least 2 claims, each [claim, [source numbers]]")
    return e, w


def fact_problems(b, pack):
    """The model-based check of the script against the pack (writer.fact_check): the problems it finds; [] when it cannot run."""
    try:
        import writer as W
        return ["facts: " + x for x in W.fact_check(b, pack)]
    except Exception as ex:
        log(f"{b.get('id')}: fact check not run: {str(ex)[:100]}")
        return []


def write(ctx, pack, said, tries=3):
    """The board for a moment: written by the free model chain, shaped (assemble), checked (check, then the fact check) and
    fixed with the problems named, twice at most (the way writer.write_board does). (board, model, notes) or (None, "", why)."""
    prompt = prompt_for(ctx, pack, said)
    ans, model = ask(prompt, 0.7)
    best = None
    for attempt in range(tries):
        b = assemble(ans, ctx, model)
        errs, warns = check(b, ctx)
        if not errs: errs = fact_problems(b, pack)
        if not errs:
            if not warns or best: return b, model, f"{len(warns)} warnings"
            best = (b, model, f"{len(warns)} warnings ({'; '.join(warns)[:160]})")
        elif best: return best
        if attempt == tries - 1: break
        fix = prompt + "\n\nYOUR SCRIPT\n" + json.dumps(ans, ensure_ascii=False) + CHECK_NOTE + "\n- ".join(errs + warns)
        ans, model = ask(fix, 0.3)
    return best or (None, "", "still failing: " + "; ".join(errs)[:300])


# ----- the render -------------------------------------------------------------------------------------------------------------
def render(board, path, sid, channel="clips", timeout=1500):
    """Renders a board with run_board.py, the Daily render (house voice with the clearest-read retries, music, captions, the
    footage's own sound in its window). path: the board file under boards/. Returns {"video", "seconds", "footage_seconds",
    "footage_share", "status", "upload"}; raises with the render's own error when it fails. What the render measured about the
    footage comes from its timeline (the clip: video shots)."""
    rel = os.path.relpath(path, ROOT)
    env = dict(os.environ, JOB_JSON=json.dumps({"board": rel, "mode": "none", "channel": channel}), TQDM_DISABLE="1")
    r = subprocess.run([sys.executable, str(ROOT / "pipeline" / "run_board.py")], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout)
    res = ROOT / "result" / sid
    try: status = json.loads((res / "status.json").read_text())
    except Exception: raise RuntimeError(f"the render left no status ({r.returncode}): {(r.stderr or r.stdout)[-400:]}")
    if status.get("state") != "rendered" or not (res / "video.mp4").exists():
        raise RuntimeError(f"the render failed: {status.get('error') or status.get('state')}")
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(res / "video.mp4")],
                                capture_output=True, text=True).stdout.strip() or 0)
    foot = 0.0
    try:
        tl = json.loads((ROOT / "pipeline" / "out" / f"{sid}.timeline.json").read_text())
        foot = sum(s["t1"] - s["t0"] for s in tl.get("shots") or [] if s.get("kind") == "video")
    except Exception: pass
    try: upload = json.loads((res / "upload.json").read_text())
    except Exception: upload = {}
    return {"video": res / "video.mp4", "seconds": round(secs, 1), "footage_seconds": round(foot, 1),
            "footage_share": round(foot / secs, 3) if secs else 0.0, "status": status, "upload": upload}


def cleanup(sid):
    """The render's working files for a board (result/, media/, voice/, out/): a runner's disk is for the next clip."""
    p = ROOT / "pipeline"
    for d in [ROOT / "result" / sid, p / "media" / sid, *p.glob(f"voice/{sid}-*"), *p.glob(f"out/{sid}*")]:
        try:
            if d.is_dir(): shutil.rmtree(d, ignore_errors=True)
            elif d.exists(): d.unlink()
        except OSError: pass


def credit_lines(desc):
    """The picture-credit and music lines of a Daily description (run_board.description): the "Visuals:" block and the "Music" line."""
    out, mode = [], False
    for ln in str(desc or "").splitlines():
        if ln.startswith("Visuals:") or ln.startswith("Imágenes:"): mode = True; out.append(ln); continue
        if mode:
            if not ln.strip(): mode = False
            else: out.append(ln)
        elif ln.startswith(("Music", "Música")): out.append(ln)
    return out


def description(c, m, rules_desc, ad_note):
    """A commentary clip's YouTube description: #ad and the summary first, the campaign's hashtags and the board's, the sources, the
    picture and music credits, then the footage's credit and the paid-clip note (UK advertising rules, as every campaign clip)."""
    r = c.get("rules") or {}
    out = [f"#ad {m.get('summary') or m.get('hook', '')} {rules_desc}".strip(), "", " ".join(m.get("hashtags") or r.get("hashtags") or []), ""]
    if m.get("sources"): out += ["Sources:"] + [f"{t}: {u}" for t, u in m["sources"] if "app.vyro.com" not in u and "contentrewards.com" not in u] + [""]
    seen = set(); cr = []
    for ln in m.get("credits") or []:
        if ln not in seen: seen.add(ln); cr.append(ln)
    if cr: out += cr + [""]
    out.append(f"Clip from {(c.get('source') or {}).get('label', '')}, posted with the creator's permission ({c.get('name', '')}). {ad_note}")
    return "\n".join(x for i, x in enumerate(out) if x or (i and out[i - 1]))
