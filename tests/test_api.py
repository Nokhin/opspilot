from fastapi.testclient import TestClient

from opspilot.api.main import create_app


def test_api_health_readiness_chat_ui_and_no_upload(service, settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 200
        result = client.post("/api/chat", json={"question": "Show INC-001"})
        assert result.status_code == 200
        assert result.json()["route"] == "data_only"
        assert result.headers["X-Request-ID"] == result.json()["request_id"]
        assert result.json()["tool_trace"][0]["tool_name"] == "get_incident"
        assert "Synthetic" in client.get("/").text
        assert client.get("/app.js").status_code == 200
        assert client.get("/style.css").status_code == 200
        assert client.post("/api/ingest").status_code == 404
        assert all(t["permission"] == "read_only" for t in client.get("/api/tools").json().values())


def test_health_without_bootstrap_and_validation(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/ready").status_code == 503
        assert client.post("/api/chat", json={"question": "a"}).status_code == 422
        assert (
            client.post("/api/chat", json={"question": "valid", "sql": "DROP TABLE"}).status_code
            == 422
        )
        assert client.post("/api/chat", json={"question": "Show INC-001"}).status_code == 503
