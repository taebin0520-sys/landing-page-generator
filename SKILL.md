---
name: landing-page-generator
description: |
  한국어 상세페이지(랜딩페이지) 자동 생성 스킬. 제품/서비스 정보를 입력받아
  13개 섹션의 고전환 상세페이지를 생성합니다. Gemini API로 섹션별 이미지를
  생성하고 최종 PNG/PDF로 출력합니다.

  Use when: 상세페이지, 랜딩페이지, 제품 소개 페이지, 판매 페이지 생성 요청 시
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Task
  - AskUserQuestion
---

# 상세페이지 생성기 (Landing Page Generator)

## 개요
제품 자료를 한 번 제공하면 전체 상세페이지(1200px 세로 PNG)를 한 번에 제작합니다.
섹션마다 사용자 승인을 받지 않습니다. 질문은 **필수 정보가 실제로 누락되어 제작이 불가능한 경우**에만 합니다.

## 실행 (예: "아벤투라 상세페이지 전체 제작해줘")

1. 사용자가 제공한 자료를 `references/private/<product>/` 에 형식대로 저장
   (형식: `references/templates/product_input/README.md`). 원문은 **한 글자도 바꾸지 않고** 복사.
   기획본이 형식과 다르면 섹션 제목/라벨만 붙이고 문구 자체는 그대로 둔다.
2. `python3 scripts/build_detail_page.py --product <product>` 실행
3. 종료 코드 2(`[제작 불가]`)면 누락 항목만 사용자에게 요청
4. 완료 후 `output/build_report.md` 기준으로 보고:
   생성 섹션 수, 최종 이미지 크기, 사용한 제품 사진, 제외된 문구, 금지어 검사 결과, 원문 누락 여부, 최종 파일 위치

## 파이프라인

```
입력 검증 → 기획본 섹션 자동 분류(parse_source.py) → 섹션 구성 결정 → 금지어 필터
→ 사진 자동 크롭(photo_crop.py) → (선택) Gemini 보조 배경 → 섹션 렌더링(render_section.py, HTML/CSS)
→ 병합(stitch_images.py) → QA(qa.py: 금지어·원문 대조·사진 픽셀·너비) → 보고서
```

섹션 타입: hero, intro, product, key_points, detail, ingredients, how_to_use, faq, product_info, closing
(기획본에 원문이 없는 섹션은 자동 생략. "이런 분께 추천" 섹션은 생성 금지)

## 안전장치 (변경 금지)

- 탈모·발모·개선·완화·재생·치료·예방·기능성 암시 표현 금지 (`scripts/copy_guard.py` + `banned.txt`)
  - 마케팅 카피에 포함 → 해당 문구 제외 후 보고 / 법정 표기(전성분·사용법·제품정보)에 포함 → 빌드 중단
- 제품명·전성분·사용법·제품정보·카피는 제공 원문만 사용, 효능 추가/요약/각색 금지
- 한국어 텍스트는 HTML/CSS 렌더링 (이미지 모델이 글자를 그리지 않음)
- 제품 사진은 크롭/리사이즈만. 병·라벨 AI 재생성 금지. Gemini는 글자·제품·인물 없는 배경에만 (기본 off)
- GEMINI_API_KEY 는 환경변수에서만 읽고 어디에도 기록하지 않음
- 원본 사진·기획본·폰트·브리프는 커밋 금지 (`references/private/`, `assets/private/`, `briefs/*.json`)

## 출력

- `output/sections/NN_<type>.png` 섹션별 PNG
- `output/final_page.png` 최종 병합본
- `output/build_report.md`, `output/build_report.json` QA 보고서
