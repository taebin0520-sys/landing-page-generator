# 제품 입력 폴더 형식

`references/private/<product>/` 에 아래 파일을 넣고 한 번만 실행합니다. (이 폴더는 gitignore 대상)

```
python3 scripts/build_detail_page.py --product <product>          # 전체 제작
python3 scripts/build_detail_page.py --product <product> --check  # 검증·분류만
```

| 파일 | 필수 | 내용 |
|------|------|------|
| `product_name.txt` | 필수 | 제품명 원문 1줄 |
| `plan.md` | 필수 | 상세페이지 전체 기획본 |
| `ingredients.txt` | 필수 | 전성분 원문 |
| `how_to_use.txt` | 필수 | 사용방법 원문 (한 줄 = 한 단계) |
| `product_info.txt` | 필수 | 제품정보/주의사항 (`항목: 내용`, 콜론 없는 줄은 앞 항목에 이어짐) |
| `photos/` | 필수 | 제품 사진 (png/jpg/webp, 누끼 PNG 가능) |
| `banned.txt` | 선택 | 추가 금지 표현 (한 줄에 하나) |
| `design.json` | 선택 | 디자인 참고사항 (아래) |

## plan.md 작성 형식

섹션 제목은 `## 제목` 또는 `[제목]` / `[N번 섹션]`. 제목 키워드로 섹션 타입을 자동 분류합니다.

| 타입 | 제목 키워드 예 |
|------|----------------|
| hero | 히어로, 메인, 1번 |
| intro | 도입, 인트로, 2번 |
| product | 제품 소개, 소개, 3번 |
| key_points | 사용감, 포인트, 특징, 4번 |
| detail | 디테일, 용기, 5번 |
| faq | FAQ, 자주 묻는 질문 |
| closing | 클로징, 마무리 |
| (제외) | 추천, 이런 분, 타깃 → 생성 금지 |

필드 라벨: `헤드라인:` `본문:`(서브/설명) `용량:` `제품명:` `소제목:` `포인트: 제목 | 설명` `Q:` `A:` `단계:` `출처:`
- 라벨만 있는 줄(`[헤드라인]`) 다음 줄부터 빈 줄 전까지가 값 (줄바꿈 그대로 유지)
- `없음` 은 무시
- `출처:` 가 없으면 `plan.md '섹션명' N행` 이 source 로 기록됩니다

## design.json (선택)

```json
{
  "photo_status": "사진 교체 대기",
  "photos": {"hero": "photos/01.webp", "detail": "none"},
  "crops": {"hero": {"left": 0, "top": 0, "right": 1200, "bottom": 1600}},
  "layouts": {"hero": {"headline_size": 76}},
  "colors": {"text": "#f2f2f2", "background": "#0a0a0a"},
  "upper_ratio": 0.6,
  "gemini": {"enabled": false, "sections": {"key_points": "배경 장면 설명 (글자/제품/인물 없음)"}}
}
```

지정하지 않은 사진·크롭은 자동으로 결정됩니다 (자동 크롭은 보고서에 경고로 표시).
