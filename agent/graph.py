"""
LangGraph application definition for the multi-agent pipeline.

Phase 2B wires:
  START ──┬── entity_resolver (parallel) ──┐
          └── master_router   (parallel) ──┴──> sync_node ──(Send)──> sql_sub_agent(s) ──> synthesizer ──> END

The compiled graph is exposed as `app` for use by the API layer.
"""

import logging
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from agent.state import AgentState
from agent.nodes.entity_resolver import entity_resolver_node
from agent.nodes.master_router import master_router_node
from agent.nodes.sql_sub_agents import sql_sub_agent_node
from agent.nodes.synthesizer import synthesizer_node

logger = logging.getLogger(__name__)


def sync_node(state: AgentState) -> dict:
    """Dummy node to join the parallel entity_resolver and master_router branches."""
    return {}


def dispatch_sub_agents(state: AgentState):
    """
    Conditional edge router: Maps sub-tasks from the master router
    to individual sql_sub_agent nodes running in parallel.
    """
    sub_tasks = state.get("sub_tasks", [])
    resolved = state.get("resolved_entities", {})
    question = state.get("question", "")

    logger.info(f"[Graph] Dispatching {len(sub_tasks)} sub-task(s) to parallel agents.")

    sends = []
    for task in sub_tasks:
        # Construct the specific state for each parallel instance
        # Note: We pass a subset of state tailored for the sub-agent
        agent_state = {
            "table_name": task["table_name"],
            "sub_question": task["sub_question"],
            "resolved_entities": resolved,
            "question": question
        }
        sends.append(Send("sql_sub_agent", agent_state))
        
    return sends


def build_graph() -> StateGraph:
    """
    Constructs and compiles the multi-agent StateGraph.
    Returns the compiled graph application.
    """
    graph = StateGraph(AgentState)

    # ── Register nodes ──
    graph.add_node("entity_resolver", entity_resolver_node)
    graph.add_node("master_router", master_router_node)
    graph.add_node("sync_node", sync_node)
    graph.add_node("sql_sub_agent", sql_sub_agent_node)
    graph.add_node("synthesizer", synthesizer_node)

    # ── Edges ──
    # 1. Parallel execution from START
    graph.add_edge(START, "entity_resolver")
    graph.add_edge(START, "master_router")

    # 2. Join both at sync_node
    graph.add_edge("entity_resolver", "sync_node")
    graph.add_edge("master_router", "sync_node")

    # 3. Fan-out: sync_node -> (conditional Send) -> multiple sql_sub_agent instances
    graph.add_conditional_edges(
        "sync_node",
        dispatch_sub_agents,
        ["sql_sub_agent"]  # The defined target nodes that Send can map to
    )

    # 4. Fan-in: all parallel sub-agents flow into synthesizer
    graph.add_edge("sql_sub_agent", "synthesizer")

    # 5. End
    graph.add_edge("synthesizer", END)

    return graph.compile()


# ── Compile the graph once at import time ──
app = build_graph()
