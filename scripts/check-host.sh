#!/usr/bin/env bash
# Check that this machine can run the recipe. Read-only; needs no root. Exits 1 if a hard requirement fails.
#   scripts/check-host.sh
set -uo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

fails=0; warns=0
ok()   { printf '  ok    %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; warns=$((warns + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; fails=$((fails + 1)); }

echo "System"
[ "$(uname -s)" = Linux ] && ok "Linux $(uname -r)" || fail "not Linux ($(uname -s))"
[ -r /etc/os-release ] && . /etc/os-release && ok "$PRETTY_NAME"
[ "$(uname -m)" = x86_64 ] && ok "x86_64" || fail "the XeStrata package is built for x86_64, this is $(uname -m)"

echo "GPU"
gpus=0
for d in /sys/bus/pci/devices/*; do
  [ "$(cat "$d/vendor")" = 0x8086 ] || continue
  case $(cat "$d/class") in 0x03*) ;; *) continue ;; esac
  id=$(cat "$d/device"); drv=$(basename "$(readlink -f "$d/driver" 2>/dev/null)" 2>/dev/null)
  # The largest memory BAR shows whether Resizable BAR exposes all of the VRAM
  bar=0
  while read -r start end _; do
    [ "$((start))" -eq 0 ] && continue
    size=$(( (end - start + 1) >> 30 )); [ "$size" -gt "$bar" ] && bar=$size
  done < <(head -n 6 "$d/resource")  # BARs 0 to 5; later lines are SR-IOV and expansion ROM
  name="Intel GPU $id at ${d##*/}"
  [ "$id" = 0xe223 ] && name="Arc Pro B70 ($id) at ${d##*/}"
  if [ "$drv" = xe ]; then
    gpus=$((gpus + 1)); ok "$name, driver xe, largest BAR ${bar} GiB"
    [ "${bar:-0}" -ge 16 ] || warn "$name: BAR ${bar} GiB; enable Resizable BAR (Above 4G decoding) in the firmware"
    # The B70 sits behind its own PCIe switch, so read the link at the CPU's root port, not the GPU function's
    root=$(readlink -f "$d" | tr / '\n' | grep -E '^[0-9a-f]{4}:' | head -n 1)
    speed=$(cat "/sys/bus/pci/devices/$root/current_link_speed" 2>/dev/null)
    width=$(cat "/sys/bus/pci/devices/$root/current_link_width" 2>/dev/null)
    if [ "${speed%%.*}" -ge 16 ] 2>/dev/null && [ "${width:-0}" -ge 16 ]; then ok "PCIe link to the CPU: $speed x$width"
    else warn "PCIe link to the CPU: $speed x$width; the reference runs at 16.0 GT/s x16 (PCIe 4.0), and a slower link cuts prompt speed"; fi
  else
    warn "$name is on driver '${drv:-none}', not xe"
  fi
done
[ "$gpus" -ge 1 ] || fail "no Intel GPU on the xe driver. The B70 needs the in-kernel xe driver (tested on 7.0.0-31-generic)"
ls /dev/dri/renderD* >/dev/null 2>&1 && ok "render nodes: $(ls /dev/dri/renderD* | tr '\n' ' ')" || fail "no /dev/dri/renderD*"

echo "CPU and memory"
model=$(awk -F': ' '/^model name/ {print $2; exit}' /proc/cpuinfo)
cores=$(awk -F': ' '/^physical id/ {p=$2} /^core id/ {print p "-" $2}' /proc/cpuinfo | sort -u | wc -l)
ok "$model, $cores physical cores, $(nproc) threads"
grep -qw avx2 /proc/cpuinfo && ok "AVX2" || fail "no AVX2: XeStrata computes experts on the CPU and needs it"
grep -qw avx512f /proc/cpuinfo && ok "AVX-512 (the reference machine has none)"
mem_gib=$(awk '/^MemTotal:/ {printf "%d", $2/1048576}' /proc/meminfo)
if [ "$mem_gib" -ge 58 ]; then ok "RAM ${mem_gib} GiB"
else fail "RAM ${mem_gib} GiB; the recipe needs a 64 GB machine (about 60 GiB usable) or more"; fi
swap_gib=$(awk '/^SwapTotal:/ {printf "%.1f", $2/1048576}' /proc/meminfo)
ok "swap ${swap_gib} GiB (fine: the image turns recoverable GPU page faults off)"

echo "Disk"
check_space() {  # label, path, GiB needed
  local p=$2; while [ ! -d "$p" ]; do p=$(dirname "$p"); done
  local free; free=$(df -BG --output=avail "$p" | tail -n 1 | tr -dc 0-9)
  [ "$free" -ge "$3" ] && ok "$1: ${free} GiB free at $p (needs $3)" || fail "$1: ${free} GiB free at $p, needs $3"
}
if [ -n "${MODELS_DIR:-}" ]; then
  have=0; [ -d "$MODELS_DIR/IQ3_S" ] && have=$(du -s --block-size=1G "$MODELS_DIR" | cut -f1)
  check_space "MODELS_DIR" "$MODELS_DIR" $(( have >= 80 ? 1 : 85 - have ))
else warn "MODELS_DIR is not set (copy .env.example to .env)"; fi
if [ -n "${STATE_DIR:-}" ]; then check_space "STATE_DIR" "$STATE_DIR" 10; else warn "STATE_DIR is not set"; fi

echo "Docker"
if command -v docker >/dev/null; then
  docker info >/dev/null 2>&1 && ok "docker $(docker version --format '{{.Server.Version}}' 2>/dev/null)" \
    || fail "docker is installed but this user cannot reach the daemon (add the user to the docker group)"
  docker compose version >/dev/null 2>&1 && ok "$(docker compose version --short 2>/dev/null | sed 's/^/compose /')" \
    || fail "no docker compose plugin"
else fail "docker is not installed"; fi

echo
echo "$fails failed, $warns warnings"
[ "$fails" -eq 0 ]
