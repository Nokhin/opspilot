"""Bounded public contracts and JSON-only LangGraph state."""

from typing import Any, Literal, TypedDict

from pydantic import AwareDatetime, Field, StrictBool, model_validator

from opspilot.domain.models import (
    AnswerFact,
    Category,
    Contract,
    EvidenceRef,
    Route,
    RoutePlan,
    Severity,
    ToolTrace,
    Usage,
)

Completion = Literal["running", "awaiting_human", "completed", "partial", "insufficient", "failed"]
InvestigationMode = Literal["offline", "configured", "chatgpt_subscription"]
PlanningRejectionCode = Literal[
    "tool_budget_exceeded",
    "route_mismatch",
    "missing_required_tools",
    "unreported_incident_id",
    "unreported_duration",
    "provider_call_budget_exhausted",
    "provider_or_output_failure",
    "evidence_source_unavailable",
    "invalid_plan_schema",
]
ToolName = Literal[
    "search_internal_policy", "get_incident", "find_similar_incidents", "calculate_incident_metrics"
]


class PlanningDiagnostic(Contract):
    """Safe rejection metadata only: no prompts, arguments, raw plans or exception text."""

    code: PlanningRejectionCode
    stage: Literal["requirements", "provider", "validation"]
    required_route: Route | None = None
    proposed_route: Route | None = None
    required_tools: list[ToolName] = Field(default_factory=list, max_length=4)
    proposed_tools: list[ToolName] = Field(default_factory=list, max_length=4)


class IncidentContext(Contract):
    incident_id: str | None = Field(default=None, pattern=r"^INC-\d{3}$")
    category: Category | None = None
    severity: Severity | None = None
    downtime_minutes: int | None = Field(default=None, ge=0, le=100000, strict=True)
    customer_impact_count: int | None = Field(default=None, ge=0, le=10000000, strict=True)
    customer_facing: StrictBool | None = None
    immediate_danger: StrictBool | None = None
    multi_site_essential_closure: StrictBool | None = None
    single_site_disruption: StrictBool | None = None
    duplicate_capture_confirmed: StrictBool | None = None
    workaround_available: StrictBool | None = None
    integrity_concern: StrictBool | None = None
    no_customer_interruption: StrictBool | None = None
    local_degradation: StrictBool | None = None
    minor_operational_defect: StrictBool | None = None
    threshold_detected_at: AwareDatetime | None = None


ContextField = Literal[
    "incident_id",
    "category",
    "severity",
    "downtime_minutes",
    "customer_impact_count",
    "customer_facing",
    "immediate_danger",
    "multi_site_essential_closure",
    "single_site_disruption",
    "duplicate_capture_confirmed",
    "workaround_available",
    "integrity_concern",
    "no_customer_interruption",
    "local_degradation",
    "minor_operational_defect",
    "threshold_detected_at",
]


class ContextObservation(Contract):
    field: str
    value: str | int | bool | None
    origin: Literal["user_reported", "incident_snapshot"]
    evidence_ids: list[str] = Field(default_factory=list)


class SeverityAssessment(Contract):
    recorded_severity: Severity | None = None
    reported_severity: Severity | None = None
    proposed_severity: Severity | None = None
    status: Literal["supported", "provisional", "insufficient", "not_requested"]
    basis: list[str] = Field(default_factory=list, max_length=8)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    context_observations: list[ContextObservation] = Field(default_factory=list, max_length=40)
    missing_fields: list[ContextField] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class EvidenceDimension(Contract):
    dimension_id: str
    description: str
    section_numbers: list[int] = Field(max_length=6)


class DimensionCoverage(Contract):
    dimension_id: str
    status: Literal["supported", "missing"]
    evidence_ids: list[str] = Field(default_factory=list)
    missing_sections: list[int] = Field(default_factory=list)


class InvestigationRequest(Contract):
    user_request: str = Field(min_length=2, max_length=3000)
    incident_context: IncidentContext = Field(default_factory=IncidentContext)
    require_review: bool = False
    mode: InvestigationMode = "offline"


class SubscriptionBinding(Contract):
    """Internal registry reference only; never contains OAuth tokens or enters graph state."""

    profile_id: str = Field(min_length=1, max_length=80, repr=False)
    model: str = Field(min_length=1, max_length=128)


class ResumeRequest(Contract):
    action: Literal["clarify", "review"]
    incident_context: IncidentContext | None = None
    decision: Literal["accept", "decline"] | None = None
    unknown_fields: list[ContextField] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def valid_response(self):
        if self.action == "clarify":
            if self.decision is not None:
                raise ValueError("Clarification cannot include a review decision")
            supplied = (
                self.incident_context.model_dump(exclude_none=True) if self.incident_context else {}
            )
            if not supplied and not self.unknown_fields:
                raise ValueError("Provide at least one incident fact")
            if set(supplied) & set(self.unknown_fields) or len(set(self.unknown_fields)) != len(
                self.unknown_fields
            ):
                raise ValueError("Known and unknown fields must be disjoint and unique")
        elif self.incident_context is not None or self.decision is None or self.unknown_fields:
            raise ValueError("Review requires accept or decline only")
        return self


class EvidenceRequirement(Contract):
    requirement_id: str
    plane: Literal["policy", "history"]
    description: str = Field(max_length=250)
    policy_type: str | None = None
    tool_name: str | None = None
    section_numbers: list[int] = Field(default_factory=list, max_length=6)
    query: str | None = Field(default=None, max_length=3000)
    dimensions: list[EvidenceDimension] = Field(default_factory=list, max_length=6)


class InvestigationPlan(Contract):
    execution: RoutePlan
    requirements: list[EvidenceRequirement] = Field(max_length=14)


class EvidenceGap(Contract):
    requirement_id: str
    description: str
    retryable: bool = False


class VerificationResult(Contract):
    sufficient: bool
    covered_requirements: list[str]
    gaps: list[EvidenceGap]
    integrity_errors: list[str]
    dimension_coverage: list[DimensionCoverage] = Field(default_factory=list)
    advisory: str = "Deterministic domain checks; semantic completeness is not guaranteed."


class ProposedAction(Contract):
    text: str
    evidence_ids: list[str]
    status: Literal["proposed_not_executed"] = "proposed_not_executed"
    owner_role: str = "Responsible human owner (confirmation required)"
    trigger: str = "Applicability must be confirmed by a human"
    deadline_minutes: int | None = Field(default=None, ge=0)
    deadline_basis: str | None = None
    due_at: AwareDatetime | None = None
    retrospective: bool = False


class InvestigationBrief(Contract):
    executive_summary: str
    incident_context_and_severity: str
    applicable_internal_policies: list[AnswerFact]
    historical_incident_comparison: list[AnswerFact]
    key_findings: list[AnswerFact]
    recommended_next_steps: list[ProposedAction]
    evidence_gaps: list[EvidenceGap]
    source_citations: list[EvidenceRef]
    investigation_status: Completion
    tool_trace: list[ToolTrace]
    workflow_trace: list[str]
    limitations: list[str]
    severity_assessment: SeverityAssessment | None = None
    context_observations: list[ContextObservation] = Field(default_factory=list)


class InvestigationResponse(Contract):
    investigation_id: str
    completion_status: Completion
    route: Route
    investigation_plan: InvestigationPlan | None = None
    verification_result: VerificationResult | None = None
    clarification_request: dict[str, Any] | None = None
    human_review_status: Literal["not_required", "pending", "accepted", "declined"]
    retry_count: int = Field(ge=0, le=1)
    investigation_brief: InvestigationBrief | None = None
    workflow_trace: list[str]
    tool_traces: list[ToolTrace]
    usage: Usage
    latency_ms: float
    usage_complete: bool = True
    mode: InvestigationMode
    model: str | None = Field(default=None, max_length=128)
    provider_call_count: int = Field(default=0, ge=0, le=1)
    planning_diagnostic: PlanningDiagnostic | None = None
    error: str | None = None
    synthetic_data: Literal[True] = True
    severity_assessment: SeverityAssessment | None = None


class InvestigationCreated(InvestigationResponse):
    owner_token: str = Field(repr=False)


class InvestigationState(TypedDict, total=False):
    """Only bounded JSON primitives are checkpointed; no clients, keys or model objects."""

    investigation_id: str
    user_request: str
    incident_context: dict
    investigation_plan: dict
    route: str
    retrieved_policy_evidence: list[dict]
    historical_incident_evidence: list[dict]
    tool_traces: list[dict]
    evidence_gaps: list[dict]
    verification_result: dict
    retry_count: int
    clarification_request: dict | None
    human_review_status: str
    investigation_brief: dict | None
    completion_status: str
    usage: dict
    latency_ms: float
    usage_complete: bool
    mode: str
    require_review: bool
    workflow_trace: list[str]
    facts: list[dict]
    evidence: list[dict]
    limitations: list[str]
    query: str
    failed: bool
    error: str | None
    clarification_done: bool
    attempted_queries: list[str]
    snapshot_identity: str
    reported_context: dict
    recorded_context: dict
    unknown_fields: list[str]
    severity_assessment: dict
    proposed_actions: list[dict]
    model: str | None
    provider_call_count: int
    planning_diagnostic: dict | None
