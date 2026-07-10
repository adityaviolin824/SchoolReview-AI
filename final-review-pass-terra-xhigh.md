# Final Review Pass: Terra XHigh

Date: 2026-07-10

## Scope And Outcome

Reviewed the active product path end to end:

- Backend modules in `backend/school_safety_validator/`, including image workflow, deterministic rules, aggregation, report generation, storage, and runtime settings.
- FastAPI models, routes, CORS, background workflow, artifact access, and API/Frontend contract.
- The shipped React client in `frontend-final/`.
- Dockerfile, `.dockerignore`, built container, and same-origin static frontend serving.
- The unreferenced `frontend-testing/` client, because it is another runnable frontend in the repository.

The reference notebook and ignored generated run artifacts were not treated as the deployable application: neither is imported by the active Docker image or described as the active product path in `README.md`.

Result: the local MVP is coherent and its tested flow works. There is one material privacy/configuration issue to resolve before real inspection images are used. The remaining points are deliberately small and should not trigger an unnecessary rewrite.

## Implementation Status

- Completed: LangSmith tracing is now opt-in through `LANGSMITH_TRACING=true`, with regression coverage for the disabled default and explicit enabled state.
- Completed: the deprecated `generate_report` start option now defaults to `false` and describes the separate finalization route in OpenAPI.
- Completed: the inactive `frontend-testing/` client was removed; `frontend-final/` is the only frontend in the repository and Docker image.
- Completed: Ruff is a backend development dependency, and the frontend has a `npm run check` type-check command.

The verification results below were rerun after these changes.

## Required Finding

### P1: LangSmith tracing is forced on despite being documented as optional

Evidence:

- `pipeline.py:277`, `single_category_inspection_runner.py:238`, and `all_categories_inspection_runner.py:151` each call `tracing_context(enabled=True, ...)`.
- The installed LangSmith implementation treats a non-`None` `enabled` argument as an explicit override. It therefore does not defer to `LANGSMITH_TRACING`.
- `README.md` and `backend/README.md` describe LangSmith tracing configuration as optional.

Impact: tracing cannot be disabled through the documented environment switch. This conflicts with the project’s privacy-sensitive inspection workflow. The precise trace payload depends on the installed wrapper configuration, so this review does not claim which fields are exported; the forced enablement itself is proven.

Minimal fix:

1. Create one settings-derived tracing flag that follows `LANGSMITH_TRACING`.
2. Pass that flag to every tracing context, or omit `enabled` so the library uses its environment setting.
3. Add one focused test proving `LANGSMITH_TRACING=false` produces a disabled tracing context.

Do this before demonstrating the application with real school images or credentials. No model calls were made during this review.

## Portfolio Cleanup

### P2: A second, unreferenced frontend should be removed or clearly archived

`frontend-testing/` is a separate runnable React application. It builds successfully, but:

- `README.md` documents only `frontend-final/`.
- `Dockerfile` builds and serves only `frontend-final/`.
- `.dockerignore` excludes `frontend-testing/` from the image.
- Both frontends use the same default Vite development port, `5173`.

Impact: it is not a production defect, but two divergent frontends make a portfolio repository look unfinished and raise the question of which UI is authoritative.

Minimal fix: after confirming no external workflow depends on it, delete `frontend-testing/` or move it outside the repository with a short archive note. Do not merge the two clients or add a compatibility layer.

## Small Improvements Worth Scheduling

### P3: Align the `/start` request schema with actual behavior

`StartInspectionRunRequest.generate_report` defaults to `true`, but `start_inspection_run` intentionally runs assessment only and never reads that field. The backend README documents this compatibility behavior, so the current frontend is correct.

Change the default to `false` and describe the field as deprecated in OpenAPI, then remove it only in a deliberate API-version change. This avoids misleading non-frontend API consumers without changing the workflow.

### P3: Add only lightweight automated quality checks

The backend tests and TypeScript build are healthy, but no linter is installed or configured:

- `ruff` is not present in the backend environment.
- `eslint` is not a frontend dependency or configuration; attempting to invoke it required an unavailable registry lookup.

Keep this small: add Ruff as a backend development dependency and a single documented `npm run check` command when frontend work resumes. Do not add a broad formatting/linting migration now.

There are no frontend test files. The current manual browser smoke test exercised the real create-run flow, while backend API tests cover the status and review gates with fakes. A full browser test suite is not required for this MVP. The next UI state change should add one narrow regression test for the relevant state rather than a large test framework rollout.

## Accepted MVP Boundaries

These are already documented and should remain simple for the portfolio version:

- Run records are in memory, so a backend restart loses active run state.
- Generated artifacts are stored on the local filesystem.
- A single process-wide lock serializes model/report jobs.
- The API has no authentication because it is documented as a local-testing MVP.

Do not add a database, queue, or application-level authentication solely for the portfolio. If the Docker image is ever exposed outside a trusted local environment, make access control and persisted run metadata a deployment prerequisite before publishing it.

## What Was Verified

| Area | Evidence | Result |
| --- | --- | --- |
| Backend tests | `uv run --no-sync pytest -q -p no:cacheprovider` | 57 passed; two third-party deprecation warnings only. |
| Active frontend | `npm run build` in `frontend-final/` | Passed TypeScript checks and Vite production build. |
| Legacy frontend | `npm run build` in `frontend-testing/` | Passed; it is not part of the shipped path. |
| Frontend dependency audit | `npm audit --omit=dev --audit-level=high --package-lock-only --offline` | No production high-severity vulnerabilities reported. |
| API health and CORS | Live FastAPI server | `/health` returned 200; Vite origin received the expected CORS allow-origin response. |
| Browser flow | Vite at `127.0.0.1:5173` | Overview rendered, navigation to New Inspection worked, creating a run succeeded, and no console warnings/errors appeared. |
| Docker build | `docker build --tag school-validator-final-review:local .` | Passed; `.dockerignore` reduced the build context to about 84 kB. |
| Packaged app | Container on local port 8001 | `/health`, `/openapi.json`, and the bundled React root all returned successfully; browser render had no console warnings/errors. |

The resulting image is approximately 413 MiB. Given the required Python, OpenCV, PDF, and native rendering dependencies, this is acceptable for the current local MVP. No image-size work is recommended now.

## Code Simplification Review

The recently changed frontend reset path is direct and readable. The report renderer is long but remains a cohesive deterministic rendering boundary; splitting it purely to reduce line count would add indirection without a current benefit. No code simplification change is justified in this pass.

## Final Recommendation

Fix the tracing configuration first. Then remove or explicitly archive `frontend-testing/` before sharing the repository. Keep the present backend/API/frontend/Docker structure otherwise; it is appropriately small for a professional portfolio MVP.
