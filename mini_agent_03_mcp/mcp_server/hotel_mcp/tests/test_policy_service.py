"""호텔 규정 서비스의 청킹·지연 적재·호텔 격리 검색 테스트."""

from hashlib import sha256

from app.schemas.policy import PolicyChunk, PolicyHit, PolicySection
from app.services import policy_service


class FakeEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [0.1, 0.2]
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self.vector[:] for _ in texts]


class FakeStore:
    def __init__(self, exists: bool = False) -> None:
        self.exists = exists
        self.upserted: tuple[list[PolicyChunk], list[list[float]]] | None = None
        self.search_call: tuple[int, list[float], int] | None = None
        self.hits: list[PolicyHit] = []

    def has_hotel(self, accommodation_id: int) -> bool:
        return self.exists

    def hotel_name(self, accommodation_id: int) -> str | None:
        return "기존 호텔" if self.exists else None

    def upsert(self, chunks: list[PolicyChunk], vectors: list[list[float]]) -> int:
        self.upserted = (chunks, vectors)
        return len(chunks)

    def search(
        self,
        accommodation_id: int,
        query_vector: list[float],
        top_k: int,
    ) -> list[PolicyHit]:
        self.search_call = (accommodation_id, query_vector, top_k)
        return self.hits


def test_chunk_sections_splits_at_item_boundaries_and_hashes():
    sections = [
        PolicySection(title="기본정보", contents=["가" * 500, "나" * 400]),
        PolicySection(title="주차", contents=["주차 가능"]),
        PolicySection(title="긴 안내", contents=["다" * 801]),
    ]

    chunks = policy_service.chunk_sections(123, "테스트 호텔", "부산광역시", sections)

    assert [chunk.chunk_index for chunk in chunks] == list(range(5))
    assert [len(chunk.content) for chunk in chunks] == [500, 400, 5, 800, 1]
    assert [chunk.section_title for chunk in chunks] == [
        "기본정보", "기본정보", "주차", "긴 안내", "긴 안내"
    ]
    assert all(
        chunk.sha == sha256(chunk.content.encode("utf-8")).hexdigest()
        for chunk in chunks
    )


def test_ensure_indexed_miss_fetches_embeds_and_upserts(monkeypatch):
    class FakeClient:
        def policy_sections(self, accommodation_id: int):
            assert accommodation_id == 123
            return (
                "부산 테스트 호텔",
                "부산 해운대구 해운대로 1",
                [PolicySection(title="기본정보", contents=["체크인 15:00"])],
            )

    store = FakeStore()
    embedder = FakeEmbedder()
    monkeypatch.setattr(policy_service.deps, "get_store", lambda: store)
    monkeypatch.setattr(policy_service.deps, "get_embedder", lambda: embedder)
    monkeypatch.setattr(policy_service.deps, "get_client", lambda: FakeClient())

    assert policy_service.ensure_indexed(123) == ("부산 테스트 호텔", True)
    assert embedder.calls == [["체크인 15:00"]]
    assert store.upserted is not None
    chunks, vectors = store.upserted
    assert chunks[0].city == "부산광역시"
    assert vectors == [[0.1, 0.2]]


def test_ask_passes_accommodation_id_filter_to_store(monkeypatch):
    store = FakeStore(exists=True)
    embedder = FakeEmbedder(vector=[0.7, 0.8])
    store.hits = [
        PolicyHit(
            chunk=PolicyChunk(
                accommodation_id=456,
                hotel_name="기존 호텔",
                city="서울특별시",
                section_title="주차",
                chunk_index=0,
                content="주차 가능",
                sha="abc",
            ),
            score=0.91,
        )
    ]
    monkeypatch.setattr(policy_service.deps, "get_store", lambda: store)
    monkeypatch.setattr(policy_service.deps, "get_embedder", lambda: embedder)

    answer = policy_service.ask(456, "주차할 수 있어?", top_k=3)

    assert store.search_call == (456, [0.7, 0.8], 3)
    assert answer.accommodation_id == 456
    assert answer.indexed_now is False
    assert answer.hits == store.hits
