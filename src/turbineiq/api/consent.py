"""Server-side cloud consent and a local audit trail of cloud requests.

Cloud mode sends data to a third party, so the API must not rely on the browser
having shown a consent sheet. A grant is created only by an explicit call to
``POST /api/assistant/consent`` and is bound to the provider, model, host and
whether document excerpts may be sent. It expires, can be revoked, and stops
working if the provider configuration changes. Cloud requests carry the grant's
token; requests without a valid one are refused before any provider call.

This hardens the API against web pages and stale clients. A process already
running on the same machine can still call the consent endpoint, which is the
same trust level as reading the local ``.env`` file.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

DEFAULT_TTL_SECONDS = 30 * 60
MAX_GRANTS = 64


@dataclass(frozen=True)
class ConsentScope:
    provider: str
    model: str
    host: str


@dataclass(frozen=True)
class _Grant:
    scope: ConsentScope
    include_documents: bool
    expires_at: float


class ConsentRegistry:
    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_grants: int = MAX_GRANTS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_grants = max_grants
        self.clock = clock
        self._grants: dict[str, _Grant] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _prune(self, now: float) -> None:
        for key in [k for k, grant in self._grants.items() if grant.expires_at <= now]:
            del self._grants[key]
        while len(self._grants) >= self.max_grants:
            oldest = min(self._grants, key=lambda k: self._grants[k].expires_at)
            del self._grants[oldest]

    def grant(self, scope: ConsentScope, *, include_documents: bool) -> tuple[str, int]:
        """Create a grant and return ``(token, seconds_until_expiry)``."""

        token = secrets.token_urlsafe(32)
        now = self.clock()
        with self._lock:
            self._prune(now)
            self._grants[self._key(token)] = _Grant(
                scope=scope,
                include_documents=include_documents,
                expires_at=now + self.ttl_seconds,
            )
        return token, int(self.ttl_seconds)

    def check(
        self, token: str | None, scope: ConsentScope, *, need_documents: bool
    ) -> str | None:
        """Return ``None`` when the token authorises the request, else a reason code."""

        if not token:
            return "consent_required"
        now = self.clock()
        with self._lock:
            grant = self._grants.get(self._key(token))
            if grant is None or grant.expires_at <= now:
                return "consent_required"
            if not hmac.compare_digest(
                repr(grant.scope).encode("utf-8"), repr(scope).encode("utf-8")
            ):
                return "consent_scope_changed"
            if need_documents and not grant.include_documents:
                return "document_consent_required"
        return None

    def revoke(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            return self._grants.pop(self._key(token), None) is not None

    def clear(self) -> None:
        with self._lock:
            self._grants.clear()


CONSENT_MESSAGES = {
    "consent_required": (
        "Cloud mode needs your confirmation. Review the Cloud sharing sheet and continue "
        "to enable it."
    ),
    "consent_scope_changed": (
        "The provider or model changed since you confirmed Cloud sharing. Review and confirm again."
    ),
    "document_consent_required": (
        "Document excerpts were not approved. Enable the document option in the Cloud "
        "sharing sheet and confirm again."
    ),
}


class CloudAuditLog:
    """Bounded in-memory record of each cloud request: where it went and what scope."""

    def __init__(self, maxlen: int = 50) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(
        self,
        *,
        scope: ConsentScope,
        documents_allowed: bool,
        mode: str,
        tool_names: list[str],
        question_chars: int,
    ) -> dict[str, Any]:
        entry = {
            "time_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "provider": scope.provider,
            "model": scope.model,
            "host": scope.host,
            "documents_allowed": documents_allowed,
            "outcome": mode,
            "tools_used": tool_names,
            "question_chars": question_chars,
        }
        with self._lock:
            self._entries.append(entry)
        return entry

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(reversed(self._entries))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
