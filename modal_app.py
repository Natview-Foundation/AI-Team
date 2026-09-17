"""
Modal Deployment Script for the Longitudinal Study NL-to-SQL backend.
Run with: `modal deploy modal_app.py`
"""

import modal
import os
from pathlib import Path

# ─── 1. Image Definition ───
# The project root directory (where this file lives)
project_root = Path(__file__).parent
requirements_path = project_root / "requirements.txt"

app_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements(str(requirements_path))
    .add_local_dir(str(project_root / "agent"), remote_path="/root/agent")
    .add_local_dir(str(project_root / "api"), remote_path="/root/api")
    .add_local_dir(str(project_root / "core"), remote_path="/root/core")
    .add_local_dir(str(project_root / "ingestion"), remote_path="/root/ingestion")
    .add_local_dir(str(project_root / "data" / "reference"), remote_path="/root/data/reference")
    .add_local_dir(str(project_root / "security"), remote_path="/root/security")
    .add_local_file(str(project_root / "config.py"), remote_path="/root/config.py")
    .add_local_file(str(project_root / ".env"), remote_path="/root/.env")
)

# ─── 2. Modal App and Infrastructure ───
app = modal.App("longitudinal-study-api")

# Persistent volume for Parquet files
data_volume = modal.Volume.from_name("ls-data-volume", create_if_missing=True)

# ─── 3. ASGI Application Endpoint ───
@app.function(
    image=app_image,
    volumes={"/data/current": data_volume},
    secrets=[modal.Secret.from_name("ls-secrets")],
    min_containers=1, # Keep one instance warm to prevent cold starts
    # Pass the environment variable to config.py so it knows where the volume is mounted,
    # and override the local .env credentials path with the container's path.
    env={
        "DATA_VOLUME_PATH": "/data/current",
        "GOOGLE_SHEETS_CREDENTIALS_PATH": "/root/security/service_account.json"
    }
)
@modal.asgi_app()
def fastapi_app():
    """
    This function wraps the FastAPI app so Modal can serve it serverlessly.
    """
    import sys
    sys.path.insert(0, "/root")
    from api.main import create_app
    return create_app()

# ─── 4. Sync Worker (Data Ingestion) ───
@app.function(
    image=app_image,
    volumes={"/data/current": data_volume},
    secrets=[modal.Secret.from_name("ls-secrets")],
    timeout=600, # Allow up to 10 minutes for data download and parsing
    env={
        "DATA_VOLUME_PATH": "/data/current",
        "GOOGLE_SHEETS_CREDENTIALS_PATH": "/root/security/service_account.json"
    }
)
def trigger_sync():
    """
    Triggers the Google Sheets ingestion pipeline.
    Run manually via: `modal run modal_app.py::trigger_sync`
    """
    import sys
    sys.path.insert(0, "/root")
    from ingestion.sync_worker import run_sync
    import logging
    
    logging.basicConfig(level=logging.INFO)
    success = run_sync()
    
    if success:
        # Important: Since we wrote to the volume, we must commit the changes
        # so they are visible to the FastAPI instances.
        data_volume.commit()
        print("✅ Sync successful and volume committed.")
    else:
        print("❌ Sync failed.")
