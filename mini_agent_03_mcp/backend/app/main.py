from fastapi import FastAPI, HTTPException, Query

from .agent import run_agent
from .mcp_client import MCP_SERVERS, discover_resources, discover_tools, read_resource
from .schemas import McpRunRequest, McpRunResult


app = FastAPI(title="Mini Agent 03 MCP", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "stage": "mini_agent_03_mcp",
        "mcp_servers": {
            name: config["transport"]
            for name, config in MCP_SERVERS.items()
        },
    }


@app.get("/api/mcp/status")
async def mcp_status():
    try:
        tools = await discover_tools()
        return {
            "status": "connected",
            "servers": [
                {
                    "name": name,
                    "transport": config["transport"],
                    "endpoint": config.get("url", "child process"),
                }
                for name, config in MCP_SERVERS.items()
            ],
            "tool_count": len(tools),
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"MCP Server 연결 실패: {error}",
        ) from error


@app.get("/api/mcp/tools")
async def list_mcp_tools():
    try:
        return {"tools": await discover_tools()}
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Tool 발견 실패: {error}") from error


@app.get("/api/mcp/resources")
async def list_mcp_resources():
    try:
        return {"resources": await discover_resources()}
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Resource 발견 실패: {error}") from error


@app.get("/api/mcp/resource")
async def get_mcp_resource(
    server: str = Query(description="MCP Server 이름 (예: hotel)"),
    uri: str = Query(description="Resource URI (예: yeogi://today)"),
):
    """Tool이 아닌 MCP Resource를 읽습니다. (예: hotel 서버의 yeogi://today)"""
    try:
        content = await read_resource(server, uri)
        return {"server": server, "uri": uri, "content": content}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Resource 읽기 실패: {error}") from error


@app.post("/api/mcp/run", response_model=McpRunResult)
async def run_mcp_agent(payload: McpRunRequest) -> McpRunResult:
    try:
        return await run_agent(payload.question)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Agent 실행 실패: {error}") from error
