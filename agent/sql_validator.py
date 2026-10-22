"""
SQL validation module using sqlglot.
Prevents execution of modifying queries (DROP, INSERT, etc.) and
ensures queries only touch allowed tables.
"""

import sqlglot
from sqlglot import exp

from agent.constants import TABLE_SCHEMAS


def validate_sql(sql: str, allowed_table: str = None) -> tuple[bool, str]:
    """
    Validates a SQL query for safety.
    
    Args:
        sql: The SQL query string to validate.
        allowed_table: If provided, only this table name is permitted.
                       If None, any table in TABLE_SCHEMAS is allowed.

    Returns (True, "OK") if safe, or (False, "Reason") if unsafe.
    """
    if not sql or not sql.strip():
        return False, "Query is empty."

    # 1. Parse with sqlglot
    try:
        # We parse with DuckDB dialect
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        return False, f"SQL parsing error: {str(e)}"
    
    # Filter out None statements which might happen on empty strings
    statements = [s for s in statements if s is not None]

    # 2. Check for multiple statements
    if len(statements) != 1:
        return False, f"Only a single statement is allowed. Found {len(statements)} statements."

    statement = statements[0]

    # 3. Must be a SELECT statement
    if not isinstance(statement, exp.Select):
        return False, f"Only SELECT statements are allowed. Found: {type(statement).__name__}"

    # 4. Check referenced tables
    valid_tables = {allowed_table.lower()} if allowed_table else {t.lower() for t in TABLE_SCHEMAS.keys()}

    # Extract Common Table Expression (CTE) aliases and allow them as valid tables
    with_node = statement.args.get("with")
    if with_node:
        for cte in with_node.expressions:
            if cte.alias:
                valid_tables.add(cte.alias.lower())

    for table in statement.find_all(exp.Table):
        if table.name.lower() not in valid_tables:
            allowed_str = allowed_table if allowed_table else ", ".join(sorted(TABLE_SCHEMAS.keys()))
            return False, f"Query references unauthorized table '{table.name}'. Allowed: {allowed_str}"

    # If we got here, the query passed all checks
    return True, "OK"
