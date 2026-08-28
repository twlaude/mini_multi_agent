"""프로세스당 하나만 만들어 공유하는 의존성 (FastAPI 의 Depends 역할)."""

from functools import lru_cache

from app.clients import AccommodationClient
from app.clients.yeogi import YeogiClient
from app.core.config import HotelSettings, get_settings


@lru_cache(maxsize=1)
def get_client() -> AccommodationClient:
    """숙소 데이터 소스. 사이트를 바꾸려면 여기서 다른 AccommodationClient 구현체를 돌려주면 된다."""
    return YeogiClient(get_settings())  # buildId 캐시를 프로세스 안에서 공유


def get_app_settings() -> HotelSettings:
    return get_settings()
