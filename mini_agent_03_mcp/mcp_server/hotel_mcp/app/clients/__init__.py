"""외부 데이터 소스 클라이언트. 소스를 바꾸려면 base.AccommodationClient 를 구현한 패키지를 추가하고 core/deps.get_client 만 바꾼다."""

from .base import AccommodationClient, SearchPage

__all__ = ["AccommodationClient", "SearchPage"]
