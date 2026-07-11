import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createRun,
  finalizeReport,
  getRunStatus,
  recordHumanReviewDecision,
  startRun,
  uploadImage,
} from "../api";
import {
  DEFAULT_API_URL,
  LAST_RUN_ID_STORAGE_KEY,
  MAX_UPLOAD_BYTES,
  SECTION_NAMES,
  SUPPORTED_UPLOAD_EXTENSIONS,
  formatSectionName,
} from "../constants";
import type {
  HumanReviewItem,
  InputStatus,
  ReviewDecisionStatus,
  RunStatusResponse,
  SectionName,
  UploadedImageResponse,
} from "../types";
import type { AppRoute } from "../routing";

export type SectionFormState = {
  selected: boolean;
  sectionComment: string;
  imageComment: string;
  selectedFiles: File[];
  uploadedImages: UploadedImageResponse[];
};

export type SectionFormStateMap = Record<SectionName, SectionFormState>;
type ActiveOperation = "create" | "upload" | "start" | "finalize" | "review" | "";

export type NextActionPrompt = {
  key: string;
  route: AppRoute;
  title: string;
  message: string;
  primaryLabel: string;
};

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function fileExtension(fileName: string): string {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex).toLowerCase() : "";
}

function createInitialSectionForms(): SectionFormStateMap {
  const forms = {} as SectionFormStateMap;
  for (const name of SECTION_NAMES) {
    forms[name] = {
      selected: name === "classroom",
      sectionComment: "",
      imageComment: "",
      selectedFiles: [],
      uploadedImages: [],
    };
  }
  return forms;
}

function clearRuntimeUploads(current: SectionFormStateMap): SectionFormStateMap {
  const forms = {} as SectionFormStateMap;
  for (const name of SECTION_NAMES) {
    forms[name] = {
      ...current[name],
      selectedFiles: [],
      uploadedImages: [],
    };
  }
  return forms;
}

function knownSectionNames(values: string[]): SectionName[] {
  return values.filter((value): value is SectionName => SECTION_NAMES.includes(value as SectionName));
}

function emptyInputStatus(sections: SectionName[]): InputStatus {
  return {
    can_start: false,
    missing_image_sections: sections,
    sections: Object.fromEntries(
      sections.map((name) => [name, { selected: true, image_count: 0, ready: false }]),
    ),
  };
}

function validateSelectedFiles(files: File[]): string | null {
  const unsupportedFile = files.find((file) => !SUPPORTED_UPLOAD_EXTENSIONS.includes(fileExtension(file.name)));
  if (unsupportedFile) {
    return `${unsupportedFile.name} is not supported. Use JPG, JPEG, or PNG images.`;
  }

  const oversizedFile = files.find((file) => file.size > MAX_UPLOAD_BYTES);
  if (oversizedFile) {
    return `${oversizedFile.name} is larger than 10 MB.`;
  }

  return null;
}

export function useInspectionRun() {
  const [message, setMessage] = useState("Ready.");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeOperation, setActiveOperation] = useState<ActiveOperation>("");
  const [uploadingSectionName, setUploadingSectionName] = useState<SectionName | null>(null);
  const [savingReviewId, setSavingReviewId] = useState("");

  const [schoolName, setSchoolName] = useState("Example Government School");
  const [inspectionDate, setInspectionDate] = useState(todayIsoDate());
  const [location, setLocation] = useState("Example District");
  const [sectionForms, setSectionForms] = useState<SectionFormStateMap>(createInitialSectionForms);

  const [runId, setRunId] = useState(() => localStorage.getItem(LAST_RUN_ID_STORAGE_KEY) || "");
  const [runSections, setRunSections] = useState<SectionName[]>([]);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [dismissedPromptKey, setDismissedPromptKey] = useState("");

  const normalizedApiUrl = DEFAULT_API_URL;
  const selectedSectionNames = useMemo(
    () => SECTION_NAMES.filter((name) => sectionForms[name].selected),
    [sectionForms],
  );
  const statusSectionNames = useMemo(
    () => knownSectionNames(Object.keys(runStatus?.input_status.sections ?? {})),
    [runStatus?.input_status.sections],
  );
  const uploadSectionNames = statusSectionNames.length ? statusSectionNames : runSections.length ? runSections : selectedSectionNames;
  const currentStatus = runStatus?.status;
  const reviewItems = runStatus?.human_review_items ?? [];
  const pendingReviewCount = reviewItems.filter((item) => item.status !== "reviewed").length;
  const reviewRequired = currentStatus === "awaiting_human_review" || pendingReviewCount > 0;
  const assessmentRunning = currentStatus === "running";
  const reportGenerating = currentStatus === "finalizing_report";
  const completedWithArtifacts = currentStatus === "completed" && Boolean(runStatus?.artifacts.length);
  const canUpload = Boolean(runId) && (!currentStatus || currentStatus === "created");
  const canStart = Boolean(runId) && (!currentStatus || currentStatus === "created") && Boolean(runStatus?.input_status.can_start);
  const allReviewItemsReviewed = Boolean(runStatus && reviewItems.every((item) => item.status === "reviewed"));
  const canFinalizeReport = Boolean(runId && runStatus?.status === "ready_for_report" && allReviewItemsReviewed);
  const reportReady = canFinalizeReport;
  const totalUploadedImages = SECTION_NAMES.reduce(
    (total, name) => total + (runStatus?.input_status.sections[name]?.image_count ?? sectionForms[name].uploadedImages.length),
    0,
  );
  const actionPrompt = useMemo<NextActionPrompt | null>(() => {
    if (!runId || !runStatus) {
      return null;
    }

    let prompt: NextActionPrompt | null = null;
    if (reviewRequired) {
      const reviewMessage = pendingReviewCount
        ? `${pendingReviewCount} flagged ${pendingReviewCount === 1 ? "item needs" : "items need"} review before the report can be generated.`
        : "Human review is required before the report can be generated.";
      prompt = {
        key: `${runId}:review:${pendingReviewCount}`,
        route: "human-review",
        title: "Human review needed",
        message: reviewMessage,
        primaryLabel: "Go to Review",
      };
    } else if (reportGenerating) {
      prompt = {
        key: `${runId}:report-generating`,
        route: "reports",
        title: "Report generation started",
        message: "The report is being prepared. Go to Reports to watch progress and download files when they appear.",
        primaryLabel: "Go to Reports",
      };
    } else if (reportReady) {
      prompt = {
        key: `${runId}:report-ready`,
        route: "reports",
        title: "Report can be generated",
        message: "All required review items are complete. Go to Reports to generate the final report.",
        primaryLabel: "Go to Reports",
      };
    } else if (completedWithArtifacts) {
      prompt = {
        key: `${runId}:report-complete:${runStatus.artifacts.length}`,
        route: "reports",
        title: "Report is ready",
        message: "The final report files are available in Reports.",
        primaryLabel: "Open Reports",
      };
    }

    if (!prompt || prompt.key === dismissedPromptKey) {
      return null;
    }
    return prompt;
  }, [
    completedWithArtifacts,
    dismissedPromptKey,
    pendingReviewCount,
    reportGenerating,
    reportReady,
    reviewRequired,
    runId,
    runStatus,
  ]);

  useEffect(() => {
    if (runId) {
      localStorage.setItem(LAST_RUN_ID_STORAGE_KEY, runId);
    }
  }, [runId]);

  const showError = useCallback((value: unknown) => {
    setError(value instanceof Error ? value.message : String(value));
  }, []);

  const updateSectionForm = useCallback((sectionName: SectionName, updates: Partial<SectionFormState>) => {
    setSectionForms((current) => ({
      ...current,
      [sectionName]: {
        ...current[sectionName],
        ...updates,
      },
    }));
  }, []);

  const refreshStatus = useCallback(async () => {
    if (!runId) {
      setError("Create an inspection first.");
      return;
    }
    setError("");
    try {
      const status = await getRunStatus(normalizedApiUrl, runId);
      const sections = knownSectionNames(Object.keys(status.input_status.sections));
      setRunStatus(status);
      if (sections.length) {
        setRunSections(sections);
      }
      setMessage(`Inspection status: ${status.status}`);
    } catch (caughtError) {
      showError(caughtError);
    }
  }, [normalizedApiUrl, runId, showError]);

  useEffect(() => {
    if (!runId || runStatus || runId.length < 8) {
      return;
    }
    void refreshStatus();
  }, [refreshStatus, runId, runStatus]);

  useEffect(() => {
    if (runStatus?.status !== "running" && runStatus?.status !== "finalizing_report") {
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

  const createInspectionRun = useCallback(async () => {
    if (!selectedSectionNames.length) {
      setError("Select at least one category.");
      return;
    }

    setBusy(true);
    setActiveOperation("create");
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
        input_status: emptyInputStatus(createdSections),
        progress: {
          phase: response.status,
          message: `Upload at least one image for: ${createdSections.map(formatSectionName).join(", ")}.`,
        },
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
        const cleared = clearRuntimeUploads(current);
        const next = {} as SectionFormStateMap;
        for (const name of SECTION_NAMES) {
          next[name] = {
            ...cleared[name],
            selected: createdSections.includes(name),
          };
        }
        return next;
      });
      setMessage(`Inspection created for ${createdSections.map(formatSectionName).join(", ")}.`);
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
      setActiveOperation("");
    }
  }, [inspectionDate, location, normalizedApiUrl, schoolName, sectionForms, selectedSectionNames, showError]);

  const uploadSectionImages = useCallback(
    async (sectionName: SectionName) => {
      const sectionForm = sectionForms[sectionName];
      if (!sectionForm.selectedFiles.length) {
        setError(`Choose at least one image for ${formatSectionName(sectionName)}.`);
        return;
      }
      if (runSections.length && !runSections.includes(sectionName)) {
        setError(`${formatSectionName(sectionName)} is not part of this inspection.`);
        return;
      }
      const fileValidationError = validateSelectedFiles(sectionForm.selectedFiles);
      if (fileValidationError) {
        setError(fileValidationError);
        return;
      }

      setBusy(true);
      setActiveOperation("upload");
      setUploadingSectionName(sectionName);
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
        await refreshStatus();
        showError(caughtError);
      } finally {
        setBusy(false);
        setActiveOperation("");
        setUploadingSectionName(null);
      }
    },
    [normalizedApiUrl, refreshStatus, runId, runSections, sectionForms, showError],
  );

  const startAssessment = useCallback(async () => {
    setBusy(true);
    setActiveOperation("start");
    setError("");
    try {
      await startRun(normalizedApiUrl, runId);
      setRunStatus((current) => (current ? { ...current, status: "running" } : current));
      setMessage("Assessment started. Status will refresh every 3 seconds.");
      await refreshStatus();
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
      setActiveOperation("");
    }
  }, [normalizedApiUrl, refreshStatus, runId, showError]);

  const finalizeCurrentReport = useCallback(async () => {
    setBusy(true);
    setActiveOperation("finalize");
    setError("");
    try {
      await finalizeReport(normalizedApiUrl, runId);
      setRunStatus((current) => (current ? { ...current, status: "finalizing_report" } : current));
      setMessage("Final report generation started. Status will refresh every 3 seconds.");
      await refreshStatus();
    } catch (caughtError) {
      showError(caughtError);
    } finally {
      setBusy(false);
      setActiveOperation("");
    }
  }, [normalizedApiUrl, refreshStatus, runId, showError]);

  const saveReviewDecision = useCallback(
    async (item: HumanReviewItem, status: ReviewDecisionStatus) => {
      setBusy(true);
      setActiveOperation("review");
      setSavingReviewId(item.review_id);
      setError("");
      try {
        await recordHumanReviewDecision(normalizedApiUrl, runId, item, status, reviewNotes[item.review_id] ?? "");
        setMessage(`Review item marked ${status}.`);
        await refreshStatus();
      } catch (caughtError) {
        showError(caughtError);
      } finally {
        setBusy(false);
        setActiveOperation("");
        setSavingReviewId("");
      }
    },
    [normalizedApiUrl, refreshStatus, reviewNotes, runId, showError],
  );

  const resetInspectionDraft = useCallback(() => {
    localStorage.removeItem(LAST_RUN_ID_STORAGE_KEY);
    setRunId("");
    setRunSections([]);
    setRunStatus(null);
    setReviewNotes({});
    setDismissedPromptKey("");
    setSectionForms(createInitialSectionForms());
    setError("");
    setMessage("Ready for a new inspection.");
  }, []);

  const dismissActionPrompt = useCallback(() => {
    if (actionPrompt) {
      setDismissedPromptKey(actionPrompt.key);
    }
  }, [actionPrompt]);

  return {
    normalizedApiUrl,
    message,
    error,
    busy,
    schoolName,
    setSchoolName,
    inspectionDate,
    setInspectionDate,
    location,
    setLocation,
    sectionForms,
    updateSectionForm,
    runId,
    runSections,
    runStatus,
    reviewNotes,
    setReviewNotes,
    activeOperation,
    uploadingSectionName,
    savingReviewId,
    selectedSectionNames,
    uploadSectionNames,
    canUpload,
    canStart,
    canFinalizeReport,
    allReviewItemsReviewed,
    pendingReviewCount,
    reviewRequired,
    assessmentRunning,
    reportReady,
    reportGenerating,
    completedWithArtifacts,
    actionPrompt,
    isCreatingInspection: activeOperation === "create",
    isUploadingImages: activeOperation === "upload",
    isStartingAssessment: activeOperation === "start",
    isFinalizingReport: activeOperation === "finalize",
    isSavingReview: activeOperation === "review",
    totalUploadedImages,
    refreshStatus,
    createInspectionRun,
    uploadSectionImages,
    startAssessment,
    finalizeCurrentReport,
    saveReviewDecision,
    resetInspectionDraft,
    dismissActionPrompt,
  };
}

export type InspectionRunController = ReturnType<typeof useInspectionRun>;
