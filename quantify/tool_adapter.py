"""Framework-neutral function-tool adapter for external AI agents."""

from __future__ import annotations

from collections.abc import Mapping

from .sdk import QuantifyClient


def quantify_verify_tool_definition() -> dict[str, object]:
    """Return a portable JSON-schema tool definition without advice semantics."""

    return {
        "name": "quantify_verify",
        "description": "Verify factual company-analysis claims against a declared frozen evidence release. Not investment advice.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["cik", "analysis", "as_of_date"],
            "properties": {
                "cik": {"type": "string", "pattern": "^[0-9]{1,10}$"},
                "analysis": {"type": "string", "maxLength": 3500},
                "as_of_date": {"type": "string", "format": "date"},
            },
        },
    }


def execute_quantify_verify_tool(*, client: QuantifyClient, access_token: str, arguments: Mapping[str, object]) -> dict[str, object]:
    """Execute one bounded verification and return the unmodified safe contract."""

    if set(arguments) != {"cik", "analysis", "as_of_date"} or not all(
        isinstance(arguments[key], str) for key in arguments
    ):
        raise ValueError("Quantify tool arguments are invalid")
    return client.verify(
        access_token=access_token,
        cik=arguments["cik"],
        analysis=arguments["analysis"],
        as_of_date=arguments["as_of_date"],
    ).as_dict()
