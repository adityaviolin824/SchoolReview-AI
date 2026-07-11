# SchoolReview AI: Guided Software Tour

SchoolReview AI supports a structured school-condition inspection workflow: capture evidence, assess visible conditions with model assistance, route uncertain findings for human review, and generate a report with downloadable artifacts.

This tour uses one complete inspection run with four selected categories and seven evidence images. The resulting report is an AI-assisted visual inspection summary, not a safety, compliance, structural-soundness, electrical-safety, or serviceability certification.

## 1. Start a new inspection

The workflow begins with the inspection context and the categories to include. Category-level comments are optional: the on-screen prompts are placeholders, so a blank field stays blank unless an inspector enters text. This keeps submitted context intentional and traceable.

![New inspection setup with school details, category selection, and optional category comments](./1.jpeg)

## 2. Upload evidence and add image comments

After creating the inspection, each selected category needs at least one JPG or PNG evidence image. Inspectors can add an optional comment for each image, select multiple files where needed, and see which categories are still missing evidence before assessment can begin.

![Evidence upload workspace with category rows, optional image comments, file selections, and readiness status](./2.jpeg)

## 3. Route uncertain evidence to human review

The assessment can identify evidence that needs qualified human judgment before reporting continues. The application surfaces that requirement immediately, shows the pending-review count in navigation, and directs the user to the review workspace.

![Human review prompt after the assessment flags an item for review](./4.jpeg)

## 4. Review the evidence in context

The human-review workspace brings together the inspection image, model findings, uncertainty notes, recommended action, and the reviewer comment. The reviewer can then record a decision before the report workflow moves forward.

![Human review workspace showing a fire extinguisher image, model inference, visible findings, uncertainty notes, and reviewer comment](./5.jpeg)

## 5. Unlock report generation after review

Once required review items are completed, the application makes the next step explicit: generate the final report. This prevents report creation from bypassing the human-review gate.

![Report-generation prompt after the required human review is completed](./6.jpeg)

## 6. Track report generation

The Reports page shows that generation is running, keeps the review and image counts visible, and refreshes automatically while report artifacts are prepared. It also preserves the processed and not-inspected category context.

![Reports page while final report generation is in progress](./7.jpeg)

## 7. Download completed report artifacts

When generation completes, the report status, overall outcome, artifact count, and download links are all available in one place. This run produced HTML, Markdown, PDF, report-content JSON, and the report-generation payload.

![Completed reports page with urgent-review outcome and five downloadable artifacts](./8.jpeg)

## 8. Inspect the generated PDF summary

The generated PDF opens with a visual-inspection summary and an explicit qualified-review boundary. The report records the evidence-image count and carries the limitation that the output is not a certification.

![Generated PDF cover page for the school inspection summary report](./9.jpeg)

## 9. Review category-level actions

Later PDF pages consolidate the category statuses, evidence IDs, review flags, and prioritized actions. This gives a reviewer a compact path from the submitted visual evidence to follow-up work.

![Generated PDF category summary table and priority actions](./10.jpeg)

## What This Demonstrates

- Structured collection of category-level and image-level inspection context.
- Evidence completeness checks before model assessment starts.
- Model-assisted visual findings separated from qualified human decisions.
- A required human-review checkpoint for uncertain or flagged evidence.
- Progress-aware report generation and downloadable HTML, Markdown, PDF, and JSON artifacts.
- Report language that remains limited to visible evidence and retains its review disclaimer.
