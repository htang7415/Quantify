"""Minimal injected FastAPI surface for the V1 verification contract."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from quantify.harness.coverage import EvidenceRequestType


class VerifyRequest(BaseModel):
    analysis: str = Field(min_length=1)
    as_of_date: date
    forms: tuple[str, ...] = ("10-K", "10-Q")
    evidence_requests: tuple[EvidenceRequestType, ...] = ()


class BatchVerifyItem(BaseModel):
    cik: str = Field(min_length=1)
    request: VerifyRequest


class BatchVerifyRequest(BaseModel):
    items: tuple[BatchVerifyItem, ...] = Field(min_length=1)


class VerificationService(Protocol):
    def verify(self, *, cik: str, request: VerifyRequest) -> dict: ...


def create_app(service: VerificationService) -> FastAPI:
    app = FastAPI(title="Quantify Research Referee", version="0.1.0")

    @app.post("/v1/companies/{cik}/verify")
    def verify_company(cik: str, request: VerifyRequest) -> dict:
        return service.verify(cik=cik, request=request)

    @app.post("/v1/companies/{cik}/review")
    def review_company(cik: str, request: VerifyRequest) -> dict:
        review = getattr(service, "review", None)
        if review is None:
            raise HTTPException(status_code=501, detail="agent-resolution interface is unavailable")
        return review(cik=cik, request=request)

    @app.post("/v1/companies/{cik}/resolve")
    def resolve_company(cik: str, request: VerifyRequest) -> dict:
        resolve = getattr(service, "resolve", None)
        if resolve is None:
            raise HTTPException(status_code=501, detail="agent-resolution interface is unavailable")
        return resolve(cik=cik, request=request)

    @app.post("/v1/verify/batch")
    def verify_batch(request: BatchVerifyRequest) -> dict:
        batch_verify = getattr(service, "verify_batch", None)
        if batch_verify is None:
            raise HTTPException(status_code=501, detail="batch verification is unavailable")
        return {
            "results": list(
                batch_verify(
                    items=tuple((item.cik, item.request) for item in request.items)
                )
            )
        }

    return app
