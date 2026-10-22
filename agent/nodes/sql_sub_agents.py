"""
SQL Sub-Agent Node for the LangGraph pipeline.

Each invocation handles a SINGLE sub-task: it receives a table name
and a sub-question, generates DuckDB SQL for that specific table,
executes it, and returns the result.

This node is invoked via LangGraph's Send() fan-out — one instance
per sub-task dispatched by the Master Router.  Results are merged
back via the operator.add reducer on AgentState["sub_agent_results"].
"""

import logging
import json
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agent.llm import get_llm
from agent.constants import (
    get_table_columns_str, 
    get_table_description,
    AGENT_PROMPTS
)
from agent.sql_validator import validate_sql
from core.database import execute_query

logger = logging.getLogger(__name__)

MAX_RETRIES = 1


def _build_sub_agent_system_prompt(table_name: str, resolved_entities: dict) -> str:
    """Build a table-specific system prompt with column schema and entity context."""
    columns_str = get_table_columns_str(table_name)
    description = get_table_description(table_name)

    entities_block = ""
    if resolved_entities:
        parts = []
        if resolved_entities.get("lga"):
            parts.append(f"LGA = '{resolved_entities['lga']}'")
        if resolved_entities.get("facility"):
            parts.append(f"Facility = '{resolved_entities['facility']}'")
        if resolved_entities.get("ward"):
            parts.append(f"Ward = '{resolved_entities['ward']}'")
        if parts:
            fac_col = "longitudinal_id" if "longitudinal_id" in columns_str else "facility"
            entities_block = f"""
PRE-RESOLVED ENTITIES:
  {', '.join(parts)}

GEOGRAPHIC FILTERING RULES:
  - Use ONLY the entities listed above in your WHERE clause.
  - NEVER guess, infer, or invent an LGA or Ward that is not listed above.
  - If only a Facility is provided, filter ONLY by that facility (e.g. {fac_col} = '{resolved_entities.get('facility')}'). Every facility identifier is globally unique. Do NOT add unrequested LGA or Ward conditions.
"""

    # Determine the geographic column names for this table
    # Some tables use "lga"/"ward", others use "facility_details-lga"/"facility_details-ward"
    geo_hint = ""
    if "facility_details-lga" in columns_str:
        geo_hint = """
GEOGRAPHIC COLUMN NOTE:
  If (and ONLY if) an LGA or Ward was explicitly requested/pre-resolved:
  This table uses "facility_details-lga" for LGA and "facility_details-ward" for ward.
  Do NOT filter by LGA or Ward if the user only specified a facility!
"""
    elif "LGA" in columns_str:
        geo_hint = """
GEOGRAPHIC COLUMN NOTE:
  If (and ONLY if) an LGA or Ward was explicitly requested/pre-resolved:
  This table uses "LGA" for LGA and "Ward" for ward (capitalized).
  Do NOT filter by LGA or Ward if the user only specified a facility!
"""

    if "longitudinal_id" in columns_str and "facility" not in columns_str:
        geo_hint += """
FACILITY COLUMN NOTE:
  This table uses "longitudinal_id" as the facility identifier (e.g. longitudinal_id = 'facility_id').
  It does NOT have a column named "facility".
"""

    # Fetch the domain-specific prompt for this table, fallback to generic
    fallback_prompt = """You are a specialist SQL agent for the "{table_name}" table.
TABLE DESCRIPTION: {description}
{entities_block}
{geo_hint}
RULES:
  - Generate a DuckDB-compatible SQL SELECT query against the table named `{table_name}`.
  - SELECT statements ONLY.
  - STRICT COLUMN MATCHING: Use ONLY exact column names.
  - EXCLUDE NOT APPLICABLE: Exclude '-1' values.
  - BROAD REQUESTS: Use SELECT *.
  - TEMPORAL: Default to latest Week/Round if available.

AVAILABLE COLUMNS:
{columns_str}

Respond with ONLY the SQL query. No markdown."""

    base_prompt_template = AGENT_PROMPTS.get(table_name, fallback_prompt)

    # Format the template with the specific details
    return base_prompt_template.format(
        table_name=table_name,
        description=description,
        entities_block=entities_block,
        geo_hint=geo_hint,
        columns_str=columns_str
    )


def sql_sub_agent_node(state: dict) -> dict:
    """
    LangGraph node: Generates and executes SQL for a single table sub-task.

    This node is invoked via Send() with a state containing:
      - table_name: str
      - sub_question: str
      - resolved_entities: dict
      - question: str (original question, for context)

    Returns: {"sub_agent_results": [SubAgentResult]}
    """
    table_name = state["table_name"]
    sub_question = state["sub_question"]
    resolved_entities = state.get("resolved_entities", {})
    original_question = state.get("question", sub_question)

    # Fetch agent name for logging if it's explicitly named in the prompt (e.g. [BaselineDataAgent])
    agent_prompt = AGENT_PROMPTS.get(table_name, "")
    agent_log_name = f"SubAgent:{table_name}"
    
    # Extract name like [BaselineDataAgent]
    match = re.search(r"\[([a-zA-Z0-9_]+Agent)\]", agent_prompt)
    if match:
        agent_log_name = match.group(1)

    logger.info(f"[{agent_log_name}] Processing: '{sub_question[:60]}...'")

    llm = get_llm()
    parser = StrOutputParser()

    system_prompt = _build_sub_agent_system_prompt(table_name, resolved_entities)

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{sub_question}")
    ])

    chain = prompt | llm | parser

    sql = ""
    rows = []
    error = None

    for attempt in range(1 + MAX_RETRIES):
        try:
            # Generate SQL
            if attempt == 0:
                sql = chain.invoke({"sub_question": sub_question}).strip()
            else:
                # Retry with error context
                retry_prompt = ChatPromptTemplate.from_messages([
                    ("system", system_prompt),
                    ("human", (
                        "Original question: {sub_question}\n\n"
                        "Your previous SQL failed with this error:\n"
                        "SQL: {failed_sql}\n"
                        "Error: {error_msg}\n\n"
                        "Fix the SQL and respond with ONLY the corrected SQL query."
                    ))
                ])
                retry_chain = retry_prompt | llm | parser
                sql = retry_chain.invoke({
                    "sub_question": sub_question,
                    "failed_sql": sql,
                    "error_msg": error
                }).strip()

            # Strip any markdown fences the LLM might add
            if sql.startswith("```"):
                sql = sql.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            logger.info(f"[{agent_log_name}] Generated SQL: {sql[:80]}...")

            # Validate
            is_safe, reason = validate_sql(sql, table_name)
            if not is_safe:
                error = f"Validation failed: {reason}"
                logger.warning(f"[{agent_log_name}] {error}")
                if attempt >= MAX_RETRIES:
                    break
                continue

            # Execute
            rows = execute_query(sql)
            logger.info(f"[{agent_log_name}] Query returned {len(rows)} rows.")
            error = None
            break

        except Exception as e:
            error = str(e)
            logger.warning(f"[{agent_log_name}] Attempt {attempt+1} failed: {error}")

    result = {
        "table_name": table_name,
        "sql": sql,
        "rows": rows,
        "error": error,
    }

    return {"sub_agent_results": [result]}
