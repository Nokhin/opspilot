"""Checkpoint ownership, retention and narrow server-controlled resume boundary."""

import fcntl
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from langsmith import tracing_context

from opspilot.domain.models import Usage
from opspilot.investigation.graph import InvestigationWorkflow
from opspilot.investigation.models import (
    InvestigationCreated,
    InvestigationRequest,
    InvestigationResponse,
    ResumeRequest,
    SubscriptionBinding,
)
from opspilot.providers.chatgpt import ChatGPTSubscription

logger = logging.getLogger("opspilot.investigations")


class InvestigationError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


class InvestigationService:
    """Single-worker demo store. Tokens authorize one investigation, not business writes."""

    def __init__(
        self,
        service,
        *,
        ttl_seconds=86400,
        capacity=100,
        accounts=None,
        subscription_provider_factory=None,
    ):
        self.service = service
        self.accounts = accounts
        # Operator injection for bounded evaluation telemetry; never client-supplied state.
        self.subscription_provider_factory = subscription_provider_factory or ChatGPTSubscription
        self.ttl_seconds, self.capacity = ttl_seconds, capacity
        self.lock = threading.RLock()
        folder = Path(service.settings.data_dir) / "investigations"
        if folder.is_symlink():
            raise ValueError("Checkpoint folder cannot be a symlink")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
        self.process_fd = os.open(
            folder / ".process.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self.process_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.process_fd)
            raise ValueError("Checkpoint store is owned by another process") from None
        try:
            path = folder / "checkpoints.sqlite"
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
            path.chmod(0o600)
            self.connection = sqlite3.connect(path, check_same_thread=False)
            self.connection.execute("PRAGMA secure_delete=ON")
            self.checkpointer = SqliteSaver(
                self.connection,
                serde=JsonPlusSerializer(
                    pickle_fallback=False,
                    allowed_json_modules=[],
                    allowed_msgpack_modules=[],
                ),
            )
            self.checkpointer.setup()
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS investigation_owners ("
                "id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, expires REAL NOT NULL, "
                "mode TEXT NOT NULL, snapshot TEXT NOT NULL, failed INTEGER NOT NULL DEFAULT 0, "
                "latency_ms REAL NOT NULL DEFAULT 0)"
            )
            columns = {
                row[1] for row in self.connection.execute("PRAGMA table_info(investigation_owners)")
            }
            if "provider_binding" not in columns:
                self.connection.execute(
                    "ALTER TABLE investigation_owners ADD COLUMN "
                    "provider_binding TEXT NOT NULL DEFAULT '{}'"
                )
            self.connection.commit()
            self.workflows = {}
            self.identity = self.current_identity()
        except Exception:
            if hasattr(self, "connection"):
                self.connection.close()
            fcntl.flock(self.process_fd, fcntl.LOCK_UN)
            os.close(self.process_fd)
            raise

    def current_identity(self):
        settings = self.service.settings
        return hashlib.sha256(
            json.dumps(
                {
                    "index": hashlib.sha256(settings.vector_index.read_bytes()).hexdigest(),
                    "database": hashlib.sha256(settings.incident_db.read_bytes()).hexdigest(),
                    "reference": settings.reference_time.isoformat(),
                    "provider": [settings.llm_provider, settings.llm_base_url, settings.llm_model],
                    "subscription_enabled": settings.subscription_enabled,
                    "subscription_timeout": settings.subscription_timeout_seconds,
                    "subscription_adapter": {
                        name: hashlib.sha256(
                            (Path(__file__).parent.parent / "providers" / name).read_bytes()
                        ).hexdigest()
                        for name in ("chatgpt.py", "chatgpt_auth.py", "chat_api.py")
                    },
                    "tool_budget": settings.max_tool_calls,
                    "source": {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in Path(__file__).parent.iterdir()
                        if p.suffix in {".py", ".json"}
                    },
                    "graph_contract": 5,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def workflow(self, mode, identifier=None):
        key = (mode, identifier) if mode == "chatgpt_subscription" else mode
        if key not in self.workflows:
            provider = self.service.provider if mode == "configured" else None
            if mode == "chatgpt_subscription":
                binding = self.binding(identifier)
                settings = self.service.settings.model_copy(
                    update={
                        "llm_provider": mode,
                        "llm_model": binding["model"],
                        "input_cost_per_million": None,
                        "output_cost_per_million": None,
                    }
                )
                provider = self.subscription_provider_factory(
                    settings, self.accounts, binding["profile_id"]
                )
            self.workflows[key] = InvestigationWorkflow(self.service, self.checkpointer, provider)
        return self.workflows[key].graph

    def binding(self, identifier):
        row = self.connection.execute(
            "SELECT provider_binding FROM investigation_owners WHERE id=?", (identifier,)
        ).fetchone()
        value = json.loads(row[0]) if row else {}
        return SubscriptionBinding.model_validate(value).model_dump() if value else {}

    def authorized_mode(self, identifier, token):
        with self.lock:
            return self.authorize(identifier, token)[1]

    @staticmethod
    def config(investigation_id):
        return {"configurable": {"thread_id": investigation_id}, "recursion_limit": 32}

    def close(self):
        with self.lock:
            self.connection.close()
            fcntl.flock(self.process_fd, fcntl.LOCK_UN)
            os.close(self.process_fd)

    def prune(self):
        expired = self.connection.execute(
            "SELECT id FROM investigation_owners WHERE expires <= ?", (time.time(),)
        ).fetchall()
        for (identifier,) in expired:
            self.checkpointer.delete_thread(identifier)
            self.connection.execute("DELETE FROM investigation_owners WHERE id = ?", (identifier,))
            self.workflows.pop(("chatgpt_subscription", identifier), None)
        self.connection.commit()

    def authorize(self, identifier, token):
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError()
        except ValueError:
            raise InvestigationError(404, "Investigation not found.") from None
        self.prune()
        row = self.connection.execute(
            "SELECT token_hash, mode, snapshot, failed FROM investigation_owners WHERE id = ?",
            (identifier,),
        ).fetchone()
        hashed = hashlib.sha256(token.encode()).hexdigest()
        if not row or not secrets.compare_digest(row[0], hashed):
            raise InvestigationError(404, "Investigation not found.")
        return row

    def create(self, payload: InvestigationRequest) -> InvestigationCreated:
        payload = InvestigationRequest.model_validate(payload.model_dump())
        with self.lock, tracing_context(enabled=False):
            self.prune()
            if self.current_identity() != self.identity:
                raise InvestigationError(409, "Evidence or graph changed; restart the service.")
            count = self.connection.execute("SELECT count(*) FROM investigation_owners").fetchone()[
                0
            ]
            if count >= self.capacity:
                raise InvestigationError(429, "Investigation capacity reached; wait for expiry.")
            if payload.mode == "configured" and not self.service.provider:
                raise InvestigationError(409, "No configured V2 LLM provider. Use offline mode.")
            binding = {}
            if payload.mode == "chatgpt_subscription":
                if not self.service.settings.subscription_enabled or self.accounts is None:
                    raise InvestigationError(409, "Local ChatGPT subscription mode is disabled.")
                profile_id, model = self.accounts.selected()
                binding = SubscriptionBinding(profile_id=profile_id, model=model).model_dump()
            if payload.mode == "offline" and self.service.settings.embedding_provider != "tfidf":
                raise InvestigationError(
                    409, "Offline investigations require the local TF-IDF index."
                )
            identifier, token = str(uuid4()), secrets.token_urlsafe(32)
            self.connection.execute(
                "INSERT INTO investigation_owners"
                "(id,token_hash,expires,mode,snapshot,provider_binding) "
                "VALUES (?,?,?,?,?,?)",
                (
                    identifier,
                    hashlib.sha256(token.encode()).hexdigest(),
                    time.time() + self.ttl_seconds,
                    payload.mode,
                    self.identity,
                    json.dumps(binding),
                ),
            )
            self.connection.commit()
            state = {
                "investigation_id": identifier,
                "user_request": payload.user_request,
                "incident_context": payload.incident_context.model_dump(exclude_none=True),
                "route": "unsupported",
                "retrieved_policy_evidence": [],
                "historical_incident_evidence": [],
                "tool_traces": [],
                "evidence_gaps": [],
                "retry_count": 0,
                "clarification_request": None,
                "human_review_status": "not_required",
                "investigation_brief": None,
                "completion_status": "running",
                "usage": Usage().model_dump(),
                "latency_ms": 0.0,
                "usage_complete": True,
                "mode": payload.mode,
                "require_review": payload.require_review,
                "workflow_trace": [],
                "facts": [],
                "evidence": [],
                "limitations": [],
                "query": payload.user_request,
                "failed": False,
                "error": None,
                "planning_diagnostic": None,
                "clarification_done": False,
                "attempted_queries": [],
                "snapshot_identity": self.identity,
                "reported_context": {},
                "recorded_context": {},
                "unknown_fields": [],
                "severity_assessment": {},
                "proposed_actions": [],
                "model": binding.get("model")
                or (self.service.settings.llm_model if payload.mode == "configured" else None),
                "provider_call_count": 0,
            }
            self._invoke(identifier, payload.mode, state)
            response = self._view(identifier, payload.mode)
            return InvestigationCreated(**response.model_dump(), owner_token=token)

    def _invoke(self, identifier, mode, value):
        start = time.perf_counter()
        graph = self.workflow(mode, identifier)
        config = self.config(identifier)
        try:
            graph.invoke(value, config, durability="sync")
            snapshot = graph.get_state(config)
            # No raw client graph configuration or serialized checkpoint is ever accepted.
            if len(json.dumps(snapshot.values).encode()) > 262144:
                raise ValueError("State-size limit")
            elapsed = snapshot.values.get("latency_ms", 0) + (time.perf_counter() - start) * 1000
            self.connection.execute(
                "UPDATE investigation_owners SET latency_ms=latency_ms+? WHERE id=?",
                (elapsed, identifier),
            )
            self.connection.commit()
        except Exception as error:
            self.connection.execute(
                "UPDATE investigation_owners SET failed=1 WHERE id=?", (identifier,)
            )
            self.connection.commit()
            logger.error(
                json.dumps(
                    {
                        "event": "investigation_failed",
                        "investigation_id": identifier,
                        "error_type": type(error).__name__,
                    }
                )
            )
        # Latest checkpoints are full state snapshots; old histories are not a public API.
        self._compact(identifier)

    def _compact(self, identifier):
        with self.connection:
            keep = self.connection.execute(
                "SELECT checkpoint_id FROM checkpoints WHERE thread_id=? "
                "ORDER BY checkpoint_id DESC LIMIT 2",
                (identifier,),
            ).fetchall()
            if not keep:
                return
            placeholders = ",".join("?" for _ in keep)
            values = (identifier, *(row[0] for row in keep))
            for table in ("writes", "checkpoints"):
                self.connection.execute(
                    f"DELETE FROM {table} WHERE thread_id=? "
                    f"AND checkpoint_id NOT IN ({placeholders})",
                    values,
                )

    def _view(self, identifier, mode):
        failed, latency = self.connection.execute(
            "SELECT failed, latency_ms FROM investigation_owners WHERE id=?", (identifier,)
        ).fetchone()
        if failed:
            return InvestigationResponse(
                investigation_id=identifier,
                completion_status="failed",
                route="unsupported",
                human_review_status="not_required",
                retry_count=0,
                workflow_trace=[],
                tool_traces=[],
                usage=Usage(),
                latency_ms=0,
                mode=mode,
                usage_complete=mode == "offline",
                model=self.binding(identifier).get("model"),
                error="Investigation failed safely; no business action was executed.",
            )
        snapshot = self.workflow(mode, identifier).get_state(self.config(identifier))
        state = snapshot.values
        pending = next((i.value for task in snapshot.tasks for i in task.interrupts), None)
        if snapshot.next and pending is None:
            # An interrupted invocation without a human interrupt must not silently
            # replay a possibly billed provider call after process recovery.
            self.connection.execute(
                "UPDATE investigation_owners SET failed=1 WHERE id=?", (identifier,)
            )
            self.connection.commit()
            return self._view(identifier, mode)
        status = "awaiting_human" if pending else state["completion_status"]
        review = (
            "pending" if pending and pending["kind"] == "review" else state["human_review_status"]
        )
        return InvestigationResponse(
            investigation_id=identifier,
            completion_status=status,
            route=state["route"],
            investigation_plan=state.get("investigation_plan"),
            verification_result=state.get("verification_result"),
            clarification_request=pending,
            human_review_status=review,
            retry_count=state["retry_count"],
            investigation_brief=state.get("investigation_brief"),
            workflow_trace=state["workflow_trace"],
            tool_traces=state["tool_traces"],
            usage=state["usage"],
            latency_ms=latency,
            usage_complete=state.get("usage_complete", True),
            mode=state["mode"],
            model=state.get("model"),
            provider_call_count=state.get("provider_call_count", 0),
            planning_diagnostic=state.get("planning_diagnostic"),
            error=state["error"],
            severity_assessment=(state.get("severity_assessment") or None)
            if state["completion_status"] != "failed"
            else None,
        )

    def get(self, identifier, token):
        with self.lock, tracing_context(enabled=False):
            row = self.authorize(identifier, token)
            if row[2] != self.identity or self.current_identity() != self.identity:
                raise InvestigationError(
                    409, "Evidence snapshot or graph changed; start a new investigation."
                )
            return self._view(identifier, row[1])

    def resume(self, identifier, token, payload: ResumeRequest):
        payload = ResumeRequest.model_validate(payload.model_dump())
        with self.lock, tracing_context(enabled=False):
            row = self.authorize(identifier, token)
            current = self.get(identifier, token)
            if current.completion_status != "awaiting_human":
                raise InvestigationError(409, "Investigation is not waiting for human input.")
            if current.clarification_request["kind"] != payload.action:
                raise InvestigationError(409, "Response does not match the pending human request.")
            if payload.action == "clarify":
                values = (
                    payload.incident_context.model_dump(exclude_none=True)
                    if payload.incident_context
                    else {}
                )
                allowed = set(current.clarification_request["accepted_fields"])
                if not (set(values) | set(payload.unknown_fields)) <= allowed:
                    raise InvestigationError(
                        422, "Supply only the requested typed clarification fields."
                    )
            self._invoke(identifier, row[1], Command(resume=payload.model_dump(mode="json")))
            return self._view(identifier, row[1])
