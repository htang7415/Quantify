"""Inert HTTP adapter for the future bounded research-task contract.

This module is intentionally not included in any deployed Lambda or API
Gateway template.  It turns the already-bounded internal task service into the
Section 5 request shape only after an authorized delivery assembly supplies an
explicit capability lifetime and admission service.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator

from quantify.harness.coverage import EvidenceRequestType
from quantify.policy_control import PolicyControlError
from quantify.research_tasks import (
    IdempotencyConflictError,
    InvalidTaskTransitionError,
    ResearchTaskRequest,
    TaskCapabilityError,
    TaskCapacityExceededError,
    TaskQueueUnavailableError,
    TaskStoreUnavailableError,
)


class ResearchTaskApiService(Protocol):
    def submit_with_task_capability(
        self, *, request: ResearchTaskRequest, idempotency_key: str, capability_ttl_seconds: int
    ) -> dict[str, object]: ...

    def status_with_task_capability(
        self, *, task_id: str, task_capability: str
    ) -> dict[str, object]: ...

    def retry_with_task_capability(
        self, *, task_id: str, task_capability: str, idempotency_key: str
    ) -> dict[str, object]: ...

    def cancel_with_task_capability(
        self, *, task_id: str, task_capability: str
    ) -> dict[str, object]: ...


class CreateResearchTaskRequest(BaseModel):
    cik: str = Field(min_length=1, max_length=10)
    analysis: str = Field(min_length=1)
    as_of_date: date
    forms: tuple[str, ...] = ("10-K", "10-Q")
    evidence_requests: tuple[EvidenceRequestType, ...] = ()

    @field_validator("analysis")
    @classmethod
    def enforce_word_limit(cls, value: str) -> str:
        if len(value.split()) > 250:
            raise ValueError("analysis must contain at most 250 words")
        return value

    def to_task_request(self) -> ResearchTaskRequest:
        return ResearchTaskRequest(
            cik=self.cik,
            analysis=self.analysis,
            as_of_date=self.as_of_date,
            forms=self.forms,
            evidence_requests=self.evidence_requests,
        )


def create_research_task_app(
    service: ResearchTaskApiService, *, capability_ttl_seconds: int
) -> FastAPI:
    """Create only the future task routes; deployment remains a separate gate."""

    if capability_ttl_seconds <= 0:
        raise ValueError("task capability lifetime is invalid")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/v1/research-tasks", status_code=status.HTTP_202_ACCEPTED)
    def create_task(
        request: CreateResearchTaskRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, object]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail={"error": "invalid_request"})
        try:
            return service.submit_with_task_capability(
                request=request.to_task_request(),
                idempotency_key=idempotency_key,
                capability_ttl_seconds=capability_ttl_seconds,
            )
        except IdempotencyConflictError:
            raise HTTPException(status_code=409, detail={"error": "idempotency_conflict"}) from None
        except TaskCapacityExceededError:
            raise HTTPException(status_code=429, detail={"error": "capacity_exhausted"}) from None
        except (TaskQueueUnavailableError, TaskStoreUnavailableError, PolicyControlError):
            raise HTTPException(status_code=503, detail={"error": "research_tasks_unavailable"}) from None
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": "invalid_request"}) from None

    @app.get("/v1/research-tasks/{task_id}")
    def task_status(task_id: str, task_capability: str | None = Header(default=None, alias="X-Quantify-Task-Capability")) -> dict[str, object]:
        return _with_capability(
            task_capability=task_capability,
            action=lambda capability: service.status_with_task_capability(
                task_id=task_id, task_capability=capability
            ),
        )

    @app.post("/v1/research-tasks/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
    def retry_task(
        task_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        task_capability: str | None = Header(default=None, alias="X-Quantify-Task-Capability"),
    ) -> dict[str, object]:
        if not idempotency_key:
            raise HTTPException(status_code=400, detail={"error": "invalid_request"})
        return _with_capability(
            task_capability=task_capability,
            action=lambda capability: service.retry_with_task_capability(
                task_id=task_id,
                task_capability=capability,
                idempotency_key=idempotency_key,
            ),
        )

    @app.post("/v1/research-tasks/{task_id}/cancel")
    def cancel_task(task_id: str, task_capability: str | None = Header(default=None, alias="X-Quantify-Task-Capability")) -> dict[str, object]:
        return _with_capability(
            task_capability=task_capability,
            action=lambda capability: service.cancel_with_task_capability(
                task_id=task_id, task_capability=capability
            ),
        )

    return app


def _with_capability(*, task_capability: str | None, action):  # type: ignore[no-untyped-def]
    if not task_capability:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    try:
        return action(task_capability)
    except TaskCapabilityError:
        raise HTTPException(status_code=404, detail={"error": "not_found"}) from None
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail={"error": "idempotency_conflict"}) from None
    except TaskCapacityExceededError:
        raise HTTPException(status_code=429, detail={"error": "capacity_exhausted"}) from None
    except InvalidTaskTransitionError:
        raise HTTPException(status_code=409, detail={"error": "invalid_task_state"}) from None
    except (TaskStoreUnavailableError, TaskQueueUnavailableError, PolicyControlError):
        raise HTTPException(status_code=503, detail={"error": "research_tasks_unavailable"}) from None
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "invalid_request"}) from None
