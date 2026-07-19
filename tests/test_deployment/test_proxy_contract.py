from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_keeps_app_private_and_persists_outputs() -> None:
    compose = yaml.safe_load(read_repo_file("compose.yaml"))
    app = compose["services"]["app"]
    nginx = compose["services"]["nginx"]

    assert "ports" not in app
    assert app["expose"] == ["8000"]
    assert app["volumes"] == [
        {
            "type": "bind",
            "source": "./outputs",
            "target": "/app/outputs",
            "bind": {"create_host_path": False},
        }
    ]
    assert nginx["ports"] == ["80:80"]
    assert nginx["depends_on"]["app"] == {
        "condition": "service_healthy",
        "restart": True,
    }
    assert app["restart"] == "unless-stopped"
    assert nginx["restart"] == "unless-stopped"
    assert (
        nginx["image"]
        == "nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236"
    )


def test_nginx_limits_generation_requests_and_allows_long_streams() -> None:
    nginx = read_repo_file("deploy/nginx.conf")

    assert "server app:8000" in nginx
    assert "limit_req_zone $binary_remote_addr zone=generate_per_client:10m rate=2r/m;" in nginx
    assert "limit_conn_zone $server_name zone=generate_concurrency:10m;" in nginx
    assert "location = /generate {" in nginx
    assert "limit_req zone=generate_per_client burst=1 nodelay;" in nginx
    assert "limit_conn generate_concurrency 1;" in nginx
    assert "proxy_read_timeout 3600s" in nginx
    assert "proxy_send_timeout 3600s" in nginx
    assert "send_timeout 3600s" in nginx
    assert "proxy_buffering off" in nginx
    assert "proxy_set_header Host $host;" in nginx
    assert "proxy_set_header X-Real-IP $remote_addr;" in nginx
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in nginx
