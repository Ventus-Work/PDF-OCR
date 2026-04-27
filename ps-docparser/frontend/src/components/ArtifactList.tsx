import { artifactDownloadUrl, type ArtifactItem } from "../api/client";
import { labelArtifactKind, labelDomain, labelQuality, labelRole } from "../labels";

interface Props {
  jobId: string | null;
  artifacts: ArtifactItem[];
  onPreview: (artifact: ArtifactItem) => void;
}

export function ArtifactList({ jobId, artifacts, onPreview }: Props) {
  if (!jobId) {
    return <p className="empty-state">완료된 작업을 선택하면 결과가 표시됩니다.</p>;
  }
  if (artifacts.length === 0) {
    return <p className="empty-state">표시할 산출물이 아직 없습니다.</p>;
  }

  const firstClassItems = artifacts.filter((artifact) => artifact.role === "representative");
  const hasMixedFirstClass =
    firstClassItems.some((artifact) => artifact.domain === "bom")
    && firstClassItems.some((artifact) => artifact.domain === "estimate");

  const groups = [
    { title: "1급 산출물", items: firstClassItems },
    { title: "진단 산출물", items: artifacts.filter((artifact) => artifact.role === "diagnostic") },
    { title: "원본 비교 산출물", items: artifacts.filter((artifact) => artifact.role === "compare") },
    {
      title: "기타 산출물",
      items: artifacts.filter((artifact) => !["representative", "diagnostic", "compare"].includes(artifact.role))
    }
  ].filter((group) => group.items.length > 0);

  return (
    <div className="artifact-groups">
      {hasMixedFirstClass ? (
        <div className="artifact-notice" role="status">
          혼합 문서로 판단되어 BOM과 견적서 산출물을 모두 1급 결과로 표시합니다.
        </div>
      ) : null}
      {groups.map((group) => (
        <section className="artifact-group" key={group.title}>
          <h3>{group.title}</h3>
          <div className="table-wrap">
            <table className="artifact-table">
              <thead>
                <tr>
                  <th>파일</th>
                  <th>종류</th>
                  <th>문서 영역</th>
                  <th>역할</th>
                  <th>품질</th>
                  <th>크기</th>
                  <th>작업</th>
                </tr>
              </thead>
              <tbody>
                {group.items.map((artifact) => (
                  <tr key={artifact.artifact_id}>
                    <td className="artifact-name">
                      {iconForKind(artifact.kind)}
                      <span>{artifact.relative_path}</span>
                    </td>
                    <td>{labelArtifactKind(artifact.kind)}</td>
                    <td>{labelDomain(artifact.domain)}</td>
                    <td>{labelRole(artifact.role)}</td>
                    <td>{labelQuality(artifact.quality_status)}</td>
                    <td>{formatBytes(artifact.size_bytes)}</td>
                    <td className="artifact-actions">
                      <button type="button" className="mini-action" onClick={() => onPreview(artifact)}>
                        보기
                      </button>
                      <a
                        className="icon-link"
                        href={artifactDownloadUrl(jobId, artifact.artifact_id)}
                        title={`${artifact.name} 다운로드`}
                      >
                        <span className="icon-mark" aria-hidden="true">받</span>
                        받기
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

function iconForKind(kind: ArtifactItem["kind"]) {
  if (kind === "json" || kind === "manifest") {
    return <span className="icon-mark" aria-hidden="true">JS</span>;
  }
  if (kind === "xlsx") {
    return <span className="icon-mark" aria-hidden="true">XL</span>;
  }
  return <span className="icon-mark" aria-hidden="true">문</span>;
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
