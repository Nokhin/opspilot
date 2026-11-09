import base64
import hashlib
import json
import stat
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from opspilot.api.main import create_app
from opspilot.domain.models import RoutePlan
from opspilot.orchestration.service import OpsPilotService
from opspilot.providers.chat_api import ProviderError
from opspilot.providers.chatgpt import ChatGPTSubscription
from opspilot.providers.chatgpt_auth import (
    API,
    ISSUER,
    PLAN_SCOPE,
    ChatGPTAccounts,
    SubscriptionError,
)


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def connect(accounts, signing_key, *, claims=None, scope=PLAN_SCOPE, profile_id=None):
    url = accounts.start_login("http://127.0.0.1:8080/auth/callback", "browser", profile_id)
    query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    client_id = query["client_id"]
    if client_id == "dynamic_agent_client":
        client_id = "oaiapp_" + query["state"][:10]
    identity = {
        "iss": ISSUER,
        "aud": client_id,
        "sub": "synthetic-account",
        "email": "operator@example.test",
        "nonce": query["nonce"],
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        **(claims or {}),
    }
    token = jwt.encode(identity, signing_key, algorithm="RS256", headers={"kid": "test-key"})
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    jwk["kid"] = "test-key"

    def handler(request):
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json={"keys": [jwk]})
        body = parse_qs(request.content.decode())
        assert body["client_id"] == [client_id]
        assert body["resource"] == [API]
        assert body["redirect_uri"] == [query["redirect_uri"]]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(body["code_verifier"][0].encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        assert challenge == query["code_challenge"]
        assert "client_secret" not in body
        return httpx.Response(
            200,
            json={
                "id_token": token,
                "access_token": "opaque-access",
                "refresh_token": "opaque-refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": scope,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        accounts.client = client
        enabled = accounts.finish_login(
            {
                "state": query["state"],
                "code": "one-time-code",
                "client_id": client_id,
            },
            "browser",
        )
    accounts.client = None
    return query, enabled


def catalog(request):
    assert request.url == API + "/models"
    assert request.headers["authorization"] == "Bearer opaque-access"
    return httpx.Response(
        200,
        json={
            "models": [
                {"slug": "gpt-test", "display_name": "Available GPT", "visibility": "list"},
                {"slug": "gpt-hidden", "display_name": "Hidden GPT", "visibility": "hidden"},
                {"slug": "gpt-second", "display_name": "Second GPT", "visibility": "list"},
            ]
        },
    )


def test_oauth_pkce_identity_permissions_and_private_persistence(tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    query, enabled = connect(accounts, signing_key)
    assert query["client_id"] == "dynamic_agent_client"
    assert query["agent_name_hint"] == "OpsPilot" and enabled
    assert query["ext_agent_host_id"].startswith("urn:uuid:")
    assert {"openid", "offline_access", "resource.invoke", PLAN_SCOPE} <= set(
        query["scope"].split()
    )
    assert stat.S_IMODE(accounts.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(accounts.directory.stat().st_mode) == 0o700
    state = accounts.status()
    assert "opaque-" not in json.dumps(state) and "id_token" not in json.dumps(state)
    restarted = ChatGPTAccounts(tmp_path)
    assert restarted.status() == state
    returning = parse_qs(
        urlsplit(
            restarted.start_login(query["redirect_uri"], "other-browser", state["active"])
        ).query
    )
    assert returning["client_id"][0] != "dynamic_agent_client"
    assert returning["ext_agent_host_id"] == [query["ext_agent_host_id"]]
    assert "agent_name_hint" not in returning and "id_token_hint" not in returning
    with pytest.raises(SubscriptionError):
        accounts.finish_login({"state": query["state"], "code": "replayed"}, "browser")


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://example.test"},
        {"aud": "another-client"},
        {"exp": 1},
        {"nonce": "wrong-nonce"},
        {"sub": ""},
    ],
)
def test_bad_id_token_never_activates_profile(tmp_path, signing_key, claims):
    accounts = ChatGPTAccounts(tmp_path)
    with pytest.raises(SubscriptionError, match="verification"):
        connect(accounts, signing_key, claims=claims)
    assert accounts.status()["active"] is None
    assert "opaque-access" not in accounts.path.read_text()


def test_bad_signature_is_rejected(tmp_path, signing_key, monkeypatch):
    decode = jwt.decode

    def invalid_signature(*args, **kwargs):
        kwargs["key"] = signing_key.public_key()
        return decode(args[0], **kwargs)

    monkeypatch.setattr("opspilot.providers.chatgpt_auth.jwt.decode", invalid_signature)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(SubscriptionError):
        connect(ChatGPTAccounts(tmp_path), other_key)


def test_missing_plan_consent_blocks_models_and_inference(tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    _, enabled = connect(accounts, signing_key, scope="openid profile email")
    assert not enabled
    with pytest.raises(SubscriptionError, match="Enable ChatGPT plan"):
        accounts.access_token(accounts.status()["active"])


def test_state_browser_binding_expiry_and_replay(tmp_path):
    accounts = ChatGPTAccounts(tmp_path)
    url = accounts.start_login("http://127.0.0.1:8080/auth/callback", "browser")
    state = parse_qs(urlsplit(url).query)["state"][0]
    for query, browser in [({"state": "wrong"}, "browser"), ({"state": state}, "other")]:
        with pytest.raises(SubscriptionError):
            accounts.finish_login(query, browser)
    accounts.pending[state]["expires"] = 1
    with pytest.raises(SubscriptionError):
        accounts.finish_login({"state": state, "code": "expired"}, "browser")


def test_models_selection_order_and_account_separation(tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    first = accounts.status()["active"]
    with httpx.Client(transport=httpx.MockTransport(catalog)) as client:
        accounts.client = client
        assert [m["id"] for m in accounts.models(first)] == ["gpt-test", "gpt-second"]
        with pytest.raises(SubscriptionError):
            accounts.select_model("gpt-hidden")
        accounts.select_model("gpt-second")
        assert accounts.selected() == (first, "gpt-second")
    connect(accounts, signing_key)
    second = accounts.status()["active"]
    assert second != first
    assert len(accounts.status()["profiles"]) == 2
    accounts.select_account(first)
    assert accounts.status()["profiles"][0]["model"] == "gpt-second"
    with pytest.raises(SubscriptionError):
        connect(accounts, signing_key, claims={"sub": "different-account"}, profile_id=first)
    assert accounts.status()["active"] == first


def test_refresh_rotates_credentials_and_lock_prevents_other_process(tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    data = accounts._read()
    profile_id = data["active"]
    data["profiles"][profile_id]["expires_at"] = 1
    accounts._write(data)
    calls = []

    def refresh(request):
        body = parse_qs(request.content.decode())
        calls.append(body)
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["opaque-refresh"]
        assert "scope" not in body
        return httpx.Response(
            200,
            json={
                "access_token": "rotated-access",
                "refresh_token": "rotated-refresh",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(refresh)) as client:
        accounts.client = client
        assert accounts.access_token(profile_id) == "rotated-access"
        assert accounts.access_token(profile_id) == "rotated-access"
    assert len(calls) == 1
    assert accounts._read()["profiles"][profile_id]["refresh_token"] == "rotated-refresh"
    with accounts.lock, pytest.raises(SubscriptionError, match="another local process"):
        ChatGPTAccounts(tmp_path).status()


@pytest.mark.parametrize("status", [200, 503])
def test_logout_revokes_or_reports_failure_and_keeps_registration(tmp_path, signing_key, status):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)

    def revoke(request):
        assert request.url.path.endswith("oauth/revoke")
        assert parse_qs(request.content.decode())["token_type_hint"] == ["refresh_token"]
        return httpx.Response(status)

    with httpx.Client(transport=httpx.MockTransport(revoke)) as client:
        accounts.client = client
        assert accounts.logout() == (status == 200)
    state = accounts.status()
    assert len(state["profiles"]) == 1 and not state["profiles"][0]["connected"]
    assert "opaque-" not in accounts.path.read_text()


def stream_events(*events):
    return "".join(
        "event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n" for event in events
    )


def completed(plan):
    return {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "usage": {"input_tokens": 31, "output_tokens": 12},
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": json.dumps(plan)},
                    ],
                }
            ],
        },
    }


def test_subscription_uses_responses_and_same_typed_executor(service, tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    profile = accounts.status()["active"]
    live = service.settings.model_copy(
        update={"llm_provider": "chatgpt_subscription", "llm_model": "gpt-test"}
    )
    plan = {
        "route": "data_only",
        "calls": [{"tool_name": "get_incident", "arguments": {"incident_id": "INC-001"}}],
    }

    def handler(request):
        assert request.url == API + "/responses"
        body = json.loads(request.content)
        assert body["store"] is False and body["stream"] is True
        assert body["model"] == "gpt-test" and isinstance(body["input"], list)
        assert body["input"][0]["role"] == "developer"
        assert "json" in body["input"][0]["content"].lower()
        assert body["input"][-1]["role"] == "user"
        assert request.extensions["timeout"]["read"] == 60
        assert "untrusted" in body["instructions"]
        assert not {"temperature", "max_tokens", "max_output_tokens", "tools"} & body.keys()
        return httpx.Response(200, text=stream_events(completed(plan)))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = OpsPilotService(live, ChatGPTSubscription(live, accounts, profile, client)).ask(
            "Show INC-001"
        )
    assert response.mode == "chatgpt_subscription" and response.model == "gpt-test"
    assert response.usage.input_tokens == 31 and response.usage.estimated_cost_usd is None
    assert response.tool_trace[0].tool_name == "get_incident"
    assert response.tool_trace[0].status == "success"


@pytest.mark.parametrize("terminal", ["response.failed", "response.incomplete", "error", None])
def test_partial_stream_never_becomes_an_answer(service, tmp_path, signing_key, terminal):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    events = [{"type": "response.output_text.delta", "delta": '{"route":"unsupported"}'}]
    if terminal:
        events.append({"type": terminal, "secret": "do-not-expose"})
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=stream_events(*events))
        )
    ) as client:
        provider = ChatGPTSubscription(
            service.settings, accounts, accounts.status()["active"], client
        )
        with pytest.raises(ProviderError) as error:
            provider.complete("JSON", {}, RoutePlan)
    assert "do-not-expose" not in str(error.value)


def test_untrusted_or_disabled_clients_cannot_use_subscription(settings, service):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/chatgpt/status").json() == {"enabled": False}
        assert client.post("/api/chatgpt/login", json={}).status_code == 404
        assert (
            client.post(
                "/api/chat", json={"question": "Show INC-001", "provider": "chatgpt_subscription"}
            ).status_code
            == 404
        )
    enabled = settings.model_copy(update={"subscription_enabled": True})
    app = create_app(enabled)
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/chatgpt/status").json()["enabled"]
        for origin in [None, "https://example.test"]:
            headers = {"Origin": origin} if origin else {}
            assert client.post("/api/chatgpt/login", json={}, headers=headers).status_code == 403
        assert (
            client.get("/api/chatgpt/status", headers={"Host": "example.test"}).status_code == 403
        )
        result = client.post(
            "/api/chatgpt/login", json={}, headers={"Origin": "http://127.0.0.1:8080"}
        )
        assert result.status_code == 200
        assert "HttpOnly" in result.headers["set-cookie"]
        assert result.headers["cache-control"] == "no-store"
        assert "127.0.0.1%3A8080%2Fauth%2Fcallback" in result.json()["authorization_url"]
        assert "id_token_hint" not in result.json()["authorization_url"]
        assert client.get("/auth/callback?code=private-code&state=wrong").status_code == 400
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("203.0.113.9", 40000)) as remote:
        assert remote.get("/api/chatgpt/status").status_code == 403


def test_symlink_credentials_are_rejected(tmp_path):
    (tmp_path / "chatgpt").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SubscriptionError):
        ChatGPTAccounts(tmp_path).status()


def test_http_failure_does_not_retry_or_leak_body(service, tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, json={"error": "do-not-expose"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = ChatGPTSubscription(
            service.settings, accounts, accounts.status()["active"], client
        )
        with pytest.raises(SubscriptionError, match="HTTP 429") as error:
            provider.plan("Show INC-001")
    assert len(requests) == 1
    assert "do-not-expose" not in str(error.value)


def test_forbidden_model_tool_plan_never_executes(service, tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    plan = {
        "route": "data_only",
        "calls": [
            {"tool_name": "execute_sql", "arguments": {"sql": "DELETE FROM incidents"}},
        ],
    }
    live = service.settings.model_copy(update={"llm_provider": "chatgpt_subscription"})
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=stream_events(completed(plan)))
        )
    ) as client:
        response = OpsPilotService(
            live, ChatGPTSubscription(live, accounts, accounts.status()["active"], client)
        ).ask("Show INC-001")
    assert response.confidence == "insufficient_evidence" and not response.tool_trace


def test_api_models_chat_default_mode_and_welcome(settings, service, signing_key, monkeypatch):
    enabled = settings.model_copy(update={"subscription_enabled": True})
    app = create_app(enabled)
    accounts = app.state.chatgpt_accounts
    connect(accounts, signing_key)
    profile = accounts.status()["active"]
    requests = []
    plan = {
        "route": "data_only",
        "calls": [
            {"tool_name": "get_incident", "arguments": {"incident_id": "INC-001"}},
        ],
    }

    def upstream(request):
        requests.append(request.url.path)
        if request.url.path.endswith("models"):
            return catalog(request)
        return httpx.Response(200, text=stream_events(completed(plan)))

    with httpx.Client(transport=httpx.MockTransport(upstream)) as transport:
        accounts.client = transport
        monkeypatch.setattr(
            "opspilot.api.main.ChatGPTSubscription",
            lambda config, store, pid: ChatGPTSubscription(config, store, pid, transport),
        )
        with TestClient(
            app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000)
        ) as client:
            headers = {"Origin": "http://127.0.0.1:8080"}
            result = client.post("/api/chat", json={"question": "Show INC-001"})
            assert result.json()["mode"] == "extractive" and not requests
            assert (
                client.post(
                    "/api/chatgpt/model", json={"model": "gpt-hidden"}, headers=headers
                ).status_code
                == 400
            )
            assert (
                client.post(
                    "/api/chatgpt/model", json={"model": "gpt-second"}, headers=headers
                ).status_code
                == 200
            )
            result = client.post(
                "/api/chat",
                json={"question": "Show INC-001", "provider": "chatgpt_subscription"},
                headers=headers,
            )
            assert result.status_code == 200 and result.json()["model"] == "gpt-second"
            assert result.json()["tool_trace"][0]["status"] == "success"
            assert client.post("/api/chatgpt/welcome", json={}, headers=headers).status_code == 200
            state = client.get("/api/chatgpt/status").json()
            assert state["active"] == profile and state["profiles"][0]["welcome_acknowledged"]
            assert "opaque-" not in json.dumps(state)


def test_successful_callback_consumes_cookie_and_redacts_query(settings, signing_key, monkeypatch):
    enabled = settings.model_copy(update={"subscription_enabled": True})
    app = create_app(enabled)
    accounts = app.state.chatgpt_accounts
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000)) as client:
        result = client.post(
            "/api/chatgpt/login", json={}, headers={"Origin": "http://127.0.0.1:8080"}
        )
        query = {
            k: v[0] for k, v in parse_qs(urlsplit(result.json()["authorization_url"]).query).items()
        }
        seen = []

        def finish(params, browser):
            assert params["code"] == "private-code" and params["state"] == query["state"]
            assert browser
            seen.append(params)
            return True

        monkeypatch.setattr(accounts, "finish_login", finish)
        response = client.get(
            "/auth/callback",
            params={"code": "private-code", "state": query["state"]},
            follow_redirects=False,
        )
        assert response.status_code == 303 and response.headers["location"] == "/"
        assert response.headers["referrer-policy"] == "no-referrer" and seen
        assert "private-code" not in response.text
        assert client.cookies.get("opspilot_oauth") is None


def test_refresh_losing_scope_stops_before_model_request(tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    data = accounts._read()
    profile = data["active"]
    data["profiles"][profile]["expires_at"] = 1
    accounts._write(data)
    requests = []

    def refresh(request):
        requests.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "access_token": "rotated-access",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(refresh)) as transport:
        accounts.client = transport
        with pytest.raises(SubscriptionError, match="permission"):
            accounts.models(profile)
    assert requests == ["/api/accounts/oauth/token"]


def test_bad_refresh_response_is_safe_and_keeps_previous_tokens(tmp_path, signing_key):
    accounts = ChatGPTAccounts(tmp_path)
    connect(accounts, signing_key)
    data = accounts._read()
    data["profiles"][data["active"]]["expires_at"] = 1
    accounts._write(data)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not-json do-not-expose")
        )
    ) as transport:
        accounts.client = transport
        with pytest.raises(SubscriptionError) as error:
            accounts.access_token(data["active"])
    assert "do-not-expose" not in str(error.value)
    assert accounts._read()["profiles"][data["active"]]["refresh_token"] == "opaque-refresh"


def test_subscription_default_and_explicit_baseline_are_distinct(
    settings, service, signing_key, monkeypatch
):
    enabled = settings.model_copy(
        update={
            "subscription_enabled": True,
            "default_chat_provider": "chatgpt_subscription",
        }
    )
    app = create_app(enabled)
    accounts = app.state.chatgpt_accounts
    connect(accounts, signing_key)
    plan = {
        "route": "data_only",
        "calls": [
            {"tool_name": "get_incident", "arguments": {"incident_id": "INC-001"}},
        ],
    }
    requests = []

    def upstream(request):
        requests.append(request.url.path)
        if request.url.path.endswith("models"):
            return catalog(request)
        return httpx.Response(200, text=stream_events(completed(plan)))

    with httpx.Client(transport=httpx.MockTransport(upstream)) as transport:
        accounts.client = transport
        accounts.select_model("gpt-test")
        monkeypatch.setattr(
            "opspilot.api.main.ChatGPTSubscription",
            lambda config, store, pid: ChatGPTSubscription(config, store, pid, transport),
        )
        with TestClient(
            app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000)
        ) as client:
            headers = {"Origin": "http://127.0.0.1:8080"}
            assert client.get("/api/health").json()["mode"] == "chatgpt_subscription"
            assert (
                client.get("/api/chatgpt/status").json()["default_provider"]
                == "chatgpt_subscription"
            )
            response = client.post("/api/chat", json={"question": "Show INC-001"}, headers=headers)
            assert response.json()["model"] == "gpt-test"
            before = len(requests)
            response = client.post(
                "/api/chat", json={"question": "Show INC-001", "provider": "configured"}
            )
            assert response.json()["mode"] == "extractive" and len(requests) == before


def test_subscription_default_without_connection_does_not_fall_back(settings, service):
    app = create_app(
        settings.model_copy(
            update={
                "subscription_enabled": True,
                "default_chat_provider": "chatgpt_subscription",
            }
        )
    )
    with TestClient(app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000)) as client:
        response = client.post(
            "/api/chat",
            json={"question": "Show INC-001"},
            headers={"Origin": "http://127.0.0.1:8080"},
        )
        assert response.status_code == 400
        assert "Continue with ChatGPT" in response.json()["detail"]
