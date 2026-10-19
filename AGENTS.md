# Agent instructions: reproduce this recipe

Your job is to get Qwen3.8-Flash-Next serving on the user's machine the way it runs on the reference machine: one Intel Arc Pro B70, 64 GB of RAM, XeStrata in Docker, an OpenAI- and Anthropic-compatible API with a key. You are done when the smoke test passes 26 of 26 on their machine and you have reported their numbers next to the reference numbers.

Every command runs from the root of this repository, on the machine with the B70. The scripts read `.env`.

## Ground rules

- Ask the user before you install or change a kernel or GPU driver, change firmware settings, reboot, or publish the API on an address other machines can reach. Everything else in the steps below is safe to do without asking.
- Keep the pins: the base image digest, the XeStrata release and its SHA-256 in `docker/Dockerfile`, and the model revision and checksums in `scripts/download-model.sh`. The reference numbers hold only for these versions.
- Reproduce first, tune second. Start with the defaults in `.env.example`. When you change a setting afterwards, change one at a time and rerun `scripts/bench.py`, so each number has one cause.
- Before restarting a container that failed, save what explains the failure: `docker logs qwen38-flash-next > failure.log 2>&1` and `sudo dmesg | grep -i xe | tail -50`. That state is gone after a restart.

## Steps

### 1. Check the host

Run `scripts/check-host.sh`. Done when it prints `0 failed`.

It checks for Linux on x86_64, a B70 on the in-kernel `xe` driver with Resizable BAR on, AVX2, at least 58 GiB of RAM, disk space, and Docker with the Compose plugin. For a failure, [docs/troubleshooting.md](docs/troubleshooting.md) has a fix under "Host check". A warning is not a blocker; mention it in your report.

### 2. Configure

Copy `.env.example` to `.env`. Set `API_KEY` (generate one with `openssl rand -hex 24`), `MODELS_DIR` and `STATE_DIR` on a disk with room (about 85 GB and 10 GB). Keep `BIND_ADDR=127.0.0.1` unless the user wants other machines to reach the API; then ask which private address to use. Done when `scripts/check-host.sh` shows both directories with enough free space.

### 3. Download the model

Run `scripts/download-model.sh`. It fetches about 84 GB from Hugging Face at a pinned revision, resumes after an interruption, and checks every file's SHA-256. Done when it prints `model files ready`. Expect this to take a while; it is safe to rerun.

### 4. Build and set up

Run `docker compose build`, then `scripts/setup.sh`. Setup runs XeStrata's own installer inside the image: it packs the model for the engine and downloads the MTP draft layer (about 5 GB). Done when it prints `setup done`. Its warning that 256K context needs about 78 GB of RAM, and its note that no API key is set, are expected: the recipe keeps fewer experts in RAM than setup assumes, and the container writes the key from `.env` at every start.

### 5. Start

Run `docker compose up -d`, then wait for the model to load:

```bash
set -a; . ./.env; set +a
until curl -fsS "http://$BIND_ADDR:$PORT/health" | grep -q '"loaded": true'; do sleep 5; done
```

The reference machine loads in 95 s; allow up to 10 minutes on a first start. Done when `/health` reports `"loaded": true`. If the container exits or keeps restarting, go to [docs/troubleshooting.md](docs/troubleshooting.md).

### 6. Verify

Run `scripts/smoke_test.py --out results/smoke.json`. Done when it prints `26 of 26 checks passed`: health, key enforcement, 18 short answers including a tool call, streaming, thinking, Anthropic Messages tool use, and two image questions.

Then run `scripts/bench.py --out results/bench.json` (about two minutes) and compare its output with the reference rows in [docs/results.md](docs/results.md). A different CPU or RAM speed moves these numbers, because XeStrata computes the experts that do not fit in VRAM on the CPU; that section of the results says what to expect.

### 7. Report

Tell the user, in a short table: their hardware (GPU, CPU, RAM, kernel), the smoke test result, their bench numbers beside the reference numbers, the API address, and where the key is (`.env`). Include any host-check warning and anything you changed from the defaults, with the reason.

## When the user wants more

- Connecting a client (Claude Code, Pi, any OpenAI-compatible tool), thinking levels, or the context window: [docs/clients.md](docs/clients.md).
- Changing a setting, a different amount of RAM, or tuning for a different CPU: [docs/settings.md](docs/settings.md) says what each setting does and what it measured on the reference machine.
- Any error, crash, slow start or wrong output: [docs/troubleshooting.md](docs/troubleshooting.md), with the exact error text to search for.
