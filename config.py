"""
Central configuration loader for the longitudinal_study project.
All environment variables and path constants are resolved here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Resolve project root (this file lives at project root) ───
PROJECT_ROOT = Path(__file__).resolve().parent

# ─── Load .env from project root ───
load_dotenv(PROJECT_ROOT / ".env")

# ─── LLM Configuration ───
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.1")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))

# ─── Data Paths ───
DATA_DIR: Path = PROJECT_ROOT / "data"

# If deployed on Modal, this will be overridden to point to the network Volume
_env_data_path = os.getenv("DATA_VOLUME_PATH")
if _env_data_path:
    CURRENT_DATA_DIR: Path = Path(_env_data_path)
else:
    CURRENT_DATA_DIR: Path = DATA_DIR / "current"
REFERENCE_DIR: Path = DATA_DIR / "reference"
ENTITIES_PATH: Path = REFERENCE_DIR / "entities.json"

# ─── Google Sheets Configuration ───
GOOGLE_SHEETS_CREDENTIALS_PATH: str = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "")
GOOGLE_SHEET_NAME: str = os.getenv("GOOGLE_SHEET_NAME", "LS 2.0 Dashboard Staging Table")

# ─── API ───
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
