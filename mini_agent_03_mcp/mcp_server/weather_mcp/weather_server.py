from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP


# 어디서 실행하든 이 파일 옆(weather_mcp/.env) → 상위 폴더(.env) 순서로 읽음
_HERE = Path(__file__).resolve().parent
ENV_CANDIDATES = [_HERE / ".env", _HERE.parent / ".env"]
ENV_FILE = next((p for p in ENV_CANDIDATES if p.exists()), None)
for _env in ENV_CANDIDATES:
    if _env.exists():
        load_dotenv(_env, override=False)

KST = timezone(timedelta(hours=9))

SHORT_BASE_URL = (
    "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
)
MID_BASE_URL = "https://apis.data.go.kr/1360000/MidFcstInfoService"

# 공공데이터포털 "Encoding" 키(%가 들어간 것)를 넣어도 자동으로 원본 키로 변환
SERVICE_KEY = unquote(os.getenv("KMA_SERVICE_KEY", "").strip())

# .env 값은 지역 인자를 생략했을 때의 "기본 지역"으로만 쓰임
DEFAULT_NX = os.getenv("KMA_NX", "")
DEFAULT_NY = os.getenv("KMA_NY", "")
DEFAULT_LAND_REG_ID = os.getenv("KMA_LAND_REG_ID", "")
DEFAULT_TEMP_REG_ID = os.getenv("KMA_TEMP_REG_ID", "")
DEFAULT_LOCATION_NAME = os.getenv("KMA_LOCATION_NAME", "설정 지역")

# 지역명 → (단기예보 격자 nx, ny, 중기육상예보 regId, 중기기온예보 regId)
REGIONS: dict[str, tuple[int, int, str, str]] = {
    "서울": (60, 127, "11B00000", "11B10101"),
    "인천": (55, 124, "11B00000", "11B20201"),
    "수원": (60, 121, "11B00000", "11B20601"),
    "파주": (56, 131, "11B00000", "11B20305"),
    "춘천": (73, 134, "11D10000", "11D10301"),
    "원주": (76, 122, "11D10000", "11D10401"),
    "강릉": (92, 131, "11D20000", "11D20501"),
    "속초": (87, 141, "11D20000", "11D20401"),
    "대전": (67, 100, "11C20000", "11C20401"),
    "세종": (66, 103, "11C20000", "11C20404"),
    "청주": (69, 106, "11C10000", "11C10301"),
    "충주": (76, 114, "11C10000", "11C10101"),
    "광주": (58, 74, "11F20000", "11F20501"),
    "목포": (50, 67, "11F20000", "21F20801"),
    "여수": (73, 66, "11F20000", "11F20401"),
    "전주": (63, 89, "11F10000", "11F10201"),
    "군산": (56, 92, "11F10000", "21F10501"),
    "대구": (89, 90, "11H10000", "11H10701"),
    "포항": (102, 94, "11H10000", "11H10201"),
    "안동": (91, 106, "11H10000", "11H10501"),
    "부산": (98, 76, "11H20000", "11H20201"),
    "울산": (102, 84, "11H20000", "11H20101"),
    "창원": (90, 77, "11H20000", "11H20301"),
    "진주": (81, 75, "11H20000", "11H20701"),
    "제주": (52, 38, "11G00000", "11G00201"),
    "서귀포": (52, 33, "11G00000", "11G00401"),
}

# "서울특별시", "부산광역시", "제주도" 같은 행정 접미사 처리용
_REGION_SUFFIXES = ("특별자치시", "특별자치도", "광역시", "특별시", "시", "도")

# 다른 PC(Backend)가 접속할 수 있게 모든 인터페이스에 바인딩. 환경변수로 바꿀 수 있음
MCP_HOST = os.getenv("WEATHER_MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("WEATHER_MCP_PORT", "8050"))

mcp = FastMCP(
    "KMA Weather",
    instructions=(
        "전국 주요 지역의 현재 날씨와 7일 예보를 제공합니다. "
        "지역명(예: 서울, 부산, 제주)을 인자로 넘기면 해당 지역을 조회하고, "
        "생략하면 서버 기본 지역을 조회합니다. "
        "지원 지역 목록은 list_regions 로 확인할 수 있습니다."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


class WeatherApiError(Exception):
    """사용자에게 보여줄 수 있는 날씨 API 오류입니다."""


def resolve_region(region: str) -> dict[str, Any]:
    """지역명을 기상청 조회 좌표/구역코드로 변환합니다. 빈 값이면 .env 기본 지역."""
    if not SERVICE_KEY:
        raise WeatherApiError(".env에서 KMA_SERVICE_KEY 값을 설정해주세요.")

    name = (region or "").strip()

    if not name:
        if not (DEFAULT_NX and DEFAULT_NY):
            raise WeatherApiError(
                "지역명을 지정하거나 .env에 KMA_NX, KMA_NY 기본값을 설정해주세요."
            )
        return {
            "name": DEFAULT_LOCATION_NAME,
            "nx": DEFAULT_NX,
            "ny": DEFAULT_NY,
            "land_reg_id": DEFAULT_LAND_REG_ID,
            "temp_reg_id": DEFAULT_TEMP_REG_ID,
        }

    matched = name if name in REGIONS else None

    if matched is None:
        for suffix in _REGION_SUFFIXES:
            if name.endswith(suffix) and name[: -len(suffix)] in REGIONS:
                matched = name[: -len(suffix)]
                break

    if matched is None:
        candidates = [known for known in REGIONS if known in name]
        if len(candidates) == 1:
            matched = candidates[0]

    if matched is None:
        raise WeatherApiError(
            f"'{name}' 지역은 지원하지 않습니다. "
            f"지원 지역: {', '.join(REGIONS)}"
        )

    nx, ny, land_reg_id, temp_reg_id = REGIONS[matched]
    return {
        "name": matched,
        "nx": nx,
        "ny": ny,
        "land_reg_id": land_reg_id,
        "temp_reg_id": temp_reg_id,
    }


def request_items(url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """기상청 API를 호출하고 item 목록만 반환합니다."""
    request_params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 2000,
        "dataType": "JSON",
        **params,
    }

    try:
        response = httpx.get(url, params=request_params, timeout=15.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        raise WeatherApiError(
            f"기상청 API 요청에 실패했습니다. (HTTP {exc.response.status_code} — "
            "401/403이면 인증키 또는 활용신청 미승인, 500이면 파라미터 확인)"
        ) from exc
    except httpx.HTTPError as exc:
        raise WeatherApiError(
            f"기상청 API 연결에 실패했습니다. ({type(exc).__name__}: 인터넷/방화벽 확인)"
        ) from exc
    except ValueError as exc:
        raise WeatherApiError(
            "기상청이 JSON이 아닌 응답을 반환했습니다. API 키를 확인해주세요."
        ) from exc

    api_response = data.get("response", {})
    header = api_response.get("header", {})
    result_code = str(header.get("resultCode", ""))

    if result_code not in {"00", "0"}:
        message = header.get("resultMsg", "알 수 없는 오류")
        raise WeatherApiError(f"기상청 API 오류: {message} ({result_code})")

    items = api_response.get("body", {}).get("items", {})
    if not isinstance(items, dict):
        return []

    item = items.get("item", [])
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return item
    return []


def latest_base_time(
    now: datetime,
    base_times: list[str],
    delay_minutes: int = 20,
) -> tuple[str, str]:
    """아직 공개되지 않은 발표시각을 피해서 가장 최근 시각을 고릅니다."""
    effective = now - timedelta(minutes=delay_minutes)

    for day_offset in (0, -1):
        target_date = effective.date() + timedelta(days=day_offset)
        candidates: list[tuple[datetime, str]] = []

        for base_time in base_times:
            hour = int(base_time[:2])
            minute = int(base_time[2:])
            candidate = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                hour,
                minute,
                tzinfo=KST,
            )
            if candidate <= effective:
                candidates.append((candidate, base_time))

        if candidates:
            candidate, base_time = max(candidates, key=lambda value: value[0])
            return candidate.strftime("%Y%m%d"), base_time

    raise WeatherApiError("사용 가능한 기상청 발표시각을 찾지 못했습니다.")


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value.is_integer() else round(value, 1)


def sky_text(code: str | None) -> str | None:
    return {
        "1": "맑음",
        "3": "구름많음",
        "4": "흐림",
    }.get(str(code)) if code is not None else None


def rain_text(code: str | None) -> str:
    return {
        "0": "없음",
        "1": "비",
        "2": "비 또는 눈",
        "3": "눈",
        "5": "빗방울",
        "6": "빗방울 또는 눈날림",
        "7": "눈날림",
    }.get(str(code), "확인 불가")


def get_current_weather_data(location: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(KST)
    hourly_times = [f"{hour:02d}00" for hour in range(24)]
    base_date, base_time = latest_base_time(now, hourly_times)

    items = request_items(
        f"{SHORT_BASE_URL}/getUltraSrtNcst",
        {
            "base_date": base_date,
            "base_time": base_time,
            "nx": location["nx"],
            "ny": location["ny"],
        },
    )

    values = {
        str(item.get("category")): str(item.get("obsrValue"))
        for item in items
    }

    temperature = to_float(values.get("T1H"))
    humidity = to_float(values.get("REH"))

    return {
        "ok": True,
        "지역": location["name"],
        "기준시각": f"{base_date} {base_time}",
        "현재기온_c": clean_number(temperature),
        "습도_percent": clean_number(humidity),
        "강수상태": rain_text(values.get("PTY")),
    }


def get_short_forecast(
    now: datetime,
    location: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    short_times = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
    base_date, base_time = latest_base_time(now, short_times)

    items = request_items(
        f"{SHORT_BASE_URL}/getVilageFcst",
        {
            "base_date": base_date,
            "base_time": base_time,
            "nx": location["nx"],
            "ny": location["ny"],
        },
    )

    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "temperatures": [],
            "rain_probabilities": [],
            "sky_values": [],
            "min_temperature": None,
            "max_temperature": None,
        }
    )

    for item in items:
        forecast_date = str(item.get("fcstDate", ""))
        forecast_time = str(item.get("fcstTime", "0000"))
        category = str(item.get("category", ""))
        value = item.get("fcstValue")

        if not forecast_date:
            continue

        day = grouped[forecast_date]

        if category == "TMP":
            number = to_float(value)
            if number is not None:
                day["temperatures"].append(number)
        elif category == "TMN":
            day["min_temperature"] = to_float(value)
        elif category == "TMX":
            day["max_temperature"] = to_float(value)
        elif category == "POP":
            number = to_float(value)
            if number is not None:
                day["rain_probabilities"].append(number)
        elif category == "SKY":
            day["sky_values"].append((forecast_time, str(value)))

    result: dict[str, dict[str, Any]] = {}

    for forecast_date, day in grouped.items():
        temperatures = day["temperatures"]
        min_temperature = day["min_temperature"]
        max_temperature = day["max_temperature"]

        if min_temperature is None and temperatures:
            min_temperature = min(temperatures)
        if max_temperature is None and temperatures:
            max_temperature = max(temperatures)

        skies = day["sky_values"]
        midday_sky = None
        if skies:
            midday_sky = min(
                skies,
                key=lambda value: abs(int(value[0]) - 1200),
            )[1]

        rain_probabilities = day["rain_probabilities"]
        result[forecast_date] = {
            "최저기온_c": clean_number(min_temperature),
            "최고기온_c": clean_number(max_temperature),
            "하늘상태": sky_text(midday_sky),
            "강수확률_percent": (
                clean_number(max(rain_probabilities))
                if rain_probabilities
                else None
            ),
        }

    return result


def get_mid_forecast(
    now: datetime,
    location: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    land_reg_id = location["land_reg_id"]
    temp_reg_id = location["temp_reg_id"]
    if not (land_reg_id and temp_reg_id):
        raise WeatherApiError(
            f"'{location['name']}' 지역의 중기예보 구역코드가 없습니다. "
            ".env의 KMA_LAND_REG_ID, KMA_TEMP_REG_ID를 확인해주세요."
        )

    tmfc_date, tmfc_time = latest_base_time(now, ["0600", "1800"])
    tmfc = f"{tmfc_date}{tmfc_time}"

    land_items = request_items(
        f"{MID_BASE_URL}/getMidLandFcst",
        {"regId": land_reg_id, "tmFc": tmfc, "numOfRows": 10},
    )
    temperature_items = request_items(
        f"{MID_BASE_URL}/getMidTa",
        {"regId": temp_reg_id, "tmFc": tmfc, "numOfRows": 10},
    )

    if not land_items or not temperature_items:
        raise WeatherApiError("중기예보 데이터가 없습니다.")

    land = land_items[0]
    temperature = temperature_items[0]
    issue_date = datetime.strptime(tmfc_date, "%Y%m%d").date()
    result: dict[str, dict[str, Any]] = {}

    for day_number in range(3, 8):
        forecast_date = (issue_date + timedelta(days=day_number)).strftime("%Y%m%d")
        morning_weather = land.get(f"wf{day_number}Am")
        afternoon_weather = land.get(f"wf{day_number}Pm")
        weather_values = [
            str(value)
            for value in (morning_weather, afternoon_weather)
            if value
        ]
        weather = " / ".join(dict.fromkeys(weather_values)) or None

        rain_values = [
            to_float(land.get(f"rnSt{day_number}Am")),
            to_float(land.get(f"rnSt{day_number}Pm")),
        ]
        valid_rain_values = [value for value in rain_values if value is not None]

        result[forecast_date] = {
            "최저기온_c": clean_number(
                to_float(temperature.get(f"taMin{day_number}"))
            ),
            "최고기온_c": clean_number(
                to_float(temperature.get(f"taMax{day_number}"))
            ),
            "하늘상태": weather,
            "강수확률_percent": (
                clean_number(max(valid_rain_values))
                if valid_rain_values
                else None
            ),
        }

    return result


def merge_day(
    short_day: dict[str, Any] | None,
    mid_day: dict[str, Any] | None,
) -> dict[str, Any]:
    short_day = short_day or {}
    mid_day = mid_day or {}
    fields = ("최저기온_c", "최고기온_c", "하늘상태", "강수확률_percent")

    return {
        field: short_day.get(field)
        if short_day.get(field) is not None
        else mid_day.get(field)
        for field in fields
    }


@mcp.tool()
def list_regions() -> dict[str, Any]:
    """날씨 조회를 지원하는 지역명 목록을 반환합니다."""
    return {"ok": True, "지역목록": list(REGIONS)}


@mcp.tool()
def get_current_weather(region: str = "") -> dict[str, Any]:
    """지정한 지역의 현재 날씨를 조회합니다.

    region: 지역명 (예: 서울, 부산, 제주, 강릉). 생략하면 서버 기본 지역.
    """
    try:
        return get_current_weather_data(resolve_region(region))
    except WeatherApiError as exc:
        return {"ok": False, "message": str(exc)}


@mcp.tool()
def get_weekly_forecast(region: str = "") -> dict[str, Any]:
    """지정한 지역의 오늘부터 7일간 예보를 조회합니다.

    region: 지역명 (예: 서울, 부산, 제주, 강릉). 생략하면 서버 기본 지역.
    """
    try:
        location = resolve_region(region)
        now = datetime.now(KST)
        short_forecast = get_short_forecast(now, location)
        mid_forecast = get_mid_forecast(now, location)
        days: list[dict[str, Any]] = []

        for offset in range(7):
            target_date = now.date() + timedelta(days=offset)
            date_key = target_date.strftime("%Y%m%d")
            day = merge_day(
                short_forecast.get(date_key),
                mid_forecast.get(date_key),
            )
            days.append({"날짜": target_date.isoformat(), **day})

        return {"ok": True, "지역": location["name"], "예보": days}
    except WeatherApiError as exc:
        return {"ok": False, "message": str(exc)}


if __name__ == "__main__":
    if not SERVICE_KEY:
        print(f"[경고] .env 에 KMA_SERVICE_KEY 값이 비어 있습니다. "
              f"(읽은 파일: {ENV_FILE or '없음'} / 찾는 위치: {', '.join(map(str, ENV_CANDIDATES))})", flush=True)
    else:
        print(f"[설정 OK] {ENV_FILE} 기본지역={DEFAULT_LOCATION_NAME} "
              f"(지역 인자로 {len(REGIONS)}개 지역 조회 가능)", flush=True)
    print(f"[서버] http://{MCP_HOST}:{MCP_PORT}/mcp  (다른 PC는 http://<이PC IP>:{MCP_PORT}/mcp)", flush=True)
    mcp.run(transport="streamable-http")
