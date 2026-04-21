"""
scripts/zai_api_check.py — ZAI API 연결 및 모델 가용성 수동 확인

실행: python scripts/zai_api_check.py
목적:
    z.ai 국제판 엔드포인트와 실제 API 키로 연결을 확인한다.
    API 비용이 발생하므로 자동화 CI에서는 실행하지 않는다.
    pytest --run-api 마커로도 실행 가능하다.

확인 항목:
    [1] 텍스트 Chat 모델 가용성 탐색 (glm-4-flash 등)
    [2] file_parser 엔드포인트 해외 차단 여부
"""

import sys
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from zhipuai import ZhipuAI

key = os.getenv("ZAI_API_KEY")
if not key:
    print("[ERROR] ZAI_API_KEY 미설정 — .env에 ZAI_API_KEY=... 추가 필요")
    sys.exit(1)

print(f"KEY: {key[:15]}...")

client = ZhipuAI(api_key=key, base_url="https://api.z.ai/api/paas/v4/")

models_to_try = ["glm-4-flash", "glm-4v", "glm-4v-flash", "glm-4-flashx", "glm-z1-flash"]
print("\n[1] 사용 가능 모델 탐색:")
for m in models_to_try:
    try:
        resp = client.chat.completions.create(
            model=m,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5
        )
        print(f"  OK  {m}: {resp.choices[0].message.content.strip()}")
    except Exception as e:
        print(f"  FAIL {m}: {str(e)[:60]}")

print("\n[2] file_parser 해외 차단 여부:")
try:
    import io
    buf = io.BytesIO(b"%PDF-1.4 test")
    resp = client.file_parser.create(file=buf, file_type="pdf", tool_type="zhipu-pro")
    print(f"  task_id={resp.task_id}, msg={resp.message}, ok={resp.success}")
except Exception as e:
    print(f"  FAIL: {e}")

print("\nDone.")
