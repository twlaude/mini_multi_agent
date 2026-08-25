"""번호판 OCR (코드 단계 — AI 추론 아님). easyocr로 이미지에서 번호판 문자열을 뽑는다.

맥북 실측(2026-08-25): 기본 옵션은 '가'의 ㅏ 획을 '1'로 오독('12713456', '12가13456').
mag_ratio=2(2배 확대)면 굵은 폰트 포함 전부 정확히 잡혀서 1차 시도로 쓰고,
실패하면 다른 확대 비율로 한 번 더 시도한다.
"""

import re

PLATE_PATTERN = re.compile(r"(\d{2,3})([가-힣])(\d{4,5})")
# 시도 순서: (mag_ratio, width_ths)
ATTEMPTS = ((2.0, 0.5), (1.5, 0.9))

_reader = None


def get_reader():
    """easyocr Reader 싱글턴. 모델 로드가 수 초 걸려서 첫 호출 때만 만든다."""
    global _reader
    if _reader is None:
        import easyocr  # 무거운 의존성이라 함수 안에서 import

        _reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
    return _reader


def extract_plate(texts: list[str]) -> str | None:
    """OCR 조각들을 이어 붙여 번호판 패턴을 찾고, 오독 잔재('가' 뒤 '1')를 정리한다."""
    joined = "".join(texts).replace(" ", "")
    match = PLATE_PATTERN.search(joined)
    if not match:
        return None
    head, hangul, tail = match.groups()
    if len(tail) == 5:
        if not tail.startswith("1"):
            return None
        tail = tail[1:]
    return f"{head}{hangul}{tail}"


class NotAnImageError(ValueError):
    """이미지로 디코딩되지 않는 업로드."""


def _decode(image_bytes: bytes):
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise NotAnImageError("이미지로 읽을 수 없는 파일입니다 (jpg/png만 지원).")
    return image


def recognize_plate(image_bytes: bytes) -> dict:
    reader = get_reader()
    image = _decode(image_bytes)
    raw_texts: list[str] = []
    for attempt, (mag_ratio, width_ths) in enumerate(ATTEMPTS, start=1):
        results = reader.readtext(image, mag_ratio=mag_ratio, width_ths=width_ths)
        raw_texts = [text for _box, text, _conf in results]
        plate = extract_plate(raw_texts)
        if plate:
            return {"plate": plate, "raw_texts": raw_texts, "attempts": attempt}
    return {"plate": None, "raw_texts": raw_texts, "attempts": len(ATTEMPTS)}
