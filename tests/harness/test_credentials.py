from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quantify.harness.credentials import (
    GEMINI_KEYCHAIN_ACCOUNT,
    GEMINI_KEYCHAIN_SERVICE,
    CredentialUnavailableError,
    load_gemini_api_key,
)


def test_environment_credential_takes_precedence_over_the_keychain() -> None:
    calls = []

    def _run(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Keychain must not be called when env is set")

    assert load_gemini_api_key(
        environment={"GEMINI_API_KEY": "test-key"}, run_command=_run, platform="darwin"
    ) == "test-key"
    assert calls == []


def test_macos_keychain_lookup_never_places_a_secret_in_command_arguments() -> None:
    calls = []

    def _run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="keychain-test-key\n")

    assert load_gemini_api_key(
        environment={}, run_command=_run, platform="darwin"
    ) == "keychain-test-key"
    assert calls == [
        (
            (
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    GEMINI_KEYCHAIN_SERVICE,
                    "-w",
                ],
            ),
            {"capture_output": True, "check": False, "text": True},
        )
    ]


def test_missing_credential_fails_without_returning_secret_material() -> None:
    with pytest.raises(CredentialUnavailableError, match="GEMINI_API_KEY is not set"):
        load_gemini_api_key(environment={}, platform="linux")


def test_gitignored_dotenv_is_used_for_local_development(tmp_path: Path) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("# local secret\nGEMINI_API_KEY='dotenv-test-key'\n")

    assert load_gemini_api_key(
        dotenv_path=dotenv_path,
        platform="linux",
    ) == "dotenv-test-key"


def test_keychain_lookup_can_use_the_fixed_quantify_account_fallback() -> None:
    def _run(command, **kwargs):
        if "-s" in command or "-l" in command:
            return subprocess.CompletedProcess(command, 44, stdout="")
        assert command == [
            "security",
            "find-generic-password",
            "-a",
            GEMINI_KEYCHAIN_ACCOUNT,
            "-w",
        ]
        return subprocess.CompletedProcess(command, 0, stdout="account-test-key\n")

    assert load_gemini_api_key(
        environment={}, run_command=_run, platform="darwin"
    ) == "account-test-key"
