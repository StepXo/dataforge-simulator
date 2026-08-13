"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dataforge.api.routes.analytics import DASHBOARD_DIRECTORY
from dataforge.api.routes.analytics import router as analytics_router
from dataforge.api.routes.export import router as export_router
from dataforge.api.routes.health import router as health_router

app = FastAPI(title="DataForge Simulator", version="0.1.0")
app.include_router(health_router)
app.include_router(export_router)
app.include_router(analytics_router)
app.mount(
    "/analytics/assets",
    StaticFiles(directory=DASHBOARD_DIRECTORY),
    name="analytics-assets",
)
