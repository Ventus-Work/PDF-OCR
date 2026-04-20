# -*- coding: utf-8 -*-
"""Z.ai 국제판 엔드포인트 + 올바른 모델명 탐색"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import os
from dotenv import load_dotenv
load_dotenv()
from zhipuai import ZhipuAI

key = os.getenv('ZAI_API_KEY')
print(f"KEY: {key[:15]}...")

# z.ai 국제판은 base_url = https://api.z.ai/api/paas/v4/
# open.bigmodel.cn는 중국 본토용
client = ZhipuAI(api_key=key, base_url="https://api.z.ai/api/paas/v4/")

# 1) 텍스트 chat (모델명 확인)
models_to_try = ['glm-4-flash', 'glm-4v', 'glm-4v-flash', 'glm-4-flashx', 'glm-z1-flash']
print("\n[1] 사용 가능 모델 탐색:")
for m in models_to_try:
    try:
        resp = client.chat.completions.create(
            model=m,
            messages=[{'role': 'user', 'content': 'hi'}],
            max_tokens=5
        )
        print(f"  OK  {m}: {resp.choices[0].message.content.strip()}")
    except Exception as e:
        msg = str(e)[:60]
        print(f"  FAIL {m}: {msg}")

# 2) file_parser
print("\n[2] file_parser 해외 차단 여부:")
try:
    import io
    buf = io.BytesIO(b'%PDF-1.4 test')
    resp = client.file_parser.create(file=buf, file_type='pdf', tool_type='zhipu-pro')
    print(f"  task_id={resp.task_id}, msg={resp.message}, ok={resp.success}")
except Exception as e:
    print(f"  FAIL: {e}")

print("\nDone.")
