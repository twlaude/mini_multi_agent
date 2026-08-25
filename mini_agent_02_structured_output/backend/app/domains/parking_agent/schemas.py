from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgentGateRequest(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    direction: Literal["enter", "exit"]
    at: datetime | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class AgentGateDecision(BaseModel):
    decision: Literal["open", "deny", "hold"]
    reason: str
    mode: Literal["agent"] = "agent"
    check_id: int | None = None
