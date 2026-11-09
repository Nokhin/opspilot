"""A real conditional LangGraph: evidence collection, verification, retry and HITL."""

import json
import re
import sqlite3
import time

from langchain_core.exceptions import OutputParserException
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import TypeAdapter

from opspilot.domain.models import (
    PolicyCall,
    PolicyHit,
    RoutePlan,
    SearchPolicyArgs,
    ToolCall,
    Usage,
)
from opspilot.investigation.assessment import observations
from opspilot.investigation.brief import context_summary, executive_summary
from opspilot.investigation.chains import PlanningChain
from opspilot.investigation.context import (
    QUESTIONS,
    clarification_fields,
    effective_severity,
    needs_assessment,
    parse_context,
)
from opspilot.investigation.evidence import EvidenceVerifier, synthesize
from opspilot.investigation.models import (
    InvestigationBrief,
    InvestigationPlan,
    InvestigationState,
    PlanningDiagnostic,
    ResumeRequest,
    VerificationResult,
)
from opspilot.investigation.planning import (
    PlanningRejected,
    make_plan,
    planning_contract,
    validate_proposed_plan,
)
from opspilot.orchestration.routing import DeterministicPlanner, shift_months, unsafe_request
from opspilot.providers.chat_api import ProviderError
from opspilot.providers.chatgpt_auth import SubscriptionError


class InvestigationWorkflow:
    def __init__(self, service, checkpointer, provider=None):
        self.service = service
        self.settings = service.settings
        self.tools = service.tools
        self.planning_chain = PlanningChain(provider) if provider else None
        self.verifier = EvidenceVerifier(service.store.snapshot()["chunks"], self.tools.as_of)
        graph = StateGraph(InvestigationState)
        for name in (
            "intake",
            "plan_investigation",
            "retrieve_policies",
            "analyse_incident_history",
            "synthesise_evidence",
            "verify_evidence",
            "targeted_retry",
            "request_clarification",
            "request_review",
            "generate_investigation_brief",
            "finalize",
        ):
            graph.add_node(name, self.bounded(getattr(self, name)))
        graph.add_edge(START, "intake")
        graph.add_conditional_edges(
            "intake",
            self.after_intake,
            {"clarify": "request_clarification", "plan": "plan_investigation"},
        )
        graph.add_edge("request_clarification", "plan_investigation")
        graph.add_conditional_edges(
            "plan_investigation",
            self.after_plan,
            {
                "history": "analyse_incident_history",
                "policy": "retrieve_policies",
                "synthesis": "synthesise_evidence",
            },
        )
        graph.add_conditional_edges(
            "analyse_incident_history",
            self.after_history,
            {"policy": "retrieve_policies", "synthesis": "synthesise_evidence"},
        )
        graph.add_edge("retrieve_policies", "synthesise_evidence")
        graph.add_edge("synthesise_evidence", "verify_evidence")
        graph.add_conditional_edges(
            "verify_evidence",
            self.after_verification,
            {
                "retry": "targeted_retry",
                "review": "request_review",
                "brief": "generate_investigation_brief",
            },
        )
        graph.add_edge("targeted_retry", "synthesise_evidence")
        graph.add_edge("request_review", "generate_investigation_brief")
        graph.add_edge("generate_investigation_brief", "finalize")
        graph.add_edge("finalize", END)
        self.graph = graph.compile(checkpointer=checkpointer, name="opspilot_investigation_v2")

    @staticmethod
    def bounded(node):
        def invoke(state):
            result = node(state)
            if len(json.dumps({**state, **result}).encode()) > 262144:
                raise ValueError("Investigation state exceeded 256 KiB")
            return result

        return invoke

    @staticmethod
    def step(state, name, **updates):
        return {"workflow_trace": state["workflow_trace"] + [name], **updates}

    def intake(self, state):
        query = state["user_request"]
        context = dict(state["incident_context"])
        ids = set(re.findall(r"\bINC-\d{3}\b", query.upper()))
        if context.get("incident_id"):
            ids.add(context["incident_id"])
        if len(ids) > 1:
            return self.step(
                state,
                "intake",
                failed=True,
                error="Multiple incident IDs require separate investigations.",
            )
        if ids:
            context["incident_id"] = next(iter(ids))
        context = parse_context(query, {k: v for k, v in context.items() if k != "source"})
        reported = dict(context)
        if context:
            context["source"] = "user_reported"
        return self.step(state, "intake", incident_context=context, reported_context=reported)

    def after_intake(self, state):
        if state["failed"] or unsafe_request(state["user_request"]):
            return "plan"
        return "clarify" if clarification_fields(state) else "plan"

    def request_clarification(self, state):
        context, reported = dict(state["incident_context"]), dict(state.get("reported_context", {}))
        unknown = list(state.get("unknown_fields", []))
        # Replayed node code only merges validated data. No tools/model calls run in this node.
        for number in range(2):
            pending = {**state, "incident_context": context, "clarification_done": False}
            fields = [n for n in clarification_fields(pending) if n not in unknown]
            if not fields:
                break
            response = interrupt(
                {
                    "kind": "clarify",
                    "message": (
                        "Provide the requested incident facts, or explicitly mark them unknown."
                    ),
                    "accepted_fields": fields,
                    "questions": [{"field": n, "question": QUESTIONS[n]} for n in fields],
                    "round": number + 1,
                    "max_rounds": 2,
                    "unknown_allowed": True,
                    "read_only": True,
                }
            )
            payload = ResumeRequest.model_validate(response)
            if payload.action != "clarify":
                raise ValueError("Wrong interrupt response")
            values = (
                payload.incident_context.model_dump(mode="json", exclude_none=True)
                if payload.incident_context
                else {}
            )
            if not (set(values) | set(payload.unknown_fields)) <= set(fields):
                raise ValueError("Unrequested clarification fields")
            context.update(values)
            reported.update(values)
            unknown.extend(n for n in payload.unknown_fields if n not in unknown)
        return self.step(
            state,
            "request_clarification",
            incident_context=context,
            reported_context=reported,
            unknown_fields=unknown,
            clarification_done=True,
        )

    def plan_investigation(self, state):
        context = state["incident_context"]
        query = state["user_request"]
        # Structured clarification values become bounded search facts, never graph instructions.
        additions = []
        for key in ("incident_id", "category", "severity"):
            if context.get(key):
                additions.append(str(context[key]).replace("_", " "))
        if context.get("downtime_minutes") is not None:
            additions.append(f"duration of {context['downtime_minutes']} minutes")
        query = (query + " " + " ".join(additions)).strip()
        if re.search(r"\binvestigat", query, re.I) and (
            context.get("incident_id") or context.get("category")
        ):
            query += " escalation policy and compare historical incidents"
        if needs_assessment(state["user_request"], context):
            query += " classification policy"
        if len(query) > 3000:
            return self.step(
                state,
                "plan_investigation",
                query=query[:3000],
                route="unsupported",
                investigation_plan=make_plan("", RoutePlan(route="unsupported")).model_dump(
                    mode="json"
                ),
                failed=True,
                error=(
                    "Expanded investigation request exceeds the query bound; shorten the request."
                ),
            )
        usage = Usage.model_validate(state["usage"])
        failed, error = state["failed"], state["error"]
        usage_complete = state.get("usage_complete", True)
        provider_calls = state.get("provider_call_count", 0)
        minimum, proposed, diagnostic = None, None, None
        stage = "requirements"
        try:
            if failed or unsafe_request(state["user_request"]):
                execution = RoutePlan(route="unsupported")
            else:
                minimum = DeterministicPlanner().plan(
                    query, self.settings.reference_time, self.settings.top_k
                )
                execution = minimum
                if state["mode"] != "offline" and self.planning_chain:
                    catalog = self.tools.incidents.planning_catalog()
                    stage = "provider"
                    if provider_calls:
                        raise PlanningRejected("provider_call_budget_exhausted")
                    provider_calls += 1
                    usage_complete = False
                    self.planning_chain.usage = Usage()
                    execution = self.planning_chain.invoke(
                        {
                            "question": query,
                            "snapshot_reference": self.settings.reference_time.isoformat(),
                            "top_k": self.settings.top_k,
                            "service_catalog": catalog,
                            "planning_contract": planning_contract(
                                minimum, query, self.settings.max_tool_calls
                            ),
                        }
                    )
                    usage = self.planning_chain.usage
                    usage_complete = True
                proposed, stage = execution, "validation"
                execution = validate_proposed_plan(
                    execution, minimum, query, self.settings.max_tool_calls
                )
                for call in execution.calls:
                    if call.tool_name == "search_internal_policy":
                        call.arguments.query = call.arguments.query[:3000]
                        call.arguments.top_k = min(call.arguments.top_k, self.settings.top_k)
        except (
            ValueError,
            OutputParserException,
            ProviderError,
            SubscriptionError,
            OSError,
            sqlite3.Error,
        ) as rejection:
            if isinstance(rejection, PlanningRejected):
                code = rejection.code
            elif isinstance(rejection, OSError | sqlite3.Error) and stage != "provider":
                code = "evidence_source_unavailable"
            elif stage == "provider":
                # The V1 adapter groups transport and output failures; do not guess a subtype.
                code = "provider_or_output_failure"
            else:
                code = "invalid_plan_schema"
            diagnostic = PlanningDiagnostic(
                code=code,
                stage=stage,
                required_route=minimum.route if minimum else None,
                proposed_route=proposed.route if proposed else None,
                required_tools=[c.tool_name for c in minimum.calls] if minimum else [],
                proposed_tools=[c.tool_name for c in proposed.calls] if proposed else [],
            ).model_dump(mode="json")
            execution = RoutePlan(route="unsupported")
            failed, error = True, "Planning failed validation or evidence service was unavailable."
            if self.planning_chain:
                usage = self.planning_chain.usage
        return self.step(
            state,
            "plan_investigation",
            query=query,
            route=execution.route,
            investigation_plan=make_plan(query, execution, context).model_dump(mode="json"),
            usage=usage.model_dump(),
            usage_complete=usage_complete,
            provider_call_count=provider_calls,
            planning_diagnostic=diagnostic,
            failed=failed,
            error=error,
        )

    @staticmethod
    def after_plan(state):
        if state["failed"]:
            return "synthesis"
        if state["route"] in {"data_only", "mixed"}:
            return "history"
        return "policy" if state["route"] == "policy_only" else "synthesis"

    @staticmethod
    def after_history(state):
        return "policy" if state["route"] == "mixed" else "synthesis"

    def execute(self, call, traces):
        start = time.perf_counter()
        call = TypeAdapter(ToolCall).validate_python(call.model_dump())
        args = call.arguments.model_dump(mode="json", exclude_none=True)
        if len(traces) >= 5:
            raise ValueError("Investigation tool budget exceeded")
        try:
            result = self.tools.execute(call).model_dump(mode="json")
            status, summary = "success", "Validated read-only evidence returned."
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            result, status, summary = None, "failed", "Evidence source unavailable; no result used."
        traces.append(
            {
                "tool_name": call.tool_name,
                "arguments": args,
                "status": status,
                "summary": summary,
                "latency_ms": (time.perf_counter() - start) * 1000,
            }
        )
        return result, args

    def analyse_incident_history(self, state):
        plan = InvestigationPlan.model_validate(state["investigation_plan"])
        traces, records = list(state["tool_traces"]), []
        context = dict(state["incident_context"])
        recorded = {}
        anchor_missing = False
        for call in sorted(plan.execution.calls, key=lambda c: c.tool_name != "get_incident"):
            if call.tool_name == "search_internal_policy":
                continue
            if anchor_missing:
                continue
            if call.tool_name != "get_incident":
                call.arguments.since = call.arguments.since or shift_months(
                    self.settings.reference_time, -12
                )
                call.arguments.until = call.arguments.until or self.settings.reference_time
                call.arguments.category = call.arguments.category or context.get("category")
            result, args = self.execute(call, traces)
            if result is None:
                continue
            records.append({"tool_name": call.tool_name, "arguments": args, "result": result})
            if call.tool_name == "get_incident" and not result["incident"]:
                anchor_missing = True
            if call.tool_name == "get_incident" and result["incident"]:
                row = result["incident"]
                reported = context.get("severity")
                reported_category = context.get("category")
                context.update(
                    {
                        k: row[k]
                        for k in (
                            "incident_id",
                            "category",
                            "severity",
                            "downtime_minutes",
                            "customer_impact_count",
                        )
                    }
                )
                recorded = {
                    k: row[k]
                    for k in (
                        "incident_id",
                        "category",
                        "severity",
                        "downtime_minutes",
                        "customer_impact_count",
                        "service",
                        "status",
                        "opened_at",
                    )
                }
                context["source"] = "incident_snapshot"
                if reported:
                    context["reported_severity"] = reported
                if reported_category:
                    context["reported_category"] = reported_category
        return self.step(
            state,
            "analyse_incident_history",
            tool_traces=traces,
            historical_incident_evidence=records,
            recorded_context=recorded,
            incident_context=context,
            investigation_plan=make_plan(state["query"], plan.execution, context).model_dump(
                mode="json"
            ),
        )

    def retrieve_policies(self, state):
        plan = InvestigationPlan.model_validate(state["investigation_plan"])
        call = next(c for c in plan.execution.calls if c.tool_name == "search_internal_policy")
        context = state["incident_context"]
        policy_queries = [
            r.query for r in plan.requirements if r.plane == "policy" and r.dimensions
        ]
        query = " ".join(
            filter(
                None,
                [
                    " ".join(policy_queries) or call.arguments.query,
                    effective_severity(context),
                    context.get("category"),
                ],
            )
        )[:3000]
        call.arguments = SearchPolicyArgs(
            query=query, top_k=call.arguments.top_k, policy_type=call.arguments.policy_type
        )
        traces = list(state["tool_traces"])
        result, _ = self.execute(call, traces)
        return self.step(
            state,
            "retrieve_policies",
            tool_traces=traces,
            retrieved_policy_evidence=result["hits"] if result else [],
            attempted_queries=[call.arguments.model_dump_json()],
        )

    def synthesise_evidence(self, state):
        try:
            values = synthesize(state, self.verifier.chunks, self.tools.as_of)
            return self.step(state, "synthesise_evidence", **values)
        except (ValueError, KeyError):
            return self.step(
                state,
                "synthesise_evidence",
                facts=[],
                evidence=[],
                failed=True,
                error="Evidence synthesis failed validation; generated claims were discarded.",
                severity_assessment={},
                proposed_actions=[],
            )

    def verify_evidence(self, state):
        result = self.verifier.invoke(state)
        return self.step(
            state,
            "verify_evidence",
            verification_result=result.model_dump(mode="json"),
            evidence_gaps=[g.model_dump() for g in result.gaps],
        )

    @staticmethod
    def after_verification(state):
        result = VerificationResult.model_validate(state["verification_result"])
        if state["failed"] or result.integrity_errors or state["route"] == "unsupported":
            return "brief"
        if (
            not result.sufficient
            and state["retry_count"] < 1
            and any(g.retryable for g in result.gaps)
            and len(state["tool_traces"]) < 5
        ):
            return "retry"
        if state["require_review"] or any(
            g.requirement_id.startswith("context:") for g in result.gaps
        ):
            return "review"
        return "brief"

    def targeted_retry(self, state):
        plan = InvestigationPlan.model_validate(state["investigation_plan"])
        gaps = state["verification_result"]["gaps"]
        actionable = [g for g in gaps if g["retryable"]]
        requirements = [
            r
            for r in plan.requirements
            if any(g["requirement_id"].startswith(r.requirement_id) for g in actionable)
        ]
        types = {r.policy_type for r in requirements}
        queries = []
        for coverage in state["verification_result"].get("dimension_coverage", []):
            if coverage["status"] != "missing":
                continue
            req = next(
                (r for r in requirements if coverage["dimension_id"].startswith(r.requirement_id)),
                None,
            )
            if req is None:
                continue
            for c in self.verifier.chunks.values():
                if (
                    c["policy_type"] == req.policy_type
                    and int(c["section"].split(".", 1)[0]) in coverage["missing_sections"]
                ):
                    queries.append(c["title"] + " " + c["section"].split(".", 1)[1].strip())
        query = " ".join(dict.fromkeys(queries)) or requirements[0].query
        args = SearchPolicyArgs(
            # Missing-section titles already identify severity bands where needed.
            # A global severity suffix diluted ownership/clock retrieval across documents.
            query=query[:3000].strip(),
            policy_type=next(iter(types)) if len(types) == 1 else None,
            top_k=8,
        )
        signature = args.model_dump_json()
        traces, hits = list(state["tool_traces"]), list(state["retrieved_policy_evidence"])
        attempts = list(state["attempted_queries"])
        if signature not in attempts:
            result, _ = self.execute(
                PolicyCall(tool_name="search_internal_policy", arguments=args), traces
            )
            attempts.append(signature)
            if result:
                by_id = {h["chunk"]["chunk_id"]: h for h in hits}
                for hit in result["hits"]:
                    validated = PolicyHit.model_validate(hit)
                    by_id[validated.chunk.chunk_id] = hit
                hits = sorted(by_id.values(), key=lambda h: -h["score"])[:14]
        return self.step(
            state,
            "targeted_retry",
            retry_count=1,
            tool_traces=traces,
            retrieved_policy_evidence=hits,
            attempted_queries=attempts,
        )

    def request_review(self, state):
        response = interrupt(
            {
                "kind": "review",
                "message": (
                    "Review findings and unresolved gaps before finalization. "
                    "Acceptance does not execute business actions."
                ),
                "accepted_decisions": ["accept", "decline"],
                "findings": state["facts"],
                "severity_assessment": state["severity_assessment"],
                "proposed_actions": state["proposed_actions"],
                "sources": state["evidence"],
                "gaps": state["evidence_gaps"],
                "read_only": True,
            }
        )
        payload = ResumeRequest.model_validate(response)
        if payload.action != "review":
            raise ValueError("Wrong interrupt response")
        return self.step(
            state,
            "request_review",
            human_review_status="accepted" if payload.decision == "accept" else "declined",
        )

    def generate_investigation_brief(self, state):
        verification = VerificationResult.model_validate(state["verification_result"])
        invalid = state["failed"] or bool(verification.integrity_errors)
        facts, evidence = ([], []) if invalid else (state["facts"], state["evidence"])
        status = (
            "failed"
            if invalid
            else "completed"
            if verification.sufficient
            else "partial"
            if facts
            else "insufficient"
        )
        if state["human_review_status"] == "declined" and status == "completed":
            status = "partial"
        policy = [f for f in facts if f["kind"] == "policy_requirement"]
        history = [f for f in facts if f["kind"] == "historical_fact"]
        recommendations = [] if invalid else state.get("proposed_actions", [])
        limits = [
            "All policies and incidents are synthetic; business tools remain read-only.",
            "Policy establishes process; snapshot history does not prove causality or compliance.",
            "Topic/severity coverage uses bounded rules; semantic completeness is not guaranteed.",
            "Samples may include the reference incident; they do not prove root cause.",
            "Metrics exclude unknown/unresolved durations; customer counts are incident exposures.",
            "Relative dates use 2026-10-01 UTC; current policy does not prove past compliance.",
        ]
        if state["human_review_status"] == "declined":
            limits.append("Human reviewer declined finalization; findings require further review.")
        brief = InvestigationBrief(
            executive_summary=(
                (
                    "Investigation failed validation; unsupported findings and proposals "
                    "were discarded."
                )
                if invalid
                else executive_summary(state, status)
            ),
            incident_context_and_severity=context_summary(state),
            severity_assessment=None if invalid else state.get("severity_assessment"),
            context_observations=observations(state),
            applicable_internal_policies=policy,
            historical_incident_comparison=history,
            key_findings=facts,
            recommended_next_steps=recommendations,
            evidence_gaps=verification.gaps,
            source_citations=evidence,
            investigation_status=status,
            tool_trace=state["tool_traces"],
            workflow_trace=state["workflow_trace"] + ["generate_investigation_brief", "finalize"],
            limitations=limits,
        )
        return self.step(
            state,
            "generate_investigation_brief",
            investigation_brief=brief.model_dump(mode="json"),
            completion_status=status,
        )

    def finalize(self, state):
        return self.step(state, "finalize")
