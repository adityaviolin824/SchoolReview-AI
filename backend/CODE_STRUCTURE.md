# Backend Code Structure

This backend is being extracted from `reviewed-updated-simplified-SSV.ipynb` into small, testable Python modules.

The important design rule is:

```text
LLMs interpret and write. Deterministic code validates, counts, routes, and renders.
```

The current backend is still local-first. The `api/` folder exists as a placeholder, but it is intentionally not wired yet. Right now we are proving that local category processing works before adding FastAPI.

## Current Runnable Boundary

The backend currently supports:

1. Running one category locally.
2. Running all configured categories locally.
3. Creating privacy-processed image copies.
4. Calling Gemini as the primary vision model.
5. Calling OpenAI as backup when Gemini fails.
6. Calling OpenAI independent review when a result is high-risk, unclear, contradictory, low-confidence, or asks for review.
7. Saving full image audit JSON for every image.
8. Saving compact category JSON for every category.
9. Saving a local all-category run summary JSON.

The backend does **not** yet support:

- final school-level aggregation,
- final report-content LLM calls,
- Markdown/HTML/PDF report rendering,
- FastAPI routes,
- frontend integration.

## Package Layout

```text
backend/
  school_safety_validator/
    inspection_runtime_settings.py
    inspection_data_models.py
    inspection_file_paths.py
    image_privacy_preprocessing.py
    inspection_prompt_templates.py
    structured_model_response_parsing.py
    vision_model_provider_clients.py
    deterministic_assessment_rules.py
    image_assessment_workflow_graph.py
    single_category_inspection_runner.py
    all_categories_inspection_runner.py
    inspection_output_storage.py
    final_verdict_aggregation.py
    final_report_content_generation.py
    final_report_artifact_rendering.py
    final_report_artifact_validation.py
    api/
      fastapi_application.py
      inspection_api_routes.py
      inspection_api_models.py
  tests/
  sample_data/
  utility_files/
  utils/
```

## Module Responsibilities

`inspection_runtime_settings.py`

Owns runtime settings that used to be notebook globals: category names, model names, retry limits, request delay, concurrency, tracing flag, input root, output root, and required API key checks.

`inspection_data_models.py`

Owns shared contracts: Pydantic model outputs, final report models, controlled status labels, and TypedDict state shapes. Other modules should import these definitions instead of redefining JSON structures.

`inspection_file_paths.py`

Builds input and output paths for a category run. It also discovers supported images and creates generated-output folders. Source images stay separate from generated artifacts.

`image_privacy_preprocessing.py`

Creates privacy-processed image copies before model calls. The current implementation uses OpenCV face and eye detection with blur. This is privacy reduction, not guaranteed anonymization.

`inspection_prompt_templates.py`

Contains shared evidence rules and category-specific prompt focus text. This keeps the prompt language reviewable and consistent across primary, backup, and review model calls.

`structured_model_response_parsing.py`

Contains provider parsing helpers, including image data URL conversion and OpenAI structured response parsing with known warning suppression.

`vision_model_provider_clients.py`

Creates wrapped Gemini/OpenAI clients and owns provider-specific calls. Gemini is primary; OpenAI is backup and independent review. This module is the main live-model boundary.

`deterministic_assessment_rules.py`

Owns deterministic cleanup and guardrails after model parsing: uncertainty cleanup, severity floors, recommended-action fallback, human-review routing, state initialization, and human-review item creation.

`image_assessment_workflow_graph.py`

Builds the LangGraph image workflow:

```text
privacy_preprocess
  -> run_primary_model
  -> optional run_backup_model
  -> optional run_review_model
  -> finalize_image
```

Each image can take a different route. This is why the graph is useful.

`single_category_inspection_runner.py`

Runs one category end to end. It discovers images, reads comments, builds image states, invokes the graph, summarizes the category, and saves image/category outputs.

`all_categories_inspection_runner.py`

Runs every configured category sequentially using the single-category runner. It reuses one model-client object across categories and saves a compact all-category run summary.

`inspection_output_storage.py`

Converts final graph state into JSON-friendly image audit records. Saves per-image audit JSON, compact category JSON, and the all-category run summary JSON.

`final_verdict_aggregation.py`

Reserved for the next phase: compact category packets, deterministic global rollups, final aggregation payloads, and final verdict validation.

`final_report_content_generation.py`

Reserved for the later report-content LLM step.

`final_report_artifact_rendering.py`

Reserved for Markdown, HTML, JSON, and PDF rendering.

`final_report_artifact_validation.py`

Reserved for validating rendered report artifacts.

`api/`

Reserved for FastAPI. Do not add API logic until local runs are stable.

## Output Layout

For local runs, generated outputs are written under:

```text
backend/school_validation_outputs/
  privacy_images/
    category_name/
      image_name.jpg
  model_outputs/
    category_name/
      image_name.json
  category_outputs/
    category_name_image_assessments.json
  run_outputs/
    all_category_run_summary.json
```

This is intentionally separate from:

```text
backend/sample_data/school/
```

## Test Layout

```text
backend/tests/
  test_inspection_data_models.py
  test_deterministic_assessment_rules.py
  test_single_category_summary.py
  test_all_categories_inspection_runner.py
```

Normal tests should not make live model calls. Tests should focus on deterministic logic and mock model/provider boundaries.

## Current Development Order

Completed:

1. Shared data models.
2. Deterministic assessment rules.
3. Single-category local runner.
4. All-category local runner.

Next:

1. Inspect real category outputs from a local all-category run.
2. Fix provider/schema issues if any appear.
3. Add final aggregation from compact category JSON.
4. Add final report content generation.
5. Add deterministic report rendering.
6. Add FastAPI only after local behavior is stable.
