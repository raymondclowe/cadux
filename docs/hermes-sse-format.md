# Hermes SSE / Session Chat Format

## Endpoint

```
POST /api/sessions/{session_id}/chat/stream
```

## Request Payload

```json
{"message": "user text here"}
```

NOT OpenAI format `{"messages": [...]}` — that's only for `/v1/chat/completions`.

## Response (SSE)

Uses `event:` + `data:` lines (NOT plain `data:` like OpenAI). Format:

```
event: run.started
data: {"user_message": {"role": "user", "content": "..."}, "session_id": "...", ...}

event: message.started
data: {"message": {"id": "msg_...", "role": "assistant"}, ...}

event: assistant.delta
data: {"message_id": "msg_...", "delta": "token_chunk"}

event: tool.progress
data: {"message_id": "msg_...", "tool_name": "_thinking", "delta": "..."}

event: assistant.completed
data: {"session_id": "...", "message_id": "...", "content": "full response", ...}

event: run.completed
data: {"session_id": "...", "completed": true, "messages": [...], "usage": {...}}

event: done
data: {}
```

## Session Create Response

```json
{
  "object": "hermes.session",
  "session": {
    "id": "api_...",
    "source": "api_server",
    "model": "hermes-agent",
    ...
  }
}
```

Extract session id via `body["session"]["id"]`.

## Session List Response

```json
{
  "data": [
    {
      "id": "session_id",
      "model": "auto-fastest",
      "title": null,
      ...
    }
  ]
}
```

Session `model` field contains the actual model name used.
