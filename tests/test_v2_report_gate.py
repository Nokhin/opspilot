"""Offline release gates preserve legacy scores and reject undocumented differences."""

import json
import shutil
from pathlib import Path

import pytest

from scripts.check_v2_reports import check_reports


@pytest.fixture
def reports(tmp_path):
    mapping = {
        "v2-completion-development": "completion-development",
        "v2-completion-reserved": "completion-reserved-regression",
        "v2-evidence-development": "new-development",
        "v2-legacy-development": "legacy-development",
        "v2-legacy-reserved": "legacy-reserved-regression",
    }
    for suite, source in mapping.items():
        target = tmp_path / suite
        target.mkdir()
        shutil.copyfile(
            Path("evaluation/v2_evidence_gap_fix") / source / "results.json",
            target / "results.json",
        )
    return tmp_path


def test_gate_accepts_current_suites_and_preserves_exact_legacy_scores(reports):
    checked = {row["suite"]: row for row in check_reports(reports, Path("opspilot/evaluation"))}
    assert checked["v2-completion-development"]["passed"] == 28
    assert checked["v2-completion-reserved"]["passed"] == 16
    assert checked["v2-evidence-development"]["passed"] == 8
    assert checked["v2-legacy-development"]["passed"] == 21
    assert checked["v2-legacy-reserved"]["passed"] == 11
    assert checked["v2-legacy-development"]["documented_contract_differences"] == [
        "mixed_comparison"
    ]
    assert all(row["gate_accepted"] and not row["scores_adjusted"] for row in checked.values())


@pytest.mark.parametrize(
    "mutation",
    [
        "new_failure",
        "missing_case",
        "false_score",
        "usage",
        "case_hash",
        "legacy_gap",
        "legacy_pending",
        "extra_legacy_failure",
    ],
)
def test_gate_rejects_report_corruption_and_new_failures(reports, mutation):
    suite = "v2-completion-development"
    if mutation in {"false_score", "legacy_gap"}:
        suite = "v2-legacy-reserved"
    elif mutation in {"legacy_pending", "extra_legacy_failure"}:
        suite = "v2-legacy-development"
    path = reports / suite / "results.json"
    report = json.loads(path.read_text())
    row = report["cases"][0]
    if mutation == "new_failure":
        row["checks"]["citation_integrity"] = False
        row["passed"] = False
        row["failures"] = ["citation_integrity"]
        report["summary"]["passed"] -= 1
        report["summary"]["failure_ids"] = [row["id"]]
    elif mutation == "missing_case":
        report["cases"].pop()
    elif mutation == "false_score":
        report["summary"]["passed"] = 12
    elif mutation == "usage":
        row["response"]["usage"]["input_tokens"] = 1
    elif mutation == "case_hash":
        report["manifest"]["cases_sha256"] = "0" * 64
    else:
        row = next(r for r in report["cases"] if not r["passed"])
        if mutation == "legacy_gap":
            row["response"]["verification_result"]["gaps"] = []
        elif mutation == "legacy_pending":
            row["response"]["clarification_request"]["accepted_fields"] = []
        else:
            row["checks"]["citation_integrity"] = False
            row["failures"].append("citation_integrity")
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        check_reports(reports, Path("opspilot/evaluation"))
