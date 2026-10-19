# Troubleshooting

Before you restart anything that failed, save the evidence: `docker logs qwen38-flash-next > failure.log 2>&1` and `sudo dmesg | grep -i xe | tail -50`. The engine's own log is in `$STATE_DIR/home/.local/state/xestrata/xestrata-iq3_s.log`.

## Host check

| Failure | Fix |
|---|---|
| `no Intel GPU on the xe driver` | The B70 needs the in-kernel `xe` driver. The reference runs Ubuntu 26.04's kernel 7.0.0-31-generic, where it binds by default. On an older kernel, `lspci -k` shows which driver claimed the card (or none). Ask the user before changing the kernel. |
| `enable Resizable BAR` | Turn on Above 4G Decoding and Re-Size BAR Support in the firmware. The B70 should show a 32 GiB BAR. |
| `PCIe link to the CPU` warning | The card is in a slower or narrower slot, or the slot runs below its maximum. It works, with slower prompt reading. |
| `no AVX2` | XeStrata's CPU expert path needs AVX2. There is no workaround in this recipe. |
| `RAM ... needs a 64 GB machine` | Below 64 GB is untested. XeStrata has a low-RAM mode (`xestrata --setup --low-ram`), outside this recipe. |
| `docker: unknown command: docker compose` or `no docker compose plugin` | Ubuntu 26.04's Docker comes without Compose: `sudo apt install docker-compose-v2`. |
| `cannot reach the daemon` | `sudo usermod -aG docker $USER`, then log in again. |

## Setup and start

| Symptom | Cause and fix |
|---|---|
| Setup warns `256K with IQ3_S needs ~78 GB of RAM` | Expected. Setup's estimate assumes every expert in RAM; the recipe keeps only the ones the GPU does not hold. |
| Setup says no API key is set | Expected. Setup's config is replaced at every container start by the entrypoint, which writes `API_KEY` from `.env`. The smoke test's `rejects a wrong key` check confirms it. |
| `recipe: missing /models/IQ3_S/...` | `MODELS_DIR` does not point at the folder `scripts/download-model.sh` filled, or the download did not finish. |
| `recipe: no MTP draft layer` | `scripts/setup.sh` has not run against this `STATE_DIR`. |
| `recipe: swap is on and GPU page faults are recoverable` | The page-fault keys were removed from the environment. Restore `NEOReadDebugKeys=1 EnableRecoverablePageFaults=0` (the image sets them). |
| `docker compose stop` takes 60 s and the container exits 137 | `init: true` is missing from `compose.yaml`. |
| First start after a reboot is slower than 95 s | The model files are not in the page cache yet. Allow a few minutes on slower disks. |
| Cold prompts take about twice as long as in [results.md](results.md), and the `engine started` line in the engine's log has `--prefill 2048` | XeStrata's launcher misread its own version and rewrote `--prefill auto` (see [settings.md](settings.md)). The Dockerfile patches this for the pinned release; if you changed the release, check that the patch step still applies. |

## While serving

| Symptom | Cause and fix |
|---|---|
| `refilling a lent slot failed: ... UR_RESULT_ERROR_OUT_OF_DEVICE_MEMORY`, often after a long cold prompt, sometimes with `xe ... VM worker error: -16` in `dmesg` | The VRAM reserve is too small. A long prompt borrows thousands of expert slots and refills them afterwards. Keep `VRAM_RESERVE_MIB` at 2048 or raise it; 700 failed on the reference machine. The server marks the engine unloaded and reloads it on the next request. |
| `Fault response: Unsuccessful -EINVAL` or `Engine memory CAT error` in `dmesg`, then `UR_RESULT_ERROR_OUT_OF_RESOURCES` and new GPU processes hanging | The `xe` driver moved the engine's host buffers to swap and the GPU faulted on them. This happens in the compute runtime's default page-fault mode; check that the container has `EnableRecoverablePageFaults=0` (`docker exec qwen38-flash-next env`). Removing the faulted container triggers a GPU reset that clears the hang. |
| A 400 near the end of a long conversation | The client asked for more output tokens than the window has left and the server rejected it. `fit_max_tokens` (set by the entrypoint) clamps instead; for Claude Code also set `CLAUDE_CODE_MAX_CONTEXT_TOKENS=229376`. See [clients.md](clients.md). |
| Claude Code gets a 401 after minutes of retries | It inherited session variables that override the token. See [clients.md](clients.md). |
| The first question about a new image takes 5 to 6 s | The CPU image encoder. Repeat questions about the same image take about 2 s. `VISION_GPU=1` is faster at larger image budgets; see [settings.md](settings.md). |
| A second client waits | One request at a time, by design. See [settings.md](settings.md). |
| Decode much slower than [results.md](results.md) | Check `docker logs` for the expert count (`filling the GPU's expert cache (N experts ...)`; about 10,980 on the reference), that nothing else uses the GPU, and the CPU's load. Fewer or slower cores lower decode, because the CPU computes the experts not in VRAM. |

## Monitoring the GPU

`intel_gpu_top` does not work with the `xe` driver (it looks for i915's counters). `sudo gputop` shows per-process engine use and GPU memory. `btop` shows no GPU panel for this card.
