import os, glob, shutil, subprocess

root = r"g:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장"
doc_dir = os.path.join(root, "고려아연 배관 Support 제작_추가 2차_ 견적서", "ps-docparser")
inputs_dir = os.path.join(doc_dir, "tests", "golden", "input")
out_dir = os.path.join(doc_dir, "tests", "golden", "output")

bom_src = None
for f in glob.glob(os.path.join(root, '**', '53-83 OKOK.pdf'), recursive=True):
    bom_src = f
    break

if bom_src:
    print("Found BOM:", bom_src)
    os.makedirs(inputs_dir, exist_ok=True)
    shutil.copy2(bom_src, os.path.join(inputs_dir, "bom.pdf"))
    
    # Run main.py
    subprocess.run(["python", "main.py", os.path.join(inputs_dir, "bom.pdf"), "--preset", "bom", "--engine", "local", "--output", "excel", "--output-dir", out_dir], cwd=doc_dir)
    
    # Run pytest again
    print("Running pytest again...")
    res = subprocess.run(["pytest"], cwd=doc_dir, capture_output=True, text=True)
    with open(os.path.join(doc_dir, "pytest_full_output.log"), "w", encoding="utf-8") as f:
        f.write(res.stdout)
        if res.stderr: f.write("\nSTDERR:\n"+res.stderr)
    print("Done")
else:
    print("bom_src not found via glob")
