"""Cache-first SEC Company Facts client with an injectable transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Callable
from urllib.request import Request, urlopen


COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


@dataclass(frozen=True, slots=True)
class SecPayload:
    cik: str
    source_url: str
    payload: bytes
    payload_sha256: str
    retrieved_at: str
    cache_hit: bool

    def json(self) -> dict:
        return json.loads(self.payload)


class SecCompanyFactsClient:
    """Fetch SEC Company Facts once, then replay exact cached bytes.

    The default transport uses the SEC's required identifying User-Agent. Tests
    inject a byte-returning transport, so ordinary test runs make no network
    calls.
    """

    def __init__(
        self,
        *,
        cache_dir: Path,
        user_agent: str,
        transport: Callable[[str, str], bytes] | None = None,
        now: Callable[[], datetime] | None = None,
        min_request_interval_seconds: float = 0.1,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC requests require an identifying user agent")
        self._cache_dir = cache_dir
        self._user_agent = user_agent
        self._transport = transport or self._default_transport
        self._now = now or (lambda: datetime.now(timezone.utc))
        if min_request_interval_seconds < 0:
            raise ValueError("minimum request interval cannot be negative")
        self._min_request_interval_seconds = min_request_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None

    @staticmethod
    def normalize_cik(cik: str | int) -> str:
        digits = str(cik).strip().lstrip("0") or "0"
        if not digits.isdigit() or int(digits) <= 0:
            raise ValueError("CIK must be a positive numeric identifier")
        return digits.zfill(10)

    def fetch_company_facts(self, cik: str | int) -> SecPayload:
        return self._fetch(
            cik=self.normalize_cik(cik),
            source_url=COMPANY_FACTS_URL.format(cik=self.normalize_cik(cik)),
            cache_kind="companyfacts",
        )

    def fetch_submissions(self, cik: str | int) -> SecPayload:
        normalized_cik = self.normalize_cik(cik)
        return self._fetch(
            cik=normalized_cik,
            source_url=SUBMISSIONS_URL.format(cik=normalized_cik),
            cache_kind="submissions",
        )

    def _fetch(self, *, cik: str, source_url: str, cache_kind: str) -> SecPayload:
        payload_path = self._cache_dir / cache_kind / f"{cik}.json"
        metadata_path = payload_path.with_suffix(".metadata.json")
        if payload_path.exists() and metadata_path.exists():
            payload = payload_path.read_bytes()
            metadata = json.loads(metadata_path.read_text())
            return SecPayload(
                cik=cik,
                source_url=metadata["source_url"],
                payload=payload,
                payload_sha256=sha256(payload).hexdigest(),
                retrieved_at=metadata["retrieved_at"],
                cache_hit=True,
            )

        if self._last_request_at is not None:
            wait_seconds = self._min_request_interval_seconds - (
                self._clock() - self._last_request_at
            )
            if wait_seconds > 0:
                self._sleeper(wait_seconds)
        payload = self._transport(source_url, self._user_agent)
        self._last_request_at = self._clock()
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_bytes(payload)
        retrieved_at = self._now().isoformat()
        metadata_path.write_text(
            json.dumps(
                {"source_url": source_url, "retrieved_at": retrieved_at},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return SecPayload(
            cik=cik,
            source_url=source_url,
            payload=payload,
            payload_sha256=sha256(payload).hexdigest(),
            retrieved_at=retrieved_at,
            cache_hit=False,
        )

    @staticmethod
    def _default_transport(source_url: str, user_agent: str) -> bytes:
        request = Request(source_url, headers={"User-Agent": user_agent})
        with urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read()
