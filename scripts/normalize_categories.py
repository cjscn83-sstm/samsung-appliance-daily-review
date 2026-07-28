"""artifacts/*/summary.json 의 카테고리명을 삼성 카테고리 트리 17개 세부 품목으로 정규화.

- "대분류 > 세부" 접두사 제거, 모델 괄호/변형 병합.
- category_sentiment 는 정규화 후 같은 품목끼리 합산, excerpts 는 라벨만 교체.
멱등(반복 실행 안전). 실행 후 load_history.py + sync_supabase.py 로 반영한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"

# 트리 세부 품목명(정본)으로의 특수 매핑 (대분류 접두사 제거 후 적용)
SPECIFIC = {
    "TV (더 프레임)": "TV",
    "TV (Neo QLED)": "TV",
    "더 프레임": "TV",
    "프로젝터/이동형 TV": "프로젝터",
    "세탁기": "세탁기/건조기",
    "건조기": "세탁기/건조기",
}


def canon(name: str) -> str:
    n = name.split(">")[-1].strip()  # "리빙가전 > 에어컨" → "에어컨"
    return SPECIFIC.get(n, n)


def normalize_summary(data: dict) -> dict:
    # category_sentiment: 정규화 후 품목별 합산
    merged: dict[str, dict] = {}
    for row in data.get("category_sentiment", []):
        c = canon(row["category"])
        acc = merged.setdefault(
            c, {"category": c, "positive": 0, "negative": 0, "mixed": 0, "unclear": 0}
        )
        for k in ("positive", "negative", "mixed", "unclear"):
            acc[k] += int(row.get(k, 0))
    data["category_sentiment"] = sorted(
        merged.values(),
        key=lambda r: r["positive"] + r["negative"] + r["mixed"] + r["unclear"],
        reverse=True,
    )

    # excerpts: 라벨 교체
    for pol in ("positive", "negative"):
        for e in data.get("excerpts", {}).get(pol, []):
            if e.get("category"):
                e["category"] = canon(e["category"])

    # headline_quote 카테고리
    hq = data.get("headline_quote")
    if hq and hq.get("category"):
        hq["category"] = canon(hq["category"])
    return data


def main() -> int:
    files = sorted(ARTIFACTS.glob("2026-*/summary.json"))
    if not files:
        sys.exit("summary.json 없음")
    changed = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        before = json.dumps(data, ensure_ascii=False, sort_keys=True)
        data = normalize_summary(data)
        after = json.dumps(data, ensure_ascii=False, sort_keys=True)
        if before != after:
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed += 1
    print(f"정규화 완료: {len(files)}개 중 {changed}개 파일 변경")
    return 0


if __name__ == "__main__":
    sys.exit(main())
