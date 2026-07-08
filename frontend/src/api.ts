import type {
  ApiRunStatus,
  CreateRunResponse,
  HealthResponse,
  HumanReviewItem,
  RunStatusResponse,
  SectionName,
  UploadedImageResponse,
} from "./types";

export const sectionNames: SectionName[] = [
  "ceiling",
  "classroom",
  "corridor",
  "electrical",
  "exterior",
  "fire_extinguisher",
  "staircase",
  "washroom",
  "other",
];

export type CreateRunPayload = {
  school: {
    name: string;
    inspection_date: string;
    location: string;
  };
  sections: {
    section_name: SectionName;
    section_comment: string;
  }[];
};

export type StartRunPayload = {
  generate_report: boolean;
};

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
    }
  } catch {
    // Keep the generic status message.
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

export async function startRun(apiUrl: string, runId: string, payload: StartRunPayload): Promise<{ run_id: string; status: ApiRunStatus }> {
  const response = await fetch(`${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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
  status: "reviewed" | "deferred",
): Promise<void> {
  const response = await fetch(
    `${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/human-review/${encodeURIComponent(
      item.review_id,
    )}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, notes: status === "reviewed" ? "Reviewed in frontend." : "Deferred in frontend." }),
    },
  );
  await parseResponse(response);
}

export function artifactUrl(apiUrl: string, runId: string, artifactName: string): string {
  return `${normalizeApiUrl(apiUrl)}/inspection-runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(
    artifactName,
  )}`;
}
