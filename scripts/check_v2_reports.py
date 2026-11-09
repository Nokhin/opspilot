"""Validate current offline V2 suites and exact, documented legacy contract differences.

Does not run Git, inference or publication. Original scores are never rewritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SUITES = {
    "v2-completion-development": ("investigation_completion_dev.json", 28),
    "v2-completion-reserved": ("investigation_completion_reserved.json", 16),
    "v2-evidence-development": ("investigation_evidence_gaps_dev.json", 8),
    "v2-legacy-development": ("investigation_dev.json", 22),
    "v2-legacy-reserved": ("investigation_heldout.json", 12),
}
LEGACY_DIFFERENCES = {
    "v2-legacy-development": {
        "mixed_comparison": {"status", "route", "frozen_reference_points"},
    },
    "v2-legacy-reserved": {"reserved_clarify": {"status"}},
}


def validate_report(report: dict, cases_path: Path, expected_count: int, suite: str) -> dict:
    """Fail on new failures, missing cases, non-offline usage or changed legacy behavior."""
    cases = json.loads(cases_path.read_text())
    expected_ids = {c["id"] for c in cases}
    rows, summary, manifest = report["cases"], report["summary"], report["manifest"]
    if not (
        len(expected_ids) == len(cases) == len(rows) == expected_count
        and {r["id"] for r in rows} == expected_ids
        and summary["cases"] == summary["executed"] == expected_count
        and manifest["cases_sha256"] == hashlib.sha256(cases_path.read_bytes()).hexdigest()
        and manifest["mode"] == "offline"
        and summary["input_tokens"] == summary["output_tokens"] == 0
        and summary["paid_inference_calls"] == 0
    ):
        raise ValueError("Incomplete, changed or non-offline report")
    expected_differences = LEGACY_DIFFERENCES.get(suite, {})
    failures = {}
    for row in rows:
        checks, response = row["checks"], row["response"]
        false_checks = {name for name, passed in checks.items() if not passed}
        if not (
            checks
            and all(isinstance(value, bool) for value in checks.values())
            and set(row["failures"]) == false_checks
            and row["passed"] is (not false_checks)
            and response["mode"] == "offline"
            and response["provider_call_count"] == 0
            and response["usage"]["input_tokens"] == response["usage"]["output_tokens"] == 0
        ):
            raise ValueError("Inconsistent checks or inference usage")
        if false_checks:
            failures[row["id"]] = false_checks
            if row["id"] == "mixed_comparison" and suite == "v2-legacy-development":
                pending = response.get("clarification_request") or {}
                if not (
                    response["completion_status"] == "awaiting_human"
                    and response["route"] == "unsupported"
                    and pending.get("kind") == "clarify"
                    and "customer_facing" in pending.get("accepted_fields", [])
                    and not response["tool_traces"]
                ):
                    raise ValueError("Legacy clarification behavior changed")
            elif row["id"] == "reserved_clarify" and suite == "v2-legacy-reserved":
                verification = response.get("verification_result") or {}
                if not (
                    response["completion_status"] == "partial"
                    and response["route"] == "mixed"
                    and not response.get("clarification_request")
                    and not verification.get("integrity_errors")
                    and "input:severity_facts"
                    in {g["requirement_id"] for g in verification.get("gaps", [])}
                ):
                    raise ValueError("Legacy severity-prerequisite behavior changed")
    if not (
        failures == expected_differences
        and set(summary["failure_ids"]) == set(failures)
        and summary["passed"] == expected_count - len(failures)
    ):
        raise ValueError("Unexpected failure or changed documented contract difference")
    return {
        "suite": suite,
        "cases": expected_count,
        "passed": summary["passed"],
        "original_failure_ids": sorted(failures),
        "documented_contract_differences": sorted(expected_differences),
        "gate_accepted": True,
        "scores_adjusted": False,
    }


def check_reports(root: Path, cases_root: Path) -> list[dict]:
    return [
        validate_report(
            json.loads((root / suite / "results.json").read_text()),
            cases_root / filename,
            count,
            suite,
        )
        for suite, (filename, count) in SUITES.items()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cases-root", type=Path, default=Path("opspilot/evaluation"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = {"accepted": True, "suites": check_reports(args.root, args.cases_root)}
    except (OSError, ValueError, KeyError, TypeError):
        # Never echo raw report content, personal data or exception details.
        result = {"accepted": False, "reason": "Offline reports failed release-contract checks"}
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return int(not result["accepted"])


if __name__ == "__main__":
    raise SystemExit(main())
