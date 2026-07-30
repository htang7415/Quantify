"""Offline construction and validation of immutable evidence-release manifests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path


class EvidenceReleaseError(ValueError):
    """A proposed evidence release is incomplete, mutable, or unverifiable."""


@dataclass(frozen=True, slots=True)
class EvidenceRelease:
    """A replayable offline approval record; never fetched by the online path."""

    release_version: str
    release_id: str
    issuer_ciks: tuple[str, ...]
    fixture_manifest_sha256: str
    fixture_payload_sha256s: tuple[tuple[str, str], ...]
    source_policy_version: str
    eligibility_policy_version: str
    restatement_policy_version: str
    evaluation_corpus_sha256: str

    @property
    def manifest_hash(self) -> str:
        return sha256(
            json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["manifest_hash"] = self.manifest_hash
        return payload


def build_evidence_release(
    *,
    fixtures_directory: Path,
    release_id: str,
    issuer_ciks: tuple[str, ...],
    evaluation_corpus: Path,
    source_policy_version: str = "sec-source-policy-v1",
    eligibility_policy_version: str = "1.0.0",
    restatement_policy_version: str = "1.0.0",
) -> EvidenceRelease:
    """Validate an approved frozen fixture set before it can be published."""

    if not release_id or not issuer_ciks or len(set(issuer_ciks)) != len(issuer_ciks):
        raise EvidenceReleaseError("release identity is invalid")
    if not all(version for version in (source_policy_version, eligibility_policy_version, restatement_policy_version)):
        raise EvidenceReleaseError("release policy versions are required")
    try:
        manifest_bytes = (fixtures_directory / "manifest.json").read_bytes()
        fixture_manifest = json.loads(manifest_bytes)
        entries = fixture_manifest["fixtures"]
        corpus_bytes = evaluation_corpus.read_bytes()
    except (FileNotFoundError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise EvidenceReleaseError("release inputs are missing or invalid") from error
    if not corpus_bytes:
        raise EvidenceReleaseError("release evaluation corpus is empty")
    if not isinstance(entries, list):
        raise EvidenceReleaseError("fixture manifest entries are invalid")
    requested = set(issuer_ciks)
    payload_hashes: list[tuple[str, str]] = []
    found: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise EvidenceReleaseError("fixture manifest entry is invalid")
        cik = entry.get("cik")
        relative_path = entry.get("path")
        declared_hash = entry.get("payload_sha256")
        if not all(isinstance(value, str) and value for value in (cik, relative_path, declared_hash)):
            raise EvidenceReleaseError("fixture provenance is incomplete")
        if cik not in requested:
            continue
        if Path(relative_path).name != relative_path:
            raise EvidenceReleaseError("fixture path is not immutable")
        payload_hash = sha256((fixtures_directory / relative_path).read_bytes()).hexdigest()
        if payload_hash != declared_hash:
            raise EvidenceReleaseError("fixture payload hash mismatch")
        found.add(cik)
        payload_hashes.append((cik, payload_hash))
    if found != requested:
        raise EvidenceReleaseError("release issuer has no approved fixture")
    return EvidenceRelease(
        release_version="1.0.0",
        release_id=release_id,
        issuer_ciks=tuple(sorted(requested)),
        fixture_manifest_sha256=sha256(manifest_bytes).hexdigest(),
        fixture_payload_sha256s=tuple(sorted(payload_hashes)),
        source_policy_version=source_policy_version,
        eligibility_policy_version=eligibility_policy_version,
        restatement_policy_version=restatement_policy_version,
        evaluation_corpus_sha256=sha256(corpus_bytes).hexdigest(),
    )
