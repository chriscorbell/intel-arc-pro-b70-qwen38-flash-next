"""Shared helpers for smoke_test.py and bench.py: settings from .env, and plain HTTP calls. Standard library only."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def defaults() -> tuple[str, str, str]:
    """Base URL, API key and model name: the environment first, then .env."""
    env = {**dotenv(), **{k: v for k, v in os.environ.items() if k in ("API_KEY", "BIND_ADDR", "PORT", "SERVED_NAME")}}
    host = env.get("BIND_ADDR", "127.0.0.1")
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    base = os.environ.get("BASE_URL") or f"http://{host}:{env.get('PORT', '8000')}"
    return base, env.get("API_KEY", ""), env.get("SERVED_NAME", "qwen38")


def request(base: str, path: str, key: str | None, body: dict | None = None, timeout: float = 1800,
            headers: dict | None = None) -> tuple[int, dict]:
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode(errors="replace")[:500]}


def stream_chat(base: str, key: str, body: dict, timeout: float = 1800) -> dict:
    """Stream a chat completion. Returns time to first token, total time, the text and the server's usage."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    t0 = time.monotonic()
    ttft = None
    usage: dict = {}
    content, reasoning, finish = "", "", None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data: "):
                continue
            if line[6:] == "[DONE]":
                break
            chunk = json.loads(line[6:])
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = (delta.get("content") or "") + (delta.get("reasoning_content") or delta.get("reasoning") or "")
                piece += "".join((c.get("function") or {}).get("arguments") or "" for c in delta.get("tool_calls") or [])
                if piece and ttft is None:
                    ttft = time.monotonic() - t0
                content += delta.get("content") or ""
                reasoning += delta.get("reasoning_content") or delta.get("reasoning") or ""
                finish = choice.get("finish_reason") or finish
    return {"ttft": ttft, "total": time.monotonic() - t0, "content": content, "reasoning": reasoning,
            "finish_reason": finish, "usage": usage}
