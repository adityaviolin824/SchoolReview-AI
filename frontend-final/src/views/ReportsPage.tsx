import { artifactUrl } from "../api";
import { formatSectionName, readableStatus } from "../constants";
import { StatusBadge } from "../components/StatusBadge";
import type { InspectionRunController } from "../hooks/useInspectionRun";

type ReportsPageProps = {
  controller: InspectionRunController;
};

export function ReportsPage({ controller }: ReportsPageProps) {
  const runStatus = controller.runStatus;
  const artifacts = runStatus?.artifacts ?? [];

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
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Report readiness</h2>
            <p>{runStatus.progress?.message ?? "Status is available for the current inspection."}</p>
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

        <button
          type="button"
          className="primary-action"
          onClick={controller.finalizeCurrentReport}
          disabled={!controller.canFinalizeReport || controller.busy}
        >
          Generate Report
        </button>
        {!controller.canFinalizeReport && (
          <p className="quiet-copy">
            Reports can be generated only after assessment completes and every human-review item is marked reviewed.
          </p>
        )}
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Downloads</h2>
            <p>Report files appear here after generation.</p>
          </div>
        </div>
        {artifacts.length ? (
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
          <p className="quiet-copy">No report artifacts are available yet.</p>
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
