from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
DEPLOYMENT = ROOT / "deploy" / "cloudrun"


def _read(name: str) -> str:
    return (DEPLOYMENT / name).read_text()


def test_staging_configuration_pins_immutable_image_secret_and_capacity() -> None:
    template = _read("service.yaml.template")
    example = _read("staging.env.example")
    deploy = _read("deploy_staging.sh")

    assert "@sha256:" in example
    assert "GEMINI_SECRET_VERSION=1" in example
    assert 'key: "__GEMINI_SECRET_VERSION__"' in template
    assert "containerConcurrency: 1" in template
    assert 'autoscaling.knative.dev/maxScale: "2"' in template
    assert "--no-traffic" in deploy
    assert "Creating the first IAM-private staging service revision" in deploy
    assert "run services describe" in deploy
    assert "--no-allow-unauthenticated" in deploy
    assert "--max-instances=2" in deploy
    assert "--concurrency=1" in deploy
    assert "@sha256:[0-9a-f]{64}" in deploy
    assert 'gcloud_bin="${GCLOUD_BIN:-gcloud}"' in deploy
    assert "latest" not in template.lower()
    assert "latest" not in deploy.lower()


def test_cloud_build_pushes_unique_build_tag_and_never_deploys() -> None:
    build = _read("cloudbuild.yaml")

    assert "requirements.test.lock" in build
    assert ":$BUILD_ID" in build
    assert "image-digest-ref.txt" in build
    assert "gcloud run deploy" not in build
    assert "gcloud run services" not in build


def test_smoke_script_checks_auditable_response_and_rejects_internal_routes() -> None:
    smoke = _read("smoke_staging.sh")

    assert "EXPECTED_IMAGE_DIGEST" in smoke
    assert "EXPECTED_FIXTURE_MANIFEST_HASH" in smoke
    assert 'audit["deployment_image_digest"]' in smoke
    assert 'audit["evidence_fixture_manifest_hash"]' in smoke
    assert 'gcloud_bin="${GCLOUD_BIN:-gcloud}"' in smoke
    assert '"/v1/companies/789019/review"' in smoke
    assert '"/v1/companies/789019/resolve"' in smoke
    assert '"/v1/verify/batch"' in smoke


def test_cloud_scripts_refuse_external_actions_without_explicit_authorization() -> None:
    for script, authorization in (
        ("provision_staging.sh", "QUANTIFY_AUTHORIZE_GCP_BOOTSTRAP"),
        ("deploy_staging.sh", "QUANTIFY_AUTHORIZE_STAGING_DEPLOY"),
        ("smoke_staging.sh", "QUANTIFY_AUTHORIZE_STAGING_SMOKE"),
    ):
        result = subprocess.run(
            ["bash", str(DEPLOYMENT / script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert authorization in result.stderr
