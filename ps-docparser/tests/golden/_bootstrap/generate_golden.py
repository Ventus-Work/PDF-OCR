import os
import subprocess

root = r"g:\My Drive\엑셀\00. 회사업무\피에스산업\견적자료\02. 이전견적서\00. 창녕공장\고려아연 배관 Support 제작_추가 2차_ 견적서\ps-docparser"
inputs = [
    ("estimate.pdf", "estimate"),
    ("bom.pdf", "bom"),
    ("pumsem.pdf", "pumsem"),
    ("generic.pdf", None)
]

for filename, preset in inputs:
    in_path = os.path.join(root, "tests", "golden", "input", filename)
    out_dir = os.path.join(root, "tests", "golden", "output")
    os.makedirs(out_dir, exist_ok=True)
    
    cmd = ["python", "main.py", in_path, "--output-dir", out_dir]
    
    # We use engine local to avoid API calls and hit rate limits, unless BOM needs zai?
    # Actually wait: let the default engine run except for bom where it defaults to zai.
    # To be safe from Zai overseas error, we might force config or just let it run.
    cmd.extend(["--engine", "local"])
    
    if preset:
        cmd.extend(["--preset", preset])
        cmd.extend(["--output", "excel"]) # mostly we want JSON and Excel
    else:
        cmd.extend(["--output", "md"]) # generic only supports md by default possibly? Or maybe json.

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR on {filename}:\n{result.stderr}")
    else:
        print(f"SUCCESS on {filename}")
        
