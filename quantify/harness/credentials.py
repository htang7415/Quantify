"""Secure local credential lookup for external Quantify adapters."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping


GEMINI_KEYCHAIN_SERVICE = "quantify.gemini_api_key"
GEMINI_KEYCHAIN_ACCOUNT = "quantify"


class CredentialUnavailableError(RuntimeError):
    """Raised without exposing secret material when no local credential exists."""


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def load_gemini_api_key(
    *,
    environment: Mapping[str, str] | None = None,
    environment_variable: str = "GEMINI_API_KEY",
    dotenv_path: Path | None = None,
    run_command: RunCommand = subprocess.run,
    platform: str | None = None,
) -> str:
    """Load Gemini credentials from environment, local ``.env``, or Keychain.

    Environment variables take precedence for CI and deployment.  For local
    development, a Git-ignored ``.env`` file at the working-directory root may
    define the key.  On macOS, the login Keychain remains an optional fallback
    under ``quantify.gemini_api_key``.  The returned secret is never logged or
    persisted by this package.
    """

    values = environment if environment is not None else os.environ
    api_key = values.get(environment_variable)
    if api_key:
        return api_key
    if environment is None:
        api_key = _load_dotenv_value(
            path=dotenv_path or Path.cwd() / ".env",
            variable=environment_variable,
        )
        if api_key:
            return api_key
    if (platform or sys.platform) != "darwin":
        raise CredentialUnavailableError(
            f"{environment_variable} is not set and the macOS Keychain is unavailable"
        )
    for query in (
        ["security", "find-generic-password", "-s", GEMINI_KEYCHAIN_SERVICE, "-w"],
        ["security", "find-generic-password", "-l", GEMINI_KEYCHAIN_SERVICE, "-w"],
        ["security", "find-generic-password", "-a", GEMINI_KEYCHAIN_ACCOUNT, "-w"],
    ):
        result = run_command(query, capture_output=True, check=False, text=True)
        api_key = result.stdout.strip()
        if result.returncode == 0 and api_key:
            return api_key
    raise CredentialUnavailableError(
        f"{environment_variable} is unavailable from environment, .env, or macOS Keychain"
    )


def _load_dotenv_value(*, path: Path, variable: str) -> str | None:
    """Read one unquoted or simply quoted key from a local private dotenv file."""

    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", maxsplit=1)
        if name.strip() != variable:
            continue
        return value.strip().strip("\"'") or None
    return None
