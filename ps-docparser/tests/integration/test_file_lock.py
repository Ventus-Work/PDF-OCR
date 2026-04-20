"""병합된 Lock 테스트 (test_file_lock.py)"""


# --- From test_lock.py ---
import time
import subprocess
import os
import datetime
import msvcrt

os.makedirs('output', exist_ok=True)
date_str = datetime.datetime.now().strftime('%Y%m%d')
target_md = f'output/{date_str}_b.md'

with open(target_md, 'w') as f:
    f.write('locked')
    f.flush()
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    
    print('Testing batch with b.md locked...')
    subprocess.run(['python', 'main.py', 'dummy_batch', '--text-only'])

    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

print('Test complete.')


# --- From test_excel_lock.py ---
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from exporters.excel_exporter import ExcelExporter
import msvcrt

target_xlsx = Path("dummy_output.xlsx")
target_xlsx.touch(exist_ok=True)

with open(target_xlsx, 'a') as f:
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        print(f"Testing direct Excel export with locked file: {target_xlsx}")
        ExcelExporter().export([{"title": "test", "tables": []}], target_xlsx)
    except Exception as e:
        print(f"\nCaught Exception during Excel export:\n{type(e).__name__}: {e}")
    finally:
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


# --- From test_folder_lock.py ---
import os
import stat
import subprocess

# Ensure dummy_batch has at least one PDF
os.makedirs('dummy_batch', exist_ok=True)
if not os.path.exists('dummy_batch/c.pdf'):
    import shutil
    shutil.copy('../아연도금강판 견적서.pdf', 'dummy_batch/c.pdf')

os.makedirs('readonly_dir', exist_ok=True)
os.chmod('readonly_dir', stat.S_IREAD) # Create a read-only folder to trigger PermissionError on _safe_write_text

try:
    print('Testing batch with readonly output dir...')
    subprocess.run(['python', 'main.py', 'dummy_batch', '--text-only', '--output-dir', 'readonly_dir'])
finally:
    os.chmod('readonly_dir', stat.S_IWRITE)

