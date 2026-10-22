"""
Entity Resolver Node for the LangGraph pipeline.

Extracts and fuzzy-matches geographic entities (LGA, Ward, Facility)
from the user's raw question to canonical names.

This node runs as one of the first steps in the graph,
in parallel with the Master Router.
"""

import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from agent.llm import get_llm
from agent.constants import ENTITY_RESOLVER_SYSTEM_PROMPT
from agent.state import AgentState

logger = logging.getLogger(__name__)


def entity_resolver_node(state: AgentState) -> dict:
    """
    LangGraph node: Resolves geographic entities from the user question.

    Reads:   state["question"]
    Writes:  state["resolved_entities"]
    """
    question = state["question"]
    logger.info(f"[EntityResolver] Resolving entities for: '{question[:80]}...'")

    llm = get_llm()
    parser = JsonOutputParser()

    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_RESOLVER_SYSTEM_PROMPT),
        ("human", "{question}")
    ])

    chain = prompt | llm | parser

    try:
        result = chain.invoke({"question": question})

        # Ensure all three keys exist
        resolved = {
            "lga": result.get("lga"),
            "facility": result.get("facility"),
            "ward": result.get("ward"),
        }

        logger.info(f"[EntityResolver] Resolved: {resolved}")
        return {"resolved_entities": resolved}

    except Exception as e:
        logger.error(f"[EntityResolver] Failed: {e}")
        return {"resolved_entities": {"lga": None, "facility": None, "ward": None}}
