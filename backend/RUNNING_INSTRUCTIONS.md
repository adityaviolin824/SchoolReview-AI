# Running Instructions

These instructions are for running the backend locally before the FastAPI layer exists.

Run all commands from:

```powershell
cd "C:\Users\surhi\Documents\AdiFiles2\04 Future\Portfolio Project\05 School Condition Validator\CODE\backend"
```

## 1. Environment Variables

The model calls require:

```text
GEMINI_API_KEY
OPENAI_API_KEY
```

Optional:

```text
LANGSMITH_PROJECT
```

You can put these in `backend/.env` or set them in your shell environment. Do not commit `.env`.

## 2. Run Tests

Use this form so pytest runs inside the `uv` project environment:

```powershell
uv run python -m pytest
```

Expected current result:

```text
30 passed
```

There may be a LangSmith deprecation warning from an installed dependency. That warning does not currently block local runs.

## 3. Check CLI Help Without Calling Models

Single category:

```powershell
uv run python -m school_safety_validator.single_category_inspection_runner --help
```

All categories:

```powershell
uv run python -m school_safety_validator.all_categories_inspection_runner --help
```

Final aggregation:

```powershell
uv run python -m school_safety_validator.final_verdict_aggregation --help
```

Final report generation:

```powershell
uv run python -m school_safety_validator.final_report_content_generation --help
```

These commands do not call Gemini or OpenAI.

## 4. Run One Category

Use a small category first when debugging model/provider behavior:

```powershell
uv run python -m school_safety_validator.single_category_inspection_runner fire_extinguisher --no-tracing
```

This reads from:

```text
sample_data/school/fire_extinguisher/
```

and writes to:

```text
school_validation_outputs/
```

Expected outputs:

```text
school_validation_outputs/
  privacy_images/fire_extinguisher/
  model_outputs/fire_extinguisher/
  category_outputs/fire_extinguisher_image_assessments.json
```

## 5. Run All Categories

After one category works, run every configured category:

```powershell
uv run python -m school_safety_validator.all_categories_inspection_runner --no-tracing
```

This runs categories in configured order:

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

Generated outputs:

```text
school_validation_outputs/
  privacy_images/
  model_outputs/
  category_outputs/
  run_outputs/all_category_run_summary.json
```

## 6. Run Only Selected Categories

Use this when debugging a subset:

```powershell
uv run python -m school_safety_validator.all_categories_inspection_runner --categories fire_extinguisher,washroom --no-tracing
```

## 7. Use Custom Input Or Output Paths

Single category:

```powershell
uv run python -m school_safety_validator.single_category_inspection_runner classroom --input-root sample_data/school --output-root school_validation_outputs --no-tracing
```

All categories:

```powershell
uv run python -m school_safety_validator.all_categories_inspection_runner --input-root sample_data/school --output-root school_validation_outputs --no-tracing
```

## 8. Enable LangSmith Tracing

Set `LANGSMITH_PROJECT`, then omit `--no-tracing`:

```powershell
uv run python -m school_safety_validator.all_categories_inspection_runner
```

Tracing is useful for inspecting graph nodes, model latency, token usage, and costs.

## 9. Debugging Outputs

Start with:

```text
school_validation_outputs/run_outputs/all_category_run_summary.json
```

Then inspect category summaries:

```text
school_validation_outputs/category_outputs/
```

Then inspect image-level audit JSON:

```text
school_validation_outputs/model_outputs/category_name/
```

Each image JSON includes:

- image id,
- category,
- job status,
- primary/backup/review model trace,
- final assessment,
- human-review status,
- errors if any.

## 10. Run Final Aggregation

After category outputs exist, run final aggregation:

```powershell
uv run python -m school_safety_validator.final_verdict_aggregation --output-root school_validation_outputs
```

This reads compact category JSON from:

```text
school_validation_outputs/category_outputs/
```

and writes:

```text
school_validation_outputs/final_reports/final_aggregation_raw_output.json
school_validation_outputs/final_reports/final_aggregation_output.json
school_validation_outputs/final_reports/final_aggregation_payload.json
```

This step calls OpenAI for the final aggregation LLM and requires `OPENAI_API_KEY`.

## 11. Generate Final Report Artifacts

After category outputs exist, generate the final report artifacts:

```powershell
uv run python -m school_safety_validator.final_report_content_generation --output-root school_validation_outputs
```

This runs final aggregation, calls the report-content LLM, renders deterministic artifacts, and validates them.

Expected report artifacts:

```text
school_validation_outputs/final_reports/school_safety_final_report_content.json
school_validation_outputs/final_reports/report_generation_payload.json
school_validation_outputs/final_reports/school_safety_final_report.md
school_validation_outputs/final_reports/school_safety_final_report.html
school_validation_outputs/final_reports/school_safety_final_report.pdf
```

This step calls OpenAI and requires `OPENAI_API_KEY`.

## 12. Common Failures

Missing API keys:

```text
Missing required environment variables: GEMINI_API_KEY, OPENAI_API_KEY
```

Fix: add keys to `backend/.env` or shell environment.

No images found:

The category will still produce an `insufficient_evidence` category summary. Check that the category has an `images/` folder and supported image extensions.

Provider failure:

Gemini failure should route to OpenAI backup. If both fail, the image job is saved as failed and queued for human review instead of disappearing.

Unexpected schema/provider issue:

Run the smallest category first:

```powershell
uv run python -m school_safety_validator.single_category_inspection_runner fire_extinguisher --no-tracing
```

Then inspect:

```text
school_validation_outputs/model_outputs/fire_extinguisher/
```

## 13. What Not To Run Yet

Do not use the `api/` package yet. It is intentionally not wired.
