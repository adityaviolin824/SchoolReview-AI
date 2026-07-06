# Backend Final Code Review

Review date: 2026-07-06

Scope: only `backend/` was reviewed.

Allowed edit in this pass: this review file only.

No backend source code, tests, configs, data files, or generated artifacts were edited in this pass.

## Bottom Line

The backend is in a much better state than the earlier review. FastAPI is now implemented, FastAPI dependencies are present, and the test suite passes.

The remaining issues are not "the API is missing" issues anymore. They are smaller correctness, observability, and cleanup issues. The most important one is that a category failure can require human review at the pipeline level but still fail to force the final aggregation/report into a provisional human-review state.

## Verification Performed

1. Worktree check:
   - Command: `git status --short -- backend`
   - Result: clean before this review file was updated.

2. Test suite:
   - Command: `UV_CACHE_DIR=/private/tmp/school-validator-uv-cache UV_PYTHON_INSTALL_DIR=/private/tmp/school-validator-uv-python PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -q -p no:cacheprovider`
   - Result: `39 passed, 2 warnings in 3.45s`
   - Warnings:
     - LangSmith wrapper deprecation warning.
     - Starlette/FastAPI TestClient warning about installing `httpx2`.

3. FastAPI dependency check:
   - `backend/pyproject.toml` includes:
     - `fastapi>=0.139.0`
     - `uvicorn[standard]>=0.50.2`
     - `python-multipart>=0.0.32`

4. FastAPI file check:
   - `backend/school_safety_validator/api/fastapi_application.py` is implemented.
   - `backend/school_safety_validator/api/inspection_api_models.py` is implemented.
   - `backend/school_safety_validator/api/inspection_api_routes.py` is implemented.
   - `backend/school_safety_validator/api/__init__.py` is implemented.

5. Non-revealing secret-pattern scan:
   - `backend/.env` was not opened.
   - The scan printed filenames only, not values.
   - Filename-only matches appeared in `backend/uv.lock` and one test file, which need a separate value-safe review if desired.

6. Reference notebook comparison:
   - Reference notebook checked: `backend/reference_notebook/reviewed-updated-SSV.ipynb`
   - The backend preserves the main LangGraph and pipeline structure:
     - privacy preprocessing
     - primary VLM
     - backup VLM
     - optional review model
     - image finalization
     - category summarization
     - compact category packets
     - deterministic global rollup
     - final aggregation
     - report content generation
     - deterministic report rendering and validation

## Current API Surface

The FastAPI layer currently provides these routes:

1. `GET /health`
2. `POST /inspection-runs`
3. `POST /inspection-runs/{run_id}/sections/{section_name}/images`
4. `POST /inspection-runs/{run_id}/start`
5. `GET /inspection-runs/{run_id}`
6. `GET /inspection-runs/{run_id}/human-review`
7. `POST /inspection-runs/{run_id}/human-review/{review_id}`
8. `GET /inspection-runs/{run_id}/artifacts/{artifact_name}`

This is simple and suitable for local testing. It does not expose server-local filesystem paths as API input, which fixes the biggest API-boundary concern from the earlier review.

## Findings

### P1 - Failed category human review is not fully propagated into the final report state

Evidence:

- `backend/school_safety_validator/all_categories_inspection_runner.py` creates failed category state with:
  - `human_review_required=True`
  - `category_status="insufficient_evidence"`
  - a human-review item
  - `saved_category_output_file=None`
- `backend/school_safety_validator/inspection_output_storage.py` loads category outputs from `saved_category_output_files`.
- `backend/school_safety_validator/final_verdict_aggregation.py` builds its `global_rollup["human_review_required"]` from loaded category packets only.
- `validate_final_report()` forces `provisional=True` only when `global_rollup["human_review_required"]` is true.

Reproduction result from a minimal fake final-aggregation run:

```text
global_human_review_required: False
not_inspected_contains_failed: True
validated_provisional: False
validated_status: insufficient_evidence
```

Impact:

- The pipeline result can correctly say human review is required because a category failed.
- The final aggregation/report can still remain non-provisional because the failed category was not represented as a loaded compact category packet.
- This weakens the project rule that uncertainty, failure, or insufficient evidence must require human review.

Recommended fix:

- Either save a compact failed-category output file for failed categories, or teach final aggregation to incorporate `failed_categories` and `category_summaries` when computing the global human-review flag.
- Add a regression test where one category fails before saving category JSON and verify:
  - final status is at least `insufficient_evidence`
  - final report `provisional` is true
  - the failed category appears in limitations or not-inspected categories
  - API status still reports human review required

### P2 - API status advertises non-downloadable metadata as artifacts

Evidence:

- `backend/school_safety_validator/pipeline.py` adds metadata entries to `artifact_paths`:
  - `run_id`
  - `output_root`
  - `materialized_input_root`
- `backend/school_safety_validator/api/inspection_api_routes.py` returns:

```python
artifacts=sorted(result.artifact_paths.keys())
```

Reproduction result from `build_artifact_paths()` without a final report:

```text
['materialized_input_root', 'output_root', 'run_id', 'run_summary']
```

Impact:

- The status endpoint can list `run_id`, `output_root`, and `materialized_input_root` as downloadable artifacts.
- Downloading those names will return 404 because they are not files inside the run root.
- This is confusing for API clients and makes the API response less honest.

Recommended fix:

- Split metadata from downloadable artifacts, or filter the API `artifacts` list to keys whose values resolve to real files inside the API run root.
- Add an API test that calls the status endpoint with a real-ish `artifact_paths` map and verifies only downloadable file artifacts are listed.

### P2 - Background task failures lose useful diagnostics in the API status response

Evidence:

- `execute_pipeline_job()` catches unexpected `Exception` and sets:
  - `record.status = "failed"`
  - `record.error = "Inspection run failed unexpectedly."`
- The exception is not logged there.
- `build_status_response()` returns only `run_id` and `status` when `record.result is None`.

Impact:

- If the background pipeline crashes before producing a result, `GET /inspection-runs/{run_id}` shows `failed` but does not include the sanitized error message in the `errors` field.
- The server side also lacks a useful exception log at the API boundary.
- This makes local testing harder because the user can see that the job failed but not why.

Recommended fix:

- Log the exception with stack trace using the backend logger.
- Include the sanitized `record.error` in `InspectionRunStatusResponse.errors` even when `record.result is None`.
- Add a route test that monkeypatches the pipeline to raise and verifies the status response includes the sanitized failure message.

### P3 - API run storage is intentionally simple, but not durable

Evidence:

- `RUNS` is an in-memory dictionary.
- `PIPELINE_LOCK` serializes pipeline jobs inside this one process.
- Uploaded files and outputs are written under `backend/school_validation_outputs/api_runs`.

Impact:

- This is fine for a local testing API.
- Run status is lost if the process restarts.
- Multiple Uvicorn workers would not share run state.
- There is no automatic cleanup for old uploaded files and generated artifacts.

Recommended fix:

- Keep this design for now if the goal is simple testing.
- Before production use, move run metadata into durable storage and add a cleanup policy.

### P3 - README is now too minimal for the implemented API

Evidence:

- `backend/README.md` currently gives only a short project summary.
- It does not show how to start the API, create a run, upload an image, start processing, check status, or download an artifact.

Impact:

- A new user cannot reliably test the API from the README alone.

Recommended fix:

- Add a minimal local testing section:
  - environment variables required
  - `uv run uvicorn school_safety_validator.api.fastapi_application:app --reload`
  - basic request sequence
  - note that live provider calls require `GEMINI_API_KEY` and `OPENAI_API_KEY`

### P3 - Some top-level utility modules look stale

Evidence:

- `backend/scripts/run_pipeline_from_json.py` imports `utils.logger`.
- `backend/utils/exception.py` imports `utils.logger`.
- `backend/utils/security_gate.py` and `backend/utils/read_yaml.py` still exist.
- Active backend package code appears to use package-local modules for the main workflow.

Impact:

- This is not breaking tests.
- It adds old-project noise and makes it less clear which modules are part of the current backend.

Recommended fix:

- Keep `backend/utils/logger.py` if the script still needs it.
- Consider moving logging into `school_safety_validator` or changing the script to package-local imports.
- Remove unused utility modules only after confirming no external scripts depend on them.

### P3 - Test warnings should be addressed later

Evidence:

- Tests pass, but two warnings appear:
  - LangSmith wrapper deprecation.
  - FastAPI/TestClient warning about `httpx2`.

Impact:

- No current test failure.
- Future dependency updates may turn these into breakages.

Recommended fix:

- Track these as dependency-maintenance tasks.
- Do not block the current API testing work on them.

## Notebook Logic Preservation Review

The main notebook workflow is preserved at the important architectural level.

Preserved:

1. Image-level LangGraph still exists.
2. Privacy preprocessing still happens before model calls.
3. Gemini primary model and OpenAI backup/review model routing still exist.
4. Full image audit JSON and compact category JSON remain separate.
5. Final LLM context is compact and category-level.
6. Deterministic global rollup still exists before the final aggregation LLM.
7. Final verdict validation still prevents weaker statuses than the deterministic floor.
8. Report content generation and deterministic artifact rendering remain separate.
9. Report validation still checks generated artifacts.

Intentional backend improvements compared with the notebook:

1. Backend image discovery supports `.jpg`, `.jpeg`, and `.png`.
2. Empty categories can be represented as `insufficient_evidence` instead of being silently skipped.
3. API uploads avoid direct client-submitted server filesystem paths.
4. Pipeline outputs are scoped under API run directories for local testing.
5. Unit tests now cover many deterministic parts of the workflow.

Main preservation gap:

- Failed categories that never save compact category JSON are not fully represented in final aggregation human-review/provisional logic. This is the one issue to fix before treating final reports as reliable.

## Simplification Review

The implemented FastAPI layer is appropriately simple for testing. It avoids authentication, databases, queues, dashboards, and other production features that were not requested.

Good simplifications already present:

1. API request models do not expose raw local filesystem paths.
2. Uploaded files are staged into a controlled API run directory.
3. Status responses are sanitized and do not return full internal pipeline state.
4. Human-review decisions are simple records attached to the in-memory run.
5. Artifact downloads are allowlisted by artifact key and constrained to the run root.

Simplifications still worth doing:

1. Separate downloadable artifacts from internal metadata.
2. Make failed-background-task status responses clearer.
3. Remove or isolate stale utility modules once external usage is checked.
4. Add a short API usage guide instead of relying on code inspection.

## Recommended Fix Order

1. Fix failed-category propagation into final aggregation/report provisional state.
2. Filter API artifact names to downloadable files only.
3. Improve API failure logging and failed-status error responses.
4. Add or update tests for the three issues above.
5. Add minimal API testing instructions to `backend/README.md`.
6. Clean stale utility modules only after confirming they are unused outside tests/scripts.

## Final Assessment

FastAPI is implemented and suitable for local testing.

The backend should not yet be treated as production-ready, mainly because run state is in memory and there is no durable job store. That is acceptable for the user's stated goal of keeping FastAPI simple for testing.

The only correctness issue that should be fixed before relying on generated reports is the failed-category provisional/human-review propagation gap.
