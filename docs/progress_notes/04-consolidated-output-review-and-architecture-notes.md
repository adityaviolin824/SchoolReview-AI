# SchoolReview AI: Consolidated Output Review Notes

> Historical note: This file captures a June 2026 review pass over consolidated model outputs. Model names and architecture ideas reflect the project state at that time.

Generated: 2026-06-21  
Source file reviewed: `all_categories_image_assessments_with_privacy_updated_consolidated.json`

## 1. Context

This review is based on the consolidated image-assessment JSON for the SchoolReview AI MVP.

The file contains image-level safety assessments generated using:

- Primary model: `gemini-3.1-flash-lite`
- Backup model: `gpt-4.1-mini`
- Review model: `gpt-4.1-mini`
- Confidence threshold: `0.8`
- Total categories: `9`
- Total images: `27`

The current pipeline includes several implementation pieces:

- Image-level structured outputs
- Primary and review model separation
- Category-wise grouping
- Officer-comment comparison
- Confidence thresholding
- Human-review flagging
- Traceable final-assessment source

However, the output also shows several design and safety-routing issues that should be fixed before final report generation.

---

## 2. High-level review result

The pipeline is a useful early version, but the biggest current weakness is not the VLM itself.

The bigger issue is this:

> The review model is currently allowed to override or soften safety-critical human-review decisions too easily.

For a safety-inspection workflow, this is risky. A model should not freely downgrade cases involving:

- Visible structural cracks
- Exposed electrical components
- Damaged or corroded fire extinguishers
- Damaged railings
- Severe dampness or wall deterioration
- Ambiguous evidence in high-risk categories

The system should use deterministic safety rules first, then use models for explanation and evidence summarization.

---

## 3. File-level observations

| Item | Value |
|---|---:|
| Total images | 27 |
| Categories listed | 9 |
| Real non-empty categories | 8 |
| Empty category | `other` |
| Primary model final outputs | 16 |
| Review-model final outputs | 11 |
| Final human-review flags | 2 |
| Missing officer comments | 4 |
| Final model-comment conflicts | 2 |
| Average final confidence | Approximately `0.86` |

The broad output quality appears usable for an MVP, but the final human-review count appears too low given the safety-critical visible issues present in the file.

---

## 4. Major issues found

### 4.1 Category-level officer comments are contaminated

Two category-level officer comments appear to be routed incorrectly.

| Category | Current issue |
|---|---|
| `classroom` | Overall comment talks about school garden mango trees and kitchen lunch timing. This is unrelated to classroom safety. |
| `exterior` | Overall comment talks about computers and drinking water taste. This is unrelated to exterior wall condition. |

This is likely a data ingestion, comment-mapping, or metadata-routing issue.

This should be fixed before report generation. If these contaminated comments are passed into a text model, the model may produce a well-written but incorrect report.

#### Suggested fix

Add validation before category aggregation:

```python
def validate_category_comment(category_name: str, comment: str) -> dict:
    """Return whether a category-level officer comment appears relevant."""

    if not comment.strip():
        return {
            "is_relevant": False,
            "reason": "missing_comment"
        }

    irrelevant_keywords_by_category = {
        "classroom": ["garden", "mango", "kitchen", "lunch"],
        "exterior": ["computer", "drinking water", "taste"],
    }

    bad_terms = irrelevant_keywords_by_category.get(category_name, [])

    if any(term in comment.lower() for term in bad_terms):
        return {
            "is_relevant": False,
            "reason": "possible_misrouted_comment"
        }

    return {
        "is_relevant": True,
        "reason": "appears_relevant"
    }
```

Also add this field to every category summary:

```json
{
  "category_comment_status": "valid | missing | possibly_misrouted",
  "category_comment_validation_reason": "..."
}
```

---

### 4.2 Human-review flags are being downgraded too easily

Several primary model assessments correctly flagged human review, but the review model removed the flag.

Examples:

| Image | Visible issue | Primary says review? | Final says review? | Suggested final |
|---|---|---:|---:|---|
| `ceiling_003.jpg` | Extensive ceiling crack | Yes | No | Review required |
| `electrical_panel_003.jpg` | Open electrical panel with visible internals | Yes | No | Review required |
| `exterior_wall_003.jpg` | Diagonal exterior wall crack | Yes | No | Review likely required |
| `exterior_wall_002.jpg` | Visible dark dampness/staining | Yes | No | Depends on severity, but should remain flagged as maintenance attention |
| `washroom_002.jpg` | Wall stain near sink | Yes | No | Can be downgraded if clearly minor |
| `staircase_002.jpg` | Lighting disagreement | Yes | No | Downgrade may be acceptable because the reviewer found no visible dimness |

The review model should not have full authority to remove human review for high-risk categories.

#### Suggested fix

Use rule-first human-review gating:

```python
def force_human_review(category: str, assessment: dict) -> tuple[bool, str | None]:
    """Return whether human review must be forced by safety rules."""

    if category == "electrical":
        if assessment.get("exposed_component_visible") == "visible":
            return True, "Open or exposed electrical components require qualified review."

    if category in {"ceiling", "exterior"}:
        if assessment.get("crack_visible") == "visible":
            return True, "Visible structural crack requires human assessment."

    if category == "fire_extinguisher":
        if assessment.get("visible_damage_or_corrosion") == "visible":
            return True, "Damaged fire extinguisher requires qualified inspection or replacement."
        if assessment.get("service_tag_or_gauge_readable") == "not_visible":
            return True, "Fire extinguisher service status cannot be verified from visible evidence."

    if category == "staircase":
        if assessment.get("railing_damage_visible") == "visible":
            return True, "Railing damage affects fall protection and requires review."
        if assessment.get("step_or_floor_hazard_visible") == "visible":
            return True, "Visible stair or floor hazard requires review."

    if category == "washroom":
        if assessment.get("wet_floor_or_standing_water_visible") == "visible":
            return True, "Wet floor or standing water may create slip risk and requires review."
        if assessment.get("leakage_visible") == "visible":
            return True, "Visible leakage requires maintenance review."

    return False, None
```

Then apply this after model review:

```python
forced, reason = force_human_review(category_name, final_assessment)

if forced:
    final_assessment["requires_human_review"] = True
    final_assessment["forced_human_review_by_rule"] = True
    final_assessment["rule_review_reason"] = reason
```

Important principle:

> A review model may upgrade human review, but should not downgrade rule-forced human review.

---

### 4.3 Review triggers are not auditable enough

The file shows `review_used: true`, but it does not always explain why review was triggered.

This is important because some reviewed images had confidence above the threshold.

For example, a review might be triggered because of:

- Low confidence
- Missing officer comment
- High-risk category
- Possible model-comment conflict
- Random audit sampling
- Schema validation issue
- Safety-critical issue type

Without this metadata, an evaluator cannot tell whether the graph is behaving intentionally or randomly.

#### Suggested fix

Add a field like:

```json
{
  "review_trigger_reason": "low_confidence | missing_comment | high_risk_category | model_comment_conflict | schema_repair | random_audit | rule_triggered"
}
```

For multiple reasons:

```json
{
  "review_trigger_reasons": [
    "low_confidence",
    "high_risk_category"
  ]
}
```

Recommended rule:

```python
def get_review_triggers(category: str, assessment: dict, officer_comment: str) -> list[str]:
    triggers = []

    if assessment.get("confidence", 1.0) < 0.8:
        triggers.append("low_confidence")

    if not officer_comment.strip():
        triggers.append("missing_comment")

    if category in {"electrical", "fire_extinguisher", "staircase"}:
        if assessment.get("visual_concern_level") in {"potential_concern_visible", "major_visible"}:
            triggers.append("high_risk_category")

    if assessment.get("agrees_with_comment") == "no":
        triggers.append("model_comment_conflict")

    return triggers
```

---

### 4.4 The schema mixes observation and judgement

The current schema includes useful fields like:

- `crack_visible`
- `stain_or_dampness_visible`
- `surface_damage_visible`
- `pathway_obstruction_visible`
- `railing_damage_visible`

But it also mixes these with judgement fields like:

- `visual_concern_level`
- `requires_human_review`
- `assessment_comment`

This makes downstream aggregation harder.

#### Suggested fix

Separate the output into four layers:

```json
{
  "image_name": "example.jpg",
  "section": "ceiling",
  "visual_observations": [
    {
      "issue_type": "crack",
      "visibility": "visible",
      "evidence": "A diagonal crack is visible across the ceiling surface.",
      "confidence": 0.85
    }
  ],
  "risk_assessment": {
    "severity": "medium",
    "requires_human_review": true,
    "reason": "Visible ceiling crack requires human assessment."
  },
  "officer_comment_assessment": {
    "comment_present": true,
    "agreement": "supports_visual_evidence | contradicts_visual_evidence | unrelated | no_comment",
    "reason": "Officer comment mentions a crack, which is visible in the image."
  },
  "recommended_action": {
    "action_type": "maintenance_review",
    "action_text": "Inspect the crack and monitor for progression."
  }
}
```

This is more defensible than letting one free-text `assessment_comment` carry everything.

---

### 4.5 `surface_damage_visible` is too vague

In the ceiling and exterior categories, `surface_damage_visible` creates ambiguity.

For example, if a crack is visible, does that count as surface damage?

Some model outputs treat cracks as surface damage. Others do not.

#### Suggested fix

Do not use one broad field. Split it:

```json
{
  "crack_visible": "visible | not_visible | unclear",
  "stain_or_dampness_visible": "visible | not_visible | unclear",
  "paint_peeling_visible": "visible | not_visible | unclear",
  "spalling_or_broken_surface_visible": "visible | not_visible | unclear",
  "hole_or_missing_material_visible": "visible | not_visible | unclear"
}
```

This reduces model disagreement caused by schema interpretation rather than visual reasoning.

---

### 4.6 Some wording is too confident

Several outputs use wording like:

- "good condition"
- "well-maintained"
- "no safety hazards"
- "serviceable"

This is too strong for single-image inspection.

A VLM can say what is visible. It should not certify condition.

#### Better wording

Instead of:

> The classroom is tidy and well-organized. No safety hazards are visible.

Use:

> No visible obstructions, clutter, or major damage are observed in this image.

Instead of:

> The electrical panel appears to be in good condition.

Use:

> The panel appears closed and no visible damage or obstruction is observed from this view.

Instead of:

> The ceiling appears to be in good condition.

Use:

> No visible cracks, stains, or surface damage are observed in this image.

Key principle:

> The system should report visible evidence, not certify safety.

---

### 4.7 Missing comments should not always trigger review

There are 4 images with missing officer comments.

Missing comments should be flagged, but not necessarily sent to human review unless the image itself has risk or ambiguity.

Recommended distinction:

```json
{
  "officer_comment_status": "present | missing | irrelevant | contradictory",
  "documentation_gap": true,
  "requires_human_review": false
}
```

A missing comment is a documentation gap. It becomes human-review-worthy only when paired with:

- Visible risk
- Low confidence
- Ambiguous evidence
- High-risk section
- Model-comment conflict
- Insufficient evidence

---

### 4.8 Empty `other` category should not appear in final report

The file includes an `other` category with zero images.

This is fine internally, but it should not appear in the final report unless you want a line like:

> No images were submitted for other/unclassified areas.

For a clean MVP report, suppress empty categories by default.

---

## 5. Better LangGraph architecture

Do not pass the entire JSON directly into one report-generation model.

Use category-wise consolidation.

### Recommended graph

```text
Upload images + comments
        ↓
Image validation and metadata extraction
        ↓
Route images by category
        ↓
Parallel async image-level VLM analysis
        ↓
Schema validation and repair
        ↓
Image-level rule-based safety gating
        ↓
Optional review model for selected images
        ↓
Rule-forced human-review override
        ↓
Category aggregation nodes
        ↓
Category-level risk classification
        ↓
School-level consolidation
        ↓
Final report writer
        ↓
Final audit node
        ↓
Human review queue
```

### Suggested LangGraph nodes

```text
validate_inputs_node
route_by_category_node

ceiling_image_analysis_node
classroom_image_analysis_node
corridor_image_analysis_node
electrical_image_analysis_node
exterior_image_analysis_node
fire_extinguisher_image_analysis_node
staircase_image_analysis_node
washroom_image_analysis_node

schema_validation_node
review_decision_node
review_model_node
rule_based_safety_gate_node

ceiling_aggregator_node
classroom_aggregator_node
corridor_aggregator_node
electrical_aggregator_node
exterior_aggregator_node
fire_extinguisher_aggregator_node
staircase_aggregator_node
washroom_aggregator_node

school_summary_aggregator_node
final_report_writer_node
final_safety_audit_node
human_review_queue_node
```

### Why category-wise consolidation is better

| Approach | Problem |
|---|---|
| One giant report model call | Higher chance of missed details, over-trusting bad comments, and weaker auditability |
| Category-wise aggregation | Cleaner debugging, better safety rules, easier retries, better LangGraph demonstration |
| Rule-first safety gating | More auditable than relying on model judgement alone |

The final report model should not decide raw safety. It should write a readable report from validated category summaries.

---

## 6. Recommended data model

### Image-level result

```json
{
  "image_id": "electrical_panel_003.jpg",
  "category": "electrical",
  "status": "completed",
  "model_trace": {
    "primary_model": "gemini-3.1-flash-lite",
    "review_model": "gpt-4.1-mini",
    "final_assessment_source": "review_model",
    "review_used": true,
    "review_trigger_reasons": ["low_confidence", "high_risk_category"]
  },
  "officer_comment": {
    "text": "The electrical panel area appears exposed and needs attention.",
    "status": "present",
    "agreement": "partially_supported",
    "reason": "Exposed panel is visible, but access obstruction is not visible."
  },
  "visual_findings": [
    {
      "issue_type": "exposed_electrical_component",
      "severity": "high",
      "evidence": "Panel door is open and internal components are visible.",
      "confidence": 0.75
    }
  ],
  "uncertainties": [
    "Electrical safety cannot be confirmed from the image alone."
  ],
  "requires_human_review": true,
  "forced_human_review_by_rule": true,
  "rule_review_reason": "Open or exposed electrical components require qualified review.",
  "recommended_action": "Have the panel inspected and secured by qualified maintenance staff."
}
```

### Category summary

```json
{
  "category": "electrical",
  "image_count": 3,
  "category_status": "urgent_review",
  "issue_counts": {
    "high": 1,
    "medium": 0,
    "low": 1
  },
  "human_review_required": true,
  "key_findings": [
    {
      "image_id": "electrical_panel_003.jpg",
      "issue_type": "exposed_electrical_component",
      "severity": "high",
      "evidence": "Panel door is open and internal components are visible."
    }
  ],
  "documentation_gaps": [
    {
      "image_id": "electrical_panel_002.jpg",
      "gap": "No officer comment was provided."
    }
  ],
  "recommended_actions": [
    "Secure and inspect the open electrical panel.",
    "Monitor minor corrosion on the closed panel."
  ]
}
```

---

## 7. Suggested category-level statuses

Use a small controlled vocabulary.

```text
acceptable_visible_condition
minor_maintenance
attention_required
urgent_review
insufficient_evidence
```

### Suggested status rules

```python
def classify_category(image_results: list[dict]) -> str:
    if any(result["requires_human_review"] for result in image_results):
        return "urgent_review"

    if any_has_high_severity_issue(image_results):
        return "urgent_review"

    if any_has_medium_severity_issue(image_results):
        return "attention_required"

    if any_has_low_severity_issue(image_results):
        return "minor_maintenance"

    if any_result_insufficient_evidence(image_results):
        return "insufficient_evidence"

    return "acceptable_visible_condition"
```

---

## 8. Suggested severity rules

### High severity

Use high severity for:

- Exposed electrical components
- Fire extinguishers visibly damaged, corroded, missing hose, unreadable gauge, or likely not serviceable
- Staircase railing damage or missing fall protection
- Large visible structural cracks in ceiling or exterior wall
- Standing water or visible leakage creating slip/electrical risk

### Medium severity

Use medium severity for:

- Wall dampness or staining suggesting possible moisture issue
- Broken or uneven washroom tile
- Corridor obstruction reducing movement space
- Surface damage on exterior walls
- Dim staircase lighting if visible and not purely a camera-exposure artifact

### Low severity

Use low severity for:

- Minor clutter not blocking the main path
- Minor dirt or scuff marks
- Minor staining without visible damage
- Cosmetic rust on closed equipment housing

---

## 9. Recommended model usage

### Current MVP without extra spending

```text
Bulk image extraction:
gemini-3.1-flash-lite

Review model:
gpt-4.1-mini

Category consolidation:
gpt-4.1-mini

Final report generation:
gpt-4.1-mini

Safety-critical human-review decision:
deterministic rules first, model explanation second
```

This is acceptable for the MVP if you fix the human-review rules.

### Possible later version if additional model budget is available

```text
Bulk image extraction:
gemini-3.1-flash-lite

Risky or low-confidence image review:
stronger tested review model

Category consolidation:
stronger tested text model

Final report writing:
stronger tested text model

Cheap final formatting if needed:
low-cost formatting model
```

The reason to test a stronger paid setup would be the final consolidation and safety-audit steps, where instruction following and conservative handling of human-review decisions matter.

### Important model policy

Do not use the expensive model for every image.

Use it only for:

- Low-confidence cases
- High-risk categories
- Model-comment conflicts
- Schema repair failures
- Rule-triggered human-review cases
- Random audit samples

---

## 10. Recommended final report generation flow

The final report should be generated from category summaries, not raw image outputs.

### Flow

```text
Validated image findings
        ↓
Rule-based safety gating
        ↓
Category summaries
        ↓
School-level summary
        ↓
Final report writer
```

### Report model input should be compact

Do not pass the full primary, backup, review, and final objects.

Pass only:

```json
{
  "school_summary": {
    "total_images": 27,
    "categories_reviewed": 8,
    "overall_status": "urgent_review"
  },
  "category_summaries": [
    {
      "category": "electrical",
      "status": "urgent_review",
      "key_findings": [...],
      "human_review_required": true,
      "recommended_actions": [...]
    }
  ],
  "documentation_gaps": [...],
  "human_review_queue": [...]
}
```

This reduces noise and prevents the report model from re-litigating image-level decisions.

---

## 11. Final report structure

Use a predictable professional structure.

```text
1. Executive summary
2. Overall inspection status
3. Category-wise findings
4. High-priority human-review items
5. Maintenance-action items
6. Documentation gaps
7. Limitations
8. Appendix: image-level findings
```

### Required disclaimer

Include a short limitation section:

> This report is based only on visible evidence in the submitted images and officer comments. It does not certify structural, electrical, fire-safety, or hygiene compliance. Items marked for human review require assessment by qualified personnel.

This protects the project from overclaiming.

---

## 12. Concrete fixes before final report generation

### Must fix

- Fix contaminated category-level comments.
- Prevent review model from downgrading rule-forced human-review cases.
- Add `review_trigger_reasons`.
- Replace `"none"` and empty uncertainty strings with `uncertainties: []`.
- Split broad fields like `surface_damage_visible`.
- Avoid wording that certifies safety from a single image.
- Suppress empty `other` category unless explicitly needed.
- Add category-level status classification.

### Should fix

- Track cost per model call.
- Track latency per model call.
- Track schema validation failures.
- Track fallback and review usage reasons.
- Add random audit sampling for some high-confidence primary outputs.
- Add report-level limitation text.
- Add final audit node that checks whether high-risk findings were accidentally omitted from the final report.

### Nice to have

- Store image thumbnails or paths in the human-review queue.
- Add a Streamlit or simple frontend for reviewing flagged cases.
- Add evaluation labels and compare model outputs against expected issue labels.
- Add confusion matrix for issue-type detection.
- Add a reproducible benchmark script.

---

## 13. Suggested implementation checklist

### Step 1: Clean input metadata

- Validate category names.
- Validate image paths.
- Validate category-level officer comments.
- Mark comments as present, missing, contradictory, or possibly misrouted.

### Step 2: Normalize image-level outputs

- Convert current fields into a stable internal schema.
- Replace vague strings with controlled enums.
- Convert missing uncertainty strings into empty lists.
- Preserve primary and review outputs for audit.

### Step 3: Add rule-based safety gating

- Apply category-specific human-review rules.
- Never allow review model to override forced human-review flags.
- Add `forced_human_review_by_rule`.

### Step 4: Build category aggregators

- Count issues by severity.
- Summarize key findings.
- Collect documentation gaps.
- Produce category status.
- Produce recommended actions.

### Step 5: Build school-level aggregator

- Merge category summaries.
- Compute overall status.
- Build human-review queue.
- Build maintenance queue.
- Build missing-evidence list.

### Step 6: Generate final report

- Pass only compact validated summaries to the report model.
- Require concise, evidence-based wording.
- Include limitations.
- Include appendix with image-level references.

### Step 7: Add evaluation harness

Track:

- Issue recall
- False positives
- Human-review recall
- Schema failure rate
- Model disagreement rate
- Cost per image
- Latency per image
- Review trigger distribution
- Final report omission rate

---

## 14. Bottom-line recommendation

Use category-wise consolidation.

Do not pass the entire raw JSON into one text model and ask it to decide everything.

Current recommended MVP design:

```text
gemini-3.1-flash-lite:
    bulk image extraction

gpt-4.1-mini:
    current low-cost review and consolidation

stronger tested model:
    possible later option for review, category consolidation, and final audit

deterministic rules:
    final authority for safety-critical human-review routing
```

The current system is a working early prototype, but the reliability will come from the rule-based safety gates, category-wise aggregation, and auditability, not from using a bigger model everywhere.
