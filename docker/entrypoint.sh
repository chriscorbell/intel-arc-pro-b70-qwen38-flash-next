#!/usr/bin/env bash
# Start XeStrata's server for Qwen3.8-Flash-Next: write the model config from the environment, then run `xestrata`.
#
# Mounts: /models holds ISTA-DASLab's GSQ-RCO IQ3_S GGUF shards in IQ3_S/ and the BF16 vision projector (read-only).
# /x is XeStrata's state (HOME=/x/home): the pack, the MTP draft layer, logs and the config this script writes.
# scripts/setup.sh fills it once.
#
# Settings, all optional except API_KEY. The defaults are the measured configuration (docs/settings.md):
#   API_KEY                  the key clients must send (required)
#   SERVED_NAME              the model name /v1/models reports (default qwen38; clients may send any name)
#   MAX_CONTEXT              context window in tokens (default 262144, the model's trained length)
#   SAMPLING                 JSON sampling defaults for requests that set none; default the model card's thinking-mode
#                            values. "{}" means greedy. Claude Code sends no sampling fields, so this decides for it.
#   VRAM_RESERVE_MIB         VRAM left free for the engine's working buffers (default 2048; 700 ran out of VRAM)
#   RESIDENT_EXPERTS         1 (default): keep only the experts the GPU does not hold in RAM; 0: keep all of them in
#                            RAM, which is faster but leaves no room for the conversation cache on a 64 GB host
#   CONVERSATION_CACHE_MIB   RAM for parked conversations (default 8192); CONVERSATION_CACHE_SLOTS (default 4)
#   PCIE_FRAC, SPEC_MIN_P    from `xestrata --calibrate` on the reference machine (defaults 0.75 and 0.70)
#   VISION_MAX_TOKENS        image tokens per picture (default 1024)
#   VISION_THREADS           CPU image encoder threads (default the number of physical cores)
#   VISION_GPU               1: the image encoder on the GPU through Vulkan (700 MiB more VRAM reserve, so fewer
#                            expert slots); default the CPU encoder. GPU_PCI picks the GPU (default the one on xe).
#   ENGINE_ARGS              extra engine arguments, appended
set -euo pipefail

swap_kb=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
if [ "${EnableRecoverablePageFaults:-}" != 0 ] && [ "${ALLOW_SWAP:-0}" != 1 ] && [ "${swap_kb:-0}" -gt 0 ]; then
  echo "recipe: swap is on and GPU page faults are recoverable, so xe may move the engine's buffers to swap." >&2
  echo "recipe: keep NEOReadDebugKeys=1 EnableRecoverablePageFaults=0 (the image sets them) or run 'sudo swapoff -a'." >&2
  sleep 30; exit 1
fi
: "${API_KEY:?API_KEY is required}"

share=$HOME/.local/share/xestrata
models=/models/IQ3_S; tag=iq3_s
shard1=$models/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00001-of-00002.gguf
ple=$models/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_S-00002-of-00002.gguf
mmproj=/models/mmproj-Qwen3.8-Flash-Next-BF16.gguf
for f in "$shard1" "$ple" "$mmproj"; do
  [ -f "$f" ] || { echo "recipe: missing $f; run scripts/download-model.sh and check MODELS_DIR" >&2; exit 1; }
done
[ -f "$share/packs/$tag/index.txt" ] || python3 /usr/share/xestrata/tools/iq_pack.py --gguf "$shard1" --out "$share/packs/$tag"
[ -d "$share/mtp/rt" ] || { echo "recipe: no MTP draft layer in $share/mtp; run scripts/setup.sh once" >&2; exit 1; }

export TAG=$tag SHARD1=$shard1 PLE=$ple MMPROJ=$mmproj SHARE=$share
python3 - <<'PY'
import glob, json, os, shlex

e = os.environ
share, tag = e["SHARE"], e["TAG"]
vision_gpu = e.get("VISION_GPU") == "1"


def physical_cores():
    cores, phys = set(), None
    with open("/proc/cpuinfo") as f:
        for line in f:
            k, _, v = line.partition(":")
            k = k.strip()
            if k == "physical id":
                phys = v.strip()
            elif k == "core id":
                cores.add((phys, v.strip()))
    return len(cores) or os.cpu_count() or 1


def xe_gpu():
    found = [os.path.basename(d) for d in glob.glob("/sys/bus/pci/devices/*")
             if os.path.basename(os.path.realpath(os.path.join(d, "driver"))) == "xe"]
    if len(found) != 1:
        raise SystemExit(f"recipe: {len(found)} GPUs on the xe driver ({found}); set GPU_PCI")
    return found[0]


reserve = int(e.get("VRAM_RESERVE_MIB", "2048")) + (700 if vision_gpu else 0)
args = ["--pack", f"{share}/packs/{tag}", "--native", e["SHARD1"], "--ple-gguf", e["PLE"],
        "--expert-profile", "/usr/share/xestrata/data/expert-profile.bin", "--expert-cache", "auto", "--prefill", "auto",
        "--spec", "4", "--mtp", f"{share}/mtp/rt", "--max-context", e.get("MAX_CONTEXT", "262144"), "--kv", "int8",
        "--vision", "--vram-reserve-mib", str(reserve),
        "--pcie-frac", e.get("PCIE_FRAC", "0.75"), "--spec-min-p", e.get("SPEC_MIN_P", "0.70")]
if e.get("RESIDENT_EXPERTS", "1") == "1":
    args.append("--resident-experts")
if int(e.get("CONVERSATION_CACHE_MIB", "8192")) > 0:
    args += ["--conversation-cache-mib", e.get("CONVERSATION_CACHE_MIB", "8192"),
             "--conversation-cache-slots", e.get("CONVERSATION_CACHE_SLOTS", "4")]
args += shlex.split(e.get("ENGINE_ARGS", ""))

engine = "/usr/lib/x86_64-linux-gnu/xestrata/engine"
state = os.path.join(e["HOME"], ".local/state/xestrata")
cpu_vision = {"mmproj": e["MMPROJ"], "model": e["SHARD1"], "exe": f"{engine}/strata-vision-cpu", "gpu": False,
              "max_tokens": int(e.get("VISION_MAX_TOKENS", "1024")),
              "threads": int(e.get("VISION_THREADS") or physical_cores())}
cfg = {"exe": f"{engine}/strata", "args": args, "cwd": state, "tokenizer": f"{share}/packs/{tag}/tokenizer",
       "model_name": e.get("SERVED_NAME") or "qwen38", "log": f"{state}/xestrata-{tag}.log",
       "lib_dirs": [f"{engine}/lib", "/opt/intel/oneapi/mkl/2026.1/lib"], "port": 8000, "host": "0.0.0.0",
       "open_browser": False, "api_key": e["API_KEY"],
       # Claude Code asks for 32,000 output tokens on every request; near the end of the window that is a 400
       # unless the server clamps the cap to what is left
       "fit_max_tokens": True,
       "sampling": json.loads(e.get("SAMPLING") or '{"temperature": 1.0, "top_p": 0.95, "top_k": 20}'),
       "vision": cpu_vision}
if vision_gpu:  # as XeStrata's setup writes it for --vision gpu: the Vulkan encoder, the CPU one as its fallback
    cfg["vision"] = {"mmproj": e["MMPROJ"], "model": e["SHARD1"], "exe": f"{engine}/strata-vision-vulkan", "gpu": True,
                     "gpu_pci": e.get("GPU_PCI") or xe_gpu(), "max_tokens": cpu_vision["max_tokens"],
                     "onednn": False, "fallback": cpu_vision}

conf = os.path.join(e["HOME"], ".config/xestrata")
os.makedirs(conf, exist_ok=True)
os.makedirs(state, exist_ok=True)
path = f"{conf}/xestrata-{tag}.json"
with open(path, "w") as f:
    json.dump(cfg, f, indent=1)
os.chmod(path, 0o600)
os.utime(path)  # `xestrata` starts the most recently used model config
print("recipe: engine args:", " ".join(args), "| sampling:", cfg["sampling"],
      "| vision:", "gpu" if vision_gpu else f"cpu, {cpu_vision['threads']} threads", flush=True)
PY
exec xestrata
