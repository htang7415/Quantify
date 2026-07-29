"""Typed runtime failures exposed by the deployment-facing API only."""

from __future__ import annotations


class ModelUnavailableError(RuntimeError):
    """The pinned extraction model or its provider contract is unavailable."""

    code = "pinned_model_unavailable"

