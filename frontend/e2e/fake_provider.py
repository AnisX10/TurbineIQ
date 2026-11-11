"""Local OpenAI-compatible fake used by browser tests only."""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length))
        messages = request.get("messages", [])
        question = next(
            (item.get("content", "") for item in messages if item.get("role") == "user"),
            "",
        )
        if "force fallback" in question.casefold():
            error_body = b'{"error":{"message":"fake rate limit"}}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(error_body)
            return
        if "slow response" in question.casefold():
            time.sleep(8 if "for capture" in question.casefold() else 2)

        tool_output = next(
            (item.get("content", "") for item in reversed(messages) if item.get("role") == "tool"),
            None,
        )
        if tool_output is None:
            function_name = "search_technical_documents" if request.get("tools") and "citation" in question.casefold() else "inspect_synthetic_twin_snapshot"
            arguments = json.dumps({"query": question}) if function_name == "search_technical_documents" else "{}"
            message: dict[str, Any] = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "fake_call_1",
                        "type": "function",
                        "function": {"name": function_name, "arguments": arguments},
                    }
                ],
            }
            finish_reason = "tool_calls"
        else:
            try:
                data = json.loads(tool_output)
            except json.JSONDecodeError:
                try:
                    data = json.loads(tool_output[tool_output.index("{"):tool_output.rindex("}") + 1])
                except (ValueError, json.JSONDecodeError):
                    data = {}
            snapshot = data.get("snapshot", {})
            ref_mw = float(snapshot.get("model_electrical_power_kw", 0)) / 1000
            observation_mw = float(snapshot.get("synthetic_observed_power_kw", 0)) / 1000
            residual_kw = float(snapshot.get("power_residual_kw", 0))
            evidence = data.get("evidence", [])
            if evidence:
                citation = evidence[0].get("citation", "")
                answer = f"The local evidence search returned supporting passage {citation}."
            else:
                answer = (
                    f"The selected synthetic sample has {ref_mw:.2f} MW reference output, "
                    f"{observation_mw:.2f} MW generated observation, and {residual_kw:.1f} kW residual."
                )
            message = {"role": "assistant", "content": answer}
            finish_reason = "stop"

        body = json.dumps({
            "id": "fake-chat-completion",
            "object": "chat.completion",
            "created": 1,
            "model": request.get("model", "fake-gpt-oss"),
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8022), Handler).serve_forever()
