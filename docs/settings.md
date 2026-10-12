# Settings and why they have these values

Every setting lives in `.env` (template: `.env.example`) and reaches the engine through `docker/entrypoint.sh`, which writes XeStrata's config at each start. The defaults are the configuration measured on the reference machine (Threadripper 3970X, 64 GB DDR4-3200, Arc Pro B70 on PCIe 4.0 x16). All speeds are at concurrency 1.

## How the engine uses the hardware

Qwen3.8-Flash-Next is a 125B mixture-of-experts model with about 6B parameters active per token. The IQ3_S GGUF holds 50.3 GB of routed experts at 3.33 bits per weight on average, 4.5 GB of everything else at 7.30, and a 28.8 GB n-gram embedding table that is read a few rows per token from disk.

XeStrata fills most of the B70's 32 GB with experts (about 10,940 of them, 20.8 GiB) and computes the experts that are not in VRAM on the CPU, at the same time as the GPU works. Upstream Strata's SYCL port instead has the GPU read those experts over PCIe; with the same files, XeStrata decodes 1.3 to 1.9 times as fast on the reference machine. That is why CPU cores, AVX2 and memory bandwidth matter here as much as the GPU.

## The settings

| Setting | Default | What it does, and the evidence |
|---|---|---|
| `MAX_CONTEXT` | 262144 | The model's trained window. A cold 250K prompt took 116 s and passed 3 of 3 retrieval checks. The KV cache is int8 and stays in VRAM: streaming it from RAM bought 14% more expert slots and cost about 55% of prompt speed. |
| `VRAM_RESERVE_MIB` | 2048 | VRAM kept free for working buffers. XeStrata's setup picks 700, which ran out of VRAM on the second cold 32K prompt: a long prompt borrows about 6,900 expert slots (13 GiB) and refills them afterwards, and the refill failed. 2,048 ran every test after that without an engine error. |
| `RESIDENT_EXPERTS` | 1 | Keeps in RAM only the experts the GPU does not hold (about 31 GiB used after load, 25 to 29 GiB left). With 0, all 46.8 GiB of experts are locked in RAM: warm decode was 85.9 instead of 78.2 tok/s, but only 7 to 8 GiB of RAM stayed free on a 64 GB machine, too little for the conversation cache. With 96 GB or more, 0 is worth measuring. |
| `CONVERSATION_CACHE_MIB`, `CONVERSATION_CACHE_SLOTS` | 8192, 4 | Parks up to four conversations' state in RAM. The server answers one request at a time, so an agent that alternates between its main thread and a subagent would otherwise re-read the whole prompt at every switch: with two 25,880-token conversations, a follow-up after a switch took 12.0 s without the cache and 0.84 to 0.88 s with it. Set the size to 0 to turn it off. |
| `PCIE_FRAC`, `SPEC_MIN_P` | 0.75, 0.70 | What `xestrata --calibrate` chose on the reference machine (it measured 68.3 to 71.3 tok/s across its candidates). On a different CPU, run `scripts/setup.sh --calibrate` with the server stopped and try what it picks. |
| `SAMPLING` | `{"temperature": 1.0, "top_p": 0.95, "top_k": 20}` | Used for requests that set no sampling fields; these are the model card's thinking-mode values. Claude Code sends none, so this decides how it samples. `{}` means greedy. A request's own fields always win. |
| `VISION_MAX_TOKENS` | 1024 | Image tokens per picture. On six 2560x1600 console screenshots with 10 to 12 px text, five questions each: 28/30 correct at 1,024, 29/30 at 2,048, 30/30 at 4,096. Every miss was one or two characters of 10 px text. The first question about a new screenshot took 5.4 to 5.8 s, 12.4 to 14.3 s and 32.6 to 35.7 s respectively. |
| `VISION_THREADS` | physical cores | Threads for the CPU image encoder (32 on the reference machine). |
| `VISION_GPU` | 0 | 1 runs the image encoder on the GPU through Vulkan. It needs 700 MiB more VRAM, so about 1,000 fewer expert slots; at 2,048 image tokens it encoded a new screenshot in 7.4 to 9.9 s instead of 12.4 to 14.3 s. At the default 1,024 tokens the CPU encoder is fast enough. `GPU_PCI` picks the GPU if more than one is on `xe`. |
| `ENGINE_ARGS` | empty | Extra engine arguments, appended to the generated list. `docker logs` prints the full list at start (`recipe: engine args:`). |

Fixed in `docker/entrypoint.sh`: MTP speculative decoding with 4 draft tokens from the original checkpoint's MTP layer (it accepted 423 of 449 drafts on a 250K continuation), `--expert-cache auto --prefill auto`, and `fit_max_tokens`, which clamps a request's output cap to the room left in the window. Claude Code asks for 32,000 output tokens on every request; near the end of the window that would otherwise be a 400.

## Fixed in the Compose file and the image

- **Recoverable GPU page faults off** (`NEOReadDebugKeys=1 EnableRecoverablePageFaults=0` in the image). The engine keeps tens of GB of experts in Level Zero host memory and polls host-mapped memory. In the compute runtime's default mode, the `xe` driver backs such buffers up to swap under memory pressure, and the next GPU access faults and kills the engine. With these keys, under the same pressure (171 GB read through the page cache and 12 GiB allocated), nothing went to swap, and decode speed was unchanged. So swap can stay on. If the keys are removed, the entrypoint refuses to start while the host has swap.
- **`init: true`**. XeStrata's launcher ignores SIGTERM as PID 1, so without an init every stop waited the full 60 s grace period and ended in a SIGKILL. With Docker's init a stop takes about 2.5 s.
- **`memlock: -1`** so the experts in RAM can be locked, and **`shm_size: 8gb`** because the image encoder hands pictures to the engine through `/dev/shm`.
- **One request at a time.** XeStrata's `--parallel N` exists and its documentation puts the cost at 10 to 25% per request; it was not measured here.
