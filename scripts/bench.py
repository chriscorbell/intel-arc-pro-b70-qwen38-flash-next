#!/usr/bin/env python3
"""Measure the numbers the recipe reports, at concurrency 1, so you can compare your machine with the reference one.

  Warm decode: a 4K-token code prompt, then a request to write a Python module (384 output tokens), thinking off and
               at effort xhigh. One warm-up request, then --reps measured ones with the prompt cached.
  Cold prompt: a summary request over a new prompt of each --cold size (32 output tokens). Time to first token is
               almost all prompt reading, so prefill speed is prompt tokens over that time.

  scripts/bench.py [--reps 3] [--cold 8192 32768 65536] [--out results/bench.json]

Decode speed is (output tokens - 1) / (total time - time to first token), from the server's own token count.
Standard library only; the URL, key and model default to .env.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe_client import defaults, stream_chat  # noqa: E402

CODE_TASK = """Write a complete Python 3 module implementing these utilities:
1. chunked(iterable, size): yield lists of at most size elements; reject size <= 0.
2. unique_by(items, key): preserve the first item for each hashable key.
3. merge_intervals(intervals): sort and merge overlapping or touching closed intervals.
4. flatten(value): recursively yield leaves from nested lists and tuples, preserving strings.
5. deep_merge(left, right): recursively merge dictionaries without mutating either input.
6. retry(fn, attempts, retry_on): call fn until it succeeds; re-raise the final exception.
Use only the standard library, type hints and short docstrings. Include examples in a
main block. The reference material above is unrelated context; do not copy it.
Return the implementation now, without discussing the reference material."""
SUMMARY_TASK = "Summarise what the text above is for, in one plain paragraph."


def corpus(n_tokens: int, seed: int) -> str:
    """Deterministic Python-like source of roughly n_tokens tokens (about 3.6 characters per token)."""
    rng = random.Random(seed)
    words = ("account cache config event file handler index item job key list map node order parser queue record "
             "request result route session state stream task token user value worker buffer client limit").split()
    out, size = [], 0
    while size < n_tokens * 3.6:
        a, b, c = rng.sample(words, 3)
        block = (f"def {a}_{b}_{rng.randrange(1000)}({c}, limit={rng.randrange(1, 64)}):\n"
                 f"    \"\"\"Return the {b} for each {c} in the {a} up to limit.\"\"\"\n"
                 f"    out = []\n    for i, {a} in enumerate({c}):\n        if i >= limit:\n            break\n"
                 f"        out.append(({a}, i * {rng.randrange(2, 9)}))\n    return out\n\n")
        out.append(block)
        size += len(block)
    return "".join(out)


def body(model: str, prompt: str, task: str, max_tokens: int, effort: str | None, seed: int) -> dict:
    b = {"model": model, "messages": [{"role": "user", "content": prompt + "\n\n" + task}], "max_tokens": max_tokens,
         "seed": seed, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0, "repetition_penalty": 1.0}
    if effort:
        b |= {"temperature": 1.0, "top_p": 0.95, "reasoning_effort": effort,
              "chat_template_kwargs": {"enable_thinking": True}}
    else:
        b |= {"temperature": 0.7, "top_p": 0.8, "reasoning_effort": "none",
              "chat_template_kwargs": {"enable_thinking": False}}
    return b


def decode_rate(r: dict) -> float:
    n = r["usage"]["completion_tokens"]
    return (n - 1) / (r["total"] - r["ttft"])


def main() -> int:
    base, key, model = defaults()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=base)
    ap.add_argument("--key", default=key)
    ap.add_argument("--model", default=model)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--cold", type=int, nargs="*", default=[8192, 32768, 65536])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if not a.key:
        raise SystemExit("no API key: set API_KEY in .env or pass --key")
    results: dict = {"base_url": a.base_url, "model": a.model, "concurrency": 1, "warm": [], "cold": []}

    prompt = f"# benchmark {uuid.uuid4().hex}\n" + corpus(4096, 1)
    for label, effort in (("thinking off", None), ("xhigh", "xhigh")):
        stream_chat(a.base_url, a.key, body(a.model, prompt, CODE_TASK, 384, effort, 41999))  # warm-up
        runs = [stream_chat(a.base_url, a.key, body(a.model, prompt, CODE_TASK, 384, effort, 42000 + i))
                for i in range(a.reps)]
        rates = [decode_rate(r) for r in runs]
        row = {"workload": f"warm 4K code, {label}", "prompt_tokens": runs[0]["usage"].get("prompt_tokens"),
               "output_tokens": [r["usage"]["completion_tokens"] for r in runs],
               "ttft_s": [round(r["ttft"], 3) for r in runs], "decode_tok_s": [round(x, 1) for x in rates],
               "decode_tok_s_median": round(statistics.median(rates), 1)}
        results["warm"].append(row)
        print(f"{row['workload']:<26} prompt {row['prompt_tokens']:>6}  decode median {row['decode_tok_s_median']:5.1f} "
              f"tok/s  runs {row['decode_tok_s']}", flush=True)

    for size in a.cold:
        prompt = f"# benchmark {uuid.uuid4().hex}\n" + corpus(size - 64, size)
        r = stream_chat(a.base_url, a.key, body(a.model, prompt, SUMMARY_TASK, 32, None, 42000))
        n = r["usage"].get("prompt_tokens") or 0
        cached = (r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens")
        row = {"workload": f"cold {size}", "prompt_tokens": n, "cached_tokens": cached,
               "ttft_s": round(r["ttft"], 3), "prefill_tok_s": round(n / r["ttft"])}
        results["cold"].append(row)
        print(f"{row['workload']:<26} prompt {n:>6}  time to first token {r['ttft']:7.2f} s  "
              f"prefill {row['prefill_tok_s']:>5} tok/s  cached {cached}", flush=True)

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
