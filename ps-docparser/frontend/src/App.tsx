import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  cancelJob,
  createJob,
  getArtifacts,
  getArtifactPreview,
  getConfig,
  getJob,
  getJobs,
  getQA,
  getUsageDaily,
  getUsageForJob,
  getUsageSummary,
  openJobFolder,
  type ArtifactItem,
  type ArtifactPreviewResponse,
  type ConfigResponse,
  type JobForm,
  type JobListItem,
  type JobStatusResponse,
  type QAResponse,
  type UsageDailyResponse,
  type UsageJobResponse,
  type UsageSummaryResponse
} from "./api/client";
import { ArtifactPreviewPanel } from "./components/ArtifactPreviewPanel";
import { ArtifactList } from "./components/ArtifactList";
import { JobStatusPanel } from "./components/JobStatusPanel";
import { LogViewer } from "./components/LogViewer";
import { ManifestViewer } from "./components/ManifestViewer";
import { QASummary } from "./components/QASummary";
import { UploadPanel } from "./components/UploadPanel";
import { UsageDashboard } from "./components/UsageDashboard";

type Tab = "artifacts" | "review" | "qa" | "logs" | "manifest" | "usage";

const terminalStates = new Set(["succeeded", "failed", "canceled"]);

export default function App() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [job, setJob] = useState<JobStatusResponse | null>(null);
  const [recentJobs, setRecentJobs] = useState<JobListItem[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [preview, setPreview] = useState<ArtifactPreviewResponse | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [qa, setQa] = useState<QAResponse | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("artifacts");
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageSummary, setUsageSummary] = useState<UsageSummaryResponse | null>(null);
  const [usageDaily, setUsageDaily] = useState<UsageDailyResponse | null>(null);
  const [jobUsage, setJobUsage] = useState<UsageJobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch((err: Error) => setError(`API 서버 연결 실패: ${err.message}`));
    getJobs()
      .then((response) => setRecentJobs(response.jobs))
      .catch(() => undefined);
  }, []);

  const refreshRecentJobs = useCallback(async () => {
    const response = await getJobs();
    setRecentJobs(response.jobs);
  }, []);

  const refreshOutputs = useCallback(async (jobId: string) => {
    const [artifactResponse, qaResponse] = await Promise.all([getArtifacts(jobId), getQA(jobId)]);
    setArtifacts(artifactResponse.artifacts);
    setQa(qaResponse);
  }, []);

  const refreshUsage = useCallback(async () => {
    setUsageLoading(true);
    try {
      const [summaryResponse, dailyResponse, jobUsageResponse] = await Promise.all([
        getUsageSummary("all"),
        getUsageDaily(),
        job ? getUsageForJob(job.job_id) : Promise.resolve(null)
      ]);
      setUsageSummary(summaryResponse);
      setUsageDaily(dailyResponse);
      setJobUsage(jobUsageResponse);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUsageLoading(false);
    }
  }, [job]);

  const refreshJob = useCallback(async () => {
    if (!job) {
      return;
    }
    setLoading(true);
    try {
      const nextJob = await getJob(job.job_id);
      setJob(nextJob);
      if (terminalStates.has(nextJob.status)) {
        await refreshOutputs(nextJob.job_id);
      }
      await refreshRecentJobs();
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [job, refreshOutputs, refreshRecentJobs]);

  useEffect(() => {
    if (!job || terminalStates.has(job.status)) {
      return;
    }
    const handle = window.setInterval(() => {
      getJob(job.job_id)
        .then(async (nextJob) => {
          setJob(nextJob);
          if (terminalStates.has(nextJob.status)) {
            await refreshOutputs(nextJob.job_id);
            await refreshRecentJobs();
          }
        })
        .catch((err: Error) => setError(err.message));
    }, 2000);
    return () => window.clearInterval(handle);
  }, [job, refreshOutputs, refreshRecentJobs]);

  useEffect(() => {
    if (activeTab === "usage") {
      void refreshUsage();
    }
  }, [activeTab, refreshUsage]);

  async function handleSubmit(form: JobForm) {
    setLoading(true);
    setError(null);
    setArtifacts([]);
    setPreview(null);
    setPreviewOpen(false);
    setQa(null);
    setActiveTab("artifacts");
    try {
      const created = await createJob(form);
      const nextJob = await getJob(created.job_id);
      setJob(nextJob);
      await refreshRecentJobs();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel() {
    if (!job) {
      return;
    }
    setLoading(true);
    try {
      const nextJob = await cancelJob(job.job_id);
      setJob(nextJob);
      await refreshRecentJobs();
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenFolder() {
    if (!job) {
      return;
    }
    setLoading(true);
    try {
      const response = await openJobFolder(job.job_id);
      setError(response.opened ? null : response.message);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectRecent(jobId: string) {
    setLoading(true);
    try {
      const nextJob = await getJob(jobId);
      setJob(nextJob);
      setPreview(null);
      setPreviewOpen(false);
      if (terminalStates.has(nextJob.status)) {
        await refreshOutputs(nextJob.job_id);
      }
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handlePreview(artifact: ArtifactItem) {
    if (!job) {
      return;
    }
    setPreviewOpen(true);
    setPreviewLoading(true);
    try {
      const response = await getArtifactPreview(job.job_id, artifact.artifact_id);
      setPreview(response);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  }

  const running = job?.status === "queued" || job?.status === "running";
  const logLines = useMemo(() => job?.log_tail ?? [], [job]);
  const stdoutLines = useMemo(() => job?.stdout_tail ?? [], [job]);
  const stderrLines = useMemo(() => job?.stderr_tail ?? [], [job]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>ps-docparser</h1>
          <p>PDF 업로드, 파서 실행, QA 확인, 결과 다운로드</p>
        </div>
        <div className="header-badges">
          <span>FastAPI</span>
          <span>React/Vite</span>
          <span>로컬 실행</span>
        </div>
      </header>

      {error ? (
        <div className="error-banner" role="alert">
          <span className="icon-mark" aria-hidden="true">!</span>
          {error}
        </div>
      ) : null}

      <main className="workbench">
        <UploadPanel config={config} disabled={loading || running} onSubmit={handleSubmit} />
        <JobStatusPanel
          job={job}
          loading={loading || running}
          onCancel={handleCancel}
          onRefresh={refreshJob}
          onOpenFolder={handleOpenFolder}
        />
        <RecentJobsPanel jobs={recentJobs} onSelect={handleSelectRecent} />
      </main>

      <section className="result-surface">
        <div className="tab-row" role="tablist" aria-label="결과 탭">
          <TabButton tab="artifacts" activeTab={activeTab} onClick={setActiveTab} icon={<span className="icon-mark">결</span>}>
            결과
          </TabButton>
          <TabButton tab="review" activeTab={activeTab} onClick={setActiveTab} icon={<span className="icon-mark">보</span>}>
            리뷰
          </TabButton>
          <TabButton tab="qa" activeTab={activeTab} onClick={setActiveTab} icon={<span className="icon-mark">검</span>}>
            QA
          </TabButton>
          <TabButton tab="logs" activeTab={activeTab} onClick={setActiveTab} icon={<span className="icon-mark">기</span>}>
            로그
          </TabButton>
          <TabButton tab="manifest" activeTab={activeTab} onClick={setActiveTab} icon={<span className="icon-mark">매</span>}>
            매니페스트
          </TabButton>
          <TabButton tab="usage" activeTab={activeTab} onClick={setActiveTab} icon={<span className="icon-mark">량</span>}>
            사용량
          </TabButton>
        </div>

        <div className="tab-panel">
          {activeTab === "artifacts" ? (
            <ArtifactList jobId={job?.job_id ?? null} artifacts={artifacts} onPreview={handlePreview} />
          ) : null}
          {activeTab === "review" ? <ArtifactPreviewPanel preview={preview} loading={previewLoading} /> : null}
          {activeTab === "qa" ? <QASummary qa={qa} /> : null}
          {activeTab === "logs" ? <LogViewer lines={logLines} stdoutLines={stdoutLines} stderrLines={stderrLines} /> : null}
          {activeTab === "manifest" ? <ManifestViewer artifacts={artifacts} qa={qa} /> : null}
          {activeTab === "usage" ? (
            <UsageDashboard summary={usageSummary} daily={usageDaily} jobUsage={jobUsage} loading={usageLoading} />
          ) : null}
        </div>
      </section>

      {previewOpen ? (
        <PreviewModal onClose={() => setPreviewOpen(false)}>
          <ArtifactPreviewPanel preview={preview} loading={previewLoading} />
        </PreviewModal>
      ) : null}
    </div>
  );
}

function PreviewModal({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="preview-modal"
        role="dialog"
        aria-modal="true"
        aria-label="산출물 리뷰"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <span className="eyebrow">미리보기</span>
            <h2>산출물 리뷰</h2>
          </div>
          <button type="button" className="modal-close" onClick={onClose} aria-label="닫기">
            닫기
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
}

function RecentJobsPanel({ jobs, onSelect }: { jobs: JobListItem[]; onSelect: (jobId: string) => void }) {
  return (
    <section className="tool-panel recent-panel">
      <div className="panel-heading">
        <span className="icon-mark" aria-hidden="true">최</span>
        <h2>최근 작업</h2>
      </div>
      {jobs.length === 0 ? (
        <p className="empty-state">저장된 작업이 없습니다.</p>
      ) : (
        <div className="recent-list">
          {jobs.map((item) => (
            <button type="button" key={item.job_id} onClick={() => onSelect(item.job_id)}>
              <span>{item.job_id}</span>
              <small>{item.status} · {item.preset} · {item.input_count}개 입력 · {item.created_at}</small>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function TabButton({
  tab,
  activeTab,
  onClick,
  icon,
  children
}: {
  tab: Tab;
  activeTab: Tab;
  onClick: (tab: Tab) => void;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <button type="button" className={activeTab === tab ? "active" : ""} onClick={() => onClick(tab)}>
      {icon}
      {children}
    </button>
  );
}
