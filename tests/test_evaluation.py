import json
from pathlib import Path

import pytest

from opspilot.evaluation.runner import EvaluationCase, grade, run_evaluation


@pytest.mark.parametrize("case_file", ["cases.json", "cases_v1_1.json"])
def test_fifty_case_regression_outputs_and_frozen_numbers(service, tmp_path, case_file):
    summary = run_evaluation(service, Path("opspilot/evaluation") / case_file, tmp_path)
    assert summary["cases"] == 50
    assert summary["passed"] == 50
    assert summary["deterministic_result_accuracy"] == 1
    assert summary["by_category"]["safety"]["passed"] == 4
    assert (tmp_path / "SUMMARY.md").is_file()
    assert (tmp_path / "cases.csv").is_file()
    data = json.loads((tmp_path / "results.json").read_text())
    assert data["manifest"]["mode"] == "extractive"
    assert data["manifest"]["cases_sha256"]


def test_grader_detects_fabricated_quote_and_wrong_number(service):
    response = service.ask("What escalation policy applies to SEV1?")
    response.facts[0].text = "Invented company procedure requiring immediate cash payment."
    case = EvaluationCase(
        id="negative",
        category="policy",
        question="policy",
        expected_route="policy_only",
        expected_tools=["search_internal_policy"],
    )
    chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
    assert not grade(case, response, chunks)["checks"]["citation_integrity"]
    data_response = service.ask("How many payment incidents occurred in the last year?")
    data_case = EvaluationCase(
        id="numeric",
        category="data",
        question="data",
        expected_route="data_only",
        expected_tools=["calculate_incident_metrics"],
        expected_results={"calculate_incident_metrics": {"incident_count": 999}},
    )
    assert not grade(data_case, data_response, chunks)["checks"]["numeric_results"]
