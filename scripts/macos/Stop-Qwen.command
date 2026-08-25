#!/bin/zsh
set -euo pipefail

: "${QWEN_SSH_TARGET:?Set QWEN_SSH_TARGET in your local shell environment}"
: "${QWEN_REMOTE_SCRIPT_DIR:?Set QWEN_REMOTE_SCRIPT_DIR to the remote scripts directory}"

ssh "$QWEN_SSH_TARGET" "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File '${QWEN_REMOTE_SCRIPT_DIR}\\Stop-Qwen.ps1'"
