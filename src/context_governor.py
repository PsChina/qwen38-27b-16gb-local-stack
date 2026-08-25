"""Provider-independent context budgeting for the local Anthropic proxy.

The governor deliberately receives a callable that counts the *rendered*
prompt.  This keeps policy separate from the HTTP/backend adapter and makes
the hard cases testable without a live llama.cpp server.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


DEFAULT_MAX_TOKENS = 65536


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return max(0, int(value))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ContextGovernorConfig:
    """Runtime policy; values can be overridden with environment variables."""

    backend_context_tokens: int = field(
        default_factory=lambda: _env_int("LLAMA_BACKEND_CONTEXT_TOKENS", 92160)
    )
    context_hard_limit: int = field(
        default_factory=lambda: _env_int("CONTEXT_HARD_LIMIT", 87063)
    )
    context_safety_tokens: int = field(
        default_factory=lambda: _env_int("LLAMA_CONTEXT_SAFETY_TOKENS", 4096)
    )
    min_generation_tokens: int = field(
        default_factory=lambda: _env_int("LLAMA_MIN_GENERATION_TOKENS", 256)
    )
    max_tool_result_chars: int = field(
        # 24K chars is roughly 6K tokens and prevents one tool result from
        # consuming the entire upstream context before the hard guard runs.
        default_factory=lambda: _env_int("MAX_TOOL_RESULT_CHARS", 24000)
    )
    max_agent_return_tokens: int = field(
        # Agent/tool output is capped more tightly by default.  The original
        # result is not mutated; only the backend-facing copy is protected.
        default_factory=lambda: _env_int("MAX_AGENT_RETURN_TOKENS", 6144)
    )
    context_debug: bool = field(
        default_factory=lambda: _env_bool("CONTEXT_DEBUG", False)
    )


@dataclass(frozen=True)
class ToolProtection:
    kind: str
    original_chars: int
    protected_chars: int


@dataclass(frozen=True)
class ContextDecision:
    request_id: str
    prompt_tokens: int
    requested_generation_tokens: int
    allowed_generation_tokens: int
    hard_limit: int
    effective_context_limit: int
    backend_context_tokens: int
    reasoning_budget: int
    available_generation_tokens: int
    breakdown: Mapping[str, Any] = field(default_factory=dict)
    protections: tuple[ToolProtection, ...] = ()


class ContextTokenizationUnavailable(ValueError):
    """The exact provider tokenizer could not safely measure the prompt."""

    error_type = "context_tokenization_unavailable"

    def __init__(self, *, request_id: str, phase: str, detail: str) -> None:
        self.request_id = request_id
        self.phase = phase
        self.detail = detail[:500]
        super().__init__("Unable to calculate exact prompt tokens safely")


class InvalidGenerationBudget(ValueError):
    """The caller supplied an invalid explicit generation budget."""

    error_type = "invalid_request_error"

    def __init__(self, *, request_id: str, field: str, value: Any) -> None:
        self.request_id = request_id
        self.field = field
        self.value = value
        super().__init__(f"{field} must be a positive integer")


class ContextWindowExceeded(ValueError):
    """The rendered prompt is at or above the configured prompt hard limit."""

    error_type = "context_window_exceeded"

    def __init__(
        self,
        *,
        request_id: str,
        prompt_tokens: int,
        hard_limit: int,
        effective_context_limit: int,
        backend_context_tokens: int,
        context_safety_tokens: int,
        reasoning_budget: int,
    ) -> None:
        self.request_id = request_id
        self.prompt_tokens = prompt_tokens
        self.hard_limit = hard_limit
        self.effective_context_limit = effective_context_limit
        self.backend_context_tokens = backend_context_tokens
        self.context_safety_tokens = context_safety_tokens
        self.reasoning_budget = reasoning_budget
        self.available_tokens = max(
            0, effective_context_limit - prompt_tokens - reasoning_budget
        )
        super().__init__(
            f"context_window_exceeded: rendered prompt uses about "
            f"{prompt_tokens} tokens; effective context limit is "
            f"{effective_context_limit}; "
            f"available generation tokens are {self.available_tokens}; "
            f"backend context is {backend_context_tokens} with "
            f"{context_safety_tokens} safety tokens reserved; "
            f"reasoning budget is {reasoning_budget}"
        )


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "".join(_as_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "value", "thinking", "reasoning"):
            if key in value:
                return _as_text(value[key])
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _looks_like_agent_result(value: str) -> bool:
    """Recognize Claude Code TaskOutput-style result envelopes conservatively."""
    markers = ("<task_id>", "<task_type>", "<retrieval_status>")
    return "<output>" in value and any(marker in value for marker in markers)


def _protected_text(value: str, *, kind: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(value) <= limit:
        return value, False

    marker = (
        "\n\n[Context Governor: result too large. "
        f"kind={kind}; original_chars={len(value)}; "
        "full content was not deleted by the proxy. "
        "Store the full content in a file and return only a summary.]\n\n"
    )
    if len(marker) >= limit:
        return marker[:limit], True

    remaining = limit - len(marker)
    head_chars = remaining // 2
    tail_chars = remaining - head_chars
    head = value[:head_chars]
    tail = value[-tail_chars:] if tail_chars else ""
    return head + marker + tail, True


class ContextGovernor:
    """Protect large tool results and enforce a rendered-prompt hard limit."""

    def __init__(
        self,
        rendered_prompt_counter: Callable[[Mapping[str, Any], str], int],
        *,
        breakdown_counter: Callable[[Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        logger: Callable[[str], None] | None = None,
        config: ContextGovernorConfig | None = None,
    ) -> None:
        self.rendered_prompt_counter = rendered_prompt_counter
        self.breakdown_counter = breakdown_counter
        self.logger = logger or print
        self.config = config or ContextGovernorConfig()

    @property
    def effective_context_limit(self) -> int:
        return min(
            self.config.context_hard_limit,
            max(0, self.config.backend_context_tokens - self.config.context_safety_tokens),
        )

    def protect_payload(
        self, payload: Mapping[str, Any]
    ) -> tuple[dict[str, Any], tuple[ToolProtection, ...]]:
        """Return a backend-facing copy with oversized tool results protected.

        The caller's original request object is never mutated.  The proxy does
        not delete or persist the full result; it places a clear handoff marker
        in the copy sent to the model so a higher layer can store/summarize it.
        """
        protected = copy.deepcopy(dict(payload))
        protections: list[ToolProtection] = []

        messages = protected.get("messages")
        if not isinstance(messages, list):
            return protected, ()

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", ""))
            content = message.get("content")

            if role == "tool":
                new_content = self._protect_content(
                    content, default_kind="tool_result", protections=protections
                )
                message["content"] = new_content
            elif role == "user" and isinstance(content, str) and _looks_like_agent_result(content):
                new_content = self._protect_one(
                    content, kind="agent_result", protections=protections
                )
                message["content"] = new_content
            elif isinstance(content, list):
                # Keep this path for callers that use the Governor directly on
                # Anthropic-shaped messages before conversion.
                for part in content:
                    if not isinstance(part, dict) or part.get("type") != "tool_result":
                        continue
                    part["content"] = self._protect_content(
                        part.get("content"),
                        default_kind="agent_result" if _looks_like_agent_result(_as_text(part.get("content"))) else "tool_result",
                        protections=protections,
                    )

        return protected, tuple(protections)

    def _protect_content(
        self,
        content: Any,
        *,
        default_kind: str,
        protections: list[ToolProtection],
    ) -> Any:
        if isinstance(content, str):
            kind = "agent_result" if _looks_like_agent_result(content) else default_kind
            return self._protect_one(content, kind=kind, protections=protections)
        if isinstance(content, list):
            return [
                self._protect_content(item, default_kind=default_kind, protections=protections)
                if isinstance(item, (str, list, dict))
                else item
                for item in content
            ]
        if isinstance(content, dict):
            copied = dict(content)
            if "text" in copied:
                copied["text"] = self._protect_one(
                    _as_text(copied["text"]), kind=default_kind, protections=protections
                )
            elif "content" in copied:
                copied["content"] = self._protect_content(
                    copied["content"], default_kind=default_kind, protections=protections
                )
            return copied
        return content

    def _protect_one(
        self,
        value: str,
        *,
        kind: str,
        protections: list[ToolProtection],
    ) -> str:
        char_limit = self.config.max_tool_result_chars
        if kind == "agent_result":
            char_limit = min(char_limit, self.config.max_agent_return_tokens * 4)
        protected, changed = _protected_text(value, kind=kind, limit=char_limit)
        if changed:
            protections.append(ToolProtection(kind, len(value), len(protected)))
        return protected

    def prepare(
        self,
        payload: Mapping[str, Any],
        *,
        request_id: str,
        requested_generation_tokens: Any = None,
        max_tokens_explicit: bool | None = None,
    ) -> tuple[dict[str, Any], ContextDecision]:
        """Protect, count, validate, and clamp a backend payload."""
        protected, protections = self.protect_payload(payload)
        explicit = (
            "max_tokens" in protected
            if max_tokens_explicit is None
            else max_tokens_explicit
        )
        requested_value = (
            protected.get("max_tokens")
            if requested_generation_tokens is None
            else requested_generation_tokens
        )
        if not explicit:
            requested = DEFAULT_MAX_TOKENS
        else:
            if isinstance(requested_value, bool):
                raise InvalidGenerationBudget(
                    request_id=request_id, field="max_tokens", value=requested_value
                )
            try:
                requested = int(requested_value)
            except (TypeError, ValueError):
                raise InvalidGenerationBudget(
                    request_id=request_id, field="max_tokens", value=requested_value
                ) from None
            if requested <= 0:
                raise InvalidGenerationBudget(
                    request_id=request_id, field="max_tokens", value=requested_value
                )

        raw_reasoning = protected.get("reasoning_budget", 0)
        if isinstance(raw_reasoning, bool):
            raise InvalidGenerationBudget(
                request_id=request_id, field="reasoning_budget", value=raw_reasoning
            )
        try:
            reasoning_budget = max(0, int(raw_reasoning or 0))
        except (TypeError, ValueError):
            raise InvalidGenerationBudget(
                request_id=request_id, field="reasoning_budget", value=raw_reasoning
            ) from None
        if raw_reasoning is not None and reasoning_budget != int(raw_reasoning or 0):
            raise InvalidGenerationBudget(
                request_id=request_id, field="reasoning_budget", value=raw_reasoning
            )

        # The callback must perform exact provider-side rendered tokenization;
        # tokenizer failures intentionally propagate as fail-closed errors.
        prompt_tokens = int(self.rendered_prompt_counter(protected, request_id))
        if prompt_tokens < 0:
            raise ValueError("rendered prompt token count cannot be negative")

        effective_limit = self.effective_context_limit
        available = effective_limit - prompt_tokens - reasoning_budget
        if prompt_tokens >= effective_limit or available < self.config.min_generation_tokens:
            raise ContextWindowExceeded(
                request_id=request_id,
                prompt_tokens=prompt_tokens,
                hard_limit=self.config.context_hard_limit,
                effective_context_limit=effective_limit,
                backend_context_tokens=self.config.backend_context_tokens,
                context_safety_tokens=self.config.context_safety_tokens,
                reasoning_budget=reasoning_budget,
            )

        allowed = min(requested, available)
        protected["max_tokens"] = allowed

        breakdown: Mapping[str, Any] = {}
        if self.config.context_debug and self.breakdown_counter is not None:
            breakdown = dict(self.breakdown_counter(protected, request_id))

        decision = ContextDecision(
            request_id=request_id,
            prompt_tokens=prompt_tokens,
            requested_generation_tokens=requested,
            allowed_generation_tokens=allowed,
            hard_limit=self.config.context_hard_limit,
            effective_context_limit=effective_limit,
            backend_context_tokens=self.config.backend_context_tokens,
            reasoning_budget=reasoning_budget,
            available_generation_tokens=available,
            breakdown=breakdown,
            protections=protections,
        )
        self._log_decision(decision)
        return protected, decision

    def _log_decision(self, decision: ContextDecision) -> None:
        if decision.allowed_generation_tokens != decision.requested_generation_tokens:
            self.logger(
                f"[context-guard] request_id={decision.request_id} "
                f"prompt_tokens={decision.prompt_tokens}, "
                f"requested={decision.requested_generation_tokens}, "
                f"clamped_max_tokens={decision.allowed_generation_tokens}, "
                f"hard_limit={decision.hard_limit}, "
                f"effective_limit={decision.effective_context_limit}, "
                f"backend_context={decision.backend_context_tokens}, "
                f"reasoning_budget={decision.reasoning_budget}"
            )

        if decision.protections:
            details = ",".join(
                f"{item.kind}:{item.original_chars}->{item.protected_chars}"
                for item in decision.protections
            )
            self.logger(
                f"[context-guard] request_id={decision.request_id} "
                f"protected_tool_results={details}"
            )

        if self.config.context_debug:
            breakdown = dict(decision.breakdown)
            self.logger(
                f"[context-debug] request_id={decision.request_id} "
                f"raw_messages_tokens={breakdown.get('raw_messages_tokens', 0)} "
                f"rendered_prompt_tokens={decision.prompt_tokens} "
                f"system_tokens={breakdown.get('system_tokens', 0)} "
                f"tools_tokens={breakdown.get('tools_tokens', 0)} "
                f"user_tokens={breakdown.get('user_tokens', 0)} "
                f"assistant_tokens={breakdown.get('assistant_tokens', 0)} "
                f"estimated_generation_budget={decision.allowed_generation_tokens}"
            )
