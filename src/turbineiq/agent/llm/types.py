"""Provider-neutral messages and replies for the bounded assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class LLMToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: tuple[LLMToolCall, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LLMReply:
    text: str
    tool_calls: tuple[LLMToolCall, ...] = field(default_factory=tuple)


class LLMAdapter(Protocol):
    def complete(
        self,
        *,
        messages: list[LLMMessage],
        instructions: str,
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        parallel_tool_calls: bool,
    ) -> LLMReply: ...
