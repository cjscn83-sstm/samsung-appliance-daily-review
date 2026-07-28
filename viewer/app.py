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
import os
import re
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

# DATABASE_URL(Supabase Postgres)이 있으면 Postgres, 없으면 로컬 SQLite 폴백.
DATABASE_URL = os.getenv("DATABASE_URL")
USE_PG = bool(DATABASE_URL)

app = FastAPI(title="Samsung Appliance Daily Review Viewer")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _mask_store(value: str | None) -> str:
    """텍스트 내 '삼성스토어 XX점' → '삼성스토어 **점' 으로 마스킹."""
    if not value:
        return ""
    return re.sub(r"삼성\s*스토어\s*\S*점", "삼성스토어 **점", value)

templates.env.filters["fmt_source"] = _mask_store
templates.env.filters["mask_store"] = _mask_store


class _Conn:
    """SQLite/Postgres 공통 커넥션 래퍼.

    Postgres일 때만 `?` 플레이스홀더를 `%s`로 변환한다(현 쿼리에 `?`·`%`
    리터럴이 없어 안전). 양쪽 모두 execute→fetchall/fetchone, dict(row)가 동작한다.
    """

    def __init__(self, raw: Any, is_pg: bool) -> None:
        self._raw = raw
        self._is_pg = is_pg

    def execute(self, sql: str, params: tuple = ()):  # noqa: ANN201
        if self._is_pg:
            sql = sql.replace("?", "%s")
        return self._raw.execute(sql, params)

    def close(self) -> None:
        self._raw.close()


def get_conn() -> _Conn:
    if USE_PG:
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
        return _Conn(raw, is_pg=True)

    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"history.db not found at {DB_PATH}. "
                "Run the orchestrator first (backfill mode) to populate data."
            ),
        )
    raw = sqlite3.connect(str(DB_PATH))
    raw.row_factory = sqlite3.Row
    return _Conn(raw, is_pg=False)


def fetch_recent_days(limit: int = 7) -> list[dict[str, Any]]:
    if not USE_PG and not DB_PATH.exists():
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


def fetch_categories() -> list[dict[str, Any]]:
    """전 기간 카테고리 목록 + 총 건수 (많은 순). 내비게이션·목록용."""
    if not USE_PG and not DB_PATH.exists():
        return []
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT category,
                   SUM(positive) AS positive, SUM(negative) AS negative,
                   SUM(mixed) AS mixed, SUM(unclear) AS unclear,
                   SUM(positive + negative + mixed + unclear) AS total
            FROM category_sentiment
            GROUP BY category
            ORDER BY total DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_category(category: str) -> dict[str, Any]:
    conn = get_conn()
    try:
        by_day = conn.execute(
            """
            SELECT date, positive, negative, mixed, unclear
            FROM category_sentiment WHERE category = ?
            ORDER BY date DESC LIMIT 14
            """,
            (category,),
        ).fetchall()
        if not by_day:
            raise HTTPException(status_code=404, detail=f"No data for category {category}")

        totals = conn.execute(
            """
            SELECT COALESCE(SUM(positive),0) AS positive,
                   COALESCE(SUM(negative),0) AS negative,
                   COALESCE(SUM(mixed),0) AS mixed,
                   COALESCE(SUM(unclear),0) AS unclear
            FROM category_sentiment WHERE category = ?
            """,
            (category,),
        ).fetchone()

        positive = conn.execute(
            "SELECT date, source, text, url FROM excerpts "
            "WHERE category = ? AND sentiment = 'positive' ORDER BY date DESC LIMIT 20",
            (category,),
        ).fetchall()
        negative = conn.execute(
            "SELECT date, source, text, url FROM excerpts "
            "WHERE category = ? AND sentiment = 'negative' ORDER BY date DESC LIMIT 20",
            (category,),
        ).fetchall()

        return {
            "totals": dict(totals),
            "by_day": [dict(r) for r in by_day],
            "excerpts_positive": [dict(r) for r in positive],
            "excerpts_negative": [dict(r) for r in negative],
        }
    finally:
        conn.close()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    days = fetch_recent_days(7)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "days": days,
            "categories": fetch_categories(),
            "db_missing": not USE_PG and not DB_PATH.exists(),
        },
    )


@app.get("/day/{date}", response_class=HTMLResponse)
def day_detail(request: Request, date: str):
    data = fetch_day(date)
    return templates.TemplateResponse(request, "day.html", {"date": date, **data})


@app.get("/api/days")
def api_days(limit: int = 7) -> JSONResponse:
    return JSONResponse(fetch_recent_days(limit))


@app.get("/api/day/{date}")
def api_day(date: str) -> JSONResponse:
    return JSONResponse(fetch_day(date))


@app.get("/category/{category:path}", response_class=HTMLResponse)
def category_detail(request: Request, category: str):
    data = fetch_category(category)
    return templates.TemplateResponse(
        request,
        "category.html",
        {"category": category, "categories": fetch_categories(), **data},
    )


@app.get("/api/category/{category:path}")
def api_category(category: str) -> JSONResponse:
    return JSONResponse(fetch_category(category))


if __name__ == "__main__":
    import uvicorn

    # 호스팅(Render 등)은 $PORT를 주입 → 0.0.0.0 바인드. 로컬은 127.0.0.1:8765.
    port = int(os.getenv("PORT", "8765"))
    host = "0.0.0.0" if os.getenv("PORT") else "127.0.0.1"
    uvicorn.run(app, host=host, port=port)
