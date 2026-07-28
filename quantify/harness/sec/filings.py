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
    *, submissions: dict, cik: str, forms: tuple[str, ...], as_of_date: date
) -> tuple[SecFiling, ...]:
    """Resolve eligible filing records known at a point in time.

    Amendments are retained rather than silently discarded; the versioned
    restatement policy decides which normalized facts enter a snapshot later.
    """

    recent = submissions["filings"]["recent"]
    filings: list[SecFiling] = []
    for index, form in enumerate(recent["form"]):
        base_form = form.removesuffix("/A")
        filing_date = date.fromisoformat(recent["filingDate"][index])
        if base_form not in forms or filing_date > as_of_date:
            continue
        report_date_value = recent.get("reportDate", [""] * len(recent["form"]))[index]
        filings.append(
            SecFiling(
                cik=cik,
                form=form,
                accession=recent["accessionNumber"][index],
                filing_date=filing_date,
                report_date=(date.fromisoformat(report_date_value) if report_date_value else None),
                primary_document=recent["primaryDocument"][index],
            )
        )
    return tuple(
        sorted(
            filings,
            key=lambda filing: (
                filing.report_date or date.min,
                filing.filing_date,
                filing.accession,
            ),
            reverse=True,
        )
    )
