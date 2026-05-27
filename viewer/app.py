"""
Samsung Appliance Daily Review — Local Viewer

Run:
    python -m viewer.app
        → http://localhost:8765

Reads artifacts/history.db (created by data-archivist) and renders:
    /            testimonials card grid (last 7 days)
    /day/{date}  detail view with positive/negative excerpts
    /api/days    JSON for the last N days
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "artifacts" / "history.db"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Samsung Appliance Daily Review Viewer")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"history.db not found at {DB_PATH}. "
                "Run the orchestrator first (backfill mode) to populate data."
            ),
        )
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_recent_days(limit: int = 7) -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT date, total, positive, negative, mixed, unclear,
                   ad_count, positive_ratio, ad_ratio, star,
                   headline_text, headline_source, headline_category,
                   trend_summary_json, ad_warning
            FROM daily_reports
            ORDER BY date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_day(date: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        meta = conn.execute(
            "SELECT * FROM daily_reports WHERE date = ?", (date,)
        ).fetchone()
        if not meta:
            raise HTTPException(status_code=404, detail=f"No report for {date}")

        category = conn.execute(
            """
            SELECT category, positive, negative, mixed, unclear
            FROM category_sentiment WHERE date = ?
            ORDER BY (positive+negative+mixed+unclear) DESC
            """,
            (date,),
        ).fetchall()

        positive = conn.execute(
            """
            SELECT category, source, text, url
            FROM excerpts WHERE date = ? AND sentiment = 'positive'
            ORDER BY category
            """,
            (date,),
        ).fetchall()

        negative = conn.execute(
            """
            SELECT category, source, text, url
            FROM excerpts WHERE date = ? AND sentiment = 'negative'
            ORDER BY category
            """,
            (date,),
        ).fetchall()

        keywords_pos = conn.execute(
            "SELECT term, count FROM keywords WHERE date = ? AND sentiment = 'positive' ORDER BY count DESC LIMIT 10",
            (date,),
        ).fetchall()
        keywords_neg = conn.execute(
            "SELECT term, count FROM keywords WHERE date = ? AND sentiment = 'negative' ORDER BY count DESC LIMIT 10",
            (date,),
        ).fetchall()

        return {
            "meta": dict(meta),
            "trend_summary": json.loads(meta["trend_summary_json"] or "[]"),
            "category_sentiment": [dict(r) for r in category],
            "excerpts_positive": [dict(r) for r in positive],
            "excerpts_negative": [dict(r) for r in negative],
            "keywords_positive": [dict(r) for r in keywords_pos],
            "keywords_negative": [dict(r) for r in keywords_neg],
        }
    finally:
        conn.close()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    days = fetch_recent_days(7)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"days": days, "db_missing": not DB_PATH.exists()},
    )


DEMO_DAY = {
    "meta": {
        "date": "2026-05-26",
        "total": 142,
        "positive": 95,
        "negative": 22,
        "mixed": 18,
        "unclear": 7,
        "ad_count": 17,
        "positive_ratio": 0.78,
        "ad_ratio": 0.12,
        "star": 4,
        "headline_text": "비스포크 냉장고가 주방을 살린다",
        "headline_source": "네이버블로그",
        "headline_category": "냉장고",
        "ad_warning": False,
        "trend_summary_json": "[]",
    },
    "trend_summary": [
        "비스포크 라인업이 디자인 만족도를 견인",
        "건조기 소음에 대한 부정 의견 비중 상승",
        "AI 기능 키워드가 전 카테고리에서 등장",
    ],
    "category_sentiment": [
        {"category": "냉장고", "positive": 24, "negative": 3, "mixed": 5, "unclear": 1},
        {"category": "세탁기", "positive": 12, "negative": 9, "mixed": 4, "unclear": 1},
        {"category": "TV", "positive": 18, "negative": 2, "mixed": 3, "unclear": 0},
        {"category": "에어컨", "positive": 15, "negative": 2, "mixed": 2, "unclear": 1},
        {"category": "건조기", "positive": 8, "negative": 6, "mixed": 2, "unclear": 2},
        {"category": "전자레인지", "positive": 10, "negative": 0, "mixed": 1, "unclear": 1},
        {"category": "공기청정기", "positive": 8, "negative": 0, "mixed": 1, "unclear": 1},
    ],
    "excerpts_positive": [
        {"category": "냉장고", "source": "네이버블로그",
         "text": "비스포크 냉장고 색상 조합이 주방 인테리어를 완전히 바꿨다. 패널 교체도 직접 했는데 생각보다 쉬웠고 마감도 깔끔하다.",
         "url": "https://blog.naver.com/sample1"},
        {"category": "에어컨", "source": "티스토리",
         "text": "무풍 갤러리 진짜 바람 안 느껴짐. 직바람 싫어하는 우리집에 딱이다. 전기료도 생각보다 적게 나옴.",
         "url": "https://example.tistory.com/sample"},
        {"category": "TV", "source": "네이버블로그",
         "text": "네오 QLED 화질은 매장에서 본 것보다 집에서가 더 좋다. 명암비가 미쳤다.",
         "url": "https://blog.naver.com/sample2"},
        {"category": "공기청정기", "source": "카페",
         "text": "필터 교체 알림이 정확하고 앱 연동도 매끄럽다. 거실에 두기에 사이즈도 적당.",
         "url": "https://cafe.naver.com/sample"},
        {"category": "냉장고", "source": "브런치",
         "text": "정수기 일체형 모델로 바꿨더니 주방이 훨씬 정돈됨. 자동 제빙 속도도 만족.",
         "url": "https://brunch.co.kr/sample"},
    ],
    "excerpts_negative": [
        {"category": "세탁기", "source": "카페",
         "text": "세탁기 소음이 생각보다 크다. 야간에 돌리기는 좀 부담스러움. 진동도 있다.",
         "url": "https://cafe.naver.com/neg1"},
        {"category": "건조기", "source": "커뮤니티",
         "text": "건조 시간이 제품 설명서보다 항상 30분쯤 더 걸린다. 옷감 손상은 없지만 답답.",
         "url": "https://example.com/community/neg1"},
        {"category": "세탁기", "source": "티스토리",
         "text": "AI 코스가 알아서 잡는다는데 결과물은 일반 코스와 큰 차이 모르겠음.",
         "url": "https://example.tistory.com/neg"},
        {"category": "건조기", "source": "카페",
         "text": "콘덴서 자동세척 기능 있는데도 먼지가 자꾸 낌. AS 대기도 2주 걸렸다.",
         "url": "https://cafe.naver.com/neg2"},
    ],
    "keywords_positive": [
        {"term": "디자인", "count": 12},
        {"term": "AI 기능", "count": 9},
        {"term": "비스포크", "count": 8},
        {"term": "무풍", "count": 7},
        {"term": "조용함", "count": 5},
        {"term": "앱 연동", "count": 4},
    ],
    "keywords_negative": [
        {"term": "소음", "count": 7},
        {"term": "AS 대기", "count": 5},
        {"term": "건조 시간", "count": 4},
        {"term": "가격", "count": 3},
        {"term": "먼지", "count": 2},
    ],
}


@app.get("/day/{date}", response_class=HTMLResponse)
def day_detail(request: Request, date: str):
    if date == "demo" or not DB_PATH.exists():
        data = DEMO_DAY
        display_date = DEMO_DAY["meta"]["date"] if date == "demo" else date
    else:
        data = fetch_day(date)
        display_date = date
    return templates.TemplateResponse(
        request, "day.html", {"date": display_date, "is_demo": date == "demo" or not DB_PATH.exists(), **data}
    )


@app.get("/api/days")
def api_days(limit: int = 7) -> JSONResponse:
    return JSONResponse(fetch_recent_days(limit))


@app.get("/api/day/{date}")
def api_day(date: str) -> JSONResponse:
    return JSONResponse(fetch_day(date))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
