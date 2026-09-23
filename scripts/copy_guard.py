"""
카피 검증 모듈

규칙:
1. 모든 카피는 {"text": ..., "source": ...} 형식이어야 합니다.
   text 또는 source가 비어 있으면 렌더링하지 않습니다 (None 반환).
2. 금지 표현이 하나라도 포함되면 BannedCopyError를 발생시켜 생성을 중단합니다.
   공백/줄바꿈을 제거한 문자열로도 검사하여 "탈 모" 같은 우회도 차단합니다.
3. 카피를 수정·요약·보완하지 않습니다. 원문 그대로 통과시키거나 거부할 뿐입니다.
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


# 금지 표현 (탈모 관련 / 의학적 / 기능성화장품 암시)
BANNED_TERMS: List[str] = [
    "탈모",
    "발모",
    "육모",
    "양모",
    "모발성장",
    "모발재생",
    "모근",
    "두피치료",
    "치료",
    "재생",
    "예방",
    "개선",
    "완화",
    "증상",
    "기능성",
    "식약처",
    "의약",
    "의학",
    "임상",
    "처방",
    "hairloss",
    "hairgrowth",
    "regrowth",
    "antihairloss",
]


# 제품별 추가 금지 표현 (banned.txt 에서 로드)
EXTRA_BANNED_TERMS: List[str] = []


def set_extra_banned_terms(terms: Iterable[str]) -> None:
    """제품 입력의 금지 표현을 기본 목록에 추가합니다."""
    EXTRA_BANNED_TERMS[:] = [_normalize(t) for t in terms if t and t.strip()]


class BannedCopyError(ValueError):
    """금지 표현이 포함된 카피"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def find_banned_terms(text: str) -> List[str]:
    """텍스트에 포함된 금지 표현 목록을 반환합니다."""
    normalized = _normalize(text)
    return [term for term in BANNED_TERMS + EXTRA_BANNED_TERMS if term in normalized]


def resolve_copy(item: Any, field_name: str = "") -> Optional[str]:
    """
    카피 항목을 검증하고 렌더링할 텍스트를 반환합니다.

    Returns:
        원문 텍스트 (그대로) 또는 None (text/source 누락 시 렌더링 제외)

    Raises:
        BannedCopyError: 금지 표현 포함 시
    """
    if not isinstance(item, dict):
        if item not in (None, ""):
            print(f"[copy_guard] 제외: {field_name} - text/source 형식이 아님")
        return None

    text = item.get("text")
    source = item.get("source")

    if not isinstance(text, str) or not text.strip():
        return None
    if not isinstance(source, str) or not source.strip():
        print(f"[copy_guard] 제외: {field_name} - source 없음")
        return None

    banned = find_banned_terms(text)
    if banned:
        raise BannedCopyError(f"{field_name}: 금지 표현 포함 {banned}")

    return text


def iter_copy_items(node: Any, path: str = "") -> Iterable[Tuple[str, Dict]]:
    """브리프 전체에서 text 필드를 가진 카피 항목을 모두 찾습니다."""
    if isinstance(node, dict):
        if "text" in node:
            yield path, node
        for key, value in node.items():
            if key != "text":
                yield from iter_copy_items(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from iter_copy_items(value, f"{path}[{i}]")


def audit_brief(brief: Dict) -> None:
    """
    렌더링 전에 브리프 전체를 검사합니다.
    금지 표현이 하나라도 있으면 (source 유무와 무관하게) 중단합니다.
    """
    errors = []
    for path, item in iter_copy_items(brief):
        text = item.get("text")
        if isinstance(text, str):
            banned = find_banned_terms(text)
            if banned:
                errors.append(f"{path}: {banned}")
    if errors:
        raise BannedCopyError("금지 표현 발견 - 생성 중단\n" + "\n".join(errors))
