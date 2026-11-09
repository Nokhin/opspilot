import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from opspilot.config import Settings
from opspilot.data.seed import seed_database
from opspilot.orchestration.service import OpsPilotService, embedding_provider
from opspilot.rag.vectorstore import JsonVectorStore


def bootstrap(settings: Settings, reset: bool = False) -> dict:
    result = {}
    if reset or not settings.incident_db.exists():
        result["incidents"] = seed_database(settings.incident_db, reset=reset)
    if reset or not settings.vector_index.exists():
        result["policy_index"] = JsonVectorStore(
            settings.vector_index, embedding_provider(settings)
        ).rebuild(settings.corpus_dir)
    if not OpsPilotService(settings).ready():
        raise ValueError("Bootstrap evidence verification failed")
    return result


def main():
    parser = argparse.ArgumentParser(description="OpsPilot controlled local administration")
    parser.add_argument(
        "command",
        choices=[
            "bootstrap",
            "seed",
            "ingest",
            "ask",
            "evaluate",
            "evaluate-live",
            "evaluate-subscription",
            "evaluate-investigations",
            "evaluate-investigations-live",
        ],
    )
    parser.add_argument(
        "--reset", action="store_true", help="Explicitly rebuild owned demo snapshots"
    )
    parser.add_argument("--question")
    parser.add_argument("--model", help="Exact selected model required for subscription evaluation")
    parser.add_argument("--cases", type=Path, default=Path("opspilot/evaluation/cases_v1_1.json"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--env-file", type=Path, default=Path(".env.live"))
    parser.add_argument("--smoke", action="store_true", help="Run five representative live cases")
    parser.add_argument("--max-http-attempts", type=int, default=120)
    parser.add_argument("--input-token-stop", type=int, default=180000)
    parser.add_argument("--output-token-stop", type=int, default=32000)
    parser.add_argument("--case-id", action="append", help="Select a curated live case; repeatable")
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument(
        "--suite",
        choices=["legacy", "completion"],
        default="legacy",
        help="Investigation case protocol; original inputs remain unchanged",
    )
    args = parser.parse_args()
    if args.command == "evaluate-investigations-live":
        from opspilot.evaluation.investigation_live import LiveBudget, run_live_investigations
        from opspilot.evaluation.live import LiveValidationError
        from opspilot.providers.chatgpt_auth import SubscriptionError

        if not args.model or args.suite != "completion":
            parser.error("Live V2 evaluation requires --model and --suite completion")
        output = args.output
        if output == Path("evaluation/results"):
            output = Path("var/live_v2") / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        case_paths = [
            Path("opspilot/evaluation/investigation_completion_" + suffix + ".json")
            for suffix in ("dev", "reserved")
        ]
        if args.cases != Path("opspilot/evaluation/cases_v1_1.json"):
            case_paths = [args.cases]
        try:
            report = run_live_investigations(
                Settings(),
                case_paths,
                output,
                model=args.model,
                budget=LiveBudget(
                    max_calls=min(args.max_http_attempts, 44),
                    input_threshold=args.input_token_stop,
                    output_threshold=args.output_token_stop,
                ),
                progress=lambda row: print(json.dumps(row), flush=True),
            )
        except (LiveValidationError, SubscriptionError) as error:
            print(json.dumps({"status": "not_completed", "reason": str(error)}))
            return 2
        print(json.dumps(report["summary"], indent=2))
        return int(
            not report["summary"]["completed"]
            or report["summary"]["passed"] != report["summary"]["requested_cases"]
        )
    if args.command == "evaluate-investigations":
        from opspilot.evaluation.investigation import run_investigation_evaluation

        settings = Settings(
            _env_file=None,
            llm_provider="extractive",
            embedding_provider="tfidf",
            subscription_enabled=False,
            default_chat_provider="configured",
        )
        bootstrap(settings)
        cases = args.cases
        if cases == Path("opspilot/evaluation/cases_v1_1.json"):
            if args.suite == "completion":
                suffix = "dev" if args.split == "development" else "reserved"
                cases = Path(f"opspilot/evaluation/investigation_completion_{suffix}.json")
            else:
                suffix = "dev" if args.split == "development" else "heldout"
                cases = Path(f"opspilot/evaluation/investigation_{suffix}.json")
        output = args.output
        if output == Path("evaluation/results"):
            output = Path("var/v2_evaluation") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        result = run_investigation_evaluation(
            OpsPilotService(settings), cases, output, split=args.split
        )
        print(json.dumps(result, indent=2))
        return int(result["passed"] != result["cases"])
    if args.command == "evaluate-subscription":
        from opspilot.evaluation.live import LiveValidationError
        from opspilot.evaluation.subscription import run_subscription_evaluation
        from opspilot.providers.chatgpt_auth import SubscriptionError

        if not args.model:
            parser.error("evaluate-subscription requires --model")
        if args.case_id:
            parser.error("Subscription evaluation supports the full suite or --smoke")
        output = args.output
        if output == Path("evaluation/results"):
            output = Path("var/live_chatgpt") / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        try:
            result = run_subscription_evaluation(
                Settings(),
                args.cases,
                output,
                model=args.model,
                smoke=args.smoke,
                max_http_attempts=args.max_http_attempts,
                progress=lambda row: print(json.dumps(row), flush=True),
            )
        except (LiveValidationError, SubscriptionError) as error:
            print(json.dumps({"status": "not_completed", "reason": str(error)}))
            return 2
        print(json.dumps(result, indent=2))
        return int(
            not result["live_validation"]["completed"]
            or result["summary"]["passed"] != result["summary"]["cases"]
        )
    if args.command == "evaluate-live":
        from opspilot.evaluation.live import (
            LiveValidationError,
            load_live_settings,
            run_live_evaluation,
        )

        output = args.output
        if output == Path("evaluation/results"):
            output = Path("evaluation/live") / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        try:
            result = run_live_evaluation(
                load_live_settings(args.env_file),
                args.cases,
                output,
                smoke=args.smoke,
                case_ids=args.case_id,
                max_http_attempts=args.max_http_attempts,
                progress=lambda row: print(json.dumps(row), flush=True),
            )
        except LiveValidationError as error:
            result = {"status": "not_completed", "reason": str(error), "output": str(output)}
            if not output.exists() or not any(output.iterdir()):
                output.mkdir(parents=True, exist_ok=True)
                (output / "PREFLIGHT.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
            return 2
        print(json.dumps(result, indent=2))
        return int(
            not result["live_validation"]["completed"]
            or result["summary"]["passed"] != result["summary"]["cases"]
        )
    settings = Settings()
    if args.command == "bootstrap":
        result = bootstrap(settings, args.reset)
    elif args.command == "seed":
        result = seed_database(settings.incident_db, reset=args.reset)
    elif args.command == "ingest":
        if settings.vector_index.exists() and not args.reset:
            parser.error("Index exists; use --reset to perform an atomic rebuild")
        result = JsonVectorStore(settings.vector_index, embedding_provider(settings)).rebuild(
            settings.corpus_dir
        )
    elif args.command == "ask":
        if not args.question:
            parser.error("ask requires --question")
        result = OpsPilotService(settings).ask(args.question).model_dump(mode="json")
    else:
        from opspilot.evaluation.runner import run_evaluation

        result = run_evaluation(OpsPilotService(settings), args.cases, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
