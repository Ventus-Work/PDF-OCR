import os

files = [
    'tests/integration/test_lock.py',
    'tests/integration/test_excel_lock.py',
    'tests/integration/test_folder_lock.py'
]

merged_content = '\"\"\"병합된 Lock 테스트 (test_file_lock.py)\"\"\"\n\n'

for f in files:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as file:
            merged_content += f'\n# --- From {os.path.basename(f)} ---\n'
            merged_content += file.read() + '\n'
        os.remove(f)

with open('tests/integration/test_file_lock.py', 'w', encoding='utf-8') as out:
    out.write(merged_content)
