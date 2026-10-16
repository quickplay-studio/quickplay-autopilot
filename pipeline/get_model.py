"""Download the Chatterbox voice model (MIT licence) at a pinned revision and check every file's hash.
usage: python get_model.py <dir>"""
import hashlib, pathlib, sys
from huggingface_hub import hf_hub_download

REPO, REV = "ResembleAI/chatterbox", "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
FILES = {"t3_cfg.safetensors": "914cb1696f47527fe8852ca8f1fe1fa63cb34f76f9c715e84e067b744dd0da81",
         "s3gen.safetensors": "2b78103c654207393955e4900aac14a12de8ef25f4b09424f1ef91941f161d4e",
         "ve.safetensors": "f0921cab452fa278bc25cd23ffd59d36f816d7dc5181dd1bef9751a7fb61f63c",
         "tokenizer.json": None}

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""): h.update(b)
    return h.hexdigest()

dest = pathlib.Path(sys.argv[1]); dest.mkdir(parents=True, exist_ok=True)
for name, want in FILES.items():
    f = dest / name
    if not f.exists():
        hf_hub_download(REPO, name, revision=REV, local_dir=dest)
    if want and sha256(f) != want:
        f.unlink(); sys.exit(f"{name}: hash mismatch, deleted")
    print(name, "ok")
