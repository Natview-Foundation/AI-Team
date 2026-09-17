"""
FastAPI routing logic for the longitudinal_study project.
Implements the core 4-step pipeline: Normalization -> SQL Gen -> DB Exec -> Responder.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Any

from api.schemas import QueryRequest, QueryResponse, HealthResponse
from core.security import normalize_question
from agent.entity_resolver_sql_agent import resolve_and_generate_sql, retry_sql_generation
from agent.sql_validator import validate_sql
from core.database import execute_query
from agent.responder import synthesize_response


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic API health check."""
    return {"status": "healthy", "message": "LS AI Database Agent API is online."}


@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Core Text-to-SQL endpoint.
    1. Normalize question
    2. Agent 1: Resolve Entities + Generate SQL
    3. Validate SQL (sqlglot)
    4. Execute on DuckDB (with 1 retry loop if failed)
    5. Agent 2: Synthesize NL response
    """
    import time
    pipeline_start = time.time()
    print(f"\n{'='*50}\n  PIPELINE START: '{request.question}'\n{'='*50}")

    # Step 1: Normalize
    clean_question = normalize_question(request.question)
    
    # Step 2: Agent 1 (Entity Resolution & SQL Gen)
    try:
        t0 = time.time()
        agent1_result = resolve_and_generate_sql(clean_question)
        sql = agent1_result.get("sql", "")
        print(f"[STEP 1] Agent 1 completed in {time.time() - t0:.2f}s")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM SQL Generation failed: {str(e)}")

    # Step 3 & 4: Validation and Execution (with retry loop)
    MAX_RETRIES = 1
    raw_results = []
    
    for attempt in range(1 + MAX_RETRIES):
        attempt_label = f"(attempt {attempt + 1}/{1 + MAX_RETRIES})"
        
        # Validate SQL
        is_safe, reason = validate_sql(sql)
        if not is_safe:
            # If the SQL is unsafe, we don't retry, we abort immediately.
            raise HTTPException(status_code=400, detail=f"Query rejected by security validator: {reason}")
            
        print(f"[STEP 2] SQL Validator passed {attempt_label}.")
        
        # Execute DuckDB
        try:
            t0 = time.time()
            raw_results = execute_query(sql)
            print(f"[STEP 3] Database execution successful in {time.time() - t0:.2f}s. Rows returned: {len(raw_results)}")
            break # Success, exit retry loop
            
        except Exception as e:
            error_msg = str(e)
            print(f"[STEP 3] Database execution failed {attempt_label}: {error_msg}")
            
            if attempt < MAX_RETRIES:
                print(f"[STEP 3.5] Triggering Retry Logic...")
                t_retry = time.time()
                # Feed error back to LLM
                agent1_retry_result = retry_sql_generation(clean_question, sql, error_msg)
                sql = agent1_retry_result.get("sql", "")
                print(f"[STEP 3.5] Agent 1 Retry completed in {time.time() - t_retry:.2f}s")
            else:
                raise HTTPException(status_code=500, detail=f"Database execution failed after {1 + MAX_RETRIES} attempts. Error: {error_msg}")

    # Step 5: Agent 2 (Synthesize NL Response)
    try:
        t0 = time.time()
        answer = synthesize_response(clean_question, raw_results)
        print(f"[STEP 4] Agent 2 completed in {time.time() - t0:.2f}s")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM Data Synthesizer failed: {str(e)}")

    total_time = time.time() - pipeline_start
    print(f"\n{'='*50}\n  PIPELINE COMPLETE in {total_time:.2f}s\n{'='*50}\n")
    
    return QueryResponse(
        question=request.question,
        generated_sql=sql,
        raw_data=raw_results,
        answer=answer
    )
