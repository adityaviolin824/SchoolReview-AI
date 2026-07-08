import { useCallback, useEffect, useMemo, useState } from "react";
import {
  artifactUrl,
  checkHealth,
  createRun,
  getRunStatus,
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

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
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

function ListBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="list-block">
      <span>{title}</span>
      {items.length ? <p>{items.join(", ")}</p> : <p className="muted">None</p>}
    </div>
  );
}

export default function App() {
  const [apiUrl, setApiUrl] = useState(() => localStorage.getItem(API_URL_STORAGE_KEY) || DEFAULT_API_URL);
  const [backendState, setBackendState] = useState<BackendState>("unknown");
  const [message, setMessage] = useState("Ready.");
  const [error, setError] = useState("");

  const [schoolName, setSchoolName] = useState("Example Government School");
  const [inspectionDate, setInspectionDate] = useState(todayIsoDate());
  const [location, setLocation] = useState("Example District");
  const [sectionName, setSectionName] = useState<SectionName>("classroom");
  const [sectionComment, setSectionComment] = useState("Classroom inspection comments.");

  const [runId, setRunId] = useState(() => localStorage.getItem(LAST_RUN_ID_STORAGE_KEY) || "");
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [imageComment, setImageComment] = useState("Visible condition image.");
  const [uploadedImages, setUploadedImages] = useState<UploadedImageResponse[]>([]);
  const [generateReport, setGenerateReport] = useState(true);
  const [busy, setBusy] = useState(false);

  const normalizedApiUrl = useMemo(() => normalizeApiUrl(apiUrl), [apiUrl]);
  const currentStatus = runStatus?.status;
  const canUpload = Boolean(runId) && (!currentStatus || currentStatus === "created");
  const canStart = Boolean(runId) && (!currentStatus || currentStatus === "created");

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

  const handleCreateRun = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await createRun(normalizedApiUrl, {
        school: {
          name: schoolName,
          inspection_date: inspectionDate,
          location,
        },
        sections: [
          {
            section_name: sectionName,
            section_comment: sectionComment,
          },
        ],
      });
      setRunId(response.run_id);
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
      setUploadedImages([]);
      setMessage("Run created. Upload images next.");
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = async () => {
    if (!selectedFiles.length) {
      setError("Choose at least one image.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const uploaded: UploadedImageResponse[] = [];
      for (const file of selectedFiles) {
        uploaded.push(await uploadImage(normalizedApiUrl, runId, sectionName, file, imageComment));
      }
      setUploadedImages((current) => [...current, ...uploaded]);
      setSelectedFiles([]);
      setMessage(`Uploaded ${uploaded.length} image${uploaded.length === 1 ? "" : "s"}.`);
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
      await recordHumanReviewDecision(normalizedApiUrl, runId, item, status);
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
              <label>
                Location
                <input value={location} onChange={(event) => setLocation(event.target.value)} />
              </label>
              <label>
                Section
                <select value={sectionName} onChange={(event) => setSectionName(event.target.value as SectionName)}>
                  {sectionNames.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="span-all">
                Section comment
                <textarea value={sectionComment} onChange={(event) => setSectionComment(event.target.value)} />
              </label>
            </div>
            <button type="button" className="primary-action" onClick={handleCreateRun} disabled={busy}>
              Create run
            </button>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span>2</span>
              <h2>Upload images</h2>
            </div>
            <label>
              Image comment
              <input value={imageComment} onChange={(event) => setImageComment(event.target.value)} />
            </label>
            <label className="file-picker">
              <input
                type="file"
                accept=".jpg,.jpeg,.png,image/jpeg,image/png"
                multiple
                onChange={(event) => setSelectedFiles(Array.from(event.target.files ?? []))}
                disabled={!canUpload || busy}
              />
              <span>{selectedFiles.length ? `${selectedFiles.length} selected` : "Choose JPG or PNG images"}</span>
            </label>
            <button type="button" onClick={handleUpload} disabled={!canUpload || busy || selectedFiles.length === 0}>
              Upload selected files
            </button>
            <div className="compact-list">
              <strong>Uploaded</strong>
              {uploadedImages.length ? (
                uploadedImages.map((image) => <p key={image.image_id}>{image.original_filename}</p>)
              ) : (
                <p className="muted">No images uploaded yet.</p>
              )}
            </div>
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
                <input value={runId} onChange={(event) => setRunId(event.target.value.trim())} />
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
              <div className="status-grid">
                <div>
                  <span className="field-label">Run status</span>
                  <span className={statusClass(runStatus.status)}>{runStatus.status}</span>
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
                <ListBlock title="Processed" items={runStatus.processed_sections} />
                <ListBlock title="Failed" items={runStatus.failed_sections} />
                <ListBlock title="Not inspected" items={runStatus.not_inspected_sections} />
              </div>
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
            {runStatus?.human_review_required ? (
              <div className="review-list">
                {runStatus.human_review_items.map((item) => (
                  <article key={item.review_id} className="review-card">
                    <div>
                      <strong>{item.category_name}</strong>
                      <p>{item.image_id}</p>
                      <p>{item.reason}</p>
                      <span className="badge badge-warning">{item.status}</span>
                    </div>
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
