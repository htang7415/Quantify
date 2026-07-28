"""Minimal injected FastAPI surface for the V1 verification contract."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from fastapi import FastAPI
from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    analysis: str = Field(min_length=1)
    as_of_date: date
    forms: tuple[str, ...] = ("10-K", "10-Q")


class VerificationService(Protocol):
    def verify(self, *, cik: str, request: VerifyRequest) -> dict: ...


def create_app(service: VerificationService) -> FastAPI:
    app = FastAPI(title="Quantify Research Referee", version="0.1.0")

    @app.post("/v1/companies/{cik}/verify")
    def verify_company(cik: str, request: VerifyRequest) -> dict:
        return service.verify(cik=cik, request=request)

    return app
