"""
Orchestrates the ingestion pipeline: Fetch -> Validate -> Write Parquet -> Reload DB.
"""

import datetime
import logging
from config import CURRENT_DATA_DIR
from ingestion.sheets_client import fetch_sheet_data
from ingestion.validators import validate_dataframe
from core.database import refresh_database

logger = logging.getLogger(__name__)

def run_sync() -> bool:
    """
    Executes the full data synchronization pipeline.
    Returns True if successful, False otherwise.
    """
    logger.info("Starting data synchronization pipeline...")
    
    try:
        # 1. Fetch
        df = fetch_sheet_data()
        
        # 2. Validate
        report = validate_dataframe(df)
        
        if report.warnings:
            for w in report.warnings:
                logger.warning(f"Validation Warning: {w}")
                
        if not report.is_valid:
            logger.error("Data validation failed! Aborting sync.")
            for e in report.errors:
                logger.error(f"Validation Error: {e}")
            return False
            
        logger.info("Data validation passed.")
        
        # 3. Write Parquet
        # Create a new versioned directory: e.g., 2026-08-11-153022
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        version_dir = CURRENT_DATA_DIR / timestamp
        version_dir.mkdir(parents=True, exist_ok=True)
        
        parquet_path = version_dir / "data.parquet"
        df.to_parquet(parquet_path, index=False)
        logger.info(f"Successfully wrote Parquet file to {parquet_path}")
        
        # 4. Refresh DuckDB connection so it sees the new data
        refresh_database()
        logger.info("Synchronization pipeline complete.")
        
        return True
        
    except Exception as e:
        logger.error(f"Sync pipeline failed: {e}")
        return False

# If run directly as a script, execute the sync
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_sync()
