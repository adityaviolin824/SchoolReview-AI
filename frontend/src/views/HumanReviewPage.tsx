import { useEffect, useMemo, useState } from "react";
import { humanReviewImageUrl } from "../api";
import { formatSectionName } from "../constants";
import { StatusBadge } from "../components/StatusBadge";
import type { InspectionRunController } from "../hooks/useInspectionRun";
import type { AppRoute } from "../routing";

type HumanReviewPageProps = {
  controller: InspectionRunController;
  onNavigate: (route: AppRoute) => void;
};

export function HumanReviewPage({ controller, onNavigate }: HumanReviewPageProps) {
  const items = controller.runStatus?.human_review_items ?? [];
  const [selectedReviewId, setSelectedReviewId] = useState("");
  const selectedItem = useMemo(
    () => items.find((item) => item.review_id === selectedReviewId) ?? items[0] ?? null,
    [items, selectedReviewId],
  );
  const reviewComplete = Boolean(items.length && controller.allReviewItemsReviewed);
  const selectedItemIsSaving = Boolean(selectedItem && controller.savingReviewId === selectedItem.review_id);

  useEffect(() => {
    if (!selectedReviewId && items[0]) {
      setSelectedReviewId(items[0].review_id);
    }
  }, [items, selectedReviewId]);

  if (!controller.runStatus) {
    return (
      <section className="surface empty-state">
        <h2>No inspection loaded</h2>
        <p>Create a new inspection before reviewing flagged evidence.</p>
      </section>
    );
  }

  if (!items.length) {
    return (
      <section className="surface empty-state">
        <h2>No human review queue</h2>
        <p>
          {controller.reportReady || controller.reportGenerating || controller.completedWithArtifacts
            ? "No human review is pending. Continue to Reports."
            : "Flagged evidence will appear here after assessment if the model requests manual review."}
        </p>
        {controller.reportReady || controller.reportGenerating || controller.completedWithArtifacts ? (
          <button type="button" className="primary-action compact-action" onClick={() => onNavigate("reports")}>
            Go to Reports
          </button>
        ) : null}
        <StatusBadge value={controller.runStatus.status} />
      </section>
    );
  }

  return (
    <div className="review-layout">
      <section className="surface review-list-panel">
        <div className="section-heading">
          <div>
            <h2>Review queue</h2>
            <p>
              {reviewComplete
                ? "Final review complete. Continue to Reports."
                : `${controller.pendingReviewCount} flagged item${
                    controller.pendingReviewCount === 1 ? "" : "s"
                  } need a human decision before reporting can proceed.`}
            </p>
          </div>
        </div>
        {reviewComplete ? (
          <div className="completion-callout">
            <strong>Final review complete.</strong>
            <p>Report generation is available on the Reports page.</p>
            <button type="button" className="primary-action compact-action" onClick={() => onNavigate("reports")}>
              Continue to Reports
            </button>
          </div>
        ) : null}
        <div className="review-list">
          {items.map((item) => (
            <button
              key={item.review_id}
              type="button"
              className={item.review_id === selectedItem?.review_id ? "review-list-item review-list-item-active" : "review-list-item"}
              onClick={() => setSelectedReviewId(item.review_id)}
            >
              <span>{formatSectionName(item.category_name)}</span>
              <small>{item.image_id}</small>
              <StatusBadge value={item.status} />
            </button>
          ))}
        </div>
      </section>

      {selectedItem && (
        <section className="surface evidence-panel">
          <div className="section-heading">
            <div>
              <h2>{formatSectionName(selectedItem.category_name)}</h2>
              <p>{selectedItem.reason || "Manual review requested."}</p>
            </div>
            <StatusBadge value={selectedItem.status} />
          </div>

          <div className="evidence-grid">
            <div className="evidence-image">
              {selectedItem.image_available ? (
                <img
                  src={humanReviewImageUrl(controller.normalizedApiUrl, controller.runStatus.run_id, selectedItem.review_id)}
                  alt={`${formatSectionName(selectedItem.category_name)} review evidence`}
                />
              ) : (
                <p>Image preview is not available for this review item.</p>
              )}
            </div>

            <div className="model-card">
              <span>Model inference</span>
              <p>
                <strong>Risk:</strong> {selectedItem.model_summary.risk_severity || "Not specified"}
                {selectedItem.model_summary.risk_reason ? ` - ${selectedItem.model_summary.risk_reason}` : ""}
              </p>
              <p>
                <strong>Recommended action:</strong>{" "}
                {selectedItem.model_summary.recommended_action || "No recommended action provided."}
              </p>
              <p>
                <strong>Officer comment:</strong> {selectedItem.model_summary.officer_comment_status || "Not assessed"}
                {selectedItem.model_summary.officer_comment_reason
                  ? ` - ${selectedItem.model_summary.officer_comment_reason}`
                  : ""}
              </p>

              <div className="mini-section">
                <strong>Visible findings</strong>
                {selectedItem.model_summary.visible_findings.length ? (
                  selectedItem.model_summary.visible_findings.map((finding, index) => (
                    <p key={`${selectedItem.review_id}-finding-${index}`}>
                      {finding.severity || "unknown"}: {finding.evidence || finding.issue_type || "Finding returned."}
                    </p>
                  ))
                ) : (
                  <p>No visible findings returned for display.</p>
                )}
              </div>

              <div className="mini-section">
                <strong>Uncertainties</strong>
                {selectedItem.model_summary.uncertainties.length ? (
                  selectedItem.model_summary.uncertainties.map((uncertainty) => (
                    <p key={`${selectedItem.review_id}-${uncertainty}`}>{uncertainty}</p>
                  ))
                ) : (
                  <p>None recorded.</p>
                )}
              </div>
            </div>
          </div>

          <label className="review-note">
            Human review comment
            <textarea
              value={controller.reviewNotes[selectedItem.review_id] ?? selectedItem.reviewer_notes}
              onChange={(event) =>
                controller.setReviewNotes((current) => ({
                  ...current,
                  [selectedItem.review_id]: event.target.value,
                }))
              }
              placeholder="Record what a reviewer confirmed, corrected, or deferred."
              disabled={controller.busy}
            />
          </label>

          <div className="review-actions">
            <button
              type="button"
              className="primary-action compact-action"
              onClick={() => controller.saveReviewDecision(selectedItem, "reviewed")}
              disabled={controller.busy}
            >
              {selectedItemIsSaving ? "Saving..." : "Mark Reviewed"}
            </button>
            <button type="button" onClick={() => controller.saveReviewDecision(selectedItem, "deferred")} disabled={controller.busy}>
              {selectedItemIsSaving ? "Saving..." : "Defer"}
            </button>
            <p>Deferred items stay visible and must be reviewed before report generation.</p>
          </div>
        </section>
      )}
    </div>
  );
}
