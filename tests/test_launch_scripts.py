import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LaunchScriptTests(unittest.TestCase):
    SAMPLER_FLAGS = (
        ("--temp", "1.0"),
        ("--top-p", "0.95"),
        ("--top-k", "20"),
        ("--min-p", "0.0"),
        ("--presence-penalty", "0.0"),
        ("--repeat-penalty", "1.0"),
    )

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

    def test_q2_uses_shared_190k_pool_with_two_slots_and_100k_guard(self):
        start = self.read("scripts/windows/Start-Qwen-Q2.ps1")
        watchdog = self.read("scripts/windows/Watch-Qwen-Server.ps1")
        args = self.read("profiles/q2/llama-server.args.example")
        self.assertIn("LLAMA_BACKEND_CONTEXT_TOKENS = '190000'", start)
        self.assertIn("CONTEXT_HARD_LIMIT = '100000'", start)
        self.assertIn("'--ctx-size', '190000'", start)
        self.assertIn("'--parallel', '2'", start)
        self.assertIn("'--kv-unified'", start)
        self.assertIn("'--spec-draft-n-max', '4'", start)
        self.assertIn("Parallel = 2", watchdog)
        self.assertIn("Context = 190000", watchdog)
        self.assertIn("HardLimit = 100000", watchdog)
        self.assertIn("SpecDraftNMax = 4", watchdog)
        self.assertIn("--ctx-size 190000", args)
        self.assertIn("--parallel 2", args)
        self.assertIn("--kv-unified", args)
        self.assertIn("--spec-draft-n-max 4", args)

    def test_q3_launch_settings_remain_single_slot_with_three_mtp_tokens(self):
        start = self.read("scripts/windows/Start-Qwen-Q3.ps1")
        watchdog = self.read("scripts/windows/Watch-Qwen-Server.ps1")
        self.assertIn("'--parallel', '1'", start)
        self.assertIn("'--spec-draft-n-max', '3'", start)
        self.assertIn("Parallel = 1", watchdog)
        self.assertIn("SpecDraftNMax = 3", watchdog)

    def test_every_server_start_uses_official_qwen_thinking_sampler(self):
        paths = (
            "scripts/windows/Start-Qwen-Q2.ps1",
            "scripts/windows/Start-Qwen-Q3.ps1",
            "scripts/windows/Watch-Qwen-Server.ps1",
            "profiles/q2/llama-server.args.example",
            "profiles/q3/llama-server.args.example",
        )
        for path in paths:
            content = self.read(path)
            expected = (
                (f"'{flag}', '{value}'" for flag, value in self.SAMPLER_FLAGS)
                if path.endswith(".ps1")
                else (f"{flag} {value}" for flag, value in self.SAMPLER_FLAGS)
            )
            with self.subTest(path=path):
                for argument in expected:
                    self.assertIn(argument, content)


if __name__ == "__main__":
    unittest.main()
