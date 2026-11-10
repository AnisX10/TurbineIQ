"""Adapters for OpenAI Responses and OpenAI-compatible Chat Completions."""

from __future__ import annotations

from typing import Any

from .types import LLMMessage, LLMReply, LLMToolCall


class ChatCompletionsAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def complete(
        self,
        *,
        messages: list[LLMMessage],
        instructions: str,
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        parallel_tool_calls: bool,
    ) -> LLMReply:
        chat_messages: list[dict[str, Any]] = [{"role": "system", "content": instructions}]
        for message in messages:
            if message.role == "tool":
                chat_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": message.content,
                    }
                )
            elif message.role == "assistant" and message.tool_calls:
                chat_messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or None,
                        "tool_calls": [
                            {
                                "id": call.call_id,
                                "type": "function",
                                "function": {"name": call.name, "arguments": call.arguments},
                            }
                            for call in message.tool_calls
                        ],
                    }
                )
            else:
                chat_messages.append({"role": message.role, "content": message.content})

        request: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "parallel_tool_calls": parallel_tool_calls,
        }
        if tools:
            request["tools"] = [_chat_tool_schema(tool) for tool in tools]
            request["tool_choice"] = "auto"
        result = self.client.chat.completions.create(**request)
        choices = getattr(result, "choices", None) or []
        if not choices:
            return LLMReply(text="")
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        text = content if isinstance(content, str) else ""
        calls: list[LLMToolCall] = []
        for call in getattr(message, "tool_calls", None) or []:
            function = getattr(call, "function", None)
            if function is None:
                continue
            calls.append(
                LLMToolCall(
                    call_id=str(getattr(call, "id", "")),
                    name=str(getattr(function, "name", "")),
                    arguments=str(getattr(function, "arguments", "")),
                )
            )
        return LLMReply(text=text, tool_calls=tuple(calls))


class ResponsesAdapter:
    def __init__(self, client: Any) -> None:
        self.client = client

    def complete(
        self,
        *,
        messages: list[LLMMessage],
        instructions: str,
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        parallel_tool_calls: bool,
    ) -> LLMReply:
        input_items: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "tool":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )
            elif message.role == "assistant" and message.tool_calls:
                if message.content:
                    input_items.append({"role": "assistant", "content": message.content})
                input_items.extend(
                    {
                        "type": "function_call",
                        "call_id": call.call_id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in message.tool_calls
                )
            else:
                input_items.append({"role": message.role, "content": message.content})
        request: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input_items,
            "tools": tools,
            "parallel_tool_calls": parallel_tool_calls,
            "store": False,
            "max_output_tokens": max_tokens,
        }
        response = self.client.responses.create(**request)
        calls: list[LLMToolCall] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) == "function_call":
                calls.append(
                    LLMToolCall(
                        call_id=str(getattr(item, "call_id", "")),
                        name=str(getattr(item, "name", "")),
                        arguments=str(getattr(item, "arguments", "")),
                    )
                )
        return LLMReply(
            text=str(getattr(response, "output_text", "") or ""),
            tool_calls=tuple(calls),
        )


def _chat_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    if isinstance(tool.get("function"), dict):
        return tool
    function: dict[str, Any] = {
        "name": tool.get("name", ""),
        "description": tool.get("description", ""),
        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
    }
    if tool.get("strict") is True:
        function["strict"] = True
    return {"type": "function", "function": function}
