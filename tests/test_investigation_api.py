"""Public V2 API regression including owner isolation and typed resume validation."""

import pytest
from fastapi.testclient import TestClient

from opspilot.api.main import create_app


def test_api_create_resume_restart_and_v1_unchanged(service, settings):
    app = create_app(settings)
    with TestClient(app) as client:
        made = client.post(
            "/api/investigations", json={"user_request": "Investigate this incident"}
        )
        assert made.status_code == 200
        assert made.headers["Cache-Control"] == "no-store"
        assert made.headers["Referrer-Policy"] == "no-referrer"
        r = made.json()
        assert r["completion_status"] == "awaiting_human"
        identifier = r["investigation_id"]
        headers = {"Authorization": "Bearer " + r["owner_token"]}
        assert client.get("/api/investigations/" + identifier).status_code == 404
        assert (
            client.get(
                "/api/investigations/" + identifier, headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 404
        )
        seen = client.get("/api/investigations/" + identifier, headers=headers)
        assert seen.status_code == 200 and "owner_token" not in seen.json()
        assert (
            client.post(
                "/api/investigations/" + identifier + "/resume",
                headers=headers,
                json={
                    "action": "clarify",
                    "incident_context": {"incident_id": "INC-001"},
                    "state": {},
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/investigations/" + identifier + "/resume",
                headers=headers,
                json={"action": "review", "decision": "accept"},
            ).status_code
            == 409
        )
        old = client.post("/api/chat", json={"question": "Show INC-001"})
        assert old.status_code == 200 and old.json()["route"] == "data_only"
        assert "investigation_brief" not in old.json()
    with TestClient(create_app(settings)) as client:
        resumed = client.post(
            "/api/investigations/" + identifier + "/resume",
            headers=headers,
            json={"action": "clarify", "incident_context": {"incident_id": "INC-001"}},
        )
        assert resumed.status_code == 200
        assert resumed.json()["completion_status"] == "completed"
        assert resumed.json()["investigation_brief"]["source_citations"]
        assert "owner_token" not in resumed.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"user_request": "a"},
        {"user_request": "Show INC-001", "checkpoint": {}},
        {"user_request": "Show INC-001", "incident_context": {"sql": "DROP TABLE incidents"}},
        {"user_request": "Show INC-001", "incident_context": {"downtime_minutes": -1}},
    ],
)
def test_invalid_input_cannot_be_graph_state(service, settings, payload):
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/investigations", json=payload).status_code == 422


def test_same_origin_budget_unknown_paths_and_readiness(service, settings):
    with TestClient(create_app(settings)) as client:
        assert (
            client.post(
                "/api/investigations",
                headers={"Origin": "https://untrusted.example"},
                json={"user_request": "Show INC-001"},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/investigations/not-an-id", headers={"Authorization": "Bearer wrong"}
            ).status_code
            == 404
        )
        assert client.get("/api/investigations").status_code == 405
        assert (
            client.post(
                "/api/investigations", json={"user_request": "Show INC-001", "mode": "configured"}
            ).status_code
            == 409
        )
        client.app.state.slots.acquire()
        client.app.state.slots.acquire()
        try:
            assert (
                client.post(
                    "/api/investigations", json={"user_request": "Show INC-001"}
                ).status_code
                == 429
            )
        finally:
            client.app.state.slots.release()
            client.app.state.slots.release()


def test_health_starts_without_v2_evidence(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert (
            client.post("/api/investigations", json={"user_request": "Show INC-001"}).status_code
            == 503
        )


def test_api_typed_unknown_and_bool_clarification(service, settings):
    with TestClient(create_app(settings)) as client:
        r = client.post(
            "/api/investigations",
            json={
                "user_request": "Assess severity for this payment outage",
                "incident_context": {
                    "category": "payment_failure",
                    "customer_facing": False,
                    "customer_impact_count": 110,
                },
            },
        ).json()
        headers = {"Authorization": "Bearer " + r["owner_token"]}
        target = "/api/investigations/" + r["investigation_id"] + "/resume"
        assert r["completion_status"] == "awaiting_human"
        assert (
            client.post(
                target,
                headers=headers,
                json={"action": "clarify", "incident_context": {"immediate_danger": "false"}},
            ).status_code
            == 422
        )
        assert (
            client.post(
                target,
                headers=headers,
                json={"action": "clarify", "incident_context": {"incident_id": "INC-001"}},
            ).status_code
            == 422
        )
        result = client.post(
            target,
            headers=headers,
            json={
                "action": "clarify",
                "incident_context": {
                    "immediate_danger": False,
                    "multi_site_essential_closure": False,
                },
            },
        )
        assert result.status_code == 200
        assert result.json()["severity_assessment"]["proposed_severity"] == "SEV2"
        assert "owner_token" not in result.json()
        assert all(
            a["status"] == "proposed_not_executed"
            for a in result.json()["investigation_brief"]["recommended_next_steps"]
        )
        assert (
            client.post(
                "/api/investigations",
                json={
                    "user_request": "Investigate this incident",
                    "incident_context": {"threshold_detected_at": "2026-09-29T10:00:00"},
                },
            ).status_code
            == 422
        )
