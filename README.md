# Longitudinal Study (LS) — AI Data Query Agent

> **Scope Notice:** This codebase currently covers the **Baseline Sheet** of the Longitudinal Study data pipeline only. Additional sheets (e.g., Follow-up rounds, Supplementary modules) will be integrated as the project expands. See [Future Sheets Integration](#future-sheets-integration) for the planned roadmap.

---

**Organization:** Natview Foundation For Technology Innovation (NFTI)  
**Platform:** Kaduna State Health Facility Assessment — Longitudinal Study (HEFA-LS)  
**Backend Deployment:** [Modal](https://modal.com/) (Serverless)  
**Frontend:** Streamlit  

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture Overview](#architecture-overview)
3. [Project Structure](#project-structure)
4. [Core Pipeline](#core-pipeline)
   - [Step 1 — Question Normalization](#step-1--question-normalization)
   - [Step 2 — Entity Resolution & SQL Generation (Agent 1)](#step-2--entity-resolution--sql-generation-agent-1)
   - [Step 3 — SQL Validation](#step-3--sql-validation)
   - [Step 4 — Database Execution (DuckDB)](#step-4--database-execution-duckdb)
   - [Step 5 — Natural Language Synthesis (Agent 2)](#step-5--natural-language-synthesis-agent-2)
5. [Data Ingestion Pipeline](#data-ingestion-pipeline)
6. [Database Layer](#database-layer)
7. [Security Model](#security-model)
8. [Deployment](#deployment)
   - [Local Development](#local-development)
   - [Modal (Serverless Cloud)](#modal-serverless-cloud)
9. [Configuration & Environment Variables](#configuration--environment-variables)
10. [Technology Stack](#technology-stack)
11. [Current Scope: Baseline Sheet](#current-scope-baseline-sheet)
12. [Future Sheets Integration](#future-sheets-integration)

---

## Project Overview

The Longitudinal Study AI Agent is a **Natural Language to SQL (NL2SQL)** backend that allows non-technical health stakeholders — including field officers, administrators, and analysts — to query complex, multi-round primary healthcare survey data using plain English questions.

The system is built on top of survey data collected across **~130 Primary Health Centres (PHCs)** spread across multiple **Local Government Areas (LGAs)** and **Wards** in Kaduna State, Nigeria. Data is collected in rounds over time (LS 1.0, LS 2.0) and organized by week, enabling longitudinal trend analysis.

### Key Capabilities

- **Natural Language Queries** — Ask questions like *"How many staff does PHC Barnawa have?"* or *"Which facilities had functional refrigerators in the latest week?"*
- **Automatic Entity Resolution** — Fuzzy matching resolves informal facility/LGA/ward names to canonical identifiers.
- **Temporal-Aware SQL** — Automatically selects the correct LS version, round, and week based on which data columns are queried.
- **Self-Healing Retry Loop** — If a generated query fails at execution, the error is fed back to the LLM for automatic correction.
- **Read-Only Security Enforcement** — A two-stage SQL validator (regex + AST) prevents any destructive or modifying queries from ever reaching the database.
- **Streamlit Frontend** — A conversational chat interface for easy interaction.

---

## Architecture Overview

```
User Question (Natural Language)
        │
        ▼
┌───────────────────────────────┐
│  Step 1: Normalization        │
│  core/security.py             │
│  (Sanitize & clean input)     │
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│  Step 2: Agent 1 — Entity Resolver +      │
│          SQL Generator                    │
│  agent/entity_resolver_sql_agent.py       │
│                                           │
│  • Fuzzy-matches facility / LGA / ward    │
│  • Generates DuckDB-compatible SQL        │
│  • Injects column-group defaults          │
│    (Round, Week, LS version)              │
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  Step 3: SQL Validation       │
│  agent/sql_validator.py       │
│                               │
│  • sqlglot AST parsing        │
│  • SELECT-only enforcement    │
│  • Table whitelist check      │
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│  Step 4: Database Execution               │
│  core/database.py                         │
│                                           │
│  • In-memory DuckDB query                 │
│  • Reads Parquet files (latest version)   │
│  • 1x auto-retry on failure via LLM       │
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  Step 5: Agent 2 — Responder  │
│  agent/responder.py           │
│                               │
│  • Synthesizes natural        │
│    language answer from rows  │
│  • Hides SQL/technical detail │
└───────────────────────────────┘
        │
        ▼
Conversational English Response
```

---

## Project Structure

```
longitudinal_study/
│
├── agent/                          # AI agent modules
│   ├── constants.py                # All LLM prompts, entity lists, column schemas, few-shot examples
│   ├── entity_resolver_sql_agent.py# Agent 1: Entity resolution + SQL generation (single LLM call)
│   ├── responder.py                # Agent 2: Natural language synthesis from query results
│   ├── sql_validator.py            # sqlglot-based AST SQL safety validator
│   └── llm.py                     # LLM client singleton factory (OpenAI)
│
├── api/                            # FastAPI application
│   ├── main.py                     # App factory, startup/shutdown lifecycle hooks
│   ├── routes.py                   # Core /query and /health endpoints
│   ├── schemas.py                  # Pydantic request/response models
│   └── dependencies.py             # Shared FastAPI dependencies
│
├── core/                           # Core infrastructure
│   ├── database.py                 # DuckDB connection management & Parquet view registration
│   └── security.py                 # Input sanitization (normalize_question)
│
├── ingestion/                      # Data ingestion pipeline
│   ├── sheets_client.py            # Google Sheets API client (fetch raw data as DataFrame)
│   ├── sync_worker.py              # Full sync orchestrator: Fetch → Validate → Write Parquet → Reload
│   └── validators.py               # DataFrame schema validators (column presence, type checks)
│
├── data/
│   ├── current/                    # Versioned Parquet snapshots (e.g., 2026-08-11-153022/)
│   └── reference/
│       └── entities.json           # Canonical entity lists: LGAs, facilities, wards, column schema
│
├── security/
│   └── service_account.json        # Google Sheets service account credentials (not committed)
│
├── streamlit_app/
│   ├── app.py                      # Streamlit chat frontend
│   └── requirements.txt            # Streamlit-specific dependencies
│
├── config.py                       # Central configuration loader (paths, env vars, constants)
├── modal_app.py                    # Modal serverless deployment definition
├── requirements.txt                # Python dependencies
├── test_pipeline.py                # Integration test script for the full pipeline
└── .env                            # Local environment variables (not committed)
```

---

## Core Pipeline

### Step 1 — Question Normalization

**Module:** `core/security.py`

The raw user question is passed through `normalize_question()`, which:
- Strips leading/trailing whitespace.
- Collapses multiple internal spaces.
- Applies any additional sanitization to prevent prompt injection.

---

### Step 2 — Entity Resolution & SQL Generation (Agent 1)

**Module:** `agent/entity_resolver_sql_agent.py`  
**Prompt source:** `agent/constants.py` → `ENTITY_SQL_SYSTEM_PROMPT`

This is the core intelligence step. A single LLM call performs **two tasks simultaneously**:

#### Task 1 — Entity Resolution

The agent receives the complete canonical lists of all valid:
- **LGAs** (e.g., `chikun`, `kaduna_south`)
- **Facilities** (e.g., `phc_barnawa`, `hc_kudenda`)
- **Wards** (e.g., `barnawa`, `kakuri_hausa`)

It uses semantic fuzzy matching to resolve informal names in the user's question to exact canonical identifiers. For example:
- `"kinkinau"` → `phc_kinkinau`
- `"gwanda hc"` → `hc_gwanda_bomo`
- `"barnawa ward"` → ward: `barnawa`

#### Task 2 — SQL Generation

The agent generates a **DuckDB-compatible `SELECT` query** against the `survey` table, using only columns from the verified whitelist.

**Key rules enforced in the prompt:**

| Rule | Detail |
|------|--------|
| **Column-group defaults** | OPERATIONS & STAFFING columns → `LS 2.0, Round 1`. REFERRAL & COMMUNITY STRUCTURES → `LS 1.0, Round 1`. All others → latest week of `LS 2.0`. |
| **Exclude Not Applicable** | All filters must exclude `-1` values (sentinel for "Not Applicable"). |
| **Aggregation logic** | Boolean/flag columns → `COUNT(DISTINCT facility)`. Numeric columns → `SUM(CAST(...))`. |
| **Broad queries** | Profile/overview requests use `SELECT *` to avoid column hallucination. |

The agent returns a single JSON object:
```json
{
  "resolved_entities": { "lga": "chikun", "facility": "phc_barnawa", "ward": null },
  "sql": "SELECT facility, staffs_number FROM survey WHERE ..."
}
```

#### Few-Shot Examples

`constants.py` includes **8 curated few-shot examples** covering the main query patterns (staffing, operations, boolean counts, service profiles, longitudinal trends, explicit round selection).

---

### Step 3 — SQL Validation

**Module:** `agent/sql_validator.py`

Every generated SQL query passes through a two-stage deterministic validator before touching the database:

| Stage | Check | Detail |
|-------|-------|--------|
| **1. AST Parsing** | `sqlglot.parse(sql, read="duckdb")` | Fails if SQL cannot be parsed at all. |
| **2. Single Statement** | `len(statements) == 1` | Blocks batch injection attacks (e.g., `SELECT 1; DROP TABLE ...`). |
| **3. SELECT Only** | `isinstance(statement, exp.Select)` | Rejects INSERT, UPDATE, DELETE, DROP, ALTER, etc. |
| **4. Table Whitelist** | All referenced tables must be `survey` | Prevents cross-table data exfiltration. |

If validation fails, the request is immediately rejected with HTTP `400` and the reason is returned. **The retry loop is not triggered for security failures** — only for execution errors.

---

### Step 4 — Database Execution (DuckDB)

**Module:** `core/database.py`

The validated SQL is executed against an **in-memory DuckDB connection** that reads from Parquet files stored on disk (or on a Modal persistent Volume in production).

**Versioned Data Loading:**  
On startup (and after each successful sync), `refresh_database()` scans `data/current/` for the latest timestamped directory and registers all `.parquet` files in it as a DuckDB view named `survey`.

```
data/current/
├── 2026-08-10-093000/
│   └── data.parquet        ← older snapshot
└── 2026-09-17-142205/
    └── data.parquet        ← ← latest (active)
```

**Retry Loop:**  
If execution fails (e.g., due to a hallucinated column that passed validation), the system triggers a single automated retry:
1. The error message + failed SQL → fed back to the LLM via `retry_sql_generation()`.
2. A corrected SQL is generated.
3. The corrected SQL passes through the full validator again.
4. Maximum **1 retry** per request to prevent infinite loops.

---

### Step 5 — Natural Language Synthesis (Agent 2)

**Module:** `agent/responder.py`  
**Prompt source:** `agent/constants.py` → `RESPONSE_SYNTHESIS_PROMPT`

The raw list-of-dicts from DuckDB is passed to Agent 2, which synthesizes a clear, professional, conversational English answer. The agent is strictly instructed to:
- Use only data from the actual results (no inference or fabrication).
- Summarize large result sets rather than listing every row.
- **Never mention SQL, database tables, column names, or JSON keys** to the end user.
- Handle empty result sets gracefully.

---

## Data Ingestion Pipeline

**Modules:** `ingestion/sheets_client.py`, `ingestion/sync_worker.py`, `ingestion/validators.py`

The system's data source is a **Google Sheets staging table** that receives data from the field survey tools. The ingestion pipeline runs on-demand and follows these steps:

```
Google Sheets (Source)
        │
        │  gspread (service account auth)
        ▼
1. Fetch — sheets_client.fetch_sheet_data()
   → Returns a Pandas DataFrame
        │
        ▼
2. Validate — validators.validate_dataframe()
   → Checks required columns, data types, sentinel values
   → Aborts sync if errors found (warnings are logged but do not block)
        │
        ▼
3. Write Parquet — sync_worker.run_sync()
   → Creates a new timestamped version directory under data/current/
   → Writes data.parquet (columnar, efficient for DuckDB reads)
        │
        ▼
4. Reload Database — database.refresh_database()
   → DuckDB view is re-registered to point to the new Parquet snapshot
```

**Triggering a Sync (Locally):**
```bash
python -m ingestion.sync_worker
```

**Triggering a Sync (Modal):**
```bash
modal run modal_app.py::trigger_sync
```

> **Note:** After a Modal sync, `data_volume.commit()` is called automatically to make the new Parquet files visible to all running FastAPI instances.

---

## Database Layer

**Module:** `core/database.py`

The project uses **DuckDB** as its query engine — an in-process, columnar SQL database optimized for analytical workloads over Parquet files.

| Aspect | Detail |
|--------|--------|
| **Engine** | DuckDB (in-memory, embedded) |
| **Storage format** | Parquet (columnar, compressed) |
| **Table name** | `survey` (configured in `config.py`) |
| **Versioning** | Timestamped directories under `data/current/` |
| **Connection lifecycle** | Initialized on FastAPI startup, closed on shutdown |

### The `survey` Table Schema

The `survey` table contains one row per facility per survey week/round. Key column groups (all stored in the Parquet file):

| Column Group | Examples | Notes |
|---|---|---|
| **Geography** | `lga`, `ward`, `facility` | Canonical snake_case identifiers |
| **Operations** | `Hours_of_Operations_24`, `days_in_week_routinely_open_7` | LS 2.0, Round 1 only |
| **Staffing** | `staffs_number`, `permanent_staffs_number`, `adhoc_a_staffs_number` | LS 2.0, Round 1 only |
| **Cold Chain (CCE)** | `cces_vaccines_storage_yes`, `refrigerators_functionality_yes` | Boolean: `1`/`0`/`-1` |
| **Workforce Training** | `Healthcare_Workforce_Training_imci`, `_malaria`, `_bemonc` | Boolean flags |
| **Services** | `Services_offered_at_PHFs_immunization`, `_antenatal_services` | Boolean flags |
| **Service Days** | `immunization_service_day`, `antenatal_services_service_day` | Day of week |
| **Transportation** | `Transportation Availability for Emergency Referral_yes_...` | Boolean flags |
| **Referral** | `referral_service_yes`, `referral_type_primary` | LS 1.0 only |
| **Community Structures** | `functional_community_structures_yes` | LS 1.0 only |
| **Metadata** | `LS`, `Week`, `Round`, `Round_No`, `start`, `key` | Temporal identifiers |

> **Sentinel Values:** `-1` = Not Applicable. All aggregation queries must filter this out.

---

## Security Model

Security is enforced at multiple independent layers:

### 1. Input Sanitization
`core/security.py` normalizes and cleans all user input before it reaches the LLM.

### 2. SQL AST Validation (Primary Gate)
`agent/sql_validator.py` uses `sqlglot` to parse the generated SQL into an Abstract Syntax Tree (AST) and enforces:
- **Single statement only** — prevents batch injection.
- **SELECT-only root node** — rejects all DDL and DML.
- **Table whitelist** — queries may only reference the `survey` table.

### 3. Prompt Confinement
The LLM system prompt (in `constants.py`) explicitly forbids the generation of any non-SELECT statements. This acts as a first line of defence before the AST validator.

### 4. Read-Only DuckDB
The DuckDB connection is used solely for reads. The application has no write path to the database (Parquet files are written by the separate ingestion pipeline, not by the query API).

### 5. Secret Management
- **Local:** All secrets live in `.env` (not committed to version control — see `.gitignore`).
- **Production (Modal):** Secrets are managed via `modal.Secret.from_name("ls-secrets")` — never baked into the container image.

---

## Deployment

### Local Development

**Prerequisites:**
- Python 3.11+
- A populated `data/current/` directory with at least one versioned Parquet snapshot.

**Setup:**

```bash
# 1. Clone the repository and enter the project directory
cd longitudinal_study

# 2. Create and activate a virtual environment
python -m venv ls_venv
source ls_venv/bin/activate       # Linux/macOS
# ls_venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your actual OPENAI_API_KEY and Google Sheets credentials

# 5. Run a data sync to populate the local database
python -m ingestion.sync_worker

# 6. Start the FastAPI server
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Run the Streamlit frontend:**

```bash
cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

**Run the integration test:**

```bash
python test_pipeline.py
```

---

### Modal (Serverless Cloud)

The production backend runs on [Modal](https://modal.com/) as a serverless ASGI application. The full deployment configuration is defined in [`modal_app.py`](modal_app.py).

**Infrastructure:**

| Resource | Detail |
|---|---|
| **Image** | `debian_slim` (Python 3.11) with all `requirements.txt` packages |
| **Persistent Volume** | `ls-data-volume` — stores versioned Parquet files across deployments |
| **Secrets** | `ls-secrets` — injects `OPENAI_API_KEY` and other sensitive variables |
| **Warm instances** | `min_containers=1` — keeps one instance alive to eliminate cold starts |

**Deploy the API:**

```bash
modal deploy modal_app.py
```

**Trigger a remote data sync:**

```bash
modal run modal_app.py::trigger_sync
```

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check — returns `{"status": "healthy"}` |
| `POST` | `/query` | Main NL-to-SQL endpoint |

**`POST /query` — Request Body:**
```json
{
  "question": "How many facilities in Chikun have functional refrigerators?"
}
```

**`POST /query` — Response Body:**
```json
{
  "question": "How many facilities in Chikun have functional refrigerators?",
  "generated_sql": "SELECT COUNT(DISTINCT facility) AS facility_count FROM survey WHERE ...",
  "raw_data": [{"facility_count": 14}],
  "answer": "In the latest week of LS 2.0, 14 facilities in Chikun LGA have functional refrigerators."
}
```

---

## Configuration & Environment Variables

All configuration is centralized in [`config.py`](config.py), which reads from `.env` at startup.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key for all LLM calls |
| `OPENAI_MODEL` | `gpt-5.1` | Model used by Agent 1 and Agent 2 |
| `LLM_TEMPERATURE` | `0` | LLM temperature — `0` for deterministic SQL generation |
| `GOOGLE_SHEETS_CREDENTIALS_PATH` | *(required for sync)* | Absolute path to the service account JSON file |
| `GOOGLE_SHEET_NAME` | `LS 2.0 Dashboard Staging Table` | Name of the Google Sheet to pull from |
| `DATA_VOLUME_PATH` | *(Modal only)* | Overrides local `data/current/` path in production |
| `API_HOST` | `0.0.0.0` | FastAPI bind address |
| `API_PORT` | `8000` | FastAPI port |

**`.env` example:**
```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.1
LLM_TEMPERATURE=0
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/security/service_account.json
GOOGLE_SHEET_NAME=LS 2.0 Dashboard Staging Table
```

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **LLM Orchestration** | LangChain Core, LangChain OpenAI | Agent chain composition, prompt management |
| **LLM** | OpenAI GPT-5.1 | Entity resolution, SQL generation, response synthesis |
| **Backend Framework** | FastAPI, Uvicorn, Python 3.11 | Async HTTP API server |
| **Query Engine** | DuckDB | In-process analytics over Parquet files |
| **Data Format** | Apache Parquet (via PyArrow + Pandas) | Columnar data storage |
| **SQL Validation** | sqlglot | AST-based SQL safety enforcement |
| **Data Ingestion** | gspread, google-auth | Google Sheets API integration |
| **Data Processing** | Pandas | DataFrame manipulation and validation |
| **Frontend** | Streamlit | Conversational chat UI |
| **Deployment** | Modal (serverless) | Cloud hosting with persistent volumes |
| **Configuration** | python-dotenv | Environment variable management |

---

## Current Scope: Baseline Sheet

> ⚠️ **This codebase currently operates on the Baseline Sheet of the Longitudinal Study only.**

The `survey` table served by DuckDB is populated from a **single Google Sheet** (`LS 2.0 Dashboard Staging Table`) which represents the **Baseline Sheet** of the full Longitudinal Study instrument. This sheet contains data collected across LS 1.0 and LS 2.0 rounds, covering the following domains:

| Domain | Coverage | LS Version |
|---|---|---|
| Facility Operations (hours open, days open) | ✅ Implemented | LS 2.0, Round 1 |
| Staffing (permanent, ad-hoc, volunteer) | ✅ Implemented | LS 2.0, Round 1 |
| Cold Chain Equipment (CCE functionality) | ✅ Implemented | All weeks |
| Healthcare Workforce Training | ✅ Implemented | All weeks |
| Services Offered at PHFs | ✅ Implemented | All weeks |
| Service Days | ✅ Implemented | All weeks |
| Transportation & Emergency Referral | ✅ Implemented | All weeks |
| Referral Services & Types | ✅ Implemented | LS 1.0, Round 1 |
| Functional Community Structures | ✅ Implemented | LS 1.0, Round 1 |

All agent prompts, entity schemas, column whitelists, and few-shot examples in `agent/constants.py` are currently scoped to match this single sheet's structure.

---

## Future Sheets Integration

As the Longitudinal Study expands, additional Google Sheets capturing supplementary data modules will be integrated into this system. The planned expansion path is:

```
Phase 1 (Current) — Baseline Sheet
  └── survey table (single Parquet source)
       └── Covers: Operations, Staffing, CCE, Training,
                  Services, Service Days, Transportation,
                  Referral, Community Structures

Phase 2 (Planned) — Additional Module Sheets
  ├── Drugs & Pharmaceuticals Sheet      → drugs table
  ├── Equipment & Infrastructure Sheet  → equipment table
  ├── Funding & Finance Sheet           → funding table
  └── Reporting & NHMIS Sheet           → reporting table

Phase 3 (Planned) — Cross-Sheet Query Support
  └── Multi-table DuckDB joins across all module tables
      (e.g., "Which facilities have poor funding AND low staffing?")
```

### Developer Checklist for Adding a New Sheet

When a new sheet is ready to be integrated, the following isolated, additive changes are required — **no modifications to the core pipeline or security layer are needed**:

| File | Change Required |
|---|---|
| `ingestion/sheets_client.py` | Add a `fetch_<module>_sheet_data()` function targeting the new sheet name |
| `ingestion/sync_worker.py` | Add a sync path that writes the new sheet's data to a separate Parquet file |
| `core/database.py` | Register the new Parquet as an additional DuckDB view/table |
| `data/reference/entities.json` | Add the new table's column schema under a new category key |
| `agent/constants.py` | Add the new column group to `COLUMN_CATEGORIES`, update the system prompt, add few-shot examples for the new domain |
| `agent/sql_validator.py` | Add the new table name to the table whitelist |
| `config.py` | Add a `GOOGLE_SHEET_NAME_<MODULE>` environment variable |
| `.env` | Set the value of the new environment variable |

This modular design ensures that each new sheet integration is **self-contained and backwards-compatible** with all existing Baseline Sheet queries.

---

## Contributing

This project is maintained by the **Natview Foundation For Technology Innovation (NFTI)** team. For questions, issues, or contributions related to the Longitudinal Study platform, please contact the project lead.

---

*© 2026 Natview Foundation For Technology Innovation (NFTI). All rights reserved.*
