"""Which of a search's pictures fits the beat? SigLIP 2 scores them (fetch_media.py, 24 October).

Until now fetch_media took the first picture a source returned (Commons by search rank and width, Pixabay by tag match), so a
Steam Deck Short got a steam locomotive, a "Munich Re" logo and a German speed-test screenshot (review/TEST-L1024.jpg). Here
each beat's candidates (the first TOP_K photos or video thumbnails of a search) are scored against the beat's own words with
SigLIP 2 base (google/siglip2-base-patch16-224, Apache-2.0, on the CPU: about 0.1 to 0.3 s a picture, model load 5 to 10 s):

  text   the shot's search words, its label, the beat's "say" line and the board's subject (first tag, with its category),
         each as one prompt, their vectors averaged (context());
  junk   the same picture is scored against "a logo", "a map", "a document", "a screenshot", "a blurry photo"; when one of
         those fits the picture better than the beat does, the difference (half of it) is taken off;
  score  sim = cos(picture, text) - JUNK_W * max(0, cos(picture, junk) - cos(picture, text));
         relevance = sigmoid(logit_scale * sim + logit_bias), SigLIP's own chance that the pair matches (0 to 1), which is
         what fetch_media keeps on the shot ("relevance") and status/<id>.json on the Short (media.pic_relevance).

A picture that is a near-duplicate (perceptual hash within PH_DIST of 64 bits, or vectors alike) of a better candidate in the
same list is dropped; one that repeats a picture already used in this Short goes behind the others. fetch_media then takes the
first. Every failure (no model files, no transformers, a bad thumbnail, the time budget) hands back None and fetch_media keeps
the source's own order, exactly as before; thumbnails that cannot be read stay unscored at the back.

The model comes from models/siglip2 (get_pictures.py: pinned download, MANIFEST.json, Actions cache) and is loaded on the first
need, from disk only. Nothing heavy is imported until then, so importing this module costs nothing and cannot fail.
"""
import io, json, math, os, pathlib, re, sys, time

HEADERS = {"User-Agent": "QuickplayAutopilot/1.0 (https://github.com/quickplay-studio/quickplay-autopilot)"}   # fetch_media passes its own

MODEL = "siglip2-base-patch16-224"
TOP_K = 8                    # candidates scored per search (the rest keep the source's order behind them)
BATCH = 8                    # pictures per forward pass
THUMB_PX = 448               # a thumbnail is cut down to this on its long side
MAX_BYTES = 4_000_000        # a thumbnail download bigger than this is not a thumbnail
BUDGET_S = 240               # seconds of ranking work one Short may use; after that the source's own order stands
JUNK = ("a logo", "a map", "a document", "a screenshot", "a blurry photo")
JUNK_KEY = {"a logo": "logo", "a map": "map", "a document": "document", "a screenshot": "screenshot"}   # a junk prompt the beat asks for is not used
JUNK_W = 0.5                 # how much of "looks more like junk than like the beat" is taken off
WEIGHTS = {"words": 0.40, "label": 0.15, "say": 0.25, "subject": 0.20}
PH_DIST = 6                  # near-duplicate: at most this many of the 64 hash bits differ
EMB_DUP = 0.95               # or the two picture vectors are this alike

_S = {}                      # the run's state (see reset())


def note(msg):
    print(f"  pictures: {msg}", file=sys.stderr)


def reset():
    """Forget everything (the model too). Tests use it; begin() does the per-Short part."""
    _S.clear()
    _S.update(model=None, tried=False, why="not tried", sha="", fails=0, texts={}, thumbs={}, embs={}, taken=[], subject="", category="",
              deadline=float("inf"), stats=_new_stats(), said_budget=False)


def _new_stats():
    return {"searches": 0, "scored": 0, "reranked": 0, "dups": 0, "files": 0, "secs": 0.0}


reset()


# ---------------- the model ----------------
class Model:
    """SigLIP 2 base through transformers, loaded from a local folder only. images() and texts() give unit vectors (numpy
    float32, one row each); scale and bias are the checkpoint's own logit_scale.exp() and logit_bias."""
    name = MODEL

    def __init__(self, path):
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        os.environ.setdefault("TQDM_DISABLE", "1")
        import numpy as np, torch
        from transformers import AutoImageProcessor, AutoModel
        self.np, self.torch = np, torch
        kw = {"local_files_only": True}
        try: model = AutoModel.from_pretrained(str(path), dtype=torch.float32, **kw)
        except TypeError: model = AutoModel.from_pretrained(str(path), torch_dtype=torch.float32, **kw)
        self.model = model.eval()
        self.tok = load_tokenizer(path)
        try: self.proc = AutoImageProcessor.from_pretrained(str(path), **kw)
        except Exception: self.proc = AutoImageProcessor.from_pretrained(str(path), use_fast=False, **kw)      # a "fast" processor needs torchvision
        self.scale = float(model.logit_scale.exp().item()) if hasattr(model, "logit_scale") else 100.0
        self.bias = float(model.logit_bias.item()) if hasattr(model, "logit_bias") else -16.0
        self.probe = self._probe() if Model.check else None

    check = True            # the colour probe below; off only for a random-weight stand-in model in a test

    def _probe(self):
        """A sanity check on the loaded model: four plain colour pictures against "a red picture" ... The right text should win for
        nearly all; fewer than 3 of 4 means the model, its tokenizer, its padding or the pooling is wrong and the ranker stays off
        (a wrong ranking would be worse than the search's own order). The result is logged so the first GitHub run shows whether
        the real checkpoint reads as expected. Returns the number right."""
        from PIL import Image
        cols = {"red": (220, 30, 30), "green": (30, 200, 60), "blue": (30, 60, 220), "yellow": (240, 220, 30)}
        E = self.images([Image.new("RGB", (224, 224), c) for c in cols.values()])
        T = self.texts([f"a {n} picture" for n in cols])
        if not self.np.isfinite(E).all() or not self.np.isfinite(T).all(): raise RuntimeError("vectors are not finite")
        if float((T @ T.T)[~self.np.eye(len(T), dtype=bool)].max()) > 0.995: raise RuntimeError("text vectors are not distinct")
        right = int(sum(int((E[i] @ T.T).argmax() == i) for i in range(len(cols))))
        if right < 3: raise RuntimeError(f"colour probe {right} of 4: the model does not read colours")
        return right

    @staticmethod
    def _pooled(out):
        """transformers 5 returns a model output (pooler_output holds the embedding); older versions return the tensor."""
        if getattr(out, "pooler_output", None) is not None: return out.pooler_output
        if isinstance(out, (tuple, list)): return out[1] if len(out) > 1 and out[1] is not None else out[0]
        return out

    def _unit(self, t):
        a = t.detach().float().cpu().numpy()
        return (a / self.np.maximum(self.np.linalg.norm(a, axis=1, keepdims=True), 1e-9)).astype(self.np.float32)

    def images(self, imgs):
        out = []
        with self.torch.inference_mode():
            for i in range(0, len(imgs), BATCH):
                inputs = self.proc(images=imgs[i:i + BATCH], return_tensors="pt")      # pixel_values (and, for NaFlex checkpoints, its masks)
                out.append(self._unit(self._pooled(self.model.get_image_features(**inputs))))
        return self.np.concatenate(out)

    def texts(self, texts):
        out = []
        with self.torch.inference_mode():
            for i in range(0, len(texts), 16):      # padded to the 64 tokens the model was trained on, with the checkpoint's own tokenizer settings
                enc = self.tok(texts[i:i + 16], padding="max_length", max_length=64, truncation=True, return_tensors="pt")
                inputs = {k: enc[k] for k in ("input_ids", "attention_mask") if k in enc}
                out.append(self._unit(self._pooled(self.model.get_text_features(**inputs))))
        return self.np.concatenate(out)


def load_tokenizer(path):
    """The checkpoint's own tokenizer (padding side, special tokens and lower-casing as its files say). transformers 5.2 cannot map a
    "siglip" model to a tokenizer without sentencepiece installed (AutoTokenizer raises an AttributeError): then the fast tokenizer
    is read straight from tokenizer.json, which is what AutoTokenizer does itself when the classes differ."""
    from transformers import AutoTokenizer
    try: return AutoTokenizer.from_pretrained(str(path), local_files_only=True)
    except Exception:
        from transformers import PreTrainedTokenizerFast
        return PreTrainedTokenizerFast.from_pretrained(str(path), local_files_only=True)


def model_dir():
    import get_pictures as GP
    return GP.models_dir() / GP.SIGLIP["dir"]


def use(model):
    """Put a model in place (tests); None turns the ranker off."""
    _S.update(model=model, tried=True, why="" if model is not None else "switched off", fails=0)


def available():
    """True when the model is loaded, loading it on the first call. False, with why() saying so, when it is not there or fails:
    callers then keep the source's own order."""
    if _S["model"] is not None: return True
    if _S["tried"]: return False
    _S["tried"] = True
    t0 = time.time()
    try:
        d = model_dir()
        try: m = json.loads((d / "MANIFEST.json").read_text())
        except Exception: m = None
        if not m: raise FileNotFoundError(f"no model files in {d.parent.name}/{d.name} (get_pictures.py did not finish)")
        _S["sha"] = ((m.get("files") or {}).get("model.safetensors") or {}).get("sha256", "")
        _S["model"] = Model(d)
        _S["why"] = ""
        probe = getattr(_S["model"], "probe", None)
        note(f"{MODEL} loaded in {time.time() - t0:.1f} s" + (f", colour probe {probe} of 4" if probe is not None else ""))
        return True
    except Exception as e:
        _S["model"] = None
        _S["why"] = f"{type(e).__name__}: {str(e)[:140]}"
        note(f"relevance ranking is off ({_S['why']}): pictures keep the search's own order")
        return False


def why():
    return _S["why"]


def unload():
    """Free the model's memory (about 1.5 GB) once the Short's pictures are chosen."""
    _S.update(model=None, tried=False)
    _S["texts"].clear(); _S["thumbs"].clear(); _S["embs"].clear()
    try:
        import gc; gc.collect()
    except Exception: pass


# ---------------- the Short ----------------
def begin(sb):
    """A new Short: clear what belongs to the last one (thumbnails, the pictures taken, the counters) and read the board's
    subject (its first tag, the story's own name, else the title's first words) and category."""
    m = sb.get("meta") or {}
    tags = [str(t).strip() for t in m.get("tags") or [] if str(t).strip()]
    title = " ".join(re.sub(r"[^\w' ]+", " ", str(m.get("title", ""))).split()[:6])
    _S.update(thumbs={}, embs={}, taken=[], stats=_new_stats(), deadline=time.time() + BUDGET_S, said_budget=False, fails=0,
              subject=tags[0] if tags else title, category=str(sb.get("category") or ""))


def _clean(s):
    return " ".join(re.sub(r"[^\w'\-,. ]+", " ", str(s or "")).lower().split())


def context(words="", say="", label=None):
    """The beat's text for the ranker: [(prompt, weight)] and the junk prompts to use. None when there is no text at all."""
    parts = []
    w = _clean(words)
    if w: parts.append((f"a photo of {w}", WEIGHTS["words"]))
    if isinstance(label, dict):
        l = ", ".join(x for x in (_clean(label.get("t")), _clean(label.get("s"))) if x)
        if l: parts.append((f"a photo of {l}", WEIGHTS["label"]))
    s = _clean(say)[:240]
    if s: parts.append((s, WEIGHTS["say"]))
    subj = _clean(_S["subject"])
    if subj: parts.append((f"a photo of {subj}" + (f", {_clean(_S['category'])}" if _S["category"] else ""), WEIGHTS["subject"]))
    if not parts: return None
    blob = " ".join(t for t, _ in parts)
    junk = [j for j in JUNK if not (j in JUNK_KEY and re.search(rf"\b{JUNK_KEY[j]}", blob))]
    return {"parts": parts, "junk": junk, "name": w or _clean(subj) or "?"}


# ---------------- thumbnails and hashes ----------------
def fetch_thumb(url):
    """A thumbnail as a small RGB PIL image, or None (any failure: it is then simply not scored)."""
    try:
        import requests
        from PIL import Image
        with requests.get(url, headers=HEADERS, timeout=(5, 20), stream=True) as r:
            r.raise_for_status()
            buf = bytearray()
            for chunk in r.iter_content(1 << 16):
                buf += chunk
                if len(buf) > MAX_BYTES: return None
        img = Image.open(io.BytesIO(bytes(buf)))
        img.draft("RGB", (THUMB_PX * 2, THUMB_PX * 2))
        img = img.convert("RGB"); img.thumbnail((THUMB_PX, THUMB_PX))
        return img
    except Exception: return None


def _fetch(urls):
    """{url: image or None} for the urls, each downloaded once per Short, six at a time."""
    need = [u for u in dict.fromkeys(urls) if u and u not in _S["thumbs"]]
    if need:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as ex:
            for u, img in zip(need, ex.map(fetch_thumb, need)): _S["thumbs"][u] = img
    return {u: _S["thumbs"].get(u) for u in urls if u}


def ahash(img):
    """A 64-bit average hash of a PIL image (the same as fetch_media._ahash)."""
    import numpy as np
    g = np.asarray(img.convert("L").resize((8, 8)), dtype=np.float32).ravel()
    return sum(1 << i for i, v in enumerate(g >= g.mean()) if v)


def phash(img):
    """A 64-bit perceptual hash (int) of a PIL image: imagehash's pHash, or the average hash when imagehash is not installed."""
    try:
        import imagehash
        return int(str(imagehash.phash(img)), 16)
    except Exception: return ahash(img)


def hamming(a, b):
    return bin(a ^ b).count("1")


def is_taken(h):
    """True when a picture used earlier in this Short is a near-duplicate of hash h."""
    return any(hamming(h, t) <= PH_DIST for t in _S["taken"])


def commit(info):
    """The picture with these scores was chosen: later candidates that repeat it go to the back."""
    if info and info.get("hash") is not None: _S["taken"].append(info["hash"])


# ---------------- scoring ----------------
def _text_vecs(texts):
    import numpy as np
    need = [t for t in dict.fromkeys(texts) if t not in _S["texts"]]
    if need:
        for t, v in zip(need, _S["model"].texts(need)): _S["texts"][t] = v
    return np.stack([_S["texts"][t] for t in texts])


def _score(E, ctx):
    """For each row of E (unit picture vectors): cos to the beat's text, cos to the nearest junk prompt, the junk-adjusted
    similarity and the relevance (0 to 1)."""
    import numpy as np
    parts = ctx["parts"]
    w = np.array([p[1] for p in parts], dtype=np.float32)
    q = (w[:, None] * _text_vecs([p[0] for p in parts])).sum(axis=0)
    q = q / max(float(np.linalg.norm(q)), 1e-9)
    cq = E @ q
    cj = (E @ _text_vecs(ctx["junk"]).T).max(axis=1) if ctx.get("junk") else np.zeros(len(E), dtype=np.float32)
    sim = cq - JUNK_W * np.maximum(0.0, cj - cq)
    z = np.clip(_S["model"].scale * sim + _S["model"].bias, -30.0, 30.0)
    return cq, cj, sim, 1.0 / (1.0 + np.exp(-z))


def _info(cq, cj, sim, rel, h):
    return {"rel": round(float(rel), 3), "sim": round(float(sim), 4), "cos": round(float(cq), 4), "junk": round(float(cj), 4), "hash": h}


def _fail(e):
    _S["fails"] += 1
    note(f"scoring failed ({type(e).__name__}: {str(e)[:120]}): the source's own order stands" + ("" if _S["fails"] < 3 else "; ranking off for this Short"))
    if _S["fails"] >= 3: _S.update(model=None, tried=True, why="three failures in a row")


def rank(thumbs, ctx, bonus=None):
    """Order a search's candidates by how well they fit the beat.
    thumbs: one thumbnail URL (or None) for each candidate, in the source's own order. ctx: context(). bonus: optional, one
    number per candidate added to its similarity (a vertical clip's small edge).
    Returns [(index, info)], best first: the first TOP_K candidates that could be scored, by similarity (a near-duplicate of a
    better one in the list is dropped; one repeating a picture already used in this Short goes last of these), then those whose
    thumbnail could not be read and those past TOP_K, in their own order, with info None. info has rel, sim, cos, junk, hash.
    None when the model is off, the time budget is used or anything fails: the caller keeps the source's own order."""
    if not thumbs or not ctx: return None
    if time.time() > _S["deadline"]:
        if not _S["said_budget"]: _S["said_budget"] = True; note(f"the {BUDGET_S} s ranking budget of this Short is used: the source's own order stands")
        return None
    if not available(): return None
    t0 = time.time()
    try:
        import numpy as np
        k = min(TOP_K, len(thumbs))
        imgs = _fetch(thumbs[:k])
        ok = [i for i in range(k) if thumbs[i] and imgs.get(thumbs[i]) is not None]
        if not ok: return None
        urls = [thumbs[i] for i in ok]
        need = [u for u in dict.fromkeys(urls) if u not in _S["embs"]]          # a picture seen again (another beat, the same search) is not read twice
        if need:
            for u, v in zip(need, _S["model"].images([imgs[u] for u in need])): _S["embs"][u] = v
        E = np.stack([_S["embs"][u] for u in urls])
        cq, cj, sim, rel = _score(E, ctx)
        adj = np.array(sim, dtype=np.float64) + np.array([(bonus[i] if bonus else 0.0) for i in ok])
        hashes = [phash(imgs[thumbs[i]]) for i in ok]
        keep, dropped = [], 0
        for j in sorted(range(len(ok)), key=lambda j: (-adj[j], ok[j])):
            if any(hamming(hashes[j], hashes[m]) <= PH_DIST or float(E[j] @ E[m]) >= EMB_DUP for m in keep): dropped += 1
            else: keep.append(j)
        keep = [j for j in keep if not is_taken(hashes[j])] + [j for j in keep if is_taken(hashes[j])]
        scored = [(ok[j], _info(cq[j], cj[j], sim[j], rel[j], hashes[j])) for j in keep]
        out = scored + [(i, None) for i in range(len(thumbs)) if i not in ok]       # dropped near-duplicates are in `ok`: they stay out
        st = _S["stats"]
        st["searches"] += 1; st["scored"] += len(ok); st["dups"] += dropped
        st["reranked"] += int(bool(out) and out[0][0] != ok[0])
        st["secs"] += time.time() - t0
        _S["fails"] = 0
        first = out[0][1]
        note(f"\"{ctx.get('name', '?')}\": scored {len(ok)} of {len(thumbs)}, picked #{out[0][0] + 1} (relevance {first['rel']}; "
             f"the search's own first scored {rel[0]:.3f}){f', {dropped} near-duplicates dropped' if dropped else ''}")
        return out
    except Exception as e:
        _fail(e); _S["stats"]["secs"] += time.time() - t0
        return None


def score_file(path, ctx):
    """Score one downloaded still picture (a shot from an explicit source: no candidates to choose between) so the Short's
    mean relevance covers every picture. The info of rank(), or None."""
    if not ctx or str(path).lower().rsplit(".", 1)[-1] not in ("jpg", "jpeg", "png", "webp"): return None
    if time.time() > _S["deadline"] or not available(): return None
    try:
        from PIL import Image
        img = Image.open(path); img.draft("RGB", (THUMB_PX * 2, THUMB_PX * 2))
        img = img.convert("RGB"); img.thumbnail((THUMB_PX, THUMB_PX))
    except Exception: return None                       # a file that is not a picture is not the model's failure
    t0 = time.time()
    try:
        cq, cj, sim, rel = _score(_S["model"].images([img]), ctx)
        _S["stats"]["files"] += 1
        _S["stats"]["secs"] += time.time() - t0
        return _info(cq[0], cj[0], sim[0], rel[0], phash(img))
    except Exception as e:
        _fail(e); return None


def summary():
    """What the ranker did for this Short, for status/<id>.json (media.pic_*)."""
    st = _S["stats"]
    out = {"pic_model": (f"{MODEL}:{_S['sha'][:12]}" if _S["sha"] else MODEL) if _S["model"] is not None
           else ("off: " + _S["why"][:100] if _S["tried"] else "not used")}
    if st["scored"] or st["files"]:
        out.update(pic_scored=st["scored"] + st["files"], pic_searches=st["searches"], pic_reranked=st["reranked"],
                   pic_dups=st["dups"], pic_secs=round(st["secs"], 1))
    return out
