"""
섹션 렌더링 모듈 (HTML/CSS → Chromium 스크린샷 → PNG)

원칙:
- 제품 사진은 Pillow로 크롭/리사이즈만 합니다. (AI 편집, 보정, 합성 없음)
- 한국어 카피는 이미지 생성 모델이 아니라 HTML/CSS 텍스트로 렌더링합니다.
- 카피는 copy_guard.resolve_copy()를 통과한 원문만 사용합니다. (source 없으면 제외)
- 출력 너비는 항상 1200px 입니다.
"""

import glob
import html
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image, ImageChops, ImageStat

from scripts.copy_guard import resolve_copy

PROJECT_ROOT = Path(__file__).parent.parent
FIXED_WIDTH = 1200


def find_chromium() -> Optional[str]:
    """사전 설치된 Chromium 실행 파일을 찾습니다. (없으면 Playwright 기본값 사용)"""
    env_path = os.getenv("CHROMIUM_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    browsers = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    candidates = sorted(glob.glob(os.path.join(browsers, "chromium-*/chrome-linux*/chrome")))
    return candidates[-1] if candidates else None


def prepare_photo(src: str, dst: str, crop: Optional[Dict] = None) -> Tuple[str, Tuple[int, int]]:
    """
    원본 사진을 크롭 후 1200px 너비로 리사이즈합니다. 그 외 변형은 하지 않습니다.

    Args:
        crop: 원본 픽셀 기준 {"left", "top", "right", "bottom"} (없으면 전체)
    """
    img = Image.open(src).convert("RGB")
    if crop:
        box = (
            crop.get("left") or 0,
            crop.get("top") or 0,
            crop.get("right") or img.width,
            crop.get("bottom") or img.height,
        )
        img = img.crop(box)

    if img.width < FIXED_WIDTH:
        print(f"Warning: 원본 너비 {img.width}px < {FIXED_WIDTH}px - 확대가 발생합니다")

    height = round(img.height * FIXED_WIDTH / img.width)
    if img.size != (FIXED_WIDTH, height):
        img = img.resize((FIXED_WIDTH, height), Image.Resampling.LANCZOS)

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG")
    return dst, img.size


def edge_color(photo_path: str, edge: str = "top", rows: int = 4) -> str:
    """사진 가장자리 평균색 (텍스트 영역 배경을 사진과 이어지게 하기 위함)"""
    img = Image.open(photo_path).convert("RGB")
    box = (0, 0, img.width, rows) if edge == "top" else (0, img.height - rows, img.width, img.height)
    r, g, b = (round(c) for c in ImageStat.Stat(img.crop(box)).mean)
    return f"#{r:02x}{g:02x}{b:02x}"


def _text_html(text: Optional[str], css_class: str) -> str:
    if not text:
        return ""
    return f'<div class="{css_class}">{html.escape(text)}</div>'


def _font_faces(design: Dict) -> str:
    faces = []
    for weight, rel_path in (design.get("fonts") or {}).items():
        path = (PROJECT_ROOT / rel_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"폰트 파일 없음: {rel_path}")
        faces.append(
            f"@font-face {{ font-family: 'PageFont'; font-weight: {weight}; "
            f"src: url('{path.as_uri()}'); }}"
        )
    if not faces:
        raise ValueError("design.fonts 에 한글 폰트 파일을 지정해야 합니다")
    return "\n".join(faces)


# Hero 레이아웃 기본값 (섹션의 "layout"으로 덮어쓸 수 있음)
HERO_LAYOUT_DEFAULTS = {
    "padding_top": 150,
    "padding_bottom": 40,
    "eyebrow_size": 20,
    "headline_size": 60,
    "headline_weight": 600,
    "headline_line_height": 1.32,
    "headline_letter_spacing": "-0.02em",
    "subcopy_size": 26,
    "product_name_size": 22,
    "product_name_weight": 500,
    "product_name_color": None,  # None이면 colors.muted
    "product_name_letter_spacing": "0.08em",
    "product_name_gap": 48,
    "divider": False,  # 헤드라인과 제품명 사이 가는 구분선
    "divider_width": 48,
    "divider_color": "#6f6f6f",
}


def build_hero_html(section: Dict, design: Dict, photo_uri: str, bg_color: str) -> Tuple[str, int]:
    """Hero HTML 생성. 반환: (html, 렌더된 카피 수)"""
    copy = section.get("copy", {})
    lines = {
        key: resolve_copy(copy.get(key), f"{section['id']}.copy.{key}")
        for key in ("eyebrow", "headline", "subcopy", "product_name")
    }
    rendered = sum(1 for v in lines.values() if v)
    colors = design.get("colors", {})
    lay = {**HERO_LAYOUT_DEFAULTS, **(section.get("layout") or {})}
    product_name_color = lay["product_name_color"] or colors.get("muted", "#9a9a9a")
    divider = '<div class="divider"></div>' if lay["divider"] and lines["product_name"] else ""

    text_block = ""
    if rendered:
        text_block = f"""
  <header class="text">
    {_text_html(lines['eyebrow'], 'eyebrow')}
    {_text_html(lines['headline'], 'headline')}
    {_text_html(lines['subcopy'], 'subcopy')}
    {divider}
    {_text_html(lines['product_name'], 'product-name')}
  </header>"""

    doc = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<style>
{_font_faces(design)}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {FIXED_WIDTH}px; background: {bg_color}; }}
body {{ font-family: 'PageFont', sans-serif; color: {colors.get('text', '#f2f2f2')};
       -webkit-font-smoothing: antialiased; }}
.text {{ padding: {lay['padding_top']}px 120px {lay['padding_bottom']}px; text-align: center;
        background: {bg_color}; word-break: keep-all; overflow-wrap: break-word; }}
.text > div {{ white-space: pre-line; }}  /* 원문 줄바꿈만 유지 (템플릿 공백은 무시) */
.eyebrow {{ font-size: {lay['eyebrow_size']}px; font-weight: 500; letter-spacing: 0.32em;
           color: {colors.get('muted', '#9a9a9a')}; margin-bottom: 36px; }}
.headline {{ font-size: {lay['headline_size']}px; font-weight: {lay['headline_weight']};
            line-height: {lay['headline_line_height']}; letter-spacing: {lay['headline_letter_spacing']}; }}
.subcopy {{ font-size: {lay['subcopy_size']}px; font-weight: 300; line-height: 1.6; margin-top: 32px;
           color: {colors.get('subtext', '#c8c8c8')}; }}
.divider {{ width: {lay['divider_width']}px; height: 1px; background: {lay['divider_color']};
           margin: {lay['product_name_gap']}px auto 0; }}
.product-name {{ font-size: {lay['product_name_size']}px; font-weight: {lay['product_name_weight']};
                letter-spacing: {lay['product_name_letter_spacing']}; color: {product_name_color};
                margin-top: {lay['product_name_gap'] if not divider else lay['product_name_gap'] // 2}px; }}
.photo {{ display: block; width: {FIXED_WIDTH}px; height: auto; }}
</style></head>
<body>{text_block}
  <img class="photo" src="{photo_uri}" alt="">
</body></html>"""
    return doc, rendered


def screenshot_html(html_path: str, output_path: str) -> str:
    """HTML을 1200px 뷰포트로 전체 캡처합니다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        executable = find_chromium()
        browser = p.chromium.launch(executable_path=executable) if executable else p.chromium.launch()
        page = browser.new_page(viewport={"width": FIXED_WIDTH, "height": 800}, device_scale_factor=1)
        page.goto(Path(html_path).resolve().as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_load_state("networkidle")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path


def verify_photo_region(rendered_path: str, photo_path: str) -> float:
    """
    렌더 결과 하단의 사진 영역이 Pillow 리사이즈 결과와 같은지 비교합니다.
    반환값: 픽셀 평균 차이 (0 = 동일)
    """
    rendered = Image.open(rendered_path).convert("RGB")
    photo = Image.open(photo_path).convert("RGB")
    region = rendered.crop((0, rendered.height - photo.height, FIXED_WIDTH, rendered.height))
    diff = ImageChops.difference(region, photo)
    return sum(ImageStat.Stat(diff).mean) / 3


def render_hero(section: Dict, design: Dict, work_dir: str, output_path: str) -> str:
    image = section.get("image") or {}
    src = PROJECT_ROOT / image.get("path", "")
    if not src.is_file():
        raise FileNotFoundError(f"제품 원본 사진 없음: {image.get('path')}")

    photo_path, size = prepare_photo(str(src), os.path.join(work_dir, f"{section['id']}_photo.png"), image.get("crop"))
    bg_color = edge_color(photo_path, "top")
    doc, rendered = build_hero_html(section, design, Path(photo_path).resolve().as_uri(), bg_color)
    if rendered == 0:
        print(f"Warning: {section['id']} - source가 있는 카피가 없어 사진만 렌더링합니다")

    html_path = os.path.join(work_dir, f"{section['id']}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)

    screenshot_html(html_path, output_path)
    out = Image.open(output_path)
    diff = verify_photo_region(output_path, photo_path)
    print(f"Rendered: {output_path} ({out.width}x{out.height}), 사진 {size[0]}x{size[1]}, "
          f"카피 {rendered}개, 사진 영역 평균 차이 {diff:.3f}")
    if out.width != FIXED_WIDTH:
        raise RuntimeError(f"출력 너비 오류: {out.width}px")
    return output_path


RENDERERS = {
    "hero": render_hero,
}
