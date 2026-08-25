from typing import Literal

from pydantic import BaseModel, Field


class SpotEventRequest(BaseModel):
    spot_id: str = Field(min_length=1, max_length=20)
    plate: str = Field(min_length=1, max_length=20)
    event: Literal["occupied", "vacated"]


class SobrietyResultRequest(BaseModel):
    result: Literal["pass", "fail"]
