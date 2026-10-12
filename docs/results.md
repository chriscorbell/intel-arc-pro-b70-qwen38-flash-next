# Results on the reference machine

## The machine

| | |
|---|---|
| GPU | Intel Arc Pro B70, 32 GB (31.9 GiB usable), Resizable BAR 32 GB, PCIe 4.0 x16 to the CPU |
| CPU | AMD Ryzen Threadripper 3970X, 32 cores (Zen 2, AVX2, no AVX-512) |
| RAM | 64 GB, four 16 GB DDR4-3200 UDIMMs (60 GiB usable), 8 GiB swap on |
| Motherboard | MSI TRX40 PRO WIFI |
| Storage | WD_BLACK SN7100 2 TB NVMe |
| OS | Ubuntu Server 26.04.1, kernel 7.0.0-31-generic, in-kernel `xe` driver |
| Docker | 29.1.3, Compose 2.40.3 |
| In the image | XeStrata xe0.1.40.2.2, Level Zero and OpenCL runtime 26.05.37020.3, oneMKL 2026.1 |

Every number below is at concurrency 1.

## This repository's checks, from a clean setup

Run on 2026-10-12 exactly as [AGENTS.md](../AGENTS.md) describes, with a fresh `STATE_DIR` and the image built from scratch: `scripts/setup.sh` took 4.5 minutes (most of it the MTP layer download), the model loaded 56 s after `docker compose up -d` with 10,942 experts in VRAM, and about 29 GiB of RAM was still available.

`scripts/smoke_test.py`: 26 of 26.

`scripts/bench.py`, two runs (the second against an identical deployment of the same configuration):

| | Run 1 | Run 2 |
|---|---:|---:|
| Warm 4K code, thinking off, decode tok/s (median of 3) | 79.5 | 68.3 |
| Warm 4K code, xhigh, decode tok/s (median of 3) | 58.0 | 60.1 |
| Cold 8,534-token prompt, time to first token | 5.45 s | 5.64 s |
| Cold 33,852-token prompt | 21.51 s | 21.30 s |
| Cold 67,703-token prompt | 32.25 s | 32.13 s |

Single decode runs ranged from 66.2 to 81.2 tok/s with thinking off and 53.4 to 61.5 at xhigh. Decode speed depends on how predictable the output is, and with sampling on that varies run to run; a median within about 10% of these is the same result.

## The same configuration, measured with other prompts

An earlier harness with different prompt text measured warm 4K decode at 72.9 to 76.6 tok/s thinking off and 57.2 to 60.3 at xhigh, and cold 8K, 32K and 64K prompts in 4.9, 15.3 and 29.1 s. Prompt speed depends on the text, so compare your results with the table above, which uses this repository's `bench.py`.

## Long context

A 249,987-token prompt with a fact to retrieve, thinking at xhigh: 3 of 3 retrieval and continuation checks. Cold time to first token 116.4 s (2,158 tok/s); the same prompt again, cached, 0.52 s; a continuation 0.84 s. Decode at 250K was 70 to 85 tok/s, with 94% of MTP drafts accepted. This ran with all experts in RAM (`RESIDENT_EXPERTS=0`) and no conversation cache, with the same number of experts in VRAM as the default.

## Images

On six 2560x1600 console screenshots with 10 to 12 px text, five questions each (tables, logs, status bars, checkboxes, click targets), thinking off: 28 of 30 at the default 1,024 image tokens, with every click target right. Both misses were one character of 10 px text. The first question about a new screenshot took 5.4 to 5.8 s; later questions about it 1.9 s.

## Coding quality

Both evaluations ran through headless Claude Code at effort xhigh, one task at a time, with both models sampling as their model cards say. The comparison model is Qwen3.8-27B (EXL3 4.00 bpw, MTP) on the same B70 through a vLLM-based engine, which decodes faster at short context (about 90 tok/s) but wrote more tokens on these tasks.

- **Sixteen real bug fixes** merged in 2026 into click, werkzeug, marshmallow and Python-Markdown, each checked to fail before the fix and pass after it. Flash-Next passed 15 of 16 with no regressions in 4,021 s; the 27B passed 15 of 16 in 7,310 s. Both failed the same task. In blind pairwise reviews of the patches (each pair judged in both orders), two judge models (Claude Opus 5.5 and Claude Fable 5.1) each preferred Flash-Next's patches 15 to 1, mostly for their tests and changelog entries; on the library source alone it was 6 to 4 with 6 ties.
- **Aider's polyglot benchmark, Python** (34 exercises, two attempts each, 900 s per attempt), with the agent cut off from the internet and from the benchmark's files: Flash-Next 31 of 34 (21 on the first attempt) in 3.67 hours; the 27B 27 of 34 (11) in 6.30 hours. Runs of one configuration on this set have moved by three passes, so read the totals as close; the first-attempt and time differences are larger than that.

One run each. Stability over weeks of daily use is not measured yet; about seven hours of benchmark and agent runs and a 3.7-hour evaluation ran without an engine error or a new `xe` kernel message.

## On other hardware

XeStrata computes the experts that are not in VRAM on the CPU, so the CPU and RAM change the result. For scale, XeStrata's own measurements on a B70 with an Intel Core i7-14700 and 96 GB of RAM (2026-10-04) list IQ3_S at 73.9 tok/s decode at 4K and 1,718 tok/s prompt reading at 32K. A slower PCIe link lowers prompt speed, and fewer or slower cores lower decode. Less than 64 GB of RAM is untested.
