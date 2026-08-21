"""견적 계산 로직: 단가표 + 수량할인 적용."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .parser import LineItem, load_price_table


@dataclass
class QuoteLine:
    code: str
    name: str
    quantity: int
    unit: str
    unit_price: int
    discount_rate: float
    discounted_unit_price: float
    line_total: int
    spec_note: str
    below_min_qty: bool = False
    min_qty: int = 0


@dataclass
class QuoteResult:
    lines: list[QuoteLine] = field(default_factory=list)
    unmatched_lines: list[LineItem] = field(default_factory=list)
    subtotal: int = 0
    vat: int = 0
    total: int = 0
    currency: str = "KRW"


def _find_price_item(code: str, price_table: dict) -> dict:
    for item in price_table["items"]:
        if item["code"] == code:
            return item
    raise KeyError(code)


def _discount_rate_for_qty(item: dict, qty: int) -> float:
    rate = 0.0
    for tier in sorted(item["discount_tiers"], key=lambda t: t["min_qty"]):
        if qty >= tier["min_qty"]:
            rate = tier["rate"]
    return rate


def build_quote(line_items: list[LineItem], price_table: Optional[dict] = None) -> QuoteResult:
    price_table = price_table or load_price_table()
    result = QuoteResult(currency=price_table.get("currency", "KRW"))

    for li in line_items:
        if not li.matched or li.quantity is None:
            result.unmatched_lines.append(li)
            continue

        item = _find_price_item(li.code, price_table)
        qty = li.quantity
        unit_price = item["base_unit_price"]
        rate = _discount_rate_for_qty(item, qty)
        discounted_unit_price = round(unit_price * (1 - rate), 2)
        line_total = round(discounted_unit_price * qty)

        below_min = qty < item["min_qty"]

        combined_spec = item["spec_note"]
        if li.spec_note:
            combined_spec = f"{combined_spec} / 요청사항: {li.spec_note}"

        result.lines.append(
            QuoteLine(
                code=item["code"],
                name=item["name"],
                quantity=qty,
                unit=item["unit"],
                unit_price=unit_price,
                discount_rate=rate,
                discounted_unit_price=discounted_unit_price,
                line_total=line_total,
                spec_note=combined_spec,
                below_min_qty=below_min,
                min_qty=item["min_qty"],
            )
        )

    result.subtotal = sum(l.line_total for l in result.lines)
    result.vat = round(result.subtotal * 0.10)
    result.total = result.subtotal + result.vat
    return result
