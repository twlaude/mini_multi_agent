from fastapi import FastAPI

from app.routers.llm_router import llm_router
from app.routers.media_router import media_router
from app.routers.structured_router import structured_router
from app.routers.transport_router import transport_router
from app.domains.parking_agent.router import parking_agent_router
from app.domains.parking_common.router import parking_common_router
from app.domains.parking_workflow.router import parking_workflow_router


app = FastAPI(title="Mini Agent 02 · Prompt와 Structured Output")
app.include_router(llm_router)
app.include_router(structured_router)
app.include_router(media_router)
app.include_router(transport_router)
app.include_router(parking_workflow_router)
app.include_router(parking_agent_router)
app.include_router(parking_common_router)
