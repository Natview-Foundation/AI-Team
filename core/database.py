"""
Database execution layer using DuckDB.
"""

import duckdb
from pathlib import Path
import logging

from config import CURRENT_DATA_DIR

logger = logging.getLogger(__name__)

# Global connection object
_con: duckdb.DuckDBPyConnection | None = None


def init_database():
    """
    Initializes the DuckDB connection and registers the latest Parquet data.
    Called on FastAPI startup.
    """
    global _con
    if _con is None:
        _con = duckdb.connect()
        logger.info("DuckDB connection initialized.")
        refresh_database()


def close_database():
    """
    Closes the DuckDB connection.
    Called on FastAPI shutdown.
    """
    global _con
    if _con is not None:
        _con.close()
        _con = None
        logger.info("DuckDB connection closed.")


def refresh_database():
    """
    Finds the latest Parquet directory and registers all parquet files as views.
    Called at startup and after a successful data ingestion sync.
    """
    global _con
    if _con is None:
        return

    # Check if data directory exists
    if not CURRENT_DATA_DIR.exists():
        logger.warning(f"Data directory {CURRENT_DATA_DIR} does not exist yet. Tables not registered.")
        return

    # Find all subdirectories (which are versioned timestamps like 2026-08-11-001)
    dirs = [d for d in CURRENT_DATA_DIR.iterdir() if d.is_dir()]
    
    if not dirs:
        logger.warning(f"No versioned data directories found in {CURRENT_DATA_DIR}. Tables not registered.")
        return
        
    # Sort to get the latest (alphabetically/chronologically)
    latest_dir = sorted(dirs)[-1]
    
    # Look for parquet files inside the latest directory
    parquet_files = list(latest_dir.glob("*.parquet"))
    
    if not parquet_files:
        logger.warning(f"No Parquet files found in {latest_dir}. Tables not registered.")
        return
        
    # Register each parquet file as a view named after its base name
    for pq_path in parquet_files:
        table_name = pq_path.stem  # e.g., "baseline_data_ls1"
        try:
            _con.execute(f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_parquet('{str(pq_path)}')")
            logger.info(f"Successfully registered table '{table_name}' pointing to {pq_path.name}")
        except Exception as e:
            logger.error(f"Failed to register DuckDB view '{table_name}': {e}")


def execute_query(sql: str) -> list[dict]:
    """
    Executes a validated SQL query against DuckDB and returns the rows as a list of dicts.
    """
    global _con
    if _con is None:
        raise RuntimeError("Database connection is not initialized.")
        
    try:
        # df() returns a Pandas DataFrame, which we convert to dicts
        # Alternatively, fetchdf() or fetchall() can be used.
        result_df = _con.execute(sql).df()
        
        # Convert DataFrame to list of dicts
        # orient="records" creates a list of rows
        records = result_df.to_dict(orient="records")
        return records
    except Exception as e:
        # Re-raise so the caller can trigger the LLM retry loop
        raise Exception(f"DuckDB execution failed: {str(e)}")
