"""
섹션별 PNG 이미지를 세로로 이어붙여 최종 상세페이지를 생성하는 모듈

⚠️ 중요: 모든 이미지는 1200px 너비로 자동 리사이즈됩니다.
   Gemini API가 정확한 픽셀 크기를 보장하지 않기 때문에
   스티칭 전 강제로 1200px로 맞춥니다.
"""

import os
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image


# 고정 너비 (절대 변경 금지)
FIXED_WIDTH = 1200


def load_images(image_paths: List[str], target_width: int = FIXED_WIDTH) -> List[Image.Image]:
    """
    이미지 파일들을 로드하고 지정된 너비로 리사이즈합니다.

    ⚠️ 중요: 모든 이미지는 target_width로 강제 리사이즈됩니다.
    이는 Gemini API가 정확한 픽셀 크기를 생성하지 않기 때문입니다.

    Args:
        image_paths: 이미지 파일 경로 리스트
        target_width: 목표 너비 (기본값: 1200px)

    Returns:
        PIL Image 객체 리스트
    """
    images = []
    for path in image_paths:
        if os.path.exists(path):
            img = Image.open(path)
            original_size = f"{img.width}x{img.height}"

            # RGBA로 변환 (투명도 지원)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 너비가 target_width와 다르면 리사이즈
            if img.width != target_width:
                ratio = target_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)
                print(f"Loaded & Resized: {path} ({original_size} → {img.width}x{img.height})")
            else:
                print(f"Loaded: {path} ({img.width}x{img.height})")

            images.append(img)
        else:
            print(f"Warning: File not found - {path}")
    return images


def stitch_sections(
    image_paths: List[str],
    output_path: str,
    background_color: Tuple[int, int, int, int] = (255, 255, 255, 255),
    alignment: str = "center",
    target_width: int = FIXED_WIDTH
) -> Optional[str]:
    """
    섹션별 PNG를 세로로 이어붙여 최종 상세페이지를 생성합니다.

    ⚠️ 중요: 모든 이미지는 target_width(기본 1200px)로 강제 리사이즈됩니다.

    Args:
        image_paths: 섹션 이미지 경로 리스트 (순서대로)
        output_path: 출력 파일 경로 (.png 또는 .pdf)
        background_color: 배경 색상 (RGBA)
        alignment: 정렬 방식 ("left", "center", "right")
        target_width: 목표 너비 (기본값: 1200px)

    Returns:
        저장된 파일 경로 또는 None (실패시)
    """
    # 1차 패스: 헤더만 읽어 최종 높이 계산 (픽셀 데이터는 로드하지 않음 → 메모리 절약)
    plan = []
    for path in image_paths:
        if not os.path.exists(path):
            print(f"Warning: File not found - {path}")
            continue
        with Image.open(path) as img:
            w, h = img.size
        plan.append((path, w, h, int(h * target_width / w) if w != target_width else h))

    if not plan:
        print("Error: No images to stitch")
        return None

    total_height = sum(p[3] for p in plan)
    final_width = target_width  # 고정 너비 사용

    print(f"\nStitching {len(plan)} images...")
    print(f"Final size: {final_width}x{total_height} (width fixed to {target_width}px)")

    # RGB 캔버스 사용 (RGBA 대비 메모리 25% 절약, PDF 저장 시 변환 복사본 불필요)
    result = Image.new('RGB', (final_width, total_height), background_color[:3])

    # 2차 패스: 한 장씩 로드 → 리사이즈 → 붙이기 → 즉시 해제
    y_offset = 0
    for i, (path, w, h, new_h) in enumerate(plan):
        with Image.open(path) as img:
            if img.width != target_width:
                img = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
                print(f"Loaded & Resized: {path} ({w}x{h} → {target_width}x{new_h})")
            else:
                img.load()
                print(f"Loaded: {path} ({w}x{h})")
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGBA')
                result.paste(img, (0, y_offset), img)
            else:
                result.paste(img.convert('RGB'), (0, y_offset))
        print(f"  Section {i+1}: y={y_offset}, height={new_h}")
        y_offset += new_h

    # 출력 디렉토리 생성
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 저장
    if output_path.lower().endswith('.pdf'):
        result.save(output_path, 'PDF', resolution=150)
        print(f"\nPDF saved: {output_path}")
    else:
        # optimize=True는 대용량 이미지에서 매우 느리므로 compress_level로 대체
        result.save(output_path, 'PNG', compress_level=6)
        print(f"\nPNG saved: {output_path}")
    result.close()

    return output_path


def stitch_from_directory(
    input_dir: str,
    output_path: str,
    section_order: Optional[List[str]] = None
) -> Optional[str]:
    """
    디렉토리 내의 섹션 이미지들을 순서대로 이어붙입니다.

    Args:
        input_dir: 섹션 이미지들이 있는 디렉토리
        output_path: 출력 파일 경로
        section_order: 섹션 파일명 순서 (없으면 자동 정렬)

    Returns:
        저장된 파일 경로
    """
    if section_order is None:
        # 기본 섹션 순서
        section_order = [
            "01_hero.png",
            "02_pain.png",
            "03_problem.png",
            "04_story.png",
            "05_solution.png",
            "06_how_it_works.png",
            "07_social_proof.png",
            "08_authority.png",
            "09_benefits.png",
            "10_risk_removal.png",
            "11_comparison.png",
            "12_target_filter.png",
            "13_final_cta.png"
        ]

    image_paths = [os.path.join(input_dir, filename) for filename in section_order]

    # 존재하는 파일만 필터링
    existing_paths = [p for p in image_paths if os.path.exists(p)]

    if not existing_paths:
        # 디렉토리 내 PNG 파일 자동 탐색
        print(f"Searching for PNG files in {input_dir}...")
        png_files = sorted([f for f in os.listdir(input_dir) if f.endswith('.png')])
        existing_paths = [os.path.join(input_dir, f) for f in png_files]

    if not existing_paths:
        print(f"Error: No PNG files found in {input_dir}")
        return None

    print(f"Found {len(existing_paths)} section images")
    return stitch_sections(existing_paths, output_path)


def create_preview(
    image_path: str,
    preview_path: str,
    max_height: int = 2000
) -> Optional[str]:
    """
    미리보기용 축소 이미지를 생성합니다.

    Args:
        image_path: 원본 이미지 경로
        preview_path: 미리보기 저장 경로
        max_height: 최대 높이

    Returns:
        저장된 파일 경로
    """
    if not os.path.exists(image_path):
        print(f"Error: File not found - {image_path}")
        return None

    with Image.open(image_path) as img:
        # thumbnail은 draft 디코딩 + 제자리 축소로 메모리를 적게 사용
        img.thumbnail((img.width, max_height), Image.Resampling.LANCZOS)
        Path(preview_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(preview_path, 'PNG', optimize=True)

    print(f"Preview saved: {preview_path} ({img.width}x{img.height})")
    return preview_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python stitch_images.py <input_dir> <output_path>")
        print("Example: python stitch_images.py output/sections output/final_page.png")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_path = sys.argv[2]

    result = stitch_from_directory(input_dir, output_path)

    if result:
        print(f"\nSuccess! Final page: {result}")
    else:
        print("\nFailed to create final page")
        sys.exit(1)
