import json
import logging
import threading
from contextlib import asynccontextmanager
from importlib.resources import files
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from opspilot.config import Settings
from opspilot.domain.models import (
    ChatRequest,
    GetIncidentArgs,
    MetricsArgs,
    OpsPilotResponse,
    SearchPolicyArgs,
    SimilarIncidentArgs,
)
from opspilot.orchestration.service import OpsPilotService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level, format="%(message)s")
        app.state.service = OpsPilotService(settings)
        app.state.slots = threading.BoundedSemaphore(2)
        yield

    app = FastAPI(
        title="OpsPilot — Operational Incident Intelligence", version="1.0.0", lifespan=lifespan
    )

    @app.middleware("http")
    async def correlation_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get("/api/health")
    def health():
        return {"status": "ok", "synthetic_data": True, "mode": settings.llm_provider}

    @app.get("/api/ready")
    def ready():
        if not app.state.service.ready():
            raise HTTPException(503, "Evidence stores unavailable; run local bootstrap.")
        return {"status": "ready"}

    @app.get("/api/tools")
    def tools():
        schemas = {
            "search_internal_policy": SearchPolicyArgs,
            "get_incident": GetIncidentArgs,
            "find_similar_incidents": SimilarIncidentArgs,
            "calculate_incident_metrics": MetricsArgs,
        }
        return {
            name: {"permission": "read_only", "arguments": model.model_json_schema()}
            for name, model in schemas.items()
        }

    @app.post("/api/chat", response_model=OpsPilotResponse)
    def chat(payload: ChatRequest, request: Request):
        if not app.state.service.ready():
            raise HTTPException(503, "Evidence stores unavailable; run local bootstrap.")
        if not app.state.slots.acquire(blocking=False):
            raise HTTPException(429, "Busy; retry after the current investigations complete.")
        try:
            logging.getLogger("opspilot.requests").info(
                json.dumps(
                    {
                        "event": "request_received",
                        "request_id": request.state.request_id,
                        "environment": settings.app_env,
                    }
                )
            )
            return app.state.service.ask(payload.question, request.state.request_id)
        except Exception as exc:
            logging.getLogger("opspilot.errors").error(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request.state.request_id,
                        "error_type": type(exc).__name__,
                    }
                )
            )
            raise HTTPException(
                500, "Investigation failed; no business action was executed."
            ) from None
        finally:
            app.state.slots.release()

    @app.get("/", response_class=HTMLResponse)
    def home():
        return files("opspilot.ui").joinpath("index.html").read_text(encoding="utf-8")

    @app.get("/app.js")
    def script():
        return Response(
            files("opspilot.ui").joinpath("app.js").read_text(), media_type="text/javascript"
        )

    @app.get("/style.css")
    def style():
        return Response(
            files("opspilot.ui").joinpath("style.css").read_text(), media_type="text/css"
        )

    return app


app = create_app()
