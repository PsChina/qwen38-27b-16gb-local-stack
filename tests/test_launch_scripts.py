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
        waiter = self.read("scripts/windows/Wait-QwenReady.ps1")
        self.assertIn("TimeoutSeconds", waiter)

    def test_stop_waits_for_process_exit(self):
        content = self.read("scripts/windows/Stop-Qwen.ps1")
        self.assertIn("Get-Process -Name 'llama-server'", content)
        self.assertIn("did not exit within", content)

    def test_watchdog_has_single_flight_guards(self):
        content = self.read("scripts/windows/Watch-Qwen-Server.ps1")
        self.assertIn("Global\\Qwen38ServerWatchdog", content)
        self.assertIn("Get-QwenServerProcess", content)
        self.assertIn("Wait-QwenReady.ps1", content)
        self.assertIn("Test-BackendReady", content)


if __name__ == "__main__":
    unittest.main()
