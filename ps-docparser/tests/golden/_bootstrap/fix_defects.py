import os
import glob
import shutil
import subprocess

root = r"g:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서"
doc_dir = os.path.join(root, "ps-docparser")
git_dir = os.path.join(root, ".git")

print("--- Step A: Cleaning git refs & scripts ---")
for r, d, files in os.walk(git_dir):
    for f in files:
        if "{" in f and "}" in f:
            target = os.path.join(r, f)
            try:
                os.remove(target)
                print("Removed broken ref:", target)
            except Exception as e:
                print("Error removing", target, e)

boot_dir = os.path.join(doc_dir, "tests", "golden", "_bootstrap")
os.makedirs(boot_dir, exist_ok=True)
for script in ["generate_golden.py", "setup_golden.py", "git_tags.py", "fix_defects.py"]:
    src = os.path.join(doc_dir, script)
    if os.path.exists(src):
        try:
            shutil.move(src, os.path.join(boot_dir, script))
            print("Moved:", script)
        except Exception:
            pass

print("--- Step B: Recollecting samples ---")
inputs_dir = os.path.join(doc_dir, "tests", "golden", "input")
bom_src = os.path.join(root, "00_견적서_원본", "53-83 OKOK.pdf")
estimate_src = os.path.join(root, "00_견적서_원본", "고려아연 배관 Support 제작_추가_2차분 견적서.pdf")
generic_src = os.path.join(doc_dir, "tests", "fixtures", "sample_markdowns", "simple_estimate.md")

for p in ["generic.pdf", "pumsem.pdf", "bom.pdf"]:
    fpath = os.path.join(inputs_dir, p)
    if os.path.exists(fpath):
        os.remove(fpath)

if os.path.exists(bom_src):
    shutil.copy2(bom_src, os.path.join(inputs_dir, "bom.pdf"))
else:
    print("bom_src not found:", bom_src)

if os.path.exists(generic_src):
    shutil.copy2(generic_src, os.path.join(inputs_dir, "generic.md"))
else:
    print("generic_src not found:", generic_src)

print("--- Step C: Generating Golden ---")
out_dir = os.path.join(doc_dir, "tests", "golden", "output")
if os.path.exists(out_dir):
    shutil.rmtree(out_dir)
os.makedirs(out_dir, exist_ok=True)

subprocess.run(["python", "main.py", os.path.join(inputs_dir, "bom.pdf"), "--preset", "bom", "--engine", "local", "--output", "excel", "--output-dir", out_dir], cwd=doc_dir)
subprocess.run(["python", "main.py", os.path.join(inputs_dir, "estimate.pdf"), "--preset", "estimate", "--engine", "local", "--output", "excel", "--output-dir", out_dir], cwd=doc_dir)
subprocess.run(["python", "main.py", os.path.join(inputs_dir, "generic.md"), "--output", "md", "--output-dir", out_dir], cwd=doc_dir)

print("--- Step D: Pytest Capture ---")
res = subprocess.run(["pytest"], cwd=doc_dir, capture_output=True, text=True)
with open(os.path.join(doc_dir, "pytest_full_output.log"), "w", encoding="utf-8") as f:
    f.write(res.stdout)
    if res.stderr:
        f.write("\nSTDERR:\n" + res.stderr)

print("Done. Check pytest_full_output.log")
