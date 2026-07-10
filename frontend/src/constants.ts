import type { ApiRunStatus, OverallInspectionStatus, SectionName } from "./types";

function defaultApiUrl(): string {
  const configuredUrl = import.meta.env.VITE_API_URL?.trim();
  if (configuredUrl) {
    return configuredUrl;
  }
  if (import.meta.env.DEV) {
    return "http://127.0.0.1:8000";
  }
  return window.location.origin;
}

export const DEFAULT_API_URL = defaultApiUrl();
export const LAST_RUN_ID_STORAGE_KEY = "school-validator-v2-last-run-id";
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const SUPPORTED_UPLOAD_EXTENSIONS = [".jpg", ".jpeg", ".png"];

export const SECTION_NAMES: SectionName[] = [
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

export const SECTION_LABELS: Record<SectionName, string> = {
  ceiling: "Ceiling",
  classroom: "Classroom",
  corridor: "Corridor",
  electrical: "Electrical",
  exterior: "Exterior",
  fire_extinguisher: "Fire Extinguisher",
  staircase: "Staircase",
  washroom: "Washroom",
  other: "Other",
};

export const STATUS_LABELS: Record<ApiRunStatus, string> = {
  created: "Created",
  running: "Assessment Running",
  awaiting_human_review: "Awaiting Review",
  ready_for_report: "Ready for Report",
  finalizing_report: "Generating Report",
  completed: "Completed",
  completed_with_human_review_required: "Completed with Review",
  failed: "Failed",
};

export const OVERALL_STATUS_LABELS: Record<OverallInspectionStatus, string> = {
  acceptable_with_minor_issues: "Acceptable with Minor Issues",
  maintenance_attention_required: "Maintenance Attention Required",
  urgent_review_required: "Urgent Review Required",
  insufficient_evidence: "Review Required",
};

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export function formatSectionName(value: string): string {
  return SECTION_LABELS[value as SectionName] ?? value.replace(/_/g, " ");
}

export function statusTone(status: string | null | undefined): Tone {
  if (!status) {
    return "neutral";
  }
  if (status === "completed" || status === "reviewed") {
    return "success";
  }
  if (status === "failed" || status === "urgent_review_required") {
    return "danger";
  }
  if (
    status === "awaiting_human_review" ||
    status === "completed_with_human_review_required" ||
    status === "insufficient_evidence" ||
    status === "deferred"
  ) {
    return "warning";
  }
  if (status === "running" || status === "created" || status === "ready_for_report" || status === "finalizing_report") {
    return "info";
  }
  return "neutral";
}

export function readableStatus(status: string | null | undefined): string {
  if (!status) {
    return "Not available";
  }
  return STATUS_LABELS[status as ApiRunStatus] ?? OVERALL_STATUS_LABELS[status as OverallInspectionStatus] ?? status;
}
