from datetime import date

from opspilot.data.repository import IncidentRepository
from opspilot.domain.models import (
    GetIncidentArgs,
    IncidentResult,
    MetricsArgs,
    MetricsResult,
    PolicyResult,
    SearchPolicyArgs,
    SimilarIncidentArgs,
    SimilarResult,
    ToolCall,
)
from opspilot.rag.vectorstore import VectorStore


class ReadOnlyTools:
    permission = "read_only"
    tool_names = frozenset(
        {
            "search_internal_policy",
            "get_incident",
            "find_similar_incidents",
            "calculate_incident_metrics",
        }
    )

    def __init__(self, policies: VectorStore, incidents: IncidentRepository, as_of: date):
        self.policies = policies
        self.incidents = incidents
        self.as_of = as_of

    def search_internal_policy(self, args: SearchPolicyArgs) -> PolicyResult:
        return PolicyResult(hits=self.policies.search(args, self.as_of))

    def get_incident(self, args: GetIncidentArgs) -> IncidentResult:
        return IncidentResult(incident=self.incidents.get(args.incident_id))

    def find_similar_incidents(self, args: SimilarIncidentArgs) -> SimilarResult:
        return self.incidents.find_similar(args)

    def calculate_incident_metrics(self, args: MetricsArgs) -> MetricsResult:
        return self.incidents.metrics(args)

    def execute(self, call: ToolCall):
        # Explicit dispatch: no dynamic attribute, SQL, shell, file, or network tool.
        if call.tool_name == "search_internal_policy":
            return self.search_internal_policy(call.arguments)
        if call.tool_name == "get_incident":
            return self.get_incident(call.arguments)
        if call.tool_name == "find_similar_incidents":
            return self.find_similar_incidents(call.arguments)
        if call.tool_name == "calculate_incident_metrics":
            return self.calculate_incident_metrics(call.arguments)
        raise ValueError("Tool is not allow-listed")
