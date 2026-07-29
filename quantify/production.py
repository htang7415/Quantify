"""Private V1 application composition with frozen embedded SEC evidence only.

This module is the deployment boundary.  It deliberately does not construct a
``SecCompanyFactsClient``: production verification can read only the validated
payloads embedded in the image.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Mapping

from fastapi import FastAPI

from quantify.api import create_app
from quantify.engine import RestatementPolicy
from quantify.harness import (
    AutonomousResolutionLoop,
    GeminiExtractionConfig,
    GeminiStructuredExtractor,
    SnapshotBuild,
    build_sec_snapshot,
)
from quantify.harness.acquisition import EvidenceAcquisitionRecord
from quantify.harness.coverage import EvidenceRequestType
from quantify.harness.sec.client import SecCompanyFactsClient, SecPayload
from quantify.harness.gemini import JsonTransport
from quantify.harness.sec.normalize import INITIAL_METRIC_ROUTES
from quantify.service import ApplicationService


DEFAULT_FIXTURES_DIRECTORY = Path(__file__).parents[1] / "fixtures" / "sec"
_IMAGE_DIGEST_ENV = "QUANTIFY_IMAGE_DIGEST"
_GEMINI_KEY_ENV = "GEMINI_API_KEY"


class ProductionConfigurationError(RuntimeError):
    """The immutable production composition cannot be assembled safely."""


@dataclass(frozen=True, slots=True)
class EmbeddedSecFixture:
    cik: str
    source_url: str
    retrieved_at: str
    payload: bytes
    payload_sha256: str


def validate_embedded_sec_fixtures(
    fixtures_directory: Path = DEFAULT_FIXTURES_DIRECTORY,
) -> tuple[EmbeddedSecFixture, ...]:
    """Load only manifest-listed, hash-validated SEC Company Facts payloads."""

    manifest_path = fixtures_directory / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        entries = manifest["fixtures"]
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ProductionConfigurationError(
            "embedded SEC fixture manifest is missing or invalid"
        ) from error
    if not isinstance(entries, list) or not entries:
        raise ProductionConfigurationError("embedded SEC fixture manifest has no fixtures")

    fixtures: list[EmbeddedSecFixture] = []
    seen_ciks: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProductionConfigurationError("embedded SEC fixture manifest entry is invalid")
        try:
            relative_path = entry["path"]
            payload_sha256 = entry["payload_sha256"]
            cik = SecCompanyFactsClient.normalize_cik(entry["cik"])
            source_url = entry["source_url"]
            retrieved_at = entry["retrieved_at"]
        except (KeyError, TypeError, ValueError) as error:
            raise ProductionConfigurationError(
                "embedded SEC fixture manifest entry is incomplete"
            ) from error
        path = fixtures_directory / relative_path
        if Path(relative_path).name != relative_path:
            raise ProductionConfigurationError("embedded SEC fixture path is not a basename")
        try:
            payload = path.read_bytes()
            document = json.loads(payload)
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise ProductionConfigurationError(
                "embedded SEC fixture payload is missing or invalid"
            ) from error
        if sha256(payload).hexdigest() != payload_sha256:
            raise ProductionConfigurationError("embedded SEC fixture hash mismatch")
        if not isinstance(document, dict):
            raise ProductionConfigurationError("embedded SEC fixture payload is not an object")
        if SecCompanyFactsClient.normalize_cik(document.get("cik", "")) != cik:
            raise ProductionConfigurationError("embedded SEC fixture CIK does not match manifest")
        if cik in seen_ciks:
            raise ProductionConfigurationError("embedded SEC fixture manifest has duplicate CIKs")
        seen_ciks.add(cik)
        fixtures.append(
            EmbeddedSecFixture(
                cik=cik,
                source_url=source_url,
                retrieved_at=retrieved_at,
                payload=payload,
                payload_sha256=payload_sha256,
            )
        )
    return tuple(sorted(fixtures, key=lambda fixture: fixture.cik))


class EmbeddedSecSnapshotProvider:
    """Snapshot provider with no client, transport, cache, or network path."""

    def __init__(
        self,
        *,
        fixtures: tuple[EmbeddedSecFixture, ...],
        restatement_policy: RestatementPolicy = RestatementPolicy.LATEST_AVAILABLE_AT_CUTOFF,
    ) -> None:
        self._fixtures_by_cik = {fixture.cik: fixture for fixture in fixtures}
        self._restatement_policy = restatement_policy

    def build(
        self,
        *,
        cik: str,
        as_of_date: date,
        forms: tuple[str, ...],
        acquisition_records: tuple[EvidenceAcquisitionRecord, ...] = (),
    ) -> SnapshotBuild:
        normalized_cik = SecCompanyFactsClient.normalize_cik(cik)
        fixture = self._fixtures_by_cik.get(normalized_cik)
        if fixture is None:
            raise ValueError("CIK is not supported by the embedded V1 evidence set")
        expanded_forms = set(forms)
        request_types = {record.request_type for record in acquisition_records}
        if EvidenceRequestType.PRIOR_ANNUAL_PERIOD in request_types:
            expanded_forms.add("10-K")
        if EvidenceRequestType.PRIOR_QUARTER in request_types:
            expanded_forms.add("10-Q")
        metric_names = {"revenue"}
        metric_names.update(
            metric
            for request_type, metrics in {
                EvidenceRequestType.PROFITABILITY_METRICS: (
                    "gross_profit",
                    "operating_income",
                    "net_income",
                ),
                EvidenceRequestType.CASH_FLOW_METRICS: (
                    "operating_cash_flow",
                    "capital_expenditure",
                ),
                EvidenceRequestType.BALANCE_SHEET_METRICS: (
                    "cash",
                    "debt_current",
                    "debt_noncurrent",
                ),
                EvidenceRequestType.DILUTION_METRICS: ("diluted_share_count",),
            }.items()
            if request_type in request_types
            for metric in metrics
        )
        return build_sec_snapshot(
            source=SecPayload(
                cik=fixture.cik,
                source_url=fixture.source_url,
                payload=fixture.payload,
                payload_sha256=fixture.payload_sha256,
                retrieved_at=fixture.retrieved_at,
                cache_hit=True,
            ),
            as_of_date=as_of_date,
            policy=self._restatement_policy,
            forms=tuple(sorted(expanded_forms)),
            routes=tuple(
                route for route in INITIAL_METRIC_ROUTES if route.metric in metric_names
            ),
            acquisition_records=tuple(
                (record.request_type.value, record.reason)
                for record in acquisition_records
            ),
            snapshot_label="embedded-sec-company-facts",
        )


def create_production_app(
    *,
    fixtures_directory: Path = DEFAULT_FIXTURES_DIRECTORY,
    api_key: str | None = None,
    image_digest: str | None = None,
    environment: Mapping[str, str] | None = None,
    extraction_config: GeminiExtractionConfig | None = None,
    transport: JsonTransport | None = None,
) -> FastAPI:
    """Create the private deployment app with an enforced V1 composition."""

    environment = environment if environment is not None else os.environ
    api_key = api_key or environment.get(_GEMINI_KEY_ENV)
    image_digest = image_digest or environment.get(_IMAGE_DIGEST_ENV)
    if not api_key:
        raise ProductionConfigurationError("GEMINI_API_KEY is required for production")
    if not image_digest:
        raise ProductionConfigurationError(
            "QUANTIFY_IMAGE_DIGEST is required for production audit metadata"
        )
    fixtures = validate_embedded_sec_fixtures(fixtures_directory)
    manifest_hash = sha256((fixtures_directory / "manifest.json").read_bytes()).hexdigest()
    # The fixed embedded fundamentals snapshot is larger than the interactive
    # evaluator's narrow fixture payload.  Keep the one-call/output limits,
    # while allowing the full validated V1 evidence context to reach Gemini.
    config = extraction_config or GeminiExtractionConfig(
        max_output_tokens=256, max_input_payload_bytes=48_000
    )
    extractor = GeminiStructuredExtractor(
        api_key=api_key, config=config, transport=transport
    )
    service = ApplicationService(
        snapshot_provider=EmbeddedSecSnapshotProvider(fixtures=fixtures),
        extractor=extractor,
        disclosure_detector=None,
        agent_resolution_loop=AutonomousResolutionLoop(max_actions=0),
        extraction_model=config.model,
        prompt_hash=config.prompt_hash,
        temperature=config.temperature,
        disclosure_detector_version="disabled-v1",
        evidence_fixture_manifest_hash=manifest_hash,
        deployment_image_digest=image_digest,
    )
    app = create_app(
        service, include_internal_routes=False, include_documentation=False
    )
    app.state.quantify_service = service
    app.state.evidence_fixture_manifest_hash = manifest_hash
    app.state.image_digest = image_digest
    return app
