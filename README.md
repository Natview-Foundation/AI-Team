# Kaduna State Health Facility Assessment (HEFA) — Longitudinal Study AI Agent

A serverless, multi-agent Natural Language to SQL (NL2SQL) system for querying longitudinal primary healthcare survey data across ~130 Primary Health Centres (PHCs) in Kaduna State, Nigeria.

**Organization:** Natview Foundation For Technology Innovation (NFTI)  
**Backend:** FastAPI + LangGraph + DuckDB (Serverless on [Modal](https://modal.com/))  
**Storage:** Versioned Apache Parquet snapshots  

---

## 1. System Architecture

The pipeline is orchestrated as a stateful, parallel multi-agent graph powered by **LangGraph**:

```
                  ┌──────────────────────┐
                  │ User Question (REST) │
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [Entity Resolver Node]           [Master Router Node]
   Fuzzy-matches canonical          Analyzes question & conversation
   LGAs, Wards, Facilities          history; selects relevant tables
            │                                 │
            └────────────────┬────────────────┘
                             ▼
                        [Sync Node]
                             │  (Send fan-out)
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
     [Sub-Agent: Table 1]  [...]     [Sub-Agent: Table N]
     Domain prompt + SQL             Domain prompt + SQL
     glot AST validation             glot AST validation
            │                │                │
            └────────────────┼────────────────┘
                             ▼
                     [Synthesizer Node]
                     Integrates multi-table rows into a
                     plain-English conversational response
                             │
                             ▼
                     Final Answer (JSON)
```

### Graph Components
- **[`Entity Resolver`](agent/nodes/entity_resolver.py)**: Matches informal facility, ward, and LGA names against canonical identifiers in `data/reference/entities.json`.
- **[`Master Router`](agent/nodes/master_router.py)**: Analyzes questions and recent conversation turns (short-term memory) to dispatch self-contained sub-tasks to specialist table sub-agents.
- **[`SQL Sub-Agents`](agent/nodes/sql_sub_agents.py)**: Async parallel fan-out (`Send`). Each sub-agent uses table-specific schemas and rules, generates DuckDB-compatible SQL, verifies safety via [`sql_validator.py`](agent/sql_validator.py), executes via DuckDB, and retries automatically on syntax error.
- **[`Synthesizer`](agent/nodes/synthesizer.py)**: Combines multi-table query results into a clear answer without technical jargon.

---

## 2. Longitudinal Data & Query Nuances

### Staggered LGA Start Dates
Data collection occurs **bi-weekly** (`WK2`, `WK4`, `WK6`, ...). Not all Local Government Areas (LGAs) joined the study at the same time:
* **Kaduna North, Kaduna South, Chikun, Makarfi**: Started at **`WK2`** (`Round 1`).
* **Kubau**: Started late at **`WK6`** (`Round 1` = `WK6`, 2 rounds behind).
* **Jema'a**: Started late at **`WK14`** (`Round 1` = `WK14`, 6 rounds behind).

> **Nuance:** Because Kubau and Jema'a have fewer total rounds, querying global `MAX(Round_No)` returns empty sets for them.

### Default Temporal Filtering Rule
Unless the user explicitly specifies a round or week, temporal sub-agents filter for **each facility's own latest round** in LS 2.0:
```sql
WHERE LS = 'LS 2.0'
  AND CAST(Round_No AS INTEGER) = (
    SELECT MAX(CAST(Round_No AS INTEGER))
    FROM {table_name} t2
    WHERE t2.facility = {table_name}.facility
      AND t2.LS = 'LS 2.0'
  )
```
*(Note: `scm_em_stock_balance` uses `"Facility"` with an uppercase F).*

### Baseline Domain Column-Switching Rules
The `baseline_data_ls1` table contains mixed historical rounds. Sub-agents apply domain-specific filters:
- **Operations** (`Hours_of_Operations_*`, `days_in_week_*`): `LS = 'LS 2.0' AND CAST(Round_No AS INTEGER) = 1`
- **Staffing** (`staffs_number`, `permanent_staffs_number`, etc.): `LS = 'LS 2.0' AND CAST(Round_No AS INTEGER) = 1`
- **Emergency Referrals** (`referral_service_*`, `referral_type_*`): `LS = 'LS 1.0' AND CAST(Round_No AS INTEGER) = 1`
- **Community Structures** (`functional_community_structures_*`): `LS = 'LS 1.0' AND CAST(Round_No AS INTEGER) = 1`
- **All Other Baseline Columns**: Latest visit per facility in LS 2.0.

### Absenteeism Calculation
Absenteeism tables record **staff present**. To derive actual absentees, subtract staff present in `bi_weekly_hw_absenteeism` from total workforce in `bi_weekly_hw_availability`.

---

## 3. Active Tables & Registry

| Table Name | Description | Key Column Nuances |
|---|---|---|
| `baseline_data_ls1` | Core health facility baseline profile | 24h operations, cold chain, training, services, referrals. |
| `scm_em_available` | Essential medicines availability | Binary flags (`1`/`0`) per medicine. |
| `scm_em_stock_balance` | Minimum stock (`_MS`) & stock balances (`_SB`) | Facility column is capitalized: `"Facility"`. |
| `scm_vaccines_available` | Vaccine stock & availability | Binary flags per vaccine (BCG, HPV, PENTA, etc.). |
| `scm_vaccines_stock_balance`| Minimum stock (`_MS`) & stock balance (`_SB`) per vaccine | Low stock alert: `_SB < _MS`. |
| `bi_weekly_hw_availability` | Staff headcount, cadre breakdowns, shift rosters | Cadre counts; shifts (morning, afternoon, evening). |
| `bi_weekly_hw_absenteeism` | Bi-weekly staff presence per cadre | Records staff present on survey day. |
| `permanent_hw_absenteeism` | Permanent staff presence per cadre | Records permanent staff present. |
| `bi_weekly_reason_absenteeism` | Reasons for staff absence by cadre | Pattern: `Cadre_Reason` (e.g. `Nurses/Midwives_Funerals`). |
| `days_service_offered_detail` | Operating days per service | Routine opening days for immunization, ANC, delivery, etc. |
| `facility_details` | Facility metadata & MAMII classification | `facility_type`, `fac_type`, `location` (Urban/Rural). |
| `ls_facilities_list` | Master facility index & HEFA IDs | Cross-reference `ls_facility_ID` to facility name. |
| `dhis2_master_lookup` | Mapping to national DHIS2 hierarchy | `dhis2_uid`, `org_unit_name`. |

> **Deprecated Tables:** `hrh_em_vaccine` and `bi_weekly_staff_roster` are commented out (`DISABLED_TABLES`) because they only contain incomplete LS 1.0 data. Master Router directs queries to the SCM and availability tables instead.

---

## 4. Security & Safety

- **AST Validation ([`agent/sql_validator.py`](agent/sql_validator.py))**: Every query is parsed using `sqlglot` with the DuckDB dialect. Rejects non-`SELECT` statements, multi-statements, and tables not in the whitelist. CTE aliases are supported.
- **Read-Only Engine**: DuckDB queries in-memory views over immutable Parquet files.
- **Input Sanitization**: Normalizes whitespace and strips dangerous injection patterns.

---

## 5. Development & Deployment

### Local Setup
```bash
# 1. Environment & dependencies
python3 -m venv ls_venv
source ls_venv/bin/activate
pip install -r requirements.txt

# 2. Environment variables (.env)
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.1
GOOGLE_SHEETS_CREDENTIALS_PATH=security/service_account.json
GOOGLE_SHEET_NAME=LS 2.0 Dashboard Staging Table

# 3. Ingestion: Download Google Sheets to versioned Parquet
python -m ingestion.sync_worker

# 4. Run API locally
uvicorn api.main:app --reload --port 8000
```

### Modal Deployment (Serverless)
```bash
# Deploy API backend (ASGI app with persistent volume)
modal deploy modal_app.py

# Trigger remote data sync from Google Sheets into Modal volume
modal run modal_app.py::trigger_sync
```

### API Usage
`POST /query`
```json
{
  "question": "What is the latest stock level of BCG vaccine at PHC Kinkinau?"
}
```
**Response:**
```json
{
  "question": "What is the latest stock level of BCG vaccine at PHC Kinkinau?",
  "generated_sql": "SELECT ... FROM scm_vaccines_stock_balance WHERE ...",
  "raw_data": [...],
  "answer": "At PHC Kinkinau in the latest round of LS 2.0, BCG vaccine has a stock balance of..."
}
```

---

*© 2026 Natview Foundation For Technology Innovation (NFTI).*
