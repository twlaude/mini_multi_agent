"""호텔 규정 fixture 파서 테스트. 네트워크·DB를 사용하지 않는다."""

import json
from pathlib import Path

from app.clients.yeogi.parser import parse_policy_sections


def test_parse_policy_sections_adds_theme_and_cleans_html():
    fixture_path = Path(__file__).parent / "fixtures" / "detail_sample.json"
    detail = json.loads(fixture_path.read_text(encoding="utf-8"))

    hotel_name, address, sections = parse_policy_sections(detail)

    assert hotel_name == "부산 샘플 호텔"
    assert address == "부산광역시 해운대구 샘플로 1"
    assert [section.title for section in sections] == ["기본정보", "인원 추가 정보", "편의시설"]
    assert sections[0].contents == ["체크인 : 15:00 | 체크아웃 : 11:00", "주차 가능"]
    assert sections[-1].contents == ["와이파이", "피트니스"]
    assert all("<" not in item and ">" not in item for section in sections for item in section.contents)
