"""FastAPI application entry point."""

from fastapi import FastAPI

from dataforge.api.routes.health import router as health_router

app = FastAPI(title="DataForge Simulator", version="0.1.0")
app.include_router(health_router)
