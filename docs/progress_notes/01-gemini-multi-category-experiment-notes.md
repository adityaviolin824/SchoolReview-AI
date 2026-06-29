# Gemini Multi-Category Experiment Notes

> Historical note: This file captures an early MVP planning stage before the privacy-aware and consolidation notebooks were introduced.

The active experiment is `gemini_testing_multiple.ipynb`.

This notebook is for early MVP testing of school inspection validation across
multiple categories:

- ceiling
- classroom
- corridor
- electrical
- exterior
- fire_extinguisher
- other
- staircase
- washroom

The goal is to compare each local inspection image with its matching
image-level officer comment, produce structured image-level JSON, and later
combine those results into category-level and school-level inspection opinions.

## Current Notebook State

- The notebook loads the Gemini API key from `.env` without printing it.
- It creates one reusable Gemini client.
- It defines `SCHOOL_PATH = Path("school")`.
- It explicitly lists the school categories in `CATEGORY_NAMES`.
- It builds `CATEGORY_DATA` with paths for each category's:
  - `images`
  - `comments`
  - `overall_comments.txt`
- It currently has category-specific Pydantic image assessment schemas.
- It has category-specific system prompts for Gemini image assessment.

## Important Processing Decision

Do not pass multiple images to Gemini in one request.

Each image should be processed with its own independent Gemini request. This
keeps visual evidence isolated and reduces the chance that Gemini mixes details
between images.

Use async processing for speed:

- use `client.aio.models.generate_content`
- use `asyncio.gather`
- use `asyncio.Semaphore(4)`
- batch/concurrency size should be 4 for the MVP

## MVP Schema Direction

Use simple image-level schemas now. Keep them configurable for later pipeline
work.

Shared image-level fields should include:

- `image_name`
- `agrees_with_comment`
- `safety_status`
- `requires_human_review`
- `assessment_comment`

Use category-specific fields only where they are useful and visually checkable.
Avoid fields that require hidden assumptions, certification checks, or expert
judgment beyond the image.

Recommended shared literal values:

- `agrees_with_comment`: `"yes"`, `"no"`, `"no_officer_comment"`,
  `"human_review_required"`
- `safety_status`: `"safe"`, `"unsafe"`, `"unclear"`

Use a mapping like `CATEGORY_ASSESSMENT_SCHEMAS` so the later pipeline can pick
the right schema from the category folder name.

## Recommended Output Files

Store both individual image outputs and consolidated JSON.

Individual image outputs are useful for debugging, audit, reruns, and human
review:

```text
school/washroom/model_outputs/washroom_001.json
school/ceiling/model_outputs/ceiling_001.json
```

Consolidated outputs are useful for category aggregation and final reporting:

```text
school_validation_outputs/image_assessments_consolidated.json
school_validation_outputs/category_assessments_consolidated.json
school_validation_outputs/final_school_summary.json
```

Use `.json` for structured model outputs. Write formatted JSON with `indent=2`
so it remains easy to inspect manually.

## Stepwise MVP Implementation Plan

### Step 1: Confirm Inputs

- Loop through each category in `CATEGORY_NAMES`.
- Count `.jpg` files in each `images` folder.
- Confirm matching `.txt` image-level comments exist where expected.
- Read `overall_comments.txt` separately for later category-level reasoning.

### Step 2: Define Schemas

- Define shared literals for comment agreement and safety status.
- Define `BaseImageAssessment`.
- Define one image-level schema per category.
- Define simple category-level and school-level wrapper schemas.
- Define `CATEGORY_ASSESSMENT_SCHEMAS`.

### Step 3: Define Prompts

- Keep one system prompt per category.
- Prompts should tell Gemini to judge only visible evidence.
- Prompts should tell Gemini what each category-specific boolean means.
- Prompts should use `"no_officer_comment"` for blank comments.
- Prompts should use human review for unclear images or unverifiable comments.

### Step 4: Process One Image Per Request

For each image:

- find the matching officer comment by filename stem
- build one user prompt with category name, image name, and officer comment
- attach exactly one image part
- call Gemini with the category-specific prompt and schema
- parse with `response.parsed`
- set `image_name` from the local filename after parsing

### Step 5: Run Async Across All Categories

- Build one task per image.
- Use `asyncio.Semaphore(4)`.
- Run all tasks with `asyncio.gather`.
- Keep failures visible and simple during the MVP.

### Step 6: Save Image-Level Outputs

For each parsed image result:

- save one JSON file under that category's `model_outputs` folder
- include the category name, image name, officer comment, and parsed assessment
- keep the output auditable and easy to compare with officer comments

### Step 7: Save Consolidated Image JSON

Create one consolidated file containing all image-level results across all
categories.

This file should be the input to the next text-model stage.

### Step 8: Category-Level Text Model Stage

Later, run a text-only model for each category.

Input should include:

- category name
- category-level officer comment from `overall_comments.txt`
- all image-level officer comments
- all image-level Gemini JSON assessments

Output should include:

- structured category JSON
- detailed text reasoning
- whether the category-level officer comment is supported
- contradictions between officer comments and image evidence
- safety concerns
- missing or weak evidence
- human-review recommendation

This stage can probably use GPT because it is reasoning over already structured
text and JSON, not raw images.

### Step 9: Master School-Level Stage

Later, a master node should read all category-level JSON outputs and produce:

- final school inspection summary
- category-wise risk overview
- unsupported or contradictory officer comments
- missing evidence
- human-review routing list
- final report-ready output

### Step 10: Human Review Later

Add human review after the image and category stages are working.

Send cases to human review when:

- image evidence is unclear
- the officer comment is contradicted
- the comment refers to something not visible
- safety status is unsafe or unclear
- the model marks `requires_human_review = True`

Preserve original model outputs and store human decisions separately so the
pipeline stays auditable.

## Current MVP Rule

Keep the notebook simple.

Do not add frontend, database, authentication, dashboards, or advanced
architecture yet. First prove that multi-category image validation works with
clean structured outputs.
