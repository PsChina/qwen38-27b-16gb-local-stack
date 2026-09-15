#!/bin/bash
set -euo pipefail

# Sanitized desktop launcher template. Replace values only in your private
# Desktop copy, or export the QWEN_* variables before launching it.
REMOTE_USER="${QWEN_REMOTE_USER:-qwen-user}"
REMOTE_HOST="${QWEN_REMOTE_HOST:-qwen-host.example}"
REMOTE_SCRIPT="${QWEN_STOP_REMOTE_SCRIPT:-C:\\Users\\qwen-user\\AI\\Stop-Qwen-Services.ps1}"
KEYCHAIN_SERVICE="${QWEN_KEYCHAIN_SERVICE:-qwen38-windows-ssh}"

if ! command -v expect >/dev/null 2>&1; then
  echo "Missing dependency: expect"
  echo "Install it with: brew install expect"
  exit 1
fi

PASSWORD="$(security find-generic-password -a "$REMOTE_USER" -s "$KEYCHAIN_SERVICE" -w 2>/dev/null || true)"
if [[ -z "$PASSWORD" ]]; then
  echo "No SSH password found in the macOS Keychain."
  echo "Add it without putting it in this file:"
  echo "  security add-generic-password -a '$REMOTE_USER' -s '$KEYCHAIN_SERVICE' -w"
  exit 1
fi

echo "Stopping Qwen services on ${REMOTE_USER}@${REMOTE_HOST}"
echo "The remote stop script drains active requests before terminating services."

expect "$PASSWORD" "$REMOTE_USER" "$REMOTE_HOST" "$REMOTE_SCRIPT" <<'EXPECT_SCRIPT'
set timeout 30
set password [lindex $argv 0]
set remote_user [lindex $argv 1]
set remote_host [lindex $argv 2]
set remote_script [lindex $argv 3]

spawn ssh -tt -o ConnectTimeout=30 -o ConnectionAttempts=3 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new "$remote_user@$remote_host" "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"$remote_script\""
expect {
  -re "(?i)are you sure.*yes/no" { send -- "yes\r"; exp_continue }
  -re "(?i)password:" { send -- "$password\r"; exp_continue }
  eof
}
EXPECT_SCRIPT
