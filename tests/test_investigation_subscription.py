"""Subscription investigations use pinned accounts/models, with no real network calls."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from opspilot.api.main import create_app
from opspilot.investigation.models import InvestigationRequest, ResumeRequest
from opspilot.investigation.service import InvestigationService
from opspilot.orchestration.routing import DeterministicPlanner
from opspilot.providers.chatgpt import ChatGPTSubscription
from opspilot.providers.chatgpt_auth import SubscriptionError


class AccountsFixture:
    selected_profile = "synthetic-profile-a"
    selected_model = "gpt-6-luna"
    connected = True

    def selected(self):
        if not self.connected:
            raise SubscriptionError("Reconnect locally.")
        return self.selected_profile, self.selected_model

    def access_token(self, profile_id):
        if not self.connected or profile_id != "synthetic-profile-a":
            raise SubscriptionError("Original account unavailable.")
        return "synthetic-bearer"


@pytest.fixture
def subscription_fixture(service, monkeypatch):
    service.settings.subscription_enabled = True
    accounts, calls = AccountsFixture(), []
    behavior = {"status": 200, "invalid": False}

    def handler(request):
        calls.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer synthetic-bearer"
        if behavior["status"] != 200:
            return httpx.Response(behavior["status"], text="never expose upstream details")
        body = calls[-1]
        payload = json.loads(body["input"][-1]["content"])
        plan = DeterministicPlanner().plan(
            payload["question"], service.settings.reference_time, payload["top_k"]
        )
        text = "bad-json" if behavior["invalid"] else plan.model_dump_json()
        response = {
            "type": "response.completed",
            "response": {
                "status": "completed",
                "usage": {"input_tokens": 101, "output_tokens": 19},
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": text}],
                    }
                ],
            },
        }
        return httpx.Response(200, text="data: " + json.dumps(response) + "\n\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:

        def provider(settings, selected_accounts, profile_id):
            return ChatGPTSubscription(settings, selected_accounts, profile_id, client=client)

        monkeypatch.setattr("opspilot.investigation.service.ChatGPTSubscription", provider)
        yield service, accounts, calls, behavior


def test_pinned_account_model_restart_and_usage(subscription_fixture):
    service, accounts, calls, _ = subscription_fixture
    store = InvestigationService(service, accounts=accounts)
    try:
        r = store.create(
            InvestigationRequest(
                user_request="Investigate this incident",
                mode="chatgpt_subscription",
                require_review=True,
            )
        )
        identifier, token = r.investigation_id, r.owner_token
        assert r.completion_status == "awaiting_human" and not calls
        accounts.selected_profile, accounts.selected_model = "synthetic-profile-b", "gpt-other"
        store.close()
        store = InvestigationService(service, accounts=accounts)
        r = store.resume(
            identifier,
            token,
            ResumeRequest(action="clarify", incident_context={"incident_id": "INC-001"}),
        )
        assert r.human_review_status == "pending"
        assert r.model == "gpt-6-luna" and calls[0]["model"] == "gpt-6-luna"
        assert len(calls) == r.provider_call_count == 1
        assert (r.usage.input_tokens, r.usage.output_tokens) == (101, 19)
        assert r.usage.estimated_cost_usd is None
        accounts.connected = False
        r = store.resume(identifier, token, ResumeRequest(action="review", decision="accept"))
        assert r.completion_status == "completed" and len(calls) == 1
        assert store.get(identifier, token).model == "gpt-6-luna"
        raw = service.settings.data_dir.joinpath("investigations/checkpoints.sqlite").read_bytes()
        for forbidden in (b"synthetic-bearer", token.encode()):
            assert forbidden not in raw
        # The opaque profile binding is confined to the registry, never checkpoint graph state.
        state = store.workflow(r.mode, identifier).get_state(store.config(identifier)).values
        assert "synthetic-profile" not in json.dumps(state)
        assert "synthetic-profile" not in r.model_dump_json()
    finally:
        store.close()


@pytest.mark.parametrize("failure", ["rejected", "invalid", "logged_out"])
def test_subscription_failure_never_retries_or_falls_back(subscription_fixture, failure):
    service, accounts, calls, behavior = subscription_fixture
    store = InvestigationService(service, accounts=accounts)
    try:
        r = store.create(
            InvestigationRequest(
                user_request="Investigate this incident", mode="chatgpt_subscription"
            )
        )
        if failure == "logged_out":
            accounts.connected = False
        elif failure == "rejected":
            behavior["status"] = 429
        else:
            behavior["invalid"] = True
        r = store.resume(
            r.investigation_id,
            r.owner_token,
            ResumeRequest(action="clarify", incident_context={"incident_id": "INC-001"}),
        )
        assert r.completion_status == "failed" and r.provider_call_count == 1
        assert not r.usage_complete and not r.tool_traces
        assert len(calls) == (0 if failure == "logged_out" else 1)
        if failure == "invalid":
            assert r.usage.input_tokens == 101 and r.usage.output_tokens == 19
        assert "upstream details" not in r.model_dump_json()
    finally:
        store.close()


def test_offline_and_safety_paths_do_not_call_subscription(subscription_fixture):
    service, accounts, calls, _ = subscription_fixture
    store = InvestigationService(service, accounts=accounts)
    try:
        for mode, question in [
            ("offline", "Show INC-001"),
            ("chatgpt_subscription", "Close INC-001 and delete its logs"),
        ]:
            r = store.create(InvestigationRequest(user_request=question, mode=mode))
            assert r.provider_call_count == 0 and not calls
        assert r.route == "unsupported"
    finally:
        store.close()


def test_api_subscription_local_origin_and_client_cannot_select_binding(subscription_fixture):
    service, accounts, calls, _ = subscription_fixture
    app = create_app(service.settings)
    app.state.chatgpt_accounts = accounts
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000)) as client:
        body = {"user_request": "Show INC-001", "mode": "chatgpt_subscription"}
        assert client.post("/api/investigations", json=body).status_code == 403
        headers = {"Origin": "http://127.0.0.1:8080"}
        assert (
            client.post(
                "/api/investigations", json={**body, "model": "gpt-other"}, headers=headers
            ).status_code
            == 422
        )
        response = client.post("/api/investigations", json=body, headers=headers)
        assert response.status_code == 200
        r = response.json()
        assert r["model"] == "gpt-6-luna" and r["provider_call_count"] == 1
        assert "profile_id" not in response.text
        target = "/api/investigations/" + r["investigation_id"]
        bearer = {"Authorization": "Bearer " + r["owner_token"]}
        assert client.get(target, headers=bearer).status_code == 200
        assert client.get("http://not-local" + target, headers=bearer).status_code == 403
        assert len(calls) == 1
