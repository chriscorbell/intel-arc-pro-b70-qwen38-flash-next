# Connecting clients

The server speaks OpenAI's Chat Completions (`/v1/chat/completions`) and Anthropic's Messages (`/v1/messages`) APIs on one port, with tool calls, streaming, thinking and images on both. Every request needs `Authorization: Bearer <API_KEY>`. The model name in a request can be anything; `/v1/models` reports `SERVED_NAME` (default `qwen38`).

It serves one request at a time. A second client waits for the first; up to four conversations stay parked in RAM, so switching between them does not re-read their prompts.

## Thinking

Set `reasoning_effort` on Chat Completions requests, or the effort in Claude Code:

| Effort | Result |
|---|---|
| `none`, `minimal` | No thinking |
| `low`, `medium`, `xhigh` | Three distinct levels of the chat template |
| `high`, `max`, or none given | Treated as `xhigh` |

`"chat_template_kwargs": {"enable_thinking": false}` also turns thinking off. Thinking arrives in `reasoning_content` on Chat Completions and as thinking blocks on Messages.

## Context window

The window is 262,144 tokens (`MAX_CONTEXT`). The server clamps a request's `max_tokens` to the room left in the window rather than rejecting it. For clients that compact on their own, declare a window that leaves room for their output cap: Claude Code asks for 32,000 output tokens on every request, so tell it 229,376 (262,144 minus 32,768).

## Claude Code

No proxy is needed. Run Claude Code with these variables:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:8000        # no /v1; use your BIND_ADDR and PORT
export ANTHROPIC_AUTH_TOKEN=<API_KEY from .env>          # sent as Authorization: Bearer
export ANTHROPIC_MODEL=qwen38
export ANTHROPIC_DEFAULT_OPUS_MODEL=qwen38               # background tasks and subagents ask for these
export ANTHROPIC_DEFAULT_SONNET_MODEL=qwen38
export ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen38
export CLAUDE_CODE_SUBAGENT_MODEL=qwen38
export CLAUDE_CODE_MAX_CONTEXT_TOKENS=229376             # otherwise it assumes 200,000 for an unknown model
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
claude --effort xhigh
```

A wrapper script that sets these and then runs `claude "$@"` keeps your normal `claude` on your Anthropic login. Notes from use:

- Claude Code sends no temperature, top_p or top_k, so the server's `SAMPLING` default applies (the model card's thinking-mode values).
- A launcher started from inside another Claude Code session, or from the Claude desktop app, inherits variables that override the token and get a 401. Unset `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_CODE_HOST_SESSION_ID`, `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH` and `CLAUDE_AGENT_SDK_VERSION` first, or start it with `env -i HOME="$HOME" PATH="$PATH" ...`.
- `[claude-code:unrecognized_model]` on stderr is a harmless warning.
- Claude Code turns off MCP tool search with a base URL that is not Anthropic's, so every MCP tool's schema is in every prompt. Many MCP tools mean long prompts; deny the ones you do not need with `--disallowedTools`.
- WebFetch works.
- Thinking blocks from this server carry signatures Anthropic's API will not accept, so do not resume one of these sessions with a normal `claude`.

Tested on this configuration with Claude Code 2.1.293 through the coding evaluations in [results.md](results.md): file reads and edits, shell commands and test runs, one request at a time.

## Pi

In `~/.pi/agent/models.json`, with the key in a file:

```json
{
  "providers": {
    "qwen38-server": {
      "baseUrl": "http://127.0.0.1:8000/v1",
      "api": "openai-completions",
      "apiKey": "!cat \"$HOME/.config/qwen38/api-key\"",
      "compat": {
        "supportsStore": false,
        "supportsDeveloperRole": false,
        "supportsReasoningEffort": true,
        "supportsUsageInStreaming": true,
        "maxTokensField": "max_tokens",
        "thinkingFormat": "openai"
      },
      "models": [
        {
          "id": "qwen38",
          "name": "Qwen3.8-Flash-Next",
          "reasoning": true,
          "thinkingLevelMap": {"off": "none", "minimal": null, "low": "low", "medium": "medium",
                               "high": null, "xhigh": "xhigh", "max": null},
          "input": ["text", "image"],
          "contextWindow": 262144,
          "maxTokens": 32768,
          "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
        }
      ]
    }
  }
}
```

Then `pi --model qwen38-server/qwen38`. Tested with Pi 1.1.0: a bug fix in a small Python project at xhigh (tests 4 of 4), each thinking level reaching the server as its own effort, and reading a PNG.

## Anything OpenAI-compatible

Base URL `http://<BIND_ADDR>:<PORT>/v1`, the key as the API key, any model name:

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions -H "Authorization: Bearer $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen38", "reasoning_effort": "low", "messages": [{"role": "user", "content": "Hello"}]}'
```

Streaming with `stream_options.include_usage` returns usage last, including `prompt_tokens_details.cached_tokens`. Images go in as `image_url` parts with a `data:` URL. `/v1/responses` answers too, but only a basic request was checked.
