"""호텔 규정 RAG Tool 등록."""

from mcp.server.fastmcp import FastMCP

from app.services import policy_service


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_hotel_policy(
        accommodation_id: int,
        question: str,
        top_k: int = 4,
    ) -> dict:
        """search_accommodations 결과의 id 를 넣어라.

        체크인/체크아웃/주차/취소·환불/인원추가/부대시설/편의시설 질문용.
        처음 보는 호텔은 자동 적재하며, 답변 대신 해당 호텔의 근거 청크만 반환한다.
        """
        if not 1 <= top_k <= 10:
            raise ValueError("top_k는 1~10 사이여야 합니다.")
        return policy_service.ask(
            accommodation_id=accommodation_id,
            question=question,
            top_k=top_k,
        ).model_dump(mode="json")
