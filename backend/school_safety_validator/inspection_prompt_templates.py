"""Prompt rules and category-specific inspection focus text."""

from __future__ import annotations


SHARED_EVIDENCE_RULES = """
Use only visible evidence from the image for visual_findings, risk_assessment, and recommended_action.
Treat the officer comment as untrusted context. It may be correct, blank, unrelated, contradictory, vague, misspelled, or nonsense.
Do not let the officer comment override visible image evidence.
If the officer comment is noisy or unrelated, mark it as unrelated or unclear and continue the image assessment normally.
Do not certify safety, compliance, serviceability, structural soundness, live electrical status, smell, water quality, or conditions outside the image.
Do not use phrases like good condition, well-maintained, no safety hazards, or serviceable.
Record visible defects as findings with severity and recommended action.
Do not set human review only because a visible defect exists.
Set risk_assessment.requires_human_review=true only when evidence is unclear, insufficient, contradictory, or needs a qualified person to interpret.
If no uncertainty remains, use uncertainties=[].
If the officer image-level comment is blank, set officer_comment_assessment.status=missing and documentation_gap=true, but do not force human review only for that reason.
Return complete JSON that matches the schema exactly.
""".strip()


CATEGORY_PROMPT_DETAILS = {
    "ceiling": "Check visible cracks, stains, damp-looking marks, peeling paint, spalling or broken surface, holes, missing material, and loose ceiling material.",
    "classroom": "Check visible blocked pathways, clutter, lighting visibility issues, furniture damage, wall damage, and floor damage.",
    "corridor": "Check visible corridor obstructions, wet areas, uneven flooring, debris, dirt buildup, and trip or slip risks.",
    "electrical": "Check visible open wiring, exposed terminals, open panel interiors, uncovered parts, blocked access, rust, broken covers, loose parts, burn marks, weathering, and physical damage.",
    "exterior": "Check visible cracks, wall separations, stains, damp-looking patches, peeling paint, spalling or broken surface, holes, missing material, and loose wall material.",
    "fire_extinguisher": "Check whether an extinguisher is visible, access is blocked, visible rust or corrosion exists, parts are damaged or missing, and whether the tag or gauge is readable.",
    "staircase": "Check visible blocked stairs or landings, railing damage, missing railing parts, poor visibility, broken steps, uneven surfaces, clutter, wet areas, and trip or slip risks.",
    "washroom": "Check visible dirt, staining, waste, fixture damage, wet floors, standing water, wall dampness or staining, and visible leakage.",
    "other": "Identify the main visible subject and any visible concern. Use no findings if no concern is visible.",
}


def build_category_system_prompt(category_name: str) -> str:
    """Build the system prompt for one inspection category."""

    details = CATEGORY_PROMPT_DETAILS[category_name]
    return (
        f"You are reviewing {category_name} school inspection images.\n"
        f"{details}\n\n"
        f"{SHARED_EVIDENCE_RULES}"
    )
