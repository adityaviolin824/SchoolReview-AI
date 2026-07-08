# Running Instructions

Run all commands from this folder:

```bash
cd "/Users/adityaviolin824/Documents/Aditya Windows 2026/AdiFiles2/04 Future/Portfolio Project/05 School Condition Validator/CODE/backend"
```

## Required Keys

Real model runs require both provider keys in your environment or in `backend/.env`:

```bash
export GEMINI_API_KEY="your-gemini-key"
export OPENAI_API_KEY="your-openai-key"
```

Do not commit real keys.

## PDF Rendering On Mac

The backend uses ReportLab for PDF generation by default. This avoids installing
native macOS GTK/Pango/GObject libraries that WeasyPrint may need.

The generated PDF artifact is still saved as:

```text
final_report:pdf_report
```

Only opt into WeasyPrint if those native libraries are already installed:

```bash
export SCHOOL_VALIDATOR_PDF_RENDERER=weasyprint
```

For normal local testing on Mac, do not set `SCHOOL_VALIDATOR_PDF_RENDERER`.

## Option 1: Run Without API

Use the local JSON runner with the included sample request:

```bash
uv run scripts/run_pipeline_from_json.py \
  --input sample_data/sample_pipeline_request.json \
  --output school_validation_outputs/local_sample_result.json \
  --output-root school_validation_outputs/local_runs \
  --run-id local_sample \
```

What this uses:

- Request JSON: `sample_data/sample_pipeline_request.json`
- Images referenced by the JSON under: `sample_data/school/`
- Generated workflow files under: `school_validation_outputs/local_runs/local_sample/`
- Pipeline result JSON: `school_validation_outputs/local_sample_result.json`

To run image and category stages only, without final aggregation/report generation:

```bash
uv run scripts/run_pipeline_from_json.py \
  --input sample_data/sample_pipeline_request.json \
  --output school_validation_outputs/local_sample_result.json \
  --output-root school_validation_outputs/local_runs \
  --run-id local_sample \
  --skip-report
```

The sample request currently includes:

- `classroom`
- `fire_extinguisher`

Valid section names are:

```text
ceiling
classroom
corridor
electrical
exterior
fire_extinguisher
staircase
washroom
other
```

## Option 2: Run With FastAPI

Start the API:

```bash
uv run uvicorn school_safety_validator.api.fastapi_application:app --reload --host 127.0.0.1 --port 8000
```

Open Swagger UI in your browser:

```text
http://127.0.0.1:8000/docs
```

Swagger UI lets you run the API from the browser without writing `curl` commands.

### Swagger UI Flow

Use the **Try it out** button for each endpoint.

Swagger UI has three common input areas:

1. **Parameters**: small text boxes for values like `run_id`, `section_name`, and `artifact_name`.
2. **Request body**: a large JSON box. Paste JSON here only when the endpoint shows a request body.
3. **file** upload field: a browser file picker. Use this for images. Do not paste image paths into JSON for the API upload step.

For the API flow, image files are uploaded through the browser file picker. The API does not accept `image_path` in the create-run JSON.

#### 1. Check The API Is Running

Open:

```text
GET /health
```

Click:

1. **Try it out**
2. **Execute**

Expected response:

```json
{
  "status": "ok"
}
```

#### 2. Create An Inspection Run

Open:

```text
POST /inspection-runs
```

Click **Try it out**.

Swagger will show a **Request body** JSON editor. Delete the placeholder JSON and paste this:

```json
{
  "school": {
    "name": "Example Government School",
    "inspection_date": "2026-06-30",
    "location": "Example District"
  },
  "sections": [
    {
      "section_name": "classroom",
      "section_comment": "Classroom inspection comments."
    }
  ]
}
```

Click **Execute**.

In the response, look for:

```json
{
  "run_id": "some-long-id",
  "status": "created",
  "sections": [
    "classroom"
  ]
}
```

Copy the `run_id` value. You will paste it into later **Parameters** boxes.

What this JSON means:

- `school.name`: school name shown in outputs.
- `school.inspection_date`: inspection date as text.
- `school.location`: location shown in outputs.
- `sections`: categories you want to inspect in this run.
- `section_name`: must be one of the valid section names listed above.
- `section_comment`: optional overall comment for that section.

To create a run with the same two sections as `sample_data/sample_pipeline_request.json`, use this request body instead:

```json
{
  "school": {
    "name": "Example Government School",
    "inspection_date": "2026-06-30",
    "location": "Example District, India"
  },
  "sections": [
    {
      "section_name": "classroom",
      "section_comment": "Classroom inspection sample with visible room-condition evidence."
    },
    {
      "section_name": "fire_extinguisher",
      "section_comment": "Fire extinguisher inspection sample."
    }
  ]
}
```

#### 3. Upload A Sample Image

Open:

```text
POST /inspection-runs/{run_id}/sections/{section_name}/images
```

Click **Try it out**.

Swagger will show **Parameters** and a form section. Fill them like this:

- `run_id`: paste the `run_id` from step 2
- `section_name`: `classroom`
- `comment`: `Field officer noted classroom condition concerns.`
- `file`: click **Choose File**, then choose this sample image from your computer:

```text
backend/sample_data/school/classroom/images/classroom_001.jpg
```

If your file picker needs the full path, choose:

```text
/Users/adityaviolin824/Documents/Aditya Windows 2026/AdiFiles2/04 Future/Portfolio Project/05 School Condition Validator/CODE/backend/sample_data/school/classroom/images/classroom_001.jpg
```

Important:

- The image path is selected in the **file** field only.
- Do not paste the image path into the create-run JSON.
- For `.jpg` and `.jpeg`, Swagger should send `image/jpeg`.
- For `.png`, Swagger should send `image/png`.

Click **Execute**.

Expected response includes:

```json
{
  "section_name": "classroom",
  "original_filename": "classroom_001.jpg"
}
```

To upload another image for the same section, repeat this same endpoint with the same `run_id` and `section_name`.

To upload for another section, change `section_name`. For example, if you created `fire_extinguisher` in step 2:

- `run_id`: same run id
- `section_name`: `fire_extinguisher`
- `comment`: `Field officer noted the extinguisher area should be checked.`
- `file`: choose:

```text
backend/sample_data/school/fire_extinguisher/images/fire_extinguisher_001.jpg
```

#### 4. Start The Pipeline

Open:

```text
POST /inspection-runs/{run_id}/start
```

Click **Try it out**.

Fill:

- `run_id`: paste the same `run_id`

Swagger will also show a **Request body** JSON editor. Paste this:

```json
{
  "generate_report": true,
}
```

Use:

- `generate_report: true` to run image checks, final aggregation, and report generation.
- `generate_report: false` to run image/category processing only.

Click **Execute**.

Expected response:

```json
{
  "run_id": "your-run-id",
  "status": "running"
}
```

This may take time because it calls Gemini/OpenAI.

Do not start the same `run_id` twice. The API only allows uploads before the run starts.

#### 5. Check Status

Open:

```text
GET /inspection-runs/{run_id}
```

Click **Try it out**.

Fill:

- `run_id`: paste the same `run_id`

Click **Execute**.

Repeat this until `status` becomes one of:

- `completed`
- `completed_with_human_review_required`
- `failed`

Look at these fields:

- `overall_status`
- `provisional`
- `human_review_required`
- `human_review_items`
- `artifacts`
- `errors`

What the status values mean:

- `created`: run exists, but processing has not started.
- `running`: pipeline is still processing.
- `completed`: pipeline completed and no human review is required.
- `completed_with_human_review_required`: pipeline completed, but at least one item should be reviewed manually.
- `failed`: the pipeline failed. Check the `errors` field and the server terminal logs.

If `artifacts` is empty, reports are not ready yet, report generation was skipped, or the run failed before report files were created.

#### 6. Do Human Review If Flagged

If `human_review_required` is `true`, open:

```text
GET /inspection-runs/{run_id}/human-review
```

Click **Try it out**, enter `run_id`, then **Execute**.

If it returns a `review_id`, open:

```text
POST /inspection-runs/{run_id}/human-review/{review_id}
```

Click **Try it out**.

Fill:

- `run_id`: same run id
- `review_id`: copied from the human-review response

Request body:

```json
{
  "status": "reviewed",
  "notes": "Reviewed manually."
}
```

Allowed `status` values:

- `reviewed`
- `deferred`

Click **Execute**.

This records the review decision in the in-memory API run state. It does not rerun the pipeline.

#### 7. Download A Report Artifact

After the run completes, check the `artifacts` field in:

```text
GET /inspection-runs/{run_id}
```

If it includes:

```text
final_report:markdown_report
```

Open:

```text
GET /inspection-runs/{run_id}/artifacts/{artifact_name}
```

Click **Try it out**.

Fill:

- `run_id`: same run id
- `artifact_name`: `final_report:markdown_report`

Click **Execute**.

Swagger UI will show the response and may provide a download link.

Common artifact names after report generation:

```text
final_report:markdown_report
final_report:html_report
final_report:pdf_report
final_report:report_content_json
final_report:report_generation_payload
final_aggregation:final_aggregation_output
final_aggregation:final_aggregation_raw_output
final_aggregation:final_aggregation_payload
```

Only use names that actually appear in your run's `artifacts` list. The API filters this list to files that are downloadable for that run.

### Swagger Troubleshooting

If Swagger returns `400` on image upload:

- Check that the file is `.jpg`, `.jpeg`, or `.png`.
- Check that you selected the file in the **file** field.
- Check that the file is 10 MB or smaller.
- Check that the uploaded image is a real readable image.

If Swagger returns `404`:

- Check that the `run_id` was copied exactly.
- Check that `section_name` matches a section you created in step 2.
- Check that the artifact name is copied exactly from the status response.

If Swagger returns `409`:

- You may be trying to upload after the run already started.
- You may be trying to start the same run more than once.

If status becomes `failed`:

- Open the server terminal where Uvicorn is running.
- Read the logged error there.
- Common causes are missing `GEMINI_API_KEY` or missing `OPENAI_API_KEY`.

If the browser shows the API docs but execution does nothing:

- Make sure the Uvicorn server is still running.
- Keep the terminal window open while using Swagger.

### Optional Curl Flow

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Create a run:

```bash
curl -s -X POST http://127.0.0.1:8000/inspection-runs \
  -H "Content-Type: application/json" \
  -d '{
    "school": {
      "name": "Example Government School",
      "inspection_date": "2026-06-30",
      "location": "Example District"
    },
    "sections": [
      {
        "section_name": "classroom",
        "section_comment": "Classroom inspection comments."
      }
    ]
  }'
```

Copy the returned `run_id`.

Upload one sample image:

```bash
curl -s -X POST "http://127.0.0.1:8000/inspection-runs/RUN_ID/sections/classroom/images" \
  -F "file=@sample_data/school/classroom/images/classroom_001.jpg;type=image/jpeg" \
  -F "comment=Field officer noted classroom condition concerns."
```

Start the pipeline:

```bash
curl -s -X POST "http://127.0.0.1:8000/inspection-runs/RUN_ID/start" \
  -H "Content-Type: application/json" \
  -d '{"generate_report": true}'
```

Check run status:

```bash
curl -s "http://127.0.0.1:8000/inspection-runs/RUN_ID"
```

List human-review items:

```bash
curl -s "http://127.0.0.1:8000/inspection-runs/RUN_ID/human-review"
```

If the previous response includes a `review_id`, record a manual review decision:

```bash
curl -s -X POST "http://127.0.0.1:8000/inspection-runs/RUN_ID/human-review/REVIEW_ID" \
  -H "Content-Type: application/json" \
  -d '{"status": "reviewed", "notes": "Reviewed manually."}'
```

Download a report artifact listed in the status response:

```bash
curl -L "http://127.0.0.1:8000/inspection-runs/RUN_ID/artifacts/final_report:markdown_report" \
  -o school_safety_final_report.md
```

API-run files are written under:

```text
school_validation_outputs/api_runs/RUN_ID/
```

The FastAPI run store is in memory. If you restart the API server, the run list is cleared, but files already written under `school_validation_outputs/api_runs/` remain on disk.

## Upload Rules

FastAPI image uploads must be:

- `.jpg`, `.jpeg`, or `.png`
- readable image files
- 10 MB or smaller

Use this content type mapping:

- `.jpg` or `.jpeg`: `image/jpeg`
- `.png`: `image/png`

## Run Tests

```bash
UV_CACHE_DIR=/private/tmp/school-validator-uv-cache UV_PYTHON_INSTALL_DIR=/private/tmp/school-validator-uv-python PYTHONDONTWRITEBYTECODE=1 uv run --no-sync pytest -q -p no:cacheprovider
```
