from dataclasses import dataclass

from fastapi import HTTPException
from langgraph.graph.state import CompiledStateGraph

from agents.rag_assistant import rag_assistant
from schema import AgentInfo

DEFAULT_AGENT = "rag-assistant"
AgentGraph = CompiledStateGraph
AgentGraphLike = AgentGraph


@dataclass
class Agent:
    description: str
    graph_like: AgentGraph


agents = {
    DEFAULT_AGENT: Agent(description="基于个人知识库的检索与引用问答助手", graph_like=rag_assistant)
}


async def load_agent(agent_id: str) -> None:
    get_agent(agent_id)


def get_agent(agent_id: str) -> AgentGraph:
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents[agent_id].graph_like


def get_all_agent_info() -> list[AgentInfo]:
    return [AgentInfo(key=key, description=value.description) for key, value in agents.items()]
