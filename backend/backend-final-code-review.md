# Backend Final Code Review Before API Integration

Scope: only `backend/` was reviewed.

Allowed edit: this file only.

No backend source code, tests, configs, data files, or API placeholders were edited.

## Review Method

This review used a code-review stance plus systematic-debugging discipline:

1. Gather concrete evidence from the code.
2. Prove where each issue comes from.
3. Separate local-pipeline concerns from API-integration concerns.
4. Recommend fixes in the order that reduces integration risk fastest.

I did not open `backend/.env`, because it may contain secrets.

## Verification Performed

1. File inventory:
   - `rg --files backend`

2. Non-revealing secret-pattern scan:
   - The scan printed no matches.
   - No secret values were displayed.
   - `backend/.env` was not opened.

3. API placeholder check:
   - `backend/school_safety_validator/api/fastapi_application.py`: 0 bytes
   - `backend/school_safety_validator/api/inspection_api_routes.py`: 0 bytes
   - `backend/school_safety_validator/api/inspection_api_models.py`: 0 bytes
   - `backend/school_safety_validator/api/__init__.py`: 0 bytes

4. Python syntax check:
   - Command used: `uv run --no-sync python -c ...`
   - Result: 42 backend Python files parsed successfully.

5. Test command check:
   - Command attempted: `uv run --no-sync pytest -q -p no:cacheprovider`
   - Result: failed before tests ran because `pytest` was not available in the current no-sync `.venv`.
   - This does not prove the tests fail. It proves the current no-sync environment cannot run them.

6. Test coverage inventory:
   - 34 test functions exist under `backend/tests/`.
   - They cover deterministic rules, schemas, runtime settings, category summaries, all-category orchestration, provider retry behavior, final aggregation, report content validation, report rendering, report artifact validation, privacy preprocessing failure handling, and pipeline orchestration.

## Current Backend Structure

### Core package

`backend/school_safety_validator/`

1. `inspection_data_models.py`
   - Central schemas and workflow state shapes.
   - Defines image assessment models, final report models, request models, execution options, and `SchoolInspectionResult`.

2. `inspection_runtime_settings.py`
   - Runtime configuration, category names, model names, tracing defaults, and API-key checks.
   - Loads `backend/.env` using `load_dotenv(..., override=True)`.

3. `inspection_file_paths.py`
   - Builds category folder paths.
   - Discovers images.
   - Supports `.jpg`, `.jpeg`, and `.png`.

4. `inspection_prompt_templates.py`
   - Shared evidence rules and category-specific prompt details.

5. `image_privacy_preprocessing.py`
   - Reads a raw image with OpenCV.
   - Runs face and eye detection.
   - Writes a privacy-processed copy before model calls.

6. `vision_model_provider_clients.py`
   - Creates Gemini and OpenAI clients.
   - Handles Gemini retry and local pacing.
   - Calls OpenAI structured responses for backup/review assessment.

7. `structured_model_response_parsing.py`
   - Converts images to data URLs.
   - Wraps OpenAI structured response parsing.

8. `deterministic_assessment_rules.py`
   - Initializes graph/category/full-run state.
   - Normalizes model output.
   - Applies deterministic severity and human-review rules.

9. `image_assessment_workflow_graph.py`
   - Builds the LangGraph image workflow.
   - Nodes: privacy preprocessing, Gemini primary model, OpenAI backup model, OpenAI review model, finalize image.

10. `single_category_inspection_runner.py`
    - Runs one category.
    - Builds image jobs.
    - Runs image graph jobs.
    - Summarizes category results.
    - Saves full image audit JSON and compact category JSON.

11. `all_categories_inspection_runner.py`
    - Runs selected categories sequentially.
    - Reuses one `ModelClients` instance per full run.
    - Saves an all-category run summary.

12. `inspection_output_storage.py`
    - Converts image graph state into saved JSON.
    - Saves image audit outputs.
    - Saves compact category outputs.
    - Saves run summary.
    - Loads category outputs for final aggregation.

13. `final_verdict_aggregation.py`
    - Builds compact category packets.
    - Computes deterministic global rollup and status floor.
    - Calls final aggregation LLM.
    - Validates and saves final aggregation output.

14. `final_report_content_generation.py`
    - Calls report-content LLM.
    - Validates that report content preserves the validated verdict, categories, counts, provisional flag, and disclaimer.

15. `final_report_artifact_rendering.py`
    - Renders Markdown, HTML, JSON, and PDF.
    - Uses WeasyPrint first and ReportLab fallback.

16. `final_report_artifact_validation.py`
    - Validates rendered artifacts and PDF text content.

17. `pipeline.py`
    - Main end-to-end orchestration entry point.
    - Materializes request images/comments into the expected category folder shape.
    - Runs category processing and optional final report generation.
    - Returns `SchoolInspectionResult`.

18. `api/`
    - Exists but is empty.
    - No FastAPI app or routes are implemented yet.

### Other backend folders

1. `backend/scripts/`
   - Contains `run_pipeline_from_json.py`, a local CLI entry point.

2. `backend/tests/`
   - Contains 34 test functions.
   - Tests are meaningful but were not executed in this review because the current no-sync environment cannot spawn `pytest`.

3. `backend/utils/`
   - `logger.py` is used.
   - `exception.py`, `read_yaml.py`, and `security_gate.py` appear unused by the active backend.

4. Generated/local folders present under `backend/`
   - `.venv`
   - `.pytest_cache`
   - `school_validation_outputs`
   - `logs`
   - `tmp`

## Sequential Runtime Flow

1. Caller provides a `SchoolInspectionRequest`.
2. Caller provides `PipelineExecutionOptions`.
3. `run_school_safety_pipeline_async()` normalizes options.
4. If no `run_id` exists, the pipeline creates one from a UTC timestamp.
5. The pipeline materializes images and comments into:
   - `<output_root>/pipeline_inputs/<run-id>/<category>/images`
   - `<output_root>/pipeline_inputs/<run-id>/<category>/comments`
6. The pipeline validates section names against configured category names.
7. `get_settings()` creates runtime settings using the materialized input root and output root.
8. `ModelClients.from_env()` loads Gemini and OpenAI clients unless clients are injected in tests.
9. `run_all_category_inspections()` runs requested categories sequentially.
10. Each category builds category paths.
11. Each category reads overall comments and image-level comments.
12. Each category discovers supported image files.
13. Each image starts with privacy preprocessing.
14. Gemini is called as the primary VLM.
15. If Gemini fails, OpenAI backup is called.
16. If the first successful model output requires review, OpenAI review is called.
17. The final image state is converted to full image audit JSON.
18. Category-level compact JSON is created from image results.
19. All-category summary is saved.
20. If report generation is enabled, final aggregation loads compact category outputs.
21. Final aggregation builds compact packets and deterministic global rollup.
22. Final aggregation LLM returns a structured final verdict.
23. Deterministic validation upgrades unsafe/weaker status and validates categories.
24. Report-content LLM creates report-ready prose.
25. Report content validation rejects changed status, changed provisional flag, changed disclaimer, invented categories, or omitted not-inspected categories.
26. Markdown, HTML, JSON, and PDF artifacts are rendered.
27. Report artifact validation checks files and PDF text.
28. `SchoolInspectionResult` is returned.

## FastAPI Readiness Summary

Current status: not ready to integrate as a public or production FastAPI API.

The core local pipeline is close to API-callable, but the API boundary is not implemented or hardened yet.

Blocking reasons:

1. API files are empty.
2. FastAPI dependencies are missing.
3. Current request model accepts server-local filesystem paths.
4. Output artifacts are not fully run-isolated.
5. Long-running model/report work should not run inline in an API request handler.
6. External API responses should not expose raw filesystem paths, raw internal errors, or full internal run summaries by default.
7. Tests were not runnable in the current no-sync environment during this review.

## Findings

### P0 - FastAPI layer is not implemented

Evidence:

- `backend/school_safety_validator/api/fastapi_application.py` is 0 bytes.
- `backend/school_safety_validator/api/inspection_api_routes.py` is 0 bytes.
- `backend/school_safety_validator/api/inspection_api_models.py` is 0 bytes.
- `backend/school_safety_validator/api/__init__.py` is 0 bytes.
- `backend/pyproject.toml` has no `fastapi`, `uvicorn`, or `python-multipart`.

Impact:

- There is no app object.
- There are no routes.
- There are no API-specific request/response models.
- There is no upload handling.
- There is no job status endpoint.
- There is no artifact download endpoint.
- The backend cannot currently be launched as a FastAPI service.

Advice:

- Add the API layer in a small first pass:
  - `GET /health`
  - `POST /inspection-runs`
  - `POST /inspection-runs/{run_id}/start`
  - `GET /inspection-runs/{run_id}`
  - `GET /inspection-runs/{run_id}/artifacts/{artifact_name}`
- Use the existing pipeline internally, but do not expose internal filesystem-oriented models directly.
- Add dependencies with `uv add fastapi uvicorn python-multipart` when ready.

### P0 - Current request model is unsafe for direct web/API use

Evidence:

- `InspectionImageInput.image_path` is a `Path`.
- `resolve_path_from_base()` returns absolute paths unchanged.
- `materialize_request_dataset()` accepts a source path if it exists, is a file, and has a supported extension.
- The source image is copied with `shutil.copy2(source_path, destination_path)`.

Impact:

- A web client could submit arbitrary server-local paths if the API directly accepts this model.
- If the file exists, has an image extension, and the process can read it, the backend can copy it and later send a privacy-processed version to model providers.
- This is acceptable for a trusted local CLI, but not acceptable as a public API boundary.

Advice:

- Do not expose `InspectionImageInput.image_path` directly to untrusted clients.
- For API v1, use uploaded files or pre-registered server-side object IDs.
- Stage uploads into a run-specific directory controlled by the backend.
- If local path registration is needed for admin-only workflows, validate paths against a configured allowlisted root.
- Add file size limits, content-type checks, and image magic/header validation before processing.

### P0 - Generated outputs are not fully run-isolated

Evidence:

- Materialized input defaults to `<output_root>/pipeline_inputs/<run-id>`.
- Category output path is fixed as `<output_root>/category_outputs/<category>_image_assessments.json`.
- Image audit output path is fixed as `<output_root>/model_outputs/<category>/<image>.json`.
- Run summary path is fixed as `<output_root>/run_outputs/all_category_run_summary.json`.
- Final report path is fixed as `<output_root>/final_reports/...`.
- Final aggregation has a disk fallback that loads from fixed `<output_root>/category_outputs`.

Impact:

- Two API runs using the same `output_root` can overwrite category outputs, image audit outputs, run summaries, final aggregation JSON, and report artifacts.
- A later final aggregation can accidentally read stale category outputs from another run.
- Artifact lookup becomes ambiguous.
- Concurrent API execution is unsafe with shared output roots.

Advice:

- Make the normalized `output_root` run-specific, for example:
  - `<base_output_root>/<run_id>/privacy_images`
  - `<base_output_root>/<run_id>/model_outputs`
  - `<base_output_root>/<run_id>/category_outputs`
  - `<base_output_root>/<run_id>/run_outputs`
  - `<base_output_root>/<run_id>/final_reports`
- Keep the internal folder names, but put all of them under one run root.
- Disable disk fallback in API mode unless it is explicitly scoped to the same run root.

### P1 - Raw final aggregation output is mutated before saving

Evidence:

- `run_final_aggregation()` sets `raw_report = response.output_parsed`.
- It then calls `validated_report = validate_final_report(raw_report, ...)`.
- `validate_final_report()` mutates the report in place:
  - updates `report.overall_status`
  - forces `report.provisional`
  - appends not-inspected category limitations
- `save_final_aggregation_outputs()` writes both `raw_report` and `validated_report` after mutation.

Impact:

- `final_aggregation_raw_output.json` may not be the true raw model output.
- Auditability is weakened because deterministic corrections cannot be compared against the original LLM response.

Advice:

- Deep-copy `raw_report` before validation.
- Or change `validate_final_report()` to return a corrected copy without mutating the input.
- Add a regression test:
  - fake LLM returns weaker status
  - raw saved JSON stays weak
  - validated saved JSON is upgraded

### P1 - Empty category semantics are inconsistent across layers

Evidence:

- `run_category_inspection()` saves empty categories with an `insufficient_evidence` category summary.
- `build_all_category_run_summary()` marks a category as processed only when it has non-empty `image_results`.
- `tests/test_all_categories_inspection_runner.py` currently asserts that an empty category is listed as not inspected.
- Because empty category outputs can still be saved, final aggregation may load that empty category output and treat it as processed.

Impact:

- With `generate_report=False`, `SchoolInspectionResult` can report an empty category as not inspected.
- With report generation enabled, final aggregation can treat the same category as processed with `insufficient_evidence`.
- API clients may see different category coverage depending on whether report generation ran.

Advice:

- Pick one meaning:
  - Recommended: a requested category with no images is processed with `insufficient_evidence`.
  - Alternative: a category with no images is not inspected and should not produce category output.
- For API clarity, prefer the recommended option.
- Update tests to match the chosen rule.

### P1 - Synchronous provider and report work sits inside async orchestration

Evidence:

- `run_backup_model_node()` and `run_review_model_node()` are async graph nodes but call synchronous OpenAI parsing.
- `parse_openai_structured_response()` calls `openai_client.responses.parse(...)` synchronously.
- `run_final_report_generation()` is synchronous.
- `run_school_safety_pipeline_async()` calls `run_final_report_generation()` inside the async function.
- PDF rendering is CPU/file-system heavy and synchronous.

Impact:

- A FastAPI async route that awaits the pipeline can still block the event loop.
- Long model calls and PDF rendering should not run inline in request/response flow.

Advice:

- Use a job-based API:
  - request creates a run
  - background task starts processing
  - status endpoint polls result
  - artifact endpoint downloads outputs
- If direct execution is needed temporarily, run blocking work in a threadpool.
- Consider async OpenAI clients later, but do not make that the first API milestone.

### P1 - External API response shape would expose internal filesystem details

Evidence:

- `HumanReviewItem` includes `raw_image_path`.
- Saved image result JSON includes `raw_image_path`.
- `SchoolInspectionResult` includes:
  - `human_review_items`
  - `category_summaries`
  - full `run_summary`
  - `artifact_paths`
  - raw `errors`
- `build_artifact_paths()` returns local filesystem paths.

Impact:

- Directly returning `SchoolInspectionResult` from FastAPI may expose server paths and internal storage layout.
- Raw error strings can expose internal details.
- The response shape is useful internally, but too broad for an external API contract.

Advice:

- Keep `SchoolInspectionResult` as an internal service result.
- Create API response models that expose:
  - `run_id`
  - `status`
  - `overall_status`
  - `human_review_required`
  - `processed_sections`
  - `failed_sections`
  - `not_inspected_sections`
  - artifact names or download URLs, not local paths
- Store detailed internal JSON server-side.

### P1 - Test suite was not executed in the current environment

Evidence:

- `uv run --no-sync pytest -q -p no:cacheprovider` failed with:
  - `Failed to spawn: pytest`
  - `No such file or directory`
- Syntax parsing passed for 42 Python files.
- 34 tests exist.

Impact:

- Syntax is verified.
- Runtime behavior is not fully verified in this review pass.
- API integration should not start until tests run cleanly.

Advice:

- Restore the environment with normal uv workflow:
  - `uv sync`
  - `uv run pytest`
- Do not run live model calls in normal tests.
- Add API tests with mocked pipeline execution after routes are implemented.

### P2 - `.env` override behavior is risky for deployed API environments

Evidence:

- `get_settings()` calls `load_dotenv(dotenv_path=BACKEND_ENV_FILE, override=True)`.
- `backend/.env` exists.
- Tests intentionally assert the absolute `.env` path and `override=True`.

Impact:

- A local `.env` can override environment variables supplied by the hosting platform.
- This can be surprising in deployment.

Advice:

- For API/deployment mode, prefer `override=False`.
- Or make override behavior explicit through an environment variable or settings parameter.
- Keep `.env.example`; do not commit real `.env`.

### P2 - Pipeline catches all exceptions and returns a failed result

Evidence:

- `run_school_safety_pipeline_async()` catches `Exception`.
- It logs the exception and returns `SchoolInspectionResult(pipeline_status="failed", errors=[...])`.

Impact:

- This is good for local CLI execution.
- In API mode, it can accidentally become HTTP 200 with `pipeline_status="failed"` unless routes map failures carefully.

Advice:

- For a background job API, store the failed result and return it through the status endpoint.
- For request validation failures, return proper 4xx responses.
- For unexpected service errors, return controlled 5xx responses without internal stack traces.

### P2 - Provider pacing is per `ModelClients` instance, not process-wide

Evidence:

- `ModelClients` owns `_gemini_lock` and `_last_gemini_request_time`.
- `run_all_category_inspections()` reuses one `ModelClients` instance within a run.
- If each API run creates new clients, each run gets its own Gemini pacing lock.

Impact:

- Within one run, Gemini pacing is controlled.
- Across concurrent API runs, provider calls can exceed intended pacing.

Advice:

- In API mode, use an application-level model-client provider or shared rate limiter.
- Alternatively, serialize model work through a background job queue.

### P2 - Disk fallback can mix stale outputs with current workflow

Evidence:

- `load_category_outputs()` uses `full_run_state["saved_category_output_files"]` when available.
- Otherwise it falls back to `<output_root>/category_outputs/<category>_image_assessments.json`.

Impact:

- Local CLI use is convenient.
- API use can accidentally aggregate stale files if `full_run_state` is missing or the output root is shared.

Advice:

- In API execution, require explicit run-scoped source files.
- Avoid disk fallback from shared roots in API mode.

### P2 - File validation is extension-based before privacy preprocessing

Evidence:

- `materialize_request_dataset()` checks suffix against supported extensions.
- `blur_faces_in_image()` later uses `cv2.imread()` and fails if the file cannot be read.

Impact:

- Invalid images are eventually rejected.
- API clients may get late pipeline failures instead of early request validation.

Advice:

- In API upload handling, validate:
  - file size
  - extension
  - MIME/content type
  - readable image header
  - pixel dimensions if needed
- Fail before creating a run or before starting model calls.

### P2 - Top-level `utils` package is deployment-fragile

Evidence:

- Core modules import `from utils.logger import ...`.
- `utils` is a top-level backend folder, not inside `school_safety_validator`.

Impact:

- It works when `backend/` is on `sys.path`.
- It is more fragile if the package is installed or run from another context.
- It can also collide with another top-level package named `utils`.

Advice:

- Move used utilities under `school_safety_validator/`.
- Or use package-relative imports after reorganizing.
- Keep this after the API blockers.

### P3 - Some dependencies and utility modules appear redundant

Evidence:

- `utils/logger.py` is used.
- `utils/exception.py`, `utils/read_yaml.py`, and `utils/security_gate.py` appear unused by active backend code/tests.
- `SecurityGate.threshold` is stored but not used.
- `pyproject.toml` includes `ipython` and `matplotlib`, but active backend code did not show imports for them.

Impact:

- Not an immediate runtime bug.
- Adds noise to the deployable backend.

Advice:

- After API integration is stable, remove unused utility modules and unused dependencies.
- Keep dependencies minimal for deployment.

### P3 - WeasyPrint fallback hides the fallback reason

Evidence:

- `render_report_pdf()` catches `Exception`.
- It falls back to ReportLab and returns `"reportlab"`.
- The exception is not logged.

Impact:

- The fallback is useful.
- Debugging deployment-specific WeasyPrint problems will be harder.

Advice:

- Log the WeasyPrint failure reason at warning level before falling back.
- Keep the ReportLab fallback.

### P3 - Report renderer is large

Evidence:

- `final_report_artifact_rendering.py` is 858 lines.

Impact:

- Not a blocker.
- It is harder to review than the rest of the backend.

Advice:

- Do not refactor this before API integration.
- Later split into:
  - shared report view model
  - Markdown renderer
  - HTML renderer
  - ReportLab PDF fallback
  - save/validation orchestration

## What Is Strong

1. The notebook has been split into clear backend modules.
2. Pydantic schemas are centralized.
3. Image privacy preprocessing happens before provider calls.
4. The image-level LangGraph keeps primary, backup, review, and finalization boundaries clear.
5. Category outputs are compact and separate from full image audit JSON.
6. Final aggregation uses deterministic rollups.
7. The deterministic status floor prevents the final LLM from weakening the outcome.
8. Report-content validation prevents the report LLM from changing core facts.
9. Report rendering is deterministic.
10. PDF/report artifact validation exists.
11. Tests exist for the important deterministic pieces.
12. The pipeline has an async entry point that can be used by FastAPI after API boundaries are hardened.

## Recommended Correction Plan

### Phase 1 - Restore verification

1. Run `uv sync`.
2. Run `uv run pytest`.
3. Fix any failures before API work.
4. Keep live model calls out of normal tests.

### Phase 2 - Fix correctness issues before API

1. Preserve true raw final aggregation output.
2. Decide empty-category semantics and make run summary/final aggregation agree.
3. Make all generated output paths run-scoped.
4. Disable or strictly scope disk fallback for API execution.

### Phase 3 - Harden the API boundary

1. Do not expose raw `Path` request fields to external clients.
2. Add upload/staging models for API requests.
3. Add file size, MIME, extension, and image-read validation.
4. Return artifact IDs or URLs instead of local paths.
5. Return sanitized errors externally.

### Phase 4 - Add minimal FastAPI shell

1. Add dependencies:
   - `fastapi`
   - `uvicorn`
   - `python-multipart` if using file uploads
2. Implement:
   - `GET /health`
   - `POST /inspection-runs`
   - `POST /inspection-runs/{run_id}/start`
   - `GET /inspection-runs/{run_id}`
   - `GET /inspection-runs/{run_id}/artifacts/{artifact_name}`
3. Use the existing pipeline internally.
4. Start processing in a background task or job queue.
5. Add mocked API tests.

### Phase 5 - Clean deployment hygiene

1. Move `utils/logger.py` into the package or make imports package-relative.
2. Remove unused utility modules.
3. Remove unused dependencies after tests confirm they are unnecessary.
4. Consider changing `.env` override behavior for deployment.
5. Add logging around WeasyPrint fallback.

## Suggested API Shape

Keep the first API small.

1. `GET /health`
   - Returns service status.

2. `POST /inspection-runs`
   - Creates a run record.
   - Accepts school metadata and section metadata.
   - Uploads or registers images.
   - Returns `run_id`.

3. `POST /inspection-runs/{run_id}/start`
   - Starts background processing.
   - Returns `202 Accepted`.

4. `GET /inspection-runs/{run_id}`
   - Returns sanitized run status and summary.
   - Does not expose local filesystem paths.

5. `GET /inspection-runs/{run_id}/artifacts/{artifact_name}`
   - Downloads allowed artifacts only.
   - Validates that the artifact belongs to that run.

## Final Recommendation

Do not integrate the public FastAPI layer directly on top of the current request/response models.

The backend core is good enough to keep. The main work before API integration is boundary hardening:

1. Restore test execution.
2. Fix run isolation.
3. Fix raw final aggregation audit preservation.
4. Resolve empty-category semantics.
5. Add API-specific request/response models that do not trust or expose server filesystem paths.

After those are done, a minimal FastAPI shell can be added without rewriting the pipeline.
