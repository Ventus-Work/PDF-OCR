from __future__ import annotations

from fastapi.testclient import TestClient
from openpyxl import Workbook

from api.app import create_app
from api.artifacts import encode_artifact_id
from api.jobs import JobManager
from utils.usage_store import UsageStore, default_usage_db


def make_client(tmp_path, *, project_root=None):
    manager = JobManager(
        base_output_dir=tmp_path / "ui_runs",
        project_root=project_root or tmp_path / "project",
        auto_start=False,
        enable_open_folder=False,
    )
    return TestClient(create_app(manager)), manager


def test_get_config_returns_phase15_options(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert data["presets"] == ["auto", "generic", "bom", "estimate", "pumsem"]
    assert data["engines"] == ["auto", "zai", "gemini", "local", "mistral", "tesseract"]
    assert data["defaults"]["engine"] == "auto"
    assert data["defaults"]["output_format"] == "excel"


def test_create_job_rejects_non_pdf(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("note.txt", b"hello", "text/plain")},
        data={"preset": "auto", "engine": "zai"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_upload"


def test_create_and_get_queued_job(tmp_path):
    client, manager = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"preset": "bom", "engine": "zai", "pages": "1-10", "bom_fallback": "never", "no_cache": "true"},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "queued"
    assert created["status_url"] == f"/api/jobs/{created['job_id']}"

    stored = manager.get_job(created["job_id"])
    assert stored.input_path.exists()
    assert stored.preset == "bom"
    assert stored.pages == "1-10"
    assert stored.bom_fallback == "never"
    assert stored.no_cache is True

    status_response = client.get(created["status_url"])
    assert status_response.status_code == 200
    assert status_response.json()["job_id"] == created["job_id"]
    assert status_response.json()["requested_engine"] == "zai"


def test_create_batch_job_accepts_multiple_pdfs(tmp_path):
    client, manager = make_client(tmp_path)

    response = client.post(
        "/api/jobs/batch",
        files=[
            ("files", ("a.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")),
            ("files", ("b.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")),
        ],
        data={"preset": "generic", "engine": "auto"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["input_count"] == 2
    stored = manager.get_job(data["job_id"])
    assert stored.input_path.is_dir()
    assert len(list(stored.input_path.glob("*.pdf"))) == 2


def test_list_jobs_returns_recent_jobs(tmp_path):
    client, _ = make_client(tmp_path)
    client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    response = client.get("/api/jobs")

    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 1


def test_missing_job_returns_structured_error(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/api/jobs/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "job_not_found"


def test_cancel_queued_job(tmp_path):
    client, _ = make_client(tmp_path)
    created = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()

    response = client.post(f"/api/jobs/{created['job_id']}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"


def test_open_folder_returns_safe_job_folder(tmp_path):
    client, _ = make_client(tmp_path)
    created = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()

    response = client.post(f"/api/jobs/{created['job_id']}/open-folder")

    assert response.status_code == 200
    assert response.json()["opened"] is False
    assert created["job_id"] in response.json()["path"]


def test_create_job_accepts_auto_engine(tmp_path):
    client, manager = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"preset": "auto", "engine": "auto"},
    )

    assert response.status_code == 201
    stored = manager.get_job(response.json()["job_id"])
    assert stored.engine == "auto"


def test_create_job_rejects_invalid_pages(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"pages": "5-3"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_pages"


def test_preview_json_artifact(tmp_path):
    client, manager = make_client(tmp_path)
    created = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()
    record = manager.get_job(created["job_id"])
    artifact = record.result_dir / "result.json"
    artifact.write_text('{"hello": "world"}', encoding="utf-8")

    response = client.get(f"/api/jobs/{record.job_id}/artifacts/{encode_artifact_id('result.json')}/preview")

    assert response.status_code == 200
    assert response.json()["kind"] == "json"
    assert response.json()["json_data"] == {"hello": "world"}


def test_preview_markdown_artifact(tmp_path):
    client, manager = make_client(tmp_path)
    created = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()
    record = manager.get_job(created["job_id"])
    artifact = record.result_dir / "result.md"
    artifact.write_text("# 제목\n본문", encoding="utf-8")

    response = client.get(f"/api/jobs/{record.job_id}/artifacts/{encode_artifact_id('result.md')}/preview")

    assert response.status_code == 200
    assert response.json()["text"].startswith("# 제목")


def test_preview_xlsx_artifact(tmp_path):
    client, manager = make_client(tmp_path)
    created = client.post(
        "/api/jobs",
        files={"file": ("sample.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    ).json()
    record = manager.get_job(created["job_id"])
    artifact = record.result_dir / "result.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["품명", "수량"])
    ws.append(["판넬", 3])
    wb.save(artifact)

    response = client.get(f"/api/jobs/{record.job_id}/artifacts/{encode_artifact_id('result.xlsx')}/preview")

    assert response.status_code == 200
    assert response.json()["columns"] == ["품명", "수량"]
    assert response.json()["rows"] == [["판넬", 3]]


def test_usage_summary_endpoint_reads_usage_db(tmp_path):
    project_root = tmp_path / "project"
    UsageStore(default_usage_db(project_root)).record_event(
        job_id="job-1",
        engine="gemini",
        provider="gemini",
        model="gemini-2.0-flash",
        input_tokens=100,
        output_tokens=50,
        estimated_cost_usd=0.001,
    )
    client, _ = make_client(tmp_path, project_root=project_root)

    summary = client.get("/api/usage/summary?range=all")
    daily = client.get("/api/usage/daily")
    job = client.get("/api/usage/jobs/job-1")

    assert summary.status_code == 200
    assert summary.json()["totals"]["total_tokens"] == 150
    assert daily.status_code == 200
    assert len(daily.json()["days"]) == 1
    assert job.status_code == 200
    assert job.json()["totals"]["call_count"] == 1
