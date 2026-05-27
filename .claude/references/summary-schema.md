# Summary Schema

`artifacts/{date}/summary.json`과 `artifacts/history.db`의 공식 스키마. data-archivist와 viewer가 함께 참조한다. 이 파일을 단일 진실 공급원으로 삼는다.

## summary.json

```json
{
  "date": "2026-05-26",
  "metrics": {
    "total": 142,
    "positive": 95,
    "negative": 22,
    "mixed": 18,
    "unclear": 7,
    "ad_count": 17,
    "positive_ratio": 0.78,
    "ad_ratio": 0.12,
    "star": 4
  },
  "headline_quote": {
    "text": "비스포크 냉장고가 주방을 살린다",
    "source": "네이버블로그",
    "category": "냉장고"
  },
  "trend_summary": [
    "...", "...", "..."
  ],
  "category_sentiment": [
    {
      "category": "TV",
      "positive": 5,
      "negative": 2,
      "mixed": 1,
      "unclear": 0
    }
  ],
  "excerpts": {
    "positive": [
      {
        "text": "원문 그대로",
        "source": "네이버블로그",
        "category": "냉장고",
        "url": "https://..."
      }
    ],
    "negative": [
      {
        "text": "원문 그대로",
        "source": "카페",
        "category": "세탁기",
        "url": "https://..."
      }
    ]
  },
  "keywords": {
    "positive": [{"term": "디자인", "count": 12}],
    "negative": [{"term": "소음", "count": 7}]
  },
  "ad_warning": false
}
```

### 필드 규칙

| 필드 | 타입 | 비고 |
| --- | --- | --- |
| `date` | `YYYY-MM-DD` | history.db의 PRIMARY KEY |
| `metrics.total` | int | 광고성 포함 총 후기 수 |
| `metrics.positive_ratio` | float 0~1 | 광고성 제외 분모 |
| `metrics.star` | int 0~5 | `round(positive_ratio * 5)`, 0건이면 0 |
| `headline_quote` | object \| null | 발췌가 0건이면 null |
| `trend_summary` | string[] | 최대 3줄. 0건 일자는 `[]` |
| `excerpts.positive[]`, `excerpts.negative[]` | array | 광고성 제외, 카테고리당 최대 5건 → 총 상한 없음 |
| `excerpts[].url` | string \| null | 없으면 null |
| `ad_warning` | bool | `ad_ratio > 0.5`이면 true |

## SQLite 스키마 (history.db)

DDL은 `.claude/skills/data-archival/SKILL.md`의 "SQL DDL" 섹션에 멱등 형태로 정의되어 있다.

핵심 테이블:

- `daily_reports` — 일자별 메트릭 1행
- `category_sentiment` — `(date, category)` 복합 PK
- `excerpts` — 자동 증가 id, `date+sentiment+category`로 조회
- `keywords` — 자동 증가 id, `date+sentiment`로 조회

## 뷰어 쿼리 예시

### 메인 카드 그리드 (최근 7일)

```sql
SELECT date, total, positive_ratio, ad_ratio, star,
       headline_text, headline_source, headline_category, ad_warning
FROM daily_reports
ORDER BY date DESC
LIMIT 7;
```

### 일자 상세

```sql
-- 메타
SELECT * FROM daily_reports WHERE date = ?;

-- 카테고리 매트릭스
SELECT category, positive, negative, mixed, unclear
FROM category_sentiment WHERE date = ?
ORDER BY (positive+negative+mixed+unclear) DESC;

-- 긍정/부정 발췌 (좌우 2열)
SELECT category, source, text, url
FROM excerpts WHERE date = ? AND sentiment = 'positive'
ORDER BY category;

SELECT category, source, text, url
FROM excerpts WHERE date = ? AND sentiment = 'negative'
ORDER BY category;

-- 키워드
SELECT sentiment, term, count
FROM keywords WHERE date = ?
ORDER BY sentiment, count DESC;
```
