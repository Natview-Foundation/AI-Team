"""
Orchestrates the ingestion pipeline: Fetch -> Validate -> Write Parquet -> Reload DB.
"""

import datetime
import logging
import json
import traceback
from pathlib import Path
import sys

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import CURRENT_DATA_DIR, ENTITIES_PATH
from ingestion.sheets_client import fetch_sheet_data
from ingestion.validators import validate_dataframe
from core.database import refresh_database

logger = logging.getLogger(__name__)

import shutil

def run_sync(target_tables: list[str] | None = None) -> bool:
    """
    Executes the data synchronization pipeline.
    If target_tables is provided, syncs only those tables and carries forward
    existing parquets from the latest snapshot for the remaining tables.
    If target_tables is None, syncs all tables defined in entities.json.
    Returns True if successful, False otherwise.
    """
    logger.info("Starting data synchronization pipeline...")
    
    try:
        # Load the entities.json to know which tables to fetch
        with open(ENTITIES_PATH, "r") as f:
            entities = json.load(f)
            
        columns_schema = entities.get("columns", {})
        if not columns_schema:
            logger.error("No tables found in entities.json under 'columns' key.")
            return False
            
        # Create a new versioned directory: e.g., 2026-08-11-153022
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        version_dir = CURRENT_DATA_DIR / timestamp
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # If targeting specific tables, carry forward existing parquets from latest snapshot
        if target_tables:
            dirs = [d for d in CURRENT_DATA_DIR.iterdir() if d.is_dir() and d != version_dir]
            if dirs:
                latest_dir = sorted(dirs)[-1]
                logger.info(f"Carrying forward existing Parquet snapshots from {latest_dir.name}...")
                for src_pq in latest_dir.glob("*.parquet"):
                    dst_pq = version_dir / src_pq.name
                    shutil.copy2(src_pq, dst_pq)

        tables_to_sync = target_tables if target_tables else list(columns_schema.keys())
        success = True
        
        for table_name in tables_to_sync:
            schema = columns_schema.get(table_name)
            if not schema:
                logger.warning(f"Table '{table_name}' not defined in entities.json schema. Skipping.")
                continue

            sheet_name = schema.get("_sheet_name")
            if not sheet_name:
                logger.warning(f"Table '{table_name}' has no '_sheet_name' specified. Skipping.")
                continue
                
            logger.info(f"Processing table: {table_name} (Sheet: {sheet_name})")
            
            # Extract expected columns (all values in schema except keys starting with _)
            expected_columns = []
            for category, cols in schema.items():
                if not category.startswith("_"):
                    expected_columns.extend(cols)
            
            try:
                # 1. Fetch
                df = fetch_sheet_data(sheet_name)
                
                # 2. Validate
                report = validate_dataframe(df, expected_columns)
                
                if report.warnings:
                    for w in report.warnings:
                        logger.warning(f"[{table_name}] Validation Warning: {w}")
                        
                if not report.is_valid:
                    logger.error(f"[{table_name}] Data validation failed! Skipping this table.")
                    for e in report.errors:
                        logger.error(f"[{table_name}] Validation Error: {e}")
                    success = False
                    continue
                    
                logger.info(f"[{table_name}] Data validation passed.")
                
                # 3. Write Parquet
                parquet_path = version_dir / f"{table_name}.parquet"
                df.to_parquet(parquet_path, index=False)
                logger.info(f"[{table_name}] Successfully wrote Parquet file to {parquet_path}")
                
            except Exception as e:
                logger.error(f"[{table_name}] Sync failed: {e}")
                logger.error(traceback.format_exc())
                success = False
        
        # 4. Refresh DuckDB connection so it sees the new data
        refresh_database()
        logger.info("Synchronization pipeline complete.")
        
        return success
        
    except Exception as e:
        logger.error(f"Sync pipeline failed completely: {e}")
        logger.error(traceback.format_exc())
        return False

# If run directly as a script, execute the sync
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    tables = sys.argv[1:] if len(sys.argv) > 1 else None
    run_sync(target_tables=tables)
