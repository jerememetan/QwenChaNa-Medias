from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dockerfile_builds_frontend_and_runs_one_app_worker() -> None:
    dockerfile = read_repo_file("Dockerfile")

    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "COPY --from=frontend-build" in dockerfile
    assert 'USER app' in dockerfile
    assert '"backend.main:app"' in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_dockerignore_excludes_secrets_and_generated_files() -> None:
    ignored = set(read_repo_file(".dockerignore").splitlines())

    assert ".env" in ignored
    assert ".env.*" in ignored
    assert "outputs/" in ignored
    assert ".git/" in ignored
    assert "venv/" in ignored
    assert "frontend/node_modules/" in ignored
