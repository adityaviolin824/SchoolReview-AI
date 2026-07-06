# Notebook Code Review Feedback

> Historical note: This file captures a static notebook review comparing two implementation versions and identifying the next fixes.

Files reviewed:

- `school-safety-validator-consolidation-simplified.ipynb`
- `school-safety-validator-langgraph-with-consolidation.ipynb`

Review scope:

- Static notebook/code review.
- Non-executing syntax compilation of all code cells.
- Workflow and JSON-shape comparison between the original consolidation notebook and the simplified notebook.

What I did not do:

- I did not execute the notebooks.
- I did not call Gemini, OpenAI, or LangSmith.
- I did not validate model names against live provider APIs.
- I did not inspect real model outputs beyond code-visible JSON contracts.

## Validation Results

No embedded API-key-looking secret was found. Both notebooks only reference API keys through environment variables:

- `GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]`
- `OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]`

Both notebooks pass non-executing Python syntax compilation across all code cells:

```text
school-safety-validator-consolidation-simplified.ipynb: all code cells compiled successfully
school-safety-validator-langgraph-with-consolidation.ipynb: all code cells compiled successfully
```

So I did not find syntax errors in either notebook.

## Overall Verdict

The simplified notebook is the better current working base.

Main reasons:

- It removes unused future state.
- It removes reducer annotations from non-LangGraph state.
- It removes the no-op routing node.
- It keeps full image audit JSON separate from compact category summary JSON.
- It prepares a smaller, cleaner final LLM payload.
- It fixes failed image jobs being absent from the human-review queue.
- It adds a clear error when final aggregation is run before category outputs exist.

The original notebook is still useful as an audit/history reference, but I would continue development from:

```text
school-safety-validator-consolidation-simplified.ipynb
```

## Findings

### P1: Original notebook drops failed image jobs from the human-review queue

File:

- `school-safety-validator-langgraph-with-consolidation.ipynb`

Evidence:

- Failed image JSON is marked as requiring review, but has no review item:
  - line 948: `def image_state_to_result(...)`
  - failed branch returns `human_review.required = True`
  - failed branch returns `"item": None`
- Category run only appends review items from final image state:
  - line 1419: `if final_image_state.get("human_review_item"):`
  - line 1420: appends `final_image_state["human_review_item"]`

Why this matters:

If an image job fails, the saved image JSON says review is required, but the category and full-run human-review queues can miss that image. This makes failed jobs easy to overlook in the downstream review process.

Status in simplified notebook:

Fixed.

Evidence:

- `school-safety-validator-consolidation-simplified.ipynb`
- line 803: `build_human_review_item(...)` accepts completed or failed image state.
- line 874: failed image JSON includes a real `human_review.item`.
- line 1303: category run reads `image_result["human_review"].get("item")`.
- line 1305: review item is appended to `human_review_queue`.

Recommendation:

Keep the simplified behavior. Do not carry the original failed-job queue logic forward.

### P1: Original category classification can hide failed evidence behind low or medium severity

File:

- `school-safety-validator-langgraph-with-consolidation.ipynb`

Evidence:

- line 1233: `def classify_category(...)`
- line 1244: failed jobs set `failed_result_seen = True`
- lines 1252-1256: high, medium, and low severities are returned before checking `failed_result_seen`
- line 1258: `failed_result_seen` is only considered after low severity

Why this matters:

If a category has one failed image and one low-severity completed image, the original code can classify the category as `minor_maintenance` instead of `insufficient_evidence`. That is risky because missing evidence should not be hidden by a lower-risk completed image.

Status in simplified notebook:

Improved.

Evidence:

- `school-safety-validator-consolidation-simplified.ipynb`
- line 1126: `def classify_category(...)`
- line 1145: high severity still returns `urgent_review`
- line 1147: failed or unclear evidence returns `insufficient_evidence` before medium/low

Recommendation:

Keep the simplified logic. It is a better safety-oriented default.

### P2: Review-model failure discards earlier successful assessment in both notebooks

Files:

- `school-safety-validator-langgraph-with-consolidation.ipynb`
- `school-safety-validator-consolidation-simplified.ipynb`

Evidence:

- Original:
  - line 1116: `def run_review_model_node(...)`
  - review failure returns `status = "failed"` and error details.
  - line 948: `image_state_to_result(...)`
  - failed branch writes `primary_assessment`, `backup_assessment`, `review_assessment`, and `final_assessment` as `None`.
- Simplified:
  - line 1012: `def run_review_model_node(...)`
  - review failure returns `status = "failed"` and error details.
  - line 846: `image_state_to_result(...)`
  - failed branch writes `primary_assessment`, `backup_assessment`, `review_assessment`, and `final_assessment` as `None`.

Why this matters:

The review model is only called after a primary or backup model already produced a usable assessment. If the review model fails, the notebooks mark the whole image job as failed and drop the earlier successful assessment from saved JSON. This loses useful audit evidence.

Practical fix:

Do not discard the earlier successful assessment when only the review step fails.

Low-complexity option:

- In `run_review_model_node`, on review failure:
  - keep `status` as not failed, or use a separate `review_error`
  - keep existing `final_assessment`
  - set `human_review_required = True`
  - add a human-review note such as: `Independent review failed; use prior model assessment only as provisional.`

Alternative:

- Keep `status = "failed"` but preserve `primary_assessment`, `backup_assessment`, and previous `final_assessment` in the failed image JSON.

I recommend the first option because the image still has a model assessment, but it should be treated as provisional and queued for human review.

### P2: Final LLM rules are not yet enforced after the future LLM call

Files:

- `school-safety-validator-langgraph-with-consolidation.ipynb`
- `school-safety-validator-consolidation-simplified.ipynb`

Evidence:

- Original:
  - line 35 cell builds `final_llm_payload`
  - rules include: `overall_status must not be weaker than deterministic_status_floor`
  - no final LLM call or post-call validation exists yet
- Simplified:
  - line 31 cell builds `final_llm_payload`
  - rules include the same status-floor rule
  - no final LLM call or post-call validation exists yet

Why this matters:

Prompt rules are helpful, but they do not guarantee the final LLM will obey the deterministic status floor or provisional flag requirement. Once the final LLM call is added, the code should validate the structured output.

Practical fix:

After the final LLM returns `FinalInspectionLLMReport`, add a small deterministic validation function:

- If `global_rollup["deterministic_status_floor"] == "urgent_review_required"`, force or reject weaker `overall_status`.
- If `global_rollup["human_review_required"]` is true, force `provisional = True`.
- If `not_inspected_categories` is non-empty, ensure limitations mention them.

This would enforce the rule outside the prompt instead of relying only on model compliance.

### P2: Original final aggregation can silently proceed with zero category outputs

File:

- `school-safety-validator-langgraph-with-consolidation.ipynb`

Evidence:

- line 1553: `def load_category_outputs(...)`
- if no files exist, the function returns `{}`.
- line 1749: `init_final_llm_state(...)` builds final state from that empty dict.

Why this matters:

If the category run did not happen, failed, or wrote outputs somewhere unexpected, the final aggregation prep can still produce an apparently valid empty rollup. That makes an operational failure look like an inspection result.

Status in simplified notebook:

Fixed.

Evidence:

- `school-safety-validator-consolidation-simplified.ipynb`
- line 1372: `def load_category_outputs(...)`
- line 1392: raises `FileNotFoundError` if no category outputs are loaded.

Recommendation:

Keep the simplified behavior.

### P3: `LANGSMITH_PROJECT` is required even though tracing may be operationally optional

Files:

- `school-safety-validator-langgraph-with-consolidation.ipynb`
- `school-safety-validator-consolidation-simplified.ipynb`

Evidence:

- Original line 1461:
  - `project_name=os.environ["LANGSMITH_PROJECT"]`
- Simplified line 1346:
  - `project_name=os.environ["LANGSMITH_PROJECT"]`

Why this matters:

The full category run fails immediately if `LANGSMITH_PROJECT` is missing, even if the model API keys are present and the user only wants a local run. Since LangSmith is useful but not core to the validation logic, this is a small workflow fragility.

Practical fix:

Use a default project name or read with `os.getenv`:

```python
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "school-safety-validator")
```

Then use:

```python
with tracing_context(enabled=True, project_name=LANGSMITH_PROJECT):
```

This avoids requiring LangSmith configuration for local runs.

### P3: Review escalation still runs for unrelated officer comments

Files:

- `school-safety-validator-langgraph-with-consolidation.ipynb`
- `school-safety-validator-consolidation-simplified.ipynb`

Evidence:

- Original `should_use_review_model(...)` includes:
  - `contradicts_visual_evidence`
  - `unrelated`
  - `unclear`
- Simplified keeps the same behavior.

Why this matters:

The shared prompt says messy or unrelated officer comments should not override visible evidence. Routing to an independent review model is not the same as requiring human review, so this is not a correctness bug. But it can increase cost and latency when the visible evidence is otherwise clear.

Practical fix:

Consider removing `unrelated` from review escalation and keeping:

- high risk
- unclear risk
- model-required human review
- unclear findings
- low-confidence findings
- direct contradiction

This is a behavior change. It is worth testing against a few known examples before changing.

### P3: Simplified notebook changes category JSON shape

File:

- `school-safety-validator-consolidation-simplified.ipynb`

Evidence:

- Original line 1319 includes:
  - `"image_results": category_results`
- Simplified category summary does not include `image_results`.

Why this matters:

This is an intentional improvement for final aggregation, but it is still a breaking output-shape change if any downstream notebook or script expects category JSON to contain full image results.

Recommendation:

Keep the simplified shape for the final-report workflow, but document the contract clearly:

- `model_outputs/<category>/<image>.json` is the full audit source.
- `category_outputs/<category>_image_assessments.json` is the compact category summary source.

This is already mostly documented in `PROGRESS_2.md`. Keep that distinction consistent.

### P3: Synchronous OpenAI calls run inside async graph nodes

Files:

- `school-safety-validator-langgraph-with-consolidation.ipynb`
- `school-safety-validator-consolidation-simplified.ipynb`

Evidence:

- `run_openai_vision_assessment(...)` is synchronous.
- It is called inside async LangGraph nodes:
  - `run_backup_model_node`
  - `run_review_model_node`

Why this matters:

With `MAX_CONCURRENT_REQUESTS = 1`, this is unlikely to cause practical trouble today. If concurrency is raised later, synchronous OpenAI calls can block the event loop and reduce the benefit of async orchestration.

Recommendation:

No immediate change is required. If concurrency is increased later, convert OpenAI backup/review calls to async or run the sync call in a thread.

## Is The Simplified Code Better?

Yes.

The simplified notebook fits the current project stage better because it removes non-working future abstractions and gives a cleaner path to final report generation.

Specific improvements:

- Simpler imports.
- Simpler state.
- No unused human-review decision fields.
- No unused `FinalLLMState`.
- No no-op graph node.
- Less duplicated model cleanup.
- Failed jobs enter human review.
- Category outputs are compact.
- Final aggregation fails clearly when no category outputs exist.

The simplified notebook still keeps the important parts:

- image-level LangGraph
- local privacy preprocessing
- Gemini primary model
- OpenAI backup model
- OpenAI independent review model
- full image-level audit JSON
- compact category-level summaries
- deterministic pre-LLM global rollup

## Recommended Next Fixes

I would make these changes in this order:

1. Fix review-model failure handling so a failed independent review does not erase the earlier successful primary/backup assessment.
2. Add deterministic validation after the future final LLM call.
3. Make `LANGSMITH_PROJECT` default gracefully when missing.
4. Decide whether unrelated officer comments should still trigger independent review.
5. Keep documenting the compact category JSON contract so downstream code does not expect `image_results` in category outputs.

I would not spend time right now on:

- Major class/module extraction.
- A full category-level LangGraph.
- Async conversion of OpenAI calls while concurrency remains `1`.
- Building a large report templating system before the final LLM output shape is tested.
