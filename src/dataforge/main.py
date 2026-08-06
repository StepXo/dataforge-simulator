"""FastAPI application entry point."""

from fastapi import FastAPI

from dataforge.api.routes.health import router as health_router
from dataforge.api.routes.simulations import router as simulations_router

app = FastAPI(title="DataForge Simulator", version="0.1.0")
app.include_router(health_router)
app.include_router(simulations_router)
