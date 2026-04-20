import sys, os, glob

sys.stdout.reconfigure(encoding='cp949', errors='backslashreplace')
root = r"g:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서"
doc_dir = os.path.join(root, "ps-docparser")

with open(os.path.join(doc_dir, 'pytest_full_output.txt'), 'r', encoding='utf-8') as f:
    print(f.read())

print('\n===Golden===')
out_dir = os.path.join(doc_dir, 'tests', 'golden', 'output')
for f in glob.glob(os.path.join(out_dir, '*')):
    print(os.path.basename(f), os.path.getsize(f))
