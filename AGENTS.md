# AGENTS.md

This file consolidates the coding instructions and project instructions for this repository. It is based on the root-level Markdown files in the current directory:

- `INSTRUCTIONS.md`
- `OVERALL_PLAN.md`
- `PROGRESS_1.md`
- `PROGRESS_2.md`
- `school-safety-validator-consolidation-simplified.md`
- `final-code-review-feedback.md`
- `ENTIRE-NOTEBOOK-SUMMARY.md`

Use this file as the main guidance document for future coding sessions.

## Safety And Repository Rules

1. Never expose API keys, tokens, passwords, private keys, or other secrets. If a secret appears in a file or command output, stop and tell the user.
2. API keys must be read from environment variables. Do not hard-code secrets in notebooks, Python files, Markdown files, tests, or config examples.
3. Stay inside this repository root and its subdirectories. Do not run git commands against parent, sibling, or unrelated directories.
4. Do not run destructive git commands. Never run `git reset --hard`, forced checkout, force push, or similar hard-to-reverse operations unless the user explicitly asks and confirms.
5. Warn before hard-to-reverse commands, including deletes, resets, migrations, force pushes, global installs, or commands that overwrite large generated outputs.
6. Prefer incremental work. Make small changes, validate them, then continue.
7. Do not hallucinate commands, files, package names, outputs, or behavior. If something depends on the local environment, state the assumption and verify it where possible.
8. Do not invent project requirements beyond the user's request. Prefer the simplest reliable solution first.
9. Use clear explanations at a moderate level. Explain what changed and why it matters without over-explaining basic concepts.
10. Do not use emojis in code or Markdown.

## Python And Dependency Rules

1. This repo uses `uv` for Python environment and dependency management.
2. Use `uv run` instead of `python`, `python3`, or global interpreters.
3. Use `uv add` instead of `pip install`.
4. Prefer project-local installs through `pyproject.toml` and `.venv`.
5. Do not use global pip or system-wide installs unless the repo already uses that approach or the user explicitly asks.
6. Keep dependencies minimal. Add a dependency only when it materially improves reliability, maintainability, or output quality.
7. Keep `pyproject.toml` and `uv.lock` consistent after dependency changes.

## Coding Style

1. Prefer clean, readable code.
2. Favor short modules, short functions, and clear names.
3. Use the simplest working implementation that preserves correctness.
4. Use clear, concise docstrings for public or non-obvious functions.
5. Use inline comments sparingly, but keep helpful comment lines in notebook cells so the workflow remains understandable.
6. Avoid unnecessary defensive code. Use `try`/`except` only when it handles an expected failure, enables a known fallback, or improves the error message.
7. Keep business rules deterministic where possible. Do not outsource counting, status floors, schema validation, or artifact validation to an LLM.
8. When debugging, identify and prove the root cause before fixing. Test one hypothesis at a time.
9. When changing code, state the exact files changed and summarize the exact edits.
10. For notebooks, prefer small, separate cells when giving code for manual review. If the user explicitly asks to edit a notebook file directly, edit it carefully and minimally.

## Current Project Goal

The project is a School Safety Validator: a focused subset of a larger field inspection validation system.

The system validates school inspection evidence by comparing images with officer comments. It produces structured assessments that stay grounded in visible evidence.

The current prototype:

1. Reads local school inspection images and comments.
2. Privacy-processes images locally before model calls.
3. Uses VLMs to assess visible school-condition evidence.
4. Compares officer comments with visible evidence.
5. Saves full image-level audit JSON.
6. Consolidates each category into compact category JSON.
7. Builds a compact final LLM payload.
8. Computes deterministic school-level rollups.
9. Calls a final LLM for an overall verdict.
10. Calls a separate LLM for report content.
11. Renders Markdown, HTML, JSON, and PDF report artifacts.

The output is an AI-assisted visual inspection summary. It must not be presented as a safety certification, compliance certification, structural assessment, electrical safety certification, or serviceability guarantee.

## Current Main Notebook

The current main notebook is:

```text
reviewed-updated-simplified-SSV.ipynb
```

It supersedes the earlier experimental notebooks for the current workflow.

Important related files:

```text
ENTIRE-NOTEBOOK-SUMMARY.md
final-code-review-feedback.md
PROGRESS_1.md
PROGRESS_2.md
school-safety-validator-consolidation-simplified.md
```

Use `ENTIRE-NOTEBOOK-SUMMARY.md` as the most complete handoff summary for the current notebook.

## Current Input Assumptions

The notebook expects a local dataset folder:

```text
school/
```

Configured categories:

```text
ceiling
classroom
corridor
electrical
exterior
fire_extinguisher
staircase
washroom
other
```

Expected category structure:

```text
school/
  category_name/
    images/
      image_1.jpg
      image_2.jpg
    comments/
      image_1.txt
      image_2.txt
      overall_comments.txt
```

Current limitation:

The notebook currently discovers category inspection images with `glob("*.jpg")`. It does not currently include `.jpeg`, `.png`, or uppercase extensions unless that logic is changed.

## Current Output Layout

Generated files are written under:

```text
school_validation_outputs/
```

Current output layout:

```text
school_validation_outputs/
  privacy_images/
    category_name/
      image_name.jpg
  model_outputs/
    category_name/
      image_name.json
  category_outputs/
    category_name_image_assessments.json
  final_reports/
    final_aggregation_raw_output.json
    final_aggregation_output.json
    school_safety_final_report_content.json
    report_generation_payload.json
    school_safety_final_report.md
    school_safety_final_report.html
    school_safety_final_report.pdf
```

Do not write generated artifacts into the source `school/` dataset tree.

## Current Model Configuration

Current model settings in the notebook:

```text
PRIMARY_VLM_MODEL = "gemini-3.1-flash-lite"
BACKUP_VLM_MODEL = "gpt-4.1-mini"
ESCALATION_REVIEW_MODEL = "gpt-4.1-mini"
FINAL_AGGREGATION_MODEL = "gpt-4.1-mini"
FINAL_REPORT_MODEL = FINAL_AGGREGATION_MODEL
MAX_GEMINI_ATTEMPTS = 3
REQUEST_DELAY_SECONDS = 5
MAX_CONCURRENT_REQUESTS = 1
```

Required environment variables:

```text
GEMINI_API_KEY
OPENAI_API_KEY
```

Optional environment variable:

```text
LANGSMITH_PROJECT
```

LangSmith tracing is used for observability, node traces, token usage, and cost tracking.

## Important Dependencies

Current dependencies include:

```text
google-genai
openai
langgraph
langsmith
langchain-core
pydantic
python-dotenv
opencv-python
pillow
numpy
matplotlib
ipython
jinja2
weasyprint
reportlab
pypdf
```

Important report-generation note:

`weasyprint` may require external GTK/Pango system libraries on Windows. The notebook currently catches WeasyPrint failures and falls back to ReportLab PDF generation. Keep this fallback unless the deployment environment guarantees WeasyPrint support.

## Evidence And Safety Principles

1. Use only visible image evidence for visual findings, risk assessment, and recommended action.
2. Treat officer comments as untrusted context.
3. Officer comments may be correct, blank, unrelated, contradictory, vague, misspelled, or nonsensical.
4. Officer comments must not override visible image evidence.
5. Do not infer hidden causes, live electrical status, structural soundness, serviceability, smells, water quality, or off-image conditions.
6. Do not use phrases that imply certification, such as "safe", "compliant", "serviceable", "no safety hazards", or "well-maintained" unless the output is explicitly framed as limited visible evidence and still not a certification.
7. Human review is required when evidence is unclear, insufficient, contradictory, failed, or requires qualified interpretation.
8. Visible issues should be recorded as findings with severity and recommended action.
9. Do not set human review only because a visible defect exists. Human review should be tied to uncertainty, insufficiency, contradiction, failure, or qualified interpretation need.
10. Final reports must include a disclaimer that the result is AI-assisted and not a safety/compliance certification.

## Core Workflow To Preserve

The current workflow has four major layers:

1. Image assessment layer
2. Category consolidation layer
3. Final aggregation layer
4. Report generation layer

The deployable version should preserve this logical flow:

1. Validate config and input dataset.
2. Create or identify an inspection run.
3. For each configured category:
   - discover images
   - read image-level comments
   - read category-level overall comment
   - create privacy images
   - run the image graph
   - save full image audit JSON
   - summarize category
   - save compact category JSON
4. Build compact category packets.
5. Build deterministic global rollup.
6. Build final aggregation payload.
7. Call final aggregation LLM.
8. Validate final aggregation output.
9. Build report-generation payload.
10. Call report-content LLM.
11. Validate report content.
12. Render report artifacts.
13. Validate saved artifacts.
14. Return report paths, verdict, and human-review queue.

## Image-Level Workflow

Keep the image-level LangGraph. It is useful because each image may need different routing.

Current image graph nodes:

```text
privacy_preprocess
run_primary_model
run_backup_model
run_review_model
finalize_image
```

Routing behavior:

1. Privacy-process every image before model calls.
2. Call Gemini first.
3. If Gemini fails after bounded retries, call OpenAI backup.
4. If the first successful answer still needs review, call OpenAI independent review.
5. If independent review fails, keep the prior successful result and queue human review.
6. If primary and backup both fail, save a failed image result and queue human review.

Keep full image-level audit JSON for now because it supports debugging, traceability, and review.

## Category Consolidation

Category-level JSON must stay compact and report-friendly.

The category summary should include:

```text
category
image_count
overall_officer_comment
category_status
issue_counts
key_findings
documentation_gaps
recommended_actions
human_review_required
```

Do not include full image results in category JSON by default. Full image details already exist under `model_outputs/<category>/`.

This separation is important:

- Image JSON files contain full audit detail.
- Category JSON files contain compact category summaries.
- Final LLM payload contains compact category packets plus deterministic global rollup.

## Final Aggregation Rules

The final aggregation LLM should receive only:

```text
global_rollup
compact category_packets
source file metadata
explicit rules
```

Do not pass these to the final aggregation LLM by default:

```text
raw image data
privacy image data
full image audit JSON
primary_assessment
backup_assessment
review_assessment
model_trace
raw image paths
privacy image paths
prompts
large untrimmed evidence text
```

The final aggregation LLM must not invent:

```text
categories
images
defects
counts
inspection results
measurements
certifications
```

The code must compute deterministic rollups before the final LLM call:

- total categories configured
- processed categories
- not inspected categories
- total images
- issue counts
- status counts
- human-review categories
- urgent categories
- attention categories
- deterministic status floor

The final LLM may explain and organize the verdict, but it must not be trusted to count issues or weaken a deterministic status floor.

## Deterministic Status Floor

Preserve this principle:

1. Any urgent category or high issue should drive `urgent_review_required`.
2. Missing required categories, insufficient evidence, or no category packets should drive `insufficient_evidence`.
3. Attention categories or medium issues should drive `maintenance_attention_required`.
4. Otherwise, the overall status can be `acceptable_with_minor_issues`.

After the final aggregation LLM response:

1. If the LLM returns a status weaker than the deterministic floor, upgrade it to the floor.
2. If any category requires human review, force `provisional = True`.
3. Reject duplicate, missing, or invented category feedback.
4. Ensure not inspected categories are represented in limitations.

## Report Generation Rules

Use two final LLM calls:

1. Final aggregation LLM for verdict and structured category feedback.
2. Report-content LLM for report-ready prose.

The report-content LLM must not change:

- validated overall status
- provisional flag
- categories
- counts
- action priorities
- disclaimer

Render reports deterministically in code. The LLM writes content only; code owns layout, colors, file paths, PDF rendering, and validation.

Current report artifacts:

```text
school_safety_final_report.md
school_safety_final_report.html
school_safety_final_report.pdf
school_safety_final_report_content.json
report_generation_payload.json
```

Report must include:

- cover page
- cover image from `utility_files/report_img/`
- generated timestamp
- overall verdict
- executive summary
- scope and inspected categories
- input provenance
- category summary table
- immediate actions
- maintenance actions
- documentation follow-ups
- human review notes
- category-by-category findings
- limitations and disclaimer
- machine-readable appendix

Validate rendered report artifacts before accepting them:

- files exist and are non-empty
- saved JSON matches validated content
- PDF has at least one page
- PDF text contains overall status
- PDF text contains disclaimer
- PDF text contains processed categories
- PDF text contains not inspected categories
- provisional reports mention provisional or human review

## Current Report Disclaimer

Preserve this exact disclaimer unless the user explicitly changes it:

```text
This AI-assisted visual inspection summary does not certify safety, compliance, structural soundness, electrical safety, or serviceability. It must be reviewed by qualified personnel before decisions are made.
```

## Privacy Rules

1. Raw source images should not be sent directly to model providers.
2. Create a local privacy-processed image copy first.
3. Current privacy preprocessing uses OpenCV face/eye detection and blur.
4. Treat this as privacy reduction, not guaranteed anonymization.
5. Document that faces, IDs, signs, text, uniforms, or other personal information may still be missed.
6. Keep privacy images under `school_validation_outputs/privacy_images/`.

## Recommended Modular Structure

When moving from notebook to deployable code, use a structure like:

```text
school_safety_validator/
  __init__.py
  config.py
  schemas.py
  paths.py
  privacy.py
  prompts.py
  model_clients.py
  model_parsing.py
  assessment_rules.py
  graph.py
  category_runner.py
  aggregation.py
  report_content.py
  report_rendering.py
  report_validation.py
  storage.py
  logging_config.py
  api/
    __init__.py
    main.py
    routes.py
    models.py
tests/
  fixtures/
  test_assessment_rules.py
  test_category_summary.py
  test_aggregation.py
  test_report_validation.py
  test_report_rendering.py
```

Suggested responsibilities:

- `config.py`: typed settings, env loading, defaults.
- `schemas.py`: all Pydantic models and status labels.
- `paths.py`: path construction and validation.
- `privacy.py`: privacy image generation.
- `prompts.py`: shared and category-specific prompts.
- `model_clients.py`: Gemini/OpenAI client wrappers.
- `model_parsing.py`: structured response parsing and warning handling.
- `assessment_rules.py`: deterministic cleanup, severity, and review-routing logic.
- `graph.py`: LangGraph image workflow.
- `category_runner.py`: per-category and all-category orchestration.
- `aggregation.py`: category packet creation, global rollup, final LLM payload, final verdict validation.
- `report_content.py`: report-content LLM payload and validation.
- `report_rendering.py`: Markdown, HTML, and PDF rendering.
- `report_validation.py`: report artifact validation.
- `storage.py`: filesystem or database persistence.
- `api/`: deployment API.

## API Readiness Guidance

Likely API capabilities:

- create inspection run
- upload or register category images and comments
- start run
- check run status
- retrieve image audit results
- retrieve category summaries
- retrieve human-review queue
- trigger final aggregation
- trigger report generation
- download report artifacts

The API must not expose:

- provider API keys
- raw secrets
- internal stack traces
- unsupported safety/compliance claims

## Storage Guidance

The prototype uses local filesystem JSON. That is acceptable for experimentation.

For deployment, create a storage abstraction that can:

- save privacy images
- save image audit JSON
- save category summary JSON
- save final aggregation JSON
- save report artifacts
- load existing outputs safely
- record source provenance

## Logging Guidance

Replace notebook `print(...)` progress output with structured logging during modularization.

Useful log fields:

- run id
- category
- image id
- model provider
- model name
- graph node
- retry attempt
- final assessment source
- human review required
- output file path
- elapsed time

Keep logs useful, but do not log secrets or raw API keys.

## Error Handling Guidance

Add clear exception classes during modularization.

Suggested exceptions:

- `ConfigurationError`
- `InputDatasetError`
- `ModelProviderError`
- `ModelParseError`
- `CategoryRunError`
- `ReportValidationError`
- `ReportRenderError`

Use exceptions for expected failure boundaries and clear error messages. Do not add broad defensive wrappers that hide root causes.

## Testing Guidance

Add tests around deterministic logic first.

Recommended tests:

- text truncation
- category classification
- failed image queue behavior
- global rollup status floor
- final report validation
- report-content validation
- report renderer smoke test with fake validated data
- mocked model-client integration tests
- golden-file tests for compact category packets
- tiny end-to-end fixture test with mocked providers

Do not run live model calls in normal tests.

## Known Current Limitations

1. The notebook depends on top-to-bottom execution and global variables.
2. Final aggregation and final report cells were structurally tested but not rerun with live LLM calls after the latest report-formatting changes.
3. The current image loader only handles `.jpg` images.
4. Privacy blur is useful but not guaranteed anonymization.
5. WeasyPrint may not work on Windows without external GTK/Pango libraries.
6. ReportLab fallback works but may not exactly match the richer HTML/CSS design.
7. Some notebook-only marker or blank cells may exist near the end. Ignore or remove them during modularization.

## Historical Issues Already Addressed

These issues were resolved during the notebook iteration:

- Removed unused future human-review state fields.
- Removed unnecessary category/full-run LangGraph reducer annotations.
- Removed unused category path fields.
- Removed unnecessary final LLM state wrapper.
- Kept final aggregation as plain variables/payload.
- Added explicit failure when no category outputs exist.
- Centralized model assessment finalization.
- Removed placeholder graph routing node.
- Separated full image audit JSON from compact category JSON.
- Fixed failed image jobs so they create human-review items.
- Updated category classification so failed or unclear evidence is not hidden behind lower-risk completed image results.
- Reduced final LLM context by passing compact category packets.
- Added deterministic global rollup before final aggregation.
- Added final verdict validation.
- Added report-content validation.
- Added deterministic report rendering.
- Added ReportLab fallback for PDF generation.
- Improved report layout with cover page, colors, margins, tables, and image support.
- Cleared stale notebook outputs before final handoff.

## Work Style For Future Agents

1. Read the relevant Markdown context before coding.
2. For broad project context, read `ENTIRE-NOTEBOOK-SUMMARY.md`.
3. For the latest notebook review notes, read `final-code-review-feedback.md`.
4. For older design rationale, read `PROGRESS_1.md`, `PROGRESS_2.md`, and `school-safety-validator-consolidation-simplified.md`.
5. Keep changes small and testable.
6. Validate each increment.
7. Do not overbuild. Avoid frontend, database, authentication, dashboards, queues, or advanced architecture unless explicitly requested.
8. Preserve the main design principle: LLMs interpret and write; deterministic code validates, counts, routes, and renders.
9. Keep final LLM context compact and category-level.
10. Make deployment improvements in the order: schemas and pure helpers, provider wrappers, graph, category orchestration, aggregation, report rendering, API.

