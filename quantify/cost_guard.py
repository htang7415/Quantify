"""Fail-closed monthly model-cost reservation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING


@dataclass(frozen=True, slots=True)
class GeminiCostPolicy:
    """Pinned standard-tier pricing and a conservative per-call reservation."""

    version: str = "gemini-3.1-flash-lite-standard-2026-07-09"
    input_price_per_million_usd: Decimal = Decimal("0.25")
    output_price_per_million_usd: Decimal = Decimal("1.50")
    max_input_payload_bytes: int = 48_000
    max_output_tokens: int = 256

    @property
    def maximum_request_micro_usd(self) -> int:
        # One byte per token is deliberately conservative. It avoids an extra
        # provider call while reserving enough budget before the model call.
        usd = (
            Decimal(self.max_input_payload_bytes) * self.input_price_per_million_usd
            + Decimal(self.max_output_tokens) * self.output_price_per_million_usd
        ) / Decimal(1_000_000)
        return int((usd * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))
