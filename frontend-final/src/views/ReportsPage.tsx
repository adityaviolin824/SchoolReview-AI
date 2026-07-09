import { artifactUrl } from "../api";
import { formatSectionName, readableStatus } from "../constants";
import { StatusBadge } from "../components/StatusBadge";
import type { InspectionRunController } from "../hooks/useInspectionRun";

type ReportsPageProps = {
  controller: InspectionRunController;
};

function reportReadinessMessage(controller: InspectionRunController): string {
  const status = controller.runStatus?.status;
  if (controller.assessmentRunning) {
    return "Assessment is still running. Report generation becomes available after assessment and required review.";
  }
  if (controller.reviewRequired) {
    return `Review ${controller.pendingReviewCount} flagged item${
      controller.pendingReviewCount === 1 ? "" : "s"
    } before generating the report.`;
  }
  if (controller.reportReady) {
    return "Review is complete. Generate the final report when ready.";
  }
  if (controller.reportGenerating) {
    return "Final review complete. Generating report. This page refreshes automatically.";
  }
  if (controller.completedWithArtifacts) {
    return "Report ready. Download files below.";
  }
  if (status === "completed") {
    return "Report generation finished, but no files are listed yet. Refresh the inspection status.";
  }
  if (status === "failed") {
    return "Assessment failed. Report generation is not available.";
  }
  return controller.runStatus?.progress?.message ?? "Status is available for the current inspection.";
}

export function ReportsPage({ controller }: ReportsPageProps) {
  const runStatus = controller.runStatus;
  const artifacts = runStatus?.artifacts ?? [];
  const readinessMessage = reportReadinessMessage(controller);
  const isGenerating = controller.reportGenerating || controller.isFinalizingReport;

  if (!runStatus) {
    return (
      <section className="surface empty-state">
        <h2>No inspection loaded</h2>
        <p>Create a new inspection before generating a report.</p>
      </section>
    );
  }

  return (
    <div className="page-grid reports-grid">
      <section className="surface report-cover">
        {controller.reportGenerating ? (
          <div className="report-generation-card">
            <div className="loading-spinner" aria-hidden="true" />
            <span>Report generation</span>
            <h2>Generating report</h2>
            <p>Final review is complete. Report files will appear here when generation finishes.</p>
            <div className="report-skeleton" aria-hidden="true">
              <i />
              <i />
              <i />
            </div>
          </div>
        ) : (
          <div className="report-paper">
            <span>Facility Condition Assessment Report</span>
            <h2>{readableStatus(runStatus.overall_status)}</h2>
            <p>Generated after model assessment and required human review decisions.</p>
            <div className="report-lines">
              <i />
              <i />
              <i />
            </div>
          </div>
        )}
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Report readiness</h2>
            <p>{readinessMessage}</p>
          </div>
          <StatusBadge value={runStatus.status} />
        </div>

        <div className="status-strip">
          <div>
            <span>Overall</span>
            <strong>{readableStatus(runStatus.overall_status)}</strong>
          </div>
          <div>
            <span>Provisional</span>
            <strong>{runStatus.provisional === null ? "Not available" : runStatus.provisional ? "Yes" : "No"}</strong>
          </div>
          <div>
            <span>Images</span>
            <strong>{runStatus.total_images}</strong>
          </div>
          <div>
            <span>Artifacts</span>
            <strong>{artifacts.length}</strong>
          </div>
        </div>

        {runStatus.status === "completed" ? (
          <p className="quiet-copy">Report files are listed below when available.</p>
        ) : (
          <>
            <button
              type="button"
              className="primary-action"
              onClick={controller.finalizeCurrentReport}
              disabled={!controller.canFinalizeReport || controller.busy || controller.reportGenerating}
            >
              {isGenerating ? "Generating report..." : "Generate Report"}
            </button>
            {!controller.canFinalizeReport ? <p className="quiet-copy">{readinessMessage}</p> : null}
          </>
        )}
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Downloads</h2>
            <p>Report files appear here after generation.</p>
          </div>
        </div>
        {controller.reportGenerating ? (
          <div className="report-loading-state">
            <div className="loading-spinner" aria-hidden="true" />
            <div>
              <h3>Final review complete. Generating report.</h3>
              <p>This page refreshes automatically while the report files are being prepared.</p>
            </div>
          </div>
        ) : artifacts.length ? (
          <div className="artifact-list">
            {artifacts.map((artifact) => (
              <a
                key={artifact}
                href={artifactUrl(controller.normalizedApiUrl, runStatus.run_id, artifact)}
                target="_blank"
                rel="noreferrer"
              >
                <span>{artifact.replace("final_report:", "")}</span>
                <strong>Download</strong>
              </a>
            ))}
          </div>
        ) : (
          <p className="quiet-copy">Report files will appear here after generation.</p>
        )}
      </section>

      <section className="surface wide-surface">
        <div className="section-heading">
          <div>
            <h2>Report inputs</h2>
            <p>Processed categories and report limitations remain visible before download.</p>
          </div>
        </div>
        <div className="overview-lists">
          <div className="list-line">
            <span>Processed</span>
            <strong>{runStatus.processed_sections.length ? runStatus.processed_sections.map(formatSectionName).join(", ") : "None"}</strong>
          </div>
          <div className="list-line">
            <span>Not inspected</span>
            <strong>{runStatus.not_inspected_sections.length ? runStatus.not_inspected_sections.map(formatSectionName).join(", ") : "None"}</strong>
          </div>
          <div className="list-line">
            <span>Failed</span>
            <strong>{runStatus.failed_sections.length ? runStatus.failed_sections.map(formatSectionName).join(", ") : "None"}</strong>
          </div>
          <div className="list-line">
            <span>Warnings</span>
            <strong>{runStatus.warnings.length ? runStatus.warnings.join(", ") : "None"}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}
