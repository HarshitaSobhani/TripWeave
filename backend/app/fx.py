"""Optional currency conversion through a configured provider only."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from .config import Settings


class FxError(Exception):
    pass


@dataclass(frozen=True)
class Rate:
    base: str
    quote: str
    rate: Decimal
    as_of: str
    provider: str


def fetch_rate(settings: Settings, base: str, quote: str, client: httpx.Client | None = None) -> Rate:
    if settings.fx_provider != "frankfurter":
        raise FxError("no currency conversion provider configured")
    if base == quote:
        return Rate(base, quote, Decimal(1), "", "identity")
    own = client is None
    client = client or httpx.Client(timeout=settings.fx_timeout_s)
    try:
        resp = client.get(f"{settings.fx_base_url.rstrip('/')}/latest", params={"base": base, "symbols": quote})
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FxError(f"rate request failed: {exc}") from exc
    finally:
        if own:
            client.close()
    try:
        if data["base"] != base:
            raise FxError("provider returned a different base currency")
        value = data["rates"][quote]
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise FxError("invalid rate type")
        rate = Decimal(str(value))
        as_of = str(data["date"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise FxError(f"invalid provider response: {exc}") from exc
    if not rate.is_finite() or rate <= 0:
        raise FxError("rate must be positive")
    return Rate(base, quote, rate, as_of, "frankfurter")
