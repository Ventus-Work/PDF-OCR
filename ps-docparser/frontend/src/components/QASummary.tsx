import type { QAResponse } from "../api/client";
import { labelDomain, labelQuality, labelStatus } from "../labels";

interface Props {
  qa: QAResponse | null;
}

export function QASummary({ qa }: Props) {
  if (!qa) {
    return <p className="empty-state">QA 리포트가 아직 없습니다.</p>;
  }

  return (
    <div className="qa-grid">
      <div className={`qa-status ${qa.status}`}>
        {statusIcon(qa.status)}
        <span>{labelStatus(qa.status)}</span>
      </div>
      <Metric label="JSON" value={qa.json_files} />
      <Metric label="Excel" value={qa.excel_files} />
      <Metric label="매니페스트" value={qa.has_manifest ? "있음" : "없음"} />
      <Metric label="입력 파일" value={qa.manifest_inputs} />
      <Metric label="대표본" value={qa.manifest_representative} />
      <Metric label="진단본" value={qa.manifest_diagnostic} />
      <Metric label="헤더/키 불일치" value={qa.header_key_mismatch} emphasis={qa.header_key_mismatch > 0} />
      <Metric label="잘못된 복합 헤더" value={qa.bad_composite_headers} emphasis={qa.bad_composite_headers > 0} />

      <section className="qa-section">
        <h3>품질 주의 항목</h3>
        <KeyValueList items={qa.quality_warnings} labeler={labelQuality} />
      </section>

      <section className="qa-section">
        <h3>문서 영역</h3>
        <KeyValueList items={qa.manifest_domains} labeler={labelDomain} />
      </section>
    </div>
  );
}

function Metric({ label, value, emphasis = false }: { label: string; value: string | number; emphasis?: boolean }) {
  return (
    <div className={`metric ${emphasis ? "emphasis" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function KeyValueList({ items, labeler }: { items: Record<string, number>; labeler?: (value: string) => string }) {
  const entries = Object.entries(items);
  if (entries.length === 0) {
    return <p className="empty-state compact">없음</p>;
  }
  return (
    <ul className="kv-list">
      {entries.map(([key, value]) => (
        <li key={key}>
          <span>{labeler ? labeler(key) : key}</span>
          <strong>{value}</strong>
        </li>
      ))}
    </ul>
  );
}

function statusIcon(status: QAResponse["status"]) {
  if (status === "ok") {
    return <span className="icon-mark" aria-hidden="true">OK</span>;
  }
  if (status === "warn") {
    return <span className="icon-mark" aria-hidden="true">주</span>;
  }
  if (status === "fail") {
    return <span className="icon-mark" aria-hidden="true">실</span>;
  }
  return <span className="icon-mark" aria-hidden="true">?</span>;
}
