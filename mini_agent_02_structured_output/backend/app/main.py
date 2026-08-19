from fastapi import FastAPI

from app.routers.llm_router import llm_router
from app.routers.media_router import media_router
from app.routers.structured_router import structured_router


app = FastAPI(title="Mini Agent 02 · Prompt와 Structured Output")
app.include_router(llm_router)
app.include_router(structured_router)
app.include_router(media_router)
