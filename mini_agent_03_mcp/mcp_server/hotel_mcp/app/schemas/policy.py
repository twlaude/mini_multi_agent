"""호텔 규정 수집·검색에 쓰는 데이터 모델."""

from pydantic import BaseModel


class PolicySection(BaseModel):
    """여기어때 상세에서 추출한 규정 섹션 하나."""

    title: str
    contents: list[str]


class PolicyChunk(BaseModel):
    """벡터 저장소에 넣는 호텔 규정 청크."""

    accommodation_id: int
    hotel_name: str
    city: str
    section_title: str
    chunk_index: int
    content: str
    sha: str


class PolicyHit(BaseModel):
    """유사도 검색 결과 한 건."""

    chunk: PolicyChunk
    score: float


class PolicyAnswer(BaseModel):
    """특정 호텔의 규정 질문에 대한 근거 청크 묶음."""

    accommodation_id: int
    hotel_name: str
    indexed_now: bool
    hits: list[PolicyHit]
