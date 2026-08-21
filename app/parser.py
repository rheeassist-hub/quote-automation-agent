"""
자유 형식 문의 텍스트(이메일/카톡) 파서.

입력 예:
    안녕하세요, 견적 부탁드립니다.
    - 명함 1000장 (350g 아트지, 양면)
    - 전단지 5000매 A4 컬러
    - 포장박스 300개 (사이즈 30x20x15)

출력: ParsedLineItem 리스트 (품목코드, 품목명, 수량, 스펙메모, 매칭실패여부)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DATA_PATH = Path(__file__).parent / "data" / "price_table.json"

# 숫자 뒤에 흔히 오는 단위 (품목 unit과 무관하게 텍스트에서 인식용)
QTY_UNIT_PATTERN = r"(?:개|매|장|부|롤|박스|box|ea|pcs)?"
QTY_PATTERN = re.compile(
    r"(\d[\d,]*)\s*" + QTY_UNIT_PATTERN, re.IGNORECASE
)


@dataclass
class LineItem:
    raw_text: str
    matched: bool
    code: Optional[str] = None
    name: Optional[str] = None
    quantity: Optional[int] = None
    spec_note: str = ""
    reason: str = ""  # 매칭 실패 사유


def load_price_table() -> dict:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean_line(line: str) -> str:
    # 앞머리의 불릿/번호 기호 제거: -, *, •, 1), 1., ①  등
    line = re.sub(r"^\s*[-*•·]+\s*", "", line)
    line = re.sub(r"^\s*\(?\d+[\.\)]\s*", "", line)
    return line.strip()


def _find_item_alias(line: str, items: list[dict]) -> Optional[dict]:
    """텍스트 내에서 가장 먼저/길게 매칭되는 품목을 찾는다."""
    best = None
    best_len = 0
    for item in items:
        for alias in [item["name"]] + item.get("aliases", []):
            if alias.lower() in line.lower():
                if len(alias) > best_len:
                    best = item
                    best_len = len(alias)
    return best


def _extract_quantity(line: str) -> Optional[int]:
    matches = QTY_PATTERN.findall(line)
    if not matches:
        return None
    # 여러 숫자가 있으면 (예: 스펙에 사이즈 30x20x15 같은게 있을 수 있음) 첫번째 채택
    # 단, x/X로 연결된 사이즈 표기(30x20x15)는 제외하도록 필터링
    for raw in matches:
        num_str = raw.replace(",", "")
        if num_str.isdigit():
            return int(num_str)
    return None


def parse_inquiry_text(text: str, price_table: Optional[dict] = None) -> list[LineItem]:
    price_table = price_table or load_price_table()
    items = price_table["items"]

    results: list[LineItem] = []

    # 줄 단위로 분리, 빈 줄/인사말 성격 줄은 스킵 후보로 둠
    candidate_lines = [ln for ln in re.split(r"[\r\n]+", text) if ln.strip()]

    for raw_line in candidate_lines:
        line = _clean_line(raw_line)
        if not line:
            continue

        matched_item = _find_item_alias(line, items)
        if not matched_item:
            # 숫자+수량단위가 있는 줄이면 품목명을 못 찾은 것으로 간주해 확인목록에 올림
            # (인사말/일반 문장은 숫자가 없거나 짧아서 대부분 제외됨)
            if _extract_quantity(line) is not None and len(line) <= 60:
                results.append(
                    LineItem(
                        raw_text=raw_line.strip(),
                        matched=False,
                        reason="등록된 단가표에서 품목을 찾지 못했습니다. 수동 확인이 필요합니다.",
                    )
                )
            continue

        qty = _extract_quantity(line)

        # spec note: alias/수량 텍스트를 제거한 나머지
        spec = line
        for alias in [matched_item["name"]] + matched_item.get("aliases", []):
            spec = re.sub(re.escape(alias), "", spec, flags=re.IGNORECASE)
        spec = QTY_PATTERN.sub("", spec, count=1)
        spec = re.sub(r"[()\[\]]", " ", spec)
        spec = re.sub(r"\s{2,}", " ", spec).strip(" ,.-")

        if qty is None:
            results.append(
                LineItem(
                    raw_text=raw_line.strip(),
                    matched=False,
                    code=matched_item["code"],
                    name=matched_item["name"],
                    reason="수량을 인식하지 못했습니다. (예: '1000장', '500개' 형식으로 입력해주세요)",
                )
            )
            continue

        results.append(
            LineItem(
                raw_text=raw_line.strip(),
                matched=True,
                code=matched_item["code"],
                name=matched_item["name"],
                quantity=qty,
                spec_note=spec,
            )
        )

    return results


def parse_unmatched_summary(text: str, price_table: Optional[dict] = None) -> list[str]:
    """품목 매칭이 전혀 안 된 줄들(참고용) 반환."""
    price_table = price_table or load_price_table()
    items = price_table["items"]
    unmatched = []
    for raw_line in re.split(r"[\r\n]+", text):
        line = _clean_line(raw_line)
        if not line:
            continue
        if not _find_item_alias(line, items):
            unmatched.append(raw_line.strip())
    return unmatched
