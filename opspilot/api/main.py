import json
import logging
import threading
from contextlib import asynccontextmanager
from importlib.resources import files
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from opspilot.api.investigations import investigation_routes
from opspilot.api.subscription import local_subscription, subscription_routes
from opspilot.config import Settings
from opspilot.domain.models import (
    ChatRequest,
    GetIncidentArgs,
    MetricsArgs,
    OpsPilotResponse,
    SearchPolicyArgs,
    SimilarIncidentArgs,
)
from opspilot.investigation.service import InvestigationError
from opspilot.orchestration.service import OpsPilotService
from opspilot.providers.chatgpt import ChatGPTSubscription
from opspilot.providers.chatgpt_auth import ChatGPTAccounts, SubscriptionError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    accounts = ChatGPTAccounts(settings.data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=settings.log_level, format="%(message)s")
        app.state.service = OpsPilotService(settings)
        app.state.slots = threading.BoundedSemaphore(2)
        app.state.investigations = None
        try:
            yield
        finally:
            if app.state.investigations is not None:
                app.state.investigations.close()

    app = FastAPI(
        title="OpsPilot — Operational Incident Intelligence", version="2.0.0-dev", lifespan=lifespan
    )
    app.include_router(investigation_routes())
    app.state.subscription_enabled = settings.subscription_enabled
    app.state.default_chat_provider = settings.default_chat_provider
    app.state.chatgpt_accounts = accounts

    if settings.subscription_enabled:
        app.include_router(subscription_routes(accounts))
    else:

        @app.get("/api/chatgpt/status")
        def subscription_disabled():
            return {"enabled": False}

    @app.exception_handler(InvestigationError)
    async def investigation_error(request: Request, error: InvestigationError):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    @app.exception_handler(SubscriptionError)
    async def subscription_error(request: Request, error: SubscriptionError):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.middleware("http")
    async def correlation_id(request: Request, call_next):
        if request.url.path == "/auth/callback":
            # Uvicorn access logs must not record OAuth codes, state or issued identities.
            request.state.oauth_query = dict(request.query_params)
            request.scope["query_string"] = b""
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path.startswith(("/api/chatgpt", "/auth/callback", "/api/investigations")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "synthetic_data": True,
            "mode": "chatgpt_subscription"
            if settings.default_chat_provider == "chatgpt_subscription"
            else settings.llm_provider,
            "configured_mode": settings.llm_provider,
        }

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
            service = app.state.service
            provider = (
                settings.default_chat_provider
                if payload.provider == "default"
                else payload.provider
            )
            if provider == "chatgpt_subscription":
                local_subscription(request)
                profile_id, model = accounts.selected()
                live_settings = settings.model_copy(
                    update={
                        "llm_provider": "chatgpt_subscription",
                        "llm_model": model,
                        "input_cost_per_million": None,
                        "output_cost_per_million": None,
                    }
                )
                service = OpsPilotService(
                    live_settings, ChatGPTSubscription(live_settings, accounts, profile_id)
                )
            logging.getLogger("opspilot.requests").info(
                json.dumps(
                    {
                        "event": "request_received",
                        "request_id": request.state.request_id,
                        "environment": settings.app_env,
                    }
                )
            )
            return service.ask(payload.question, request.state.request_id)
        except (SubscriptionError, HTTPException):
            raise
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
