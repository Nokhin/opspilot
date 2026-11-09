"""Loopback-only subscription controls, separate from business tools."""

import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import Field

from opspilot.domain.models import Contract
from opspilot.providers.chatgpt_auth import ChatGPTAccounts, SubscriptionError


def local_subscription(request: Request):
    if not request.app.state.subscription_enabled:
        raise HTTPException(404, "Local ChatGPT subscription mode is disabled.")
    if (
        request.url.hostname != "127.0.0.1"
        or not request.client
        or request.client.host
        not in {
            "127.0.0.1",
            "::1",
        }
    ):
        raise HTTPException(403, "ChatGPT subscription controls require a local 127.0.0.1 session.")
    if request.method == "POST":
        origin = request.headers.get("origin")
        expected = str(request.base_url).rstrip("/")
        if origin != expected or request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Use the local OpsPilot interface for this operation.")


class LoginRequest(Contract):
    profile_id: str | None = Field(default=None, max_length=80)


class AccountRequest(Contract):
    profile_id: str = Field(min_length=1, max_length=80)


class ModelRequest(Contract):
    model: str = Field(min_length=1, max_length=128)


def subscription_routes(accounts: ChatGPTAccounts):
    router = APIRouter(dependencies=[Depends(local_subscription)])

    @router.get("/api/chatgpt/status")
    def status(request: Request):
        return {
            "enabled": True,
            "default_provider": request.app.state.default_chat_provider,
            **accounts.status(),
        }

    @router.post("/api/chatgpt/login")
    def login(payload: LoginRequest, request: Request):
        browser_secret = secrets.token_urlsafe(32)
        redirect_uri = str(request.base_url).rstrip("/") + "/auth/callback"
        # The request guard fixes scheme/host to the local listener, never a forwarded host.
        if urlsplit(redirect_uri).scheme != "http":
            raise HTTPException(400, "Use the local HTTP loopback listener for sign-in.")
        url = accounts.start_login(redirect_uri, browser_secret, payload.profile_id)
        from fastapi.responses import JSONResponse

        response = JSONResponse({"authorization_url": url})
        response.set_cookie(
            "opspilot_oauth",
            browser_secret,
            max_age=600,
            httponly=True,
            samesite="lax",
            path="/auth/callback",
        )
        return response

    @router.get("/auth/callback")
    def callback(request: Request):
        query = request.state.oauth_query
        try:
            accounts.finish_login(query, request.cookies.get("opspilot_oauth", ""))
            response = RedirectResponse("/", status_code=303)
        except (SubscriptionError, ValueError, KeyError, TypeError):
            response = HTMLResponse(
                "<h1>ChatGPT sign-in did not complete</h1>"
                '<p>Return to <a href="/">OpsPilot</a> and reconnect your account. '
                "No ChatGPT plan inference was made.</p>",
                status_code=400,
            )
        response.delete_cookie("opspilot_oauth", path="/auth/callback")
        return response

    @router.get("/api/chatgpt/models")
    def models():
        profile = accounts.status()["active"]
        return {"models": accounts.models(profile)}

    @router.post("/api/chatgpt/account")
    def account(payload: AccountRequest):
        accounts.select_account(payload.profile_id)
        return accounts.status()

    @router.post("/api/chatgpt/model")
    def model(payload: ModelRequest):
        accounts.select_model(payload.model)
        return accounts.status()

    @router.post("/api/chatgpt/logout")
    def logout():
        revoked = accounts.logout()
        return {"remote_revocation_confirmed": revoked, **accounts.status()}

    @router.post("/api/chatgpt/welcome")
    def welcome():
        accounts.acknowledge_welcome()
        return {"acknowledged": True}

    return router
