"""Decimal-safe money helpers. Currencies are never mixed implicitly."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def q(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def totals_by_currency(items: Iterable[tuple[str, Decimal]]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for ccy, amt in items:
        out[ccy] += amt
    return {k: q(v) for k, v in sorted(out.items())}
