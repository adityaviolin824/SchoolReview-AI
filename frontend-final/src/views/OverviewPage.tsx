import { formatSectionName, readableStatus } from "../constants";
import { StatusBadge } from "../components/StatusBadge";
import type { InspectionRunController } from "../hooks/useInspectionRun";
import type { AppRoute } from "../routing";

type OverviewPageProps = {
  controller: InspectionRunController;
  onNavigate: (route: AppRoute) => void;
};

function ListLine({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="list-line">
      <span>{label}</span>
      <strong>{values.length ? values.map(formatSectionName).join(", ") : "None"}</strong>
    </div>
  );
}

export function OverviewPage({ controller, onNavigate }: OverviewPageProps) {
  const { runStatus } = controller;
  const categoryEntries = Object.entries(runStatus?.category_summaries ?? {}).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  const humanReviewCount = runStatus?.human_review_items.length ?? 0;
  const readyMessage = runStatus?.progress?.message ?? "Start a new inspection to begin.";

  return (
    <div className="page-grid overview-grid">
      <section className="hero-panel">
        <div>
          <h2>School condition review.</h2>
          <p>Upload inspection evidence, run the model assessment, review flagged items, and generate the report.</p>
        </div>
        <div className="hero-actions">
          <button type="button" className="primary-action" onClick={() => onNavigate("new-inspection")}>
            New Inspection
          </button>
          <button type="button" onClick={controller.refreshStatus} disabled={!controller.runId || controller.busy}>
            Refresh Inspection
          </button>
        </div>
      </section>

      <section className="surface current-run-panel">
        <div className="section-heading">
          <div>
            <h2>Current inspection</h2>
            <p>Status and next steps for the inspection created in this browser session.</p>
          </div>
          <StatusBadge value={runStatus?.status ?? null} />
        </div>

        <div className="status-strip">
          <div>
            <span>Phase</span>
            <strong>{readyMessage}</strong>
          </div>
          <div>
            <span>Total images</span>
            <strong>{runStatus?.total_images ?? controller.totalUploadedImages}</strong>
          </div>
          <div>
            <span>Human review</span>
            <strong>{humanReviewCount ? `${humanReviewCount} item(s)` : "No flagged items"}</strong>
          </div>
          <div>
            <span>Overall</span>
            <strong>{readableStatus(runStatus?.overall_status)}</strong>
          </div>
        </div>

        {runStatus ? (
          <div className="overview-lists">
            <ListLine label="Processed" values={runStatus.processed_sections} />
            <ListLine label="Missing images" values={runStatus.input_status.missing_image_sections} />
            <ListLine label="Not inspected" values={runStatus.not_inspected_sections} />
            <ListLine label="Failed" values={runStatus.failed_sections} />
          </div>
        ) : (
          <p className="quiet-copy">No inspection has been created in this browser session.</p>
        )}
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Next action</h2>
            <p>Continue when the current step is complete.</p>
          </div>
        </div>
        <div className="action-rail">
          <button type="button" onClick={() => onNavigate("new-inspection")}>
            Setup and uploads
          </button>
          <button type="button" onClick={() => onNavigate("human-review")} disabled={!runStatus}>
            Review evidence
          </button>
          <button type="button" onClick={() => onNavigate("reports")} disabled={!runStatus}>
            Reports
          </button>
        </div>
      </section>

      <section className="surface wide-surface">
        <div className="section-heading">
          <div>
            <h2>Category summary</h2>
            <p>Status by inspection area.</p>
          </div>
        </div>
        {categoryEntries.length ? (
          <div className="summary-table">
            <div className="summary-row summary-row-head">
              <span>Category</span>
              <span>Status</span>
              <span>Images</span>
              <span>Review</span>
            </div>
            {categoryEntries.map(([name, summary]) => (
              <div key={name} className="summary-row">
                <strong>{formatSectionName(name)}</strong>
                <StatusBadge value={summary.category_status} />
                <span>{summary.image_count}</span>
                <span>{summary.human_review_required ? `${summary.human_review_item_count} item(s)` : "Clear"}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="quiet-copy">Category results appear after the assessment finishes.</p>
        )}
      </section>
    </div>
  );
}
