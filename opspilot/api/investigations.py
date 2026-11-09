"""V2 capability-authorized investigation APIs; no checkpoint/state editing API."""

import sqlite3
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from opspilot.api.subscription import local_subscription
from opspilot.investigation.models import (
    InvestigationCreated,
    InvestigationRequest,
    InvestigationResponse,
    ResumeRequest,
)
from opspilot.investigation.service import InvestigationService

bearer = HTTPBearer(auto_error=False)


def owner_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if credentials is None or len(credentials.credentials) > 128:
        raise HTTPException(404, "Investigation not found.")
    return credentials.credentials


def same_origin(request: Request):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin is not None and origin != str(request.base_url).rstrip("/")
    ):
        raise HTTPException(403, "Use the same-origin investigation interface.")


def investigation_routes():
    router = APIRouter(prefix="/api/investigations", dependencies=[Depends(same_origin)])
    initialization = threading.Lock()

    def store(request: Request):
        app = request.app
        if not app.state.service.ready():
            raise HTTPException(503, "Evidence stores unavailable; run local bootstrap.")
        with initialization:
            if app.state.investigations is None:
                try:
                    app.state.investigations = InvestigationService(
                        app.state.service, accounts=app.state.chatgpt_accounts
                    )
                except (OSError, ValueError, sqlite3.Error):
                    raise HTTPException(
                        503, "Checkpoint storage unavailable or owned by another worker."
                    ) from None
        return app.state.investigations

    def slot(request: Request):
        if not request.app.state.slots.acquire(blocking=False):
            raise HTTPException(429, "Busy; retry after the current investigations complete.")
        try:
            yield
        finally:
            request.app.state.slots.release()

    @router.post("", response_model=InvestigationCreated, dependencies=[Depends(slot)])
    def create(
        payload: InvestigationRequest,
        request: Request,
        service: Annotated[InvestigationService, Depends(store)],
    ):
        if payload.mode == "chatgpt_subscription":
            local_subscription(request)
        return service.create(payload)

    @router.get("/{identifier}", response_model=InvestigationResponse)
    def get(
        identifier: str,
        request: Request,
        token: Annotated[str, Depends(owner_token)],
        service: Annotated[InvestigationService, Depends(store)],
    ):
        if service.authorized_mode(identifier, token) == "chatgpt_subscription":
            local_subscription(request)
        return service.get(identifier, token)

    @router.post(
        "/{identifier}/resume", response_model=InvestigationResponse, dependencies=[Depends(slot)]
    )
    def resume(
        identifier: str,
        request: Request,
        payload: ResumeRequest,
        token: Annotated[str, Depends(owner_token)],
        service: Annotated[InvestigationService, Depends(store)],
    ):
        if service.authorized_mode(identifier, token) == "chatgpt_subscription":
            local_subscription(request)
        return service.resume(identifier, token, payload)

    return router
