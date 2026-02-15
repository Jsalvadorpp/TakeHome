"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    """Health check endpoint.

    Returns:
        {"ok": True}
    """
    return {"ok": True}
