"""
제품 입력 자료 로드 · 검증 · 섹션 자동 분류 모듈

입력 폴더 (references/private/<product>/, 커밋 금지):
    product_name.txt   제품명 원문 (필수)
    plan.md            상세페이지 전체 기획본 (필수)
    ingredients.txt    전성분 원문 (필수)
    how_to_use.txt     사용방법 원문 (필수)
    product_info.txt   제품정보/주의사항 원문 (필수, "항목: 내용" 줄 단위)
    banned.txt         추가 금지 표현 (선택, 한 줄에 하나)
    design.json        디자인 참고사항 / 사진·크롭·레이아웃 지정 (선택)
    photos/            제품 사진 (필수, 1장 이상)

원칙:
- 원문을 요약·수정·보완하지 않습니다. 줄 단위로 잘라 섹션/필드에 배치만 합니다.
- 모든 카피에는 입력 파일과 위치를 source로 기록합니다.
- "이런 분께 추천" 류 섹션은 분류 단계에서 제외합니다.
- 금지 표현이 포함된 마케팅 카피는 제외하고 기록합니다.
  법정 표기(전성분·사용방법·제품정보)에 금지 표현이 있으면 빌드를 중단합니다.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.copy_guard import find_banned_terms, set_extra_banned_terms

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_ROOT = PROJECT_ROOT / "references" / "private"
PHOTO_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

REQUIRED_FILES = {
    "product_name.txt": "제품명",
    "plan.md": "상세페이지 기획본",
    "ingredients.txt": "전성분",
    "how_to_use.txt": "사용방법",
    "product_info.txt": "제품정보/주의사항",
}

# 섹션 순서 (기본 구성)
SECTION_ORDER = [
    "hero", "intro", "product", "key_points", "detail",
    "ingredients", "how_to_use", "faq", "product_info", "closing",
]

# 기획본 섹션 제목 → 섹션 타입 (먼저 매칭되는 항목 우선)
SECTION_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("excluded", ["추천", "이런 분", "이런분", "타깃", "타겟"]),
    ("hero", ["히어로", "hero", "메인", "첫 화면", "첫화면"]),
    ("intro", ["도입", "intro", "인트로", "공감"]),
    ("key_points", ["사용감", "포인트", "texture", "key", "특징"]),
    ("detail", ["디테일", "detail", "용기", "노즐"]),
    ("ingredients", ["전성분", "성분", "ingredient"]),
    ("how_to_use", ["사용법", "사용 방법", "사용방법", "how to", "how_to"]),
    ("faq", ["faq", "자주 묻는", "질문"]),
    ("product_info", ["제품 정보", "제품정보", "고시", "주의사항"]),
    ("closing", ["클로징", "closing", "마무리", "엔딩"]),
    ("product", ["제품 소개", "제품소개", "소개", "product"]),
]

# 필드 라벨 → 필드명 (먼저 매칭되는 항목 우선)
FIELD_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("source", ["출처"]),
    ("spec", ["용량", "규격"]),
    ("product_name", ["제품명"]),
    ("eyebrow", ["소제목", "상단 문구"]),
    ("headline", ["헤드라인", "타이틀", "제목"]),
    ("subcopy", ["본문", "서브", "설명", "카피"]),
    ("point", ["포인트"]),
    ("step", ["단계", "스텝", "step"]),
    ("question", ["q", "질문"]),
    ("answer", ["a", "답변"]),
]

NONE_VALUES = {"없음", "-", "n/a", "해당 없음", "해당없음"}


class InputError(ValueError):
    """제작이 불가능한 입력 누락/오류"""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()


def _copy(text: str, source: str) -> Dict:
    return {"text": text, "source": source}


# ---------------------------------------------------------------------------
# 입력 로드 / 검증
# ---------------------------------------------------------------------------

def load_input(product: str, input_root: Path = INPUT_ROOT) -> Dict:
    """제품 입력 폴더를 읽고 필수 항목을 검증합니다. 누락 시 InputError."""
    base = input_root / product
    if not base.is_dir():
        raise InputError(f"입력 폴더 없음: {base}")

    missing = []
    data: Dict = {"product": product, "base": str(base), "files": {}}
    for name, label in REQUIRED_FILES.items():
        path = base / name
        if not path.is_file() or not _read(path):
            missing.append(f"{label} ({name})")
        else:
            data["files"][name] = _read(path)

    photos_dir = base / "photos"
    photos = sorted(
        p for p in photos_dir.glob("*") if p.suffix.lower() in PHOTO_EXTS
    ) if photos_dir.is_dir() else []
    if not photos:
        missing.append("제품 사진 (photos/)")
    data["photos"] = [str(p.relative_to(PROJECT_ROOT)) for p in photos]

    if missing:
        raise InputError("필수 입력 누락 - 제작 불가:\n- " + "\n- ".join(missing))

    banned_path = base / "banned.txt"
    data["banned"] = [
        line.strip() for line in _read(banned_path).splitlines()
        if line.strip() and not line.startswith("#")
    ] if banned_path.is_file() else []

    design_path = base / "design.json"
    data["design"] = json.loads(_read(design_path)) if design_path.is_file() else {}
    return data


# ---------------------------------------------------------------------------
# 기획본 파싱
# ---------------------------------------------------------------------------

def classify_heading(heading: str) -> Optional[str]:
    lowered = heading.lower()
    for section_type, keywords in SECTION_KEYWORDS:
        if any(k in lowered for k in keywords):
            return section_type
    number = re.search(r"(\d+)\s*번", heading) or re.match(r"\s*(\d+)[.)]", heading)
    if number:
        index = int(number.group(1)) - 1
        if 0 <= index < len(SECTION_ORDER):
            return SECTION_ORDER[index]
    return None


def classify_field(label: str) -> Optional[str]:
    lowered = label.strip().lower()
    for field, keywords in FIELD_KEYWORDS:
        for k in keywords:
            if len(k) == 1:  # Q / A 는 라벨 전체가 일치할 때만
                if lowered == k:
                    return field
            elif k in lowered:
                return field
    return None


HEADING_RE = re.compile(r"^\s*(#{1,6})\s*(.+?)\s*#*\s*$")
BRACKET_RE = re.compile(r"^\s*\[(.+?)\]\s*$")
LABEL_RE = re.compile(r"^\s*(?:[-*•]\s*)?([^:：]{1,20})[:：]\s*(.*)$")


def parse_plan(text: str, filename: str = "plan.md") -> Tuple[Dict[str, Dict], List[Dict]]:
    """
    기획본을 섹션별 원문으로 분류합니다.

    지원 형식:
        ## 히어로            또는  [1번 섹션] / [히어로]
        헤드라인: 문구        (다음 줄들은 빈 줄 전까지 같은 필드로 이어짐)
        [헤드라인]           (라벨만 있는 줄 → 다음 줄부터 값)
        포인트: 제목 | 설명
        Q: 질문 / A: 답변
        출처: 확정 기획본 1페이지   (해당 섹션 전체 카피의 source)

    Returns:
        (sections, notes)  notes: 분류하지 못했거나 제외한 줄 기록
    """
    sections: Dict[str, Dict] = {}
    notes: List[Dict] = []
    current: Optional[Dict] = None
    field: Optional[str] = None

    def start_section(heading: str, line_no: int) -> Optional[Dict]:
        section_type = classify_heading(heading)
        if section_type is None:
            notes.append({"line": line_no, "text": heading, "reason": "섹션 분류 불가 - 제외"})
            return {"type": None, "fields": {}, "heading": heading}
        if section_type == "excluded":
            notes.append({"line": line_no, "text": heading, "reason": "추천 대상 섹션 - 생성 금지 규칙으로 제외"})
            return {"type": None, "fields": {}, "heading": heading}
        sec = sections.setdefault(section_type, {"type": section_type, "fields": {}, "heading": heading,
                                                 "line": line_no, "source": None})
        return sec

    def add_value(sec: Dict, fld: str, value: str, line_no: int, append: bool) -> None:
        fields = sec["fields"]
        if fld == "source":
            sec["source"] = value
            return
        if fld in ("point", "step", "question", "answer"):
            items = fields.setdefault(fld, [])
            if append and items:
                items[-1]["text"] += "\n" + value
            else:
                items.append({"text": value, "line": line_no})
            return
        if append and fld in fields:
            fields[fld]["text"] += "\n" + value
        else:
            if fld in fields:
                notes.append({"line": line_no, "text": value, "reason": f"{fld} 중복 - 첫 번째만 사용"})
                return
            fields[fld] = {"text": value, "line": line_no}

    for line_no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            field = None
            continue

        heading = HEADING_RE.match(line)
        bracket = BRACKET_RE.match(line)
        if heading or bracket:
            title = (heading or bracket).group(heading and 2 or 1)
            if bracket and classify_field(title) and not classify_heading(title):
                field = classify_field(title)  # [헤드라인] 같은 라벨 줄
                continue
            current = start_section(title, line_no)
            field = None
            continue

        if current is None:
            notes.append({"line": line_no, "text": line.strip(), "reason": "섹션 제목 이전 줄 - 제외"})
            continue

        label = LABEL_RE.match(line)
        if label and classify_field(label.group(1)):
            field = classify_field(label.group(1))
            value = label.group(2).strip()
            if value.lower() in NONE_VALUES:
                field = None
                continue
            if value and current["type"]:
                add_value(current, field, value, line_no, append=False)
            elif value and field != "source":
                notes.append({"line": line_no, "text": value, "reason": f"제외 섹션 '{current['heading']}'의 문구"})
            if field == "source":
                field = None
            continue

        value = line.strip()
        if value.lower() in NONE_VALUES:
            field = None
            continue
        if not current["type"]:
            notes.append({"line": line_no, "text": value, "reason": f"제외 섹션 '{current['heading']}'의 문구"})
            continue
        if field is None:
            # 라벨 없는 줄: 헤드라인이 없으면 헤드라인, 있으면 본문
            field = "headline" if "headline" not in current["fields"] else "subcopy"
            add_value(current, field, value, line_no, append=field in current["fields"])
        elif field == "step":
            add_value(current, field, value, line_no, append=False)  # 단계는 줄마다 새 항목
        else:
            add_value(current, field, value, line_no, append=bool(current["fields"].get(field)))

    # source 부여
    for sec in sections.values():
        default_source = f"{filename} '{sec['heading']}' 섹션"
        source = sec.get("source") or default_source
        fields = sec["fields"]
        for key, value in list(fields.items()):
            if isinstance(value, list):
                for item in value:
                    item["source"] = source if sec.get("source") else f"{default_source} {item['line']}행"
            else:
                value["source"] = source if sec.get("source") else f"{default_source} {value['line']}행"
    return sections, notes


# ---------------------------------------------------------------------------
# 법정 표기 파일 파싱
# ---------------------------------------------------------------------------

def parse_steps(text: str, filename: str) -> List[Dict]:
    return [_copy(line.strip(), f"{filename} {i}행")
            for i, line in enumerate(text.splitlines(), 1) if line.strip()]


def parse_info_rows(text: str, filename: str) -> List[Dict]:
    """'항목: 내용' 줄을 표 행으로. 콜론 없는 줄은 앞 행 내용에 이어붙입니다."""
    rows: List[Dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = re.match(r"^\s*([^:：]{1,30})[:：]\s*(.*)$", line)
        if match:
            rows.append({
                "label": _copy(match.group(1).strip(), f"{filename} {i}행"),
                "value": _copy(match.group(2).strip(), f"{filename} {i}행"),
            })
        elif rows:
            value = rows[-1]["value"]
            value["text"] = (value["text"] + "\n" + line.strip()).strip()
        else:
            rows.append({"label": None, "value": _copy(line.strip(), f"{filename} {i}행")})
    return rows


# ---------------------------------------------------------------------------
# 브리프 생성
# ---------------------------------------------------------------------------

def _field(sec: Optional[Dict], name: str) -> Optional[Dict]:
    if not sec:
        return None
    value = sec["fields"].get(name)
    if isinstance(value, dict):
        return _copy(value["text"], value["source"])
    return None


def _points(sec: Optional[Dict]) -> List[Dict]:
    """'포인트: 제목 | 설명' → {title, desc}"""
    result = []
    for item in (sec or {}).get("fields", {}).get("point", []):
        title, _, desc = item["text"].partition("|")
        entry = {"title": _copy(title.strip(), item["source"])}
        if desc.strip():
            entry["desc"] = _copy(desc.strip(), item["source"])
        result.append(entry)
    return result


def _faq(sec: Optional[Dict]) -> List[Dict]:
    fields = (sec or {}).get("fields", {})
    questions, answers = fields.get("question", []), fields.get("answer", [])
    return [
        {"q": _copy(q["text"], q["source"]), "a": _copy(a["text"], a["source"])}
        for q, a in zip(questions, answers)
    ]


def build_brief(data: Dict) -> Dict:
    """입력 자료 → 렌더링용 브리프 (모든 카피는 text + source)"""
    files = data["files"]
    set_extra_banned_terms(data.get("banned", []))
    plan_sections, notes = parse_plan(files["plan.md"])
    product_name = _copy(files["product_name.txt"].splitlines()[0].strip(), "product_name.txt 1행")

    sections = []
    for section_type in SECTION_ORDER:
        sec = plan_sections.get(section_type)
        entry: Dict = {"id": f"{len(sections) + 1:02d}_{section_type}", "type": section_type, "copy": {}}
        copy = entry["copy"]
        for name in ("eyebrow", "headline", "subcopy", "spec"):
            value = _field(sec, name)
            if value:
                copy[name] = value

        if section_type == "hero":
            copy["product_name"] = _field(sec, "product_name") or product_name
        elif section_type == "key_points":
            entry["points"] = _points(sec)
            if not entry["points"] and not copy.get("headline"):
                continue
        elif section_type == "ingredients":
            entry["body"] = _copy(files["ingredients.txt"], "ingredients.txt 전체")
        elif section_type == "how_to_use":
            steps = [_copy(s["text"], s["source"]) for s in (sec or {}).get("fields", {}).get("step", [])]
            entry["steps"] = steps or parse_steps(files["how_to_use.txt"], "how_to_use.txt")
        elif section_type == "faq":
            entry["faq"] = _faq(sec)
            if not entry["faq"]:
                continue
        elif section_type == "product_info":
            entry["rows"] = parse_info_rows(files["product_info.txt"], "product_info.txt")
        elif section_type == "closing":
            copy.setdefault("product_name", _field(sec, "product_name") or product_name)
        elif not sec or not copy:
            continue  # intro / product / detail: 기획본에 원문이 있을 때만

        if sec:
            entry["plan_heading"] = sec["heading"]
        sections.append(entry)

    # 번호 재부여
    for i, entry in enumerate(sections, 1):
        entry["id"] = f"{i:02d}_{entry['type']}"

    return {
        "product": data["product"],
        "product_name": product_name,
        "photos": data["photos"],
        "design": data.get("design", {}),
        "sections": sections,
        "parse_notes": notes,
    }


# ---------------------------------------------------------------------------
# 금지 표현 필터
# ---------------------------------------------------------------------------

LEGAL_TYPES = {"ingredients", "how_to_use", "product_info"}


def _walk_copies(node, path=""):
    if isinstance(node, dict):
        if "text" in node and "source" in node:
            yield path, node
            return
        for k, v in node.items():
            yield from _walk_copies(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_copies(v, f"{path}[{i}]")


def filter_banned(brief: Dict) -> List[Dict]:
    """
    금지 표현이 포함된 카피를 제거하고 제외 목록을 반환합니다.
    법정 표기 섹션에서 발견되면 InputError (원문 수정 필요).
    """
    excluded = []
    legal_errors = []
    for section in brief["sections"]:
        for path, item in list(_walk_copies(section)):
            banned = find_banned_terms(item["text"])
            if not banned:
                continue
            record = {"section": section["id"], "field": path, "text": item["text"],
                      "source": item["source"], "banned": banned}
            if section["type"] in LEGAL_TYPES:
                legal_errors.append(record)
            else:
                item["text"] = ""  # 렌더링 제외 (resolve_copy가 빈 텍스트는 건너뜀)
                excluded.append(record)
    if legal_errors:
        lines = [f"{r['section']} {r['field']}: {r['banned']} ({r['source']})" for r in legal_errors]
        raise InputError("법정 표기 원문에 금지 표현 포함 - 원문 확인 필요:\n- " + "\n- ".join(lines))

    # 제목이 빠진 key_points 항목 정리
    for section in brief["sections"]:
        if "points" in section:
            section["points"] = [p for p in section["points"] if p["title"]["text"]]
    return excluded
