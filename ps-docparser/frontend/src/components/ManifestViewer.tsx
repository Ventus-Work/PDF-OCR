import type { ArtifactItem, QAResponse } from "../api/client";
import { labelArtifactKind } from "../labels";

interface Props {
  artifacts: ArtifactItem[];
  qa: QAResponse | null;
}

export function ManifestViewer({ artifacts, qa }: Props) {
  const manifestArtifacts = artifacts.filter((item) => item.kind === "manifest" || item.kind === "summary" || item.kind === "qa");

  return (
    <div className="manifest-view">
      <div className="manifest-list">
        {manifestArtifacts.length > 0 ? (
          manifestArtifacts.map((item) => (
            <div className="manifest-row" key={item.artifact_id}>
              <span className="icon-mark" aria-hidden="true">매</span>
              <span>{item.relative_path}</span>
              <small>{labelArtifactKind(item.kind)}</small>
            </div>
          ))
        ) : (
          <p className="empty-state">매니페스트 관련 산출물이 아직 없습니다.</p>
        )}
      </div>

      {qa?.summary_markdown ? (
        <pre className="summary-markdown">{qa.summary_markdown}</pre>
      ) : (
        <p className="empty-state">QA 원문 요약을 불러올 수 없습니다.</p>
      )}
    </div>
  );
}
