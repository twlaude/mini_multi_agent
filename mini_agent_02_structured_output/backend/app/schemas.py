from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ProviderName = Literal["mock", "gemini", "openai", "ollama"]
StructuredSchemaName = Literal["travel_plan", "support_ticket", "travel_route"]


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class DecisionResult(BaseModel):
    route: str
    reason: str
    confidence: float = Field(ge=0, le=1)


class ConceptCompareResult(BaseModel):
    message: str
    workflow: DecisionResult
    semantic_router: DecisionResult
    note: str


class TravelIntentResult(BaseModel):
    intent: str
    reason: str
    confidence: float = Field(ge=0, le=1)
    missing_information: list[str] = Field(default_factory=list)
    next_action: Literal["continue", "ask_user"]
    follow_up_question: str = ""


class GenerateRequest(MessageRequest):#제너레이트 리퀘스트는 메시지 리퀘스트를 상속받는다는 의미다.
    provider: ProviderName | None = None
    system_prompt: str = Field(
        default="당신은 초보자를 돕는 친절한 여행 도우미입니다.",
        max_length=2000,
    )


class GenerateResult(BaseModel):
    provider: ProviderName
    model: str
    content: str
    latency_ms: int


class ProviderCompareRequest(MessageRequest):
    providers: list[ProviderName] = Field(
        default_factory=lambda: ["mock"], min_length=1, max_length=4
    )
    system_prompt: str = Field(
        default="당신은 초보자를 돕는 친절한 여행 도우미입니다.",
        max_length=2000,
    )


class ProviderComparisonItem(BaseModel):
    provider: ProviderName
    status: Literal["success", "error"]
    model: str = ""
    content: str = ""
    latency_ms: int = 0
    error: str | None = None


class ProviderCompareResult(BaseModel):
    request_count: int
    results: list[ProviderComparisonItem]


class PromptPreviewRequest(BaseModel):
    role: str = Field(min_length=1, max_length=500)
    instruction: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1, max_length=1000)
    constraint: str = Field(min_length=1, max_length=1000)
    output_format: str = Field(default="", max_length=1000)


class PromptPreviewResult(PromptPreviewRequest):
    prompt: str


class TravelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=500)
    recommended_days: int = Field(ge=1, le=30)
    activities: list[str] = Field(min_length=1, max_length=10)
    cautions: list[str] = Field(default_factory=list, max_length=10)


class SupportTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["billing", "technical", "account", "other"]
    priority: Literal["low", "medium", "high"]
    summary: str = Field(min_length=1, max_length=300)
    requires_human: bool = Field(strict=True)
    missing_information: list[str] = Field(default_factory=list, max_length=10)


class LandmarkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=50)
    day: int = Field(ge=1, le=30)
    visit_order: int = Field(ge=1, le=10)
    stay_minutes: int = Field(ge=10, le=600)
    tip: str = Field(default="", max_length=300)


class FoodItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    cuisine: str = Field(min_length=1, max_length=50)
    signature_menu: str = Field(min_length=1, max_length=100)
    price_range: str = Field(min_length=1, max_length=50)
    day: int = Field(ge=1, le=30)
    meal_time: Literal["아침", "점심", "저녁"]
    near_landmark: str = Field(default="", max_length=100)


class TravelRoutePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str = Field(min_length=1)
    nights: int = Field(ge=0, le=29)
    days: int = Field(ge=1, le=30)
    summary: str = Field(min_length=1, max_length=500)
    landmarks: list[LandmarkItem] = Field(min_length=1, max_length=30)
    foods: list[FoodItem] = Field(default_factory=list, max_length=30)


class OriginPoint(BaseModel):
    """프론트에서 확정한 브라우저 위치 또는 장소 검색 결과."""

    lat: float
    lng: float
    name: str = ""


class TransitRoutePreference(BaseModel):
    """LLM이 선택하는 대중교통 선호값. 좌표는 서버가 주입한다."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["all", "train", "bus", "air"] = "all"


class DrivingRoutePreference(BaseModel):
    """LLM이 선택하는 자가용 비용 계산 선호값. 좌표는 서버가 주입한다."""

    model_config = ConfigDict(extra="forbid")

    fuel_efficiency_kmpl: float = Field(default=12.0, gt=0, le=40)
    fuel_price_per_liter: int = Field(default=1650, gt=0, le=5000)


class TransitRouteArgs(BaseModel):
    """LLM이 제안하되 백엔드가 좌표와 출발 시각을 확정하는 대중교통 인자."""

    model_config = ConfigDict(extra="forbid")

    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    departure_time: datetime | None = None
    mode: Literal["all", "train", "bus", "air"] = "all"


class DrivingRouteArgs(BaseModel):
    """자가용 길찾기와 유류비 계산에 필요한 검증된 인자."""

    model_config = ConfigDict(extra="forbid")

    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    departure_time: datetime | None = None
    fuel_efficiency_kmpl: float = Field(default=12.0, gt=0, le=40)
    fuel_price_per_liter: int = Field(default=1650, gt=0, le=5000)


class TravelRouteRequest(BaseModel):
    provider: ProviderName | None = None
    # 기존 자연어 한 줄 요청도 계속 받는다.
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    origin: OriginPoint | None = None
    destination: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "TravelRouteRequest":
        has_schedule = bool(
            self.destination and self.start_date is not None and self.end_date is not None
        )
        if not self.message and not has_schedule:
            raise ValueError(
                "message 또는 destination, start_date, end_date를 입력해야 합니다."
            )
        if self.start_date is not None and self.end_date is not None:
            nights = (self.end_date - self.start_date).days
            if nights < 0:
                raise ValueError("end_date는 start_date보다 빠를 수 없습니다.")
            if nights >= 30:
                raise ValueError("여행 기간은 30일 이하여야 합니다.")
        return self


class TravelSchedule(BaseModel):
    destination: str
    start_date: date
    end_date: date
    start_time: time | None = None
    end_time: time | None = None
    nights: int
    days: int


class GeoPlace(BaseModel):
    name: str
    kind: Literal["landmark", "food", "origin"]
    day: int
    order: int  # landmark는 visit_order, food는 0 (경로선은 landmark만 잇는다)
    lat: float
    lng: float
    address: str = ""


class TravelRouteResult(BaseModel):
    provider: ProviderName
    model: str
    plan: TravelRoutePlan
    places: list[GeoPlace]
    not_found: list[str] = Field(default_factory=list)
    latency_ms: int
    origin: GeoPlace | None = None
    schedule: TravelSchedule | None = None


class ToolRunRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolRunResult(BaseModel):
    success: bool
    tool_name: str
    data: Any | None = None
    error: dict[str, Any] | None = None


class ToolSelectionResult(BaseModel):
    provider: ProviderName
    model: str
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str
    confidence: float = Field(ge=0, le=1)
    latency_ms: int = 0
    raw_tool_call: dict[str, Any] | None = None


class TravelTransportRequest(BaseModel):
    provider: ProviderName | None = None
    message: str = Field(min_length=1, max_length=4000)
    origin: OriginPoint
    destination: OriginPoint
    departure_time: datetime | None = None
    tool_choice: Literal["auto", "none", "required"] = "auto"


class ToolCompleteResult(BaseModel):
    provider: ProviderName
    question: str
    decision: ToolSelectionResult
    tool_result: ToolRunResult | None = None
    final_answer: str
    trace: list[dict[str, Any]] = Field(default_factory=list)


class PlaceCandidate(BaseModel):
    name: str
    address: str
    lat: float
    lng: float
    category: str = ""


class PlaceSearchResult(BaseModel):
    query: str
    candidates: list[PlaceCandidate] = Field(default_factory=list)
    note: str = ""


class ReverseGeocodeResult(BaseModel):
    lat: float
    lng: float
    address: str = ""
    region: str = ""
    note: str = ""


class CityItem(BaseModel):
    name: str
    lat: float
    lng: float


class StructuredValidationRequest(BaseModel):
    schema_type: StructuredSchemaName = "travel_plan"
    payload: dict[str, Any]


class StructuredValidationResult(BaseModel):
    schema_type: StructuredSchemaName
    valid: bool
    data: TravelPlan | SupportTicket | TravelRoutePlan | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class StructuredOutputRequest(MessageRequest):
    provider: ProviderName | None = None
    schema_type: StructuredSchemaName = "travel_plan"
    system_prompt: str = Field(
        default=(
            "당신은 사용자 요청 분석 도우미입니다. 제공된 Pydantic Schema에 맞춰 "
            "추측을 피하고 안전하고 간결한 결과를 작성하세요."
        ),
        max_length=2000,
    )


class StructuredOutputResult(BaseModel):
    provider: ProviderName
    model: str
    schema_type: StructuredSchemaName
    content: TravelPlan | SupportTicket | TravelRoutePlan
    latency_ms: int


class StructuredCompareRequest(MessageRequest):
    providers: list[ProviderName] = Field(
        default_factory=lambda: ["mock"], min_length=1, max_length=4
    )
    schema_type: StructuredSchemaName = "travel_plan"
    system_prompt: str = Field(
        default=(
            "당신은 사용자 요청 분석 도우미입니다. 제공된 Pydantic Schema에 맞춰 "
            "추측을 피하고 안전하고 간결한 결과를 작성하세요."
        ),
        max_length=2000,
    )


class StructuredComparisonItem(BaseModel):
    provider: ProviderName
    status: Literal["success", "error"]
    model: str = ""
    schema_type: StructuredSchemaName
    content: TravelPlan | SupportTicket | TravelRoutePlan | None = None
    latency_ms: int = 0
    error: str | None = None


class StructuredCompareResult(BaseModel):
    request_count: int
    results: list[StructuredComparisonItem]


class TravelImageAnalysis(BaseModel):
    scene_type: Literal[
        "landmark", "food", "transport", "accommodation", "document", "other"
    ]
    summary: str = Field(min_length=1, max_length=500)
    visible_text: list[str] = Field(default_factory=list, max_length=10)
    travel_tips: list[str] = Field(default_factory=list, max_length=10)
    safety_notes: list[str] = Field(default_factory=list, max_length=10)


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: Literal[
        "alloy", "ash", "ballad", "coral", "echo", "fable", "nova",
        "onyx", "sage", "shimmer", "verse", "marin", "cedar"
    ] | None = None
    instructions: str = Field(
        default="한국어로 또렷하고 따뜻한 여행 가이드처럼 말하세요.",
        max_length=500,
    )
