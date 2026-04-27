export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";

export interface ConfigResponse {
  presets: string[];
  engines: string[];
  bom_fallback_modes: string[];
  defaults: {
    preset: string;
    engine: string;
    output_format: string;
    bom_fallback: string;
  };
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
  status_url: string;
  input_count: number;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  preset: string;
  engine: string;
  requested_engine: string;
  effective_preset: string | null;
  effective_engine: string | null;
  engine_note: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  cli_exit_code: number | null;
  analyzer_exit_code: number | null;
  message: string | null;
  log_tail: string[];
  stdout_tail: string[];
  stderr_tail: string[];
}

export interface JobListItem {
  job_id: string;
  status: JobStatus;
  preset: string;
  engine: string;
  created_at: string;
  finished_at: string | null;
  message: string | null;
  input_count: number;
}

export interface JobsListResponse {
  jobs: JobListItem[];
}

export interface ArtifactItem {
  artifact_id: string;
  name: string;
  relative_path: string;
  kind: "md" | "json" | "xlsx" | "manifest" | "summary" | "qa" | "other";
  size_bytes: number;
  download_url: string;
  role: string;
  domain: string;
  quality_status: string;
}

export interface ArtifactsResponse {
  job_id: string;
  artifacts: ArtifactItem[];
  message: string | null;
}

export interface QAResponse {
  job_id: string;
  status: "ok" | "warn" | "fail" | "unknown";
  json_files: number;
  excel_files: number;
  has_manifest: boolean;
  manifest_inputs: number;
  manifest_representative: number;
  manifest_diagnostic: number;
  header_key_mismatch: number;
  bad_composite_headers: number;
  quality_warnings: Record<string, number>;
  manifest_domains: Record<string, number>;
  report_path: string | null;
  summary_markdown: string | null;
}

export interface ArtifactPreviewResponse {
  job_id: string;
  artifact_id: string;
  name: string;
  kind: "md" | "json" | "xlsx" | "manifest" | "summary" | "qa" | "other";
  text: string | null;
  json_data: unknown | null;
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  message: string | null;
}

export interface FolderOpenResponse {
  job_id: string;
  path: string;
  opened: boolean;
  message: string;
}

export interface UsageTotals {
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  unknown_token_calls: number;
}

export interface UsageByEngine extends UsageTotals {
  engine: string;
  provider: string;
}

export interface UsageSummaryResponse {
  range: string;
  totals: UsageTotals;
  by_engine: UsageByEngine[];
}

export interface UsageDailyItem {
  date: string;
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

export interface UsageDailyResponse {
  month: string;
  days: UsageDailyItem[];
}

export interface UsageEventItem {
  timestamp: string;
  job_id: string | null;
  engine: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  status: string;
  token_status: string;
}

export interface UsageJobResponse {
  job_id: string;
  totals: UsageTotals;
  events: UsageEventItem[];
}

export interface JobForm {
  files: File[];
  preset: string;
  engine: string;
  pages: string;
  bom_fallback: string;
  no_cache: boolean;
}

// Default to the FastAPI server so preview/static runs do not send API calls to Vite.
const configuredApiBase = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const API_BASE = configuredApiBase.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof body === "object" && body?.error?.message ? body.error.message : "요청 처리 중 오류가 발생했습니다.";
    throw new Error(message);
  }
  return body as T;
}

export function getConfig(): Promise<ConfigResponse> {
  return request<ConfigResponse>("/api/config");
}

export function createJob(form: JobForm): Promise<CreateJobResponse> {
  const data = new FormData();
  const batch = form.files.length > 1;
  for (const file of form.files) {
    data.append(batch ? "files" : "file", file);
  }
  data.append("preset", form.preset);
  data.append("engine", form.engine);
  data.append("pages", form.pages);
  data.append("bom_fallback", form.bom_fallback);
  data.append("no_cache", String(form.no_cache));
  return request<CreateJobResponse>(batch ? "/api/jobs/batch" : "/api/jobs", {
    method: "POST",
    body: data
  });
}

export function getJob(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/api/jobs/${jobId}`);
}

export function getJobs(): Promise<JobsListResponse> {
  return request<JobsListResponse>("/api/jobs");
}

export function cancelJob(jobId: string): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/api/jobs/${jobId}/cancel`, { method: "POST" });
}

export function getArtifacts(jobId: string): Promise<ArtifactsResponse> {
  return request<ArtifactsResponse>(`/api/jobs/${jobId}/artifacts`);
}

export function getQA(jobId: string): Promise<QAResponse> {
  return request<QAResponse>(`/api/jobs/${jobId}/qa`);
}

export function openJobFolder(jobId: string): Promise<FolderOpenResponse> {
  return request<FolderOpenResponse>(`/api/jobs/${jobId}/open-folder`, { method: "POST" });
}

export function getArtifactPreview(jobId: string, artifactId: string): Promise<ArtifactPreviewResponse> {
  return request<ArtifactPreviewResponse>(`/api/jobs/${jobId}/artifacts/${artifactId}/preview`);
}

export function getUsageSummary(range: "today" | "month" | "all" = "all"): Promise<UsageSummaryResponse> {
  return request<UsageSummaryResponse>(`/api/usage/summary?range=${encodeURIComponent(range)}`);
}

export function getUsageDaily(month?: string): Promise<UsageDailyResponse> {
  const suffix = month ? `?month=${encodeURIComponent(month)}` : "";
  return request<UsageDailyResponse>(`/api/usage/daily${suffix}`);
}

export function getUsageForJob(jobId: string): Promise<UsageJobResponse> {
  return request<UsageJobResponse>(`/api/usage/jobs/${jobId}`);
}

export function artifactDownloadUrl(jobId: string, artifactId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/artifacts/${artifactId}`;
}
