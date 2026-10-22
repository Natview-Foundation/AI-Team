"""
LangGraph shared state definition for the multi-agent pipeline.

This TypedDict defines the "short-term memory" that flows through
every node in the graph. Each node reads what it needs and writes
its outputs back into the state dict.

Uses Annotated reducers so that parallel sub-agent results are
merged (appended) rather than overwritten.
"""

from __future__ import annotations

import operator
from typing import TypedDict, Optional, Annotated


class SubTask(TypedDict):
    """A single task dispatched by the Master Router to a sub-agent."""
    table_name: str          # DuckDB view name, e.g. "hrh_em_vaccine"
    sub_question: str        # The specific sub-question for this table


class SubAgentResult(TypedDict):
    """The result returned by a single table sub-agent."""
    table_name: str
    sql: str
    rows: list[dict]
    error: Optional[str]


class AgentState(TypedDict, total=False):
    """
    The central state object passed between all LangGraph nodes.

    Fields are populated progressively as the graph executes:
      1. 'question'           – set at graph entry
      2. 'resolved_entities'  – set by entity_resolver node
      3. 'sub_tasks'          – set by master_router node
      4. 'sub_agent_results'  – set by sql_sub_agent node (uses add reducer for fan-in)
      5. 'answer'             – set by synthesizer node
    """
    # ── Input ──
    question: str                                  # The normalized user question
    conversation_history: list[dict]                # Recent Q&A pairs for follow-up context

    # ── Entity Resolver output ──
    resolved_entities: dict[str, Optional[str]]    # {"lga": ..., "facility": ..., "ward": ...}

    # ── Master Router output ──
    sub_tasks: list[SubTask]                       # Which tables to query and with what question

    # ── Sub-Agent outputs ──
    # Annotated with operator.add so parallel Send() results are appended, not overwritten
    sub_agent_results: Annotated[list[SubAgentResult], operator.add]

    # ── Final Synthesizer output ──
    answer: str                                     # The natural language response
