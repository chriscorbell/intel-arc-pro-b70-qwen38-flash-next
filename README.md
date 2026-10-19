# Qwen3.8-Flash-Next on one Intel Arc Pro B70

A tested, reproducible setup for serving [Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) (125B mixture of experts, about 6B active, 262K context, image input) on a single Intel Arc Pro B70 and a 64 GB desktop. It runs [XeStrata](https://github.com/MistVVK/XeStrata) in Docker Compose: the GPU holds about 11,000 of the model's experts and the CPU computes the rest at the same time. Clients get OpenAI- and Anthropic-compatible APIs with tool calls, thinking, streaming and images.

**To reproduce it with a coding agent,** clone this repository on the machine with the B70 and tell the agent: "Follow AGENTS.md." It checks the hardware, downloads and verifies the model, builds the image, starts the server, runs the tests and reports your numbers next to these.

## What it does on the reference machine

Threadripper 3970X, 64 GB DDR4-3200, Arc Pro B70 on PCIe 4.0 x16, Ubuntu 26.04 (kernel 7.0). One request at a time.

| | |
|---|---|
| Decode, warm 4K code prompt | 89 tok/s with thinking off, 66 tok/s at xhigh |
| Cold prompt | 8.5K tokens in 4.6 s, 34K in 15.7 s, 68K in 30.9 s |
| 250K-token prompt | 116 s cold, 3.4 s for the same prompt again, 0.4 s for a follow-up, 3 of 3 retrieval checks, decode 74 to 83 tok/s |
| Images | 28 of 30 questions on dense 2560x1600 screenshots |
| Load time | 95 s |
| Real 2026 bug fixes through Claude Code | 15 of 16 in 4,021 s (Qwen3.8-27B on the same card: 15 of 16 in 7,310 s) |
| Aider polyglot, Python, offline | 31 of 34 (27B: 27 of 34) |

The first five rows are from 2026-10-19, XeStrata xe0.1.45-1 with this repository's defaults. The image and coding rows were measured on 2026-10-11 with xe0.1.40.2.2 and the earlier settings, which decoded 68 to 80 tok/s and read a 34K prompt in 21.4 s on the same bench. Method, spread between runs and the full numbers: [docs/results.md](docs/results.md).

## Requirements

- Intel Arc Pro B70 on the in-kernel `xe` driver, with Resizable BAR on
- x86_64 CPU with AVX2; core count and memory bandwidth set the decode speed
- 64 GB of RAM (the engine locks about 37 GiB; about 18 GiB stays available after load)
- About 95 GB of disk: 84 GB of model files and 10 GB of engine state
- Docker with the Compose plugin

## Quick start

```bash
cp .env.example .env              # set API_KEY, MODELS_DIR, STATE_DIR
scripts/check-host.sh             # hardware, driver, RAM, disk, Docker
scripts/download-model.sh         # 84 GB at a pinned revision, SHA-256 checked
docker compose build
scripts/setup.sh                  # XeStrata's installer: model pack and MTP draft layer
docker compose up -d              # loads in about two minutes
scripts/smoke_test.py             # expect 26 of 26
scripts/bench.py                  # compare with docs/results.md
```

The API listens on `127.0.0.1:8000` by default. Client setup for Claude Code, Pi and OpenAI-compatible tools: [docs/clients.md](docs/clients.md).

## Files

| Path | What it is |
|---|---|
| [AGENTS.md](AGENTS.md) | Step-by-step instructions for an agent reproducing the setup |
| `compose.yaml`, `.env.example` | The service and its settings |
| `docker/` | The image: XeStrata's release package (pinned, checksum-checked), Intel's GPU runtime, oneMKL, and the entrypoint that writes the engine config |
| `scripts/` | Host check, model download, one-time setup, smoke test, benchmark |
| [docs/settings.md](docs/settings.md) | Every setting, what it does and what it measured |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Known failures with their exact error text |

## Credits and licenses

- [XeStrata](https://github.com/MistVVK/XeStrata) by MistVVK (LGPL-3.0), a SYCL and Level Zero port of [Strata](https://github.com/Niko1221/Strata) (MIT). The image downloads XeStrata's release package; this repository does not redistribute it.
- [GSQ-RCO GGUF quants](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF) by ISTA-DASLab (Apache-2.0).
- [Qwen3.8-Flash-Next](https://huggingface.co/Qwen/Qwen3.8-Flash-Next) by the Qwen team, under its own license.
- This repository's files are MIT licensed.
