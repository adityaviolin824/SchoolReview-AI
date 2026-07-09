import { useCallback, useEffect, useMemo, useState } from "react";
import {
  artifactUrl,
  checkHealth,
  createRun,
  getRunStatus,
  humanReviewImageUrl,
  normalizeApiUrl,
  recordHumanReviewDecision,
  sectionNames,
  startRun,
  uploadImage,
} from "./api";
import type { ApiRunStatus, HumanReviewItem, RunStatusResponse, SectionName, UploadedImageResponse } from "./types";

const API_URL_STORAGE_KEY = "school-validator-api-url";
const LAST_RUN_ID_STORAGE_KEY = "school-validator-last-run-id";
const DEFAULT_API_URL = "http://127.0.0.1:8000";

type BackendState = "unknown" | "online" | "offline";

type SectionFormState = {
  selected: boolean;
  sectionComment: string;
  imageComment: string;
  selectedFiles: File[];
  uploadedImages: UploadedImageResponse[];
};

type SectionFormStateMap = Record<SectionName, SectionFormState>;

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatSectionName(value: string): string {
  return value.replace(/_/g, " ");
}

function createInitialSectionForms(): SectionFormStateMap {
  const forms = {} as SectionFormStateMap;
  for (const name of sectionNames) {
    forms[name] = {
      selected: name === "classroom",
      sectionComment: `${formatSectionName(name)} inspection comments.`,
      imageComment: "Visible condition image.",
      selectedFiles: [],
      uploadedImages: [],
    };
  }
  return forms;
}

function clearSectionRuntimeState(current: SectionFormStateMap): SectionFormStateMap {
  const forms = {} as SectionFormStateMap;
  for (const name of sectionNames) {
    forms[name] = {
      ...current[name],
      selectedFiles: [],
      uploadedImages: [],
    };
  }
  return forms;
}

function knownSectionNames(values: string[]): SectionName[] {
  return values.filter((value): value is SectionName => sectionNames.includes(value as SectionName));
}

function statusClass(status: string | null | undefined): string {
  if (!status) {
    return "badge";
  }
  if (status === "completed") {
    return "badge badge-success";
  }
  if (status === "running" || status === "created") {
    return "badge badge-info";
  }
  if (status === "completed_with_human_review_required") {
    return "badge badge-warning";
  }
  if (status === "failed") {
    return "badge badge-danger";
  }
  return "badge";
}

function pipelinePhase(runStatus: RunStatusResponse | null): string {
  if (!runStatus) {
    return "No run loaded";
  }
  if (runStatus.status === "created") {
    return "Created, waiting for uploads or start";
  }
  if (runStatus.status === "running") {
    return "Pipeline is running";
  }
  if (runStatus.status === "completed_with_human_review_required") {
    return "Completed, human review required";
  }
  if (runStatus.status === "completed") {
    return "Completed";
  }
  if (runStatus.status === "failed") {
    return "Failed";
  }
  return runStatus.status;
}

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="list-block">
      <span>{title}</span>
      {items.length ? <p>{items.join(", ")}</p> : <p className="muted">None</p>}
    </div>
  );
}

function reviewStatusClass(status: string): string {
  if (status === "reviewed") {
    return "badge badge-success";
  }
  if (status === "deferred") {
    return "badge badge-info";
  }
  return "badge badge-warning";
}

export default function App() {
  const [apiUrl, setApiUrl] = useState(() => localStorage.getItem(API_URL_STORAGE_KEY) || DEFAULT_API_URL);
  const [backendState, setBackendState] = useState<BackendState>("unknown");
  const [message, setMessage] = useState("Ready.");
  const [error, setError] = useState("");

  const [schoolName, setSchoolName] = useState("Example Government School");
  const [inspectionDate, setInspectionDate] = useState(todayIsoDate());
  const [location, setLocation] = useState("Example District");
  const [sectionForms, setSectionForms] = useState<SectionFormStateMap>(createInitialSectionForms);

  const [runId, setRunId] = useState(() => localStorage.getItem(LAST_RUN_ID_STORAGE_KEY) || "");
  const [runSections, setRunSections] = useState<SectionName[]>([]);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [generateReport, setGenerateReport] = useState(true);
  const [busy, setBusy] = useState(false);

  const normalizedApiUrl = useMemo(() => normalizeApiUrl(apiUrl), [apiUrl]);
  const selectedSectionNames = useMemo(
    () => sectionNames.filter((name) => sectionForms[name].selected),
    [sectionForms],
  );
  const uploadSectionNames = runSections.length ? runSections : selectedSectionNames;
  const categorySummaryEntries = useMemo(
    () => Object.entries(runStatus?.category_summaries ?? {}).sort(([left], [right]) => left.localeCompare(right)),
    [runStatus?.category_summaries],
  );
  const currentStatus = runStatus?.status;
  const canUpload = Boolean(runId) && (!currentStatus || currentStatus === "created");
  const canStart = Boolean(runId) && (!currentStatus || currentStatus === "created");
  const totalUploadedImages = sectionNames.reduce(
    (total, name) => total + sectionForms[name].uploadedImages.length,
    0,
  );

  useEffect(() => {
    localStorage.setItem(API_URL_STORAGE_KEY, apiUrl);
  }, [apiUrl]);

  useEffect(() => {
    if (runId) {
      localStorage.setItem(LAST_RUN_ID_STORAGE_KEY, runId);
    }
  }, [runId]);

  const showError = (value: unknown) => {
    setError(value instanceof Error ? value.message : String(value));
  };

  const updateSectionForm = (sectionName: SectionName, updates: Partial<SectionFormState>) => {
    setSectionForms((current) => ({
      ...current,
      [sectionName]: {
        ...current[sectionName],
        ...updates,
      },
    }));
  };

  const handleRunIdChange = (value: string) => {
    setRunId(value.trim());
    setRunSections([]);
    setRunStatus(null);
    setReviewNotes({});
    setSectionForms(clearSectionRuntimeState);
  };

  const handleHealthCheck = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      await checkHealth(normalizedApiUrl);
      setBackendState("online");
      setMessage("Backend is online.");
    } catch (caughtError) {
      setBackendState("offline");
      showError(caughtError);
    } finally {
      setBusy(false);
    }
  }, [normalizedApiUrl]);

  const refreshStatus = useCallback(async () => {
    if (!runId) {
      setError("Create or paste a run id first.");
      return;
    }
    setError("");
    try {
      const status = await getRunStatus(normalizedApiUrl, runId);
      setRunStatus(status);
      setMessage(`Run status: ${status.status}`);
    } catch (caughtError) {
      showError(caughtError);
    }
  }, [normalizedApiUrl, runId]);

  useEffect(() => {
    if (runStatus?.status !== "running") {
      return undefined;
    }
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [refreshStatus, runStatus?.status]);

  useEffect(() => {
    if (!runStatus?.human_review_items.length) {
      return;
    }

    setReviewNotes((current) => {
      const next = { ...current };
      for (const item of runStatus.human_review_items) {
        if (next[item.review_id] === undefined) {
          next[item.review_id] = item.reviewer_notes;
        }
      }
      return next;
    });
  }, [runStatus?.human_review_items]);

  const handleCreateRun = async () => {
    if (!selectedSectionNames.length) {
      setError("Select at least one category.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const response = await createRun(normalizedApiUrl, {
        school: {
          name: schoolName,
          inspection_date: inspectionDate,
          location,
        },
        sections: selectedSectionNames.map((name) => ({
          section_name: name,
          section_comment: sectionForms[name].sectionComment,
        })),
      });
      const createdSections = knownSectionNames(response.sections);
      setRunId(response.run_id);
      setRunSections(createdSections);
      setReviewNotes({});
      setRunStatus({
        run_id: response.run_id,
        status: response.status,
        pipeline_status: null,
        overall_status: null,
        provisional: null,
        processed_sections: [],
        failed_sections: [],
        not_inspected_sections: [],
        total_images: 0,
        human_review_required: false,
        human_review_items: [],
        category_summaries: {},
        artifacts: [],
        warnings: [],
        errors: [],
      });
      setSectionForms((current) => {
        const cleared = clearSectionRuntimeState(current);
        const next = {} as SectionFormStateMap;
        for (const name of sectionNames) {
          next[name] = {
            ...cleared[name],
            selected: createdSections.includes(name),
          };
        }
        return next;
      });
      setMessage(`Run created for ${createdSections.map(formatSectionName).join(", ")}. Upload images next.`);
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = async (sectionName: SectionName) => {
    const sectionForm = sectionForms[sectionName];
    if (!sectionForm.selectedFiles.length) {
      setError(`Choose at least one image for ${formatSectionName(sectionName)}.`);
      return;
    }
    if (runSections.length && !runSections.includes(sectionName)) {
      setError(`${formatSectionName(sectionName)} is not part of this run.`);
      return;
    }

    setBusy(true);
    setError("");
    try {
      const uploaded = await Promise.all(
        sectionForm.selectedFiles.map((file) =>
          uploadImage(normalizedApiUrl, runId, sectionName, file, sectionForm.imageComment),
        ),
      );
      setSectionForms((current) => ({
        ...current,
        [sectionName]: {
          ...current[sectionName],
          selectedFiles: [],
          uploadedImages: [...current[sectionName].uploadedImages, ...uploaded],
        },
      }));
      setMessage(
        `Uploaded ${uploaded.length} image${uploaded.length === 1 ? "" : "s"} for ${formatSectionName(sectionName)}.`,
      );
      await refreshStatus();
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
    }
  };

  const handleStart = async () => {
    setBusy(true);
    setError("");
    try {
      await startRun(normalizedApiUrl, runId, {
        generate_report: generateReport,
      });
      setRunStatus((current) => (current ? { ...current, status: "running" } : current));
      setMessage("Pipeline started. Status will refresh every 3 seconds.");
      await refreshStatus();
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
    }
  };

  const handleReviewDecision = async (item: HumanReviewItem, status: "reviewed" | "deferred") => {
    setBusy(true);
    setError("");
    try {
      await recordHumanReviewDecision(normalizedApiUrl, runId, item, status, reviewNotes[item.review_id] ?? "");
      setMessage(`Review item ${status}.`);
      await refreshStatus();
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <h1>School Safety Validator</h1>
          <p>Local frontend for testing uploads, pipeline runs, human review, and reports.</p>
        </div>
        <div className="connection-bar">
          <label htmlFor="api-url">Backend API</label>
          <div className="inline-controls">
            <input id="api-url" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} />
            <button type="button" onClick={handleHealthCheck} disabled={busy}>
              Check
            </button>
          </div>
          <span className={`health health-${backendState}`}>{backendState}</span>
        </div>
      </header>

      {(message || error) && (
        <section className="notice-row">
          {message && <div className="notice">{message}</div>}
          {error && <div className="notice notice-error">{error}</div>}
        </section>
      )}

      <section className="workspace">
        <div className="column">
          <section className="panel">
            <div className="panel-heading">
              <span>1</span>
              <h2>Create run</h2>
            </div>
            <div className="form-grid">
              <label>
                School name
                <input value={schoolName} onChange={(event) => setSchoolName(event.target.value)} />
              </label>
              <label>
                Inspection date
                <input
                  type="date"
                  value={inspectionDate}
                  onChange={(event) => setInspectionDate(event.target.value)}
                />
              </label>
              <label className="span-all">
                Location
                <input value={location} onChange={(event) => setLocation(event.target.value)} />
              </label>
            </div>

            <div className="category-toolbar">
              <strong>Categories</strong>
              <span>{selectedSectionNames.length} selected</span>
            </div>
            <div className="category-select-grid">
              {sectionNames.map((name) => {
                const sectionForm = sectionForms[name];
                return (
                  <article key={name} className={`category-card ${sectionForm.selected ? "category-card-active" : ""}`}>
                    <label className="checkbox-line">
                      <input
                        type="checkbox"
                        checked={sectionForm.selected}
                        onChange={(event) => updateSectionForm(name, { selected: event.target.checked })}
                        disabled={busy}
                      />
                      <span>{formatSectionName(name)}</span>
                    </label>
                    <label>
                      Section comment
                      <textarea
                        value={sectionForm.sectionComment}
                        onChange={(event) => updateSectionForm(name, { sectionComment: event.target.value })}
                        disabled={!sectionForm.selected || busy}
                      />
                    </label>
                  </article>
                );
              })}
            </div>
            <button
              type="button"
              className="primary-action"
              onClick={handleCreateRun}
              disabled={busy || selectedSectionNames.length === 0}
            >
              Create run for selected categories
            </button>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span>2</span>
              <h2>Upload images</h2>
            </div>
            <div className="upload-summary">
              <span>Run sections: {uploadSectionNames.length ? uploadSectionNames.map(formatSectionName).join(", ") : "none"}</span>
              <span>Uploaded images: {totalUploadedImages}</span>
            </div>
            {uploadSectionNames.length ? (
              <div className="section-upload-list">
                {uploadSectionNames.map((name) => {
                  const sectionForm = sectionForms[name];
                  const uploadDisabled = !canUpload || busy || (runSections.length > 0 && !runSections.includes(name));
                  return (
                    <article key={name} className="upload-card">
                      <div className="upload-card-header">
                        <h3>{formatSectionName(name)}</h3>
                        <span className="badge">{sectionForm.uploadedImages.length} uploaded</span>
                      </div>
                      <label>
                        Image comment
                        <input
                          value={sectionForm.imageComment}
                          onChange={(event) => updateSectionForm(name, { imageComment: event.target.value })}
                          disabled={uploadDisabled}
                        />
                      </label>
                      <label className="file-picker">
                        <input
                          type="file"
                          accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                          multiple
                          onChange={(event) =>
                            updateSectionForm(name, { selectedFiles: Array.from(event.target.files ?? []) })
                          }
                          disabled={uploadDisabled}
                        />
                        <span>
                          {sectionForm.selectedFiles.length
                            ? `${sectionForm.selectedFiles.length} selected`
                            : "Choose JPG or PNG images"}
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => handleUpload(name)}
                        disabled={uploadDisabled || sectionForm.selectedFiles.length === 0}
                      >
                        Upload for {formatSectionName(name)}
                      </button>
                      <div className="compact-list">
                        <strong>Uploaded</strong>
                        {sectionForm.uploadedImages.length ? (
                          sectionForm.uploadedImages.map((image) => (
                            <p key={image.image_id}>{image.original_filename}</p>
                          ))
                        ) : (
                          <p className="muted">No images uploaded yet.</p>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p className="muted">Select categories and create a run before uploading images.</p>
            )}
          </section>
        </div>

        <div className="column">
          <section className="panel">
            <div className="panel-heading">
              <span>3</span>
              <h2>Start and monitor</h2>
            </div>
            <div className="run-id-row">
              <label>
                Run ID
                <input value={runId} onChange={(event) => handleRunIdChange(event.target.value)} />
              </label>
              <button type="button" onClick={refreshStatus} disabled={!runId || busy}>
                Refresh
              </button>
            </div>
            <div className="checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={generateReport}
                  onChange={(event) => setGenerateReport(event.target.checked)}
                />
                Generate report
              </label>
            </div>
            <button type="button" className="primary-action" onClick={handleStart} disabled={!canStart || busy}>
              Start pipeline
            </button>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span>4</span>
              <h2>Status</h2>
            </div>
            {runStatus ? (
              <>
                <div className="status-grid">
                  <div>
                    <span className="field-label">Run status</span>
                    <span className={statusClass(runStatus.status)}>{runStatus.status}</span>
                  </div>
                  <div>
                    <span className="field-label">Phase</span>
                    <p>{pipelinePhase(runStatus)}</p>
                  </div>
                  <div>
                    <span className="field-label">Overall</span>
                    <p>{runStatus.overall_status ?? "Not available yet"}</p>
                  </div>
                  <div>
                    <span className="field-label">Provisional</span>
                    <p>{runStatus.provisional === null ? "Not available yet" : runStatus.provisional ? "Yes" : "No"}</p>
                  </div>
                  <div>
                    <span className="field-label">Images</span>
                    <p>{runStatus.total_images}</p>
                  </div>
                  <div>
                    <span className="field-label">Human review</span>
                    <p>{runStatus.human_review_required ? "Required" : "Not required"}</p>
                  </div>
                  <ListBlock title="Processed" items={runStatus.processed_sections} />
                  <ListBlock title="Failed" items={runStatus.failed_sections} />
                  <ListBlock title="Not inspected" items={runStatus.not_inspected_sections} />
                </div>
                {!!categorySummaryEntries.length && (
                  <div className="category-summary-list">
                    <strong>Category summaries</strong>
                    {categorySummaryEntries.map(([name, summary]) => (
                      <div key={name} className="category-summary-row">
                        <span>{formatSectionName(name)}</span>
                        <span>{summary.category_status ?? "pending"}</span>
                        <span>{summary.image_count} image(s)</span>
                        <span>{summary.human_review_required ? "review required" : "no review"}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <p className="muted">Create a run or paste a run id, then refresh.</p>
            )}
            {!!runStatus?.warnings.length && (
              <div className="message-list">
                <strong>Warnings</strong>
                {runStatus.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            )}
            {!!runStatus?.errors.length && (
              <div className="message-list message-list-error">
                <strong>Errors</strong>
                {runStatus.errors.map((statusError) => (
                  <p key={statusError}>{statusError}</p>
                ))}
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span>5</span>
              <h2>Human review</h2>
            </div>
            {runStatus?.human_review_items.length ? (
              <div className="review-workspace">
                {runStatus.human_review_items.map((item) => (
                  <article key={item.review_id} className="review-detail-card">
                    <div className="review-detail-header">
                      <div>
                        <strong>{formatSectionName(item.category_name)}</strong>
                        <p>{item.image_id}</p>
                      </div>
                      <span className={reviewStatusClass(item.status)}>{item.status}</span>
                    </div>

                    <div className="review-detail-grid">
                      <div className="review-image-frame">
                        {item.image_available ? (
                          <img
                            src={humanReviewImageUrl(normalizedApiUrl, runStatus.run_id, item.review_id)}
                            alt={`${formatSectionName(item.category_name)} review`}
                          />
                        ) : (
                          <p className="muted">Image preview is not available for this review item.</p>
                        )}
                      </div>

                      <div className="model-summary">
                        <span className="field-label">Model inference</span>
                        <p>
                          <strong>Review reason:</strong> {item.reason || "No reason provided."}
                        </p>
                        <p>
                          <strong>Risk:</strong>{" "}
                          {item.model_summary.risk_severity || "Not specified"}
                          {item.model_summary.risk_reason ? ` - ${item.model_summary.risk_reason}` : ""}
                        </p>
                        <p>
                          <strong>Recommended action:</strong>{" "}
                          {item.model_summary.recommended_action || "No recommended action provided."}
                        </p>
                        <p>
                          <strong>Officer comment:</strong>{" "}
                          {item.model_summary.officer_comment_status || "Not assessed"}
                          {item.model_summary.officer_comment_reason
                            ? ` - ${item.model_summary.officer_comment_reason}`
                            : ""}
                        </p>

                        <div className="mini-list">
                          <strong>Visible findings</strong>
                          {item.model_summary.visible_findings.length ? (
                            item.model_summary.visible_findings.map((finding, index) => (
                              <p key={`${item.review_id}-finding-${index}`}>
                                {finding.severity || "unknown"} | {finding.issue_type || "finding"}:{" "}
                                {finding.evidence || "No evidence text provided."}
                              </p>
                            ))
                          ) : (
                            <p className="muted">No visible findings were returned for display.</p>
                          )}
                        </div>

                        <div className="mini-list">
                          <strong>Uncertainties</strong>
                          {item.model_summary.uncertainties.length ? (
                            item.model_summary.uncertainties.map((uncertainty) => (
                              <p key={`${item.review_id}-${uncertainty}`}>{uncertainty}</p>
                            ))
                          ) : (
                            <p className="muted">None recorded.</p>
                          )}
                        </div>
                      </div>
                    </div>

                    <label className="review-comment">
                      Human review comment
                      <textarea
                        value={reviewNotes[item.review_id] ?? item.reviewer_notes}
                        onChange={(event) =>
                          setReviewNotes((current) => ({
                            ...current,
                            [item.review_id]: event.target.value,
                          }))
                        }
                        placeholder="Write your review comment here before marking reviewed or deferred."
                        disabled={busy}
                      />
                    </label>

                    <div className="review-actions">
                      <button type="button" onClick={() => handleReviewDecision(item, "reviewed")} disabled={busy}>
                        Reviewed
                      </button>
                      <button type="button" onClick={() => handleReviewDecision(item, "deferred")} disabled={busy}>
                        Deferred
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : runStatus?.human_review_required ? (
              <p className="muted">Human review is required, but no individual review items were returned. Check failed sections and errors.</p>
            ) : (
              <p className="muted">No human-review items are currently flagged.</p>
            )}
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span>6</span>
              <h2>Artifacts</h2>
            </div>
            {runStatus?.artifacts.length ? (
              <div className="artifact-list">
                {runStatus.artifacts.map((artifact) => (
                  <a
                    key={artifact}
                    href={artifactUrl(normalizedApiUrl, runStatus.run_id, artifact)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {artifact}
                  </a>
                ))}
              </div>
            ) : (
              <p className="muted">Artifacts appear here after report generation completes.</p>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
