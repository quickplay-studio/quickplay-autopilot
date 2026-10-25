"""Download the Chatterbox voice models (MIT licence) at pinned revisions and check every file's hash.
usage: python get_model.py <dir>            the standard model (every Short's voices)
       python get_model.py <dir> --turbo    Chatterbox-Turbo, for the george_turbo voice (24 October; chatterbox-tts 0.1.7 reads it)
       python get_model.py <dir> --multilingual    Chatterbox Multilingual, for the Spanish mirror's voice (25 October; pipeline/mirror.py)
A hash of 64 hex digits is a SHA-256 (the large weight files); one of 40 is the file's git blob id, which is what the Hugging Face
file list gives for the small text files (SHA-1 of "blob <size>", a NUL byte, then the file)."""
import hashlib, pathlib, re, sys
from huggingface_hub import hf_hub_download

REPO, REV = "ResembleAI/chatterbox", "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
FILES = {"t3_cfg.safetensors": "914cb1696f47527fe8852ca8f1fe1fa63cb34f76f9c715e84e067b744dd0da81",
         "s3gen.safetensors": "2b78103c654207393955e4900aac14a12de8ef25f4b09424f1ef91941f161d4e",
         "ve.safetensors": "f0921cab452fa278bc25cd23ffd59d36f816d7dc5181dd1bef9751a7fb61f63c",
         "tokenizer.json": None}
# Chatterbox-Turbo (ResembleAI/chatterbox-turbo, not gated, 15 December 2025 is its latest commit): the files ChatterboxTurboTTS.from_local
# reads (chatterbox-tts 0.1.7, chatterbox/tts_turbo.py), not the standard s3gen.safetensors, conds.pt or the README
TURBO_REPO, TURBO_REV = "ResembleAI/chatterbox-turbo", "749d1c1a46eb10492095d68fbcf55691ccf137cd"
TURBO_FILES = {"t3_turbo_v1.safetensors": "fcf1f8c1d651bb7e3acd69ee5be269b4ac10c02980b7708213d598bc9f7cdf87",
               "s3gen_meanflow.safetensors": "d65cb687a2ed581ee6cc297e919ffefa63386944f42364ae13b78a594945514f",
               "ve.safetensors": "f0921cab452fa278bc25cd23ffd59d36f816d7dc5181dd1bef9751a7fb61f63c",     # the same file as the standard model's
               "vocab.json": "a15dd0028acd1dd2c1c2394c80e1de8f3f12a0e4",
               "merges.txt": "226b0752cac7789c48f0cb3ec53eda48b7be36cc",
               "tokenizer_config.json": "58bc759ea7dab3dd5442f0500e493f170eeba67f",
               "added_tokens.json": "fd85325cdfafc690469b6f0e8aeb5cf4649c1450",
               "special_tokens_map.json": "b2d2dbc845800c78fe98656af927d831ab4ff7b7"}

# Chatterbox Multilingual (the same ResembleAI repo, later files; chatterbox-tts 0.1.7, chatterbox/mtl_tts.py reads ve.pt,
# t3_mtl23ls_v2.safetensors, s3gen.pt, grapheme_mtl_merged_expanded_v1.json and, as the built-in voice, conds.pt). It could not be
# pinned when it was added (25 October: Hugging Face was not reachable from where it was written), so the first run resolves
# MTL_REV ("main") to its commit, downloads at that commit and prints the commit and every file's SHA-256: put them in MTL_REV
# and MTL_FILES to pin it like the models above. The render step that runs it is optional (a failure costs a Spanish Short's
# voice, never the main channel), and its cache keeps the first download.
MTL_REPO, MTL_REV = "ResembleAI/chatterbox", "main"
MTL_FILES = {"ve.pt": None, "t3_mtl23ls_v2.safetensors": None, "s3gen.pt": None, "grapheme_mtl_merged_expanded_v1.json": None, "conds.pt": None}

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""): h.update(b)
    return h.hexdigest()

def blob_id(p):
    data = pathlib.Path(p).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

def matches(p, want):
    return sha256(p) == want if len(want) == 64 else blob_id(p) == want

def fetch(repo, rev, files, dest):
    """Every file of `files` in `dest`, downloaded from `repo` at commit `rev` when missing and checked against its hash
    (None: not checked). A file that fails its check is deleted and the run stops."""
    dest = pathlib.Path(dest); dest.mkdir(parents=True, exist_ok=True)
    for name, want in files.items():
        f = dest / name
        if not f.exists():
            hf_hub_download(repo, name, revision=rev, local_dir=dest)
        if want and not matches(f, want):
            f.unlink(); sys.exit(f"{name}: hash mismatch, deleted")
        print(name, "ok" if want else f"ok (not pinned) sha256 {sha256(f)}")

def resolve(repo, rev):
    """A branch name as the commit it is now (printed, so it can be pinned); a commit stays as it is."""
    if re.fullmatch(r"[0-9a-f]{40}", rev): return rev
    try:
        from huggingface_hub import HfApi
        sha = HfApi().model_info(repo, revision=rev).sha
        print(f"{repo}@{rev} is commit {sha}: set MTL_REV to it to pin the download")
        return sha
    except Exception as e:
        print(f"could not resolve {repo}@{rev} to a commit ({type(e).__name__}); downloading it as it is")
        return rev

if __name__ == "__main__":
    if "--turbo" in sys.argv[2:]: fetch(TURBO_REPO, TURBO_REV, TURBO_FILES, sys.argv[1])
    elif "--multilingual" in sys.argv[2:]: fetch(MTL_REPO, resolve(MTL_REPO, MTL_REV), MTL_FILES, sys.argv[1])
    else: fetch(REPO, REV, FILES, sys.argv[1])
