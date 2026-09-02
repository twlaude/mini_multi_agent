import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))
TOOLS_MCP_URL = os.getenv("TOOLS_MCP_URL", "http://127.0.0.1:8010/mcp")
MARKET_MCP_URL = os.getenv("MARKET_MCP_URL", "http://127.0.0.1:8011/mcp")

# Agent Profile의 mcp_server 이름 → 실제 MCP Server 주소
MCP_SERVERS: dict[str, str] = {
    "business-tools": TOOLS_MCP_URL,
    "market-data": MARKET_MCP_URL,
}


def require_openai_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("프로젝트 루트의 .env에 OPENAI_API_KEY를 설정하세요.")
