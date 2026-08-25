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
