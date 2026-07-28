"""Injected application service for the API verification workflow."""
from __future__ import annotations
from dataclasses import asdict
from quantify.api import VerifyRequest

class ApplicationService:
    def __init__(self, verify): self._verify = verify
    def verify(self, *, cik: str, request: VerifyRequest) -> dict:
        return self._verify(cik=cik, analysis=request.analysis, as_of_date=request.as_of_date, forms=request.forms)
