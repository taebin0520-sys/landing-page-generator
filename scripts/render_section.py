"""
섹션 렌더링 모듈 (HTML/CSS → Chromium 스크린샷 → PNG)

원칙:
- 제품 사진은 Pillow로 크롭/리사이즈만 합니다. (AI 편집, 보정, 합성 없음)
- 한국어 카피는 이미지 생성 모델이 아니라 HTML/CSS 텍스트로 렌더링합니다.
- 카피는 copy_guard.resolve_copy()를 통과한 원문만 사용합니다. (source 없으면 제외)
- 출력 너비는 항상 1200px 입니다.

섹션 타입:
    hero / intro / product / detail / closing   텍스트 + 원본 사진 크롭
    key_points (texture)                        헤드라인 + 사진 + 포인트 목록
    ingredients                                 전성분 원문
    how_to_use                                  사용방법 단계
    faq                                         Q / A
    product_info                                제품정보 표 (주의사항 포함)
"""

import glob
import html
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageStat

from scripts.copy_guard import resolve_copy

PROJECT_ROOT = Path(__file__).parent.parent
FIXED_WIDTH = 1200

# 텍스트 전용 섹션 제목 (기획본에 헤드라인이 없을 때 쓰는 구조 라벨, 효능 표현 아님)
STRUCTURAL_LABELS = {
    "ingredients": "전성분",
    "how_to_use": "사용 방법",
    "faq": "FAQ",
    "product_info": "제품 정보",
}


def find_chromium() -> Optional[str]:
    """사전 설치된 Chromium 실행 파일을 찾습니다. (없으면 Playwright 기본값 사용)"""
    env_path = os.getenv("CHROMIUM_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    browsers = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    candidates = sorted(glob.glob(os.path.join(browsers, "chromium-*/chrome-linux*/chrome")))
    return candidates[-1] if candidates else None


# ---------------------------------------------------------------------------
# 사진 처리 (크롭 / 리사이즈만)
# ---------------------------------------------------------------------------

def prepare_photo(src: str, dst: str, crop: Optional[Dict] = None,
                  target_width: int = FIXED_WIDTH) -> Tuple[str, Tuple[int, int], float]:
    """
    원본 사진을 크롭 후 target_width 로 리사이즈합니다. 그 외 변형은 하지 않습니다.

    Returns:
        (저장 경로, 크기, 배율)  배율 > 1 이면 확대
    """
    img = Image.open(src)
    img = img.convert("RGBA" if "A" in img.getbands() else "RGB")  # 누끼 PNG는 투명도 유지
    if crop:
        box = (
            crop.get("left") or 0,
            crop.get("top") or 0,
            crop.get("right") or img.width,
            crop.get("bottom") or img.height,
        )
        img = img.crop(box)

    scale = target_width / img.width
    height = round(img.height * scale)
    if img.size != (target_width, height):
        img = img.resize((target_width, height), Image.Resampling.LANCZOS)

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "PNG")
    return dst, img.size, scale


def edge_color(photo_path: str, edge: str = "top", rows: int = 4) -> str:
    """사진 가장자리 평균색 (텍스트 영역 배경을 사진과 이어지게 하기 위함)"""
    img = Image.open(photo_path).convert("RGB")
    box = (0, 0, img.width, rows) if edge == "top" else (0, img.height - rows, img.width, img.height)
    r, g, b = (round(c) for c in ImageStat.Stat(img.crop(box)).mean)
    return f"#{r:02x}{g:02x}{b:02x}"


def verify_photo_region(rendered: Image.Image, photo_path: str, box: Dict) -> float:
    """
    렌더 결과의 사진 영역이 Pillow 크롭/리사이즈 결과와 같은지 비교합니다.
    반환값: 픽셀 평균 차이 (0 = 동일)
    """
    photo = Image.open(photo_path)
    if photo.mode == "RGBA":  # 투명 영역은 배경색과 합성되므로 불투명 픽셀만 비교
        alpha = photo.getchannel("A").point(lambda a: 255 if a == 255 else 0)
        photo = photo.convert("RGB")
    else:
        alpha = None
    # 레이아웃 좌표가 소수점일 수 있어 내림/올림 위치를 모두 비교
    diffs = []
    for x in {math.floor(box["x"]), math.ceil(box["x"])}:
        for y in {math.floor(box["y"]), math.ceil(box["y"])}:
            region = rendered.crop((x, y, x + photo.width, y + photo.height))
            stat = ImageStat.Stat(ImageChops.difference(region, photo), alpha)
            diffs.append(sum(stat.mean) / 3)
    return min(diffs)


# ---------------------------------------------------------------------------
# HTML 조립
# ---------------------------------------------------------------------------

LAYOUT_DEFAULTS = {
    "padding_top": 150,
    "padding_bottom": 40,
    "eyebrow_size": 20,
    "headline_size": 56,
    "headline_weight": 700,
    "headline_line_height": 1.32,
    "headline_letter_spacing": "-0.03em",
    "subcopy_size": 30,
    "product_name_size": 30,
    "product_name_weight": 600,
    "product_name_color": None,  # None이면 colors.muted
    "product_name_letter_spacing": "0.02em",
    "product_name_gap": 36,
    "divider": False,  # 헤드라인과 제품명 사이 가는 구분선
    "divider_width": 48,
    "divider_color": "#6f6f6f",
    "spec_size": 26,
    "text_position": "top",  # top | bottom (사진 위/아래)
    "photo_frame_width": None,  # 지정 시 사진을 이 너비의 프레임 안에 배치 (풀블리드 대신)
    "photo_frame_border": "#2e2e2e",  # "none" 이면 테두리 없음
    "photo_frame_margin": 60,
    "spec_below_photo": False,  # spec 줄을 사진 아래에 배치하여 섹션을 마무리
    "background": None,  # None 이면 사진 가장자리 색 / 프레임형은 colors.background
}


class Collector:
    """렌더링된 카피를 QA용으로 기록"""

    def __init__(self, section_id: str):
        self.section_id = section_id
        self.items: List[Dict] = []

    def take(self, item, field: str) -> Optional[str]:
        text = resolve_copy(item, f"{self.section_id}.{field}")
        if text:
            self.items.append({"field": field, "text": text, "source": item["source"]})
        return text

    def label(self, text: str, field: str) -> str:
        self.items.append({"field": field, "text": text, "source": "구조 라벨", "structural": True})
        return text


def _div(text: Optional[str], css_class: str) -> str:
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


def _document(design: Dict, lay: Dict, bg: str, body: str) -> str:
    colors = design.get("colors", {})
    text = colors.get("text", "#f2f2f2")
    sub = colors.get("subtext", "#c8c8c8")
    muted = colors.get("muted", "#9a9a9a")
    line = colors.get("line", "#2e2e2e")
    pn_color = lay["product_name_color"] or muted
    frame_border = "none" if lay["photo_frame_border"] == "none" else f"1px solid {lay['photo_frame_border']}"
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<style>
{_font_faces(design)}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {FIXED_WIDTH}px; background: {bg}; }}
body {{ font-family: 'PageFont', sans-serif; color: {text}; -webkit-font-smoothing: antialiased; }}
.text {{ padding: {lay['padding_top']}px 120px {lay['padding_bottom']}px; text-align: center;
        word-break: keep-all; overflow-wrap: break-word; }}
.text div, .keep {{ white-space: pre-line; word-break: keep-all; }}  /* 원문 줄바꿈만 유지 */
.eyebrow {{ font-size: {lay['eyebrow_size']}px; font-weight: 500; letter-spacing: 0.32em;
           color: {muted}; margin-bottom: 36px; }}
.headline {{ font-size: {lay['headline_size']}px; font-weight: {lay['headline_weight']};
            line-height: {lay['headline_line_height']}; letter-spacing: {lay['headline_letter_spacing']}; }}
.subcopy {{ font-size: {lay['subcopy_size']}px; font-weight: 300; line-height: 1.6; margin-top: 32px; color: {sub}; }}
.divider {{ width: {lay['divider_width']}px; height: 1px; background: {lay['divider_color']};
           margin: {lay['product_name_gap']}px auto 0; }}
.product-name {{ font-size: {lay['product_name_size']}px; font-weight: {lay['product_name_weight']};
                letter-spacing: {lay['product_name_letter_spacing']}; color: {pn_color};
                margin-top: {lay['product_name_gap']}px; }}
.divider + .product-name {{ margin-top: {lay['product_name_gap'] // 2}px; }}
.spec {{ font-size: {lay['spec_size']}px; font-weight: 500; letter-spacing: 0.06em; margin-top: 20px; color: {muted}; }}
.photo {{ display: block; width: {FIXED_WIDTH}px; height: auto; }}
.frame {{ padding: {lay['photo_frame_margin']}px 0 {lay['photo_frame_margin']}px; }}
.frame .photo {{ width: {lay['photo_frame_width'] or FIXED_WIDTH}px; margin: 0 auto; outline: {frame_border}; }}
.below {{ text-align: center; padding: 0 0 {lay['padding_bottom']}px; }}
.below .spec {{ margin-top: 0; }}
.points {{ padding: 20px 160px {lay['padding_bottom']}px; }}
.point {{ display: flex; gap: 36px; padding: 40px 0; border-top: 1px solid {line}; }}
.point:last-child {{ border-bottom: 1px solid {line}; }}
.point .num {{ font-size: 22px; font-weight: 500; color: {muted}; letter-spacing: 0.1em; min-width: 48px; padding-top: 8px; }}
.point .title {{ font-size: 36px; font-weight: 600; line-height: 1.4; }}
.point .desc {{ font-size: 26px; font-weight: 300; line-height: 1.6; color: {sub}; margin-top: 10px; }}
.block {{ padding: 0 140px {lay['padding_bottom']}px; }}
.body-text {{ font-size: 24px; font-weight: 300; line-height: 1.8; color: {sub}; }}
.step {{ display: flex; gap: 32px; padding: 34px 0; border-top: 1px solid {line}; align-items: baseline; }}
.step:last-child {{ border-bottom: 1px solid {line}; }}
.step .num {{ font-size: 24px; font-weight: 600; color: {muted}; min-width: 64px; letter-spacing: 0.06em; }}
.step .txt {{ font-size: 30px; font-weight: 400; line-height: 1.6; }}
.qa {{ padding: 36px 0; border-top: 1px solid {line}; }}
.qa:last-child {{ border-bottom: 1px solid {line}; }}
.qa .q {{ font-size: 30px; font-weight: 600; line-height: 1.5; }}
.qa .a {{ font-size: 26px; font-weight: 300; line-height: 1.7; color: {sub}; margin-top: 14px; }}
table {{ width: 100%; border-collapse: collapse; }}
td {{ border-top: 1px solid {line}; border-bottom: 1px solid {line}; padding: 22px 0; vertical-align: top;
      font-size: 22px; line-height: 1.7; }}
td.k {{ width: 240px; color: {muted}; font-weight: 500; padding-right: 24px; }}
td.v {{ color: {sub}; font-weight: 300; }}
</style></head>
<body>{body}</body></html>"""


def _photo_html(photo_uri: str, framed: bool) -> str:
    img = f'<img class="photo verify" src="{photo_uri}" alt="">'
    return f'<div class="frame">{img}</div>' if framed else img


def _text_block(c: Collector, copy: Dict, lay: Dict,
                keys=("eyebrow", "headline", "subcopy", "product_name", "spec"), skip=()) -> str:
    parts = []
    for key in keys:
        if key in skip:
            continue
        text = c.take(copy.get(key), f"copy.{key}")
        if key == "product_name" and text and lay["divider"]:
            parts.append('<div class="divider"></div>')
        parts.append(_div(text, key.replace("_", "-")))
    inner = "".join(p for p in parts if p)
    return f'<header class="text">{inner}</header>' if inner else ""


# ---------------------------------------------------------------------------
# 섹션별 본문
# ---------------------------------------------------------------------------

def body_text_photo(section: Dict, c: Collector, lay: Dict, photo_uri: Optional[str]) -> str:
    copy = section.get("copy", {})
    below = lay["spec_below_photo"] and copy.get("spec")
    text = _text_block(c, copy, lay, skip=("spec",) if below else ())
    photo = _photo_html(photo_uri, bool(lay["photo_frame_width"])) if photo_uri else ""
    footer = ""
    if below:
        footer = f'<footer class="below">{_div(c.take(copy.get("spec"), "copy.spec"), "spec")}</footer>'
    if lay["text_position"] == "bottom":
        return photo + footer + text
    return text + photo + footer


def body_key_points(section: Dict, c: Collector, lay: Dict, photo_uri: Optional[str]) -> str:
    copy = section.get("copy", {})
    text = _text_block(c, copy, lay, keys=("eyebrow", "headline", "subcopy"))
    photo = _photo_html(photo_uri, bool(lay["photo_frame_width"])) if photo_uri else ""
    rows = []
    for i, point in enumerate(section.get("points", [])):
        title = c.take(point.get("title"), f"points[{i}].title")
        if not title:
            continue
        desc = c.take(point.get("desc"), f"points[{i}].desc")
        rows.append(f'<div class="point"><div class="num">{len(rows) + 1:02d}</div><div>'
                    f'{_div(title, "title keep")}{_div(desc, "desc keep")}</div></div>')
    points = f'<section class="points">{"".join(rows)}</section>' if rows else ""
    return text + photo + points


def _label_header(section: Dict, c: Collector) -> str:
    copy = section.get("copy", {})
    headline = c.take(copy.get("headline"), "copy.headline")
    if not headline:
        headline = c.label(STRUCTURAL_LABELS[section["type"]], "label")
    sub = c.take(copy.get("subcopy"), "copy.subcopy")
    return f'<header class="text">{_div(headline, "headline")}{_div(sub, "subcopy")}</header>'


def body_ingredients(section: Dict, c: Collector, lay: Dict, photo_uri: Optional[str]) -> str:
    text = c.take(section.get("body"), "body")
    return _label_header(section, c) + f'<section class="block">{_div(text, "body-text keep")}</section>'


def body_how_to_use(section: Dict, c: Collector, lay: Dict, photo_uri: Optional[str]) -> str:
    rows = []
    for i, step in enumerate(section.get("steps", [])):
        text = c.take(step, f"steps[{i}]")
        if text:
            # 원문에 STEP/번호가 이미 있으면 번호를 덧붙이지 않음
            numbered = re.match(r"^\s*(step\s*\d+|\d+[.)])", text, re.I)
            num = "" if numbered else f'<div class="num">{len(rows) + 1:02d}</div>'
            rows.append(f'<div class="step">{num}{_div(text, "txt keep")}</div>')
    return _label_header(section, c) + f'<section class="block">{"".join(rows)}</section>'


def body_faq(section: Dict, c: Collector, lay: Dict, photo_uri: Optional[str]) -> str:
    rows = []
    for i, qa in enumerate(section.get("faq", [])):
        q = c.take(qa.get("q"), f"faq[{i}].q")
        a = c.take(qa.get("a"), f"faq[{i}].a")
        if q and a:
            rows.append(f'<div class="qa"><div class="q keep">Q. {html.escape(q)}</div>{_div(a, "a keep")}</div>')
    return _label_header(section, c) + f'<section class="block">{"".join(rows)}</section>'


def body_product_info(section: Dict, c: Collector, lay: Dict, photo_uri: Optional[str]) -> str:
    rows = []
    for i, row in enumerate(section.get("rows", [])):
        label = c.take(row.get("label"), f"rows[{i}].label") if row.get("label") else None
        value = c.take(row.get("value"), f"rows[{i}].value")
        if value:
            rows.append(f'<tr><td class="k keep">{html.escape(label or "")}</td>'
                        f'<td class="v keep">{html.escape(value)}</td></tr>')
    return _label_header(section, c) + f'<section class="block"><table>{"".join(rows)}</table></section>'


BODY_BUILDERS = {
    "hero": body_text_photo,
    "intro": body_text_photo,
    "product": body_text_photo,
    "detail": body_text_photo,
    "closing": body_text_photo,
    "key_points": body_key_points,
    "texture": body_key_points,
    "ingredients": body_ingredients,
    "how_to_use": body_how_to_use,
    "faq": body_faq,
    "product_info": body_product_info,
}

# 섹션 타입별 기본 레이아웃 (design.json "layouts" → 섹션 "layout" 순으로 덮어쓰기)
TYPE_LAYOUTS = {
    "hero": {"padding_top": 120, "padding_bottom": 20, "headline_size": 76, "headline_line_height": 1.26,
             "product_name_size": 36, "product_name_color": "#ececec"},
    "intro": {"padding_top": 160},
    "product": {"padding_top": 150, "padding_bottom": 140, "photo_frame_width": 880,
                "photo_frame_margin": 70, "spec_below_photo": True},
    "detail": {"padding_top": 150, "padding_bottom": 140, "photo_frame_width": 880,
               "photo_frame_margin": 70, "spec_below_photo": True},
    "key_points": {"padding_top": 150, "padding_bottom": 150, "photo_frame_width": 880, "photo_frame_margin": 60},
    "ingredients": {"padding_top": 140, "padding_bottom": 140, "headline_size": 44},
    "how_to_use": {"padding_top": 140, "padding_bottom": 140, "headline_size": 44},
    "faq": {"padding_top": 140, "padding_bottom": 140, "headline_size": 44},
    "product_info": {"padding_top": 140, "padding_bottom": 160, "headline_size": 44},
    "closing": {"padding_top": 150, "padding_bottom": 20, "product_name_size": 40,
                "product_name_color": "#ececec", "product_name_gap": 24},
}
TYPE_LAYOUTS["texture"] = TYPE_LAYOUTS["key_points"]


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------

class Renderer:
    """하나의 Chromium 세션으로 여러 섹션을 렌더링합니다."""

    def __init__(self):
        self._pw = None
        self._browser = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        executable = find_chromium()
        self._browser = (self._pw.chromium.launch(executable_path=executable)
                         if executable else self._pw.chromium.launch())
        return self

    def __exit__(self, *exc):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def screenshot(self, html_path: str, output_path: str) -> List[Dict]:
        page = self._browser.new_page(viewport={"width": FIXED_WIDTH, "height": 100}, device_scale_factor=1)
        page.goto(Path(html_path).resolve().as_uri())
        page.evaluate("document.fonts.ready")
        page.wait_for_load_state("networkidle")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=output_path, full_page=True)
        boxes = page.evaluate(
            "Array.from(document.querySelectorAll('img.verify')).map(el => {"
            " const r = el.getBoundingClientRect();"
            " return {x: r.x + scrollX, y: r.y + scrollY, w: r.width, h: r.height}; })"
        )
        page.close()
        return boxes

    def render(self, section: Dict, design: Dict, work_dir: str, output_path: str) -> Dict:
        """섹션 1개 렌더링. 반환: QA용 결과 (카피, 사진, 크기)"""
        section_type = section["type"]
        builder = BODY_BUILDERS.get(section_type)
        if builder is None:
            raise ValueError(f"지원하지 않는 섹션 타입: {section_type}")

        lay = {**LAYOUT_DEFAULTS, **TYPE_LAYOUTS.get(section_type, {}),
               **((design.get("layouts") or {}).get(section_type) or {}), **(section.get("layout") or {})}

        photo_info = None
        photo_uri = None
        image = section.get("image")
        if image and image.get("path"):
            src = PROJECT_ROOT / image["path"]
            if not src.is_file():
                raise FileNotFoundError(f"제품 사진 없음: {image['path']}")
            width = lay["photo_frame_width"] or FIXED_WIDTH
            photo_path, size, scale = prepare_photo(
                str(src), os.path.join(work_dir, f"{section['id']}_photo.png"), image.get("crop"), width)
            photo_uri = Path(photo_path).resolve().as_uri()
            photo_info = {"source": image["path"], "crop": image.get("crop"), "size": list(size),
                          "scale": round(scale, 3), "work_path": photo_path}

        if lay["background"]:
            bg = lay["background"]
        elif photo_info and not lay["photo_frame_width"]:
            bg = edge_color(photo_info["work_path"], "bottom" if lay["text_position"] == "bottom" else "top")
        else:
            bg = design.get("colors", {}).get("background", "#0a0a0a")

        collector = Collector(section["id"])
        body = builder(section, collector, lay, photo_uri)
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        html_path = os.path.join(work_dir, f"{section['id']}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(_document(design, lay, bg, body))

        boxes = self.screenshot(html_path, output_path)
        out = Image.open(output_path).convert("RGB")
        if out.width != FIXED_WIDTH:
            raise RuntimeError(f"출력 너비 오류: {out.width}px")

        if photo_info:
            photo_info["pixel_diff"] = round(verify_photo_region(out, photo_info["work_path"], boxes[0]), 4)
        print(f"Rendered: {section['id']} ({out.width}x{out.height}), 카피 {len(collector.items)}개"
              + (f", 사진 배율 {photo_info['scale']}, 픽셀 차이 {photo_info['pixel_diff']}" if photo_info else ""))
        return {"id": section["id"], "type": section_type, "path": output_path, "size": list(out.size),
                "copies": collector.items, "photo": photo_info}


def render_one(section: Dict, design: Dict, work_dir: str, output_path: str) -> Dict:
    with Renderer() as renderer:
        return renderer.render(section, design, work_dir, output_path)
