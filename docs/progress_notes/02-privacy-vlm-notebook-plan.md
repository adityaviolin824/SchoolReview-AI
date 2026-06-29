# Privacy-Aware VLM Notebook Plan

> Historical note: This file captures the implementation plan for adding privacy preprocessing, model fallback, and review routing to the notebook workflow.

This file is the working plan for creating the new notebook:

```text
vlm-inspection-with-privacy.ipynb
```

The new notebook should be based on the current multi-category VLM inspection
notebook, but with privacy protection added before any image is sent to a VLM.

## Main Goal

Create a new notebook that performs school inspection validation with:

- one image per VLM request
- category-specific prompts
- category-specific Pydantic schemas
- local face blurring before VLM calls
- Gemini as the primary low-cost VLM
- a review or backup VLM when Gemini is unavailable
- a stronger review model when Gemini is uncertain, unsafe, contradictory, or
  low-confidence
- individual per-image outputs
- one consolidated JSON output

## Files To Reference

Read these files before building the notebook:

- `INSTRUCTIONS.md`
  - Follow notebook coding style rules.
  - Keep code simple.
  - Add comment lines.
  - Provide clear, separate cells.

- `gemini_testing_multiple.ipynb`
  - Use this as the base notebook.
  - Preserve its general structure.
  - Copy the existing multi-category schemas, prompts, routing logic, and output
    structure unless a privacy or fallback change is needed.

- `AGENTS.md`
  - Use as project-level implementation context.
  - It describes the current multi-category MVP plan and output conventions.

- `OVERALL_PLAN.md`
  - Use only for high-level project context if needed.
  - Do not overbuild beyond the MVP.

- `MVP_IMPLEMENTATION_PLAN.md`
  - Reference if it contains useful details at implementation time.
  - It may currently be empty.

- `pyproject.toml`
  - Add the OpenCV dependency required for local face blurring.

## Files To Edit

Only edit these files when implementing the updated notebook:

- `pyproject.toml`
- `vlm-inspection-with-privacy.ipynb`

## Files Not To Edit

Do not edit any other existing files.

Specifically, do not edit:

- `gemini_testing_multiple.ipynb`
- `gemini_testing_single.ipynb`
- `AGENTS.md`
- `INSTRUCTIONS.md`
- `OVERALL_PLAN.md`
- `MVP_IMPLEMENTATION_PLAN.md`
- existing image files
- existing officer comment files
- existing model output files

## Dependency Plan

Add OpenCV to `pyproject.toml`.

Preferred dependency:

```text
opencv-python
```

Use the existing project dependency style. Do not use global pip.

## Privacy Requirement

Add local face blurring before sending images to any VLM.

Use OpenCV Haar Cascade for the first MVP version because it is:

- local
- free
- simple
- fast on CPU
- good enough for a first privacy layer

The preprocessing flow should be:

```text
raw image
-> detect faces locally
-> blur detected face regions
-> save privacy-processed image
-> send privacy-processed image to VLM
```

Do not send the raw image to a third-party face-blurring API.

## Privacy Output Location

Save privacy-processed images separately from raw images.

Recommended folder pattern:

```text
school/<category>/privacy_images/
```

Do not overwrite original images.

## VLM Input Requirement

The VLM should receive the privacy-processed image, not the raw image.

If no face is detected, still save or use a privacy-processed copy so the
pipeline stays consistent and auditable.

## Primary Model Requirement

Keep Gemini as the primary low-cost VLM.

The model name should remain configurable through a variable such as:

```python
PRIMARY_VLM_MODEL = "..."
```

Do not hardcode the primary model inside helper functions.

## Backup Model Requirement

Add a backup VLM path when the primary model cannot be accessed.

Use the backup VLM only for access or availability failures, such as:

- rate limit exhaustion
- quota errors
- temporary server errors
- 503 unavailable
- high-demand errors
- timeout-like failures

This is different from quality escalation.

The logic should be:

```text
try primary Gemini VLM
-> retry a few times with backoff
-> if primary still unavailable, use backup VLM
```

The backup model should be configurable through a variable such as:

```python
BACKUP_VLM_MODEL = "..."
```

The backup provider may be OpenAI direct or OpenRouter later, but keep the MVP
simple.

## Review Model Requirement

Keep the existing stronger review model logic.

Use the review model when the primary or backup VLM returns a result but the
result is:

- low-confidence
- unsafe
- unclear
- contradictory to the officer comment
- marked for human review

This is quality escalation, not availability fallback.

The logic should be:

```text
primary result succeeds
or backup result succeeds
-> inspect assessment fields
-> if uncertain/risky/contradictory, call review model
```

## Keep Fallback Types Separate

There are two separate fallback concepts:

1. Availability fallback
   - Primary model cannot be accessed.
   - Use backup VLM.

2. Quality review escalation
   - A model returned an answer, but the answer is uncertain or risky.
   - Use stronger review model.

Do not mix these into one flag.

## Output Requirements

Continue saving:

- one readable output file per image
- one consolidated JSON file

Each image output should include enough information to audit the route:

- category name
- raw image path
- privacy image path
- officer comment
- primary model name
- primary assessment, if available
- whether backup was used
- backup model name, if used
- backup assessment, if used
- whether review escalation was used
- review model name, if used
- review assessment, if used
- final assessment
- final assessment source
- whether human review is still needed

## Notebook Style

Keep notebook cells short and readable.

Use markdown cells before major code sections, such as:

- imports and clients
- paths and categories
- schemas
- prompts
- privacy preprocessing
- model routing
- async runner
- saving outputs

Add comment lines inside code so the notebook remains understandable later.

## MVP Boundaries

Do not add:

- frontend
- database
- authentication
- dashboard
- LangGraph implementation
- advanced logging framework
- production orchestration

Comprehensive logging can be added later. For now, simple route fields in JSON
and clean notebook print statements are enough.

## Implementation Order

1. Copy the structure of `gemini_testing_multiple.ipynb` into the new notebook.
2. Add OpenCV dependency to `pyproject.toml`.
3. Add imports needed for OpenCV face blurring.
4. Add a face-blurring preprocessing section.
5. Update image job preparation to create/use privacy images.
6. Update VLM calls to send privacy images instead of raw images.
7. Add primary-model retry with simple exponential backoff.
8. Add backup VLM fallback when primary Gemini is unavailable.
9. Keep review-model escalation for low-confidence or risky results.
10. Save individual outputs and consolidated JSON with route metadata.
11. Run a small category-only test before running all categories.

## Final Reminder

When implementing, edit only:

- `pyproject.toml`
- `vlm-inspection-with-privacy.ipynb`

Do not modify existing notebooks or project instruction files.
