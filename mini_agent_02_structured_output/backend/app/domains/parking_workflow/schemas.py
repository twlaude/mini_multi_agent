from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GateRequest(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    direction: Literal["enter", "exit"]
    at: datetime | None = None


class GateDecision(BaseModel):
    decision: Literal["open", "deny", "hold"]
    reason: str
    mode: Literal["workflow"] = "workflow"
    check_id: int | None = None
