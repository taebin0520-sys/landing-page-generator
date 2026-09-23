"""
상세페이지 one-shot 빌드

    python3 scripts/build_detail_page.py --product aventura
    python3 scripts/build_detail_page.py --product aventura --check   # 검증/분류만 (렌더링 없음)

입력: references/private/<product>/ (형식: references/templates/product_input/README.md)
출력:
    output/sections/NN_<type>.png   섹션별 PNG
    output/final_page.png           최종 병합본 (1200px 폭)
    output/build_report.md / .json  QA 보고서
    briefs/<product>.json           자동 생성된 브리프 (gitignore)

단계:
    1 입력 검증 → 2 기획본 섹션 분류 → 3 섹션 구성 결정 → 4 금지어 필터
    → 5 사진 자동 크롭 → 6 (선택) 보조 비주얼 → 7 섹션 렌더링(HTML/CSS)
    → 8 병합 → 9 QA(금지어/원문 대조/사진/크기) → 10 보고서
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.parse_source import INPUT_ROOT, InputError, build_brief, filter_banned, load_input
from scripts.photo_crop import detect_product_box, resolve_crop
from scripts.qa import run_qa
from scripts.render_section import Renderer
from scripts.stitch_images import stitch_sections

DEFAULT_FONTS = {
    "300": "assets/private/fonts/Pretendard-Light.otf",
    "400": "assets/private/fonts/Pretendard-Regular.otf",
    "500": "assets/private/fonts/Pretendard-Medium.otf",
    "600": "assets/private/fonts/Pretendard-SemiBold.otf",
    "700": "assets/private/fonts/Pretendard-Bold.otf",
}

# 섹션별 사진 역할과 자동 크롭 프리셋 (design.json "photos"/"crops" 로 덮어쓰기)
PHOTO_PLAN = {
    "hero": ("primary", "full"),
    "intro": ("secondary", "top"),
    "product": ("primary", "upper"),
    "key_points": ("primary", "top"),
    "detail": ("cutout", "whole"),
    "closing": ("primary", "full"),
}


def assign_photos(brief: Dict) -> List[str]:
    """섹션별 사진·크롭 결정. 반환: 경고 목록"""
    design = brief["design"]
    photos = brief["photos"]
    base = Path(INPUT_ROOT / brief["product"])
    warnings = []

    def resolve_path(p: str) -> str:
        candidate = base / p
        return str(candidate.relative_to(PROJECT_ROOT)) if candidate.is_file() else p

    infos = {p: detect_product_box(str(PROJECT_ROOT / p)) for p in photos}
    cutouts = [p for p in photos if infos[p]["has_alpha"]]
    opaque = [p for p in photos if not infos[p]["has_alpha"]] or photos
    roles = {
        "primary": opaque[0],
        "secondary": opaque[1] if len(opaque) > 1 else opaque[0],
        "cutout": cutouts[0] if cutouts else None,
    }

    for section in brief["sections"]:
        stype = section["type"]
        explicit = (design.get("photos") or {}).get(stype)
        if explicit == "none":
            continue
        if explicit:
            path = resolve_path(explicit)
        elif stype in PHOTO_PLAN:
            role, _ = PHOTO_PLAN[stype]
            path = roles.get(role)
            if not path:
                continue
        else:
            continue
        preset = PHOTO_PLAN.get(stype, ("primary", "full"))[1]
        override = (design.get("crops") or {}).get(stype)
        crop = resolve_crop(str(PROJECT_ROOT / path), preset, override, design.get("upper_ratio", 0.6))
        section["image"] = {"path": path, "crop": crop}
        if crop["mode"].startswith("auto"):
            warnings.append(f"{section['id']}: 자동 크롭({crop['mode']}) - 라벨 노출 범위 육안 확인 권장")
    return warnings


def add_backgrounds(brief: Dict, work_dir: Path) -> List[str]:
    """design.json gemini.enabled 일 때만 보조 배경 생성 (글자·제품·인물 없음)"""
    gemini = brief["design"].get("gemini") or {}
    if not gemini.get("enabled"):
        return []
    from scripts.gemini_api import generate_background

    notes = []
    for section in brief["sections"]:
        prompt = (gemini.get("sections") or {}).get(section["type"])
        if not prompt:
            continue
        out = work_dir / f"{section['id']}_bg.png"
        if generate_background(prompt, str(out)):
            section.setdefault("layout", {})["background"] = f"#0a0a0a url('{out.resolve().as_uri()}') center/cover"
            notes.append(f"{section['id']}: Gemini 보조 배경 사용")
        else:
            notes.append(f"{section['id']}: Gemini 배경 생성 실패 - 단색 배경으로 진행")
    return notes


def write_report(out_dir: Path, report: Dict) -> None:
    (out_dir / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    qa = report["qa"]
    lines = [
        f"# 빌드 보고서 - {report['product']}",
        "",
        f"- 결과: {'QA 통과' if qa['passed'] else 'QA 실패'}",
        f"- 생성 섹션: {len(report['sections'])}개 ({', '.join(s['id'] for s in report['sections'])})",
        f"- 최종 이미지: {report['final_size'][0]}x{report['final_size'][1]}px → {report['final_path']}",
        f"- 사진 상태: {report.get('photo_status') or '-'}",
        "",
        "## 사용한 제품 사진",
    ]
    for s in report["sections"]:
        if s.get("photo"):
            p = s["photo"]
            lines.append(f"- {s['id']}: {p['source']} / 크롭 {p['crop']} / 배율 {p['scale']} / 픽셀 차이 {p['pixel_diff']}")
    lines += ["", "## 제외된 문구"]
    lines += [f"- [금지어 {e['banned']}] {e['section']}: {e['text']} ({e['source']})" for e in report["excluded"]] or ["- 없음"]
    lines += [f"- [분류 제외] {n['line']}행: {n['text']} - {n['reason']}" for n in report["parse_notes"]]
    lines += ["", "## 금지어 검사", f"- 렌더링 결과 금지어: {len(qa['banned_hits'])}건"]
    lines += [f"  - {h['section']}: {h['banned']}" for h in qa["banned_hits"]]
    lines += ["", "## 원문 대조", f"- 원문과 불일치: {len(qa['verbatim_fail'])}건"]
    lines += [f"  - {v['section']} {v['field']}: {v['text']}" for v in qa["verbatim_fail"]]
    lines += [f"- 구조 라벨(원문 외 고정 제목): {', '.join(qa['structural_labels']) or '없음'}"]
    lines += ["", "## 원문 누락 (분류됐지만 렌더링 안 됨)"]
    lines += [f"- {n['section']}: {n['text']} ({n['source']})" for n in qa["not_rendered"]] or ["- 없음"]
    lines += ["", "## 생략된 섹션"]
    lines += [f"- {s}" for s in report["skipped_sections"]] or ["- 없음"]
    lines += ["", "## 경고"]
    lines += [f"- {w}" for w in report["warnings"] + qa["photo_issues"] + qa["width_issues"]] or ["- 없음"]
    (out_dir / "build_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(product: str, check_only: bool = False, input_root: Path = INPUT_ROOT,
          output_root: Path = PROJECT_ROOT / "output") -> Dict:
    # 1. 입력 검증
    data = load_input(product, input_root)

    # 2~3. 기획본 분류 → 섹션 구성
    brief = build_brief(data)
    brief["design"] = {"fonts": DEFAULT_FONTS, **brief["design"]}

    # 4. 금지어 필터 (마케팅 카피 제외 / 법정 표기는 중단)
    excluded = filter_banned(brief)

    # 5. 사진 배정 + 자동 크롭
    warnings = assign_photos(brief)

    from scripts.parse_source import SECTION_ORDER
    present = {s["type"] for s in brief["sections"]}
    skipped = [f"{t}: 기획본에 해당 원문 없음" for t in SECTION_ORDER if t not in present]

    briefs_dir = PROJECT_ROOT / "briefs"
    briefs_dir.mkdir(exist_ok=True)
    (briefs_dir / f"{product}.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    if check_only:
        return {"product": product, "sections": [s["id"] for s in brief["sections"]],
                "excluded": excluded, "parse_notes": brief["parse_notes"],
                "skipped_sections": skipped, "warnings": warnings}

    out_dir = output_root
    sections_dir = out_dir / "sections"
    work_dir = out_dir / "_work"
    for d in (sections_dir, work_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)

    # 6. 보조 비주얼 (선택)
    warnings += add_backgrounds(brief, work_dir)

    # 7. 섹션 렌더링
    results = []
    with Renderer() as renderer:
        for section in brief["sections"]:
            results.append(renderer.render(section, brief["design"], str(work_dir),
                                           str(sections_dir / f"{section['id']}.png")))

    # 8. 병합
    final_path = out_dir / "final_page.png"
    stitch_sections([r["path"] for r in results], str(final_path))
    from PIL import Image
    with Image.open(final_path) as final_img:
        final_size = list(final_img.size)

    # 9. QA
    qa = run_qa(results, brief, data["files"], final_size)

    # 10. 보고서
    report = {
        "product": product,
        "final_path": str(final_path.relative_to(PROJECT_ROOT)),
        "final_size": final_size,
        "photo_status": brief["design"].get("photo_status"),
        "sections": [dict(r) for r in results],
        "excluded": excluded,
        "parse_notes": brief["parse_notes"],
        "skipped_sections": skipped,
        "warnings": warnings,
        "qa": qa,
    }
    for s in report["sections"]:
        s["path"] = str(Path(s["path"]).relative_to(PROJECT_ROOT)) if str(s["path"]).startswith(str(PROJECT_ROOT)) else s["path"]
        if s.get("photo"):
            s["photo"].pop("work_path", None)
    write_report(out_dir, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="상세페이지 one-shot 빌드")
    parser.add_argument("--product", required=True, help="references/private/<product>/ 폴더명")
    parser.add_argument("--check", action="store_true", help="입력 검증·섹션 분류만 실행")
    args = parser.parse_args()

    try:
        report = build(args.product, check_only=args.check)
    except InputError as e:
        print(f"\n[제작 불가] {e}")
        return 2

    if args.check:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    qa = report["qa"]
    print("\n" + "=" * 50)
    print(f"섹션 {len(report['sections'])}개 / 최종 {report['final_size'][0]}x{report['final_size'][1]}px")
    print(f"QA: {'통과' if qa['passed'] else '실패'} (금지어 {len(qa['banned_hits'])}, 원문 불일치 {len(qa['verbatim_fail'])}, "
          f"누락 {len(qa['not_rendered'])}, 제외 {len(report['excluded'])})")
    print(f"최종: {report['final_path']}")
    print("보고서: output/build_report.md")
    return 0 if qa["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
