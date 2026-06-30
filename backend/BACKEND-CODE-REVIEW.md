# Backend Code Review

Date reviewed: 2026-06-30

Scope reviewed:

- `backend/school_safety_validator/`
- `backend/tests/`
- `backend/utils/`
- `backend/CODE_STRUCTURE.md`
- `backend/RUNNING_INSTRUCTIONS.md`
- `backend/pyproject.toml`

Explicitly ignored:

- `backend/reference_notebook/`

Validation after fixes:

```text
uv run pytest -q
21 passed, 1 warning
```

The warning is the existing LangSmith dependency deprecation warning from an installed package. It is not an application test failure.

## Issues Found

1. Gemini retry handling could raise `NameError`.

   `call_gemini_with_retry(...)` caught `except Exception:` but then used `error`. A temporary Gemini failure could therefore become `NameError` instead of retrying.

2. One unexpected image failure could abort the whole category.

   If one image graph invocation raised, `asyncio.gather(...)` stopped the category before saving failed image JSON or continuing with other images.

3. One category failure could abort the whole all-category run.

   If one `run_category_inspection(...)` call raised, later categories did not run and the all-category summary was not saved.

4. Empty categories were treated as processed.

   A category with zero images was saved as a category output and appeared in `processed_categories`, which could confuse later final aggregation. The notebook's later rollup logic distinguishes `not_inspected_categories`, so the backend needed the same distinction.

5. `.env` loading depended on the current working directory.

   `get_settings()` used `Path(".env")`, which only worked reliably when commands were run from `backend/`.

6. The new validator runners were not using the shared backend logger.

   The project already has `backend/utils/logger.py`. The local runners only used `print(...)` for progress output.

7. Privacy image writes were not checked.

   `cv2.imwrite(...)` returns `False` when a file cannot be written, but the code ignored that return value.

8. Category summarization could crash on malformed failed-result error data.

   `summarize_category(...)` assumed `result["error"]` was a dictionary. If it was `None`, summarization crashed.

## Fixes Applied

1. Gemini retry handling fixed.

   File: `backend/school_safety_validator/vision_model_provider_clients.py`

   The exception handler now uses `except Exception as error`, matching the reference notebook behavior. Fake-client tests verify temporary Gemini errors retry and non-temporary errors do not retry.

2. Image-level failure safety added.

   File: `backend/school_safety_validator/single_category_inspection_runner.py`

   One image graph failure is now converted into a failed image state with `error_type` and `error_message`. Existing storage logic saves the failed image JSON and queues human review. Other images in the category continue.

3. Category-level failure safety added.

   File: `backend/school_safety_validator/all_categories_inspection_runner.py`

   One failed category is now represented as an `insufficient_evidence` category state. Later categories continue, and the all-category summary is still saved.

4. Empty-category summary semantics clarified.

   File: `backend/school_safety_validator/all_categories_inspection_runner.py`

   The all-category summary now separates:

   - `processed_categories`
   - `failed_categories`
   - `not_inspected_categories`

   Empty categories with no image results and no category-level error are listed as `not_inspected_categories`, not processed.

5. `.env` loading made path-stable.

   File: `backend/school_safety_validator/inspection_runtime_settings.py`

   `get_settings()` now loads `backend/.env` from an absolute path based on the module location, not the process working directory.

6. Shared logging added at runner boundaries.

   Files:

   - `backend/school_safety_validator/single_category_inspection_runner.py`
   - `backend/school_safety_validator/all_categories_inspection_runner.py`

   The runners now use `backend/utils/logger.py` for operational events such as category start, image/category failures, empty categories, and saved outputs. CLI `print(...)` remains only for final command-line summaries.

7. Privacy image write failures now raise clearly.

   File: `backend/school_safety_validator/image_privacy_preprocessing.py`

   `cv2.imwrite(...)` is checked. If it returns `False`, the code raises `ValueError("Unable to write privacy image: ...")`. The image/category failure-safety path can then preserve that failure instead of silently pretending the privacy image exists.

8. Failed-result summarization made safe.

   File: `backend/school_safety_validator/single_category_inspection_runner.py`

   `summarize_category(...)` now treats missing or `None` error data as an empty dictionary and uses the default message `Image job failed.`

## Tests Added Or Updated

- `backend/tests/test_vision_model_provider_clients.py`
- `backend/tests/test_single_category_failure_safety.py`
- `backend/tests/test_all_categories_inspection_runner.py`
- `backend/tests/test_single_category_summary.py`
- `backend/tests/test_runtime_settings.py`
- `backend/tests/test_image_privacy_preprocessing.py`

These tests use fake clients, fake graphs, monkeypatching, and temporary files. They do not call live model APIs and do not read API keys.

## Current Status

All important issues from the original backend review have been fixed and tested.

Still intentionally not implemented:

- final school-level aggregation,
- final report-content LLM calls,
- Markdown/HTML/PDF report rendering,
- FastAPI routes,
- frontend integration.

Those are planned future phases, not unresolved bugs in the current local category-runner boundary.

Not worth fixing right now:

- empty future modules for final aggregation/report/API,
- empty future tests for those modules,
- sequential all-category execution, which is useful while local behavior is being proven,
- the LangSmith dependency deprecation warning, because it does not break tests or current backend behavior.

## Recommended Next Step

Proceed to final aggregation modularization only after reviewing a fresh local all-category output. The backend now has better failure preservation and clearer run summaries, so it is in a safer state for that next phase.
