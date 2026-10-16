# Rough intelligibility check for narration: offline recognition (pocketsphinx), then how many of the
# script's content words were heard. Catches skipped clauses and babble, not subtle mispronunciations.
import re, sys, json
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
from pocketsphinx import Decoder

STOP = set("the a an and of to in on is it its it's for with as at by be or but if so this that these those was were are he she they we you".split())

def hear(path):
    y, sr = sf.read(path, dtype="float32")
    if y.ndim > 1: y = y.mean(1)
    y = resample_poly(y, 16000, sr)
    pcm = (np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes()
    d = Decoder(samprate=16000)
    d.start_utt(); d.process_raw(pcm, full_utt=True); d.end_utt()
    return d.hyp().hypstr if d.hyp() else ""

def words(s):
    return [w for w in re.sub(r"[^a-z' ]", " ", s.lower()).split() if w]

def recall(script, heard):
    want = [w for w in words(script) if w not in STOP and len(w) > 2]
    got = set(words(heard))
    hit = [w for w in want if w in got or w.rstrip("s") in got or (w + "s") in got]
    return round(len(hit) / max(1, len(want)), 2), [w for w in want if w not in hit]

if __name__ == "__main__":
    # usage: qa_asr.py file.wav "script text" [file.wav "script" ...]
    args = sys.argv[1:]
    for f, s in zip(args[::2], args[1::2]):
        h = hear(f); r, miss = recall(s, h)
        print(json.dumps({"file": f.split("/")[-1], "recall": r, "missing": miss[:8], "heard": h[:120]}))
