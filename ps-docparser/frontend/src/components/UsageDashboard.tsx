import type { UsageDailyResponse, UsageJobResponse, UsageSummaryResponse } from "../api/client";
import { labelEngine } from "../labels";

interface Props {
  summary: UsageSummaryResponse | null;
  daily: UsageDailyResponse | null;
  jobUsage: UsageJobResponse | null;
  loading: boolean;
}

export function UsageDashboard({ summary, daily, jobUsage, loading }: Props) {
  if (loading) {
    return <p className="empty-state">사용량을 불러오는 중입니다.</p>;
  }
  if (!summary) {
    return <p className="empty-state">아직 사용량 데이터가 없습니다.</p>;
  }

  return (
    <div className="usage-dashboard">
      <section className="usage-cards">
        <Metric label="API 호출" value={`${summary.totals.call_count}회`} />
        <Metric label="입력 토큰" value={formatNumber(summary.totals.input_tokens)} />
        <Metric label="출력 토큰" value={formatNumber(summary.totals.output_tokens)} />
        <Metric label="예상 비용" value={`$${summary.totals.estimated_cost_usd.toFixed(4)}`} />
      </section>

      <section className="usage-section">
        <h3>엔진별 누적</h3>
        <div className="table-wrap">
          <table className="preview-table">
            <thead>
              <tr>
                <th>엔진</th>
                <th>호출</th>
                <th>입력 토큰</th>
                <th>출력 토큰</th>
                <th>총 토큰</th>
                <th>미확인 호출</th>
                <th>예상 비용</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_engine.map((item) => (
                <tr key={`${item.provider}-${item.engine}`}>
                  <td>{labelEngine(item.engine)}</td>
                  <td>{item.call_count}</td>
                  <td>{formatNumber(item.input_tokens)}</td>
                  <td>{formatNumber(item.output_tokens)}</td>
                  <td>{formatNumber(item.total_tokens)}</td>
                  <td>{item.unknown_token_calls}</td>
                  <td>${item.estimated_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="usage-section">
        <h3>일별 사용량 {daily ? `(${daily.month})` : ""}</h3>
        {daily && daily.days.length > 0 ? (
          <div className="usage-bars">
            {daily.days.map((day) => (
              <div className="usage-bar" key={day.date}>
                <span>{day.date}</span>
                <strong>{formatNumber(day.total_tokens)} tokens</strong>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state compact">이번 달 사용량이 없습니다.</p>
        )}
      </section>

      <section className="usage-section">
        <h3>현재 작업 사용량</h3>
        {jobUsage && jobUsage.events.length > 0 ? (
          <div className="table-wrap">
            <table className="preview-table">
              <thead>
                <tr>
                  <th>시간</th>
                  <th>엔진</th>
                  <th>모델</th>
                  <th>총 토큰</th>
                  <th>상태</th>
                </tr>
              </thead>
              <tbody>
                {jobUsage.events.map((event) => (
                  <tr key={`${event.timestamp}-${event.engine}-${event.total_tokens}`}>
                    <td>{event.timestamp}</td>
                    <td>{labelEngine(event.engine)}</td>
                    <td>{event.model}</td>
                    <td>{formatNumber(event.total_tokens)}</td>
                    <td>{event.token_status === "unknown" ? "토큰 미확인" : "정상"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-state compact">현재 선택한 작업의 사용량 기록이 없습니다.</p>
        )}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("ko-KR").format(value);
}
