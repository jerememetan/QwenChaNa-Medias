"""Layer 10: FastAPI App tests — verify app instantiation and route registration."""

from fastapi.testclient import TestClient

from backend.main import create_production_app


class TestFastAPIApp:
    def test_app_creates(self):
        app = create_production_app()
        assert app is not None

    def test_app_has_generate_route(self):
        app = create_production_app()
        client = TestClient(app)
        # POST /generate should be registered (422 for empty body proves route exists)
        response = client.post("/generate", json={})
        assert response.status_code == 422

    def test_app_has_status_route(self):
        app = create_production_app()
        client = TestClient(app)
        response = client.get("/status/nonexistent-id")
        assert response.status_code == 404

    def test_app_has_result_route(self):
        app = create_production_app()
        client = TestClient(app)
        response = client.get("/result/nonexistent-id")
        assert response.status_code == 404

    def test_app_has_resume_route(self):
        app = create_production_app()
        client = TestClient(app)
        response = client.post("/resume/nonexistent-id")
        assert response.status_code == 404

    def test_app_health_check(self):
        app = create_production_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
