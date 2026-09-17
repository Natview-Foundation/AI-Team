"""
LLM client factory for the longitudinal_study project.

This is the ONLY file that imports langchain_openai.
Every other module that needs an LLM calls get_llm() from here.
"""

from langchain_openai import ChatOpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, LLM_TEMPERATURE


def get_llm() -> ChatOpenAI:
    """
    Returns a configured ChatOpenAI instance.
    
    - temperature=0 for deterministic SQL generation
    - Model and API key are read from config.py (which reads .env)
    """
    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is not set. "
        )
    
    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=LLM_TEMPERATURE,
    )
