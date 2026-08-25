from fastapi.testclient import TestClient

from app.domains.parking_common import ocr
from app.main import app


client = TestClient(app)


def test_extract_plate_normalizes_misread_one_after_hangul() -> None:
    assert ocr.extract_plate(["12가", "3456"]) == "12가3456"
    assert ocr.extract_plate(["12가13456"]) == "12가3456"  # ㅏ 획 오독 잔재 제거
    assert ocr.extract_plate(["99허 9999"]) == "99허9999"
    assert ocr.extract_plate(["12713456"]) is None  # 한글 자체가 사라진 오독은 못 살림
    assert ocr.extract_plate(["12가33456"]) is None  # 5자리인데 '1'로 시작 안 하면 불신


def test_recognize_endpoint_retries_and_returns_plate(monkeypatch) -> None:
    calls: list[float] = []

    class FakeReader:
        def readtext(self, _image, mag_ratio, width_ths):
            calls.append(mag_ratio)
            if mag_ratio == 2.0:
                return [((0, 0, 0, 0), "12713456", 0.9)]  # 1차 오독
            return [((0, 0, 0, 0), "12가", 1.0), ((0, 0, 0, 0), "3456", 0.6)]

    monkeypatch.setattr(ocr, "get_reader", lambda: FakeReader())
    response = client.post(
        "/parking/plate/recognize",
        files={"image": ("plate.png", b"fake-png-bytes", "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {
        "plate": "12가3456", "raw_texts": ["12가", "3456"], "attempts": 2,
    }
    assert calls == [2.0, 1.5]


def test_recognize_endpoint_reports_unreadable_plate(monkeypatch) -> None:
    class BlindReader:
        def readtext(self, _image, **_kwargs):
            return [((0, 0, 0, 0), "hello", 0.3)]

    monkeypatch.setattr(ocr, "get_reader", lambda: BlindReader())
    response = client.post(
        "/parking/plate/recognize",
        files={"image": ("plate.png", b"fake", "image/png")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["data"]["plate"] is None and body["data"]["raw_texts"] == ["hello"]
