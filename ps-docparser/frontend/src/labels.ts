export function labelPreset(value: string): string {
  return (
    {
      auto: "자동",
      generic: "범용",
      bom: "BOM 도면",
      estimate: "견적서",
      pumsem: "품셈"
    }[value] ?? value
  );
}

export function labelEngine(value: string): string {
  return (
    {
      auto: "자동",
      zai: "Z.ai",
      gemini: "Gemini",
      local: "로컬",
      mistral: "Mistral",
      tesseract: "Tesseract"
    }[value] ?? value
  );
}

export function labelFallback(value: string): string {
  return (
    {
      auto: "자동",
      always: "항상 생성",
      never: "생성 안 함"
    }[value] ?? value
  );
}

export function labelStatus(value: string): string {
  return (
    {
      queued: "대기",
      running: "실행 중",
      succeeded: "성공",
      failed: "실패",
      canceled: "취소됨",
      ok: "정상",
      warn: "주의",
      fail: "실패",
      unknown: "알 수 없음"
    }[value] ?? value
  );
}

export function labelArtifactKind(value: string): string {
  return (
    {
      md: "마크다운",
      json: "JSON",
      xlsx: "Excel",
      manifest: "매니페스트",
      summary: "요약",
      qa: "QA",
      other: "기타"
    }[value] ?? value
  );
}

export function labelRole(value: string): string {
  return (
    {
      representative: "대표본",
      diagnostic: "진단본",
      compare: "비교본",
      unknown: "미분류"
    }[value] ?? value
  );
}

export function labelDomain(value: string): string {
  return (
    {
      bom: "BOM",
      estimate: "견적서",
      pumsem: "품셈",
      trade_statement: "거래명세",
      generic: "일반",
      unknown: "미분류"
    }[value] ?? value
  );
}

export function labelQuality(value: string): string {
  return (
    {
      ok: "정상",
      warning: "주의",
      warn: "주의",
      fail: "실패",
      unknown: "미확인"
    }[value] ?? value
  );
}
