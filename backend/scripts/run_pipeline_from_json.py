"""Run the School Safety Validator pipeline from a request JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from school_safety_validator.inspection_data_models import PipelineExecutionOptions
from school_safety_validator.pipeline import load_school_inspection_request_json, run_school_safety_pipeline
from utils.logger import configure_logging


def parse_args() -> argparse.Namespace:
    """Parse local executor arguments."""

    parser = argparse.ArgumentParser(description="Run the end-to-end school safety pipeline from JSON.")
    parser.add_argument("--input", type=Path, required=True, help="Request JSON file.")
    parser.add_argument("--output", type=Path, required=True, help="Where to save the pipeline result JSON.")
    parser.add_argument("--output-root", type=Path, required=True, help="Generated workflow output root.")
    parser.add_argument(
        "--materialized-input-root",
        type=Path,
        default=None,
        help="Optional generated input folder. Defaults to <output-root>/pipeline_inputs/<run-id>.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Optional base directory for relative image paths. Defaults to the request JSON folder.",
    )
    parser.add_argument("--run-id", default=None, help="Optional run id used for generated input subfolders.")
    parser.add_argument("--skip-report", action="store_true", help="Run image/category stages without final report LLMs.")
    return parser.parse_args()


def write_json(path: Path, payload: dict | str) -> None:
    """Write JSON output, creating only the requested parent folder."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
        return
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main() -> int:
    """Load the request, run the pipeline, and save the result."""

    configure_logging()
    args = parse_args()

    try:
        request = load_school_inspection_request_json(args.input, args.base_dir)
        options = PipelineExecutionOptions(
            output_root=args.output_root,
            materialized_input_root=args.materialized_input_root,
            run_id=args.run_id,
            generate_report=not args.skip_report,
        )
        result = run_school_safety_pipeline(request, options)
        write_json(args.output, result.model_dump_json(indent=2))
    except Exception as error:
        failure_payload = {
            "pipeline_status": "failed",
            "errors": [f"{type(error).__name__}: {error}"],
        }
        write_json(args.output, failure_payload)
        print("Pipeline failed:", failure_payload["errors"][0])
        print("Saved failure result:", args.output)
        return 1

    print("Pipeline status:", result.pipeline_status)
    if result.overall_status:
        print("Overall status:", result.overall_status)
    print("Processed sections:", ", ".join(result.processed_sections) or "none")
    print("Human review items:", len(result.human_review_items))
    print("Saved result:", args.output)
    return 0 if result.pipeline_status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
