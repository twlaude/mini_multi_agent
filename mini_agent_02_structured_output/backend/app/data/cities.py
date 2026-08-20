"""국내 여행지 선택 상자에 보여줄 대표 도시와 중심 좌표."""

from app.schemas import CityItem


KOREA_CITIES: list[CityItem] = [
    CityItem(name="서울", lat=37.5663, lng=126.9779),
    CityItem(name="부산", lat=35.1797, lng=129.0750),
    CityItem(name="인천", lat=37.4563, lng=126.7052),
    CityItem(name="대구", lat=35.8714, lng=128.6014),
    CityItem(name="대전", lat=36.3504, lng=127.3845),
    CityItem(name="광주", lat=35.1601, lng=126.8514),
    CityItem(name="울산", lat=35.5395, lng=129.3115),
    CityItem(name="세종", lat=36.4800, lng=127.2890),
    CityItem(name="수원", lat=37.2636, lng=127.0286),
    CityItem(name="고양", lat=37.6584, lng=126.8320),
    CityItem(name="용인", lat=37.2411, lng=127.1776),
    CityItem(name="창원", lat=35.2279, lng=128.6819),
    CityItem(name="청주", lat=36.6424, lng=127.4890),
    CityItem(name="천안", lat=36.8151, lng=127.1139),
    CityItem(name="전주", lat=35.8242, lng=127.1480),
    CityItem(name="포항", lat=36.0190, lng=129.3435),
    CityItem(name="경주", lat=35.8562, lng=129.2247),
    CityItem(name="강릉", lat=37.7519, lng=128.8761),
    CityItem(name="속초", lat=38.2070, lng=128.5918),
    CityItem(name="여수", lat=34.7604, lng=127.6622),
    CityItem(name="순천", lat=34.9506, lng=127.4872),
    CityItem(name="목포", lat=34.8118, lng=126.3922),
    CityItem(name="춘천", lat=37.8813, lng=127.7300),
    CityItem(name="제주", lat=33.4996, lng=126.5312),
    CityItem(name="서귀포", lat=33.2541, lng=126.5601),
]
