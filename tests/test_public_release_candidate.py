import hashlib
import json
from pathlib import Path

import pytest

import scripts.acquire_investor_sec_bundle as investor_acquisition
import scripts.build_investor_catalog as investor_compiler
from scripts.build_investor_catalog import SEC_ARCHIVES, SEC_SUBMISSIONS, compile_catalog_from_bundle
from scripts.build_public_release_candidate import build_candidate


ROOT = Path(__file__).resolve().parents[1]
RUN_AT = "2026-08-14T05:00:00Z"


def paths() -> dict[str, Path]:
    return {
        "investor_catalog_path": ROOT / "web/src/data/investorCatalog.json",
        "etf_flow_input_path": ROOT / "tests/fixtures/public_data/etf_flows_2026-03-31.json",
        "etf_holdings_input_path": ROOT / "tests/fixtures/public_data/etf_holdings_2026q2.json",
        "security_metadata_path": ROOT / "scripts/investor_security_metadata.json",
        "active_release_index_path": ROOT / "web/src/data/publicReleaseIndex.json",
    }


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def directory_payloads(path: Path) -> dict[str, bytes]:
    return {str(item.relative_to(path)): item.read_bytes() for item in sorted(path.rglob("*")) if item.is_file()}


def make_investor_source_bundle(root: Path, manager: investor_compiler.Manager) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    resources: list[dict] = []

    def resource(name: str, url: str, payload: bytes, media_type: str) -> None:
        relative = f"resources/{name}"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        resources.append({
            "url": url,
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "media_type": media_type,
        })

    accessions = ["0001541617-26-000006", "0001541617-26-000005"]
    submissions = {
        "name": "Synthetic reporting manager",
        "filings": {"recent": {
            "form": ["13F-HR", "13F-HR"],
            "reportDate": ["2026-03-31", "2025-12-31"],
            "filingDate": ["2026-05-15", "2026-02-14"],
            "accessionNumber": accessions,
        }},
    }
    resource(
        "submissions.json",
        SEC_SUBMISSIONS.format(cik=manager.reporting_cik),
        json.dumps(submissions, separators=(",", ":")).encode(),
        "application/json",
    )
    for index, accession in enumerate(accessions):
        accession_path = accession.replace("-", "")
        base = {"cik": str(int(manager.reporting_cik)), "accession": accession_path}
        index_url = SEC_ARCHIVES.format(**base, name="index.json")
        xml_url = SEC_ARCHIVES.format(**base, name="information-table.xml")
        index_payload = json.dumps({"directory": {"item": [{"name": "information-table.xml"}]}}, separators=(",", ":")).encode()
        value = 250_000_000 if index == 0 else 200_000_000
        shares = 1_000_000 if index == 0 else 800_000
        xml_payload = f"""<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>NVIDIA CORPORATION</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>67066G104</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>""".encode()
        resource(f"index-{index}.json", index_url, index_payload, "application/json")
        resource(f"information-table-{index}.xml", xml_url, xml_payload, "application/xml")
    manifest = {
        "schema_version": "investor-sec-source-bundle.v1",
        "source_id": "sec-edgar-public-filings",
        "created_at": "2026-08-14T01:30:00Z",
        "quarters": 2,
        "manager_ciks": [manager.reporting_cik],
        "resources": resources,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def test_candidate_is_deterministic_and_does_not_mutate_active_catalogs(tmp_path: Path) -> None:
    active = paths()
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in active.items()}
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_manifest = build_candidate(**active, target_directory=first, run_at=RUN_AT)
    second_manifest = build_candidate(**active, target_directory=second, run_at=RUN_AT)

    assert first_manifest == second_manifest
    assert directory_payloads(first) == directory_payloads(second)
    assert before == {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in active.items()}
    assert first_manifest["publication_authorized"] is False
    assert first_manifest["status"] == "ready_for_review"
    assert {row["catalog"] for row in first_manifest["previous_bindings"]} == {"etf_flows", "etf_holdings"}

    candidate_index = load(first / "publicReleaseIndex.json")
    releases = {row["catalog"]: row for row in candidate_index["releases"]}
    flow_catalog = load(first / "catalogs/etfFlowCatalog.json")
    holdings_catalog = load(first / "catalogs/etfHoldingsCatalog.json")
    assert releases["etf_flows"]["release_id"] == flow_catalog["release_id"]
    assert releases["etf_holdings"]["manifest_hash"] == holdings_catalog["manifest_hash"]
    assert releases["investors"]["release_id"] == load(active["investor_catalog_path"])["release_id"]


def test_dependency_mismatch_fails_without_partial_candidate(tmp_path: Path) -> None:
    active = paths()
    holdings = load(active["etf_holdings_input_path"])
    holdings["dataset_sha256"] = "a" * 64
    bad_holdings = tmp_path / "bad-holdings.json"
    bad_holdings.write_text(json.dumps(holdings), encoding="utf-8")
    target = tmp_path / "candidate"

    with pytest.raises(ValueError, match="dataset identity does not match"):
        build_candidate(**{**active, "etf_holdings_input_path": bad_holdings}, target_directory=target, run_at=RUN_AT)

    assert not target.exists()
    assert not list(tmp_path.glob(".candidate.*"))


def test_tampered_investor_catalog_fails_before_compilation(tmp_path: Path) -> None:
    active = paths()
    investor = load(active["investor_catalog_path"])
    investor["managers"][0]["firm"] = "Tampered manager"
    bad_investor = tmp_path / "bad-investor.json"
    bad_investor.write_text(json.dumps(investor), encoding="utf-8")
    target = tmp_path / "candidate"

    with pytest.raises(ValueError, match="manifest hash does not replay"):
        build_candidate(**{**active, "investor_catalog_path": bad_investor}, target_directory=target, run_at=RUN_AT)

    assert not target.exists()


def test_existing_target_and_implicit_time_fail_closed(tmp_path: Path) -> None:
    active = paths()
    target = tmp_path / "candidate"
    target.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        build_candidate(**active, target_directory=target, run_at=RUN_AT)
    with pytest.raises(ValueError, match="exact UTC timestamp"):
        build_candidate(**active, target_directory=tmp_path / "other", run_at="now")
    with pytest.raises(ValueError, match="cannot precede"):
        build_candidate(**active, target_directory=tmp_path / "early", run_at="2026-08-13T18:00:00Z")


def test_candidate_manifest_schema_declares_review_and_rollback_boundaries() -> None:
    schema = load(ROOT / "schemas/public_refresh_candidate.v2.schema.json")
    assert schema["properties"]["schema_version"]["const"] == "public-refresh-candidate.v2"
    assert schema["properties"]["status"]["const"] == "ready_for_review"
    assert schema["properties"]["publication_authorized"]["const"] is False
    assert "investor_compilation" in schema["required"]
    assert "venture_compilation" in schema["required"]
    assert schema["properties"]["previous_bindings"]["minItems"] == 2


def test_candidate_compiles_reviewed_venture_source_without_promoting_it(tmp_path: Path) -> None:
    active = paths()
    target = tmp_path / "venture-candidate"
    source = ROOT / "tests/fixtures/public_data/vc_portfolio_sources_candidate_2026-08-14.json"

    manifest = build_candidate(**active, target_directory=target, run_at=RUN_AT, venture_source_path=source)

    assert manifest["publication_authorized"] is False
    assert manifest["venture_compilation"]["publication_authorized"] is False
    assert manifest["venture_compilation"]["firm_count"] == 6
    assert manifest["venture_compilation"]["relationship_count"] == 36
    assert {row["catalog"] for row in manifest["previous_bindings"]} == {"venture", "etf_flows", "etf_holdings"}
    catalog = load(target / "catalogs/vcCatalog.json")
    index = {row["catalog"]: row for row in load(target / "publicReleaseIndex.json")["releases"]}
    assert catalog["release_id"] == "vc-2026-08-14-6ff758da0f36"
    assert index["venture"]["manifest_hash"] == catalog["manifest_hash"]
    assert load(active["active_release_index_path"])["releases"][1]["release_id"] != catalog["release_id"]


def test_manifest_bound_investor_compilation_is_replayable_and_network_free(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    monkeypatch.setattr(investor_compiler.urllib.request, "urlopen", lambda *_args, **_kwargs: pytest.fail("network called"))
    manifest_path = make_investor_source_bundle(tmp_path / "bundle", manager)

    first_catalog, first_record = compile_catalog_from_bundle(manifest_path, ROOT / "scripts/investor_security_metadata.json")
    second_catalog, second_record = compile_catalog_from_bundle(manifest_path, ROOT / "scripts/investor_security_metadata.json")

    assert first_catalog == second_catalog
    assert first_record == second_record
    assert first_catalog["report_period"] == "2026-03-31"
    assert first_catalog["managers"][0]["holdings"][0]["ticker"] == "NVDA"
    assert first_record["source_manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert first_record["resource_count"] == 5
    assert first_record["catalog_manifest_hash"] == first_catalog["manifest_hash"]


def test_investor_source_bundle_rejects_tampering_and_unused_resources(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    manifest_path = make_investor_source_bundle(tmp_path / "tampered", manager)
    manifest = load(manifest_path)
    resource_path = manifest_path.parent / manifest["resources"][-1]["path"]
    resource_path.write_bytes(resource_path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash does not match"):
        compile_catalog_from_bundle(manifest_path, ROOT / "scripts/investor_security_metadata.json")

    unused_manifest = make_investor_source_bundle(tmp_path / "unused", manager)
    unused = load(unused_manifest)
    extra_payload = b"{}"
    extra_path = unused_manifest.parent / "resources/unused.json"
    extra_path.write_bytes(extra_payload)
    unused["resources"].append({
        "url": "https://data.sec.gov/submissions/unused.json",
        "path": "resources/unused.json",
        "sha256": hashlib.sha256(extra_payload).hexdigest(),
        "media_type": "application/json",
    })
    unused_manifest.write_text(json.dumps(unused), encoding="utf-8")
    with pytest.raises(ValueError, match="unused resource"):
        compile_catalog_from_bundle(unused_manifest, ROOT / "scripts/investor_security_metadata.json")


def test_candidate_compiles_investor_and_rebuilds_bound_crypto_exposure(tmp_path: Path, monkeypatch) -> None:
    active = paths()
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    manifest_path = make_investor_source_bundle(tmp_path / "bundle", manager)
    first = tmp_path / "candidate-a"
    second = tmp_path / "candidate-b"
    source_args = {
        **active,
        "investor_catalog_path": None,
        "investor_source_manifest_path": manifest_path,
        "crypto_exposure_metadata_path": ROOT / "scripts/crypto_exposure_metadata.json",
    }

    first_manifest = build_candidate(**source_args, target_directory=first, run_at=RUN_AT)
    second_manifest = build_candidate(**source_args, target_directory=second, run_at=RUN_AT)

    assert directory_payloads(first) == directory_payloads(second)
    assert first_manifest == second_manifest
    assert first_manifest["investor_compilation"]["source_manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert {row["catalog"] for row in first_manifest["previous_bindings"]} == {
        "investors", "etf_flows", "etf_holdings", "crypto_exposure"
    }
    investor = load(first / "catalogs/investorCatalog.json")
    crypto = load(first / "catalogs/cryptoExposureCatalog.json")
    index = {row["catalog"]: row for row in load(first / "publicReleaseIndex.json")["releases"]}
    assert crypto["investor_manifest_hash"] == investor["manifest_hash"]
    assert index["investors"]["manifest_hash"] == investor["manifest_hash"]
    assert index["crypto_exposure"]["manifest_hash"] == crypto["manifest_hash"]
    assert index["investors"]["manifest_hash"] != load(active["active_release_index_path"])["releases"][0]["manifest_hash"]


def test_investor_source_bundle_scope_and_path_escape_fail_closed(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    manifest_path = make_investor_source_bundle(tmp_path / "bundle", manager)
    manifest = load(manifest_path)
    manifest["manager_ciks"] = ["0000000000"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manager scope"):
        compile_catalog_from_bundle(manifest_path, ROOT / "scripts/investor_security_metadata.json")

    escape_manifest = make_investor_source_bundle(tmp_path / "escape", manager)
    escape = load(escape_manifest)
    escape["resources"][0]["path"] = "../outside.json"
    escape_manifest.write_text(json.dumps(escape), encoding="utf-8")
    with pytest.raises(ValueError, match="stay inside"):
        compile_catalog_from_bundle(escape_manifest, ROOT / "scripts/investor_security_metadata.json")

    early_manifest = make_investor_source_bundle(tmp_path / "early", manager)
    early = load(early_manifest)
    early["created_at"] = "2026-01-01T00:00:00Z"
    early_manifest.write_text(json.dumps(early), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot precede the latest filing"):
        compile_catalog_from_bundle(early_manifest, ROOT / "scripts/investor_security_metadata.json")


def test_acquisition_writes_a_deterministic_review_bundle_atomically(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    seed_manifest_path = make_investor_source_bundle(tmp_path / "seed", manager)
    seed_manifest = load(seed_manifest_path)
    payloads = {
        row["url"]: (seed_manifest_path.parent / row["path"]).read_bytes()
        for row in seed_manifest["resources"]
    }

    class FakeSecClient:
        def get_bytes(self, url: str) -> bytes:
            return payloads[url]

    monkeypatch.setattr(investor_acquisition, "MANAGERS", (manager,))
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    first = tmp_path / "acquired-a"
    second = tmp_path / "acquired-b"
    args = {"client": FakeSecClient(), "created_at": "2026-08-14T01:30:00Z", "quarters": 2}

    first_manifest = investor_acquisition.acquire_bundle(**args, target_directory=first)
    second_manifest = investor_acquisition.acquire_bundle(**args, target_directory=second)

    assert first_manifest == second_manifest
    assert directory_payloads(first) == directory_payloads(second)
    assert len(first_manifest["resources"]) == 5
    catalog, record = compile_catalog_from_bundle(first / "manifest.json", ROOT / "scripts/investor_security_metadata.json")
    assert record["catalog_manifest_hash"] == catalog["manifest_hash"]
    assert catalog["report_period"] == "2026-03-31"


def test_acquisition_failure_leaves_no_partial_bundle(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    seed_manifest_path = make_investor_source_bundle(tmp_path / "seed", manager)
    seed_manifest = load(seed_manifest_path)
    payloads = {
        row["url"]: (seed_manifest_path.parent / row["path"]).read_bytes()
        for row in seed_manifest["resources"][:-1]
    }

    class MissingSecClient:
        def get_bytes(self, url: str) -> bytes:
            if url not in payloads:
                raise ValueError("missing SEC response")
            return payloads[url]

    monkeypatch.setattr(investor_acquisition, "MANAGERS", (manager,))
    target = tmp_path / "failed-acquisition"
    with pytest.raises(ValueError, match="missing SEC response"):
        investor_acquisition.acquire_bundle(
            client=MissingSecClient(),
            target_directory=target,
            created_at="2026-08-14T01:30:00Z",
            quarters=2,
        )
    assert not target.exists()
    assert not list(tmp_path.glob(".failed-acquisition.*"))
