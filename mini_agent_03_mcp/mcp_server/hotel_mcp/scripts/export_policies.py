"""호텔 규정 청크와 OpenAI embedding을 팀원용 번들로 내보낸다."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Mapping
from itertools import zip_longest
from pathlib import Path
from typing import Any

# 어느 디렉터리에서 실행해도 hotel_mcp/app 패키지를 찾게 합니다 (seed_policies.py 와 동일).
HOTEL_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(HOTEL_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(HOTEL_MCP_ROOT))

from app.core.deps import get_store


EXPECTED_PROVIDER = "openai"
EXPECTED_MODEL = "text-embedding-3-small"
EXPECTED_DIMENSION = 1536
TEXT_FIELDS = (
    "accommodation_id",
    "hotel_name",
    "city",
    "section_title",
    "chunk_index",
    "content",
    "sha",
)
DEFAULT_OUTPUT_DIR = Path.home() / "Downloads" / "hotel_policy_bundle_0828"


def normalize_export_row(item: Any, *, with_vector: bool) -> dict[str, Any]:
    """dict 또는 ``(PolicyChunk, vector)``를 고정 JSONL 형식으로 바꾼다."""
    vector = None
    chunk = item
    if isinstance(item, tuple) and len(item) == 2:
        chunk, vector = item

    if isinstance(chunk, Mapping):
        values = chunk
    elif hasattr(chunk, "model_dump"):
        values = chunk.model_dump()
    else:
        values = {field: getattr(chunk, field) for field in TEXT_FIELDS}

    try:
        row = {
            "accommodation_id": int(values["accommodation_id"]),
            "hotel_name": str(values["hotel_name"]),
            "city": str(values["city"]),
            "section_title": str(values["section_title"]),
            "chunk_index": int(values["chunk_index"]),
            "content": str(values["content"]),
            "sha": str(values["sha"]),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"export 청크 필드가 올바르지 않습니다: {error}") from error

    if with_vector:
        if vector is None and isinstance(values, Mapping):
            vector = values.get("embedding")
        if hasattr(vector, "tolist"):
            vector = vector.tolist()
        if vector is None:
            raise ValueError("벡터 export row에 embedding이 없습니다.")
        embedding = [float(value) for value in vector]
        if len(embedding) != EXPECTED_DIMENSION:
            raise ValueError(
                f"embedding 차원이 {len(embedding)}입니다; "
                f"{EXPECTED_DIMENSION}차원이어야 합니다."
            )
        if not all(math.isfinite(value) for value in embedding):
            raise ValueError("embedding에 NaN 또는 무한대가 있습니다.")
        row["embedding"] = embedding
    return row


def _validate_model_rows(store: Any) -> None:
    configured = (store.embedding_provider, store.embedding_model)
    if configured != (EXPECTED_PROVIDER, EXPECTED_MODEL):
        raise RuntimeError(
            "export는 openai/text-embedding-3-small 저장소만 지원합니다; "
            f"현재 설정은 {configured[0]}/{configured[1]}입니다."
        )

    with store._connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT embedding_provider, embedding_model
            FROM documents
            WHERE collection_name = %s
              AND (embedding_provider <> %s OR embedding_model <> %s)
            ORDER BY 1, 2
            """,
            (store.collection_name, EXPECTED_PROVIDER, EXPECTED_MODEL),
        )
        mismatches = cursor.fetchall()
    if mismatches:
        pairs = ", ".join(f"{provider}/{model}" for provider, model in mismatches)
        raise RuntimeError(
            "hotel_policy에 export 대상이 아닌 provider/model row가 있습니다: " + pairs
        )


def export_bundle(output_dir: Path) -> int:
    """일관성이 검증된 두 JSONL, loader, README와 zip을 생성한다."""
    store = get_store()
    _validate_model_rows(store)

    output_dir = output_dir.expanduser().resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    source_dir = Path(__file__).resolve().parent
    assets = {
        "load_hotel_policies.py": source_dir / "load_hotel_policies.py",
        "README.md": source_dir / "BUNDLE_README.md",
    }
    missing = [str(path) for path in assets.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("bundle source asset이 없습니다: " + ", ".join(missing))

    sentinel = object()
    with tempfile.TemporaryDirectory(
        prefix=f".{output_dir.name}-", dir=output_dir.parent
    ) as temporary:
        build_dir = Path(temporary)
        text_path = build_dir / "hotel_policy_chunks.jsonl"
        vector_path = (
            build_dir
            / "hotel_policy_embeddings_openai_text-embedding-3-small.jsonl"
        )
        count = 0
        text_rows = store.iter_chunks(with_vectors=False)
        vector_rows = store.iter_chunks(with_vectors=True)
        with text_path.open("w", encoding="utf-8", newline="\n") as text_file, \
             vector_path.open("w", encoding="utf-8", newline="\n") as vector_file:
            for number, pair in enumerate(
                zip_longest(text_rows, vector_rows, fillvalue=sentinel), start=1
            ):
                text_item, vector_item = pair
                if sentinel in pair:
                    raise RuntimeError(
                        "같은 DB snapshot의 텍스트/벡터 row 수가 일치하지 않습니다."
                    )
                text_row = normalize_export_row(text_item, with_vector=False)
                vector_row = normalize_export_row(vector_item, with_vector=True)
                if text_row != {field: vector_row[field] for field in TEXT_FIELDS}:
                    raise RuntimeError(f"텍스트/벡터 snapshot row {number}가 다릅니다.")
                text_file.write(json.dumps(text_row, ensure_ascii=False) + "\n")
                vector_file.write(json.dumps(vector_row, ensure_ascii=False) + "\n")
                count += 1
        if count == 0:
            raise RuntimeError("export할 hotel_policy 청크가 없습니다.")

        for destination, source in assets.items():
            shutil.copy2(source, build_dir / destination)

        output_dir.mkdir(parents=True, exist_ok=True)
        filenames = [text_path.name, vector_path.name, *assets]
        for filename in filenames:
            shutil.copy2(build_dir / filename, output_dir / filename)

        zip_path = output_dir.parent / f"{output_dir.name}.zip"
        temporary_zip = build_dir / f"{output_dir.name}.zip"
        with zipfile.ZipFile(temporary_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename in filenames:
                archive.write(
                    build_dir / filename,
                    arcname=f"{output_dir.name}/{filename}",
                )
        shutil.copy2(temporary_zip, zip_path)

    print(f"[EXPORT] chunks={count} output={output_dir} zip={zip_path}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"번들 출력 폴더 (기본: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    export_bundle(args.output_dir)


if __name__ == "__main__":
    main()
