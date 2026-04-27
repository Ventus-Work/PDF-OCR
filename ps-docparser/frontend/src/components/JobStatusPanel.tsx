import type { JobStatusResponse } from "../api/client";
import { labelEngine, labelPreset, labelStatus } from "../labels";

interface Props {
  job: JobStatusResponse | null;
  loading: boolean;
  onCancel: () => void;
  onRefresh: () => void;
  onOpenFolder: () => void;
}

export function JobStatusPanel({ job, loading, onCancel, onRefresh, onOpenFolder }: Props) {
  const canCancel = job?.status === "queued" || job?.status === "running";
  const canOpenFolder = job?.status === "succeeded" || job?.status === "failed" || job?.status === "canceled";

  return (
    <section className="tool-panel status-panel">
      <div className="panel-heading">
        <span className={`icon-mark ${loading ? "spin" : ""}`} aria-hidden="true">상</span>
        <h2>작업 상태</h2>
      </div>

      {job ? (
        <>
          <div className="status-line">
            <span className={`status-badge ${job.status}`}>{labelStatus(job.status)}</span>
            <span className="job-id">{job.job_id}</span>
          </div>
          <dl className="status-grid">
            <dt>문서 유형</dt>
            <dd>{labelPreset(job.preset)}</dd>
            <dt>요청 엔진</dt>
            <dd>{labelEngine(job.requested_engine ?? job.engine)}</dd>
            <dt>실제 문서 유형</dt>
            <dd>{job.effective_preset ? labelPreset(job.effective_preset) : "-"}</dd>
            <dt>실제 엔진</dt>
            <dd>{job.effective_engine ? labelEngine(job.effective_engine) : "-"}</dd>
            <dt>생성</dt>
            <dd>{job.created_at}</dd>
            <dt>시작</dt>
            <dd>{job.started_at ?? "-"}</dd>
            <dt>종료</dt>
            <dd>{job.finished_at ?? "-"}</dd>
            <dt>최종 코드</dt>
            <dd>{job.exit_code ?? "-"}</dd>
            <dt>CLI 코드</dt>
            <dd>{job.cli_exit_code ?? "-"}</dd>
            <dt>QA 코드</dt>
            <dd>{job.analyzer_exit_code ?? "-"}</dd>
          </dl>
          {job.engine_note ? <p className="message muted">{job.engine_note}</p> : null}
          {job.message ? <p className="message">{job.message}</p> : null}
          <div className="action-row">
            <button type="button" className="secondary-action" onClick={onRefresh}>
              <span className="icon-mark" aria-hidden="true">새</span>
              새로고침
            </button>
            <button type="button" className="danger-action" onClick={onCancel} disabled={!canCancel}>
              <span className="icon-mark" aria-hidden="true">중</span>
              취소
            </button>
            <button type="button" className="secondary-action" onClick={onOpenFolder} disabled={!canOpenFolder}>
              <span className="icon-mark" aria-hidden="true">폴</span>
              작업폴더 열기
            </button>
          </div>
        </>
      ) : (
        <p className="empty-state">아직 실행한 작업이 없습니다.</p>
      )}
    </section>
  );
}
