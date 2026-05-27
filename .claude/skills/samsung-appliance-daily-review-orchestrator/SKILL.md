---
name: samsung-appliance-daily-review-orchestrator
description: 삼성 가전제품 구매 후기를 네이버 블로그와 일반 웹 블로그에서 수집해 일자별 긍정/부정 트렌드 리포트를 만들고 SQLite에 적재한다. 첫 실행은 D-7 backfill, 이후는 D-1 daily 모드로 동작한다. "삼성 가전 후기 정리해줘", "어제 가전 트렌드 리포트 만들어줘", "지난 7일 가전 후기 보여줘" 같은 자연어 요청에 사용한다.
---

# Samsung Appliance Daily Review Orchestrator

## 목적

삼성 가전제품 구매 후기를 일자별로 수집·분석·작성·검토·디자인·적재까지 처리해, 누적된 SQLite + 일자 폴더 산출물로 만든다. FastAPI 뷰어가 이 데이터를 testimonials 카드 + 상세 화면으로 표시한다.

## 두 가지 실행 모드

요청을 받으면 먼저 모드를 판정한다.

### Backfill 모드 (첫 실행 또는 명시적 요청)

판정 조건:
- `artifacts/history.db`가 존재하지 않는다 → 자동 backfill
- 사용자가 "지난 7일", "D-7", "backfill" 등을 명시
- 사용자가 "처음 실행" 의도를 보임

동작:
- 대상 날짜 = D-7부터 D-1까지 7일
- 7개 일자를 병렬로 처리

### Daily 모드 (이후 매일)

판정 조건:
- `artifacts/history.db`가 이미 존재하고
- 사용자가 "어제", "오늘자" 등 단일 일자만 요청

동작:
- 대상 날짜 = D-1 1일
- 적재 후 DB에서 가장 오래된 D-8 이전 데이터는 유지 (삭제 안 함, 누적)

## 입력

- 사용자 요청
- 오늘 날짜 → D-1 또는 D-7~D-1 산출
- 카테고리 트리: `.claude/references/samsung-category-tree.md`
- 요약 스키마: `.claude/references/summary-schema.md`

## 실행 흐름

### 0단계. 모드 판정

`artifacts/history.db` 존재 여부와 사용자 요청 문구를 보고 backfill/daily 결정. 결정 사실을 사용자에게 1줄로 알린다.

### 1단계. 준비

1. 대상 날짜 목록 산출 (backfill: 7일, daily: 1일).
2. 각 날짜마다 출력 디렉터리 생성: `artifacts/{YYYY-MM-DD}/`.
3. 카테고리 트리를 읽어 세부 품목 확인.

### 2단계. 수집 (병렬)

각 대상 날짜 D에 대해:
- `naver-blog-researcher` subagent — 입력: 날짜 D → 출력: `artifacts/{D}/01-naver-raw.md`
- `web-blog-researcher` subagent — 입력: 날짜 D → 출력: `artifacts/{D}/01-web-raw.md`

**병렬 규칙**:
- backfill 모드: `날짜 × 리서처 = 14개`를 한 메시지에서 동시에 호출 (subagent 호출은 한 응답에 모두 담아 병렬 실행)
- daily 모드: 2개 리서처를 동시에

### 3단계. 분석 (일자별 병렬)

각 날짜 D에 대해 `sentiment-analyst` subagent → `artifacts/{D}/02-sentiment.md`.
- backfill 모드: 7개를 한 메시지에서 동시 호출.
- 분석은 수집 완료 후에만 시작 (2단계 의존).

### 4단계. 작성 (일자별 병렬)

`report-writer` subagent → `artifacts/{D}/03-draft.md`. 일자별 병렬.

### 5단계. 검토 (일자별 순차)

`report-reviewer` subagent → `artifacts/{D}/04-review.md`. 한 일자 내에서 REVISE → 재작성 루프(최대 2회). 일자 간에는 병렬 가능.

PASS 시 `03-draft.md`를 `artifacts/{D}/final.md`로 복사.

### 6단계. 디자인 (선택, 일자별 병렬)

`report-designer` subagent → `artifacts/{D}/final.docx`, `final.pptx`.

기본 정책:
- backfill 모드: 디자인 단계 **생략** (7일치 docx/pptx는 양이 많고 뷰어가 final.md를 직접 렌더링). 사용자가 명시 요청하면 진행.
- daily 모드: 평소대로 진행.

### 7단계. 적재 (필수, 일자별 병렬)

`data-archivist` subagent → `artifacts/{D}/summary.json` 생성 + `artifacts/history.db`에 upsert.

스키마는 `.claude/references/summary-schema.md` 참조. 동일 일자 재실행 시 upsert(덮어쓰기).

### 8단계. 보고

backfill 모드 보고:
- 적재한 일자 수 / 총 후기 건수 / 전체 긍정 비율
- 일자별 1줄 요약 7개
- 뷰어 실행 안내: `python -m viewer.app` → `http://localhost:8765`

daily 모드 보고:
- 어제 날짜와 메트릭
- 산출물 경로 (final.md, final.docx, final.pptx)
- 누적 일자 수
- 뷰어 링크

## 파일 기반 산출물 (일자 폴더 구조)

```
artifacts/
├── history.db                          ← SQLite 누적 인덱스
├── 2026-05-20/
│   ├── 01-naver-raw.md
│   ├── 01-web-raw.md
│   ├── 02-sentiment.md
│   ├── 03-draft.md
│   ├── 04-review.md
│   ├── final.md
│   └── summary.json                    ← 뷰어용
├── 2026-05-21/
│   └── ...
└── 2026-05-26/
    ├── ...
    ├── final.md
    ├── final.docx                      ← daily 모드만
    ├── final.pptx                      ← daily 모드만
    └── summary.json
```

## 병렬 실행 가이드

한 응답에서 여러 subagent를 동시에 호출하려면 **하나의 메시지 안에 여러 Agent 도구 호출**을 함께 넣는다. backfill 모드 2단계 예시 (의사 코드):

```
[같은 메시지에 14개 호출]
Agent(naver-blog-researcher, date=2026-05-20)
Agent(web-blog-researcher,   date=2026-05-20)
Agent(naver-blog-researcher, date=2026-05-21)
Agent(web-blog-researcher,   date=2026-05-21)
... (D-7 ~ D-1)
```

각 단계 사이에는 의존성이 있어 순차로 가지만, **단계 내부는 항상 일자 병렬**.

## 실패 처리

- **수집 0건 (일자 단위)**: 해당 일자만 `summary.json`에 `total: 0`으로 적재하고 다음 일자 진행. 모든 일자 0건이면 사용자에게 보고.
- **검토 2회 연속 REVISE**: 해당 일자만 멈추고 다른 일자는 계속. 마지막 보고에서 실패 일자 명시.
- **광고성 비중 50% 초과**: 해당 일자 final.md 상단에 경고 배너, summary.json에 `ad_warning: true`.
- **DB 락 충돌**: data-archivist가 트랜잭션 재시도 3회. 그래도 실패하면 summary.json만 남기고 다음 실행 때 일괄 재적재.
- **디자인 단계 실패**: final.md / summary.json은 살린 채 디자인만 실패 보고.

## 사람이 확인해야 하는 지점

- 모든 일자에서 검토 2회 연속 REVISE
- 모든 일자에서 수집 0건
- backfill 모드인데 사용자가 디자인까지 요구한 경우 (시간/비용 안내 후 진행)
- 타사 비교, 1개월 등 범위 외 요청

## 모드 판정 체크리스트

| 상황 | 모드 |
| --- | --- |
| `history.db` 없음 + "리포트 만들어줘" | backfill |
| `history.db` 있음 + "어제 리포트" | daily |
| `history.db` 있음 + "다시 7일치 채워줘" | backfill (재실행) |
| `history.db` 있음 + 특정 과거 일자 | 해당 일자 1개만 backfill 로직 (단일 일자) |
