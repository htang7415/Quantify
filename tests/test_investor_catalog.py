from decimal import Decimal

from scripts.build_investor_catalog import Manager, compile_snapshot, filing_rows, manager_release, parse_information_table


def test_information_table_aggregates_only_compatible_security_rows() -> None:
    payload = b"""<?xml version="1.0"?>
    <informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
      <infoTable><nameOfIssuer>Example Inc</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>100000000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
      <infoTable><nameOfIssuer>Example Inc</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>50000000</value><shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
      <infoTable><nameOfIssuer>Example Inc</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>123456789</cusip><value>25000000</value><shrsOrPrnAmt><sshPrnamt>2</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
    </informationTable>"""

    rows = parse_information_table(payload)

    assert len(rows) == 2
    common = next(row for row in rows if row["put_call"] is None)
    option = next(row for row in rows if row["put_call"] == "CALL")
    assert common["value_usd"] == Decimal("150000000")
    assert common["shares"] == Decimal("15")
    assert option["instrument_type"] == "Option"


def test_snapshot_uses_exact_reported_dollars_and_versioned_metadata() -> None:
    rows = [
        {
            "security_id": "123456789|COM||SH",
            "issuer": "Example Inc",
            "title": "COM",
            "cusip": "123456789",
            "put_call": None,
            "share_type": "SH",
            "instrument_type": "Common equity",
            "value_usd": Decimal("150000000"),
            "shares": Decimal("15"),
        }
    ]
    filing = {"form": "13F-HR", "report_period": "2026-03-31", "filed_date": "2026-05-15", "accession": "0000000000-26-000001"}

    snapshot = compile_snapshot(filing, rows, "https://www.sec.gov/example.xml", {"123456789": {"ticker": "EXM", "theme": "Other"}})

    assert snapshot["total_value_usd"] == 150_000_000
    assert snapshot["holdings"][0]["weight_pct"] == Decimal("100")
    assert snapshot["holdings"][0]["ticker"] == "EXM"


def test_suspicious_filing_scale_fails_closed() -> None:
    manager = Manager("example", "0000000001", "Example", None, "Test", "Test")
    base = {
        "form": "13F-HR",
        "report_period": "2026-03-31",
        "filed_date": "2026-05-15",
        "accession": "0000000001-26-000001",
        "source_url": "https://www.sec.gov/example.xml",
        "reporting_manager_name": "Example Manager",
        "total_value_usd": 3_000_000,
        "holdings_count": 1,
        "holdings": [],
    }
    previous = {**base, "report_period": "2025-12-31", "accession": "0000000001-26-000000"}

    release = manager_release(manager, [base, previous])

    assert release["status"] == "source_review"
    assert release["disclosed_portfolio_value_usd"] is None
    assert release["holdings"] == []


def test_filing_selection_uses_report_period_not_late_filing_order() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["13F-HR/A", "13F-HR", "13F-HR"],
                "reportDate": ["2025-12-31", "2026-03-31", "2025-12-31"],
                "filingDate": ["2026-06-01", "2026-05-15", "2026-02-15"],
                "accessionNumber": ["late-amendment", "current", "original"],
            }
        }
    }

    selected = filing_rows(submissions, 2)

    assert [row["report_period"] for row in selected] == ["2026-03-31", "2025-12-31"]
    assert selected[1]["accession"] == "late-amendment"
