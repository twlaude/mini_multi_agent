#!/usr/bin/env python3
"""hotel_policy JSONL 번들을 PostgreSQL documents 테이블에 적재한다.

hotel_mcp 패키지에 의존하지 않는 팀원 배포용 단일 파일이다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import NAMESPACE_URL, uuid5


DEFAULT_DATABASE_URL = (
    "postgresql://agent_user:agent_password@127.0.0.1:5433/agent_db"
)
DEFAULT_COLLECTION = "hotel_policy"
BATCH_SIZE = 64
REQUIRED_FIELDS = (
    "accommodation_id",
    "hotel_name",
    "city",
    "section_title",
    "chunk_index",
    "content",
    "sha",
)

SCHEMA_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY,
        collection_name TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        embedding_provider TEXT NOT NULL,
        embedding_model TEXT NOT NULL,
        embedding_dimension INTEGER NOT NULL,
        embedding VECTOR NOT NULL,
        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS documents_collection_idx
        ON documents (collection_name, embedding_provider, embedding_model)
    """,
)

UPSERT_SQL = """
    INSERT INTO documents
        (id, collection_name, title, content, source, chunk_index,
         embedding_provider, embedding_model, embedding_dimension,
         embedding, metadata)
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
        metadata = EXCLUDED.metadata,
        created_at = NOW()
"""


class LoaderError(RuntimeError):
    """사용자가 바로 조치할 수 있는 적재 오류."""


def _records(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise LoaderError(f"입력 파일을 열 수 없습니다: {path} ({exc})") from exc

    with handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LoaderError(
                    f"{path} {line_number}행의 JSON이 올바르지 않습니다: {exc.msg}"
                ) from exc
            if not isinstance(value, dict):
                raise LoaderError(f"{path} {line_number}행은 JSON 객체여야 합니다.")
            yield line_number, value


def _validate_vector(value: Any, line_number: int) -> list[float]:
    if not isinstance(value, list) or not value:
        raise LoaderError(
            "--embed none은 모든 행에 embedding 배열이 필요합니다. "
            f"{line_number}행에 벡터가 없습니다. 벡터 포함본을 사용하거나 "
            "텍스트본에 --embed openai 또는 --embed ollama를 지정하세요."
        )
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise LoaderError(f"{line_number}행 embedding에 숫자가 아닌 값이 있습니다.")
        number = float(item)
        if not math.isfinite(number):
            raise LoaderError(f"{line_number}행 embedding에 유한하지 않은 값이 있습니다.")
        vector.append(number)
    return vector


def _validate_record(record: dict[str, Any], line_number: int) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in record]
    if missing:
        raise LoaderError(
            f"{line_number}행에 필수 필드가 없습니다: {', '.join(missing)}"
        )
    try:
        accommodation_id = int(record["accommodation_id"])
        chunk_index = int(record["chunk_index"])
    except (TypeError, ValueError) as exc:
        raise LoaderError(
            f"{line_number}행 accommodation_id/chunk_index는 정수여야 합니다."
        ) from exc
    if accommodation_id <= 0 or chunk_index < 0:
        raise LoaderError(
            f"{line_number}행 accommodation_id는 양수, chunk_index는 0 이상이어야 합니다."
        )
    for field in ("hotel_name", "city", "section_title", "content", "sha"):
        if not isinstance(record[field], str) or not record[field].strip():
            raise LoaderError(f"{line_number}행 {field}는 비어 있지 않은 문자열이어야 합니다.")
    actual_sha = hashlib.sha256(record["content"].encode("utf-8")).hexdigest()
    if record["sha"] != actual_sha:
        raise LoaderError(f"{line_number}행 sha가 content의 SHA-256과 일치하지 않습니다.")


def _inspect_input(path: Path, embed_mode: str) -> tuple[int, int | None]:
    count = 0
    dimension: int | None = None
    seen: set[tuple[int, int]] = set()
    for line_number, record in _records(path):
        _validate_record(record, line_number)
        key = (int(record["accommodation_id"]), int(record["chunk_index"]))
        if key in seen:
            raise LoaderError(
                f"{line_number}행의 호텔/청크 키가 중복입니다: {key[0]}:{key[1]}"
            )
        seen.add(key)
        if embed_mode == "none":
            vector = _validate_vector(record.get("embedding"), line_number)
            if dimension is None:
                dimension = len(vector)
            elif dimension != len(vector):
                raise LoaderError(
                    f"{line_number}행 embedding 차원이 {len(vector)}입니다. "
                    f"앞선 차원 {dimension}과 같아야 합니다."
                )
        count += 1
    if count == 0:
        raise LoaderError(f"입력 파일에 적재할 JSON 행이 없습니다: {path}")
    return count, dimension


def _openai_embedder() -> tuple[str, Callable[[list[str]], list[list[float]]]]:
    if not os.getenv("OPENAI_API_KEY"):
        raise LoaderError("--embed openai 사용 전 OPENAI_API_KEY 환경 변수를 설정하세요.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LoaderError(
            "OpenAI 재임베딩에는 openai 패키지가 필요합니다: py -m pip install openai"
        ) from exc

    model = os.getenv("HOTEL_EMBEDDING_MODEL", "text-embedding-3-small")
    client = OpenAI()

    def embed(texts: list[str]) -> list[list[float]]:
        try:
            response = client.embeddings.create(model=model, input=texts)
        except Exception as exc:
            raise LoaderError(f"OpenAI 임베딩 요청에 실패했습니다: {exc}") from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        return [[float(value) for value in item.embedding] for item in ordered]

    return model, embed


def _ollama_embedder() -> tuple[str, Callable[[list[str]], list[list[float]]]]:
    try:
        import httpx
    except ImportError as exc:
        raise LoaderError(
            "Ollama 재임베딩에는 httpx 패키지가 필요합니다: py -m pip install httpx"
        ) from exc

    model = os.getenv("HOTEL_EMBEDDING_MODEL", "embeddinggemma")
    base_url = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    if "://" not in base_url:
        base_url = f"http://{base_url}"
    endpoint = f"{base_url.rstrip('/')}/api/embed"

    def embed(texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                endpoint,
                json={"model": model, "input": texts},
                timeout=120.0,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise LoaderError(f"Ollama 임베딩 요청에 실패했습니다: {exc}") from exc
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise LoaderError("Ollama /api/embed 응답에 embeddings 배열이 없습니다.")
        return embeddings

    return model, embed


def _document_id(collection: str, accommodation_id: int, chunk_index: int):
    if collection == DEFAULT_COLLECTION:
        key = f"hotel_policy:{accommodation_id}:{chunk_index}"
    else:
        # 같은 DB에서 loadtest 컬렉션을 검증해도 운영 UUID와 충돌하지 않게 한다.
        key = f"{collection}:{accommodation_id}:{chunk_index}"
    return uuid5(NAMESPACE_URL, key)


def _chunks(path: Path) -> Iterator[list[tuple[int, dict[str, Any]]]]:
    batch: list[tuple[int, dict[str, Any]]] = []
    for item in _records(path):
        batch.append(item)
        if len(batch) == BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


def load(args: argparse.Namespace) -> None:
    input_path = args.input.expanduser().resolve()
    total, input_dimension = _inspect_input(input_path, args.embed)

    embedder: Callable[[list[str]], list[list[float]]] | None = None
    if args.embed == "openai":
        model, embedder = _openai_embedder()
        provider = "openai"
    elif args.embed == "ollama":
        model, embedder = _ollama_embedder()
        provider = "ollama"
    else:
        provider = "openai"
        model = "text-embedding-3-small"

    try:
        import psycopg
        from pgvector.psycopg import register_vector
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise LoaderError(
            "DB 적재 의존성을 설치하세요: py -m pip install \"psycopg[binary]\" pgvector"
        ) from exc

    print(
        f"[load] 입력 {total}개 검증 완료 · provider={provider} · model={model}"
    )
    try:
        connection = psycopg.connect(args.database_url)
    except Exception as exc:
        raise LoaderError(f"PostgreSQL 연결에 실패했습니다: {exc}") from exc

    loaded = 0
    dimension = input_dimension
    try:
        with connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            connection.commit()
            register_vector(connection)

            with connection.cursor() as cursor:
                if args.replace:
                    cursor.execute(
                        "DELETE FROM documents WHERE collection_name = %s",
                        (args.collection,),
                    )

                for batch in _chunks(input_path):
                    records = [record for _, record in batch]
                    if embedder is None:
                        vectors = [
                            _validate_vector(record["embedding"], line_number)
                            for line_number, record in batch
                        ]
                    else:
                        vectors = embedder([record["content"] for record in records])
                        if len(vectors) != len(records):
                            raise LoaderError(
                                "임베딩 응답 개수가 요청 텍스트 개수와 일치하지 않습니다."
                            )
                        vectors = [
                            _validate_vector(vector, line_number)
                            for (line_number, _), vector in zip(batch, vectors)
                        ]

                    for line_number, vector in zip((item[0] for item in batch), vectors):
                        if dimension is None:
                            dimension = len(vector)
                        elif dimension != len(vector):
                            raise LoaderError(
                                f"{line_number}행 벡터 차원 {len(vector)}이 "
                                f"앞선 차원 {dimension}과 다릅니다."
                            )

                    rows = []
                    for record, vector in zip(records, vectors):
                        accommodation_id = int(record["accommodation_id"])
                        chunk_index = int(record["chunk_index"])
                        metadata = {
                            "accommodation_id": accommodation_id,
                            "hotel_name": record["hotel_name"],
                            "city": record["city"],
                            "section_title": record["section_title"],
                            "sha": record["sha"],
                        }
                        rows.append(
                            (
                                _document_id(args.collection, accommodation_id, chunk_index),
                                args.collection,
                                f"{record['hotel_name']} · {record['section_title']}",
                                record["content"],
                                f"yeogi:{accommodation_id}",
                                chunk_index,
                                provider,
                                model,
                                len(vector),
                                vector,
                                Jsonb(metadata),
                            )
                        )
                    cursor.executemany(UPSERT_SQL, rows)
                    loaded += len(rows)
                    print(f"[load] {loaded}/{total}개 적재")

                cursor.execute(
                    "SELECT count(*) FROM documents WHERE collection_name = %s",
                    (args.collection,),
                )
                collection_count = int(cursor.fetchone()[0])
    except LoaderError:
        raise
    except Exception as exc:
        raise LoaderError(f"documents 적재에 실패했습니다: {exc}") from exc
    finally:
        connection.close()

    print(
        f"[done] 이번 실행 {loaded}개 · collection={args.collection} "
        f"전체 {collection_count}개 · dimension={dimension}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="호텔 규정 JSONL을 pgvector documents 테이블에 적재합니다.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", required=True, type=Path, help="적재할 JSONL 파일")
    parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help="PostgreSQL 접속 URL",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help="documents.collection_name 값",
    )
    parser.add_argument(
        "--embed",
        choices=("none", "openai", "ollama"),
        default="none",
        help="none은 파일 벡터 사용, 나머지는 content 재임베딩",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="적재 전 지정 collection만 삭제",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.collection.strip():
        parser.error("--collection은 비어 있을 수 없습니다.")
    try:
        load(args)
    except LoaderError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
