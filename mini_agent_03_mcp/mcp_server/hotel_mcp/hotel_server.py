"""8030 포트에서 독립 실행되는 여기어때(yeogi.com) 숙소 검색 Streamable HTTP MCP Server입니다.

travel_server.py 와 같은 방식(FastMCP + streamable-http)이지만 mock 데이터 대신
**진짜 여기어때 검색 결과**를 돌려줍니다. 이 파일은 서버를 만들고 ``app/tools`` 의 Tool/Resource 를
등록하는 진입점일 뿐이고, 로직은 전부 ``app/`` 패키지 안에 있습니다 (README 의 구조 참고).

Tool 3개 (모두 인증 불필요)
    1. search_accommodations   지역 키워드+날짜(+최대 가격) → 숙소 목록
    2. get_room_options        숙소 id+날짜 → 객실별 대실/숙박 옵션·재고
    3. make_checkout_link      숙소 id+객실 id → 결제 직전 페이지 URL (결제는 하지 않음)

실행
    python hotel_server.py
    → http://<이 컴퓨터 IP>:8030/mcp   (다른 컴퓨터의 Backend 가 이 주소로 접속)

환경변수
    HOTEL_MCP_HOST  기본 0.0.0.0 (같은 네트워크의 다른 컴퓨터가 접속할 수 있게 모든 인터페이스에 바인딩)
    HOTEL_MCP_PORT  기본 8030

주의
    여기어때 공식 API 가 아니라 웹 페이지가 쓰는 Next.js data endpoint 를 그대로 읽습니다.
    스펙이 예고 없이 바뀔 수 있고, 과도한 호출은 차단될 수 있습니다 (교육용).
"""

import sys
from pathlib import Path

# 어느 디렉터리에서 실행해도 같은 폴더의 app 패키지를 찾게 합니다.
SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.tools import checkout, resources, rooms, search


settings = get_settings()

mcp = FastMCP(
    "hotel-search",
    instructions=(
        "여기어때(yeogi.com) 국내 숙소를 실시간으로 검색하고 객실 재고를 확인한 뒤 "
        "결제 직전 링크를 만드는 교육용 MCP Server. 검색 → 객실 옵션 → 결제 링크 순서로 "
        "호출한다. 로그인이 필요 없고, 결제는 절대 자동으로 하지 않는다."
    ),
    host=settings.mcp_host,
    port=settings.mcp_port,
    stateless_http=True,
    json_response=True,
)

# FastAPI 의 app.include_router(...) 처럼 Tool/Resource 를 진입점에서 직접 등록한다
search.register(mcp)      # search_accommodations
rooms.register(mcp)       # get_room_options
checkout.register(mcp)    # make_checkout_link
resources.register(mcp)   # yeogi://sort-types, yeogi://today


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
