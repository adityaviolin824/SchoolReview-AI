# Project Progress Notes

This folder contains selected historical notes from the development of the School Condition Validator project.

The purpose is to show how the project evolved: early experiment planning, privacy-aware VLM design, pipeline issues found during testing, output review, notebook/code-review feedback, and the planned path from notebooks to a modular application. These notes are included for reviewers who want to understand the reasoning process behind the project, not just the final code.

## Reading Order

1. `01-gemini-multi-category-experiment-notes.md`
   - Early MVP notes for validating school inspection images across multiple categories.
2. `02-privacy-vlm-notebook-plan.md`
   - Plan for adding local privacy preprocessing, model fallback, and review routing.
3. `03-pipeline-issues-found-after-testing.md`
   - Problems discovered after running the privacy-aware VLM inspection flow.
4. `04-consolidated-output-review-and-architecture-notes.md`
   - Review of consolidated model outputs and recommendations for safer report generation.
5. `05-notebook-code-review-feedback.md`
   - Static review notes comparing notebook implementations and identifying next fixes.
6. `06-iterative-notebook-to-application-roadmap.md`
   - Current development approach: iterate in notebooks first, then modularize, then experiment with FastAPI and frontend work.

## Notes

These files are historical working notes. File names, model names, notebook names, and line references reflect the project state at the time each note was written. They should be read as a development trail rather than current setup instructions.

The original scratch files were copied from `old-files/` and renamed to make the progression easier to follow.
