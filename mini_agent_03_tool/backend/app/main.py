from fastapi import FastAPI

from app.routers.llm_router import llm_router
from app.routers.media_router import media_router
from app.routers.structured_router import structured_router
from app.routers.tool_router import tool_router


app = FastAPI(title="Mini Agent 03 · Tool Use")
app.include_router(llm_router)
app.include_router(structured_router)
app.include_router(tool_router)
app.include_router(media_router)
