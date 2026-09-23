"""
one-shot 파이프라인 테스트 (가상 제품 데이터 사용 - 실제 제품 카피 아님)

    python3 -m unittest tests.test_pipeline -v
"""

import shutil
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_detail_page import DEFAULT_FONTS, build  # noqa: E402
from scripts.copy_guard import set_extra_banned_terms  # noqa: E402
from scripts.parse_source import InputError, parse_plan  # noqa: E402

TMP_ROOT = PROJECT_ROOT / "output" / "_test"
INPUT_ROOT = TMP_ROOT / "input"
PRODUCT = "sample"
KEEP_OUTPUT = bool(__import__("os").environ.get("KEEP_TEST_OUTPUT"))

PLAN = """[1번 섹션]
[헤드라인]
테스트 헤드라인 첫 줄
테스트 헤드라인 둘째 줄
출처: 테스트 기획본 1p

## 도입
헤드라인: 테스트 도입 문구
본문: 두피 개선 테스트 문구

## 이런 분께 추천
- 추천 대상 문구

## 제품 소개
헤드라인: 테스트 소개 문구
본문: 테스트 소개 본문
용량: 100ml

## 사용감 포인트
헤드라인: 테스트 포인트 헤드라인
포인트: 포인트 하나 | 설명 하나
포인트: 포인트 둘

## FAQ
Q: 테스트 질문
A: 테스트 답변

## 클로징
헤드라인: 테스트 마무리 문구
"""


def make_photo(path: Path, cutout: bool = False) -> None:
    if cutout:
        img = Image.new("RGBA", (400, 1000), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle((60, 40, 340, 960), fill=(40, 40, 40, 255))
    else:
        img = Image.new("RGB", (1500, 2000), (12, 12, 12))
        d = ImageDraw.Draw(img)
        d.rectangle((650, 300, 850, 400), fill=(60, 60, 60))      # 캡
        d.rectangle((560, 400, 940, 1600), fill=(70, 70, 70))     # 병
        d.rectangle((200, 1600, 1500, 2000), fill=(90, 90, 90))   # 받침대
    img.save(path)


def make_input(**overrides) -> None:
    base = INPUT_ROOT / PRODUCT
    if base.exists():
        shutil.rmtree(base)
    (base / "photos").mkdir(parents=True)
    files = {
        "product_name.txt": "테스트 제품",
        "plan.md": PLAN,
        "ingredients.txt": "정제수, 글리세린, 테스트성분",
        "how_to_use.txt": "첫 번째 테스트 단계\n두 번째 테스트 단계",
        "product_info.txt": "용량: 100ml\n제조국: 테스트\n주의사항: 테스트 주의 1\n테스트 주의 2",
        "banned.txt": "금지테스트어",
    }
    files.update(overrides)
    for name, text in files.items():
        if text is not None:
            (base / name).write_text(text, encoding="utf-8")
    make_photo(base / "photos" / "01.png")
    make_photo(base / "photos" / "02_cutout.png", cutout=True)


class ParsePlanTest(unittest.TestCase):
    def test_sections_and_exclusion(self):
        sections, notes = parse_plan(PLAN)
        self.assertEqual(set(sections), {"hero", "intro", "product", "key_points", "faq", "closing"})
        self.assertEqual(sections["hero"]["fields"]["headline"]["text"], "테스트 헤드라인 첫 줄\n테스트 헤드라인 둘째 줄")
        self.assertEqual(sections["hero"]["fields"]["headline"]["source"], "테스트 기획본 1p")
        self.assertTrue(any("추천" in n["reason"] for n in notes))
        self.assertTrue(any(n["text"] == "- 추천 대상 문구" for n in notes))


@unittest.skipUnless(all((PROJECT_ROOT / p).exists() for p in DEFAULT_FONTS.values()), "폰트 없음")
class BuildTest(unittest.TestCase):
    def tearDown(self):
        set_extra_banned_terms([])
        (PROJECT_ROOT / "briefs" / f"{PRODUCT}.json").unlink(missing_ok=True)

    @classmethod
    def tearDownClass(cls):
        if not KEEP_OUTPUT:
            shutil.rmtree(TMP_ROOT, ignore_errors=True)

    def test_missing_required_input(self):
        make_input(**{"ingredients.txt": None})
        with self.assertRaises(InputError) as ctx:
            build(PRODUCT, input_root=INPUT_ROOT, output_root=TMP_ROOT / "out")
        self.assertIn("전성분", str(ctx.exception))

    def test_banned_in_legal_text_stops(self):
        make_input(**{"how_to_use.txt": "탈모 테스트 단계"})
        with self.assertRaises(InputError):
            build(PRODUCT, input_root=INPUT_ROOT, output_root=TMP_ROOT / "out")

    def test_full_build(self):
        make_input()
        out = TMP_ROOT / "out"
        report = build(PRODUCT, input_root=INPUT_ROOT, output_root=out)

        types = [s["type"] for s in report["sections"]]
        for expected in ("hero", "intro", "product", "key_points", "ingredients",
                         "how_to_use", "faq", "product_info", "closing"):
            self.assertIn(expected, types)
        self.assertNotIn("detail", types)  # 기획본에 디테일 섹션 없음

        qa = report["qa"]
        self.assertTrue(qa["passed"], qa)
        self.assertEqual(qa["banned_hits"], [])
        self.assertEqual(qa["verbatim_fail"], [])
        self.assertEqual(report["final_size"][0], 1200)
        self.assertTrue((out / "final_page.png").is_file())
        self.assertTrue((out / "build_report.md").is_file())
        self.assertEqual(len(list((out / "sections").glob("*.png"))), len(types))

        excluded = [e["text"] for e in report["excluded"]]
        self.assertIn("두피 개선 테스트 문구", excluded)
        rendered_texts = [c["text"] for s in report["sections"] for c in s.get("copies", [])]
        self.assertFalse(any("추천" in t for t in rendered_texts))
        for section in report["sections"]:
            if section.get("photo"):
                self.assertLessEqual(section["photo"]["pixel_diff"], 0.5)


if __name__ == "__main__":
    unittest.main()
