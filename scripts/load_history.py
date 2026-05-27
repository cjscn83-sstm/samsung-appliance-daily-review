"""Load summary.json files from artifacts/{date}/ into artifacts/history.db."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"
DB_PATH = ARTIFACTS / "history.db"

DDL = """
CREATE TABLE IF NOT EXISTS daily_reports (
  date TEXT PRIMARY KEY,
  total INTEGER NOT NULL,
  positive INTEGER NOT NULL,
  negative INTEGER NOT NULL,
  mixed INTEGER NOT NULL,
  unclear INTEGER NOT NULL,
  ad_count INTEGER NOT NULL,
  positive_ratio REAL NOT NULL,
  ad_ratio REAL NOT NULL,
  star INTEGER NOT NULL,
  headline_text TEXT,
  headline_source TEXT,
  headline_category TEXT,
  trend_summary_json TEXT,
  ad_warning INTEGER NOT NULL DEFAULT 0,
  summary_json_path TEXT NOT NULL,
  final_md_path TEXT,
  created_at TEXT NOT NULL
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
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK(sentiment IN ('positive','negative')),
  category TEXT NOT NULL,
  source TEXT,
  text TEXT NOT NULL,
  url TEXT
);
CREATE TABLE IF NOT EXISTS keywords (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK(sentiment IN ('positive','negative')),
  term TEXT NOT NULL,
  count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_excerpts_date ON excerpts(date);
CREATE INDEX IF NOT EXISTS idx_keywords_date ON keywords(date);
"""


def upsert(conn: sqlite3.Connection, summary: dict, paths: dict) -> None:
    date = summary["date"]
    m = summary["metrics"]
    hq = summary.get("headline_quote") or {}
    conn.execute(
        """
        INSERT INTO daily_reports
        (date, total, positive, negative, mixed, unclear, ad_count,
         positive_ratio, ad_ratio, star,
         headline_text, headline_source, headline_category,
         trend_summary_json, ad_warning,
         summary_json_path, final_md_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
          total=excluded.total, positive=excluded.positive,
          negative=excluded.negative, mixed=excluded.mixed,
          unclear=excluded.unclear, ad_count=excluded.ad_count,
          positive_ratio=excluded.positive_ratio,
          ad_ratio=excluded.ad_ratio, star=excluded.star,
          headline_text=excluded.headline_text,
          headline_source=excluded.headline_source,
          headline_category=excluded.headline_category,
          trend_summary_json=excluded.trend_summary_json,
          ad_warning=excluded.ad_warning,
          summary_json_path=excluded.summary_json_path,
          final_md_path=excluded.final_md_path,
          created_at=excluded.created_at
        """,
        (
            date,
            m["total"], m["positive"], m["negative"], m["mixed"], m["unclear"],
            m["ad_count"], m["positive_ratio"], m["ad_ratio"], m["star"],
            hq.get("text"), hq.get("source"), hq.get("category"),
            json.dumps(summary.get("trend_summary") or [], ensure_ascii=False),
            1 if summary.get("ad_warning") else 0,
            paths["summary"], paths["final"],
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.execute("DELETE FROM category_sentiment WHERE date = ?", (date,))
    for row in summary.get("category_sentiment", []):
        conn.execute(
            "INSERT INTO category_sentiment (date, category, positive, negative, mixed, unclear) VALUES (?, ?, ?, ?, ?, ?)",
            (date, row["category"], row["positive"], row["negative"], row["mixed"], row["unclear"]),
        )
    conn.execute("DELETE FROM excerpts WHERE date = ?", (date,))
    for sentiment in ("positive", "negative"):
        for e in summary.get("excerpts", {}).get(sentiment, []):
            conn.execute(
                "INSERT INTO excerpts (date, sentiment, category, source, text, url) VALUES (?, ?, ?, ?, ?, ?)",
                (date, sentiment, e.get("category", ""), e.get("source"), e["text"], e.get("url")),
            )
    conn.execute("DELETE FROM keywords WHERE date = ?", (date,))
    for sentiment in ("positive", "negative"):
        for k in summary.get("keywords", {}).get(sentiment, []):
            conn.execute(
                "INSERT INTO keywords (date, sentiment, term, count) VALUES (?, ?, ?, ?)",
                (date, sentiment, k["term"], k["count"]),
            )


def main() -> int:
    summaries = sorted(ARTIFACTS.glob("2026-*/summary.json"))
    if not summaries:
        print("No summary.json files found.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(DDL)
    inserted = []
    try:
        conn.execute("BEGIN")
        for path in summaries:
            date = path.parent.name
            with path.open(encoding="utf-8") as f:
                summary = json.load(f)
            final_md = path.parent / "final.md"
            upsert(
                conn,
                summary,
                {
                    "summary": str(path.relative_to(ROOT)).replace("\\", "/"),
                    "final": str(final_md.relative_to(ROOT)).replace("\\", "/") if final_md.exists() else None,
                },
            )
            inserted.append((date, summary["metrics"]["total"], summary["metrics"]["positive_ratio"], summary["metrics"]["star"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"Loaded {len(inserted)} days into {DB_PATH}")
    for date, total, pr, star in inserted:
        print(f"  {date}: total={total}, positive_ratio={pr:.2f}, star={star}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
