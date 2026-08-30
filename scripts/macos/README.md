# macOS Qwen launchers

These three `.command` files are sanitized versions of the desktop commands
used to start Qwen Q2/Q3 and stop the remote services over SSH.

They contain no real host, username, Windows path, or password. The SSH
password is read at runtime from the macOS Keychain. The start commands call
the remote `Keep-Qwen-SSH.ps1` script with `-Mode Q2` or `-Mode Q3`; the stop
command calls `Stop-Qwen-Services.ps1`.

## Private installation

Install `expect` if needed:

```bash
brew install expect
```

Store the SSH password in Keychain without putting it in a file:

```bash
security add-generic-password \
  -a "qwen-user" \
  -s "qwen38-windows-ssh" \
  -w
```

Copy the templates to the Desktop and edit only those private copies:

```bash
cp scripts/macos/Start-Qwen-Q2.command "$HOME/Desktop/启动 Qwen Q2.command"
cp scripts/macos/Start-Qwen-Q3.command "$HOME/Desktop/启动 Qwen Q3.command"
cp scripts/macos/Stop-Qwen.command "$HOME/Desktop/关闭 Qwen 服务.command"
```

Replace the placeholder values at the top of each private copy, or provide
`QWEN_REMOTE_USER`, `QWEN_REMOTE_HOST`, `QWEN_REMOTE_SCRIPT`,
`QWEN_STOP_REMOTE_SCRIPT`, and `QWEN_KEYCHAIN_SERVICE` in the environment.
Make the private copies executable if Finder does not launch them:

```bash
chmod +x "$HOME/Desktop/启动 Qwen Q2.command" \
  "$HOME/Desktop/启动 Qwen Q3.command" \
  "$HOME/Desktop/关闭 Qwen 服务.command"
```
