# School Safety Validator Backend

Local-first backend modules for the School Safety Validator prototype.

The current backend supports category-level image inspection, compact category
outputs, final aggregation, deterministic report artifact generation, and a
minimal FastAPI layer for testing staged inspection runs.

## Run The Local API

Run commands from this `backend/` folder.

Required for real model calls:

```bash
export GEMINI_API_KEY="your-gemini-key"
export OPENAI_API_KEY="your-openai-key"
```

Start the API:

```bash
uv run uvicorn school_safety_validator.api.fastapi_application:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Valid Inputs

Valid section names:

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

Image uploads must be readable `.jpg`, `.jpeg`, or `.png` files up to 10 MB.

Each run needs:

1. School metadata: `name`, `inspection_date`, `location`
2. One or more sections
3. Optional section-level comment
4. Zero or more uploaded images per section
5. Optional image-level comment per upload

## Minimal API Test Flow

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

Upload an image for the `classroom` section. Replace the image path with a real local image:

```bash
curl -s -X POST "http://127.0.0.1:8000/inspection-runs/RUN_ID/sections/classroom/images" \
  -F "file=@/absolute/path/to/classroom.png;type=image/png" \
  -F "comment=Visible classroom condition image."
```

Start the pipeline:

```bash
curl -s -X POST "http://127.0.0.1:8000/inspection-runs/RUN_ID/start" \
  -H "Content-Type: application/json" \
  -d '{"generate_report": true}'
```

Check status:

```bash
curl -s "http://127.0.0.1:8000/inspection-runs/RUN_ID"
```

List human-review items:

```bash
curl -s "http://127.0.0.1:8000/inspection-runs/RUN_ID/human-review"
```

Record a human-review decision when the status response includes a `review_id`:

```bash
curl -s -X POST "http://127.0.0.1:8000/inspection-runs/RUN_ID/human-review/REVIEW_ID" \
  -H "Content-Type: application/json" \
  -d '{"status": "reviewed", "notes": "Reviewed manually."}'
```

Download an artifact listed in the status response:

```bash
curl -L "http://127.0.0.1:8000/inspection-runs/RUN_ID/artifacts/final_report:markdown_report" \
  -o school_safety_final_report.md
```

Generated API-run files are written under:

```text
backend/school_validation_outputs/api_runs/RUN_ID/
```

This API stores run status in memory. Restarting the server clears the in-memory run list, although files already written under `school_validation_outputs/api_runs/` remain on disk.
