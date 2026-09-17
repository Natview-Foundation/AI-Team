"""
FastAPI dependency injection module.
"""

from agent.constants import _ENTITIES

def get_entities() -> dict:
    """
    Returns the loaded entities reference.
    Can be used by routes if they need access to the raw entity data.
    """
    return _ENTITIES
