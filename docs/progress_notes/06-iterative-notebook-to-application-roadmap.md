# Iterative Notebook To Application Roadmap

> Historical note: This file explains the current development approach and how the project is expected to move from exploratory notebooks toward a more structured application.

## Why Notebooks First

The project is currently being developed through notebooks because the main work is still experimental:

- add one feature at a time
- run it on a small set of inspection images
- review the model outputs manually
- identify missing metadata, weak prompts, schema issues, and safety-routing problems
- adjust the notebook and repeat

This makes it easier to inspect intermediate outputs before committing to a fixed application structure. The goal is not to treat the notebook as the final product, but to use it as a clear draft space while the pipeline behavior is still changing.

## Current Iteration Pattern

The current loop is:

1. Add or revise one pipeline capability.
2. Run the notebook on a focused test set.
3. Save structured outputs for image-level and category-level review.
4. Review failures, unclear cases, and model-comment disagreements.
5. Update prompts, schemas, routing rules, or aggregation logic.
6. Repeat until the full report draft is reliable enough to build around.

This loop has already shaped several architectural decisions:

- process one image per VLM request to avoid mixing visual evidence across images
- keep privacy preprocessing before any VLM call
- preserve image-level JSON outputs for audit and debugging
- separate primary model output, backup fallback, and independent review
- use deterministic safety rules for high-risk human-review routing
- aggregate image findings into category summaries before writing a final report
- keep final report generation downstream from validated structured data

## Near-Term Goal

The near-term goal is to produce an entire draft workflow:

```text
inspection images and officer comments
-> privacy-aware image preprocessing
-> image-level VLM assessment
-> fallback or review when needed
-> deterministic safety gating
-> category-level summaries
-> school-level consolidation
-> draft inspection report
```

At this stage, the priority is correctness, traceability, and simple reviewability rather than polish.

## After The Draft Works

Once the notebook version works end to end, the next step is to modularize the code.

Planned cleanup:

- move repeated notebook logic into small Python modules
- keep schemas, prompts, routing logic, aggregation, and report generation in separate files
- add more structured logging for model calls, retries, review triggers, and output paths
- improve exception handling where failures are expected and need clearer messages
- keep the code simple and readable, avoiding abstractions until they are useful

The notebook will still be useful as a demonstration and experimentation layer, but the reusable logic should live outside the notebook.

## Application Direction

After the modular version works, the plan is to experiment with a FastAPI backend.

Likely backend responsibilities:

- accept image and comment inputs
- run or queue the validation pipeline
- return image-level, category-level, and report-level results
- expose human-review items
- keep enough trace metadata to debug model behavior

After the backend shape is clearer, the frontend can be added.

Likely frontend responsibilities:

- upload or select inspection inputs
- show image-level findings and evidence
- show category summaries
- display human-review queues
- preview or export the draft report

This order keeps the project grounded: first prove the reasoning pipeline, then modularize it, then expose it through an API, and only then build the user-facing interface.
