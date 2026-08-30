import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
JSON_EXAMPLE = ROOT / "configs" / "dsh" / "qwen38.provider.example.json"
YAML_EXAMPLE = ROOT / "configs" / "dsh" / "qwen38.provider.example.yaml"
INTEGRATION_DOC = ROOT / "docs" / "integration.md"

EXPECTED_THINKING_LEVELS = [
    "off", "minimal", "low", "medium", "high", "xhigh", "max",
]

EXPECTED_WIRE_EFFORTS = {
    "off": "none",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "extra",
    "max": "ultra",
}


class DshConfigTests(unittest.TestCase):
    def _provider(self):
        config = json.loads(JSON_EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(config["agent-default-model"]["provider"], "qwen38")
        return config["llm-pi-ai"]["providers"]["qwen38"]

    def test_json_is_valid_and_route_is_qwen38(self):
        config = json.loads(JSON_EXAMPLE.read_text(encoding="utf-8"))
        provider = self._provider()
        self.assertIn("llm-pi-ai", config)
        self.assertEqual(provider["api"], "openai-completions")
        self.assertEqual(provider["transport"], "sse")

    def test_base_url_is_provider_root_without_chat_suffix(self):
        base_url = self._provider()["baseURL"]
        self.assertEqual(base_url, "http://qwen-host.example:8098/v1")
        self.assertFalse(base_url.endswith("/chat/completions"))
        self.assertFalse("/chat/completions" in base_url)

    def test_compatibility_flags(self):
        compat = self._provider()["compat"]
        self.assertIs(compat["supportsDeveloperRole"], False)
        self.assertEqual(compat["maxTokensField"], "max_tokens")
        self.assertIs(compat["supportsReasoningEffort"], True)
        self.assertEqual(compat["thinkingFormat"], "openai")

    def test_models_and_context_windows(self):
        models = {m["id"]: m for m in self._provider()["models"]}
        self.assertIn("Qwen3.8-27B-Q3", models)
        self.assertIn("Qwen3.8-27B-Q2", models)
        self.assertEqual(models["Qwen3.8-27B-Q3"]["contextWindow"], 87063)
        self.assertEqual(models["Qwen3.8-27B-Q2"]["contextWindow"], 144000)
        for model in models.values():
            self.assertEqual(model["maxTokens"], 8192)

    def test_default_model_and_thinking_level(self):
        config = json.loads(JSON_EXAMPLE.read_text(encoding="utf-8"))
        provider = self._provider()
        self.assertEqual(config["agent-default-model"]["model"], "Qwen3.8-27B-Q3")
        self.assertEqual(config["agent-default-model"]["reasoningEffort"], "max")
        self.assertIn(provider["reasoning"], {"xhigh", "max"})

    def test_thinking_levels_are_the_dsh_set(self):
        efforts = self._provider()["models"][0]["reasoningEfforts"]
        self.assertEqual(list(efforts), EXPECTED_THINKING_LEVELS)
        self.assertEqual(efforts, EXPECTED_WIRE_EFFORTS)

    def test_api_key_uses_env_name_only_and_no_real_credential(self):
        provider = self._provider()
        self.assertEqual(provider["apiKeyEnv"], "QWEN38_API_KEY")
        self.assertNotRegex(json.dumps(provider), r"(sk-|api[_-]?key[=:]\s*\w{16,})", "real-looking credential present")

    def test_yaml_example_mentions_required_contract(self):
        text = YAML_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("qwen38:", text)
        self.assertIn("api: openai-completions", text)
        self.assertIn("http://qwen-host.example:8098/v1", text)
        self.assertIn("transport: sse", text)
        self.assertIn("QWEN38_API_KEY", text)
        self.assertIn("reasoningEfforts:", text)
        for level in EXPECTED_THINKING_LEVELS:
            self.assertIn(level, text)
        for model in ("Qwen3.8-27B-Q3", "Qwen3.8-27B-Q2"):
            self.assertIn(model, text)
        for value in ("87063", "144000", "8192"):
            self.assertIn(value, text)
        # The requirement is that the baseUrl VALUE must not carry the chat
        # completions path; a comment may warn about it.
        base_url_line = next(
            line.split(" #", 1)[0].strip() for line in text.splitlines()
            if line.lstrip().startswith("baseURL:")
        )
        self.assertNotIn("/chat/completions", base_url_line)
        self.assertNotIn("sk-", text)

    def test_integration_documents_compaction_reasoning_contract(self):
        text = INTEGRATION_DOC.read_text(encoding="utf-8")
        self.assertIn("X-DSH-Purpose: compaction", text)
        self.assertIn("reasoning_effort", text)
        self.assertIn("none", text)
        self.assertIn("disabled-thinking", text)

    def test_examples_are_sanitized(self):
        for path in (JSON_EXAMPLE, YAML_EXAMPLE):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?")
            self.assertNotRegex(text, r"(?i)(?:password|passwd)\s*[:=]")
            self.assertNotRegex(text, r"C:\\Users\\(?!qwen-user)")


if __name__ == "__main__":
    unittest.main()
