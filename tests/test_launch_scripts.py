import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LaunchScriptTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_q2_and_q3_wait_for_health(self):
        for name in ("Start-Qwen-Q2.ps1", "Start-Qwen-Q3.ps1"):
            content = self.read(Path("scripts/windows") / name)
            self.assertIn("Wait-QwenReady.ps1", content)
            self.assertIn("-TargetHost", content)
            self.assertIn("Wait-QwenIdle.ps1", content)
            self.assertIn("--mmproj", content)
            self.assertIn("--no-mmproj-offload", content)
            self.assertIn("-RequireVision", content)
            self.assertIn("already vision-ready", content)
        waiter = self.read("scripts/windows/Wait-QwenReady.ps1")
        self.assertIn("TimeoutSeconds", waiter)
        self.assertIn("RequireVision", waiter)

    def test_idle_waiter_drains_active_slots(self):
        content = self.read("scripts/windows/Wait-QwenIdle.ps1")
        self.assertIn("/slots", content)
        self.assertIn("is_processing", content)
        self.assertIn("did not become idle", content)

    def test_stop_waits_for_process_exit(self):
        content = self.read("scripts/windows/Stop-Qwen.ps1")
        self.assertIn("Get-Process -Name 'llama-server'", content)
        self.assertIn("Wait-QwenIdle.ps1", content)
        self.assertIn("did not exit within", content)

    def test_macos_launchers_retry_ssh_banner_failures(self):
        for name in ("Start-Qwen-Q2.command", "Start-Qwen-Q3.command", "Stop-Qwen.command"):
            content = self.read(Path("scripts/macos") / name)
            self.assertIn("ConnectTimeout=30", content)
            self.assertIn("ConnectionAttempts=3", content)

    def test_watchdog_has_single_flight_guards(self):
        content = self.read("scripts/windows/Watch-Qwen-Server.ps1")
        self.assertIn("Global\\Qwen38ServerWatchdog", content)
        self.assertIn("Get-QwenServerProcess", content)
        self.assertIn("Wait-QwenReady.ps1", content)
        self.assertIn("Wait-QwenIdle.ps1", content)
        self.assertIn("Test-BackendReady", content)
        self.assertIn("vision", content)
        self.assertIn("--mmproj", content)
        self.assertIn("--no-mmproj-offload", content)


if __name__ == "__main__":
    unittest.main()
