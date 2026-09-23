"""
제품 사진 자동 크롭 모듈

- 사진 픽셀은 절대 수정하지 않습니다. 크롭 박스(원본 좌표)만 계산합니다.
- 누끼 PNG(투명 배경)는 알파 채널로, 배경이 있는 사진은 모서리 배경색과의
  차이로 제품 영역을 추정합니다. 받침대처럼 제품보다 넓은 물체는 행 너비가
  급격히 넓어지는 지점을 제품 하단으로 판단해 분리합니다.
- design.json 의 crops 지정값이 있으면 자동 계산보다 우선합니다.
"""

from statistics import median
from typing import Dict, Optional, Tuple

from PIL import Image, ImageChops, ImageFilter, ImageStat

Box = Tuple[int, int, int, int]


def has_alpha(img: Image.Image) -> bool:
    return "A" in img.getbands() and img.getchannel("A").getextrema()[0] < 255


def detect_product_box(path: str) -> Dict:
    """제품 영역 추정. 반환: {box, has_alpha, size, below}  below: 제품 아래 받침대 등 유무"""
    img = Image.open(path)
    if has_alpha(img):
        box = img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
        return {"box": box, "has_alpha": True, "size": img.size, "below": False}

    rgb = img.convert("RGB")
    w, h = rgb.size
    k = max(4, min(w, h) // 40)
    corners = [rgb.crop(b) for b in ((0, 0, k, k), (w - k, 0, w, k))]  # 상단 모서리 = 배경
    bg = tuple(round(sum(ImageStat.Stat(c).mean[i] for c in corners) / 2) for i in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg)).convert("L")
    mask = diff.point(lambda v: 255 if v > 28 else 0).filter(ImageFilter.MedianFilter(5))

    rows = []
    for y in range(h):
        bbox = mask.crop((0, y, w, y + 1)).getbbox()
        rows.append((bbox[0], bbox[2]) if bbox else None)

    ys = [y for y, r in enumerate(rows) if r]
    if not ys:
        return {"box": (0, 0, w, h), "has_alpha": False, "size": (w, h), "below": False}
    top = ys[0]

    # 제품 폭 기준: 상단~중간 구간 행 너비의 중앙값
    widths = [(rows[y][1] - rows[y][0], y) for y in ys]
    body = [wd for wd, y in widths if y < top + (h - top) * 0.6]
    ref = median(sorted(body)[len(body) // 2:]) if body else w
    bottom, below = ys[-1], False
    for wd, y in widths:
        if y > top + (h - top) * 0.3 and wd > max(ref * 1.6, w * 0.5):
            bottom, below = y, True
            break
    xs = [rows[y] for y in ys if y <= bottom]
    left = int(median(x[0] for x in xs[len(xs) // 3:]))
    right = int(median(x[1] for x in xs[len(xs) // 3:]))
    # 노즐처럼 옆으로 튀어나온 부분 포함
    right = max(right, max(x[1] for x in xs[: len(xs) // 3] or [right]))
    return {"box": (left, top, right, bottom), "has_alpha": False, "size": (w, h), "below": below}


def _clamp(box, size) -> Box:
    w, h = size
    l, t, r, b = box
    return (max(0, int(l)), max(0, int(t)), min(w, int(r)), min(h, int(b)))


def _centered(cx: float, width: float, img_w: int) -> Tuple[float, float]:
    width = min(width, img_w)
    left = min(max(0, cx - width / 2), img_w - width)
    return left, left + width


def auto_crop(info: Dict, preset: str, upper_ratio: float = 0.6) -> Box:
    """
    크롭 프리셋:
        full   제품 전체 + 받침대 일부 (hero, closing)
        top    노즐/캡 상단부 (intro)  - 라벨 글자 대부분 제외
        upper  제품 상단 ~ upper_ratio 지점 (product 클로즈업)
        whole  사진 전체
    """
    w, h = info["size"]
    l, t, r, b = info["box"]
    bw, bh = r - l, b - t
    cx = l + bw / 2

    if preset == "whole":
        return (0, 0, w, h)
    if preset == "full":
        left, right = _centered(cx, max(bw / 0.37, 1200), w)
        extra = bh * (0.15 if info["below"] else 0.08)
        return _clamp((left, t - bh * 0.05, right, b + extra), (w, h))
    if preset == "top":
        left, right = _centered(cx, max(bw * 2.7, 1200), w)
        return _clamp((left, t - bh * 0.1, right, t + bh * 0.3), (w, h))
    if preset == "upper":
        left, right = _centered(cx, bw * 2.26, w)
        return _clamp((left, t - bh * 0.06, right, t + bh * upper_ratio), (w, h))
    raise ValueError(f"unknown preset: {preset}")


def resolve_crop(path: str, preset: str, override: Optional[Dict] = None,
                 upper_ratio: float = 0.6) -> Dict:
    """design.json 지정 크롭이 있으면 사용, 없으면 자동 계산"""
    if override:
        return {"left": override.get("left"), "top": override.get("top"),
                "right": override.get("right"), "bottom": override.get("bottom"), "mode": "manual"}
    info = detect_product_box(path)
    l, t, r, b = auto_crop(info, preset, upper_ratio)
    return {"left": l, "top": t, "right": r, "bottom": b, "mode": f"auto:{preset}"}
