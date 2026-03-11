import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.api.routes_health import router as health_router
from src.api.routes_transactions import router as transactions_router
from src.api.routes_review import router as review_router
from src.api.routes_ab import router as ab_router
from src.api.routes_metrics import router as metrics_router
from src.api.routes_dashboard import router as dashboard_router


def create_app() -> FastAPI:
    app = FastAPI(title="Fraud AI Streaming", version="1.0.0")
    app.include_router(health_router)
    app.include_router(transactions_router, prefix="/transactions", tags=["transactions"])
    app.include_router(review_router, prefix="/review", tags=["review"])
    app.include_router(ab_router, prefix="/experiments", tags=["experiments"])
    app.include_router(metrics_router, tags=["metrics"])
    app.include_router(dashboard_router, tags=["dashboard"])

    # Serve frontend static files
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    frontend_dir = os.path.abspath(frontend_dir)
    if os.path.isdir(frontend_dir):
        @app.get("/", include_in_schema=False)
        async def serve_dashboard():
            return FileResponse(os.path.join(frontend_dir, "index.html"))

        app.mount("/static", StaticFiles(directory=frontend_dir), name="frontend")

    return app
