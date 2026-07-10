import { readableStatus } from "../constants";
import type { InspectionRunController } from "../hooks/useInspectionRun";
import type { AppRoute } from "../routing";

type RunStatusPanelProps = {
  controller: InspectionRunController;
  onNavigate: (route: AppRoute) => void;
};

function runMessage(controller: InspectionRunController): string {
  if (!controller.runId) {
    return "No inspection loaded.";
  }
  if (controller.assessmentRunning) {
    return "Assessment is running. Status refreshes automatically.";
  }
  if (controller.reportGenerating) {
    return "Report generation is running. Status refreshes automatically.";
  }
  if (controller.reviewRequired) {
    return "Human review is needed before report generation.";
  }
  if (controller.reportReady) {
    return "Review is complete. The report can be generated.";
  }
  if (controller.completedWithArtifacts) {
    return "Report files are ready.";
  }
  return controller.runStatus?.progress?.message ?? "Ready.";
}

function reviewMetric(controller: InspectionRunController): string {
  const reviewCount = controller.runStatus?.human_review_items.length ?? 0;
  if (controller.pendingReviewCount) {
    return `${controller.pendingReviewCount} pending`;
  }
  if (reviewCount) {
    return "Reviewed";
  }
  return "No flags";
}

function reportMetric(controller: InspectionRunController): string {
  const artifactCount = controller.runStatus?.artifacts.length ?? 0;
  if (controller.completedWithArtifacts) {
    return `${artifactCount} file${artifactCount === 1 ? "" : "s"} ready`;
  }
  if (controller.reportGenerating) {
    return "Generating";
  }
  if (controller.reportReady) {
    return "Ready";
  }
  return "Not ready";
}

export function RunStatusPanel({ controller, onNavigate }: RunStatusPanelProps) {
  const runStatus = controller.runStatus;
  const isLive =
    controller.assessmentRunning ||
    controller.reportGenerating ||
    controller.isCreatingInspection ||
    controller.isUploadingImages ||
    controller.isStartingAssessment ||
    controller.isFinalizingReport ||
    controller.isSavingReview;

  return (
    <section className={isLive ? "run-status-panel run-status-panel-live" : "run-status-panel"} aria-live="polite">
      <div className="run-status-main">
        {isLive ? <div className="loading-spinner run-status-spinner" aria-hidden="true" /> : <span className="run-status-dot" />}
        <div>
          <span>Current run</span>
          <strong>{runMessage(controller)}</strong>
          <p>{runStatus ? `Phase: ${readableStatus(runStatus.status)}` : "Create an inspection to begin."}</p>
        </div>
      </div>

      <div className="run-status-metrics">
        <div>
          <span>Images</span>
          <strong>{runStatus?.total_images ?? controller.totalUploadedImages}</strong>
        </div>
        <div>
          <span>Review</span>
          <strong>{reviewMetric(controller)}</strong>
        </div>
        <div>
          <span>Report</span>
          <strong>{reportMetric(controller)}</strong>
        </div>
      </div>

      <div className="run-status-actions">
        {controller.reviewRequired ? (
          <button type="button" className="attention-action compact-action" onClick={() => onNavigate("human-review")}>
            Open Review
          </button>
        ) : null}
        {controller.reportReady || controller.reportGenerating || controller.completedWithArtifacts ? (
          <button type="button" className="attention-action compact-action" onClick={() => onNavigate("reports")}>
            Open Reports
          </button>
        ) : null}
        {!controller.reviewRequired &&
        !controller.reportReady &&
        !controller.reportGenerating &&
        !controller.completedWithArtifacts ? (
          <button
            type="button"
            className="compact-action"
            onClick={() => (controller.runId ? controller.refreshStatus() : onNavigate("new-inspection"))}
            disabled={Boolean(controller.runId) && controller.busy}
          >
            {controller.runId ? "Refresh" : "New Inspection"}
          </button>
        ) : null}
      </div>
    </section>
  );
}
