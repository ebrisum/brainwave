"""Pluggable data providers. Each provider declares its licence and attribution (docs/LICENSES.md)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    kind: str
    license: str
    attribution: str
    resolution_m: float | None = None
    # May the data be stored/baked into course packages under its terms?
    bakeable: bool = True


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot serve a request (offline, no coverage, missing dependency)."""


def http_client(timeout: float):
    import httpx

    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "gpx2course/2026.10 (RidePrep)"})
