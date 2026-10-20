#!/usr/bin/env bash
# The engine for the open model on this runner (llama.cpp, MIT licence): a pinned release, else the latest one. Nothing
# runs yet: factpack.local_llm() starts llama-server (and downloads the model) only when every API model is out of
# quota. Sets LLAMA_SERVER for the workflow's next steps; never fails the job.
set -u
tag="${LLAMA_TAG:-b11757}"
get() { curl -sfL --retry 3 "https://github.com/ggml-org/llama.cpp/releases/download/$1/llama-$1-bin-ubuntu-x64.tar.gz" -o /tmp/llama.tgz; }
if ! get "$tag"; then
  tag=$(curl -sf -H "Authorization: Bearer ${GH_TOKEN:-}" https://api.github.com/repos/ggml-org/llama.cpp/releases/latest \
        | python3 -c "import json, sys; print(json.load(sys.stdin)['tag_name'])") && get "$tag" \
    || { echo "llama.cpp: no release downloaded, the writer runs without the local model"; exit 0; }
fi
mkdir -p /tmp/llama && tar -xzf /tmp/llama.tgz -C /tmp/llama
bin=$(find /tmp/llama -name llama-server -type f | head -1)
if [ -n "$bin" ] && "$bin" --version >/dev/null 2>&1; then
  echo "LLAMA_SERVER=$bin" >> "${GITHUB_ENV:-/dev/null}"; echo "llama.cpp $tag ready: $bin"
else
  echo "llama.cpp $tag: llama-server would not run, the writer runs without the local model"
fi
exit 0
