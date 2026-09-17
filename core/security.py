"""
Security and input sanitization utilities.
"""

import re

def normalize_question(question: str) -> str:
    """
    Normalizes the user's natural language question.
    - Converts to lowercase
    - Strips leading/trailing whitespace
    - Collapses multiple spaces
    - Removes potentially harmful or extremely weird characters while keeping alphanumeric and basic punctuation
    """
    if not question:
        return ""
        
    q = question.lower().strip()
    
    # Remove multiple spaces
    q = re.sub(r'\s+', ' ', q)
    
    # We want to keep letters, numbers, spaces, and basic punctuation (?,.-)
    # This prevents users from trying to inject weird control characters
    q = re.sub(r'[^\w\s\?\.,\-]', '', q)
    
    return q
