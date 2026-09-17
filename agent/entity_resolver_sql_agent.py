"""
LLM Agent responsible for Entity Resolution and SQL Generation (Combined Phase).

This module handles "Call 1" to the LLM:
1. Takes the normalized user question
2. Injects the full context from constants.py
3. Returns a JSON dictionary containing:
   - resolved_entities: {facility, ward}
   - sql: SELECT ...
"""

import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException

from agent.llm import get_llm
from agent.constants import ENTITY_SQL_SYSTEM_PROMPT, RETRY_PROMPT_TEMPLATE
from config import TABLE_NAME


def resolve_and_generate_sql(question: str) -> dict:
    """
    Takes a user question, performs fuzzy entity resolution and generates a SQL query.
    Returns a dict with 'resolved_entities' and 'sql'.
    """
    llm = get_llm()
    parser = JsonOutputParser()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", ENTITY_SQL_SYSTEM_PROMPT),
        ("human", "{question}")
    ])
    
    chain = prompt | llm | parser
    
    try:
        print(f"  [AGENT 1] Calling LLM for Entity Resolution & SQL Generation...")
        result = chain.invoke({"question": question})
        
        # Ensure correct structure
        if "resolved_entities" not in result:
            result["resolved_entities"] = {"lga": None, "facility": None, "ward": None}
        if "sql" not in result:
            result["sql"] = f"SELECT * FROM {TABLE_NAME} LIMIT 10" # Fallback
            
        print(f"  [AGENT 1] Success. Generated SQL: {result['sql'][:50]}...")
        return result
        
    except OutputParserException as e:
        print(f"  [AGENT 1] ERROR: LLM returned invalid JSON. {e}")
        return {
            "resolved_entities": {"lga": None, "facility": None, "ward": None},
            "sql": f"-- ERROR: Invalid JSON from LLM: {str(e)}"
        }
    except Exception as e:
        print(f"  [AGENT 1] ERROR: {e}")
        return {
            "resolved_entities": {"lga": None, "facility": None, "ward": None},
            "sql": f"-- ERROR: {str(e)}"
        }


def retry_sql_generation(question: str, failed_sql: str, error_message: str) -> dict:
    """
    Called when DuckDB fails to execute the generated SQL.
    Feeds the error back to the LLM for correction.
    """
    llm = get_llm()
    parser = JsonOutputParser()
    
    # Combine the system prompt with the retry instructions
    retry_prompt_text = ENTITY_SQL_SYSTEM_PROMPT + "\n\n" + RETRY_PROMPT_TEMPLATE
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", retry_prompt_text),
        ("human", "Original Question: {question}")
    ])
    
    chain = prompt | llm | parser
    
    try:
        print(f"  [AGENT 1 RETRY] Calling LLM to fix SQL error...")
        result = chain.invoke({
            "question": question,
            "failed_sql": failed_sql,
            "error_message": error_message
        })
        
        # Ensure correct structure
        if "resolved_entities" not in result:
            result["resolved_entities"] = {"lga": None, "facility": None, "ward": None}
        if "sql" not in result:
            result["sql"] = failed_sql # Fallback to original
            
        print(f"  [AGENT 1 RETRY] Success. Generated new SQL: {result['sql'][:50]}...")
        return result
        
    except Exception as e:
        print(f"  [AGENT 1 RETRY] ERROR: {e}")
        return {
            "resolved_entities": {"lga": None, "facility": None, "ward": None},
            "sql": f"-- RETRY ERROR: {str(e)}"
        }
