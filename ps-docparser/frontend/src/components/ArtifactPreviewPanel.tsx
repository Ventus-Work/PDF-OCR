import type { ArtifactPreviewResponse } from "../api/client";
import { labelArtifactKind } from "../labels";

interface Props {
  preview: ArtifactPreviewResponse | null;
  loading: boolean;
}

export function ArtifactPreviewPanel({ preview, loading }: Props) {
  if (loading) {
    return <p className="empty-state">산출물 미리보기를 불러오는 중입니다.</p>;
  }
  if (!preview) {
    return <p className="empty-state">결과 탭에서 `보기`를 누르면 JSON, Markdown, Excel 내용을 여기서 확인할 수 있습니다.</p>;
  }

  return (
    <div className="preview-panel">
      <div className="preview-heading">
        <div>
          <span className="eyebrow">{labelArtifactKind(preview.kind)}</span>
          <h3>{preview.name}</h3>
        </div>
        {preview.message ? <small>{preview.message}</small> : null}
      </div>

      {preview.kind === "xlsx" ? <ExcelPreview preview={preview} /> : <TextPreview preview={preview} />}
    </div>
  );
}

function TextPreview({ preview }: { preview: ArtifactPreviewResponse }) {
  if (!preview.text) {
    return <p className="empty-state">표시할 텍스트가 없습니다.</p>;
  }
  if (preview.kind === "md" || preview.kind === "summary" || preview.kind === "qa") {
    return (
      <div className="markdown-viewer">
        <div className="markdown-preview">
          {renderMarkdown(preview.text)}
        </div>
        <details className="raw-markdown">
          <summary>원문 보기</summary>
          <pre>{preview.text}</pre>
        </details>
      </div>
    );
  }
  return <pre className="json-preview">{preview.text}</pre>;
}

function ExcelPreview({ preview }: { preview: ArtifactPreviewResponse }) {
  if (preview.columns.length === 0 && preview.rows.length === 0) {
    return <p className="empty-state">표시할 Excel 행이 없습니다.</p>;
  }
  return (
    <div className="table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            {preview.columns.map((column, index) => (
              <th key={`${column}-${index}`}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {preview.columns.map((_, columnIndex) => (
                <td key={columnIndex}>{formatCell(row[columnIndex])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {preview.truncated ? <p className="field-help">상위 행만 표시했습니다. 전체 내용은 다운로드해서 확인하세요.</p> : null}
    </div>
  );
}

function renderMarkdown(text: string) {
  const parts = splitMarkdownTables(text);
  return parts.map((part, index) => {
    if (part.kind === "table") {
      return <HtmlTablePreview html={part.value} key={`table-${index}`} />;
    }
    return (
      <div className="markdown-block" key={`text-${index}`}>
        {part.value.split(/\r?\n/).map((line, lineIndex) => renderMarkdownLine(line, `${index}-${lineIndex}`))}
      </div>
    );
  });
}

function splitMarkdownTables(text: string): Array<{ kind: "text" | "table"; value: string }> {
  const parts: Array<{ kind: "text" | "table"; value: string }> = [];
  const tablePattern = /<table[\s\S]*?<\/table>/gi;
  let lastIndex = 0;
  for (const match of text.matchAll(tablePattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      parts.push({ kind: "text", value: text.slice(lastIndex, index) });
    }
    parts.push({ kind: "table", value: match[0] });
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push({ kind: "text", value: text.slice(lastIndex) });
  }
  return parts.length ? parts : [{ kind: "text", value: text }];
}

function HtmlTablePreview({ html }: { html: string }) {
  return (
    <div
      className="markdown-table"
      dangerouslySetInnerHTML={{ __html: sanitizeTableHtml(html) }}
    />
  );
}

function sanitizeTableHtml(html: string): string {
  const allowedTags = new Set(["table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col", "br"]);
  const allowedAttrs = new Set(["colspan", "rowspan", "scope"]);
  return html
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<\s*(script|style|iframe|object|embed)[\s\S]*?<\s*\/\s*\1\s*>/gi, "")
    .replace(/<\/?([a-z][\w-]*)([^>]*)>/gi, (match, rawTag: string, rawAttrs: string) => {
      const tag = rawTag.toLowerCase();
      const closing = match.startsWith("</");
      if (!allowedTags.has(tag)) {
        return "";
      }
      if (closing) {
        return `</${tag}>`;
      }
      const attrs: string[] = [];
      for (const attrMatch of rawAttrs.matchAll(/\s+([a-zA-Z:-]+)(?:=(".*?"|'.*?'|[^\s"'>]+))?/g)) {
        const name = attrMatch[1].toLowerCase();
        const rawValue = attrMatch[2] ?? "";
        const value = rawValue.replace(/^["']|["']$/g, "");
        if (allowedAttrs.has(name) && (/^\d{1,3}$/.test(value) || (name === "scope" && /^(row|col|rowgroup|colgroup)$/.test(value)))) {
          attrs.push(` ${name}="${escapeAttribute(value)}"`);
        }
      }
      return `<${tag}${attrs.join("")}>`;
    });
}

function escapeAttribute(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderMarkdownLine(line: string, key: string) {
  if (!line.trim()) {
    return <div className="md-line blank" key={key} />;
  }
  const pageMarker = line.match(/^<!--\s*(PAGE\s+\d+)\s*-->$/i);
  if (pageMarker) {
    return <div className="page-marker" key={key}>{pageMarker[1].toUpperCase()}</div>;
  }
  if (line.startsWith("# ")) {
    return <h2 key={key}>{line.replace(/^#\s+/, "")}</h2>;
  }
  if (line.startsWith("## ")) {
    return <h3 key={key}>{line.replace(/^##\s+/, "")}</h3>;
  }
  if (line.startsWith("### ")) {
    return <h4 key={key}>{line.replace(/^###\s+/, "")}</h4>;
  }
  if (line.startsWith("- ")) {
    return <p className="md-bullet" key={key}>{line}</p>;
  }
  return <p className="md-line" key={key}>{line}</p>;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}
