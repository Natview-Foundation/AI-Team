"""
Master Router Node for the LangGraph pipeline.

Analyzes the user's question and determines which database tables
contain the data needed to answer it. Creates specific sub-tasks
for each relevant table's specialist sub-agent.

This node runs as one of the first steps in the graph,
in parallel with the Entity Resolver.
"""

import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from agent.llm import get_llm
from agent.constants import MASTER_ROUTER_SYSTEM_PROMPT, TABLE_SCHEMAS, DISABLED_TABLES
from agent.state import AgentState

logger = logging.getLogger(__name__)


def master_router_node(state: AgentState) -> dict:
    """
    LangGraph node: Routes the user question to the correct table sub-agents.

    Reads:   state["question"]
    Writes:  state["sub_tasks"]
    """
    question = state["question"]
    conversation_history = state.get("conversation_history", [])
    logger.info(f"[MasterRouter] Routing question: '{question[:80]}...'")

    llm = get_llm()
    parser = JsonOutputParser()

    # Build the human message with conversation history for follow-up context
    human_message = ""
    if conversation_history:
        history_lines = []
        for turn in conversation_history[-3:]:  # Last 3 turns max
            history_lines.append(f"User: {turn.get('question', '')}")
            history_lines.append(f"Answer: {turn.get('answer', '')[:150]}...")
        human_message = f"CONVERSATION HISTORY:\n" + "\n".join(history_lines) + f"\n\nCURRENT QUESTION: {question}"
    else:
        human_message = question

    prompt = ChatPromptTemplate.from_messages([
        ("system", MASTER_ROUTER_SYSTEM_PROMPT),
        ("human", "{question}")
    ])

    chain = prompt | llm | parser

    try:
        result = chain.invoke({"question": human_message})
        sub_tasks = result.get("sub_tasks", [])

        # Validate that each sub_task references an active, non-disabled table
        valid_tables = set(TABLE_SCHEMAS.keys()) - DISABLED_TABLES
        validated_tasks = []
        for task in sub_tasks:
            table_name = task.get("table_name", "")
            if table_name in valid_tables:
                validated_tasks.append({
                    "table_name": table_name,
                    "sub_question": task.get("sub_question", question)
                })
            elif table_name in DISABLED_TABLES:
                logger.warning(f"[MasterRouter] Ignoring disabled/deprecated table: '{table_name}'")
            else:
                logger.warning(f"[MasterRouter] Ignoring unknown table: '{table_name}'")

        if not validated_tasks:
            # Fallback: if router returned nothing valid, default to baseline
            logger.warning("[MasterRouter] No valid tables selected. Defaulting to baseline_data_ls1.")
            validated_tasks = [{
                "table_name": "baseline_data_ls1",
                "sub_question": question
            }]

        logger.info(f"[MasterRouter] Dispatching to {len(validated_tasks)} table(s): "
                     f"{[t['table_name'] for t in validated_tasks]}")
        return {"sub_tasks": validated_tasks}

    except Exception as e:
        logger.error(f"[MasterRouter] Failed: {e}")
        # Fallback to baseline on error
        return {"sub_tasks": [{
            "table_name": "baseline_data_ls1",
            "sub_question": question
        }]}
