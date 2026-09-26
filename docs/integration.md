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
| `LLAMA_BACKEND_CONTEXT_TOKENS` | `92160` | `190000` |
| `CONTEXT_HARD_LIMIT` | `87063` | `100000` |
| `LLAMA_CONTEXT_SAFETY_TOKENS` | `4096` | `4096` |

The effective limit is:

```text
min(CONTEXT_HARD_LIMIT,
    LLAMA_BACKEND_CONTEXT_TOKENS - LLAMA_CONTEXT_SAFETY_TOKENS)
```

Q2 uses a shared 190,000-token KV pool with two slots (`--parallel 2 --kv-unified`). Set `LLAMA_BACKEND_CONTEXT_TOKENS=190000`; the governor's per-request hard limit is `100000`. The effective limit is therefore 100,000, while the pool remains shared across both slots. Two requests cannot both use 100,000 tokens simultaneously; their combined active context must stay within 190,000.

The agent/client limit is configured outside the server launcher. Keep the client-side targets at `82000` for Q3 and `100000` for Q2 rather than raising them to the backend capacities.

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
- `configs/dsh/qwen38.compaction-policy.example.yaml` (Cordis `compaction-basic.config` fragment; do not merge it into `~/.dsh/settings.yaml`)

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
| `Qwen3.8-27B-Q3` | `82000` | `9216` | `xhigh` |
| `Qwen3.8-27B-Q2` | `100000` | `16384` | `xhigh` |

Both model entries advertise `input: [text, image]`; the proxy must preserve
the image parts when translating requests to llama.cpp. These `maxTokens` values
cap ordinary requests. Merge the separate compaction-policy fragment under the
active Cordis profile's `compaction-basic.config`; it caps summary output at
`55000` for Q3 and `100000` for Q2. The context governor clamps each request to
the generation capacity remaining after the rendered prompt and reasoning
budget. `maxTokens` is a per-generation-request ceiling, not a context-window
or reasoning-effort setting; automatic continuation may issue another request
under the same ceiling.

For Q2, the `100000`-token Harness window, `16384`-token ordinary output cap,
and `3616`-token compaction headroom yield an automatic pressure trigger at
`80000` tokens. The separate `100000` summary cap does not set that trigger.

The model card's Qwen-native thinking levels are `low`, `medium`, and `xhigh`;
DSH exposes those unchanged and adds `off` as a disable-thinking control mapped
to wire effort `none`. Both routes default to `xhigh`, the model card's default
thinking effort. The llama-server launch scripts set Qwen's official
thinking-mode sampler as the server default: `temp=1.0`, `top_p=0.95`,
`top_k=20`, `min_p=0`, `presence_penalty=0`, `repeat_penalty=1`. The DSH profile
sends that preset for every enabled-effort request and Qwen's separate
non-thinking preset (`temp=0.7`, `top_p=0.80`, `top_k=20`, `min_p=0`,
`presence_penalty=1.5`, `repeat_penalty=1`) when `off` is selected. Direct
llama-server clients continue to use server defaults.
See the [official Qwen3.8-27B model card](https://huggingface.co/Qwen/Qwen3.8-27B) for the upstream recommendations.

API key: the examples reference `QWEN38_API_KEY` through DSH's `apiKeyEnv`. Store the actual value in DSH's managed credential file (or enter it once in the DSH Models page). The local compatibility layer has no authentication, so the dummy value `local` is sufficient:

```yaml
# ~/.dsh/.credentials.yaml
version: 1
refs:
  QWEN38_API_KEY: local
```

Never write a real API key into a checked-in config. The credentials file is user-local and should remain mode `0600`. The model `contextWindow` values above are client-side budgets. The proxy enforces per-request context limits of `87063` for Q3 and `100000` for Q2. Q2's 190,000-token backend pool is shared by two slots, so their combined live context cannot exceed the pool. The governor clamps `max_tokens` to the space remaining after the rendered prompt and reasoning budget.
