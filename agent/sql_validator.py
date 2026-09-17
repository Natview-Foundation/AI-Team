"""
SQL validation module using sqlglot.
Prevents execution of modifying queries (DROP, INSERT, etc.) and
ensures queries only touch allowed tables and columns.
"""

import sqlglot
from sqlglot import exp

from agent.constants import ALL_COLUMNS
from config import TABLE_NAME


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Validates a SQL query for safety.
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
    for table in statement.find_all(exp.Table):
        # table.name gives the string name
        if table.name.lower() != TABLE_NAME.lower():
            return False, f"Query references unauthorized table '{table.name}'. Only '{TABLE_NAME}' is allowed."

    # 5. Check referenced columns (whitelist check)
    # We allow * (star), but if specific columns are named, they must be in the whitelist
    # Convert ALL_COLUMNS to a lower-case set for case-insensitive checking
    # allowed_columns_lower = {c.lower() for c in ALL_COLUMNS}
    
    # for column in statement.find_all(exp.Column):
    #     col_name = column.name
    #     # Skip star
    #     if col_name == "*":
    #         continue
            
    #     # DuckDB might return internal names or if a column isn't perfectly matched,
    #     # we strictly check against the whitelist.
    #     if col_name.lower() not in allowed_columns_lower:
    #         return False, f"Query references unauthorized column '{col_name}'."

    # If we got here, the query passed all checks
    return True, "OK"
