"""
상세페이지 생성 파이프라인

브리프(JSON) → 카피 검증(copy_guard) → 섹션별 HTML/CSS 렌더링 → 1200px PNG → 스티칭

사용법:
    python3 scripts/generate_page.py --brief briefs/aventura.json --sections 01_hero
    python3 scripts/generate_page.py --brief briefs/aventura.json --stitch   # 전체 렌더 후 병합

주의:
- 브리프(briefs/*.json)와 assets/private/ 는 비공개 자료이므로 커밋하지 않습니다.
- 모든 카피는 {"text", "source"} 형식이며 source가 없으면 렌더링되지 않습니다.
- 금지 표현이 하나라도 있으면 즉시 중단합니다.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.copy_guard import audit_brief
from scripts.render_section import RENDERERS
from scripts.stitch_images import stitch_sections


def load_brief(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_sections(brief: Dict, only: Optional[List[str]], output_dir: str) -> List[str]:
    sections_dir = os.path.join(output_dir, "sections")
    work_dir = os.path.join(output_dir, "_work")
    design = brief.get("design", {})
    rendered = []

    for section in brief.get("sections", []):
        section_id = section["id"]
        if only and section_id not in only:
            continue
        if not section.get("enabled", True):
            print(f"Skip (disabled): {section_id}")
            continue

        renderer = RENDERERS.get(section.get("type"))
        if renderer is None:
            print(f"Skip (renderer 미구현): {section_id} / type={section.get('type')}")
            continue

        print(f"\n=== {section_id} ===")
        if section.get("status"):
            print(f"Status: {section['status']}")
        output_path = os.path.join(sections_dir, f"{section_id}.png")
        rendered.append(renderer(section, design, work_dir, output_path))

    return rendered


def stitch_all(brief: Dict, output_dir: str) -> Optional[str]:
    """브리프의 섹션 순서대로, 렌더된 PNG만 이어붙입니다."""
    sections_dir = os.path.join(output_dir, "sections")
    paths = [
        os.path.join(sections_dir, f"{s['id']}.png")
        for s in brief.get("sections", [])
        if s.get("enabled", True)
    ]
    paths = [p for p in paths if os.path.exists(p)]
    pending = [s["id"] for s in brief.get("sections", []) if s.get("enabled", True) and s.get("status")]
    if pending:
        print(f"Warning: 확정되지 않은 섹션 포함 {pending} - 최종본 아님")
    if not paths:
        print("Error: 렌더된 섹션이 없습니다")
        return None
    return stitch_sections(paths, os.path.join(output_dir, "final_page.png"))


def main() -> int:
    parser = argparse.ArgumentParser(description="상세페이지 생성")
    parser.add_argument("--brief", required=True, help="브리프 JSON 경로 (예: briefs/aventura.json)")
    parser.add_argument("--sections", nargs="*", help="렌더링할 섹션 id (생략 시 전체)")
    parser.add_argument("--stitch", action="store_true", help="렌더된 섹션을 최종 PNG로 병합")
    parser.add_argument("--output", default="output", help="출력 디렉토리")
    args = parser.parse_args()

    brief = load_brief(args.brief)
    audit_brief(brief)  # 금지 표현 발견 시 BannedCopyError로 중단

    output_dir = str(PROJECT_ROOT / args.output)
    render_sections(brief, args.sections or None, output_dir)
    if args.stitch and not stitch_all(brief, output_dir):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
