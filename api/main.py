"""
FastAPI application factory and main entrypoint.
Manages lifecycle events (startup/shutdown) for the DuckDB connection.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as api_router
from core.database import init_database, close_database

def create_app() -> FastAPI:
    app = FastAPI(
        title="Longitudinal Study Database Agent",
        description="NL-to-SQL API for querying health facility data using LLMs and DuckDB.",
        version="1.0.0"
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add endpoints
    app.include_router(api_router)

    # Lifecycle events
    @app.on_event("startup")
    async def startup_event():
        init_database()

    @app.on_event("shutdown")
    async def shutdown_event():
        close_database()

    return app

# The ASGI application instance
app = create_app()
