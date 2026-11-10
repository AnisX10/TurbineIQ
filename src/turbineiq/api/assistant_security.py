"""Small in-process protections for assistant API requests and logs."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

MAX_ASSISTANT_REQUEST_BYTES = 64 * 1024

_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|token|key)\s*[:=]\s*)[^\s,;&]+"),
    re.compile(r"(?i)(https?://[^:/\s]+:)[^@/\s]+(@)"),
    re.compile(r"\b(?:sk-or-v1-|sk-|gsk_|csk-|hf_)[A-Za-z0-9_-]{8,}\b"),
)


class TokenBucketLimiter:
    def __init__(
        self,
        *,
        capacity: float = 30,
        refill_per_second: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def consume(self, client_key: str, amount: float = 1) -> bool:
        now = self.clock()
        with self._lock:
            tokens, updated = self._buckets.get(client_key, (self.capacity, now))
            tokens = min(self.capacity, tokens + max(0.0, now - updated) * self.refill_per_second)
            if tokens < amount:
                self._buckets[client_key] = (tokens, now)
                return False
            self._buckets[client_key] = (tokens - amount, now)
            return True

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = MAX_ASSISTANT_REQUEST_BYTES) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = str(scope.get("path", ""))
        if scope["type"] != "http" or not path.startswith("/api/assistant"):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length", b"")
        try:
            if raw_length and int(raw_length) > self.limit:
                await _send_too_large(send)
                return
        except ValueError:
            await _send_too_large(send)
            return

        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.limit:
                    await _send_too_large(send)
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break

        body = b"".join(chunks)
        delivered = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, replay_receive, send)


async def _send_too_large(send: Send) -> None:
    payload = json.dumps({"detail": "Assistant request body is too large."}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class SecretRedactionFilter(logging.Filter):
    """Redact common API key shapes before a log record is formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        for pattern in _SECRET_PATTERNS:
            if pattern.groups:
                message = pattern.sub(r"\1[REDACTED]", message)
            else:
                message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def install_secret_redaction_filter() -> None:
    redactor = SecretRedactionFilter()
    loggers = (
        logging.getLogger(),
        logging.getLogger("uvicorn"),
        logging.getLogger("uvicorn.access"),
        logging.getLogger("uvicorn.error"),
    )
    for logger in loggers:
        if redactor not in logger.filters:
            logger.addFilter(redactor)
        for handler in logger.handlers:
            if redactor not in handler.filters:
                handler.addFilter(redactor)
