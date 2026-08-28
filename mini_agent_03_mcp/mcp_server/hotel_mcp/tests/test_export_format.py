import json

from scripts.export_policies import TEXT_FIELDS, normalize_export_row


def test_export_jsonl_one_line_has_exact_fields():
    source = {
        "accommodation_id": 12345,
        "hotel_name": "부산 테스트 호텔",
        "city": "부산",
        "section_title": "기본정보",
        "chunk_index": 0,
        "content": "체크인 15:00",
        "sha": "abc123",
    }
    line = json.dumps(normalize_export_row(source, with_vector=False), ensure_ascii=False)
    decoded = json.loads(line)

    assert set(decoded) == set(TEXT_FIELDS)
    assert decoded == source
    assert "부산 테스트 호텔" in line
