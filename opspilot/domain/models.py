from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, model_validator

Category = Literal[
    "digital_outage",
    "payment_failure",
    "facility_disruption",
    "customer_impact",
    "data_integrity",
    "vendor_disruption",
]
Severity = Literal["SEV1", "SEV2", "SEV3", "SEV4"]
BusinessUnit = Literal[
    "Operations", "Customer Service", "Digital Services", "Facilities", "Risk & Compliance"
]
Status = Literal["open", "investigating", "resolved"]
Route = Literal["policy_only", "data_only", "mixed", "unsupported"]
PolicyType = Literal[
    "classification",
    "escalation",
    "recovery",
    "communication",
    "continuity",
    "vendor",
    "review",
    "retention",
    "payment",
    "facility",
]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Incident(Contract):
    incident_id: str = Field(pattern=r"^INC-\d{3}$")
    opened_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    category: Category
    subcategory: str
    severity: Severity
    business_unit: BusinessUnit
    service: str = Field(min_length=1, max_length=80)
    site: str
    customer_impact_count: NonNegativeInt
    downtime_minutes: NonNegativeInt | None = None
    estimated_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    root_cause: str | None = None
    vendor_related: bool
    status: Status
    resolution_summary: str | None = None
    post_incident_review_required: bool

    @model_validator(mode="after")
    def validate_times(self):
        if self.resolved_at and self.resolved_at < self.opened_at:
            raise ValueError("resolved_at cannot precede opened_at")
        if (self.status == "resolved") != (self.resolved_at is not None):
            raise ValueError("resolved status and resolved_at must agree")
        return self


class IncidentFilters(Contract):
    category: Category | None = None
    severity: Severity | None = None
    business_unit: BusinessUnit | None = None
    service: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Exact named service from the catalog; null for generic category wording.",
    )
    status: Status | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    vendor_related: bool | None = None
    min_customer_impact: NonNegativeInt | None = Field(
        default=None,
        description="Explicit historical cohort threshold; not the current scenario's impact.",
    )

    @model_validator(mode="after")
    def validate_window(self):
        if self.since and self.until and self.since >= self.until:
            raise ValueError("since must precede until (half-open UTC window)")
        return self


class SearchPolicyArgs(Contract):
    query: str = Field(min_length=2, max_length=3000)
    policy_type: PolicyType | None = Field(
        default=None,
        description="Explicit metadata restriction only. Default null; do not infer from topic.",
    )
    top_k: int = Field(default=6, ge=1, le=8)


class GetIncidentArgs(Contract):
    incident_id: str = Field(pattern=r"^INC-\d{3}$")


class SimilarIncidentArgs(IncidentFilters):
    limit: int = Field(default=5, ge=1, le=20)


class MetricsArgs(IncidentFilters):
    group_by: Literal["category", "severity", "business_unit", "service", "status"] | None = None


class PolicyCall(Contract):
    tool_name: Literal["search_internal_policy"]
    arguments: SearchPolicyArgs


class IncidentCall(Contract):
    tool_name: Literal["get_incident"]
    arguments: GetIncidentArgs


class SimilarCall(Contract):
    tool_name: Literal["find_similar_incidents"] = Field(
        description="Bounded recent examples and total matches; not aggregate duration statistics."
    )
    arguments: SimilarIncidentArgs


class MetricsCall(Contract):
    tool_name: Literal["calculate_incident_metrics"] = Field(
        description="Whole-cohort counts, medians, distributions and duration comparisons."
    )
    arguments: MetricsArgs


ToolCall = Annotated[
    PolicyCall | IncidentCall | SimilarCall | MetricsCall, Field(discriminator="tool_name")
]


class RoutePlan(Contract):
    route: Route
    calls: list[ToolCall] = Field(
        default_factory=list,
        max_length=4,
        description="Each tool at most once. One policy search can retrieve multiple documents.",
    )
    current_duration_minutes: NonNegativeInt | None = Field(
        default=None, description="Explicit scenario duration to compare with historical metrics."
    )

    @model_validator(mode="after")
    def validate_evidence_planes(self):
        names = [c.tool_name for c in self.calls]
        if len(names) != len(set(names)):
            raise ValueError("duplicate tools are not allowed in V1")
        policy = "search_internal_policy" in names
        data = any(n != "search_internal_policy" for n in names)
        expected = {
            "policy_only": (True, False),
            "data_only": (False, True),
            "mixed": (True, True),
            "unsupported": (False, False),
        }
        if (policy, data) != expected[self.route]:
            raise ValueError("route and required evidence planes disagree")
        return self


class PolicyChunk(Contract):
    document_id: str
    title: str
    version: str
    effective_date: date
    owner: str
    policy_type: PolicyType
    status: Literal["active"]
    section: str
    chunk_id: str
    content: str = Field(min_length=1)


class PolicyHit(Contract):
    chunk: PolicyChunk
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class PolicyResult(Contract):
    hits: list[PolicyHit]


class IncidentResult(Contract):
    incident: Incident | None


class SimilarResult(Contract):
    incidents: list[Incident]
    filters: dict[str, Any]
    total_matches: NonNegativeInt


class MetricsResult(Contract):
    filters: dict[str, Any]
    incident_count: NonNegativeInt
    resolved_count: NonNegativeInt
    downtime_sample_count: NonNegativeInt
    missing_downtime_count: NonNegativeInt
    mean_downtime_minutes: float | None
    median_downtime_minutes: float | None
    p90_downtime_minutes: float | None
    total_customer_impact: NonNegativeInt
    mean_customer_impact: float | None
    severity_distribution: dict[str, int]
    group_counts: dict[str, int]
    repeat_incident_count_by_service: dict[str, int]
    window_basis: Literal["opened_at; since inclusive, until exclusive"] = (
        "opened_at; since inclusive, until exclusive"
    )


class EvidenceRef(Contract):
    evidence_id: str
    source_type: Literal["internal_policy", "incident_db"]
    source_id: str
    title: str
    section: str
    excerpt: str
    chunk_id: str | None = None
    version: str | None = None
    effective_date: date | None = None
    score: float | None = None


class ToolTrace(Contract):
    tool_name: str
    arguments: dict[str, Any]
    status: Literal["success", "failed", "skipped"]
    summary: str
    latency_ms: float


class ToolResult(Contract):
    tool_name: str
    result: dict[str, Any]


class AnswerFact(Contract):
    kind: Literal["policy_requirement", "historical_fact", "interpretation"]
    text: str
    evidence_ids: list[str]


class Usage(Contract):
    input_tokens: NonNegativeInt = 0
    output_tokens: NonNegativeInt = 0
    estimated_cost_usd: float | None = None


class OpsPilotResponse(Contract):
    request_id: str
    route: Route
    answer: str
    confidence: Literal["high", "medium", "low", "insufficient_evidence"]
    evidence_sufficiency: Literal["supported", "partial", "insufficient"]
    evidence: list[EvidenceRef]
    facts: list[AnswerFact]
    tool_trace: list[ToolTrace]
    tool_results: list[ToolResult]
    limitations: list[str]
    latency_ms: float
    mode: Literal["extractive", "chat_api"]
    usage: Usage


class ChatRequest(Contract):
    question: str = Field(min_length=2, max_length=3000)


class PolicyQuote(Contract):
    evidence_id: str
    quote: str = Field(min_length=20, max_length=1800)


class PolicySelection(Contract):
    sufficient: bool
    quotes: list[PolicyQuote] = Field(default_factory=list, max_length=8)
