import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_generate_returns_202_with_job_id(client: TestClient) -> None:
    response = client.post("/generate", json={"prompt": "A short test prompt"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"]
    assert payload["status"] == "pending"
    assert "placeholder" in payload["message"].lower()


def test_generate_rejects_empty_prompt(client: TestClient) -> None:
    response = client.post("/generate", json={"prompt": "   "})

    assert response.status_code == 422


def test_status_endpoint_returns_known_job(client: TestClient) -> None:
    created = client.post("/generate", json={"prompt": "Another prompt"})
    job_id = created.json()["job_id"]

    response = client.get(f"/status/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "pending"


def test_result_endpoint_returns_placeholder_response(client: TestClient) -> None:
    created = client.post("/generate", json={"prompt": "Prompt for result"})
    job_id = created.json()["job_id"]

    response = client.get(f"/result/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "pending"


def test_resume_endpoint_returns_placeholder_response(client: TestClient) -> None:
    created = client.post("/generate", json={"prompt": "Prompt for resume"})
    job_id = created.json()["job_id"]

    response = client.post(f"/resume/{job_id}")

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == job_id
    assert "placeholder" in payload["message"].lower()
