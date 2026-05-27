# Samsung Appliance Daily Review Harness

이 디렉터리는 삼성 가전제품(삼성닷컴 카테고리 트리: TV/영상∙음향, 주방가전, 리빙가전) 구매 후기를 네이버 블로그와 일반 웹·카페·커뮤니티에서 수집해, **일자별** 긍정/부정 트렌드 리포트를 만들고 **SQLite에 누적 적재**한 뒤, **FastAPI 로컬 뷰어**에서 testimonials 카드 + 상세 발췌로 볼 수 있게 하는 Claude Code 하네스다.

## 실행 모드

| 모드 | 트리거 | 범위 |
| --- | --- | --- |
| **Backfill** | `artifacts/history.db` 없음, 또는 "지난 7일/처음 실행" 명시 | D-7 ~ D-1 (7일) |
| **Daily** | DB 있음 + "어제/오늘자" 요청 | D-1 (1일) |

오케스트레이터가 자동 판정한다. 모드 결정 사실을 1줄로 사용자에게 알린 뒤 진행.

## 주요 위치

- 입구 스킬: `.claude/skills/samsung-appliance-daily-review-orchestrator/`
- 작업 스킬: `.claude/skills/{naver-blog-search, web-blog-search, sentiment-classification, daily-report-writing, report-review-checklist, report-design, data-archival}/`
- Agent: `.claude/agents/{naver-blog-researcher, web-blog-researcher, sentiment-analyst, report-writer, report-reviewer, report-designer, data-archivist}.md`
- 공용 참조: `.claude/references/samsung-category-tree.md`, `.claude/references/summary-schema.md`
- 일자 산출물: `artifacts/{YYYY-MM-DD}/01-naver-raw.md, 01-web-raw.md, 02-sentiment.md, 03-draft.md, 04-review.md, final.md, summary.json` (+ daily 모드만 `final.docx`, `final.pptx`)
- 누적 DB: `artifacts/history.db`
- 뷰어: `viewer/app.py` (`python -m viewer.app` → http://localhost:8765)

## 자연어 라우팅

스킬명을 직접 입력하지 않아도 다음 같은 요청이 오면 **반드시 `samsung-appliance-daily-review-orchestrator`를 먼저 사용**한다.

- "어제 삼성 가전 후기 리포트 만들어줘" → daily
- "삼성 가전 일일 후기 보고서 만들어줘" → daily (또는 DB 없으면 backfill)
- "지난 7일 가전 트렌드 보여줘" → backfill
- "처음부터 데이터 채워줘" → backfill
- "어제 가전 후기로 PPT 만들어줘" → daily

확인 질문이 필요한 경우:
- "이번 한 달" → 7일 backfill만 지원함을 알리고 진행 여부 확인
- "LG/타사 비교" → 삼성 전용 하네스 안내
- "특정 모델만" → 카테고리 매핑 확인

## 병렬 실행

backfill 모드는 **일자별로 독립**이므로 단계 내부에서 항상 병렬 실행한다.

- 2단계 수집: `naver + web` × 7일 = **14개 subagent 동시 호출**
- 3~5단계: 일자별 7개 동시 (단, 한 일자 내 4단계 작성↔5단계 검토 루프는 순차)
- 7단계 적재: 7개 동시 (DB는 단일 파일이므로 archivist가 트랜잭션·재시도로 직렬화)

병렬을 위해 같은 응답에서 여러 Agent 도구 호출을 한 번에 보낸다.

## 사용 흐름 (요약)

1. 자연어 요청 → 오케스트레이터 모드 판정
2. **수집 (병렬)**: 일자별 `naver-blog-researcher` + `web-blog-researcher`
3. **분석 (병렬)**: 일자별 `sentiment-analyst` (헤드라인 인용구 + 원문 발췌 풀 포함)
4. **작성 (병렬)**: 일자별 `report-writer`
5. **검토 (일자별 순차 루프)**: `report-reviewer`, 통과 시 final.md 승격
6. **디자인 (daily만)**: `report-designer` → final.docx + final.pptx
7. **적재 (병렬)**: `data-archivist` → summary.json + history.db
8. 보고 + 뷰어 안내

## 뷰어

```bash
pip install fastapi uvicorn jinja2
python -m viewer.app
```

- `/` — 최근 7일 testimonials 카드 (헤드라인 인용구 + 별점 + 메트릭)
- `/day/{date}` — 종합 트렌드 + 카테고리×감성 매트릭스 + **긍정/부정 발췌 2열** + 키워드
- `/api/days?limit=7`, `/api/day/{date}` — JSON

## 카테고리 트리 변경 시

`.claude/references/samsung-category-tree.md` 한 파일만 수정. 모든 Agent와 Skill이 이를 참조.

## 스키마 변경 시

`.claude/references/summary-schema.md`와 `.claude/skills/data-archival/SKILL.md`의 DDL을 함께 수정. 뷰어 쿼리도 같은 파일을 참조하므로 한 곳을 바꾸면 됨.

## 테스트 프롬프트

| 유형 | 프롬프트 | 기대 결과 |
| --- | --- | --- |
| 첫 실행 | "삼성 가전 후기 리포트 만들어줘" (DB 없음) | backfill 모드, 7일치 적재, 뷰어 안내 |
| 매일 | "어제 가전 후기 정리해줘" (DB 있음) | daily 모드, D-1 1일치 추가, Word+PPT |
| 명시 backfill | "지난 7일 다시 채워줘" | backfill 재실행, 7일 upsert |
| 애매 | "이번 달 가전 트렌드" | "7일 backfill만 지원, 진행할까요?" 확인 |
| 실패 위험 | "LG와 비교" | 삼성 전용 안내, 진행 여부 확인 |

## 개선 기록

```md
- 날짜:
- 실행한 요청:
- 모드:
- 기대한 결과:
- 실제 결과:
- 잘된 점:
- 막힌 점:
- 다음 버전에서 바꿀 규칙:
```
