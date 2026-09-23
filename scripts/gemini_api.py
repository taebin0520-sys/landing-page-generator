"""
Gemini API로 배경·공간 연출·보조 비주얼만 생성하는 모듈

원칙:
- 제품병, 로고, 라벨, 글자는 절대 생성하지 않습니다. (제품은 원본 사진, 카피는 HTML/CSS)
- GEMINI_API_KEY는 환경변수에서만 읽습니다.
  키는 URL이 아닌 요청 헤더로 전송하며, 코드·로그·JSON·HTML 어디에도 기록하지 않습니다.
"""

import base64
import os
from pathlib import Path
from typing import Optional

import requests

# Gemini 3 Pro Image Preview 모델 (Nano Banana Pro)
MODEL_NAME = "gemini-3-pro-image-preview"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# 모든 배경 프롬프트에 강제로 붙는 제약
BACKGROUND_CONSTRAINTS = """
=== STRICT CONSTRAINTS (MANDATORY) ===
- Background / environment / supporting visual ONLY.
- NO text, NO letters, NO numbers, NO typography, NO watermark.
- NO logos, NO labels, NO brand marks.
- NO bottles, NO cosmetic containers, NO products of any kind.
- NO people, NO body parts, NO hair, NO scalp.
- Photorealistic studio photography look. NOT illustration, cartoon, or vector art.
- Leave clean empty space where a product photo will be placed later.
"""


def _get_api_key() -> Optional[str]:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    return key or None


def _redact(message: str) -> str:
    """혹시라도 응답/에러 메시지에 키가 포함되면 가립니다."""
    key = _get_api_key()
    return message.replace(key, "[REDACTED]") if key else message


def _post(payload: dict, timeout: int) -> requests.Response:
    key = _get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되지 않았습니다")
    return requests.post(
        GEMINI_API_URL,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        json=payload,
        timeout=timeout,
    )


def generate_background(prompt: str, output_path: str, width: int = 1200, height: int = 800) -> Optional[str]:
    """
    배경/보조 비주얼 이미지를 생성합니다. (글자·제품·인물 없음)

    Returns:
        저장된 파일 경로 또는 None
    """
    full_prompt = f"""Generate a background image, approximately {width}x{height} pixels, full bleed.
{BACKGROUND_CONSTRAINTS}
=== SCENE ===
{prompt}"""

    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    try:
        print(f"Calling API: {MODEL_NAME}")
        response = _post(payload, timeout=180)
        if response.status_code != 200:
            print(f"Error: API returned status {response.status_code}")
            print(_redact(response.text[:500]))
            return None

        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(part["inlineData"]["data"]))
                print(f"Image saved: {output_path}")
                return output_path

        print("Error: No image data in response")
        return None

    except Exception as e:
        print(f"Error: {_redact(str(e))}")
        return None


def test_api_connection() -> bool:
    """API 연결 테스트 (키 값은 출력하지 않음)"""
    if not _get_api_key():
        print("GEMINI_API_KEY: not set")
        return False
    print("GEMINI_API_KEY: set")

    payload = {"contents": [{"parts": [{"text": "Reply with OK."}]}]}
    try:
        response = _post(payload, timeout=30)
        if response.status_code == 200:
            print("API connection successful!")
            return True
        print(f"API test failed: {response.status_code}")
        print(_redact(response.text[:500]))
        return False
    except Exception as e:
        print(f"API test error: {_redact(str(e))}")
        return False


if __name__ == "__main__":
    print("Testing Gemini API connection...")
    test_api_connection()
