import os
import subprocess
import datetime

os.makedirs('conflict_dir', exist_ok=True)

date_str = datetime.datetime.now().strftime('%Y%m%d')
target_path = f'conflict_dir/{date_str}_a.md'
os.makedirs(target_path, exist_ok=True)

print(f'Testing batch with {target_path} blocked by a directory...')
subprocess.run(['python', 'main.py', 'dummy_batch', '--text-only', '--output-dir', 'conflict_dir'])
