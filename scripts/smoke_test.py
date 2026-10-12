#!/usr/bin/env python3
"""Check that the running server works the way the recipe says: health, the API key, 18 short answers with a tool
call, streaming, thinking, the Anthropic Messages API and image input. Concurrency 1. Standard library only.

  scripts/smoke_test.py [--base-url URL] [--key KEY] [--model NAME] [--out results/smoke.json]

The URL, key and model default to BIND_ADDR, PORT, API_KEY and SERVED_NAME from .env. Exits 1 if any check fails.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import struct
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe_client import defaults, request, stream_chat  # noqa: E402

WRITE_TOOL = {"type": "function", "function": {
    "name": "write", "description": "Write a UTF-8 file.", "parameters": {
        "type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"]}}}
SHORT = [
    ("addition", "What is 17 + 25? Return only the integer.", "42"),
    ("multiplication", "What is 9 * 9? Return only the integer.", "81"),
    ("python", "Evaluate Python sum([4, 6, 8]). Return only the integer.", "18"),
    ("lowercase", "Convert HELLO to lowercase. Return only that word.", "hello"),
    ("json", 'Return exactly this JSON object: {"ok":true,"count":3}', {"ok": True, "count": 3}),
    ("tool", "Use write to save exactly hello to greeting.txt.", {"path": "greeting.txt", "content": "hello"}),
]
FONT = {  # 5x7 digits
    "0": "01110 10001 10011 10101 11001 10001 01110", "1": "00100 01100 00100 00100 00100 00100 01110",
    "2": "01110 10001 00001 00010 00100 01000 11111", "3": "11111 00010 00100 00010 00001 10001 01110",
    "4": "00010 00110 01010 10010 11111 00010 00010", "5": "11111 10000 11110 00001 00001 10001 01110",
    "6": "00110 01000 10000 11110 10001 10001 01110", "7": "11111 00001 00010 00100 01000 01000 01000",
    "8": "01110 10001 10001 01110 10001 10001 01110", "9": "01110 10001 10001 01111 00001 00010 01100",
}


def png(width: int, height: int, pixel) -> bytes:
    rows = b"".join(b"\x00" + bytes(c for x in range(width) for c in pixel(x, y)) for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def shapes_png() -> bytes:
    """Three red circles and five blue squares on white."""
    def pixel(x, y):
        for i in range(3):
            if (x - (90 + i * 140)) ** 2 + (y - 120) ** 2 <= 50 ** 2:
                return (210, 34, 34)
        for i in range(5):
            if 40 + i * 140 <= x < 140 + i * 140 and 220 <= y < 320:
                return (34, 34, 210)
        return (255, 255, 255)
    return png(760, 360, pixel)


def digits_png(text: str, scale: int = 14) -> bytes:
    rows = [FONT[d].split() for d in text]
    width, height = (len(text) * 6 + 3) * scale, 11 * scale

    def pixel(x, y):
        cx, cy = x // scale - 2, y // scale - 2
        if 0 <= cy < 7 and cx >= 0 and cx % 6 < 5 and cx // 6 < len(text) and rows[cx // 6][cy][cx % 6] == "1":
            return (20, 20, 20)
        return (255, 255, 255)
    return png(width, height, pixel)


class Checks:
    def __init__(self):
        self.rows: list[dict] = []

    def record(self, name: str, passed: bool, seconds: float, detail: str = ""):
        self.rows.append({"check": name, "passed": bool(passed), "seconds": round(seconds, 2), "detail": detail[:300]})
        print(f"{'pass' if passed else 'FAIL'}  {name:<28} {seconds:6.2f} s  {detail[:90]}", flush=True)


def main() -> int:
    base, key, model = defaults()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=base)
    ap.add_argument("--key", default=key)
    ap.add_argument("--model", default=model)
    ap.add_argument("--repetitions", type=int, default=3, help="of the six short checks (default 3, so 18 checks)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if not a.key:
        raise SystemExit("no API key: set API_KEY in .env or pass --key")
    c = Checks()
    off = {"chat_template_kwargs": {"enable_thinking": False}}

    t = time.monotonic()
    status, data = request(a.base_url, "/health", None, timeout=10)
    c.record("health", status == 200 and data.get("loaded") is True, time.monotonic() - t, json.dumps(data)[:90])

    t = time.monotonic()
    status, _ = request(a.base_url, "/v1/models", "wrong-key", timeout=10)
    c.record("rejects a wrong key", status in (401, 403), time.monotonic() - t, f"HTTP {status}")

    t = time.monotonic()
    status, data = request(a.base_url, "/v1/models", a.key, timeout=10)
    names = [m.get("id") for m in data.get("data", [])]
    c.record("lists the model", status == 200 and bool(names), time.monotonic() - t, ", ".join(map(str, names)))

    for rep in range(a.repetitions):
        for name, prompt, expected in SHORT:
            body = {"model": a.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                    "top_p": 1, "top_k": 20, "max_tokens": 128, "seed": 42, **off}
            if name == "tool":
                body |= {"tools": [WRITE_TOOL], "tool_choice": "auto"}
            t = time.monotonic()
            status, data = request(a.base_url, "/v1/chat/completions", a.key, body, timeout=300)
            passed, detail = False, f"HTTP {status}"
            try:
                message = data["choices"][0]["message"]
                answer = (message.get("content") or "").strip()
                detail = answer
                if name == "tool":
                    calls = message.get("tool_calls") or []
                    detail = json.dumps([x["function"] for x in calls])
                    passed = (len(calls) == 1 and calls[0]["function"]["name"] == "write"
                              and json.loads(calls[0]["function"]["arguments"]) == expected)
                elif name == "json":
                    passed = json.loads(answer) == expected
                else:
                    passed = answer == expected
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            c.record(f"short {name} {rep + 1}", passed, time.monotonic() - t, detail)

    t = time.monotonic()
    try:
        r = stream_chat(a.base_url, a.key, {"model": a.model, "max_tokens": 64, "temperature": 0, **off,
                                            "messages": [{"role": "user", "content": "Count from 1 to 5, separated by spaces."}]})
        passed = "1 2 3 4 5" in r["content"] and bool(r["usage"].get("completion_tokens"))
        detail = f"{r['content'].strip()!r}, usage {r['usage'].get('prompt_tokens')}+{r['usage'].get('completion_tokens')}"
    except Exception as e:  # noqa: BLE001
        passed, detail = False, repr(e)
    c.record("streaming with usage", passed, time.monotonic() - t, detail)

    t = time.monotonic()
    status, data = request(a.base_url, "/v1/chat/completions", a.key, {
        "model": a.model, "max_tokens": 4096, "reasoning_effort": "low",
        "messages": [{"role": "user", "content": "What is 12 * 12? Answer with the integer only."}]}, timeout=600)
    try:
        message = data["choices"][0]["message"]
        thought = message.get("reasoning_content") or message.get("reasoning") or ""
        passed = "144" in (message.get("content") or "") and bool(thought.strip())
        detail = f"answer {(message.get('content') or '').strip()!r}, {len(thought)} characters of reasoning"
    except (KeyError, IndexError, TypeError):
        passed, detail = False, f"HTTP {status} {json.dumps(data)[:80]}"
    c.record("thinking, effort low", passed, time.monotonic() - t, detail)

    t = time.monotonic()
    status, data = request(a.base_url, "/v1/messages", a.key, {
        "model": a.model, "max_tokens": 1024, "tools": [{
            "name": "write", "description": "Write a UTF-8 file.", "input_schema": WRITE_TOOL["function"]["parameters"]}],
        "messages": [{"role": "user", "content": "Use write to save exactly hello to greeting.txt."}]},
        timeout=600, headers={"anthropic-version": "2023-06-01"})
    blocks = data.get("content") or []
    uses = [b for b in blocks if b.get("type") == "tool_use"]
    passed = status == 200 and len(uses) == 1 and uses[0].get("input") == {"path": "greeting.txt", "content": "hello"}
    c.record("Anthropic messages tool use", passed, time.monotonic() - t,
             json.dumps(uses[0].get("input")) if uses else f"HTTP {status} {json.dumps(data)[:80]}")

    images = [("image: count shapes", shapes_png(),
               "How many red circles and how many blue squares are in this image? Reply exactly in the form: red=<n> blue=<n>",
               lambda s: re.search(r"red\s*=\s*3\b", s, re.I) and re.search(r"blue\s*=\s*5\b", s, re.I)),
              ("image: read digits", digits_png("58139"),
               "What number is written in this image? Reply with the digits only.",
               lambda s: re.sub(r"\D", "", s) == "58139")]
    for name, data_png, question, check in images:
        t = time.monotonic()
        status, data = request(a.base_url, "/v1/chat/completions", a.key, {
            "model": a.model, "max_tokens": 256, "temperature": 0, **off, "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(data_png).decode()}},
                {"type": "text", "text": question}]}]}, timeout=600)
        try:
            answer = (data["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError):
            answer = f"HTTP {status} {json.dumps(data)[:80]}"
        c.record(name, bool(check(answer)), time.monotonic() - t, answer)

    passed = sum(r["passed"] for r in c.rows)
    print(f"\n{passed} of {len(c.rows)} checks passed")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"base_url": a.base_url, "model": a.model, "passed": passed,
                                     "total": len(c.rows), "checks": c.rows}, indent=2))
    return 0 if passed == len(c.rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
