import logging

import pytest
from fastapi.testclient import TestClient

from turbineiq.agent import TurbineAssistant
from turbineiq.agent.llm import LLMReply, LLMSettings
from turbineiq.api import main as api_main
from turbineiq.api.consent import ConsentRegistry, ConsentScope

SCOPE = ConsentScope(provider="groq", model="gpt-oss", host="api.groq.com")
ASK = "/api/assistant/ask"


class RecordingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, **_kwargs) -> LLMReply:
        self.calls += 1
        return LLMReply("A cloud answer.")


@pytest.fixture()
def cloud(monkeypatch):
    adapter = RecordingAdapter()
    settings = LLMSettings(
        provider="groq",
        api_key="server-only-secret",
        model="gpt-oss",
        base_url="https://api.groq.com/openai/v1",
    )
    monkeypatch.setattr(
        api_main, "assistant", TurbineAssistant(cloud_settings=settings, adapter=adapter)
    )
    monkeypatch.setattr(api_main, "_status_cache", None)
    api_main.assistant_rate_limiter.clear()
    api_main.consent_registry.clear()
    api_main.cloud_audit_log.clear()
    return TestClient(api_main.app), adapter


def grant(client: TestClient, *, include_documents: bool = False) -> dict:
    response = client.post("/api/assistant/consent", json={"include_documents": include_documents})
    assert response.status_code == 200
    return response.json()


def test_cloud_request_without_consent_is_refused_before_any_provider_call(cloud) -> None:
    client, adapter = cloud

    response = client.post(ASK, json={"question": "Calculate output", "enable_cloud": True})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_required"
    assert adapter.calls == 0


def test_cloud_request_with_unknown_token_is_refused(cloud) -> None:
    client, adapter = cloud

    response = client.post(
        ASK,
        json={"question": "Calculate output", "enable_cloud": True, "consent_token": "forged"},
    )

    assert response.status_code == 403
    assert adapter.calls == 0


def test_granted_consent_allows_cloud_and_names_the_destination(cloud) -> None:
    client, adapter = cloud
    consent = grant(client)

    assert consent["provider"] == "groq"
    assert consent["base_url_host"] == "api.groq.com"
    assert consent["include_documents"] is False
    assert "server-only-secret" not in str(consent)

    response = client.post(
        ASK,
        json={
            "question": "Calculate output",
            "enable_cloud": True,
            "consent_token": consent["consent_token"],
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "cloud"
    assert adapter.calls == 1


def test_local_mode_never_needs_consent(cloud) -> None:
    client, adapter = cloud

    response = client.post(ASK, json={"question": "Calculate the turbine output."})

    assert response.status_code == 200
    assert response.json()["mode"] == "local"
    assert adapter.calls == 0


def test_document_excerpts_need_their_own_consent(cloud) -> None:
    client, adapter = cloud
    without_documents = grant(client)
    body = {
        "question": "Find a citation",
        "enable_cloud": True,
        "allow_cloud_document_context": True,
    }

    refused = client.post(ASK, json={**body, "consent_token": without_documents["consent_token"]})
    with_documents = grant(client, include_documents=True)
    allowed = client.post(ASK, json={**body, "consent_token": with_documents["consent_token"]})

    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "document_consent_required"
    assert allowed.status_code == 200
    assert adapter.calls == 1


def test_stream_endpoint_enforces_consent_too(cloud) -> None:
    client, adapter = cloud

    response = client.post(
        "/api/assistant/stream", json={"question": "Calculate output", "enable_cloud": True}
    )

    assert response.status_code == 403
    assert adapter.calls == 0


def test_consent_stops_working_when_the_provider_changes(cloud, monkeypatch) -> None:
    client, adapter = cloud
    consent = grant(client)
    other = LLMSettings(
        provider="openrouter",
        api_key="k",
        model="other-model",
        base_url="https://openrouter.ai/api/v1",
    )
    monkeypatch.setattr(
        api_main, "assistant", TurbineAssistant(cloud_settings=other, adapter=adapter)
    )

    response = client.post(
        ASK,
        json={
            "question": "Calculate output",
            "enable_cloud": True,
            "consent_token": consent["consent_token"],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "consent_scope_changed"
    assert adapter.calls == 0


def test_revoked_consent_is_refused(cloud) -> None:
    client, adapter = cloud
    token = grant(client)["consent_token"]

    assert client.post("/api/assistant/consent/revoke", json={"consent_token": token}).json() == {
        "revoked": True
    }
    response = client.post(
        ASK, json={"question": "Calculate output", "enable_cloud": True, "consent_token": token}
    )

    assert response.status_code == 403
    assert adapter.calls == 0


def test_every_cloud_request_is_audited_without_content(cloud, caplog) -> None:
    client, _adapter = cloud
    token = grant(client)["consent_token"]
    caplog.set_level(logging.INFO, logger="turbineiq.audit")

    client.post(
        ASK,
        json={"question": "Calculate output", "enable_cloud": True, "consent_token": token},
    )
    client.post(ASK, json={"question": "Local question only"})
    entries = client.get("/api/assistant/audit").json()["entries"]

    assert len(entries) == 1
    assert entries[0]["host"] == "api.groq.com"
    assert entries[0]["outcome"] == "cloud"
    assert entries[0]["question_chars"] == len("Calculate output")
    assert "Calculate output" not in str(entries[0])
    assert "host=api.groq.com" in caplog.text


def test_registry_expires_grants_and_bounds_their_number() -> None:
    now = [0.0]
    registry = ConsentRegistry(ttl_seconds=10, max_grants=2, clock=lambda: now[0])
    first, _ = registry.grant(SCOPE, include_documents=False)

    assert registry.check(first, SCOPE, need_documents=False) is None
    now[0] = 11
    assert registry.check(first, SCOPE, need_documents=False) == "consent_required"

    tokens = [registry.grant(SCOPE, include_documents=False)[0] for _ in range(3)]
    assert registry.check(tokens[0], SCOPE, need_documents=False) == "consent_required"
    assert registry.check(tokens[2], SCOPE, need_documents=False) is None


def test_requests_for_other_hosts_are_refused() -> None:
    client = TestClient(api_main.app)

    rebound = client.get("/api/health", headers={"Host": "attacker.example"})

    assert rebound.status_code == 400
    assert client.get("/api/health", headers={"Host": "localhost:8000"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "127.0.0.1:5173"}).status_code == 200


def test_cross_origin_api_requests_are_refused_even_when_simple() -> None:
    client = TestClient(api_main.app)
    api_main.assistant_rate_limiter.clear()

    hostile = client.post(
        "/api/assistant/consent",
        content="{}",
        headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
    )
    local = client.post(
        "/api/assistant/consent", json={}, headers={"Origin": "http://localhost:5173"}
    )

    assert hostile.status_code == 403
    assert local.status_code == 200
