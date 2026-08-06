"""Health-check endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class PingResponse(BaseModel):
    """Response returned by the health-check endpoint."""

    status: Literal["ok"]
    message: Literal["pong"]


@router.get("/ping", response_model=PingResponse)
def ping() -> PingResponse:
    """Confirm that the API process is available."""
    return PingResponse(status="ok", message="pong")
