"""reportlab 기반 견적서 PDF 생성."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .pricing import QuoteResult

# ---- 한글 폰트 등록 ----
# 1순위: 리포에 번들된 NanumGothic (Vercel Linux 서버리스 환경 포함 모든 환경에서 동작)
# 2순위: macOS 로컬 개발 환경의 시스템 폰트
# 3순위: reportlab 기본 폰트(Helvetica, 한글 미지원)로 폴백
KOREAN_FONT_NAME = "Helvetica"
KOREAN_FONT_BOLD_NAME = "Helvetica-Bold"

_BUNDLED_DIR = Path(__file__).resolve().parent / "fonts"
_CANDIDATE_FONTS = [
    (_BUNDLED_DIR / "NanumGothic-Regular.ttf", _BUNDLED_DIR / "NanumGothic-Bold.ttf"),
    (Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf"), None),
    (Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"), None),
    (Path("/Library/Fonts/AppleGothic.ttf"), None),
]
for _regular_path, _bold_path in _CANDIDATE_FONTS:
    if _regular_path.exists():
        try:
            pdfmetrics.registerFont(TTFont("KoreanFont", str(_regular_path)))
            KOREAN_FONT_NAME = "KoreanFont"
            if _bold_path and Path(_bold_path).exists():
                pdfmetrics.registerFont(TTFont("KoreanFont-Bold", str(_bold_path)))
                KOREAN_FONT_BOLD_NAME = "KoreanFont-Bold"
            else:
                KOREAN_FONT_BOLD_NAME = "KoreanFont"
            break
        except Exception:
            continue


def _fmt_money(value, currency: str) -> str:
    return f"{value:,.0f} {currency}"


def generate_quote_pdf(
    quote: QuoteResult,
    output_path: str,
    customer_name: str = "고객사",
    quote_no: Optional[str] = None,
    issuer_name: str = "샘플 인쇄포장 주식회사",
    issuer_contact: str = "담당자: 김견적 | 02-1234-5678 | sales@sample-print.co.kr",
    valid_days: int = 14,
) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today()
    valid_until = today + datetime.timedelta(days=valid_days)
    quote_no = quote_no or f"Q-{today.strftime('%Y%m%d')}-{abs(hash(customer_name + str(today))) % 10000:04d}"

    styles = getSampleStyleSheet()
    base_style = ParagraphStyle(
        "Korean", parent=styles["Normal"], fontName=KOREAN_FONT_NAME, fontSize=9, leading=12
    )
    title_style = ParagraphStyle(
        "KoreanTitle", parent=styles["Title"], fontName=KOREAN_FONT_NAME, fontSize=20
    )
    small_style = ParagraphStyle(
        "KoreanSmall", parent=styles["Normal"], fontName=KOREAN_FONT_NAME, fontSize=8, textColor=colors.grey
    )
    h2_style = ParagraphStyle(
        "KoreanH2", parent=styles["Heading2"], fontName=KOREAN_FONT_NAME, fontSize=12
    )

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title=f"견적서 {quote_no}",
    )

    story = []
    story.append(Paragraph("견 적 서 (Quotation)", title_style))
    story.append(Spacer(1, 4 * mm))

    meta_table = Table(
        [
            ["견적번호", quote_no, "견적일자", today.isoformat()],
            ["고객사", customer_name, "유효기간", valid_until.isoformat() + "까지"],
            ["발행사", issuer_name, "", ""],
        ],
        colWidths=[25 * mm, 65 * mm, 25 * mm, 55 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), KOREAN_FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(issuer_contact, small_style))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("■ 견적 내역", h2_style))
    story.append(Spacer(1, 2 * mm))

    header = ["No", "품목", "규격/사양", "수량", "단가", "할인율", "적용단가", "금액"]
    data = [header]
    for idx, line in enumerate(quote.lines, start=1):
        spec_p = Paragraph(line.spec_note or "-", base_style)
        warn = " ⚠최소수량미만" if line.below_min_qty else ""
        data.append(
            [
                str(idx),
                Paragraph(line.name + warn, base_style),
                spec_p,
                f"{line.quantity:,} {line.unit}",
                f"{line.unit_price:,.0f}",
                f"{line.discount_rate*100:.0f}%",
                f"{line.discounted_unit_price:,.0f}",
                f"{line.line_total:,.0f}",
            ]
        )

    items_table = Table(
        data,
        colWidths=[8 * mm, 25 * mm, 55 * mm, 20 * mm, 18 * mm, 14 * mm, 18 * mm, 22 * mm],
        repeatRows=1,
    )
    items_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), KOREAN_FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (3, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fa")]),
            ]
        )
    )
    story.append(items_table)
    story.append(Spacer(1, 5 * mm))

    totals_data = [
        ["공급가액", _fmt_money(quote.subtotal, quote.currency)],
        ["부가세(10%)", _fmt_money(quote.vat, quote.currency)],
        ["합계금액", _fmt_money(quote.total, quote.currency)],
    ]
    totals_table = Table(totals_data, colWidths=[130 * mm, 50 * mm])
    totals_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), KOREAN_FONT_NAME),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 2), (-1, 2), 1, colors.black),
                ("FONTSIZE", (0, 2), (-1, 2), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(totals_table)
    story.append(Spacer(1, 8 * mm))

    if quote.unmatched_lines:
        story.append(Paragraph("■ 확인 필요 항목 (자동 인식 실패)", h2_style))
        story.append(Spacer(1, 2 * mm))
        for li in quote.unmatched_lines:
            reason = li.reason or "품목/수량 인식 실패"
            story.append(Paragraph(f"- \"{li.raw_text}\" → {reason}", base_style))
        story.append(Spacer(1, 6 * mm))

    story.append(
        Paragraph(
            "* 본 견적서는 자동 생성된 참고용 견적이며, 실제 계약 조건에 따라 변동될 수 있습니다.",
            small_style,
        )
    )
    story.append(Paragraph("* 최소 발주 수량 미만 항목은 단가가 변동될 수 있습니다.", small_style))

    doc.build(story)
    return output_path
