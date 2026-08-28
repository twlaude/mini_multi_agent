"""OpenAI 또는 Ollama로 호텔 규정 텍스트를 임베딩합니다."""

from __future__ import annotations

from typing import Any

import httpx


BATCH_SIZE = 64
DEFAULT_MODELS = {
    "openai": "text-embedding-3-small",
    "ollama": "embeddinggemma",
}


class Embedder:
    """공급자 차이를 숨기고 입력 순서대로 임베딩 벡터를 반환한다."""

    def __init__(
        self,
        provider: str = "openai",
        model: str | None = None,
        ollama_base_url: str = "http://127.0.0.1:11434",
    ) -> None:
        provider = provider.strip().lower()
        if provider not in DEFAULT_MODELS:
            raise ValueError("embedding provider는 openai 또는 ollama여야 합니다.")
        self.provider = provider
        self.model = model or DEFAULT_MODELS[provider]
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self._openai_client: Any | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트를 최대 64개씩 보내며 빈 입력에는 외부 호출을 하지 않는다."""
        if not texts:
            return []

        cleaned = [text.replace("\x00", "") for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(cleaned), BATCH_SIZE):
            batch = cleaned[start:start + BATCH_SIZE]
            if self.provider == "openai":
                batch_vectors = self._embed_openai(batch)
            else:
                batch_vectors = self._embed_ollama(batch)
            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    f"임베딩 응답 수가 입력 수와 다릅니다: {len(batch_vectors)} != {len(batch)}"
                )
            vectors.extend(batch_vectors)
        return vectors

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        if self._openai_client is None:
            from openai import OpenAI

            self._openai_client = OpenAI()
        response = self._openai_client.embeddings.create(model=self.model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [[float(value) for value in item.embedding] for item in ordered]

    def _embed_ollama(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.ollama_base_url}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=300,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings")
        if not isinstance(embeddings, list):
            raise RuntimeError("Ollama 응답에 embeddings 배열이 없습니다.")
        return [[float(value) for value in vector] for vector in embeddings]
