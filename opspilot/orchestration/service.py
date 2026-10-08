import hashlib
import json
import logging
import re
import sqlite3
import time
from datetime import UTC
from uuid import uuid4

from opspilot.config import Settings
from opspilot.data.repository import IncidentRepository
from opspilot.domain.models import (
    AnswerFact,
    EvidenceRef,
    IncidentResult,
    MetricsResult,
    OpsPilotResponse,
    PolicyResult,
    PolicySelection,
    RoutePlan,
    SimilarResult,
    ToolResult,
    ToolTrace,
    Usage,
)
from opspilot.orchestration.grounding import (
    explicitly_missing,
    policy_question,
    select_extractive,
    validate_selection,
)
from opspilot.orchestration.routing import DeterministicPlanner, shift_months, unsafe_request
from opspilot.providers.chat_api import ChatAPI, ProviderError
from opspilot.providers.embedding_api import APIEmbeddings
from opspilot.providers.embeddings import TfidfEmbeddings
from opspilot.rag.vectorstore import JsonVectorStore
from opspilot.tools.registry import ReadOnlyTools

logger = logging.getLogger("opspilot.requests")


def embedding_provider(settings: Settings):
    return (
        APIEmbeddings(settings)
        if settings.embedding_provider == "embedding_api"
        else TfidfEmbeddings()
    )


class OpsPilotService:
    def __init__(self, settings: Settings, provider: ChatAPI | None = None):
        self.settings = settings
        self.store = JsonVectorStore(settings.vector_index, embedding_provider(settings))
        self.tools = ReadOnlyTools(
            self.store, IncidentRepository(settings.incident_db), settings.reference_time.date()
        )
        self.planner = DeterministicPlanner()
        self.provider = provider or (
            ChatAPI(settings) if settings.llm_provider == "chat_api" else None
        )

    def ready(self) -> bool:
        try:
            self.store.snapshot()
            return self.tools.incidents.get("INC-001") is not None
        except (OSError, ValueError, KeyError, RuntimeError, sqlite3.Error):
            return False

    def ask(self, question: str, request_id: str | None = None) -> OpsPilotResponse:
        start = time.perf_counter()
        request_id = request_id or str(uuid4())
        traces, results, evidence, facts = [], [], [], []
        limitations = [
            "All policies and incident records are fictional synthetic demo data.",
            "V1 tools are read-only; no actions or notifications are executed.",
        ]
        usage = Usage()
        provider_failed = False
        if unsafe_request(question):
            plan = RoutePlan(route="unsupported")
        elif self.provider:
            try:
                plan, current_usage = self.provider.plan(
                    question, service_catalog=self.tools.incidents.planning_catalog()
                )
                usage.input_tokens += current_usage.input_tokens
                usage.output_tokens += current_usage.output_tokens
            except (ProviderError, ValueError, sqlite3.Error):
                plan, provider_failed = RoutePlan(route="unsupported"), True
                limitations.append(
                    "Configured provider or planning metadata failed; no tools were executed."
                )
        else:
            try:
                plan = self.planner.plan(
                    question, self.settings.reference_time, self.settings.top_k
                )
            except ValueError:
                plan = RoutePlan(route="unsupported")
                limitations.append(
                    "The query's filters are invalid or ambiguous; supply explicit UTC dates."
                )

        if len(plan.calls) > self.settings.max_tool_calls:
            plan = RoutePlan(route="unsupported")
            limitations.append("The request exceeds the configured tool-call budget.")
        if {"find_similar_incidents", "calculate_incident_metrics"}.issubset(
            {call.tool_name for call in plan.calls}
        ) and not re.search(
            r"\b(similar|examples?|samples?|list|show|find)\b|類似|相似|例子|列出|舉例",
            question,
            re.I,
        ):
            # Aggregates use the complete cohort; an unrequested sample adds no evidence.
            plan.calls = [c for c in plan.calls if c.tool_name != "find_similar_incidents"]
            plan = RoutePlan.model_validate(plan.model_dump())
            limitations.append(
                "An unrequested similarity sample was omitted; "
                "metrics cover the requested aggregate population."
            )
        # A provider cannot introduce an unmentioned scenario duration.
        if plan.current_duration_minutes is not None and not re.search(
            rf"\b{plan.current_duration_minutes}\s+minutes\b", question, re.I
        ):
            plan.current_duration_minutes = None

        policy_hits, selection, data_missing = [], PolicySelection(sufficient=False), False
        anchor = None
        metric_result = None
        metric_evidence_id = None
        # Anchor first so subsequent similarity filters can be derived from the actual record.
        calls = sorted(plan.calls, key=lambda c: c.tool_name != "get_incident")
        for call in calls:
            if call.tool_name == "search_internal_policy":
                call.arguments.top_k = min(call.arguments.top_k, self.settings.top_k)
                call.arguments.query = policy_question(question)
                if re.search(r"escalat", call.arguments.query, re.I):
                    call.arguments.query += " notify notification"
                if anchor:
                    call.arguments.query += (
                        f" {anchor.severity} {anchor.category.replace('_', ' ')}"
                    )
            elif call.tool_name in {"find_similar_incidents", "calculate_incident_metrics"}:
                if call.arguments.since is None:
                    call.arguments.since = shift_months(self.settings.reference_time, -12)
                if call.arguments.until is None:
                    call.arguments.until = self.settings.reference_time
                if anchor:
                    call.arguments.category = call.arguments.category or anchor.category
                    call.arguments.service = call.arguments.service or anchor.service
            args = call.arguments.model_dump(mode="json", exclude_none=True)
            tool_start = time.perf_counter()
            try:
                call.arguments = type(call.arguments).model_validate(call.arguments.model_dump())
                result = self.tools.execute(call)
            except (OSError, ValueError, RuntimeError, sqlite3.Error):
                traces.append(
                    ToolTrace(
                        tool_name=call.tool_name,
                        arguments=args,
                        status="failed",
                        summary="Evidence source unavailable; no result used.",
                        latency_ms=(time.perf_counter() - tool_start) * 1000,
                    )
                )
                data_missing |= call.tool_name != "search_internal_policy"
                limitations.append(f"{call.tool_name} could not access validated evidence.")
                continue
            results.append(
                ToolResult(tool_name=call.tool_name, result=result.model_dump(mode="json"))
            )
            if isinstance(result, PolicyResult):
                policy_hits = result.hits
                summary = f"Retrieved {len(policy_hits)} active internal policy chunks."
            else:
                serialized = result.model_dump(mode="json")
                evidence_id = (
                    "db:"
                    + call.tool_name
                    + ":"
                    + hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()[:12]
                )
                data_ref = EvidenceRef(
                    evidence_id=evidence_id,
                    source_type="incident_db",
                    source_id="harbourlink-incidents-v1",
                    title="HarbourLink synthetic incident snapshot",
                    section=call.tool_name,
                    excerpt=json.dumps(serialized, sort_keys=True),
                )
                if isinstance(result, IncidentResult):
                    anchor = result.incident
                    summary = "Incident found." if anchor else "Incident not found."
                    if anchor:
                        evidence.append(data_ref)
                        facts.append(
                            AnswerFact(
                                kind="historical_fact",
                                evidence_ids=[evidence_id],
                                text=f"{anchor.incident_id}: {anchor.category.replace('_', ' ')}, "
                                f"{anchor.severity}, "
                                f"{anchor.service}, {anchor.status}; "
                                "downtime="
                                + (
                                    f"{anchor.downtime_minutes} minutes"
                                    if anchor.downtime_minutes is not None
                                    else "not recorded"
                                )
                                + "; "
                                f"customer impact={anchor.customer_impact_count}. "
                                f"Opened {anchor.opened_at.astimezone(UTC).isoformat()}.",
                            )
                        )
                    else:
                        data_missing = True
                        limitations.append("The requested incident ID is absent from the snapshot.")
                elif isinstance(result, SimilarResult):
                    evidence.append(data_ref)
                    summary = (
                        f"Returned {len(result.incidents)} of "
                        f"{result.total_matches} matching incidents."
                    )
                    ids = ", ".join(r.incident_id for r in result.incidents) or "none"
                    facts.append(
                        AnswerFact(
                            kind="historical_fact",
                            evidence_ids=[evidence_id],
                            text=f"Matching incidents: {result.total_matches}; "
                            f"most recent sample: {ids}. "
                            f"Filters: {json.dumps(result.filters, sort_keys=True)}.",
                        )
                    )
                    limitations.append(
                        "Similar incidents are exact-filter matches, "
                        "not causal or semantic matches; "
                        "the displayed list is a bounded sample "
                        "and may include the reference incident."
                    )
                elif isinstance(result, MetricsResult):
                    evidence.append(data_ref)
                    metric_result, metric_evidence_id = result, evidence_id
                    summary = f"Calculated metrics for {result.incident_count} incidents."

                    def duration_text(value: float | None) -> str:
                        return (
                            f"{value:g} minutes"
                            if value is not None
                            else "N/A (no known resolved duration)"
                        )

                    text = (
                        f"Incident count: {result.incident_count}; median downtime: "
                        f"{duration_text(result.median_downtime_minutes)}; mean downtime: "
                        f"{duration_text(result.mean_downtime_minutes)}; "
                        "p90 downtime (nearest-rank): "
                        f"{duration_text(result.p90_downtime_minutes)}. "
                        "Resolved known-duration sample: "
                        f"{result.downtime_sample_count}; "
                        "excluded/open or missing-duration records: "
                        f"{result.missing_downtime_count}. "
                        "Total customer-impact exposures: "
                        f"{result.total_customer_impact}; "
                        f"mean exposure: {result.mean_customer_impact}. "
                        f"Filters: {json.dumps(result.filters, sort_keys=True)}."
                    )
                    if result.group_counts:
                        text += (
                            " Group counts: "
                            + json.dumps(result.group_counts, sort_keys=True)
                            + "."
                        )
                    text += (
                        " Severity distribution: "
                        + json.dumps(result.severity_distribution, sort_keys=True)
                        + "."
                    )
                    facts.append(
                        AnswerFact(kind="historical_fact", text=text, evidence_ids=[evidence_id])
                    )
                    limitations.extend(
                        [
                            "Duration metrics use resolved records with known downtime; "
                            "downtime differs from opened-to-resolved time.",
                            "Customer-impact totals are incident exposures, "
                            "not deduplicated unique customers.",
                            "Time filters use opened_at, inclusive since / exclusive until; "
                            "relative windows use "
                            + self.settings.reference_time.isoformat()
                            + ".",
                        ]
                    )
            traces.append(
                ToolTrace(
                    tool_name=call.tool_name,
                    arguments=args,
                    status="success",
                    summary=summary,
                    latency_ms=(time.perf_counter() - tool_start) * 1000,
                )
            )

        if plan.route in {"policy_only", "mixed"}:
            try:
                if (
                    self.provider
                    and policy_hits
                    and not explicitly_missing(policy_question(question))
                ):
                    selection, current_usage = self.provider.select(
                        policy_question(question),
                        [
                            {
                                "evidence_id": h.chunk.chunk_id,
                                "title": h.chunk.title,
                                "section": h.chunk.section,
                                "paragraphs": h.chunk.content.split("\n\n"),
                            }
                            for h in policy_hits
                        ],
                        incident_context=anchor.model_dump(
                            mode="json",
                            include={
                                "incident_id",
                                "severity",
                                "category",
                                "service",
                                "business_unit",
                                "status",
                                "customer_impact_count",
                                "downtime_minutes",
                                "opened_at",
                            },
                        )
                        if anchor
                        else None,
                    )
                    usage.input_tokens += current_usage.input_tokens
                    usage.output_tokens += current_usage.output_tokens
                elif not self.provider:
                    selection = select_extractive(question, policy_hits)
                validate_selection(selection, policy_hits)
            except (ProviderError, ValueError):
                selection = PolicySelection(sufficient=False)
                limitations.append(
                    "Policy selection failed evidence validation; "
                    "no generated policy claim was used."
                )
            if selection.sufficient:
                by_id = {h.chunk.chunk_id: h for h in policy_hits}
                policy_facts = []
                for quote in selection.quotes:
                    hit = by_id[quote.evidence_id]
                    chunk = hit.chunk
                    evidence.append(
                        EvidenceRef(
                            evidence_id=chunk.chunk_id,
                            source_type="internal_policy",
                            source_id=chunk.document_id,
                            title=chunk.title,
                            section=chunk.section,
                            excerpt=quote.quote,
                            chunk_id=chunk.chunk_id,
                            version=chunk.version,
                            effective_date=chunk.effective_date,
                            score=hit.score,
                        )
                    )
                    policy_facts.append(
                        AnswerFact(
                            kind="policy_requirement",
                            text=quote.quote,
                            evidence_ids=[chunk.chunk_id],
                        ),
                    )
                facts = policy_facts + facts
            else:
                limitations.append(
                    "Insufficient internal evidence for the requested policy detail; "
                    "no web or prior-knowledge fallback."
                )

        duration = plan.current_duration_minutes
        if (
            duration is not None
            and metric_result
            and metric_result.median_downtime_minutes is not None
        ):
            median = metric_result.median_downtime_minutes
            difference = round(duration - median, 4)
            facts.append(
                AnswerFact(
                    kind="interpretation",
                    evidence_ids=[metric_evidence_id],
                    text=f"The supplied scenario duration ({duration} minutes) "
                    f"is {difference:+g} minutes "
                    f"relative to the matching historical median ({median:g} minutes). "
                    "This comparison is context, not an approved restoration deadline.",
                )
            )
        if plan.route == "mixed":
            limitations.append(
                "Current policy is not evidence that pre-effective-date incidents "
                "complied with this version."
            )
        if not self.provider:
            limitations.append(
                "Offline extractive baseline uses English intent rules and lexical vectors; "
                "semantic paraphrases may require chat_api/dense embeddings."
            )

        missing_policy = plan.route in {"policy_only", "mixed"} and not selection.sufficient
        insufficient = missing_policy or data_missing or plan.route == "unsupported"
        sufficiency = (
            "partial" if insufficient and facts else "insufficient" if insufficient else "supported"
        )
        refs = {e.evidence_id: e for e in evidence}
        labels = {
            "policy_requirement": "Policy requirement",
            "historical_fact": "Historical fact",
            "interpretation": "Interpretation",
        }
        paragraphs = []
        for fact in facts:
            citations = [f"{refs[i].title} | {refs[i].section} | {i}" for i in fact.evidence_ids]
            paragraphs.append(
                labels[fact.kind] + ": " + fact.text + " [" + "; ".join(citations) + "]"
            )
        if insufficient:
            if plan.route == "unsupported":
                paragraphs.insert(
                    0,
                    "This V1 assistant supports read-only operational policy "
                    "and incident investigation. "
                    "It cannot execute writes, notifications or bypass controls.",
                )
            else:
                paragraphs.insert(
                    0,
                    "Insufficient evidence for part or all of this request. "
                    "The supported facts are shown below.",
                )
        if (
            self.settings.input_cost_per_million is not None
            and self.settings.output_cost_per_million is not None
        ):
            usage.estimated_cost_usd = (
                usage.input_tokens * self.settings.input_cost_per_million
                + usage.output_tokens * self.settings.output_cost_per_million
            ) / 1_000_000
        response = OpsPilotResponse(
            request_id=request_id,
            route=plan.route,
            answer="\n\n".join(paragraphs),
            confidence="insufficient_evidence" if insufficient else "high",
            evidence_sufficiency=sufficiency,
            evidence=evidence,
            facts=facts,
            tool_trace=traces,
            tool_results=results,
            limitations=list(dict.fromkeys(limitations)),
            latency_ms=(time.perf_counter() - start) * 1000,
            mode=self.settings.llm_provider,
            usage=usage,
        )
        logger.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "route": plan.route,
                    "outcome": sufficiency,
                    "tools": [{"name": t.tool_name, "status": t.status} for t in traces],
                    "source_ids": sorted({e.source_id for e in evidence}),
                    "latency_ms": response.latency_ms,
                    "provider_failed": provider_failed,
                }
            )
        )
        return response
