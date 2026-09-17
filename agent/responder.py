"""
LLM Agent responsible for Response Synthesis (Phase 8).

This module handles "Call 2" to the LLM:
1. Takes the user's original question and the raw JSON rows returned by DuckDB.
2. Returns a clear, natural language answer.
"""

import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agent.llm import get_llm
from agent.constants import RESPONSE_SYNTHESIS_PROMPT


def synthesize_response(question: str, results: list[dict]) -> str:
    """
    Takes the user question and database results, and asks the LLM
    to generate a natural language summary.
    """
    llm = get_llm()
    parser = StrOutputParser()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", RESPONSE_SYNTHESIS_PROMPT),
        ("human", "Question: {question}\n\nDatabase Results (JSON):\n{results}")
    ])
    
    chain = prompt | llm | parser
    
    try:
        print(f"  [AGENT 2] Calling LLM for Response Synthesis...")
        # Convert results to a formatted JSON string to feed the LLM
        results_str = json.dumps(results, indent=2) if results else "[]"
        
        answer = chain.invoke({"question": question, "results": results_str})
        print(f"  [AGENT 2] Success. Generated answer: {answer[:50]}...")
        return answer.strip()
        
    except Exception as e:
        print(f"  [AGENT 2] ERROR: {e}")
        return f"An error occurred while generating the response: {str(e)}"
