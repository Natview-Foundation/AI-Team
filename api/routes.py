"""
FastAPI routing logic for the longitudinal_study project.
Implements the core pipeline via LangGraph.
"""

from collections import deque
from fastapi import APIRouter, HTTPException
import time
import logging

from api.schemas import QueryRequest, QueryResponse, HealthResponse
from core.security import normalize_question
from agent.graph import app

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Short-term conversation memory (last 5 Q&A turns) ──
# This gives the MasterRouter context for follow-up questions.
_conversation_history: deque = deque(maxlen=5)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic API health check."""
    return {"status": "healthy", "message": "LS AI Database Agent API is online (Multi-Agent)."}


@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Core Text-to-SQL endpoint.
    1. Normalize question
    2. Invoke LangGraph multi-agent pipeline (with conversation history)
    3. Return structured response
    4. Save Q&A to short-term memory for follow-up context
    """
    pipeline_start = time.time()
    logger.info(f"\n{'='*50}\n  PIPELINE START: '{request.question}'\n{'='*50}")

    # Step 1: Normalize
    clean_question = normalize_question(request.question)
    
    # Step 2: Invoke LangGraph with conversation history
    try:
        t0 = time.time()
        result = app.invoke({
            "question": clean_question,
            "conversation_history": list(_conversation_history)
        })
        
        answer = result.get("answer", "No answer generated.")
        
        # Aggregate SQL and raw data from all sub-agents for the response payload
        sub_agent_results = result.get("sub_agent_results", [])
        
        # We join all generated SQLs so the frontend can see what queries were executed
        all_sqls = "\n\n".join([f"-- [{res['table_name']}]\n{res.get('sql', 'Failed')}" for res in sub_agent_results])
        
        # Combine all row lists into one large list for the raw_data payload
        all_raw_data = []
        for res in sub_agent_results:
            if res.get("rows"):
                all_raw_data.extend(res["rows"])
                
        logger.info(f"[Graph Pipeline] Completed in {time.time() - t0:.2f}s")

        # Step 3: Save to conversation memory for follow-up context
        _conversation_history.append({
            "question": clean_question,
            "answer": answer,
            "tables_used": [res["table_name"] for res in sub_agent_results]
        })
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    total_time = time.time() - pipeline_start
    logger.info(f"\n{'='*50}\n  PIPELINE COMPLETE in {total_time:.2f}s\n{'='*50}\n")
    
    return QueryResponse(
        question=request.question,
        generated_sql=all_sqls,
        raw_data=all_raw_data,
        answer=answer
    )
