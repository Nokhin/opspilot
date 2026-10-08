import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, TypeAdapter

from opspilot.domain.models import Contract, OpsPilotResponse, Route, ToolCall
from opspilot.orchestration.service import OpsPilotService


class EvaluationCase(Contract):
    id: str
    category: Literal[
        "policy", "multi_document", "ambiguous", "unsupported", "data", "mixed", "safety"
    ]
    question: str
    expected_route: Route
    expected_tools: list[str]
    expected_sources: list[str] = Field(default_factory=list)
    expected_chunks: list[str] = Field(default_factory=list)
    expected_source_types: list[str] = Field(default_factory=list)
    must_refuse: bool = False
    answer_contains: list[str] = Field(default_factory=list)
    expected_arguments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    expected_results: dict[str, dict[str, Any]] = Field(default_factory=dict)


def lookup(value: dict, path: str):
    for key in path.split("."):
        value = value[key]
    return value


def matches(actual, expected) -> bool:
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        return isinstance(actual, int | float) and math.isclose(actual, expected, abs_tol=1e-4)
    return actual == expected


def grade(case: EvaluationCase, response: OpsPilotResponse, chunks: dict) -> dict:
    retrieved, retrieved_chunks = set(), set()
    for result in response.tool_results:
        if result.tool_name == "search_internal_policy":
            for hit in result.result["hits"]:
                retrieved.add(hit["chunk"]["document_id"])
                retrieved_chunks.add(hit["chunk"]["chunk_id"])
    refs = {e.evidence_id: e for e in response.evidence}
    selected = {e.source_id for e in response.evidence if e.source_type == "internal_policy"}
    selected_chunks = {e.chunk_id for e in response.evidence if e.source_type == "internal_policy"}
    citations_valid = True
    for fact in response.facts:
        if not fact.evidence_ids or any(i not in refs for i in fact.evidence_ids):
            citations_valid = False
            continue
        for evidence_id in fact.evidence_ids:
            ref = refs[evidence_id]
            if fact.kind == "policy_requirement":
                original = chunks.get(evidence_id)
                citations_valid &= bool(
                    original
                    and fact.text in original["content"].split("\n\n")
                    and ref.source_type == "internal_policy"
                    and ref.title == original["title"]
                    and ref.section == original["section"]
                    and ref.version == original["version"]
                    and ref.source_id == original["document_id"]
                    and ref.excerpt == fact.text
                )
            elif fact.kind in {"historical_fact", "interpretation"}:
                citations_valid &= ref.source_type == "incident_db"

    result_by_tool = {t.tool_name: t.result for t in response.tool_results}
    trace_by_tool = {t.tool_name: t for t in response.tool_trace}
    args_valid = True
    adapter = TypeAdapter(ToolCall)
    for trace in response.tool_trace:
        try:
            adapter.validate_python({"tool_name": trace.tool_name, "arguments": trace.arguments})
        except ValueError:
            args_valid = False
    argument_match, numeric_match = True, True
    for tool, expected in case.expected_arguments.items():
        actual = trace_by_tool[tool].arguments if tool in trace_by_tool else {}
        argument_match &= all(k in actual and matches(actual[k], v) for k, v in expected.items())
    for tool, expected in case.expected_results.items():
        for path, value in expected.items():
            try:
                numeric_match &= matches(lookup(result_by_tool[tool], path), value)
            except (KeyError, TypeError):
                numeric_match = False
    checks = {
        "response_schema": True,
        "route": response.route == case.expected_route,
        "tool_selection": set(trace_by_tool) == set(case.expected_tools),
        "tool_success": all(t.status == "success" for t in response.tool_trace),
        "argument_schema": args_valid,
        "argument_match": bool(argument_match),
        "source_recall": set(case.expected_sources) <= retrieved,
        "chunk_recall": set(case.expected_chunks) <= retrieved_chunks,
        "citation_integrity": bool(citations_valid),
        "citation_coverage": set(case.expected_sources) <= selected
        and set(case.expected_chunks) <= selected_chunks,
        "refusal": (response.confidence == "insufficient_evidence") == case.must_refuse,
        "numeric_results": bool(numeric_match),
        "reference_points": all(
            text.lower() in response.answer.lower() for text in case.answer_contains
        ),
        "evidence_planes": set(case.expected_source_types)
        <= {e.source_type for e in response.evidence},
        "read_only": not response.tool_trace if case.category == "safety" else True,
    }
    return {
        "id": case.id,
        "category": case.category,
        "question": case.question,
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
        "source_recall_at_k": len(set(case.expected_sources) & retrieved)
        / len(case.expected_sources)
        if case.expected_sources
        else None,
        "latency_ms": response.latency_ms,
        "response": response.model_dump(mode="json"),
    }


def load_cases(cases_path: Path) -> list[EvaluationCase]:
    cases = TypeAdapter(list[EvaluationCase]).validate_json(cases_path.read_bytes())
    if not 40 <= len(cases) <= 60 or len({c.id for c in cases}) != len(cases):
        raise ValueError("Golden set must contain 40–60 uniquely identified curated cases")
    return cases


def run_evaluation(service: OpsPilotService, cases_path: Path, output: Path) -> dict:
    cases = load_cases(cases_path)
    chunks = {c["chunk_id"]: c for c in service.store.snapshot()["chunks"]}
    results = []
    for case in cases:
        response = service.ask(case.question, request_id="eval-" + case.id)
        results.append(grade(case, response, chunks))
    return write_report(service, cases, results, cases_path, output)


def write_report(
    service: OpsPilotService,
    cases: list[EvaluationCase],
    results: list[dict],
    cases_path: Path,
    output: Path,
    *,
    manifest_extra: dict | None = None,
    summary_extra: dict | None = None,
) -> dict:
    if not results or len(results) != len(cases):
        raise ValueError("A report requires matching nonempty cases and results")
    total = len(results)
    categories = defaultdict(list)
    for result in results:
        categories[result["category"]].append(result)
    recall = [r["source_recall_at_k"] for r in results if r["source_recall_at_k"] is not None]
    cited = [r for r in results if r["response"]["facts"]]
    tools = [t for r in results for t in r["response"]["tool_trace"]]
    numeric = [r for r, c in zip(results, cases, strict=True) if c.expected_results]
    latency = sorted(r["latency_ms"] for r in results)
    summary = {
        "cases": total,
        "passed": sum(r["passed"] for r in results),
        "end_to_end_pass_rate": sum(r["passed"] for r in results) / total,
        "source_recall_at_k": statistics.mean(recall) if recall else None,
        "citation_integrity_rate": sum(r["checks"]["citation_integrity"] for r in cited)
        / len(cited)
        if cited
        else None,
        "refusal_accuracy": sum(r["checks"]["refusal"] for r in results) / total,
        "tool_selection_accuracy": sum(r["checks"]["tool_selection"] for r in results) / total,
        "route_accuracy": sum(r["checks"]["route"] for r in results) / total,
        "argument_schema_accuracy": sum(r["checks"]["argument_schema"] for r in results) / total,
        "tool_success_rate": sum(t["status"] == "success" for t in tools) / len(tools)
        if tools
        else None,
        "deterministic_result_accuracy": sum(r["checks"]["numeric_results"] for r in numeric)
        / len(numeric)
        if numeric
        else None,
        "latency_median_ms": statistics.median(latency),
        "latency_p95_ms": latency[math.ceil(total * 0.95) - 1],
        "input_tokens": sum(r["response"]["usage"]["input_tokens"] for r in results),
        "output_tokens": sum(r["response"]["usage"]["output_tokens"] for r in results),
        "estimated_cost_usd": sum(r["response"]["usage"]["estimated_cost_usd"] for r in results)
        if all(r["response"]["usage"]["estimated_cost_usd"] is not None for r in results)
        else None,
        "by_category": {
            k: {"cases": len(v), "passed": sum(r["passed"] for r in v)}
            for k, v in sorted(categories.items())
        },
        "failure_counts": dict(Counter(f for r in results for f in r["failures"])),
    }
    manifest = {
        "run_at_utc": datetime.now(UTC).isoformat(),
        "mode": service.settings.llm_provider,
        "embedding": service.store.embeddings.fingerprint,
        "top_k": service.settings.top_k,
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "corpus_sha256": service.store.snapshot()["corpus_sha256"],
        "snapshot_reference": service.settings.reference_time.isoformat(),
    }
    summary.update(summary_extra or {})
    manifest.update(manifest_extra or {})
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(
        json.dumps({"manifest": manifest, "summary": summary, "cases": results}, indent=2)
    )
    with (output / "cases.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["id", "category", "passed", "failures", "latency_ms"]
        )
        writer.writeheader()
        for result in results:
            writer.writerow({k: result[k] for k in writer.fieldnames})
    lines = [
        "# OpsPilot V1 evaluation",
        "",
        f"Mode: **{manifest['mode']}**, embedding: "
        f"`{manifest['embedding']}`, top-k: {manifest['top_k']}.",
        "",
        f"**{summary['passed']}/{total} cases passed ({summary['end_to_end_pass_rate']:.1%}).**",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for key in [
        "source_recall_at_k",
        "citation_integrity_rate",
        "refusal_accuracy",
        "route_accuracy",
        "tool_selection_accuracy",
        "argument_schema_accuracy",
        "tool_success_rate",
        "deterministic_result_accuracy",
    ]:
        value = summary[key]
        lines.append(f"| {key} | {value:.1%} |" if value is not None else f"| {key} | N/A |")
    lines.extend(
        [
            f"| Median latency | {summary['latency_median_ms']:.2f} ms |",
            f"| p95 latency | {summary['latency_p95_ms']:.2f} ms |",
            "",
            "## Category results",
            "",
            "| Category | Passed |",
            "|---|---:|",
        ]
    )
    lines.extend(f"| {k} | {v['passed']}/{v['cases']} |" for k, v in summary["by_category"].items())
    lines.extend(["", "## Failed cases", ""])
    failed = [r for r in results if not r["passed"]]
    lines.extend(f"- `{r['id']}`: {', '.join(r['failures'])} — {r['question']}" for r in failed)
    if not failed:
        lines.append("No failed cases in this run.")
    lines.extend(
        [
            "",
            "## Interpretation and limits",
            "",
            "This is a curated, English-language synthetic-corpus regression set, "
            "not a general enterprise benchmark.",
            "Citation integrity measures exact paragraph/provenance validity; "
            "it does not prove semantic relevance or answer completeness.",
            "Reference points and expected section IDs add deterministic coverage checks. "
            "Missing-topic rules remain conservative and corpus-specific.",
            "Numeric expectations are frozen in cases.json from independent raw-SQL checks, "
            "not recomputed by the tool under test.",
            "End-to-end pass requires every applicable route, tool, schema, filter, "
            "source/chunk, citation, refusal, numeric and reference-point check.",
            "Offline runs make no LLM calls. Their latency and zero token counts "
            "must not be presented as live-model performance.",
            "Response-level API cost estimates require configured per-million-token rates. "
            "Observed provider HTTP usage/cost, when available, is recorded separately "
            "in live reports; dense-embedding API cost is not included.",
            "Held-out/manual semantic quality and public VPS operation require "
            "separate validation.",
            "",
            "## Reproducibility",
            "",
            "```json",
            json.dumps(manifest, indent=2),
            "```",
            "",
        ]
    )
    if "live_validation" in manifest:
        live = manifest["live_validation"]
        lines.extend(
            [
                "",
                "## Live provider verification",
                "",
                f"Scope: **{live['scope']}**; completed: **{live['completed']}**; "
                f"executed/requested cases: {total}/{live['requested_cases']}.",
                f"Model: `{live['model']}`; endpoint: `{live['endpoint']}`.",
                f"Stop reason: {live['stop_reason'] or 'none'}.",
                f"HTTP attempts: {summary['provider_http_attempts']}; "
                f"successful structured calls: {summary['provider_structured_successes']}/"
                f"{summary['provider_logical_calls']}.",
                f"Provider-reported input/output tokens: "
                f"{summary['provider_input_tokens']} / {summary['provider_output_tokens']}.",
                "Provider-reported cost (USD): "
                + (
                    f"{summary['provider_reported_cost_usd']:.8f}."
                    if summary["provider_reported_cost_usd"] is not None
                    else "unavailable or incomplete."
                ),
                "Usage includes HTTP responses rejected for invalid structured output; "
                "missing usage is recorded as unknown, not zero. "
                "Partial runs must not be presented as a full-suite pass.",
                "Unsafe requests are rejected before a model call. "
                "All other cases require a successful live planning call, "
                "and any provider/evidence-validation failure fails the case.",
            ]
        )
    (output / "SUMMARY.md").write_text("\n".join(lines))
    return summary
