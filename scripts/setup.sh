#!/usr/bin/env bash
# One-time XeStrata setup, in the recipe's image: checks the GPU, packs the model for the engine (1.5 GB) and fetches
# the MTP draft layer from the original Qwen checkpoint (about 5 GB download, 6.5 GB on disk) into STATE_DIR.
# Run after scripts/download-model.sh. The GPU may be busy; this does not start the model.
#   scripts/setup.sh
#   scripts/setup.sh --calibrate     also runs XeStrata's calibration (about 25 minutes) and prints the settings it
#                                    chooses: --pcie-frac, --spec-min-p, --pool-workers (needs the GPU free; set
#                                    PCIE_FRAC, SPEC_MIN_P and POOL_WORKERS in .env to use them)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
: "${MODELS_DIR:?set MODELS_DIR in .env}" "${STATE_DIR:?set STATE_DIR in .env}"
image=${IMAGE:-local/xestrata-qwen38:xe0.1.45-1}

docker image inspect "$image" >/dev/null 2>&1 || docker compose build
mkdir -p "$STATE_DIR/home"
run=(docker run --rm --device /dev/dri -v /dev/dri/by-path:/dev/dri/by-path:ro --ulimit memlock=-1:-1 --shm-size 8g
     -e HOME=/x/home -v "$STATE_DIR:/x" -v "$MODELS_DIR:/models:ro" --entrypoint xestrata "$image")

# --context 262144 with --yes is the consent to setup's RAM warning: it estimates 78 GB for its own defaults, which
# keep every expert in RAM. The recipe keeps only the experts the GPU does not hold (RESIDENT_EXPERTS=1).
"${run[@]}" --setup --yes --no-start --no-browser --no-warmup --model IQ3_S --models-dir /models \
  --gguf-dir /models/IQ3_S --context 262144 --vision cpu --vision-tokens 1024 --host 0.0.0.0 --port 8000

if [ "${1:-}" = --calibrate ]; then
  "${run[@]}" --calibrate
fi

share=$STATE_DIR/home/.local/share/xestrata
if [ -d "$share/mtp/rt" ] && [ -f "$share/packs/iq3_s/index.txt" ]; then
  echo "setup done: pack and MTP layer in $share"
else
  echo "setup finished, but $share/mtp/rt or $share/packs/iq3_s is missing; read the output above" >&2
  exit 1
fi
