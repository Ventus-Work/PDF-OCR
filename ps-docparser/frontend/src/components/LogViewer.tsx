interface Props {
  lines: string[];
  stdoutLines?: string[];
  stderrLines?: string[];
}

export function LogViewer({ lines, stdoutLines = [], stderrLines = [] }: Props) {
  if (lines.length === 0 && stdoutLines.length === 0 && stderrLines.length === 0) {
    return <p className="empty-state">표시할 로그가 없습니다.</p>;
  }

  return (
    <div className="log-stack">
      {stdoutLines.length > 0 || stderrLines.length > 0 ? (
        <>
          <LogBlock title="stdout" lines={stdoutLines} />
          <LogBlock title="stderr" lines={stderrLines} />
        </>
      ) : (
        <pre className="log-viewer" aria-label="job log tail">
          {lines.join("\n")}
        </pre>
      )}
    </div>
  );
}

function LogBlock({ title, lines }: { title: string; lines: string[] }) {
  return (
    <section className="log-block">
      <h3>{title}</h3>
      {lines.length > 0 ? (
        <pre className="log-viewer" aria-label={`${title} log tail`}>
          {lines.join("\n")}
        </pre>
      ) : (
        <p className="empty-state compact">표시할 로그가 없습니다.</p>
      )}
    </section>
  );
}
