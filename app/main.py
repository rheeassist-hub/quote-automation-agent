"""B2B 견적서 자동화 에이전트 - FastAPI 백엔드."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .parser import parse_inquiry_text, load_price_table
from .pricing import build_quote
from .pdf_generator import generate_quote_pdf

BASE_DIR = Path(__file__).resolve().parent.parent

# Vercel(및 대부분의 서버리스 환경)은 배포 코드 디렉토리가 읽기 전용이며,
# 오직 /tmp 만 쓰기 가능하다. VERCEL 환경변수가 있으면 /tmp를 사용하고,
# 로컬 개발 환경에서는 기존처럼 프로젝트 내 output/ 디렉토리를 사용한다.
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    OUTPUT_DIR = Path("/tmp") / "output"
else:
    OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

import jinja2

app = FastAPI(title="B2B 견적서 자동화 에이전트", version="0.1.0")

# Vercel 서버리스 환경에서 Jinja2Templates(FastAPI 래퍼)의 내부 LRUCache가
# "unhashable type: 'dict'"로 깨지는 문제가 있어, 캐시를 아예 끈 순수 jinja2
# Environment를 직접 사용한다 (요청마다 템플릿을 새로 컴파일하지만 이 앱 규모에선 무해함).
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(BASE_DIR / "app" / "templates")),
    cache_size=0,
    autoescape=jinja2.select_autoescape(["html"]),
)


def render_template(name: str, **context) -> str:
    return _jinja_env.get_template(name).render(**context)


if (BASE_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

PRICE_TABLE = load_price_table()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return HTMLResponse(render_template("index.html", request=request, items=PRICE_TABLE["items"]))


@app.get("/api/price-table")
def api_price_table():
    return JSONResponse(PRICE_TABLE)


@app.post("/api/parse")
def api_parse(inquiry_text: str = Form(...)):
    """텍스트만 파싱해서 미리보기 (PDF 생성 없이)."""
    line_items = parse_inquiry_text(inquiry_text, PRICE_TABLE)
    quote = build_quote(line_items, PRICE_TABLE)
    return {
        "matched": [
            {
                "name": l.name,
                "quantity": l.quantity,
                "unit": l.unit,
                "unit_price": l.unit_price,
                "discount_rate": l.discount_rate,
                "line_total": l.line_total,
                "spec_note": l.spec_note,
            }
            for l in quote.lines
        ],
        "unmatched": [
            {"raw_text": u.raw_text, "reason": u.reason or "품목 인식 실패"}
            for u in quote.unmatched_lines
        ],
        "subtotal": quote.subtotal,
        "vat": quote.vat,
        "total": quote.total,
    }


def _run_pipeline(inquiry_text: str, customer_name: str) -> tuple[Path, dict]:
    line_items = parse_inquiry_text(inquiry_text, PRICE_TABLE)
    quote = build_quote(line_items, PRICE_TABLE)

    quote_id = uuid.uuid4().hex[:8]
    filename = f"quote_{quote_id}.pdf"
    output_path = OUTPUT_DIR / filename

    generate_quote_pdf(
        quote,
        str(output_path),
        customer_name=customer_name or "고객사",
    )

    summary = {
        "quote_id": quote_id,
        "filename": filename,
        "matched_count": len(quote.lines),
        "unmatched_count": len(quote.unmatched_lines),
        "subtotal": quote.subtotal,
        "vat": quote.vat,
        "total": quote.total,
    }
    return output_path, summary


@app.post("/generate-quote")
def generate_quote_api(inquiry_text: str = Form(...), customer_name: str = Form("")):
    """문의 텍스트 -> PDF 생성 -> PDF 파일을 바로 반환 (curl/API용)."""
    output_path, _summary = _run_pipeline(inquiry_text, customer_name)
    return FileResponse(
        path=str(output_path),
        media_type="application/pdf",
        filename=output_path.name,
    )


@app.post("/generate-quote-form", response_class=HTMLResponse)
def generate_quote_form(request: Request, inquiry_text: str = Form(...), customer_name: str = Form("")):
    """웹 폼 제출용: 결과 페이지에서 파싱 결과 보여주고 PDF 다운로드 링크 제공."""
    output_path, summary = _run_pipeline(inquiry_text, customer_name)

    line_items = parse_inquiry_text(inquiry_text, PRICE_TABLE)
    quote = build_quote(line_items, PRICE_TABLE)

    return HTMLResponse(render_template(
        "result.html",
        request=request,
        quote=quote,
        summary=summary,
        pdf_url=f"/download/{output_path.name}",
        inquiry_text=inquiry_text,
        customer_name=customer_name,
        lead_saved=False,
    ))


@app.get("/download/{filename}")
def download_pdf(filename: str):
    file_path = OUTPUT_DIR / filename
    if not file_path.exists():
        return JSONResponse({"error": "file not found"}, status_code=404)
    return FileResponse(str(file_path), media_type="application/pdf", filename=filename)


LEADS_FILE = OUTPUT_DIR / "leads.jsonl"


@app.post("/leads", response_class=HTMLResponse)
def submit_lead(request: Request, company: str = Form(...), contact: str = Form(...), message: str = Form("")):
    """도입 문의 리드 저장. Vercel 서버리스에서는 /tmp라 휘발성이지만,
    실제 운영 시 여기서 이메일 발송(SMTP)이나 외부 DB/시트 연동으로 교체하면 된다."""
    import json
    from datetime import datetime

    entry = {
        "company": company,
        "contact": contact,
        "message": message,
        "received_at": datetime.now().isoformat(),
    }
    try:
        with open(LEADS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 저장 실패해도 사용자에게는 접수 확인을 보여준다

    return HTMLResponse(render_template(
        "result.html",
        request=request,
        quote=None,
        summary=None,
        pdf_url=None,
        inquiry_text=None,
        customer_name=company,
        lead_saved=True,
    ))


@app.get("/api/leads")
def api_leads():
    """관리자 확인용: 저장된 리드 목록 반환 (인증 없음 - MVP 단계, 운영 시 반드시 인증 추가 필요)."""
    import json

    if not LEADS_FILE.exists():
        return {"leads": []}
    leads = []
    with open(LEADS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                leads.append(json.loads(line))
    return {"leads": leads, "count": len(leads)}


@app.get("/health")
def health():
    return {"status": "ok"}
