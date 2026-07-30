"""Typed runtime failures exposed by the deployment-facing API only."""

from __future__ import annotations


class ModelUnavailableError(RuntimeError):
    """The pinned extraction model or its provider contract is unavailable."""

    code = "pinned_model_unavailable"


class AuditPersistenceError(RuntimeError):
    """The required durable audit-manifest write did not complete."""

    code = "audit_manifest_unavailable"


class MonthlyCostLimitError(RuntimeError):
    code = "monthly_cost_limit_reached"


class CostLedgerUnavailableError(RuntimeError):
    code = "cost_ledger_unavailable"
