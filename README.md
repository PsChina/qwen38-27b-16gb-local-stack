# Qwen 3.8 27B — 16 GB Local Stack

Public, template-first launch profiles for running the Qwen3.8-27B Q2 and Q3 GGUF variants with `llama-server` on a 16 GB GPU.

The two profiles use the same backend port and are intended to be run one at a time:

| Profile | Model | Server context | Hard gate | Effective gate after safety | Client/agent target |
| --- | --- | ---: | ---: | ---: | ---: |
| Q3 | `Qwen3.8-27B-UD-Q3_K_XL.gguf` | 92,160 | 87,063 | 87,063 | configure separately |
| Q2 | `Qwen3.8-27B-UD-Q2_K_XL.gguf` | 182,000 | 178,000 | 177,904 | 144,000 |

The client/agent limit is deliberately independent of the llama-server limit. The Q2 profile leaves approximately 4K tokens between the governor and the backend capacity.

## What is included

- `profiles/q2/llama-server.args.example`: Q2 server arguments.
- `profiles/q3/llama-server.args.example`: Q3 server arguments.
- `scripts/windows/`: two Windows launch entries, a readiness probe, a stop entry, and a single-instance server watchdog, driven by a local ignored config.
- `scripts/macos/`: optional SSH wrappers for launching Q2 or Q3 remotely from a Mac desktop.
- `src/context_governor.py`: provider-independent rendered-prompt context guard.
- `tests/`: local unit tests for the governor policy; no Qwen connection is required.
- `docs/`: integration and safety notes.

## Privacy boundary

This repository intentionally contains templates only. Do not commit:

- private IP addresses, hostnames, usernames, passwords, SSH targets, or API keys;
- local absolute paths;
- model files, logs, transcripts, or remote server snapshots.

Copy `scripts/windows/config.local.ps1.example` to `config.local.ps1` and fill in local paths. That file is ignored by Git.

## Quick start

1. Install a compatible `llama-server` build and place the Q2/Q3 GGUF files locally.
2. Copy `scripts/windows/config.local.ps1.example` to `scripts/windows/config.local.ps1`.
3. Set the model directory and server executable path in the ignored local file.
4. Run exactly one of:

   - `scripts/windows/Start-Qwen-Q3.ps1`
   - `scripts/windows/Start-Qwen-Q2.ps1`

5. Stop the active server with `scripts/windows/Stop-Qwen.ps1` before switching profiles.

The profiles bind the llama-server backend to port `8080`. Existing compatibility layers can continue to expose their own client ports, such as `8098` or `8100`; this repository does not hard-code proxy credentials or remote addresses.

## Important operational notes

- Q2 and Q3 must not be started simultaneously.
- The watchdog waits for `/health` after launching the server; a model that is still loading is not treated as a reason to start another server.
- `Stop-Qwen.ps1` waits for the old process to exit before a new profile starts.
- The executable path is configurable; no particular CUDA build directory is assumed.
- `--parallel 1` is intentional for a single-user long-context workload.
- The server arguments keep flash attention, Q4 KV cache, MTP draft settings, Jinja templates, metrics, and verbose logging explicit.
- The governor must count the final rendered chat-template prompt with the backend tokenizer. Character estimates are not a safe fallback.

## Tests

From the repository root:

```text
python -m unittest discover -s tests -v
```

The tests use fake token counts and never connect to a model server.
