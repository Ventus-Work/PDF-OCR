import json
from parsers.table_parser import process_section_tables

with open('output/20260422_260421_견적(R0)_대산 HD현대오일뱅크 10TON CRANE 설치_bom.md', 'r', encoding='utf-8') as f:
    text = f.read()

section = {'raw_text': text, 'section_id': 'BOM-1', 'title': 'Test'}
result = process_section_tables(section)

print(f"Found {len(result['tables'])} tables.")
for t in result['tables']:
    print(f"Type: {t['type']}")
    print(f"Headers: {t['headers']}")
    if t['rows']:
        print(f"Rows 0: {json.dumps(t['rows'][0], ensure_ascii=False)}")
