"""
아벤투라 두피·뿌리 볼륨 토닉 상세페이지 - Gemini 섹션 이미지 생성
제품 사진(output/aventura/product.png)을 참조 이미지로 함께 전달해 병 디자인을 유지합니다.

실행: python3 scripts/generate_aventura.py
"""

import base64
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from gemini_api import GEMINI_API_KEY, GEMINI_API_URL  # noqa: E402
from stitch_images import stitch_from_directory  # noqa: E402

ROOT = Path(__file__).parent.parent
PRODUCT = ROOT / "output/aventura/product.png"
OUT_DIR = ROOT / "output/aventura/sections"

STYLE = """Premium Korean cosmetic detail page section, 1200px wide, full bleed, no margins.
PHOTOGRAPHY STYLE (MANDATORY): photorealistic luxury product/beauty photography (Sulwhasoo, Laneige ad quality).
NO illustration, NO cartoon. Palette: deep black, charcoal, silver, soft sage green, muted gold accents.
The product is EXACTLY the black 200ml bottle with black spray nozzle in the reference image - keep its shape and label.
Korean typography: elegant Noto Serif KR style headlines, clean sans-serif body, perfectly legible, no typos.
Render ONLY the Korean text given below, exactly as written."""

SECTIONS = [
    ("01_hero", 1400, """Dark studio, product bottle centered on reflective black surface, silver rim light, faint mist.
Top text: '두피는 산뜻하게 / 뿌리 볼륨은 가볍게'. Small text: '드라이 전 뿌리에 뿌리는 데일리 두피 토닉'.
Four thin pill tags: '두피 관리' '뿌리 볼륨' '수분' '산뜻함'. Small brand line 'AVENTURA'."""),
    ("02_why", 1100, """Real Korean woman in her 30s, fine flat hair at the crown, soft natural light, cream background, slightly concerned look.
Headline: '왜 모발은 쉽게 가라앉을까요?'. Below, three circles joined by '+': '두피 컨디셔닝' '산뜻한 사용감' '뿌리 볼륨 연출'.
Bottom band black with text: '뿌리가 살아야 헤어스타일이 살아납니다'."""),
    ("03_scalp", 1000, """Macro photo of healthy clean scalp with fresh water droplets, calm cream and sage tones.
Headline: '건강한 헤어스타일의 첫 단계, 두피 컨디션부터'.
Four card grid: '수분 · 보습 공급' '산뜻한 두피 컨디셔닝' '가볍고 깔끔한 토닉 타입' '멘톨의 청량감'."""),
    ("04_volume", 1200, """Hands lifting hair roots with a round brush while blow-drying, product bottle beside, dark charcoal backdrop, gold accents.
Headline: '힘없이 처지는 뿌리에 자연스럽고 가벼운 볼륨감'.
Vertical 5-step list: '샴푸' '타월로 물기 제거' '뿌리 중심 도포' '손끝 마사지' '뿌리를 들어 올리며 드라이'.
Bottom text: '두피 관리와 볼륨 연출을 하나의 루틴으로'."""),
    ("05_waters", 1100, """Four glass beakers of clear floral water with fresh chamomile, sage, lavender, rosemary, product bottle in middle, soft cream daylight.
Headline: '두피에 닿는 베이스부터 식물 유래 워터를 담았습니다'.
Labels under each herb: '캐모마일꽃수' '살비아잎수' '라벤더수' '로즈마리잎수'."""),
    ("06_botanical", 1000, """Flat lay of many fresh flowers, leaves and roots arranged around the product bottle on linen, sage and cream tones.
Headline: '자연에서 찾은 다양한 식물 유래 성분'. Large number '14' with text '가지 식물 유래 추출물'.
Small text: '황칠나무추출물 외 꽃 · 잎 · 뿌리 유래 성분'."""),
    ("07_peptide", 1000, """Dark lab-luxury scene, product bottle with floating translucent silver molecular spheres, gold light.
Headline: '두피와 모발을 생각한 집중 컨디셔닝 포뮬러'. Big text: '바이오틴 + 5종 펩타이드 복합체'.
Tiny footnote: '※ 화장품 내 일반적인 컨디셔닝 특성에 대한 설명입니다'."""),
    ("08_moisture", 1000, """Cool refreshing scene: product bottle spraying fine mist, water splash, mint leaves, sage-blue light.
Headline: '촉촉함은 더하고 답답한 느낌은 산뜻하게'.
Ingredient chips: '글리세린' '판테놀' '하이드롤라이즈드콜라겐' '멘톨'."""),
    ("09_target", 1100, """Real Korean man and woman with voluminous natural hairstyles, bright clean daylight, smiling naturally.
Headline: '두피와 뿌리 볼륨이 함께 고민이라면'. Check list with sage check icons:
'정수리 볼륨이 쉽게 가라앉는 분' '드라이 후 볼륨이 금방 사라지는 분' '두피가 답답하고 무겁게 느껴지는 분' '끈적이는 헤어 제품이 부담스러운 분'."""),
    ("10_final", 1200, """Dark hero shot of product bottle on black reflective surface, dramatic silver spotlight.
Headline: '두피가 가벼우면 볼륨도 달라집니다'. Text: '아벤투라 두피 · 뿌리 볼륨 토닉 200ml'.
Bottom small text: '아벤투라협동조합'."""),
]


def generate(name: str, height: int, content: str, product_b64: str) -> bool:
    prompt = f"{STYLE}\nCanvas: 1200x{height}px (vertical).\n\n=== CONTENT ===\n{content}"
    payload = {
        "contents": [{"parts": [
            {"inlineData": {"mimeType": "image/png", "data": product_b64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    r = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", json=payload, timeout=180)
    if r.status_code != 200:
        print(f"[{name}] API error {r.status_code}: {r.text[:300]}")
        return False
    for part in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            (OUT_DIR / f"{name}.png").write_bytes(base64.b64decode(part["inlineData"]["data"]))
            print(f"[{name}] saved")
            return True
    print(f"[{name}] no image in response")
    return False


def main():
    if not GEMINI_API_KEY:
        sys.exit("Error: GEMINI_API_KEY not set")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    product_b64 = base64.b64encode(PRODUCT.read_bytes()).decode()
    for i, (name, h, content) in enumerate(SECTIONS):
        if (OUT_DIR / f"{name}.png").exists():
            print(f"[{name}] exists, skip")
            continue
        generate(name, h, content, product_b64)
        if i < len(SECTIONS) - 1:
            time.sleep(3)
    stitch_from_directory(str(OUT_DIR), str(ROOT / "output/aventura/final_page.png"))


if __name__ == "__main__":
    main()
