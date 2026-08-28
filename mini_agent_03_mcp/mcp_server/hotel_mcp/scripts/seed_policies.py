#!/usr/bin/env python3
"""대표 도시의 여기어때 호텔 규정을 순차적으로 pgvector에 적재한다."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ``python scripts/seed_policies.py``로 실행해도 hotel_mcp/app을 찾을 수 있게 한다.
HOTEL_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(HOTEL_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(HOTEL_MCP_ROOT))

from app.clients.yeogi.parser import parse_policy_sections
from app.core.config import get_settings
from app.core.deps import get_client, get_store
from app.services import policy_service
from app.services.dates import default_dates


CITIES = (
    "서울", "부산", "제주", "강릉", "경주", "여수", "전주", "속초", "인천", "대구",
    "대전", "광주", "춘천", "가평", "통영", "포항", "수원", "천안", "안동", "군산",
)
SEED_SORTS = ("HIRATING", "LOWPRICE")
MAX_SEARCH_PAGES = 3


@dataclass
class Candidate:
    accommodation_id: int
    name: str
    city: str


@dataclass
class CityCounts:
    success: int = 0
    fail: int = 0
    skip: int = 0
    dry_run: int = 0


class NetworkPacer:
    """여기어때 네트워크 요청 사이의 최소 간격을 보장한다."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._last_finished: float | None = None

    def before_request(self) -> None:
        if self._last_finished is None:
            return
        remaining = self.delay - (time.monotonic() - self._last_finished)
        if remaining > 0:
            time.sleep(remaining)

    def after_request(self) -> None:
        self._last_finished = time.monotonic()


def _sort_code(value: Any) -> str | None:
    """캐시의 영문/한글 정렬명 변형을 시딩 정렬 코드로 정규화한다."""
    if not isinstance(value, str):
        return None
    compact = re.sub(r"[\s_-]+", "", value).upper()
    if compact in {"HIRATING", "평점높은순", "높은평점순", "평점순"}:
        return "HIRATING"
    if compact in {
        "LOWPRICE", "낮은가격순", "가격낮은순", "가격순", "저가순", "최저가순",
    }:
        return "LOWPRICE"
    return None


def _load_raw_index(raw_cache: Path | None) -> dict[int, dict[str, Any]]:
    if raw_cache is None:
        return {}
    index_path = raw_cache / "_index.json"
    if not index_path.is_file():
        print(f"[WARN] raw cache index 없음: {index_path}; 네트워크 검색으로 보충")
        return {}
    with index_path.open(encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"raw cache index는 JSON object여야 합니다: {index_path}")

    entries: dict[int, dict[str, Any]] = {}
    for raw_id, raw_entry in payload.items():
        if not isinstance(raw_entry, dict):
            continue
        try:
            accommodation_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        entries[accommodation_id] = raw_entry
    return entries


def _cached_candidates(
    raw_index: dict[int, dict[str, Any]], city: str, sort_type: str, limit: int
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for accommodation_id, entry in raw_index.items():
        if str(entry.get("city") or "").strip() != city:
            continue
        sorts = entry.get("sorts") or []
        if not isinstance(sorts, list) or sort_type not in {_sort_code(item) for item in sorts}:
            continue
        candidates.append(
            Candidate(
                accommodation_id=accommodation_id,
                name=str(entry.get("name") or "").strip(),
                city=city,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _network_candidates(
    city: str,
    sort_type: str,
    wanted: int,
    existing_ids: set[int],
    pacer: NetworkPacer,
) -> list[Candidate]:
    """캐시에 부족한 정렬 후보만, 최대 3페이지를 순차 조회해 보충한다."""
    if wanted <= 0:
        return []

    client = get_client()
    check_in, check_out = default_dates("", "")
    found: list[Candidate] = []
    for page in range(1, MAX_SEARCH_PAGES + 1):
        pacer.before_request()
        try:
            result = client.search_page(
                city,
                check_in,
                check_out,
                personal=2,
                page=page,
                sort_type=sort_type,
                category="호텔",
            )
        finally:
            pacer.after_request()

        for hotel in result.items:
            accommodation_id = int(hotel.id)
            if accommodation_id in existing_ids:
                continue
            existing_ids.add(accommodation_id)
            found.append(
                Candidate(
                    accommodation_id=accommodation_id,
                    name=hotel.name or "",
                    city=city,
                )
            )
            if len(found) >= wanted:
                return found
        if not result.items or page >= result.total_pages:
            break
    return found


def _city_candidates(
    city: str,
    per_sort: int,
    raw_index: dict[int, dict[str, Any]],
    pacer: NetworkPacer,
) -> tuple[list[Candidate], int]:
    """정렬별 목표 수를 캐시 우선으로 모은 뒤 호텔 ID로 합친다."""
    combined: dict[int, Candidate] = {}
    search_failures = 0
    for sort_type in SEED_SORTS:
        per_sort_candidates = _cached_candidates(raw_index, city, sort_type, per_sort)
        per_sort_ids = {candidate.accommodation_id for candidate in per_sort_candidates}
        missing = per_sort - len(per_sort_candidates)
        if missing:
            try:
                per_sort_candidates.extend(
                    _network_candidates(city, sort_type, missing, per_sort_ids, pacer)
                )
            except Exception as error:
                search_failures += 1
                print(f"[{city}] SEARCH-FAIL sort={sort_type}: {error}")
        for candidate in per_sort_candidates[:per_sort]:
            combined.setdefault(candidate.accommodation_id, candidate)
    return list(combined.values()), search_failures


def _index_cached(
    raw_path: Path,
    candidate: Candidate,
) -> tuple[str, int]:
    with raw_path.open(encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("raw cache payload는 JSON object여야 합니다")

    parsed_name, _address, sections = parse_policy_sections(payload)
    raw_entry = payload.get("index") or {}
    if not isinstance(raw_entry, dict):
        raw_entry = {}
    hotel_name = parsed_name or str(raw_entry.get("name") or candidate.name).strip()
    city = str(raw_entry.get("city") or candidate.city).strip()
    if not hotel_name:
        hotel_name = str(candidate.accommodation_id)
    if not sections:
        raise ValueError("파싱된 규정 섹션이 없습니다")

    indexed = policy_service.index_sections(
        candidate.accommodation_id,
        hotel_name,
        city,
        sections,
    )
    return hotel_name, int(indexed or 0)


def seed_city(
    city: str,
    per_sort: int,
    raw_cache: Path | None,
    raw_index: dict[int, dict[str, Any]],
    dry_run: bool,
    pacer: NetworkPacer,
) -> CityCounts:
    counts = CityCounts()
    candidates, search_failures = _city_candidates(city, per_sort, raw_index, pacer)
    counts.fail += search_failures
    store = None if dry_run else get_store()

    for candidate in candidates:
        prefix = f"[{city}] id={candidate.accommodation_id} name={candidate.name or '-'}"
        if dry_run:
            counts.dry_run += 1
            print(f"{prefix} DRY-RUN")
            continue
        try:
            if store.has_hotel(candidate.accommodation_id):
                counts.skip += 1
                print(f"{prefix} SKIP already-indexed")
                continue

            raw_path = raw_cache / f"{candidate.accommodation_id}.json" if raw_cache else None
            if raw_path is not None and raw_path.is_file():
                hotel_name, chunks = _index_cached(raw_path, candidate)
                counts.success += 1
                print(f"[{city}] id={candidate.accommodation_id} name={hotel_name} OK cache chunks={chunks}")
            else:
                pacer.before_request()
                try:
                    hotel_name, indexed_now = policy_service.ensure_indexed(
                        candidate.accommodation_id
                    )
                finally:
                    pacer.after_request()
                if indexed_now:
                    counts.success += 1
                    print(f"[{city}] id={candidate.accommodation_id} name={hotel_name} OK network")
                else:
                    counts.skip += 1
                    print(f"[{city}] id={candidate.accommodation_id} name={hotel_name} SKIP already-indexed")
        except Exception as error:
            counts.fail += 1
            print(f"{prefix} FAIL {type(error).__name__}: {error}")

    print(
        f"[{city}] SUMMARY success={counts.success} fail={counts.fail} "
        f"skip={counts.skip} dry-run={counts.dry_run} candidates={len(candidates)}"
    )
    return counts


def _parse_cities(value: str) -> list[str]:
    requested = [city.strip() for city in value.split(",") if city.strip()]
    if not requested:
        raise argparse.ArgumentTypeError("도시를 하나 이상 지정해야 합니다")
    invalid = [city for city in requested if city not in CITIES]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"지원하지 않는 도시: {', '.join(invalid)} (허용: {', '.join(CITIES)})"
        )
    return list(dict.fromkeys(requested))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="대표 도시 호텔 규정 pgvector 시딩")
    parser.add_argument(
        "--cities",
        type=_parse_cities,
        default=list(CITIES),
        help="쉼표로 구분한 도시(기본: 고정 20개 도시 전체)",
    )
    parser.add_argument(
        "--per-sort",
        type=int,
        default=20,
        help="도시별 정렬당 후보 수(1~60, 기본: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="후보만 출력하고 DB 조회·상세 조회·임베딩·적재는 하지 않음",
    )
    parser.add_argument(
        "--raw-cache",
        type=Path,
        help="_index.json 및 <accommodation_id>.json이 있는 선수집 디렉터리",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.per_sort <= 60:
        parser.error("--per-sort는 1~60 사이여야 합니다")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_cache = args.raw_cache.expanduser().resolve() if args.raw_cache else None
    try:
        raw_index = _load_raw_index(raw_cache)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[FATAL] raw cache index 읽기 실패: {error}", file=sys.stderr)
        return 2

    settings = get_settings()
    pacer = NetworkPacer(settings.page_delay)
    totals = CityCounts()
    for city in args.cities:
        counts = seed_city(
            city,
            args.per_sort,
            raw_cache,
            raw_index,
            args.dry_run,
            pacer,
        )
        totals.success += counts.success
        totals.fail += counts.fail
        totals.skip += counts.skip
        totals.dry_run += counts.dry_run

    print(
        f"[TOTAL] success={totals.success} fail={totals.fail} "
        f"skip={totals.skip} dry-run={totals.dry_run}"
    )
    return 1 if totals.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
