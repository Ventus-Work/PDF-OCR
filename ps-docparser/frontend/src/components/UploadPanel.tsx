import { useEffect, useState, type DragEvent, type FormEvent } from "react";
import type { ConfigResponse, JobForm } from "../api/client";
import { labelEngine, labelFallback, labelPreset } from "../labels";

interface Props {
  config: ConfigResponse | null;
  disabled: boolean;
  onSubmit: (form: JobForm) => void;
}

export function UploadPanel({ config, disabled, onSubmit }: Props) {
  const presets = config?.presets ?? ["auto", "generic", "bom", "estimate", "pumsem"];
  const engines = config?.engines ?? ["auto", "zai", "gemini", "local", "mistral", "tesseract"];
  const fallbackModes = config?.bom_fallback_modes ?? ["auto", "always", "never"];
  const [preset, setPreset] = useState(config?.defaults.preset ?? "auto");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [pageError, setPageError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const bomFallbackEnabled = preset === "auto" || preset === "bom";

  useEffect(() => {
    if (config?.defaults.preset) {
      setPreset(config.defaults.preset);
    }
  }, [config?.defaults.preset]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const selectedPreset = String(form.get("preset") ?? "auto");
    const pages = String(form.get("pages") ?? "");
    const pageValidation = validatePages(pages);
    setPageError(pageValidation);
    if (pageValidation) {
      return;
    }
    if (selectedFiles.length === 0) {
      setFileError("PDF 파일을 선택하거나 끌어오세요.");
      return;
    }
    onSubmit({
      files: selectedFiles,
      preset: selectedPreset,
      engine: String(form.get("engine") ?? "auto"),
      pages,
      bom_fallback: bomFallbackEnabled ? String(form.get("bom_fallback") ?? "auto") : "auto",
      no_cache: form.get("no_cache") === "on"
    });
  }

  function acceptFiles(files: FileList | File[] | null) {
    const incoming = Array.from(files ?? []);
    if (incoming.length === 0) {
      return;
    }
    const pdfs = incoming.filter(isPdf);
    if (pdfs.length === 0) {
      setSelectedFiles([]);
      setFileError("PDF 파일만 사용할 수 있습니다.");
      return;
    }
    setSelectedFiles(pdfs);
    setFileError(pdfs.length === incoming.length ? null : "PDF가 아닌 파일은 제외했습니다.");
  }

  function handleDrag(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (disabled) {
      return;
    }
    setDragActive(event.type === "dragenter" || event.type === "dragover");
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setDragActive(false);
    if (disabled) {
      return;
    }
    acceptFiles(event.dataTransfer.files);
  }

  return (
    <form className="tool-panel upload-panel" onSubmit={submit}>
      <div className="panel-heading">
        <span className="icon-mark" aria-hidden="true">업</span>
        <h2>업로드</h2>
      </div>

      <label className="field">
        <span>PDF 파일</span>
        <div
          className={`drop-zone ${dragActive ? "active" : ""}`}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
        >
          <div className="upload-actions">
            <label className="file-pick-button">
              <input
                name="file"
                type="file"
                accept="application/pdf,.pdf"
                disabled={disabled}
                onChange={(event) => acceptFiles(event.target.files)}
              />
              PDF 파일 선택
            </label>
            <label className="file-pick-button secondary">
              <input
                name="folder"
                type="file"
                accept="application/pdf,.pdf"
                multiple
                webkitdirectory=""
                directory=""
                disabled={disabled}
                onChange={(event) => acceptFiles(event.target.files)}
              />
              PDF 폴더 선택
            </label>
          </div>
          <span className="selected-file">{selectedLabel(selectedFiles)}</span>
          <small className="field-help">파일 또는 폴더를 선택하거나 PDF를 이 영역에 끌어오세요.</small>
        </div>
        {fileError ? <small className="field-error">{fileError}</small> : null}
      </label>

      <div className="field-grid">
        <label className="field">
          <span>문서 유형</span>
          <select
            name="preset"
            value={preset}
            disabled={disabled}
            onChange={(event) => setPreset(event.target.value)}
          >
            {presets.map((item) => (
              <option key={item} value={item}>
                {labelPreset(item)}
              </option>
            ))}
          </select>
          <small className="field-help">{presetHelp(preset)}</small>
        </label>

        <label className="field">
          <span>OCR 엔진</span>
          <select name="engine" defaultValue={config?.defaults.engine ?? "auto"} disabled={disabled}>
            {engines.map((item) => (
              <option key={item} value={item}>
                {labelEngine(item)}
              </option>
            ))}
          </select>
          <small className="field-help">자동은 기본 엔진 설정을 사용합니다.</small>
        </label>
      </div>

      <label className="field">
        <span>페이지 범위</span>
        <input
          name="pages"
          type="text"
          placeholder="1-10, 20-, 1,3,5-10"
          disabled={disabled}
          aria-invalid={pageError ? "true" : "false"}
          onChange={(event) => setPageError(validatePages(event.target.value))}
        />
        {pageError ? <small className="field-error">{pageError}</small> : null}
      </label>

      <div className="field-grid">
        <label className="field">
          <span>BOM 보조 산출물</span>
          <select
            name="bom_fallback"
            defaultValue={config?.defaults.bom_fallback ?? "auto"}
            disabled={disabled || !bomFallbackEnabled}
          >
            {fallbackModes.map((item) => (
              <option key={item} value={item}>
                {labelFallback(item)}
              </option>
            ))}
          </select>
          <small className="field-help">
            {bomFallbackEnabled ? "자동 또는 BOM 도면에서만 적용됩니다." : "현재 문서 유형에서는 적용되지 않습니다."}
          </small>
        </label>

        <label className="check-field">
          <input name="no_cache" type="checkbox" disabled={disabled} />
          <span>캐시 미사용</span>
        </label>
      </div>

      <button className="primary-action" type="submit" disabled={disabled}>
        <span className="icon-mark" aria-hidden="true">실</span>
        실행
      </button>
    </form>
  );
}

function isPdf(file: File): boolean {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function selectedLabel(files: File[]): string {
  if (files.length === 0) {
    return "선택된 파일 없음";
  }
  if (files.length === 1) {
    return files[0].name;
  }
  const totalSize = files.reduce((sum, file) => sum + file.size, 0);
  return `${files.length}개 PDF 선택 · ${formatBytes(totalSize)}`;
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function presetHelp(value: string): string {
  return (
    {
      auto: "문서 내용을 분석해 특화 또는 범용 경로로 처리합니다.",
      generic: "자동 판별 없이 일반 문서 경로로 처리합니다.",
      bom: "BOM 전용 추출과 표 정합성 경로로 처리합니다.",
      estimate: "견적서 preset 기준으로 처리합니다.",
      pumsem: "품셈 preset 기준으로 처리합니다."
    }[value] ?? ""
  );
}

function validatePages(value: string): string | null {
  const text = value.trim();
  if (!text) {
    return null;
  }
  for (const token of text.split(",")) {
    const part = token.trim();
    const match = part.match(/^([1-9]\d*)(?:-(\d*))?$/);
    if (!match) {
      return "페이지 범위 형식이 올바르지 않습니다.";
    }
    if (match[2] && Number(match[2]) < Number(match[1])) {
      return "끝 페이지는 시작 페이지보다 작을 수 없습니다.";
    }
  }
  return null;
}
