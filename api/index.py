"""Vercel Python 서버리스 함수 진입점.

Vercel의 Python 런타임은 `api/` 디렉토리 아래의 파일에서 WSGI/ASGI 호환
`app` 객체(혹은 `handler`)를 찾는다. 여기서는 기존 FastAPI 앱(app.main:app)을
그대로 재노출한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가해서 `app` 패키지를 import 할 수 있게 한다.
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app  # noqa: E402

# Vercel Python 런타임이 인식하는 이름은 'app' (ASGI) 이다.
__all__ = ["app"]
