import { SECTION_NAMES, formatSectionName } from "../constants";
import { StatusBadge } from "../components/StatusBadge";
import { WorkflowStepper } from "../components/WorkflowStepper";
import type { InspectionRunController } from "../hooks/useInspectionRun";
import type { SectionName } from "../types";

type NewInspectionPageProps = {
  controller: InspectionRunController;
};

function activeStep(controller: InspectionRunController): number {
  if (controller.runStatus?.status && controller.runStatus.status !== "created") {
    return 3;
  }
  if (controller.totalUploadedImages > 0) {
    return 2;
  }
  if (controller.runId) {
    return 1;
  }
  return 0;
}

export function NewInspectionPage({ controller }: NewInspectionPageProps) {
  const runStatus = controller.runStatus;
  const uploadSectionNames = controller.uploadSectionNames;

  return (
    <div className="page-grid setup-grid">
      <section className="surface setup-intro">
        <div className="section-heading">
          <div>
            <h2>New inspection</h2>
            <p>Add school details, choose categories, upload evidence, then start the model assessment.</p>
          </div>
          <StatusBadge value={runStatus?.status ?? null} />
        </div>
        <WorkflowStepper activeIndex={activeStep(controller)} />
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Inspection details</h2>
            <p>Basic context for the report and category assessments.</p>
          </div>
        </div>
        <div className="form-grid">
          <label>
            School name
            <input value={controller.schoolName} onChange={(event) => controller.setSchoolName(event.target.value)} />
          </label>
          <label>
            Inspection date
            <input
              type="date"
              value={controller.inspectionDate}
              onChange={(event) => controller.setInspectionDate(event.target.value)}
            />
          </label>
          <label className="span-all">
            Location
            <input value={controller.location} onChange={(event) => controller.setLocation(event.target.value)} />
          </label>
        </div>
      </section>

      <section className="surface">
        <div className="section-heading">
          <div>
            <h2>Categories</h2>
            <p>{controller.selectedSectionNames.length} selected for this inspection.</p>
          </div>
          {controller.runId ? (
            <button type="button" className="compact-action" onClick={controller.resetInspectionDraft} disabled={controller.busy}>
              Start New Draft
            </button>
          ) : (
            <button
              type="button"
              className="primary-action compact-action"
              onClick={controller.createInspectionRun}
              disabled={controller.busy || controller.selectedSectionNames.length === 0}
            >
              {controller.isCreatingInspection ? "Creating..." : "Create Inspection"}
            </button>
          )}
        </div>
        {controller.runId ? (
          <p className="quiet-copy">
            Category choices are locked for the loaded run. Start a new draft to change the selected categories.
          </p>
        ) : null}
        <div className="category-grid">
          {SECTION_NAMES.map((name) => {
            const form = controller.sectionForms[name];
            return (
              <article key={name} className={form.selected ? "category-tile category-tile-active" : "category-tile"}>
                <label className="check-line">
                  <input
                    type="checkbox"
                    checked={form.selected}
                    onChange={(event) => controller.updateSectionForm(name, { selected: event.target.checked })}
                    disabled={controller.busy || Boolean(controller.runId)}
                  />
                  <span>{formatSectionName(name)}</span>
                </label>
                {form.selected && (
                  <textarea
                    value={form.sectionComment}
                    onChange={(event) => controller.updateSectionForm(name, { sectionComment: event.target.value })}
                    disabled={controller.busy || Boolean(controller.runId)}
                    aria-label={`${formatSectionName(name)} section comment`}
                    placeholder="Enter category-level comments (optional)"
                  />
                )}
              </article>
            );
          })}
        </div>
      </section>

      <section className="surface wide-surface">
        <div className="section-heading">
          <div>
            <h2>Upload evidence</h2>
            <p>Each selected category needs at least one JPG or PNG image before assessment starts.</p>
          </div>
          <span className="metric-pill">{controller.totalUploadedImages} uploaded</span>
        </div>

        {uploadSectionNames.length ? (
          <div className="upload-list">
            {uploadSectionNames.map((name: SectionName) => {
              const form = controller.sectionForms[name];
              const sectionStatus = runStatus?.input_status.sections[name];
              const uploadedCount = sectionStatus?.image_count ?? form.uploadedImages.length;
              const uploadDisabled =
                !controller.canUpload || controller.busy || (controller.runSections.length > 0 && !controller.runSections.includes(name));
              return (
                <article key={name} className="upload-row">
                  <div>
                    <strong>{formatSectionName(name)}</strong>
                    <span>{uploadedCount} uploaded</span>
                  </div>
                  <label>
                    Image comment
                    <input
                      value={form.imageComment}
                      onChange={(event) => controller.updateSectionForm(name, { imageComment: event.target.value })}
                      disabled={uploadDisabled}
                      placeholder="Enter image-specific comments (optional)"
                    />
                  </label>
                  <label className="file-input">
                    <input
                      type="file"
                      accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                      multiple
                      onChange={(event) =>
                        controller.updateSectionForm(name, { selectedFiles: Array.from(event.target.files ?? []) })
                      }
                      disabled={uploadDisabled}
                    />
                    <span>{form.selectedFiles.length ? `${form.selectedFiles.length} selected` : "Choose files"}</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => controller.uploadSectionImages(name)}
                    disabled={uploadDisabled || form.selectedFiles.length === 0}
                  >
                    {controller.uploadingSectionName === name ? "Uploading..." : "Upload"}
                  </button>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="quiet-copy">Create an inspection before uploading evidence.</p>
        )}

        <div className="start-band">
          <div>
            <strong>Ready to assess?</strong>
            <p>
              {runStatus?.input_status.missing_image_sections.length
                ? `Missing images: ${runStatus.input_status.missing_image_sections.map(formatSectionName).join(", ")}.`
                : "Inputs are ready when every selected category has evidence."}
            </p>
          </div>
          <button type="button" className="primary-action" onClick={controller.startAssessment} disabled={!controller.canStart || controller.busy}>
            {controller.isStartingAssessment ? "Starting..." : "Start Assessment"}
          </button>
        </div>
      </section>
    </div>
  );
}
