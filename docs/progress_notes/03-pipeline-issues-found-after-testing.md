# Pipeline Issues Found After Testing

> Historical note: This file captures issues discovered after testing the privacy-aware VLM inspection output. It is intentionally problem-focused.

This file lists the problems found in the current privacy-aware VLM inspection
output and notebook flow. It is intentionally focused on issues only, not
solutions.

## Priority 0: Critical Pipeline Reliability Issues

### 1. Failed image jobs can disappear from the final consolidated JSON

The all-category run prepared 27 image jobs, but the final consolidated JSON
contains only 26 image assessments.

Missing image:

```text
school/corridor/images/corridor_003.jpg
```

This is a serious issue because the missing image has an officer comment about
a visibly obstructed corridor. Excluding it makes the consolidated corridor
evidence look safer than it really is.

Current problem:

- The notebook uses `asyncio.gather(..., return_exceptions=True)`.
- It separates `successful_results` from `failed_results`.
- Only `successful_results` are saved into the final JSON.
- Failed jobs are printed, but not preserved in the consolidated output.

Impact:

- Downstream category-level reasoning will not know that an image failed.
- The final inspection summary may be incomplete or biased.
- Human review cannot see which images were skipped.

### 2. API failures and timeouts are not preserved as structured output

The notebook output shows Gemini quota/rate-limit issues and at least one
OpenAI timeout. However, failed image jobs are not saved with their image name,
category, error type, and error message in the final consolidated JSON.

Impact:

- Debugging depends on notebook cell output instead of durable files.
- Failed inspections are easy to miss.
- Later reruns cannot target only failed images cleanly.

## Priority 1: Major Hallucination And Evidence Issues

### 3. The model is making inspection conclusions beyond visible evidence

The final output often goes beyond what the image can prove.

Examples:

- Electrical image says wiring is "live", which cannot be visually confirmed.
- Exterior wall image says the wall is "structurally sound", which cannot be
  verified from a single image.
- Ceiling stain image says "moisture ingress", which is a cause inference, not
  a directly visible fact.
- Fire extinguisher outputs make serviceability/removal judgments that require
  qualified inspection.

Impact:

- The JSON appears more authoritative than the image evidence supports.
- Final reports may contain unsupported safety/compliance conclusions.
- Human reviewers may over-trust model-generated claims.

### 4. The model agrees with officer comments too easily

The final consolidated output has:

```text
yes                  22
no_officer_comment    4
no                    0
human_review_required 0
```

There are no direct disagreements and no cases where the model says the comment
requires human review.

Impact:

- The model appears anchored to officer comments.
- The system may validate comments instead of independently checking visual
  support.
- Contradictory or unverifiable comments may pass through too easily.

### 5. Confidence scores are unrealistically high

The confidence distribution is:

```text
1.0   -> 20 images
0.95  -> 5 images
0.9   -> 1 image
```

This is too confident for real inspection imagery, especially where the model
uses inferred language.

Impact:

- Confidence cannot currently be trusted for escalation.
- Low-quality or ambiguous assessments may avoid human review.
- The confidence threshold does not meaningfully separate strong and weak
  visual evidence.

### 6. The review model reinforces the primary model instead of challenging it

For escalated cases, the review prompt includes the previous model assessment.
The review model often restates and polishes the primary model's conclusion
instead of independently checking the image.

Impact:

- Incorrect primary assumptions can be amplified.
- Review output may appear more confident but not more reliable.
- The review step does not currently function as an independent verifier.

### 7. OpenAI backup/review calls do not receive full category-specific prompts

Gemini receives category-specific system prompts that define fields and limits.
The OpenAI backup/review helper receives a shorter generic prompt.

Impact:

- Backup/review behavior may be less constrained than Gemini behavior.
- Category-specific field meanings may be interpreted inconsistently.
- The backup/review model may be more likely to infer from officer comments.

## Priority 2: Schema Problems

### 8. Boolean fields force overconfident true/false decisions

Many schema fields are plain booleans, such as:

```python
crack_visible: bool
surface_damage_visible: bool
panel_access_clear: bool
accessible: bool
lighting_appears_adequate: bool
```

This forces the model to choose true or false even when the image is unclear or
the feature is not visible enough to judge.

Impact:

- `false` can mean either "definitely absent" or "not visible".
- The JSON loses uncertainty.
- Ambiguous image conditions become falsely precise.

### 9. Some schema fields mix multiple concepts

Example:

```python
water_or_slip_hazard_visible: bool
```

This mixes wall staining, dampness, standing water, leakage, and floor slip
risk. In the output, some washroom assessments mention visible water staining
while setting this field to `false`.

Impact:

- The JSON can become internally inconsistent.
- Downstream reasoning cannot distinguish wall stains from floor hazards.
- Human reviewers may not know what the boolean actually represents.

### 10. `safety_status` asks the image model for a broad safety judgment

The image-level model is currently asked to produce:

```python
safety_status: Literal["safe", "unsafe", "unclear"]
```

This encourages broad inspection conclusions from a single image.

Impact:

- The model may declare something safe or unsafe without enough evidence.
- Professional inspection decisions are mixed with visual observations.
- Final reports may overstate the VLM's authority.

## Priority 3: Privacy Preprocessing Issues

### 11. Haar Cascade face detection creates false positives

Some images report faces where no clear faces are present.

Example:

```text
ceiling_001.jpg -> faces_detected = 6
```

The privacy image shows blurred window/background regions rather than actual
faces.

Impact:

- Non-face regions can be blurred.
- Important inspection details may be degraded.
- Face counts in the JSON may be misleading.

### 12. Face blurring can erase inspection evidence

In `corridor_003.jpg`, the privacy image has a large blurred region over the
stacked boxes/obstruction area.

Impact:

- The VLM may receive an image where the relevant defect is partially erased.
- Obstruction, damage, stains, cracks, or labels could be hidden by false blur.
- Privacy preprocessing can reduce inspection accuracy.

## Priority 4: Data And Downstream Reasoning Issues

### 13. Some overall officer comments are intentionally unrelated to category evidence

Examples:

```text
classroom: The school garden has healthy mango trees, and the kitchen reportedly serves lunch before noon.
exterior: All computers were tested successfully, and the drinking water tastes acceptable.
```

These are source-data comments, not model hallucinations.

Impact:

- A future category-level model may incorrectly treat unrelated comments as
  valid category evidence.
- The category-level stage must identify unsupported or unrelated comments.

### 14. Individual output files use `.txt` extension for JSON content

The notebook saves structured JSON text under files like:

```text
school/corridor/privacy_model_outputs/corridor_001.txt
```

Impact:

- The content is JSON, but the extension suggests plain text.
- This may make later automated loading less clear.
- It is easy to confuse officer comment `.txt` files with model output `.txt`
  files.

### 15. Output comments sometimes hit the maximum length and appear truncated

Some `assessment_comment` values are exactly 240 characters and end awkwardly,
for example with incomplete phrases.

Impact:

- The output can look unpolished or incomplete.
- Important reasoning may be cut off.
- Truncated wording can reduce auditability.

## Priority 5: Configuration And Run-State Clarity Issues

### 16. Notebook output and saved JSON can reflect different runs

The notebook cell output shows earlier runs using `gemini-2.5-flash-lite`, while
the saved consolidated JSON records `gemini-3.1-flash-lite`.

Impact:

- It can be unclear which model/run produced which artifact.
- Debugging is harder when notebook outputs and saved files are out of sync.
- The final JSON needs stronger run metadata to avoid confusion later.

### 17. Category count excludes empty categories

The configured category list includes `other`, but the final JSON has only 8
categories because `other` has no images.

Impact:

- This is acceptable for now, but it should be explicit.
- Downstream code should know whether a category was skipped because it had no
  images or because it failed.

## Summary

The largest current risks are:

1. Failed images disappearing from the final JSON.
2. The VLM making unsupported inspection conclusions.
3. The model agreeing with officer comments too readily.
4. The review model reinforcing the primary model instead of independently
   checking it.
5. Privacy blurring creating false positives and degrading important visual
   evidence.

These should be fixed before building the category-level and school-level
reasoning stages.
