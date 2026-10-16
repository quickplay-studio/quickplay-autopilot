# Timeline from pre-rendered narration (Chatterbox, one WAV per beat).
# Word times: split each beat at its audible pauses, match pauses to punctuation, then share each
# phrase's time between its words by syllable weight.
import json, pathlib, re, sys
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render as R

def pauses(y, sr, win=0.01, min_len=0.09, rel_db=-38):
    """(start, end) of silent stretches inside the clip, longest first is not assumed."""
    n = int(win * sr); f = len(y) // n
    rms = np.sqrt(np.mean(y[: f * n].reshape(f, n) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms / (rms.max() + 1e-9))
    quiet = db < rel_db
    out, i = [], 0
    while i < f:
        if quiet[i]:
            j = i
            while j < f and quiet[j]: j += 1
            if (j - i) * win >= min_len and i > 0 and j < f: out.append((i * win, j * win))
            i = j
        else: i += 1
    return out

def phrase_words(say):
    words = R.split_words(say); groups, cur = [], []
    for j, w in enumerate(words):
        cur.append(j)
        if re.search(r"[,;:.!?]$", w) and j < len(words) - 1: groups.append(cur); cur = []
    if cur: groups.append(cur)
    return words, groups

def word_times(say, y, sr, t0):
    words, groups = phrase_words(say)
    L = len(y) / sr
    gaps = pauses(y, sr)
    need = len(groups) - 1
    if need and len(gaps) >= need:
        # keep the `need` longest pauses, in time order, as phrase boundaries
        keep = sorted(sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)[:need])
        spans, s = [], 0.0
        for a, b in keep: spans.append((s, a)); s = b
        spans.append((s, L))
    else:   # no usable pauses: share time by syllables, with punctuation pauses
        wts = [sum(R.word_weight(words[j]) for j in g) for g in groups]
        tot = sum(wts); spans, s = [], 0.0
        for w in wts: spans.append((s, s + L * w / tot)); s += L * w / tot
    out = []
    for g, (a, b) in zip(groups, spans):
        wts = [R.word_weight(words[j]) for j in g]; tot = sum(wts); cur = a
        for j, w in zip(g, wts):
            d = (b - a) * w / tot
            out.append((j, round(t0 + cur, 3), round(t0 + cur + d, 3))); cur += d
    return words, out

def make_groups(words, sb):
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        brk = len(cur) >= sb.get("group", 3) or re.search(r"[.,!?;:]$", w["w"]) or i == len(words) - 1 or words[i + 1]["beat"] != w["beat"]
        if len(" ".join(words[k]["cap"] for k in cur)) > 22 and len(cur) > 1 and not brk: brk = True
        if brk:
            groups.append({"words": cur, "start": words[cur[0]]["start"], "end": words[cur[-1]]["end"]}); cur = []
    for g, nxt in zip(groups, groups[1:] + [None]):
        if nxt is not None and words[nxt["words"][0]]["beat"] == words[g["words"][0]]["beat"]: g["end"] = nxt["start"]
        else: g["end"] = round(g["end"] + 0.15, 3)
    return groups

def build_timeline_cb(sb, vdir, tag="cb", tempo=1.0):
    vdir = pathlib.Path(vdir); man = json.loads((vdir / f"{tag}_manifest.json").read_text())
    by_beat = {m["beat"]: m for m in man["beats"]}
    t = 0.06; gap = sb.get("gap", 0.2)
    segs, words, beats = [], [], []
    for bi, beat in enumerate(sb["beats"]):
        y, sr = sf.read(vdir / by_beat[bi]["file"], dtype="float32")
        if y.ndim > 1: y = y.mean(1)
        if tempo != 1.0:   # gentle speed-up without changing pitch
            import librosa
            y = librosa.effects.time_stretch(y, rate=tempo)
        y = resample_poly(y, R.SR, sr).astype(np.float32)
        say = beat["say"]; cw = R.split_words(beat.get("cap", say))
        sw, times = word_times(say, y, R.SR, t)
        if len(cw) != len(sw): cw = sw
        for j, a, b in times:
            words.append({"w": sw[j], "cap": re.sub(r"[,;:]$", "", cw[j]), "start": a, "end": b, "beat": bi})
        L = len(y) / R.SR
        segs.append((t, y)); beats.append({"start": round(t, 3), "speech_end": round(t + L, 3), "visual": beat["visual"]})
        t += L + beat.get("gap", gap)
    duration = t + sb.get("tail", 0.55)
    for i, b in enumerate(beats):
        b["end"] = round(beats[i + 1]["start"], 3) if i + 1 < len(beats) else round(duration, 3)
    return segs, words, beats, make_groups(words, sb), duration
