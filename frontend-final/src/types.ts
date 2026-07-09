export type ApiRunStatus =
  | "created"
  | "running"
  | "awaiting_human_review"
  | "ready_for_report"
  | "finalizing_report"
  | "completed"
  | "completed_with_human_review_required"
  | "failed";

export type PipelineStatus = "completed" | "completed_with_human_review_required" | "failed";

export type OverallInspectionStatus =
  | "acceptable_with_minor_issues"
  | "maintenance_attention_required"
  | "urgent_review_required"
  | "insufficient_evidence";

export type SectionName =
  | "ceiling"
  | "classroom"
  | "corridor"
  | "electrical"
  | "exterior"
  | "fire_extinguisher"
  | "staircase"
  | "washroom"
  | "other";

export type ReviewItemStatus = "pending" | "reviewed" | "deferred";
export type ReviewDecisionStatus = "reviewed" | "deferred";

export type SchoolPayload = {
  name: string;
  inspection_date: string;
  location: string;
};

export type CreateRunPayload = {
  school: SchoolPayload;
  sections: {
    section_name: SectionName;
    section_comment: string;
  }[];
};

export type CreateRunResponse = {
  run_id: string;
  status: ApiRunStatus;
  sections: string[];
};

export type UploadedImageResponse = {
  run_id: string;
  section_name: string;
  image_id: string;
  original_filename: string;
};

export type HumanReviewFindingSummary = {
  issue_type: string;
  visibility: string;
  severity: string;
  evidence: string;
  confidence: number | null;
};

export type HumanReviewModelSummary = {
  risk_severity: string;
  risk_reason: string;
  recommended_action: string;
  officer_comment_status: string;
  officer_comment_reason: string;
  uncertainties: string[];
  visible_findings: HumanReviewFindingSummary[];
};

export type HumanReviewItem = {
  review_id: string;
  category_name: string;
  image_id: string;
  reason: string;
  status: ReviewItemStatus;
  image_available: boolean;
  model_summary: HumanReviewModelSummary;
  reviewer_notes: string;
};

export type CategorySummary = {
  category_status: string | null;
  image_count: number;
  human_review_required: boolean;
  human_review_item_count: number;
};

export type InputSectionStatus = {
  selected: boolean;
  image_count: number;
  ready: boolean;
};

export type InputStatus = {
  can_start: boolean;
  missing_image_sections: string[];
  sections: Record<string, InputSectionStatus>;
};

export type RunProgress = {
  phase: ApiRunStatus;
  message: string;
};

export type RunStatusResponse = {
  run_id: string;
  status: ApiRunStatus;
  input_status: InputStatus;
  progress: RunProgress | null;
  pipeline_status: PipelineStatus | null;
  overall_status: OverallInspectionStatus | null;
  provisional: boolean | null;
  processed_sections: string[];
  failed_sections: string[];
  not_inspected_sections: string[];
  total_images: number;
  human_review_required: boolean;
  human_review_items: HumanReviewItem[];
  category_summaries: Record<string, CategorySummary>;
  artifacts: string[];
  warnings: string[];
  errors: string[];
};

export type HealthResponse = {
  status: "ok";
};
