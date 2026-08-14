import hashlib
import json
from pathlib import Path

import pytest

import scripts.acquire_investor_sec_bundle as acquisition
import scripts.build_investor_catalog as investor_compiler
import scripts.check_investor_filing_readiness as readiness
from scripts.build_investor_catalog import SEC_ARCHIVES, SEC_SUBMISSIONS, compile_catalog_from_bundle
from scripts.check_investor_filing_readiness import build_readiness_report, write_new_report
from tests.test_public_release_candidate import directory_payloads, load, make_investor_source_bundle


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "scripts/investor_security_metadata.json"


def filing_payloads(manager: investor_compiler.Manager, periods: list[tuple[str, str, str]]) -> dict[str, bytes]:
    submissions = {
        "name": f"{manager.firm} filing manager",
        "filings": {"recent": {
            "form": ["13F-HR" for _ in periods],
            "reportDate": [period for period, _filed, _accession in periods],
            "filingDate": [filed for _period, filed, _accession in periods],
            "accessionNumber": [accession for _period, _filed, accession in periods],
        }},
    }
    payloads = {
        SEC_SUBMISSIONS.format(cik=manager.reporting_cik): json.dumps(submissions, separators=(",", ":")).encode()
    }
    for _period, _filed, accession in periods:
        accession_path = accession.replace("-", "")
        base = {"cik": str(int(manager.reporting_cik)), "accession": accession_path}
        index_url = SEC_ARCHIVES.format(**base, name="index.json")
        xml_url = SEC_ARCHIVES.format(**base, name="information-table.xml")
        payloads[index_url] = json.dumps(
            {"directory": {"item": [{"name": "information-table.xml"}]}}, separators=(",", ":")
        ).encode()
        payloads[xml_url] = b"""<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>NVIDIA CORPORATION</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>67066G104</cusip><value>250000000</value><shrsOrPrnAmt><sshPrnamt>1000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""
    return payloads


def test_complete_readiness_report_is_deterministic_and_never_authorizes_candidate(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    monkeypatch.setattr(readiness, "MANAGERS", (manager,))
    manifest = make_investor_source_bundle(tmp_path / "bundle", manager)

    args = {
        "source_manifest_path": manifest,
        "target_report_period": "2026-03-31",
        "checked_at": "2026-08-14T03:30:00Z",
    }
    first = build_readiness_report(**args)
    second = build_readiness_report(**args)

    assert first == second
    assert first["status"] == "complete"
    assert first["manager_count"] == 1
    assert first["ready_manager_count"] == 1
    assert first["managers"][0]["status"] == "ready"
    assert first["candidate_build_authorized"] is False
    assert first["source_manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()


def test_readiness_reports_waiting_and_ahead_without_guessing(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    monkeypatch.setattr(readiness, "MANAGERS", (manager,))
    manifest = make_investor_source_bundle(tmp_path / "bundle", manager)

    waiting = build_readiness_report(
        source_manifest_path=manifest,
        target_report_period="2026-06-30",
        checked_at="2026-08-14T03:30:00Z",
    )
    ahead = build_readiness_report(
        source_manifest_path=manifest,
        target_report_period="2025-12-31",
        checked_at="2026-08-14T03:30:00Z",
    )

    assert waiting["status"] == "incomplete"
    assert waiting["ready_manager_count"] == 0
    assert waiting["managers"][0]["status"] == "waiting"
    assert ahead["status"] == "incomplete"
    assert ahead["managers"][0]["status"] == "ahead"


def test_mixed_period_acquisition_is_reviewable_but_compilation_fails_closed(tmp_path: Path, monkeypatch) -> None:
    ready_manager, waiting_manager = investor_compiler.MANAGERS[:2]
    periods = {
        ready_manager.reporting_cik: [
            ("2026-06-30", "2026-08-10", "0001541617-26-000010"),
            ("2026-03-31", "2026-05-15", "0001541617-26-000006"),
        ],
        waiting_manager.reporting_cik: [
            ("2026-03-31", "2026-05-15", "0001336528-26-000006"),
            ("2025-12-31", "2026-02-14", "0001336528-26-000005"),
        ],
    }
    payloads: dict[str, bytes] = {}
    for manager in (ready_manager, waiting_manager):
        payloads.update(filing_payloads(manager, periods[manager.reporting_cik]))

    class FakeSecClient:
        def get_bytes(self, url: str) -> bytes:
            return payloads[url]

    managers = (ready_manager, waiting_manager)
    monkeypatch.setattr(acquisition, "MANAGERS", managers)
    monkeypatch.setattr(investor_compiler, "MANAGERS", managers)
    monkeypatch.setattr(readiness, "MANAGERS", managers)
    first = tmp_path / "bundle-a"
    second = tmp_path / "bundle-b"
    args = {"client": FakeSecClient(), "created_at": "2026-08-14T03:30:00Z", "quarters": 2}

    acquisition.acquire_bundle(**args, target_directory=first)
    acquisition.acquire_bundle(**args, target_directory=second)

    assert directory_payloads(first) == directory_payloads(second)
    report = build_readiness_report(
        source_manifest_path=first / "manifest.json",
        target_report_period="2026-06-30",
        checked_at="2026-08-14T03:31:00Z",
    )
    assert report["status"] == "incomplete"
    assert report["ready_manager_count"] == 1
    assert [row["status"] for row in report["managers"]] == ["ready", "waiting"]
    with pytest.raises(ValueError, match="do not share a latest reporting period"):
        compile_catalog_from_bundle(first / "manifest.json", METADATA)


def test_readiness_fails_closed_for_invalid_time_period_tampering_and_existing_output(tmp_path: Path, monkeypatch) -> None:
    manager = investor_compiler.MANAGERS[0]
    monkeypatch.setattr(investor_compiler, "MANAGERS", (manager,))
    monkeypatch.setattr(readiness, "MANAGERS", (manager,))
    manifest = make_investor_source_bundle(tmp_path / "bundle", manager)

    with pytest.raises(ValueError, match="quarter-end"):
        build_readiness_report(
            source_manifest_path=manifest,
            target_report_period="2026-06-29",
            checked_at="2026-08-14T03:30:00Z",
        )
    with pytest.raises(ValueError, match="cannot precede"):
        build_readiness_report(
            source_manifest_path=manifest,
            target_report_period="2026-03-31",
            checked_at="2026-08-14T01:00:00Z",
        )

    source = load(manifest)
    resource = manifest.parent / source["resources"][0]["path"]
    resource.write_bytes(resource.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash does not match"):
        build_readiness_report(
            source_manifest_path=manifest,
            target_report_period="2026-03-31",
            checked_at="2026-08-14T03:30:00Z",
        )

    unused_manifest = make_investor_source_bundle(tmp_path / "unused", manager)
    unused = load(unused_manifest)
    extra_payload = b"{}"
    extra_path = unused_manifest.parent / "resources/extra.json"
    extra_path.write_bytes(extra_payload)
    unused["resources"].append({
        "url": "https://data.sec.gov/submissions/CIK0001541617-extra.json",
        "path": "resources/extra.json",
        "sha256": hashlib.sha256(extra_payload).hexdigest(),
        "media_type": "application/json",
    })
    unused_manifest.write_text(json.dumps(unused), encoding="utf-8")
    with pytest.raises(ValueError, match="unused resource"):
        build_readiness_report(
            source_manifest_path=unused_manifest,
            target_report_period="2026-03-31",
            checked_at="2026-08-14T03:30:00Z",
        )

    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        write_new_report(output, {"not": "written"})
    assert output.read_text(encoding="utf-8") == "existing"
