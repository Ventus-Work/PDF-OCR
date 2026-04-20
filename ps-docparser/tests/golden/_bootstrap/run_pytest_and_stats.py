import subprocess, glob, os

root = r"g:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서"
doc_dir = os.path.join(root, "ps-docparser")

res = subprocess.run(["pytest", "-v", "--tb=short"], cwd=doc_dir, capture_output=True, encoding="utf-8", errors="backslashreplace")

with open(os.path.join(doc_dir, 'pytest_actual_log.txt'), 'w', encoding='utf-8') as f:
    f.write(res.stdout)
    if res.stderr:
        f.write("\n" + res.stderr)

print("pytest summary:")
lines = res.stdout.splitlines()
print("\n".join(lines[-20:]))

print("\n--- Golden Files ---")
out_dir = os.path.join(doc_dir, 'tests', 'golden', 'output')
for f in glob.glob(os.path.join(out_dir, '*')):
    print(os.path.basename(f), os.path.getsize(f))
