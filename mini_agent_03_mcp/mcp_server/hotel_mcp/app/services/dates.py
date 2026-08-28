"""날짜 검증·기본값 도우미 (여러 service 가 공유)."""

from datetime import date, timedelta


def check_date(name: str, value: str) -> str:
    """YYYY-MM-DD 형식인지 검사하고 그대로 돌려준다."""
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name}는 YYYY-MM-DD 형식이어야 합니다: {value!r}")
    return value


def default_dates(check_in: str, check_out: str) -> tuple[str, str]:
    """날짜를 안 주면 오늘~내일(1박)로 채운다. check_in 만 주면 그 다음 날을 check_out 으로."""
    if not check_in:
        check_in = date.today().isoformat()
    check_date("check_in", check_in)
    if not check_out:
        check_out = (date.fromisoformat(check_in) + timedelta(days=1)).isoformat()
    check_date("check_out", check_out)
    if check_out <= check_in:
        raise ValueError("check_out은 check_in보다 뒤여야 합니다.")
    return check_in, check_out


def today_text() -> str:
    """서버 기준 오늘/내일 날짜 (yeogi://today Resource)."""
    return (
        f"today: {date.today().isoformat()}\n"
        f"tomorrow: {(date.today() + timedelta(days=1)).isoformat()}"
    )
