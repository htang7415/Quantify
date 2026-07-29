"""Point-in-time SEC filing resolution from cached submissions data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SecFiling:
    cik: str
    form: str
    accession: str
    filing_date: date
    report_date: date | None
    primary_document: str

    @property
    def is_amendment(self) -> bool:
        return self.form.endswith("/A")


def resolve_filings(
    *,
    submissions: dict,
    cik: str,
    forms: tuple[str, ...],
    as_of_date: date,
    historical_submissions: tuple[dict, ...] = (),
) -> tuple[SecFiling, ...]:
    """Resolve eligible filing records known at a point in time.

    Amendments are retained rather than silently discarded; the versioned
    restatement policy decides which normalized facts enter a snapshot later.
    """

    records = [submissions["filings"]["recent"]]
    records.extend(
        historical.get("filings", {}).get("recent", historical)
        for historical in historical_submissions
    )
    filings: list[SecFiling] = []
    for records_set in records:
        for index, form in enumerate(records_set["form"]):
            base_form = form.removesuffix("/A")
            filing_date = date.fromisoformat(records_set["filingDate"][index])
            if base_form not in forms or filing_date > as_of_date:
                continue
            report_date_value = records_set.get("reportDate", [""] * len(records_set["form"]))[index]
            filings.append(
                SecFiling(
                    cik=cik,
                    form=form,
                    accession=records_set["accessionNumber"][index],
                    filing_date=filing_date,
                    report_date=(date.fromisoformat(report_date_value) if report_date_value else None),
                    primary_document=records_set["primaryDocument"][index],
                )
            )
    unique_accessions = {filing.accession: filing for filing in filings}
    return tuple(
        sorted(
            unique_accessions.values(),
            key=lambda filing: (
                filing.report_date or date.min,
                filing.filing_date,
                filing.accession,
            ),
            reverse=True,
        )
    )
