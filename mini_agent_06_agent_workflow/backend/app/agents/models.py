from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    name: str
    goal: str
    description: str
    example_question: str
    instructions: str
    allowed_tools: frozenset[str]
    mcp_server: str = "business-tools"  # app.core.config.MCP_SERVERS의 키
