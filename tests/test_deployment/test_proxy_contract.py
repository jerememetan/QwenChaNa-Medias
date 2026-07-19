from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_keeps_app_private_and_persists_outputs() -> None:
    compose = read_repo_file("compose.yaml")

    assert "./outputs:/app/outputs" in compose
    assert "./.env:/app/.env:ro" not in compose
    assert '"8000:8000"' not in compose
    assert '"80:80"' in compose
    assert "condition: service_healthy" in compose
    assert "restart: unless-stopped" in compose


def test_nginx_allows_long_generation_requests() -> None:
    nginx = read_repo_file("deploy/nginx.conf")

    assert "server app:8000" in nginx
    assert "proxy_read_timeout 3600s" in nginx
    assert "proxy_send_timeout 3600s" in nginx
    assert "proxy_buffering off" in nginx
    assert "proxy_set_header X-Forwarded-For" in nginx
