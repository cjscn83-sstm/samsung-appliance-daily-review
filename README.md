# Samsung Appliance Daily Review Harness

Claude Code 하네스 실습 프로젝트. 어제 날짜 기준 삼성 가전제품 구매 후기를 네이버 블로그와 일반 웹·카페·커뮤니티에서 수집해, 일자별 긍정/부정 트렌드 리포트를 만들고 SQLite에 누적 적재한 뒤, FastAPI 로컬 뷰어에서 testimonials 카드와 상세 발췌로 조회할 수 있게 한다.

## 구조

```
.claude/
├── agents/              naver-blog-researcher, web-blog-researcher,
│                        sentiment-analyst, report-writer, report-reviewer,
│                        report-designer, data-archivist
├── skills/              orchestrator + 7개 작업 스킬
├── references/          카테고리 트리, summary-schema
└── CLAUDE.md

viewer/                  FastAPI 로컬 뷰어 (testimonials 카드 + D-7 상세)
scripts/load_history.py  summary.json → SQLite 일괄 적재
artifacts/               일자별 산출물 + history.db
```

## 실행 모드

| 모드 | 트리거 | 범위 |
| --- | --- | --- |
| Backfill | `history.db` 없음 또는 "지난 7일" 명시 | D-7 ~ D-1 |
| Daily | DB 있음 + "어제 리포트" | D-1 |

## 사용

Claude Code에서:

```
삼성 가전 후기 리포트 만들어줘
```

→ orchestrator가 자동 판정·실행.

뷰어 실행:

```bash
pip install fastapi uvicorn jinja2
python -m viewer.app
# http://127.0.0.1:8765
```

## 데이터 흐름

```
수집 (병렬, 일자×리서처)
  → 감성 분석 (일자별 병렬)
    → 리포트 작성 (일자별 병렬)
      → 검토 (REVISE 루프, 일자별)
        → final.md
          → data-archivist (summary.json + history.db upsert)
            → FastAPI 뷰어가 SQLite에서 조회
```

## 카테고리 트리

삼성닷컴 기준 17개 세부 품목 (TV/영상·음향, 주방가전, 리빙가전). 변경 시 `.claude/references/samsung-category-tree.md` 한 파일만 수정.
