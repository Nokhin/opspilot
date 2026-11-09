"""Local Sign in with ChatGPT: PKCE/OIDC, protected profiles and model discovery."""

import base64
import fcntl
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import jwt

from opspilot.providers.chat_api import UserFacingProviderError

ISSUER = "https://auth.openai.com"
API = "https://api.openai.com/v1"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"


class SubscriptionError(UserFacingProviderError):
    """Safe, actionable message, without tokens or upstream response bodies."""


class CredentialLock:
    """Serialize rotating refresh tokens across threads and local worker processes."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.thread_lock = threading.RLock()
        self.local = threading.local()

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            depth = getattr(self.local, "depth", 0)
            if depth == 0:
                if self.directory.is_symlink():
                    raise SubscriptionError("Unsafe credential storage path.")
                self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                self.local.fd = os.open(
                    self.directory / ".session.lock",
                    os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                    0o600,
                )
                try:
                    fcntl.flock(self.local.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(self.local.fd)
                    raise SubscriptionError(
                        "ChatGPT session is busy in another local process."
                    ) from None
            self.local.depth = depth + 1
            return self
        except Exception:
            self.thread_lock.release()
            raise

    def __exit__(self, *exc):
        self.local.depth -= 1
        if self.local.depth == 0:
            fcntl.flock(self.local.fd, fcntl.LOCK_UN)
            os.close(self.local.fd)
        self.thread_lock.release()


class ChatGPTAccounts:
    """One local process owns the credentials; never return them to the UI."""

    def __init__(self, data_dir: Path, client: httpx.Client | None = None):
        self.directory = data_dir / "chatgpt"
        self.path = self.directory / "accounts.json"
        self.client = client
        self.lock = CredentialLock(self.directory)
        self.pending: dict[str, dict] = {}
        self.catalogs: dict[str, list[dict]] = {}

    def _read(self):
        if self.directory.is_symlink() or self.path.is_symlink():
            raise SubscriptionError("Unsafe credential storage path.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        if not self.path.exists():
            data = {"host_id": "urn:uuid:" + str(uuid4()), "active": None, "profiles": {}}
            self._write(data)
            return data
        self.path.chmod(0o600)
        try:
            return json.loads(self.path.read_text())
        except (ValueError, OSError):
            raise SubscriptionError("Credential storage unavailable; reconnect locally.") from None

    def _write(self, data):
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".accounts-")
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(data, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _http(self, method, url, **kwargs):
        owned = self.client is None
        client = self.client or httpx.Client(trust_env=False, follow_redirects=False)
        try:
            response = client.request(method, url, timeout=20, **kwargs)
            if response.status_code >= 300:
                raise SubscriptionError(
                    f"ChatGPT connection rejected (HTTP {response.status_code}); "
                    "reconnect or review ChatGPT Settings → Usage."
                )
            return response
        except httpx.HTTPError:
            raise SubscriptionError("ChatGPT connection unavailable; retry later.") from None
        finally:
            if owned:
                client.close()

    def status(self):
        with self.lock:
            data = self._read()
            profiles = []
            for key, profile in data["profiles"].items():
                profiles.append(
                    {
                        "id": key,
                        "label": profile.get("email") or f"Account {key[:8]}",
                        "registration": profile["client_id"][-8:],
                        "connected": bool(profile.get("access_token")),
                        "plan_enabled": PLAN_SCOPE in profile.get("scopes", []),
                        "model": profile.get("model"),
                        "welcome_acknowledged": profile.get("welcome_acknowledged", False),
                    }
                )
            return {"active": data["active"], "profiles": profiles}

    def _json(self, method, url, **kwargs):
        try:
            data = self._http(method, url, **kwargs).json()
            if not isinstance(data, dict):
                raise ValueError("invalid payload")
            return data
        except (ValueError, TypeError):
            raise SubscriptionError(
                "ChatGPT returned an invalid connection response; reconnect."
            ) from None

    def start_login(self, redirect_uri: str, browser_secret: str, profile_id: str | None = None):
        with self.lock:
            data = self._read()
            profile = data["profiles"].get(profile_id) if profile_id else None
            if profile_id and not profile:
                raise SubscriptionError("Unknown account registration.")
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            self.pending = {k: v for k, v in self.pending.items() if v["expires"] > time.time()}
            if len(self.pending) >= 8:
                raise SubscriptionError("Too many pending sign-ins; wait ten minutes.")
            self.pending[state] = {
                "nonce": nonce,
                "verifier": verifier,
                "redirect_uri": redirect_uri,
                "browser_secret": browser_secret,
                "expires": time.time() + 600,
                "profile_id": profile_id,
                "client_id": profile["client_id"] if profile else None,
                "subject": profile.get("subject") if profile else None,
            }
            parameters = {
                "client_id": profile["client_id"] if profile else "dynamic_agent_client",
                "ext_agent_host_id": data["host_id"],
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": SCOPES,
                "resource": API,
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode()).digest()
                )
                .rstrip(b"=")
                .decode(),
            }
            if not profile:
                parameters["agent_name_hint"] = "OpsPilot"
            # Do not expose retained ID tokens in browser JavaScript or URLs.
            return AUTHORIZE + "?" + urlencode(parameters)

    def finish_login(self, query: dict[str, str], browser_secret: str):
        with self.lock:
            state = query.get("state", "")
            pending = self.pending.get(state)
            if (
                not pending
                or not secrets.compare_digest(pending["browser_secret"], browser_secret)
                or pending["expires"] <= time.time()
            ):
                raise SubscriptionError("Sign-in expired or did not match this browser.")
            del self.pending[state]
            if query.get("error") or not query.get("code"):
                raise SubscriptionError("Sign-in cancelled; no ChatGPT plan request was made.")
            issued = query.get("client_id") or pending["client_id"]
            if (
                not issued
                or issued == "dynamic_agent_client"
                or (pending["client_id"] and issued != pending["client_id"])
            ):
                raise SubscriptionError("Sign-in returned an invalid account registration.")
            data = self._read()
            profile_id = pending["profile_id"] or str(uuid4())
            profile = data["profiles"].setdefault(profile_id, {"client_id": issued})
            # Keep an issued registration if the one-time code expires during exchange.
            self._write(data)
            tokens = self._json(
                "POST",
                TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "client_id": issued,
                    "code": query["code"],
                    "code_verifier": pending["verifier"],
                    "redirect_uri": pending["redirect_uri"],
                    "resource": API,
                },
            )
            try:
                id_token = tokens["id_token"]
                keys = self._json("GET", ISSUER + "/.well-known/jwks.json")["keys"]
                header = jwt.get_unverified_header(id_token)
                key = next(k for k in keys if k["kid"] == header["kid"])
                identity = jwt.decode(
                    id_token,
                    jwt.PyJWK.from_dict(key, algorithm="RS256").key,
                    algorithms=["RS256"],
                    audience=issued,
                    issuer=ISSUER,
                    leeway=5,
                    options={"require": ["sub", "exp", "iat", "nonce"]},
                )
                if not secrets.compare_digest(identity["nonce"], pending["nonce"]):
                    raise ValueError("nonce")
                if not isinstance(identity["sub"], str) or not identity["sub"]:
                    raise ValueError("subject")
                if pending["subject"] and identity["sub"] != pending["subject"]:
                    raise ValueError("different account")
                profile.update(self._token_record(tokens))
                profile.update(subject=identity["sub"], email=identity.get("email"))
            except (jwt.PyJWTError, KeyError, StopIteration, ValueError, TypeError):
                raise SubscriptionError(
                    "ChatGPT identity verification failed; sign in again."
                ) from None
            profile.pop("model", None)
            data["active"] = profile_id
            self.catalogs.clear()
            self._write(data)
            return PLAN_SCOPE in profile["scopes"]

    @staticmethod
    def _token_record(tokens, previous=None):
        previous = previous or {}
        if not isinstance(tokens.get("access_token"), str) or not tokens["access_token"]:
            raise ValueError("access token missing")
        if tokens.get("token_type", "").lower() != "bearer":
            raise ValueError("unsupported token type")
        lifetime = int(tokens["expires_in"])
        if lifetime <= 0:
            raise ValueError("invalid lifetime")
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token", previous.get("refresh_token")),
            "id_token": tokens.get("id_token", previous.get("id_token")),
            "scopes": tokens.get("scope", " ".join(previous.get("scopes", []))).split(),
            "expires_at": time.time() + lifetime,
        }

    def access_token(self, profile_id: str):
        with self.lock:
            data = self._read()
            profile = data["profiles"].get(profile_id)
            if not profile or not profile.get("access_token"):
                raise SubscriptionError("Continue with ChatGPT before investigating.")
            if PLAN_SCOPE not in profile.get("scopes", []):
                raise SubscriptionError("Enable ChatGPT plan usage by reconnecting your account.")
            if profile["expires_at"] <= time.time() + 60:
                if not profile.get("refresh_token"):
                    raise SubscriptionError("ChatGPT session expired; reconnect your account.")
                tokens = self._json(
                    "POST",
                    TOKEN,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": profile["client_id"],
                        "refresh_token": profile["refresh_token"],
                        "resource": API,
                    },
                )
                try:
                    profile.update(self._token_record(tokens, profile))
                except (ValueError, KeyError, TypeError):
                    raise SubscriptionError("ChatGPT session renewal failed; reconnect.") from None
                self._write(data)
                if PLAN_SCOPE not in profile["scopes"]:
                    raise SubscriptionError("ChatGPT plan permission is no longer available.")
            return profile["access_token"]

    def models(self, profile_id: str):
        with self.lock:
            token = self.access_token(profile_id)
            try:
                payload = self._json(
                    "GET",
                    API + "/models",
                    headers={
                        "Authorization": "Bearer " + token,
                    },
                )
                models = [
                    {"id": row["slug"], "name": row["display_name"]}
                    for row in payload["models"]
                    if row.get("visibility") == "list"
                    and isinstance(row.get("slug"), str)
                    and isinstance(row.get("display_name"), str)
                ]
            except (ValueError, KeyError, TypeError):
                raise SubscriptionError(
                    "ChatGPT model catalog unavailable; refresh models."
                ) from None
            self.catalogs[profile_id] = models
            return models

    def select_account(self, profile_id):
        with self.lock:
            data = self._read()
            if profile_id not in data["profiles"]:
                raise SubscriptionError("Unknown account registration.")
            data["active"] = profile_id
            self.catalogs.clear()
            self._write(data)

    def acknowledge_welcome(self):
        with self.lock:
            data = self._read()
            if data["active"]:
                data["profiles"][data["active"]]["welcome_acknowledged"] = True
                self._write(data)

    def select_model(self, model):
        with self.lock:
            data = self._read()
            profile_id = data["active"]
            if model not in {row["id"] for row in self.models(profile_id)}:
                raise SubscriptionError("Select a currently available ChatGPT model.")
            data = self._read()  # A model-list request may have rotated tokens.
            data["profiles"][profile_id]["model"] = model
            self._write(data)

    def selected(self):
        with self.lock:
            data = self._read()
            profile_id = data["active"]
            profile = data["profiles"].get(profile_id, {})
            if not profile.get("access_token"):
                raise SubscriptionError("Continue with ChatGPT before investigating.")
            model = profile.get("model")
            if not model or model not in {row["id"] for row in self.models(profile_id)}:
                raise SubscriptionError("Select an available model before investigating.")
            return profile_id, model

    def logout(self):
        with self.lock:
            data = self._read()
            profile_id = data["active"]
            profile = data["profiles"].get(profile_id)
            confirmed = True
            if profile:
                if profile.get("refresh_token"):
                    try:
                        self._http(
                            "POST",
                            ISSUER + "/api/accounts/oauth/revoke",
                            data={
                                "token": profile["refresh_token"],
                                "token_type_hint": "refresh_token",
                                "client_id": profile["client_id"],
                            },
                        )
                    except SubscriptionError:
                        confirmed = False
                for key in ["access_token", "refresh_token", "id_token", "scopes", "expires_at"]:
                    profile.pop(key, None)
            self.pending.clear()
            self.catalogs.clear()
            self._write(data)
            return confirmed
