from __future__ import annotations

from datetime import date

from quantify.harness.sec import resolve_filings


def test_resolves_forms_as_known_at_cutoff_and_retains_amendments() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-K", "10-Q", "10-K/A", "8-K"],
                "filingDate": ["2024-07-30", "2024-10-24", "2025-01-15", "2024-08-01"],
                "reportDate": ["2024-06-30", "2024-09-30", "2024-06-30", "2024-08-01"],
                "accessionNumber": [
                    "0000950170-24-087843",
                    "0000950170-24-132722",
                    "0000950170-25-000001",
                    "0000950170-24-090000",
                ],
                "primaryDocument": ["msft-20240630.htm", "msft-20240930.htm", "amendment.htm", "8k.htm"],
            }
        }
    }

    filings = resolve_filings(
        submissions=submissions,
        cik="0000789019",
        forms=("10-K", "10-Q"),
        as_of_date=date(2025, 1, 15),
    )

    assert [filing.form for filing in filings] == ["10-Q", "10-K/A", "10-K"]
    assert filings[1].is_amendment is True


def test_excludes_filings_not_known_at_cutoff() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2024-07-30"],
                "reportDate": ["2024-06-30"],
                "accessionNumber": ["0000950170-24-087843"],
                "primaryDocument": ["msft-20240630.htm"],
            }
        }
    }
    assert resolve_filings(
        submissions=submissions,
        cik="0000789019",
        forms=("10-K",),
        as_of_date=date(2024, 7, 29),
    ) == ()


def test_resolves_historical_submission_indexes_and_deduplicates_accessions() -> None:
    root = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2024-07-30"],
                "reportDate": ["2024-06-30"],
                "accessionNumber": ["0000950170-24-087843"],
                "primaryDocument": ["msft-20240630.htm"],
            }
        }
    }
    historical = {
        "form": ["10-K", "10-Q/A", "8-K"],
        "filingDate": ["2019-08-01", "2019-10-24", "2019-08-02"],
        "reportDate": ["2019-06-30", "2019-09-30", "2019-08-02"],
        "accessionNumber": [
            "0001564590-19-027952",
            "0001564590-19-037549",
            "0001564590-19-028000",
        ],
        "primaryDocument": ["msft-20190630.htm", "amendment.htm", "8k.htm"],
    }

    filings = resolve_filings(
        submissions=root,
        historical_submissions=(historical,),
        cik="0000789019",
        forms=("10-K", "10-Q"),
        as_of_date=date(2024, 7, 30),
    )

    assert [filing.accession for filing in filings] == [
        "0000950170-24-087843",
        "0001564590-19-037549",
        "0001564590-19-027952",
    ]
    assert filings[1].is_amendment is True
