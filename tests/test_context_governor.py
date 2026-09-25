import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from context_governor import (  # noqa: E402
    ContextGovernor,
    ContextGovernorConfig,
    ContextTokenizationUnavailable,
    ContextWindowExceeded,
    InvalidGenerationBudget,
)


class ContextGovernorTests(unittest.TestCase):
    def governor(self, *, backend=190000, hard=100000, safety=4096, minimum=256):
        def counter(payload, request_id):
            if payload.get("tokenizer_unavailable"):
                raise ContextTokenizationUnavailable(
                    request_id=request_id,
                    phase="tokenize",
                    detail="test failure",
                )
            return payload["prompt_tokens"]

        return ContextGovernor(
            counter,
            config=ContextGovernorConfig(
                backend_context_tokens=backend,
                context_hard_limit=hard,
                context_safety_tokens=safety,
                min_generation_tokens=minimum,
            ),
        )

    def test_q2_effective_limit_uses_per_request_hard_limit(self):
        governor = self.governor()
        self.assertEqual(governor.effective_context_limit, 100000)

    def test_prompt_is_allowed_and_output_is_clamped(self):
        prepared, decision = self.governor().prepare(
            {"prompt_tokens": 70000, "max_tokens": 12000, "messages": []},
            request_id="clamp",
        )
        self.assertEqual(decision.allowed_generation_tokens, 12000)
        self.assertEqual(prepared["max_tokens"], 12000)

    def test_effective_limit_is_rejected(self):
        with self.assertRaises(ContextWindowExceeded):
            self.governor().prepare(
                {"prompt_tokens": 100000, "max_tokens": 1000, "messages": []},
                request_id="limit",
            )

    def test_safety_reserve_reduces_limit_when_hard_limit_is_high(self):
        governor = self.governor(backend=182000, hard=190000)
        self.assertEqual(governor.effective_context_limit, 177904)

    def test_minimum_generation_is_enforced(self):
        with self.assertRaises(ContextWindowExceeded):
            self.governor(minimum=256).prepare(
                {"prompt_tokens": 99750, "max_tokens": 1000, "messages": []},
                request_id="minimum",
            )

    def test_zero_and_negative_max_tokens_are_invalid(self):
        for value in (0, -1):
            with self.assertRaises(InvalidGenerationBudget):
                self.governor().prepare(
                    {"prompt_tokens": 50000, "max_tokens": value, "messages": []},
                    request_id=f"invalid-{value}",
                )

    def test_missing_max_tokens_uses_default(self):
        _, decision = self.governor().prepare(
            {"prompt_tokens": 50000, "messages": []},
            request_id="default",
        )
        self.assertGreater(decision.requested_generation_tokens, 0)

    def test_reasoning_budget_consumes_generation_space(self):
        prepared, decision = self.governor().prepare(
            {
                "prompt_tokens": 90000,
                "max_tokens": 10000,
                "reasoning_budget": 4000,
                "messages": [],
            },
            request_id="reasoning",
        )
        self.assertEqual(decision.reasoning_budget, 4000)
        self.assertEqual(decision.available_generation_tokens, 6000)
        self.assertEqual(prepared["max_tokens"], 6000)

    def test_tokenizer_failure_is_fail_closed(self):
        with self.assertRaises(ContextTokenizationUnavailable) as raised:
            self.governor().prepare(
                {
                    "prompt_tokens": 50000,
                    "tokenizer_unavailable": True,
                    "max_tokens": 1000,
                    "messages": [],
                },
                request_id="tokenizer-down",
            )
        self.assertEqual(
            raised.exception.error_type,
            "context_tokenization_unavailable",
        )


if __name__ == "__main__":
    unittest.main()
