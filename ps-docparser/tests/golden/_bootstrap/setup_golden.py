import os
import glob
import shutil

root = r"g:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서"
in_dir = os.path.join(root, "00_견적서_원본")
out_dir = os.path.join(root, "ps-docparser", "tests", "golden", "input")
os.makedirs(out_dir, exist_ok=True)

pdf1 = os.path.join(in_dir, "고려아연 배관 Support 제작_추가_2차분 견적서.pdf")
pdf2 = os.path.join(in_dir, "아연도금강판 견적서.pdf")

if os.path.exists(pdf1):
    shutil.copy2(pdf1, os.path.join(out_dir, "estimate.pdf"))
    shutil.copy2(pdf1, os.path.join(out_dir, "bom.pdf"))
    shutil.copy2(pdf1, os.path.join(out_dir, "pumsem.pdf"))
if os.path.exists(pdf2):
    shutil.copy2(pdf2, os.path.join(out_dir, "generic.pdf"))

print(f"Files in {out_dir}:")
print(os.listdir(out_dir))
