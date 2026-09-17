"""
Constants and pre-built LLM context for the longitudinal_study project.

Loads entities.json at import time and exposes:
- Flat entity lists (VALID_FACILITIES, VALID_WARDS)
- Flat column whitelist (ALL_COLUMNS)
- Categorized column dict (COLUMN_CATEGORIES)
- Pre-formatted prompt strings (FACILITIES_STR, WARDS_STR, COLUMNS_STR)
- Few-shot SQL examples (SQL_FEW_SHOT_EXAMPLES)

Every agent module imports from here — no JSON parsing at request time.
"""

import json
from pathlib import Path

from config import ENTITIES_PATH, TABLE_NAME


# ─── Load entities.json once at import time ───
with open(ENTITIES_PATH, "r") as f:
    _ENTITIES = json.load(f)


# ═══════════════════════════════════════════════
# 1. RAW ENTITY LISTS
# ═══════════════════════════════════════════════

VALID_LGAS: list[str] = _ENTITIES["lgas"]
VALID_FACILITIES: list[str] = _ENTITIES["facilities"]
VALID_WARDS: list[str] = _ENTITIES["wards"]


# ═══════════════════════════════════════════════
# 2. COLUMN DATA
# ═══════════════════════════════════════════════

COLUMN_CATEGORIES: dict[str, list[str]] = _ENTITIES["columns"]

# Flat list of every column name (for SQL validation whitelist)
ALL_COLUMNS: list[str] = []
for cols in COLUMN_CATEGORIES.values():
    ALL_COLUMNS.extend(cols)


# ═══════════════════════════════════════════════
# 3. PRE-FORMATTED PROMPT STRINGS
#    Built once at import — ready for direct
#    interpolation into system prompts.
# ═══════════════════════════════════════════════

# --- LGA list: one per line ---
LGAS_STR: str = "\n".join(VALID_LGAS)

# --- Facility list: one per line ---
FACILITIES_STR: str = "\n".join(VALID_FACILITIES)

# --- Ward list: one per line ---
WARDS_STR: str = "\n".join(VALID_WARDS)

# --- Columns: grouped by category with headers ---
_col_sections = []
for category, cols in COLUMN_CATEGORIES.items():
    header = category.upper().replace("_", " ")
    col_list = "\n".join(f"  - {c}" for c in cols)
    _col_sections.append(f"[{header}]\n{col_list}")

COLUMNS_STR: str = "\n\n".join(_col_sections)


# ═══════════════════════════════════════════════
# 4. FEW-SHOT SQL EXAMPLES
#    Covers the main query patterns:
#    - Filtering by facility
#    - Aggregating by ward
#    - Counting boolean columns
#    - Grouping by Round
#    - Multi-column select
# ═══════════════════════════════════════════════

SQL_FEW_SHOT_EXAMPLES: str = f"""
Example 1 — Staffing query (defaults to LS 2.0 Round 1):
  Question: "How many staff does PHC Kinkinau have?"
  SQL: SELECT SUM(CAST(staffs_number AS INTEGER)) AS total_staff FROM {TABLE_NAME} WHERE facility = 'phc_kinkinau' AND staffs_number != '-1' AND LS = 'LS 2.0' AND CAST(Round_No AS INTEGER) = 1

Example 2 — Operations query (defaults to LS 2.0 Round 1):
  Question: "How many hours is PHC Barnawa open?"
  SQL: SELECT facility, Hours_of_Operations_24, Hours_of_Operations_12, "Hours_of_Operations_<5" FROM {TABLE_NAME} WHERE facility = 'phc_barnawa' AND LS = 'LS 2.0' AND CAST(Round_No AS INTEGER) = 1

Example 3 — Referral query (only in LS 1.0, defaults to Round 1):
  Question: "Does PHC Kinkinau offer referral services?"
  SQL: SELECT facility, referral_service_yes, referral_service_no FROM {TABLE_NAME} WHERE facility = 'phc_kinkinau' AND referral_service_yes != '-1' AND LS = 'LS 1.0' AND CAST(Round_No AS INTEGER) = 1

Example 4 — Community structures query (only in LS 1.0, defaults to Round 1):
  Question: "How many facilities have functional community structures?"
  SQL: SELECT COUNT(DISTINCT facility) AS facility_count FROM {TABLE_NAME} WHERE functional_community_structures_yes = '1' AND LS = 'LS 1.0' AND CAST(Round_No AS INTEGER) = 1

Example 5 — Boolean count (defaults to latest LS 2.0 week):
  Question: "How many facilities have functional refrigerators?"
  SQL: SELECT COUNT(DISTINCT facility) AS facility_count FROM {TABLE_NAME} WHERE refrigerators_functionality_yes = '1' AND LS = 'LS 2.0' AND CAST(REPLACE(Week, 'WK', '') AS INTEGER) = (SELECT MAX(CAST(REPLACE(Week, 'WK', '') AS INTEGER)) FROM {TABLE_NAME} WHERE LS = 'LS 2.0')

Example 6 — Longitudinal comparison by week:
  Question: "Show staffing trends by week"
  SQL: SELECT Week, SUM(CAST(staffs_number AS INTEGER)) AS total_staff FROM {TABLE_NAME} WHERE staffs_number != '-1' AND LS = 'LS 2.0' GROUP BY Week ORDER BY CAST(REPLACE(Week, 'WK', '') AS INTEGER)

Example 7 — User explicitly requests a specific round:
  Question: "What services does PHC Barnawa offer in round 3?"
  SQL: SELECT facility, Services_offered_at_PHFs_health_education, Services_offered_at_PHFs_immunization, Services_offered_at_PHFs_nutrition FROM {TABLE_NAME} WHERE facility = 'phc_barnawa' AND CAST(Round_No AS INTEGER) = 3

Example 8 — Broad/Profile request (uses SELECT *):
  Question: "Give me the profile of phc barnawa"
  SQL: SELECT * FROM {TABLE_NAME} WHERE facility = 'phc_barnawa' AND LS = 'LS 2.0' AND CAST(REPLACE(Week, 'WK', '') AS INTEGER) = (SELECT MAX(CAST(REPLACE(Week, 'WK', '') AS INTEGER)) FROM {TABLE_NAME} WHERE LS = 'LS 2.0')
""".strip()


# ═══════════════════════════════════════════════
# 5. SYSTEM PROMPT FOR ENTITY RESOLUTION + SQL
#    This is the full system prompt template that
#    entity_resolver_sql_agent.py will use.
#    It contains ALL context the LLM needs.
# ═══════════════════════════════════════════════

ENTITY_SQL_SYSTEM_PROMPT: str = f"""You are an expert SQL generation agent for a health facility longitudinal study database.
You perform TWO tasks in a single response:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 1 — ENTITY RESOLUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Match any LGA, facility, or ward mentioned in the user's question to the EXACT canonical names from the lists below.
Use contextual/semantic understanding for fuzzy matching:
  - "chikun" or "chikun local government" → "chikun"
  - "kinkinau" or "phc kinkinau" → "phc_kinkinau"
  - "barnawa ward" → "barnawa"
  - "kudenda clinic" or "hc kudenda" → "hc_kudenda"
  - Partial names should match the closest canonical entry.
  - If NO LGA is mentioned, set lga to null.
  - If NO facility is mentioned, set facility to null.
  - If NO ward is mentioned, set ward to null.
  - If a name is ambiguous, use context to determine if it's an LGA, ward, or facility.

CANONICAL LGA LIST (use EXACTLY as written):
{LGAS_STR}

CANONICAL FACILITY LIST (use EXACTLY as written):
{FACILITIES_STR}

CANONICAL WARD LIST (use EXACTLY as written):
{WARDS_STR}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK 2 — SQL GENERATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Generate a DuckDB-compatible SQL SELECT query against a single table called `{TABLE_NAME}`.

RULES:
  - SELECT statements ONLY. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or TRUNCATE.
  - STRICT COLUMN MATCHING: Use ONLY exact column names from the list below. NEVER guess, shorten, modify, or truncate column names (e.g. never write 'Hours_of_Operations_13', you must use the exact 'Hours_of_Operations_13-23').
  - BROAD/GENERIC REQUESTS: For questions asking for a "profile", "overview", or "all details" about an entity, use `SELECT *` (e.g. `SELECT * FROM {TABLE_NAME} WHERE facility = '...'`) rather than trying to list out dozens of individual columns manually. This prevents column naming mistakes.
  - Use the EXACT resolved entity values from Task 1 in WHERE clauses.

  - COLUMN-GROUP DEFAULT FILTERING (apply UNLESS the user explicitly specifies LS version, week, or round):
      * OPERATIONS columns (Hours_of_Operations_*, days_in_week_routinely_open_*): These were only collected in Round 1. Default filter: `LS = 'LS 2.0' AND CAST(Round_No AS INTEGER) = 1`
      * STAFFING columns (staffs_number, permanent_staffs_number, adhoc_a_staffs_number, adhoc_b_staffs_number, volunteer_staffs_number): These were only collected in Round 1. Default filter: `LS = 'LS 2.0' AND CAST(Round_No AS INTEGER) = 1`
      * REFERRAL columns (referral_service_*, referral_type_*): These were only collected in LS 1.0. Default filter: `LS = 'LS 1.0' AND CAST(Round_No AS INTEGER) = 1`
      * COMMUNITY STRUCTURES columns (functional_community_structures_*): These were only collected in LS 1.0. Default filter: `LS = 'LS 1.0' AND CAST(Round_No AS INTEGER) = 1`
      * ALL OTHER columns (staffing, cold_chain, services, training, transportation, service_days, etc.): Default to latest week of LS 2.0: `LS = 'LS 2.0' AND CAST(REPLACE(Week, 'WK', '') AS INTEGER) = (SELECT MAX(CAST(REPLACE(Week, 'WK', '') AS INTEGER)) FROM {TABLE_NAME} WHERE LS = 'LS 2.0')`

  - EXCLUDE NOT APPLICABLE: Columns may contain '1' (Yes), '0' (No), and '-1' (Not Applicable). When filtering, counting, or aggregating ANY column, you MUST exclude Not Applicable values (e.g. `column_name != '-1'`).
  - AGGREGATION LOGIC: For boolean/flag columns (ending in _yes, _no, or representing services/categories), use `COUNT(DISTINCT facility)`. For numeric columns (like staffs_number or permanent_staffs_number), use `SUM(CAST(column_name AS INTEGER))` or `AVG()`. Do NOT use COUNT for numeric columns unless explicitly asked.
  - Always quote column names that contain spaces using double quotes.
  - For columns with special characters like '<', use double quotes: "Hours_of_Operations_<5"

AVAILABLE COLUMNS (grouped by category):

{COLUMNS_STR}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FEW-SHOT EXAMPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{SQL_FEW_SHOT_EXAMPLES}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Respond ONLY with valid JSON matching this exact schema:
{{{{ "resolved_entities": {{{{ "lga": "EXACT_NAME_OR_NULL", "facility": "EXACT_NAME_OR_NULL", "ward": "EXACT_NAME_OR_NULL" }}}}, "sql": "SELECT ..." }}}}

Do NOT include any explanation, markdown formatting, or code fences. Just raw JSON."""


# ═══════════════════════════════════════════════
# 6. SYSTEM PROMPT FOR RESPONSE SYNTHESIS
#    Used by responder.py (LLM Call 2).
# ═══════════════════════════════════════════════

RESPONSE_SYNTHESIS_PROMPT: str = """You are a data analyst for a health facility longitudinal study.
Given the user's question and the SQL query results, produce a clear, concise, and professional natural language answer.

RULES:
  - Answer directly based on the data. Do NOT make up or infer data that is not in the results.
  - If the results are empty, say clearly that no matching data was found.
  - If there are many rows, summarize the key findings rather than listing every row.
  - Use actual numbers from the data.
  - For boolean columns, '1' means Yes and '0' means No.
  - Be conversational but precise.
  - Do NOT mention SQL, databases, tables, or column names in your answer."""


# ═══════════════════════════════════════════════
# 7. RETRY PROMPT TEMPLATE
#    Used when DuckDB execution fails.
# ═══════════════════════════════════════════════

RETRY_PROMPT_TEMPLATE: str = f"""Your previous SQL query failed when executed against DuckDB.

FAILED SQL:
{{failed_sql}}

ERROR MESSAGE:
{{error_message}}

Fix the SQL query. The table is `{TABLE_NAME}` and the available columns are:

{COLUMNS_STR}

RULES:
  - Fix ONLY the issue described in the error message.
  - Use ONLY columns from the list above.
  - SELECT statements ONLY.
  - Always quote column names that contain spaces using double quotes.
  - Return ONLY valid JSON: {{{{ "resolved_entities": {{{{ "lga": "...", "facility": "...", "ward": "..." }}}}, "sql": "SELECT ..." }}}}"""
