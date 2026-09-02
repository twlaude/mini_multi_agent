"""Market Data MCP Tool의 입력 검증 계약을 확인하는 회귀 테스트입니다."""

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp_server.market_data_server import calculate_pnl, get_quote, search_stock  # noqa: E402


def test_blank_stock_query_is_rejected() -> None:
    result = search_stock("   ")

    assert result["success"] is False
    assert result["error"] == "INVALID_QUERY"
    assert result["items"] == []


def test_unknown_code_is_not_found() -> None:
    result = get_quote("999999")

    assert result["success"] is False
    assert result["error"] == "STOCK_NOT_FOUND"


def test_pnl_uses_current_price() -> None:
    result = calculate_pnl("005930", quantity=10, avg_price=68_000)

    assert result["success"] is True
    assert result["pnl"] == (result["current_price"] - 68_000) * 10


def test_invalid_quantity_raises() -> None:
    with pytest.raises(ValueError):
        calculate_pnl("005930", quantity=0, avg_price=68_000)
