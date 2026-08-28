"""호텔 규정 청크 생성, 지연 적재, 벡터 검색 로직."""

from __future__ import annotations

from hashlib import sha256

from app.core import deps
from app.schemas.policy import PolicyAnswer, PolicyChunk, PolicySection


MAX_CHUNK_CHARS = 800

_CITY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("서울특별시", ("서울특별시", "서울시", "서울")),
    ("부산광역시", ("부산광역시", "부산시", "부산")),
    ("대구광역시", ("대구광역시", "대구시", "대구")),
    ("인천광역시", ("인천광역시", "인천시", "인천")),
    ("광주광역시", ("광주광역시", "광주시", "광주")),
    ("대전광역시", ("대전광역시", "대전시", "대전")),
    ("울산광역시", ("울산광역시", "울산시", "울산")),
    ("세종특별자치시", ("세종특별자치시", "세종시", "세종")),
    ("경기도", ("경기도", "경기")),
    ("강원특별자치도", ("강원특별자치도", "강원도", "강원")),
    ("충청북도", ("충청북도", "충북")),
    ("충청남도", ("충청남도", "충남")),
    ("전북특별자치도", ("전북특별자치도", "전라북도", "전북")),
    ("전라남도", ("전라남도", "전남")),
    ("경상북도", ("경상북도", "경북")),
    ("경상남도", ("경상남도", "경남")),
    ("제주특별자치도", ("제주특별자치도", "제주도", "제주")),
)


def normalize_city(address: str) -> str:
    """주소 첫 행정구역을 공식 대표명으로 정규화한다."""
    normalized = " ".join(address.split())
    for city, aliases in _CITY_ALIASES:
        if any(normalized.startswith(alias) for alias in aliases):
            return city
    return normalized.split(" ", 1)[0] if normalized else "미상"


def _split_contents(contents: list[str], max_chars: int) -> list[str]:
    """contents 경계를 보존하고, 단일 항목만 너무 길 때 하드 분할한다."""
    chunks: list[str] = []
    pending: list[str] = []
    pending_chars = 0

    def flush() -> None:
        nonlocal pending, pending_chars
        if pending:
            chunks.append("\n".join(pending))
            pending = []
            pending_chars = 0

    for raw_item in contents:
        item = raw_item.strip()
        if not item:
            continue
        if len(item) > max_chars:
            flush()
            chunks.extend(
                item[start:start + max_chars]
                for start in range(0, len(item), max_chars)
            )
            continue

        joined_chars = pending_chars + (1 if pending else 0) + len(item)
        if pending and joined_chars > max_chars:
            flush()
        pending.append(item)
        pending_chars += (1 if len(pending) > 1 else 0) + len(item)

    flush()
    return chunks


def chunk_sections(
    accommodation_id: int,
    hotel_name: str,
    city: str,
    sections: list[PolicySection],
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[PolicyChunk]:
    """규정 섹션을 최대 길이 청크로 바꾸고 전역 순번과 SHA-256을 붙인다."""
    if max_chars < 1:
        raise ValueError("max_chars는 1 이상이어야 합니다.")

    chunks: list[PolicyChunk] = []
    for section in sections:
        for content in _split_contents(section.contents, max_chars):
            chunks.append(
                PolicyChunk(
                    accommodation_id=accommodation_id,
                    hotel_name=hotel_name,
                    city=city,
                    section_title=section.title,
                    chunk_index=len(chunks),
                    content=content,
                    sha=sha256(content.encode("utf-8")).hexdigest(),
                )
            )
    return chunks


def index_sections(
    accommodation_id: int,
    hotel_name: str,
    city: str,
    sections: list[PolicySection],
) -> int:
    """이미 파싱된 규정 섹션을 공용 싱글턴으로 임베딩하고 upsert한다."""
    chunks = chunk_sections(accommodation_id, hotel_name, city, sections)
    if not chunks:
        raise ValueError(f"accommodation_id={accommodation_id}에 적재할 규정이 없습니다.")
    vectors = deps.get_embedder().embed([chunk.content for chunk in chunks])
    return deps.get_store().upsert(chunks, vectors)


def ensure_indexed(accommodation_id: int) -> tuple[str, bool]:
    """이미 적재된 호텔은 재사용하고, 처음 본 호텔만 여기어때에서 읽어 적재한다."""
    store = deps.get_store()
    if store.has_hotel(accommodation_id):
        hotel_name = store.hotel_name(accommodation_id)
        if not hotel_name:
            raise RuntimeError(f"accommodation_id={accommodation_id}의 호텔 이름이 없습니다.")
        return hotel_name, False

    hotel_name, address, sections = deps.get_client().policy_sections(accommodation_id)
    if not hotel_name:
        raise ValueError(f"accommodation_id={accommodation_id} 숙소 정보를 찾지 못했습니다.")
    index_sections(
        accommodation_id=accommodation_id,
        hotel_name=hotel_name,
        city=normalize_city(address),
        sections=sections,
    )
    return hotel_name, True


def ask(accommodation_id: int, question: str, top_k: int = 4) -> PolicyAnswer:
    """특정 호텔 안에서만 질문과 가까운 규정 청크를 반환한다."""
    if accommodation_id < 1:
        raise ValueError("accommodation_id는 1 이상이어야 합니다.")
    question = question.strip()
    if not question:
        raise ValueError("question은 빈 문자열일 수 없습니다.")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k는 1~10 사이여야 합니다.")

    hotel_name, indexed_now = ensure_indexed(accommodation_id)
    query_vector = deps.get_embedder().embed([question])[0]
    hits = deps.get_store().search(accommodation_id, query_vector, top_k)
    return PolicyAnswer(
        accommodation_id=accommodation_id,
        hotel_name=hotel_name,
        indexed_now=indexed_now,
        hits=hits,
    )
