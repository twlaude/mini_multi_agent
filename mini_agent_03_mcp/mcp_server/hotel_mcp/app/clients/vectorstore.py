"""공용 documents 테이블을 쓰는 호텔 규정 pgvector 저장소."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from app.schemas.policy import PolicyChunk, PolicyHit


COLLECTION_NAME = "hotel_policy"


class PolicyStore:
    """호텔 규정 청크를 현재 임베딩 공급자·모델 범위에서 읽고 쓴다."""

    def __init__(
        self,
        database_url: str,
        embedding_provider: str,
        embedding_model: str,
    ) -> None:
        self.database_url = database_url
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.collection_name = COLLECTION_NAME

    def _connect(self):
        connection = psycopg.connect(self.database_url)
        register_vector(connection)
        return connection

    def has_hotel(self, accommodation_id: int) -> bool:
        """현재 공급자·모델로 적재된 해당 호텔 청크가 하나라도 있는지 확인한다."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM documents
                    WHERE collection_name = %s
                      AND embedding_provider = %s
                      AND embedding_model = %s
                      AND metadata->>'accommodation_id' = %s
                )
                """,
                (
                    self.collection_name,
                    self.embedding_provider,
                    self.embedding_model,
                    str(accommodation_id),
                ),
            )
            return bool(cursor.fetchone()[0])

    def hotel_name(self, accommodation_id: int) -> str | None:
        """이미 적재된 호텔 이름을 반환하고, 없으면 None을 반환한다."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT metadata->>'hotel_name'
                FROM documents
                WHERE collection_name = %s
                  AND embedding_provider = %s
                  AND embedding_model = %s
                  AND metadata->>'accommodation_id' = %s
                ORDER BY chunk_index
                LIMIT 1
                """,
                (
                    self.collection_name,
                    self.embedding_provider,
                    self.embedding_model,
                    str(accommodation_id),
                ),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def upsert(self, chunks: list[PolicyChunk], vectors: list[list[float]]) -> int:
        """결정적 UUID로 청크를 넣어 동일 호텔 재적재를 idempotent하게 만든다."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks와 vectors의 개수가 같아야 합니다.")
        if not chunks:
            return 0

        dimensions = {len(vector) for vector in vectors}
        if 0 in dimensions or len(dimensions) != 1:
            raise ValueError("모든 embedding은 같은 양의 차원이어야 합니다.")

        rows = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            metadata = {
                "accommodation_id": chunk.accommodation_id,
                "hotel_name": chunk.hotel_name,
                "city": chunk.city,
                "section_title": chunk.section_title,
                "sha": chunk.sha,
            }
            rows.append(
                (
                    uuid5(
                        NAMESPACE_URL,
                        f"hotel_policy:{chunk.accommodation_id}:{chunk.chunk_index}",
                    ),
                    self.collection_name,
                    f"{chunk.hotel_name} · {chunk.section_title}",
                    chunk.content,
                    f"yeogi:{chunk.accommodation_id}",
                    chunk.chunk_index,
                    self.embedding_provider,
                    self.embedding_model,
                    len(vector),
                    vector,
                    Jsonb(metadata),
                )
            )

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO documents (
                    id, collection_name, title, content, source, chunk_index,
                    embedding_provider, embedding_model, embedding_dimension,
                    embedding, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    collection_name = EXCLUDED.collection_name,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    source = EXCLUDED.source,
                    chunk_index = EXCLUDED.chunk_index,
                    embedding_provider = EXCLUDED.embedding_provider,
                    embedding_model = EXCLUDED.embedding_model,
                    embedding_dimension = EXCLUDED.embedding_dimension,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """,
                rows,
            )
        return len(rows)

    def search(
        self,
        accommodation_id: int,
        query_vector: list[float],
        top_k: int,
    ) -> list[PolicyHit]:
        """호텔 ID를 먼저 격리한 뒤 그 호텔 청크 안에서만 코사인 검색한다."""
        if not query_vector:
            raise ValueError("query_vector는 비어 있을 수 없습니다.")
        if top_k < 1:
            raise ValueError("top_k는 1 이상이어야 합니다.")

        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH hotel_chunks AS MATERIALIZED (
                    SELECT content, chunk_index, embedding, metadata
                    FROM documents
                    WHERE metadata->>'accommodation_id' = %s
                      AND collection_name = %s
                      AND embedding_provider = %s
                      AND embedding_model = %s
                      AND embedding_dimension = %s
                )
                SELECT content, chunk_index, metadata,
                       1 - (embedding <=> %s::vector) AS score
                FROM hotel_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    str(accommodation_id),
                    self.collection_name,
                    self.embedding_provider,
                    self.embedding_model,
                    len(query_vector),
                    query_vector,
                    query_vector,
                    top_k,
                ),
            )
            return [self._row_to_hit(row) for row in cursor.fetchall()]

    @staticmethod
    def _row_to_hit(row: tuple[Any, ...]) -> PolicyHit:
        metadata = row[2]
        chunk = PolicyChunk(
            accommodation_id=int(metadata["accommodation_id"]),
            hotel_name=metadata["hotel_name"],
            city=metadata["city"],
            section_title=metadata["section_title"],
            chunk_index=int(row[1]),
            content=row[0],
            sha=metadata["sha"],
        )
        return PolicyHit(chunk=chunk, score=float(row[3]))

    def stats(self) -> dict[str, int]:
        """현재 공급자·모델로 적재된 호텔 수와 청크 수를 반환한다."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT metadata->>'accommodation_id'), COUNT(*)
                FROM documents
                WHERE collection_name = %s
                  AND embedding_provider = %s
                  AND embedding_model = %s
                """,
                (
                    self.collection_name,
                    self.embedding_provider,
                    self.embedding_model,
                ),
            )
            hotels, chunks = cursor.fetchone()
            return {"hotels": int(hotels), "chunks": int(chunks)}

    def iter_chunks(self, with_vectors: bool = False) -> Iterator[dict[str, Any]]:
        """현재 공급자·모델의 청크를 export용 dict로 순서대로 순회한다."""
        vector_column = ", embedding" if with_vectors else ""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT content, chunk_index, metadata{vector_column}
                FROM documents
                WHERE collection_name = %s
                  AND embedding_provider = %s
                  AND embedding_model = %s
                ORDER BY (metadata->>'accommodation_id')::bigint, chunk_index
                """,
                (
                    self.collection_name,
                    self.embedding_provider,
                    self.embedding_model,
                ),
            )
            for row in cursor:
                metadata = row[2]
                item = {
                    "accommodation_id": int(metadata["accommodation_id"]),
                    "hotel_name": metadata["hotel_name"],
                    "city": metadata["city"],
                    "section_title": metadata["section_title"],
                    "chunk_index": int(row[1]),
                    "content": row[0],
                    "sha": metadata["sha"],
                }
                if with_vectors:
                    vector = row[3]
                    if hasattr(vector, "to_list"):
                        vector = vector.to_list()
                    elif hasattr(vector, "tolist"):
                        vector = vector.tolist()
                    item["embedding"] = [
                        float(value) for value in vector
                    ]
                yield item
