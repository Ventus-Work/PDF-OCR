"""Run a small real-PDF regression suite into a timestamped output folder."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.run_manifest import write_run_summary

DEFAULT_CASES = [
    {
        "name": "bom_mixed_260421",
        "files": ["260421_견적(R0)_대산 HD현대오일뱅크 10TON CRANE 설치.pdf"],
        "args": ["--preset", "bom", "--output", "excel"],
    },
    {
        "name": "bom_pipe_fp",
        "files": [f"PIPE-FP-PS-{num}-S1-R1.pdf" for num in range(5007, 5014)],
        "args": ["--preset", "bom", "--output", "excel"],
    },
    {
        "name": "pumsem_53_83_p1_10",
        "files": ["53-83 OKOK.pdf"],
        "args": ["--preset", "pumsem", "--pages", "1-10", "--output", "excel"],
    },
    {
        "name": "estimate_samples",
        "files": [
            "고려아연 배관 Support 제작_추가_2차분 견적서.pdf",
            "260325_ SC WALL 잡철물 제작_추가 견적서R2.pdf",
        ],
        "args": ["--preset", "estimate", "--output", "excel"],
    },
]

CASE_SETS = {
    "20260424_bom_backend": DEFAULT_CASES,
}


def _run_case(pdf: Path, output_dir: Path, engine: str, extra_args: list[str]) -> int:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "main.py"),
        str(pdf),
        "--engine",
        engine,
        "--output-dir",
        str(output_dir),
        *extra_args,
    ]
    print(" ".join(cmd))
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return completed.returncode


def _prefix_artifact_paths(artifact: dict[str, Any], case_name: str) -> dict[str, Any]:
    prefixed = dict(artifact)
    for key in ("md", "json", "xlsx"):
        value = prefixed.get(key)
        if not value:
            continue
        path = Path(str(value))
        if path.is_absolute():
            continue
        prefixed[key] = str(Path(case_name) / path)
    return prefixed


def _write_suite_manifest(run_root: Path) -> Path:
    inputs: list[dict[str, Any]] = []
    seen_jsons: set[str] = set()
    for manifest_path in sorted(run_root.glob("*/RUN_MANIFEST.json")):
        case_name = manifest_path.parent.name
        try:
            case_manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue

        for entry in case_manifest.get("inputs", []):
            suite_entry = dict(entry)
            suite_entry["case"] = case_name
            if isinstance(suite_entry.get("primary"), dict):
                suite_entry["primary"] = _prefix_artifact_paths(
                    suite_entry["primary"],
                    case_name,
                )
                rel_json = suite_entry["primary"].get("json")
                if rel_json:
                    seen_jsons.add(str(Path(rel_json)))
            diagnostics = []
            for diagnostic in suite_entry.get("diagnostics", []) or []:
                if isinstance(diagnostic, dict):
                    prefixed = _prefix_artifact_paths(diagnostic, case_name)
                    rel_json = prefixed.get("json")
                    if rel_json:
                        seen_jsons.add(str(Path(rel_json)))
                    diagnostics.append(prefixed)
            suite_entry["diagnostics"] = diagnostics
            inputs.append(suite_entry)

    for json_path in sorted(run_root.rglob("*.json")):
        if json_path.name in {"RUN_MANIFEST.json", "route_manifest.json"}:
            continue
        rel_json = json_path.relative_to(run_root)
        if str(rel_json) in seen_jsons:
            continue

        case_name = rel_json.parts[0] if len(rel_json.parts) > 1 else ""
        domain = "generic"
        if "pumsem" in case_name:
            domain = "pumsem"
        elif "estimate" in case_name:
            domain = "estimate"
        elif json_path.name.endswith("_bom.json"):
            domain = "bom"

        md_path = json_path.with_suffix(".md")
        xlsx_path = json_path.with_suffix(".xlsx")
        inputs.append(
            {
                "case": case_name,
                "source_pdf": json_path.stem,
                "preset": domain,
                "status": "success",
                "primary": {
                    "kind": "output",
                    "role": "representative",
                    "domain": domain,
                    "md": str(md_path.relative_to(run_root)) if md_path.exists() else None,
                    "json": str(rel_json),
                    "xlsx": str(xlsx_path.relative_to(run_root)) if xlsx_path.exists() else None,
                    "quality_status": "ok",
                },
                "diagnostics": [],
            }
        )

    manifest = {
        "run_id": run_root.name,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "inputs": inputs,
    }
    manifest_path = run_root / "RUN_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_run_summary(run_root, manifest)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real PDF suite.")
    parser.add_argument(
        "--input-root",
        type=Path,
        default=PROJECT_ROOT.parent / "00_견적서_원본",
    )
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "output")
    parser.add_argument("--engine", default="zai")
    parser.add_argument(
        "--case-set",
        choices=sorted(CASE_SETS),
        default="20260424_bom_backend",
    )
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    run_id = args.run_id or f"실측테스트_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_root = args.output_root / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for case in CASE_SETS[args.case_set]:
        case_dir = run_root / case["name"]
        case_dir.mkdir(parents=True, exist_ok=True)
        for filename in case["files"]:
            pdf = args.input_root / filename
            if not pdf.exists():
                print(f"SKIP missing: {pdf}")
                continue
            code = _run_case(pdf, case_dir, args.engine, case["args"])
            if code != 0:
                failures.append(f"{filename}: exit {code}")

    _write_suite_manifest(run_root)

    analyzer = PROJECT_ROOT / "tools" / "analyze_outputs.py"
    subprocess.run([sys.executable, str(analyzer), str(run_root)], cwd=PROJECT_ROOT)

    if failures:
        print("Failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"Run output: {run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
