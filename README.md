# Qwen 3.8 27B — 16 GB Local Stack

Public, template-first launch profiles for running the Qwen3.8-27B Q2 and Q3 GGUF variants with `llama-server` on a 16 GB GPU.

The two profiles use the same backend port and are intended to be run one at a time:

| Profile | Model | Server context | Hard gate | Effective gate after safety | Client/agent target |
| --- | --- | ---: | ---: | ---: | ---: |
| Q3 | `Qwen3.8-27B-UD-Q3_K_XL.gguf` | 92,160 | 87,063 | 87,063 | 82,000 |
| Q2 | `Qwen3.8-27B-UD-Q2_K_XL.gguf` | 182,000 | 178,000 | 177,904 | 170,000 |

The client/agent limit is deliberately independent of the llama-server limit. The Q2 profile leaves approximately 4K tokens between the governor and the backend capacity.

## What is included

- `configs/q2.env.example`: Q2 launcher environment template.
- `configs/q3.env.example`: Q3 launcher environment template.
- `configs/dsh/`: DeepSeek Harness (DSH / pi-ai) provider and compaction-policy examples for the `qwen38` route.
- `scripts/macos/`: sanitized desktop launchers for remote Q2/Q3 start and stop.
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

1. Install a compatible `llama-server` build and place the Q2/Q3 GGUF files and the matching `mmproj-Qwen3.8-27B-BF16.gguf` projector locally.
2. Copy `scripts/windows/config.local.ps1.example` to `scripts/windows/config.local.ps1`.
3. Set the model directory and server executable path in the ignored local file.
4. Run exactly one of:

   - `scripts/windows/Start-Qwen-Q3.ps1`
   - `scripts/windows/Start-Qwen-Q2.ps1`

5. Stop the active server with `scripts/windows/Stop-Qwen.ps1` before switching profiles. The stop path drains active slots first.

The profiles bind the llama-server backend to port `8080`. Existing compatibility layers can continue to expose their own client ports, such as `8098` or `8100`; this repository does not hard-code proxy credentials or remote addresses.

## Vision and the Mac desktop self-start chain

Both profiles load the Qwen3.8 multimodal projector with `--mmproj` and
`--no-mmproj-offload`. The projector is kept on CPU so enabling image input
does not claim additional GPU memory; the model layers and KV cache keep the
existing GPU placement. `Wait-QwenReady.ps1 -RequireVision` checks both
`/health` and `/props` and refuses to report a text-only server as ready.

The intended production path is the Mac Desktop `.command` launcher, then SSH,
then the remote `Keep-Qwen-SSH.ps1 -Mode Q2|Q3` script. Keep that remote copy
aligned with the `scripts/windows/` files here. The Mac launcher remains attached
to the SSH session so the remote watchdog can own the service lifecycle; a
restart waits for `/slots` to become idle before replacing a text-only process.
Do not switch profiles while a request is active. If the projector cannot fit
in the available host memory, use the smaller Q8 projector and reduce GPU
layers or context; do not silently fall back to text-only mode.

## DeepSeek Harness (DSH) integration

`configs/dsh/qwen38.provider.example.json` (and the annotated `.yaml` twin) is a ready-to-copy DeepSeek Harness / pi-ai settings fragment pointing at the local Qwen 3.8 stack:

- Provider route: `llm-pi-ai.providers.qwen38`
- API: `openai-completions`, transport `sse`
- `baseURL`: `http://qwen-host.example:8098/v1` (replace the host in a private copy; do not append `/chat/completions`)
- Models: `Qwen3.8-27B-Q3` (`contextWindow` 82000, ordinary-request `maxTokens` 9216) and `Qwen3.8-27B-Q2` (`contextWindow` 170000, ordinary-request `maxTokens` 16384), both with `input: [text, image]`
- Thinking levels: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`; default model `Qwen3.8-27B-Q3` with `max`
- Compatibility: `compat.supportsDeveloperRole=false`, `compat.maxTokensField=max_tokens`, `compat.supportsReasoningEffort=true`, `compat.thinkingFormat=openai`

The provider examples set ordinary-request caps. `configs/dsh/qwen38.compaction-policy.example.yaml` separately sets summary output caps of `55,000` for Q3 and `100,000` for Q2; merge it under the active Cordis profile's `compaction-basic.config`, not `~/.dsh/settings.yaml`. These are upper bounds, not normal-request limits; the context governor clamps each request to the generation capacity left after tokenizing its prompt and reserving reasoning tokens.

Merge the file into `~/.dsh/settings.yaml`; it uses the DSH-native `apiKeyEnv` field. The actual local key is stored separately in DSH's credential store:

```yaml
# ~/.dsh/.credentials.yaml
version: 1
refs:
  QWEN38_API_KEY: local
```

`QWEN38_API_KEY` is the only key reference used; `local` is the dummy value for the no-auth local endpoint. The DSH Models page can also write this credential. Never commit a real key. The `8098` client port is served by a compatibility proxy; the llama-server backend itself stays on `8080`. See `docs/integration.md` for the full contract.

The macOS launchers are sanitized templates of the desktop commands. They read the SSH password from the macOS Keychain and require the real remote host, user, and Windows script path only in a private copy. See `scripts/macos/README.md`.

## Important operational notes

- Q2 and Q3 must not be started simultaneously.
- The watchdog waits for `/health` and vision-enabled `/props` after launching the server; a model that is still loading is not treated as a reason to start another server.
- `Stop-Qwen.ps1` waits for active `/slots` to drain and then waits for the old process to exit before a new profile starts.
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
