from __future__ import annotations

import re

import pytest

from api.errors import ApiError
from api.jobs import JobManager, normalize_pages, sanitize_filename
from api.schemas import JobOptions


def test_sanitize_filename_keeps_pdf_suffix():
    assert sanitize_filename("../견적서?.pdf").endswith(".pdf")
    assert "/" not in sanitize_filename("../견적서?.pdf")


def test_job_id_format_and_directories(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)

    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(),
    )

    assert re.match(r"^ui_\d{8}_\d{6}_[0-9a-f]{8}$", record.job_id)
    assert record.input_path.exists()
    assert record.result_dir.exists()
    assert record.stdout_log.parent.exists()


def test_build_cli_command_for_auto_preset(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="auto", engine="local", pages="1-3", no_cache=True),
    )

    command = manager.build_cli_command(record)

    assert "--preset" not in command
    assert command[command.index("--engine") + 1] == "local"
    assert command[command.index("--pages") + 1] == "1-3"
    assert "--no-cache" in command


def test_build_cli_command_for_auto_engine_omits_engine_flag(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="auto", engine="auto"),
    )

    command = manager.build_cli_command(record)

    assert "--engine" not in command


def test_build_cli_command_for_bom_fallback(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="bom", engine="zai", bom_fallback="always"),
    )

    command = manager.build_cli_command(record)

    assert command[command.index("--preset") + 1] == "bom"
    assert command[command.index("--bom-fallback") + 1] == "always"


def test_build_cli_command_for_generic_preset(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="generic", engine="auto", bom_fallback="never"),
    )

    command = manager.build_cli_command(record)

    assert command[command.index("--preset") + 1] == "generic"
    assert "--bom-fallback" not in command


def test_build_cli_command_for_auto_preset_passes_non_default_bom_fallback(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="auto", engine="auto", bom_fallback="never"),
    )

    command = manager.build_cli_command(record)

    assert "--preset" not in command
    assert command[command.index("--bom-fallback") + 1] == "never"


def test_status_file_can_restore_completed_job(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    record = manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(preset="generic"),
    )
    record.status = "succeeded"
    record.cli_exit_code = 0
    record.analyzer_exit_code = 0
    record.exit_code = 0
    manager._save_status(record)

    restored_manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False)
    restored = restored_manager.get_job(record.job_id)

    assert restored.status == "succeeded"
    assert restored.cli_exit_code == 0
    assert restored.analyzer_exit_code == 0


def test_capacity_limit_rejects_too_many_queued_jobs(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False, max_queued_jobs=1)
    manager.create_job(
        filename="sample.pdf",
        content=b"%PDF-1.4\n%%EOF",
        options=JobOptions(),
    )

    with pytest.raises(ApiError) as exc_info:
        manager.create_job(
            filename="sample2.pdf",
            content=b"%PDF-1.4\n%%EOF",
            options=JobOptions(),
        )

    assert exc_info.value.code == "queue_full"


def test_upload_size_limit_rejects_large_file(tmp_path):
    manager = JobManager(base_output_dir=tmp_path / "ui_runs", auto_start=False, max_upload_mb=0)

    with pytest.raises(ApiError) as exc_info:
        manager.create_job(
            filename="sample.pdf",
            content=b"%PDF-1.4\n%%EOF",
            options=JobOptions(),
        )

    assert exc_info.value.code == "upload_too_large"


def test_normalize_pages_rejects_invalid_range():
    with pytest.raises(ApiError):
        normalize_pages("5-3")


def test_normalize_pages_canonicalizes_spaces():
    assert normalize_pages("1, 3, 5-10") == "1,3,5-10"
