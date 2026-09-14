# Integration contract

The context governor is intentionally backend-facing. A compatibility proxy should use this order:

1. Convert the incoming request into the backend message shape.
2. Apply the exact llama.cpp chat template.
3. Tokenize the rendered prompt with the same backend tokenizer.
4. Call `ContextGovernor.prepare(...)`.
5. Reject `ContextTokenizationUnavailable` and `ContextWindowExceeded` before `/v1/chat/completions`.
6. Forward the protected payload with the clamped `max_tokens`.

Do not use a character estimate as a fallback after `/apply-template` or `/tokenize` fails. The safe behavior is fail-closed.

## Profile-specific environment

The launcher sets the policy values for the selected model:

| Variable | Q3 | Q2 |
| --- | ---: | ---: |
| `LLAMA_BACKEND_CONTEXT_TOKENS` | `92160` | `182000` |
| `CONTEXT_HARD_LIMIT` | `87063` | `178000` |
| `LLAMA_CONTEXT_SAFETY_TOKENS` | `4096` | `4096` |

The effective limit is:

```text
min(CONTEXT_HARD_LIMIT,
    LLAMA_BACKEND_CONTEXT_TOKENS - LLAMA_CONTEXT_SAFETY_TOKENS)
```

The agent/client limit is configured outside the server launcher. For Q2, keep the client-side target at `144000` rather than raising it to the server's `182000` capacity.

## Vision path and restart safety

The Q2 and Q3 launchers load `mmproj-Qwen3.8-27B-BF16.gguf` with
`--no-mmproj-offload`, keeping the vision projector on CPU while the language
model remains on the GPU. The readiness gate checks `/health` and then requires
`/props` to report `modalities.vision=true`; a healthy text-only process is not
accepted as ready. The watcher and stop script poll `/slots` and wait for active
requests to finish before replacing a process. This makes the Mac Desktop
`.command` → SSH → `Keep-Qwen-SSH.ps1 -Mode` chain safe to use for the next
restart without interrupting the request currently in flight.

## DeepSeek Harness (DSH / pi-ai) client

The llama-server backend binds port `8080`. A compatibility proxy (for example an LM Studio-style layer or the local proxy) exposes the OpenAI-compatible surface on a client port such as `8098`. DSH talks to that client port, never directly to the llama-server backend.

Ready-to-copy provider examples:

- `configs/dsh/qwen38.provider.example.json` (machine-readable settings fragment)
- `configs/dsh/qwen38.provider.example.yaml` (annotated settings fragment)

Request flow:

```text
DSH / pi-ai client
  -> POST http://qwen-host.example:8098/v1/chat/completions   (replace host privately; openai-completions, SSE)
  -> compatibility proxy (client port 8098)
  -> llama-server backend (port 8080, Qwen3.8-27B-Q2/Q3)
```

For `dsh-compaction-basic` auxiliary summaries, DSH / pi-ai sends `X-DSH-Purpose: compaction`. A compatible proxy preserves an explicit `reasoning_effort` from the request; when that field is absent for this purpose, it must use the `none` budget rather than the provider's default reasoning level. It should also interpret an explicit disabled-thinking marker as `none` so `off` cannot fall back to `medium`.

Provider contract used by the examples:

| Setting | Value | Meaning |
| --- | --- | --- |
| `llm-pi-ai.providers` | `qwen38` | Provider route name (must stay `qwen38`) |
| `api` | `openai-completions` | Wire protocol |
| `baseURL` | `http://qwen-host.example:8098/v1` | Replace the host privately; do not append `/chat/completions` |
| `transport` | `sse` | Stream responses |
| `compat.supportsDeveloperRole` | `false` | llama.cpp OpenAI layer has no developer role |
| `compat.maxTokensField` | `max_tokens` | Output cap request field |
| `compat.supportsReasoningEffort` | `true` | Reasoning effort is forwarded |
| `compat.thinkingFormat` | `openai` | OpenAI-style reasoning field |

Models:

| Model id (`--alias`) | `contextWindow` | `maxTokens` | Default thinking |
| --- | ---: | ---: | --- |
| `Qwen3.8-27B-Q3` | `87063` | `8192` | `max` |
| `Qwen3.8-27B-Q2` | `144000` | `8192` | `low` |

Both model entries advertise `input: [text, image]`; the proxy must preserve
the image parts when translating requests to llama.cpp.

Thinking levels accepted by DSH / pi-ai are declared under each model's `reasoningEfforts`: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. The checked-in map preserves the existing proxy vocabulary: `off → none`, `minimal → minimal`, `xhigh → extra`, and `max → ultra`. The default provider model is `Qwen3.8-27B-Q3` with `max`.

API key: the examples reference `QWEN38_API_KEY` through DSH's `apiKeyEnv`. Store the actual value in DSH's managed credential file (or enter it once in the DSH Models page). The local compatibility layer has no authentication, so the dummy value `local` is sufficient:

```yaml
# ~/.dsh/.credentials.yaml
version: 1
refs:
  QWEN38_API_KEY: local
```

Never write a real API key into a checked-in config. The credentials file is user-local and should remain mode `0600`. The context window values above are client-side caps: `87063` is the Q3 hard gate and `144000` is the Q2 client/agent target. The governor still clamps `max_tokens` per request, so raising the client `maxTokens` does not bypass the backend safety reserve.
