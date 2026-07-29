from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import time
from urllib.request import urlopen
from uuid import uuid4

import pytest


ROOT = Path(__file__).parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text()
LOCK = (ROOT / "requirements.production.lock").read_text()


def _docker_daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def _remove_appledouble_files() -> None:
    """Keep macOS metadata out of Docker's build-context xattr traversal."""

    for path in ROOT.rglob("._*"):
        if path.is_file():
            path.unlink()


def test_production_container_contract_is_locked_non_root_and_fixture_only() -> None:
    assert "FROM python:3.12.6-slim-bookworm" in DOCKERFILE
    assert "requirements.production.lock" in DOCKERFILE
    assert "pip install --no-deps" in DOCKERFILE
    assert "COPY fixtures/sec ./fixtures/sec" in DOCKERFILE
    assert "USER quantify" in DOCKERFILE
    assert "chmod -R a=rX /app" in DOCKERFILE
    assert "--factory quantify.production:create_production_app" in DOCKERFILE
    assert "--port ${PORT}" in DOCKERFILE
    assert "--workers 1" in DOCKERFILE
    assert "--proxy-headers" in DOCKERFILE
    assert "uvicorn==0.30.6" in LOCK
    assert "fastapi==0.140.13" in LOCK
    assert "pyarrow==19.0.1" in LOCK


def test_container_build_context_excludes_credentials_and_private_artifacts() -> None:
    for rule in (".env", ".env.*", ".quantify-private/", "._*"):
        assert rule in DOCKERIGNORE


@pytest.mark.skipif(
    not _docker_daemon_available(), reason="Docker daemon is not available"
)
def test_built_container_runs_non_root_and_serves_healthz() -> None:
    """Build/run smoke test for CI or a local machine with Docker running."""

    tag = f"quantify-container-test:{uuid4().hex}"
    container_id = ""
    try:
        _remove_appledouble_files()
        subprocess.run(
            ["docker", "build", "--tag", tag, "."],
            cwd=ROOT,
            check=True,
        )
        uid = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "id", tag, "-u"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert uid == "10001"
        container_id = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--detach",
                "--publish",
                "127.0.0.1::8080",
                "--env",
                "GEMINI_API_KEY=container-test-key",
                "--env",
                "QUANTIFY_IMAGE_DIGEST=sha256:container-test",
                tag,
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        port = subprocess.run(
            ["docker", "port", container_id, "8080/tcp"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip().rsplit(":", 1)[1]
        deadline = time.monotonic() + 20
        while True:
            try:
                with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:  # noqa: S310
                    assert json.loads(response.read()) == {"status": "ok"}
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
    finally:
        if container_id:
            subprocess.run(["docker", "stop", container_id], check=False)
        subprocess.run(["docker", "image", "rm", "--force", tag], check=False)
