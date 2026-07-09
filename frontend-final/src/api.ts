import type {
  ApiRunStatus,
  CreateRunPayload,
  CreateRunResponse,
  HealthResponse,
  HumanReviewItem,
  ReviewDecisionStatus,
  RunStatusResponse,
  SectionName,
  UploadedImageResponse,
} from "./types";

export function normalizeApiUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let detail = `Request failed with status ${response.status}.`;
  try {
    const errorPayload = (await response.json()) as { detail?: unknown };
    if (typeof errorPayload.detail === "string") {
      detail = errorPayload.detail;
    } else if (errorPayload.detail && typeof errorPayload.detail === "object") {
      const structuredDetail = errorPayload.detail as { message?: unknown; sections?: unknown };
      if (typeof structuredDetail.message === "string") {
        const sections = Array.isArray(structuredDetail.sections)
          ? ` Missing: ${structuredDetail.sections.join(", ")}.`
          : "";
        detail = `${structuredDetail.message}${sections}`;
      }
    }
  } catch {
    // Keep the generic status message when the backend does not return JSON.
  }
  throw new Error(detail);
}

export async function checkHealth(apiUrl: string): Promise<HealthResponse> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/health`);
  return parseResponse<HealthResponse>(response);
}

export async function createRun(apiUrl: string, payload: CreateRunPayload): Promise<CreateRunResponse> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/inspection-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<CreateRunResponse>(response);
}

export async function uploadImage(
  apiUrl: string,
  runId: string,
  sectionName: SectionName,
  file: File,
  comment: string,
): Promise<UploadedImageResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("comment", comment);

  const response = await fetch(
    `${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/sections/${encodeURIComponent(
      sectionName,
    )}/images`,
    {
      method: "POST",
      body: formData,
    },
  );
  return parseResponse<UploadedImageResponse>(response);
}

export async function startRun(apiUrl: string, runId: string): Promise<{ run_id: string; status: ApiRunStatus }> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ generate_report: false }),
  });
  return parseResponse<{ run_id: string; status: ApiRunStatus }>(response);
}

export async function finalizeReport(apiUrl: string, runId: string): Promise<{ run_id: string; status: ApiRunStatus }> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/finalize-report`, {
    method: "POST",
  });
  return parseResponse<{ run_id: string; status: ApiRunStatus }>(response);
}

export async function getRunStatus(apiUrl: string, runId: string): Promise<RunStatusResponse> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}`);
  return parseResponse<RunStatusResponse>(response);
}

export async function recordHumanReviewDecision(
  apiUrl: string,
  runId: string,
  item: HumanReviewItem,
  status: ReviewDecisionStatus,
  notes: string,
): Promise<void> {
  const response = await fetch(
    `${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/human-review/${encodeURIComponent(
      item.review_id,
    )}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, notes }),
    },
  );
  await parseResponse(response);
}

export function humanReviewImageUrl(apiUrl: string, runId: string, reviewId: string): string {
  return `${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/human-review/${encodeURIComponent(
    reviewId,
  )}/image`;
}

export function artifactUrl(apiUrl: string, runId: string, artifactName: string): string {
  return `${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(
    artifactName,
  )}`;
}
