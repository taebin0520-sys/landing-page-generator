"""
최종 QA 모듈

검사 항목:
1. 원문 대조: 렌더링된 모든 카피가 입력 원문에 그대로 존재하는지 (공백/줄바꿈 차이만 허용)
2. 금지어: 렌더링된 모든 텍스트 (구조 라벨 포함)
3. 원문 누락: 기획본에서 분류된 카피 중 렌더링되지 않은 항목
4. 사진: 렌더 결과의 사진 영역이 크롭/리사이즈 결과와 동일한지, 확대 여부
5. 크기: 모든 섹션과 최종 이미지 너비 1200px
"""

import re
from typing import Dict, List

from scripts.copy_guard import find_banned_terms

PIXEL_TOLERANCE = 0.5
UPSCALE_WARNING = 1.05


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


def run_qa(results: List[Dict], brief: Dict, source_texts: Dict[str, str],
           final_size=None) -> Dict:
    corpus = _norm("\n".join(source_texts.values()))
    verbatim_fail, banned_hits, photo_issues, width_issues = [], [], [], []
    rendered_texts = set()

    for result in results:
        if result["size"][0] != 1200:
            width_issues.append(f"{result['id']}: {result['size'][0]}px")
        for item in result["copies"]:
            rendered_texts.add(_norm(item["text"]))
            hits = find_banned_terms(item["text"])
            if hits:
                banned_hits.append({"section": result["id"], "text": item["text"], "banned": hits})
            if not item.get("structural") and _norm(item["text"]) not in corpus:
                verbatim_fail.append({"section": result["id"], "field": item["field"], "text": item["text"]})
        photo = result.get("photo")
        if photo:
            if photo["pixel_diff"] > PIXEL_TOLERANCE:
                photo_issues.append(f"{result['id']}: 사진 픽셀 차이 {photo['pixel_diff']}")
            if photo["scale"] > UPSCALE_WARNING:
                photo_issues.append(f"{result['id']}: 사진 {photo['scale']}배 확대 (화질 저하 가능)")

    # 원문 누락: 브리프에 있지만 렌더링되지 않은 카피
    not_rendered = []

    def walk(node, section_id):
        if isinstance(node, dict):
            if "text" in node and "source" in node:
                if node["text"] and _norm(node["text"]) not in rendered_texts:
                    not_rendered.append({"section": section_id, "text": node["text"], "source": node["source"]})
                return
            for v in node.values():
                walk(v, section_id)
        elif isinstance(node, list):
            for v in node:
                walk(v, section_id)

    for section in brief["sections"]:
        walk({k: v for k, v in section.items() if k not in ("image", "layout")}, section["id"])

    if final_size and final_size[0] != 1200:
        width_issues.append(f"final_page: {final_size[0]}px")

    passed = not (verbatim_fail or banned_hits or width_issues
                  or any("픽셀 차이" in p for p in photo_issues))
    return {
        "passed": passed,
        "verbatim_fail": verbatim_fail,
        "banned_hits": banned_hits,
        "not_rendered": not_rendered,
        "photo_issues": photo_issues,
        "width_issues": width_issues,
        "structural_labels": sorted({i["text"] for r in results for i in r["copies"] if i.get("structural")}),
    }
