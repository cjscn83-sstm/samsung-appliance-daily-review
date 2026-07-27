"""로컬 artifacts/history.db(SQLite) → Supabase(Postgres) 동기화.

재실행 가능·멱등. history.db에 있는 모든 날짜를 날짜별로 upsert 하므로,
Supabase에 이미 쌓인 다른 날짜는 보존된다(매일 클라우드 루틴이 하루치를 누적).

사용:
    # PowerShell:  $env:DATABASE_URL = "postgresql://postgres.xxxx:<PW>@...pooler.supabase.com:5432/postgres"
    # bash:        export DATABASE_URL="postgresql://..."
    python scripts/sync_supabase.py

연결 문자열은 Supabase → Settings → Database → Connection string 의 "Session pooler" 값을 쓴다.
절대 커밋하지 말 것(환경변수/시크릿으로만).
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

try:
    import psycopg
except ModuleNotFoundError:
    sys.exit("psycopg 가 필요합니다:  pip install \"psycopg[binary]\"")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "artifacts" / "history.db"

# SQLite → Postgres DDL (load_history.py 스키마 변환: REAL→DOUBLE PRECISION,
# AUTOINCREMENT→BIGSERIAL). date는 문자열 유지 위해 TEXT.
DDL = """
CREATE TABLE IF NOT EXISTS daily_reports (
  date TEXT PRIMARY KEY,
  total INTEGER NOT NULL,
  positive INTEGER NOT NULL,
  negative INTEGER NOT NULL,
  mixed INTEGER NOT NULL,
  unclear INTEGER NOT NULL,
  ad_count INTEGER NOT NULL,
  positive_ratio DOUBLE PRECISION NOT NULL,
  ad_ratio DOUBLE PRECISION NOT NULL,
  star INTEGER NOT NULL,
  headline_text TEXT,
  headline_source TEXT,
  headline_category TEXT,
  trend_summary_json TEXT,
  ad_warning INTEGER NOT NULL DEFAULT 0,
  summary_json_path TEXT,
  final_md_path TEXT,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS category_sentiment (
  date TEXT NOT NULL,
  category TEXT NOT NULL,
  positive INTEGER NOT NULL,
  negative INTEGER NOT NULL,
  mixed INTEGER NOT NULL,
  unclear INTEGER NOT NULL,
  PRIMARY KEY (date, category)
);
CREATE TABLE IF NOT EXISTS excerpts (
  id BIGSERIAL PRIMARY KEY,
  date TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK (sentiment IN ('positive','negative')),
  category TEXT NOT NULL,
  source TEXT,
  text TEXT NOT NULL,
  url TEXT
);
CREATE TABLE IF NOT EXISTS keywords (
  id BIGSERIAL PRIMARY KEY,
  date TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK (sentiment IN ('positive','negative')),
  term TEXT NOT NULL,
  count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_excerpts_date ON excerpts(date);
CREATE INDEX IF NOT EXISTS idx_keywords_date ON keywords(date);
"""

DAILY_COLS = [
    "date", "total", "positive", "negative", "mixed", "unclear", "ad_count",
    "positive_ratio", "ad_ratio", "star", "headline_text", "headline_source",
    "headline_category", "trend_summary_json", "ad_warning",
    "summary_json_path", "final_md_path", "created_at",
]


def upsert_date(pg: "psycopg.Connection", sl: sqlite3.Connection, date: str) -> None:
    """한 날짜의 4개 테이블을 Postgres에 upsert(날짜 단위 교체)."""
    dr = sl.execute("SELECT * FROM daily_reports WHERE date = ?", (date,)).fetchone()
    placeholders = ", ".join(["%s"] * len(DAILY_COLS))
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in DAILY_COLS if c != "date")
    pg.execute(
        f"INSERT INTO daily_reports ({', '.join(DAILY_COLS)}) VALUES ({placeholders}) "
        f"ON CONFLICT (date) DO UPDATE SET {updates}",
        tuple(dr[c] for c in DAILY_COLS),
    )

    pg.execute("DELETE FROM category_sentiment WHERE date = %s", (date,))
    for r in sl.execute(
        "SELECT category, positive, negative, mixed, unclear "
        "FROM category_sentiment WHERE date = ?", (date,)
    ).fetchall():
        pg.execute(
            "INSERT INTO category_sentiment (date, category, positive, negative, mixed, unclear) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (date, r["category"], r["positive"], r["negative"], r["mixed"], r["unclear"]),
        )

    pg.execute("DELETE FROM excerpts WHERE date = %s", (date,))
    for r in sl.execute(
        "SELECT sentiment, category, source, text, url FROM excerpts WHERE date = ?", (date,)
    ).fetchall():
        pg.execute(
            "INSERT INTO excerpts (date, sentiment, category, source, text, url) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (date, r["sentiment"], r["category"], r["source"], r["text"], r["url"]),
        )

    pg.execute("DELETE FROM keywords WHERE date = %s", (date,))
    for r in sl.execute(
        "SELECT sentiment, term, count FROM keywords WHERE date = ?", (date,)
    ).fetchall():
        pg.execute(
            "INSERT INTO keywords (date, sentiment, term, count) VALUES (%s, %s, %s, %s)",
            (date, r["sentiment"], r["term"], r["count"]),
        )


def main() -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL 환경변수가 없습니다. Supabase Session pooler 연결 문자열을 설정하세요.")
    if not DB_PATH.exists():
        sys.exit(f"{DB_PATH} 가 없습니다. 먼저 오케스트레이터로 데이터를 적재하세요.")

    sl = sqlite3.connect(str(DB_PATH))
    sl.row_factory = sqlite3.Row
    dates = [r["date"] for r in sl.execute("SELECT date FROM daily_reports ORDER BY date").fetchall()]
    if not dates:
        sys.exit("history.db에 daily_reports 행이 없습니다.")

    with psycopg.connect(url) as pg:  # 트랜잭션: 정상 종료 시 커밋, 예외 시 롤백
        pg.execute(DDL)  # 파라미터 없음 → 다중 문장 DDL 실행 가능
        for date in dates:
            upsert_date(pg, sl, date)
        counts = {
            t: pg.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()[0]
            for t in ("daily_reports", "category_sentiment", "excerpts", "keywords")
        }
    sl.close()

    print(f"Supabase 동기화 완료 — {len(dates)}개 날짜 upsert ({dates[0]} ~ {dates[-1]})")
    for t, n in counts.items():
        print(f"  {t}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
