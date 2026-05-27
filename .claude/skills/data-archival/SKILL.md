---
name: data-archival
description: 일자별 final.md와 02-sentiment.md를 summary.json + SQLite(history.db)로 적재하는 절차. data-archivist가 사용한다.
---

# Data Archival

## 목적

리포트 텍스트(`final.md`, `02-sentiment.md`)에서 구조화 데이터를 추출해 누적 DB에 적재. 뷰어가 D-7 카드와 상세 발췌를 보여줄 수 있게 단일 진실 공급원을 만든다.

## 입력

- `date`
- `artifacts/{date}/final.md`
- `artifacts/{date}/02-sentiment.md`
- 스키마: `.claude/references/summary-schema.md`

## 산출물

- `artifacts/{date}/summary.json`
- `artifacts/history.db`

## 절차 요약

1. 02-sentiment.md 파싱 → 통계, 헤드라인, 매트릭스, 발췌, 키워드 추출
2. final.md에서 종합 트렌드 3줄 추출
3. summary.json 작성 (스키마 참조)
4. history.db 트랜잭션 upsert (daily_reports / category_sentiment / excerpts / keywords)
5. 성공 시 1줄 요약 출력

## SQL DDL (history.db 최초 생성 시)

```sql
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
  PRIMARY KEY (date, category),
  FOREIGN KEY (date) REFERENCES daily_reports(date)
);

CREATE TABLE IF NOT EXISTS excerpts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK(sentiment IN ('positive','negative')),
  category TEXT NOT NULL,
  source TEXT,
  text TEXT NOT NULL,
  url TEXT,
  FOREIGN KEY (date) REFERENCES daily_reports(date)
);

CREATE TABLE IF NOT EXISTS keywords (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  sentiment TEXT NOT NULL CHECK(sentiment IN ('positive','negative')),
  term TEXT NOT NULL,
  count INTEGER NOT NULL,
  FOREIGN KEY (date) REFERENCES daily_reports(date)
);

CREATE INDEX IF NOT EXISTS idx_excerpts_date ON excerpts(date);
CREATE INDEX IF NOT EXISTS idx_keywords_date ON keywords(date);
```

## Upsert 패턴

```sql
BEGIN;
INSERT INTO daily_reports (date, total, ...) VALUES (?, ?, ...)
ON CONFLICT(date) DO UPDATE SET total=excluded.total, ... ;

DELETE FROM category_sentiment WHERE date = ?;
INSERT INTO category_sentiment (date, category, ...) VALUES (?, ?, ...);

DELETE FROM excerpts WHERE date = ?;
INSERT INTO excerpts (date, sentiment, category, source, text, url) VALUES (?, ?, ?, ?, ?, ?);

DELETE FROM keywords WHERE date = ?;
INSERT INTO keywords (date, sentiment, term, count) VALUES (?, ?, ?, ?);
COMMIT;
```

## Python 실행 패턴

`sqlite3.exe`가 없을 수 있으니 Python을 기본으로 사용:

```python
import sqlite3, json, sys
from pathlib import Path

date = sys.argv[1]
root = Path("artifacts")
summary = json.loads((root / date / "summary.json").read_text(encoding="utf-8"))

db_path = root / "history.db"
conn = sqlite3.connect(str(db_path))
conn.executescript(open(".claude/references/_init.sql").read())  # DDL idempotent
cur = conn.cursor()
try:
    cur.execute("BEGIN")
    # upsert daily_reports / replace category_sentiment / excerpts / keywords
    # ...
    conn.commit()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
```

(편의상 DDL은 매번 `CREATE TABLE IF NOT EXISTS`로 멱등 실행.)

## 품질 기준

- 발췌 원문 무변형
- 같은 date 재실행 시 데이터 중복 없이 깔끔히 교체
- 트랜잭션 보장
- 광고성 발췌는 제외

## 검증

적재 직후 다음 쿼리로 자가 점검:

```sql
SELECT date, total, positive_ratio, ad_ratio,
       (SELECT COUNT(*) FROM excerpts WHERE date = d.date AND sentiment='positive') AS pos_excerpts,
       (SELECT COUNT(*) FROM excerpts WHERE date = d.date AND sentiment='negative') AS neg_excerpts
FROM daily_reports d
WHERE date = ?;
```

행이 1개고 발췌 카운트가 summary.json과 일치하면 통과.
