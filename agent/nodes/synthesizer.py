"""
Synthesizer Node for the LangGraph pipeline.

Aggregates the data results from all invoked Sub-Agents and produces
a single, cohesive natural language response to the user's question.
"""

import json
import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agent.llm import get_llm
from agent.constants import RESPONSE_SYNTHESIS_PROMPT

logger = logging.getLogger(__name__)


def synthesizer_node(state: dict) -> dict:
    """
    LangGraph node: Synthesizes a final NL answer from all sub-agent results.

    Reads:   state["question"], state["sub_agent_results"]
    Writes:  state["answer"]
    """
    question = state["question"]
    sub_agent_results = state.get("sub_agent_results", [])

    logger.info(f"[Synthesizer] Aggregating {len(sub_agent_results)} sub-agent result(s).")

    # Build a structured summary of all results for the LLM
    result_sections = []
    for result in sub_agent_results:
        table = result["table_name"]
        rows = result.get("rows", [])
        error = result.get("error")

        if error:
            result_sections.append(f"[{table}] ERROR: {error}")
        elif not rows:
            result_sections.append(f"[{table}] No data found.")
        else:
            # Truncate large result sets to avoid token overflow
            display_rows = rows[:50]  # Cap at 50 rows per table
            rows_str = json.dumps(display_rows, indent=2)
            if len(rows) > 50:
                rows_str += f"\n... and {len(rows) - 50} more rows (truncated)"
            result_sections.append(f"[{table}] {len(rows)} row(s):\n{rows_str}")

    combined_results = "\n\n".join(result_sections) if result_sections else "No results from any table."

    llm = get_llm()
    parser = StrOutputParser()

    prompt = ChatPromptTemplate.from_messages([
        ("system", RESPONSE_SYNTHESIS_PROMPT),
        ("human", "Question: {question}\n\nDatabase Results:\n{results}")
    ])

    chain = prompt | llm | parser

    try:
        answer = chain.invoke({"question": question, "results": combined_results})
        answer = answer.strip()
        logger.info(f"[Synthesizer] Generated answer ({len(answer)} chars).")
        return {"answer": answer}

    except Exception as e:
        logger.error(f"[Synthesizer] Failed: {e}")
        return {"answer": f"I was unable to generate a response: {str(e)}"}
