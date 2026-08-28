"""프로세스당 하나만 만들어 공유하는 의존성 (FastAPI 의 Depends 역할)."""

from functools import lru_cache

from app.clients import AccommodationClient
from app.clients.embedding import Embedder
from app.clients.vectorstore import PolicyStore
from app.clients.yeogi import YeogiClient
from app.core.config import HotelSettings, get_settings


@lru_cache(maxsize=1)
def get_client() -> AccommodationClient:
    """숙소 데이터 소스. 사이트를 바꾸려면 여기서 다른 AccommodationClient 구현체를 돌려주면 된다."""
    return YeogiClient(get_settings())  # buildId 캐시를 프로세스 안에서 공유


def get_app_settings() -> HotelSettings:
    return get_settings()


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """설정된 공급자의 임베딩 클라이언트를 프로세스에서 공유한다."""
    settings = get_settings()
    return Embedder(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        ollama_base_url=settings.ollama_base_url,
    )


@lru_cache(maxsize=1)
def get_store() -> PolicyStore:
    """호텔 규정 pgvector 저장소를 프로세스에서 공유한다."""
    settings = get_settings()
    return PolicyStore(
        database_url=settings.database_url,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
    )
