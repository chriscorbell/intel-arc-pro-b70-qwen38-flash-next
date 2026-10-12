#!/usr/bin/env bash
# Download ISTA-DASLab's GSQ-RCO IQ3_S GGUF of Qwen3.8-Flash-Next and its BF16 vision projector into MODELS_DIR, at
# the pinned revision, and check each file's SHA-256. About 84 GB. Resumes a partial download; skips finished files.
#   scripts/download-model.sh            uses MODELS_DIR from .env
#   VERIFY=0 scripts/download-model.sh   skips the checksums (they read all 84 GB once)
# Uses the `hf` CLI when it is installed (faster), curl otherwise. Set HF_TOKEN if you have one; the repo is public.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
: "${MODELS_DIR:?set MODELS_DIR in .env}"

repo=ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF
rev=ed59f92082b1e93c0e96d60a8b11aab089b52f09
files=(
  "IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf 54817524224 4c1eb2ceb4915e1192f4f386021897bde56a97f40a0bb78bb86465e0f7d2aca3"
  "IQ3_S/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf 28800138432 316b46f3a2dbd68c900f43136ab9449f9dcc3725dfd8c794847c204bc161e113"
  "mmproj-Qwen3.8-Flash-Next-BF16.gguf 907543008 b1a82259702816a5330d7bd7607cd9676b11780e79ff7348c21103ff3ce49bd0"
)
mkdir -p "$MODELS_DIR/IQ3_S"

for entry in "${files[@]}"; do
  read -r path size sha <<<"$entry"
  dest=$MODELS_DIR/$path
  if [ -f "$dest" ] && [ "$(stat -c %s "$dest")" = "$size" ]; then
    echo "have $path"
  elif command -v hf >/dev/null; then
    echo "downloading $path with hf"
    hf download "$repo" "$path" --revision "$rev" --local-dir "$MODELS_DIR"
  else
    echo "downloading $path with curl"
    auth=(); [ -n "${HF_TOKEN:-}" ] && auth=(-H "Authorization: Bearer $HF_TOKEN")
    curl -fL --retry 5 --retry-delay 10 -C - "${auth[@]}" -o "$dest" "https://huggingface.co/$repo/resolve/$rev/$path"
  fi
  [ "$(stat -c %s "$dest")" = "$size" ] || { echo "$path: size $(stat -c %s "$dest"), expected $size" >&2; exit 1; }
done

if [ "${VERIFY:-1}" = 1 ]; then
  echo "checking SHA-256 (a few minutes)"
  pids=()
  for entry in "${files[@]}"; do
    read -r path size sha <<<"$entry"
    ( echo "$sha  $MODELS_DIR/$path" | sha256sum -c --quiet - && echo "ok $path" ) & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || { echo "a checksum failed; delete that file and run this again" >&2; exit 1; }; done
fi
echo "model files ready in $MODELS_DIR"
