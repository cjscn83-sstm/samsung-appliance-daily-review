# artifacts/

Orchestrator가 실행될 때 단계별 산출물이 이 폴더에 쌓입니다. 초기에는 비어 있는 상태가 정상입니다.

## 생성 순서

1. `01-naver-raw.md` — 네이버 블로그 수집 결과 (naver-blog-researcher)
2. `01-web-raw.md` — 웹/카페/커뮤니티 수집 결과 (web-blog-researcher)
3. `02-sentiment.md` — 통합·중복제거·감성 분류 (sentiment-analyst)
4. `03-draft.md` — 리포트 초안 (report-writer)
5. `04-review.md` — 검토 결과 (report-reviewer)
6. `final.md` — 검토 통과 본문
7. `final.docx` — Word 디자인 (report-designer)
8. `final.pptx` — PPT 디자인 (report-designer)

이전 회차 파일을 보존하려면 실행 전 `artifacts/YYYY-MM-DD/`로 옮겨두면 됩니다.
