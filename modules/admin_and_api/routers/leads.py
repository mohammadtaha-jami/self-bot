"""Leads management endpoints."""

from fastapi import APIRouter

from modules.admin_and_api.schemas import FeedbackCreate, LeadResponse

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("/", response_model=list[LeadResponse])
async def list_leads() -> list[LeadResponse]:
    """Return paginated leads for the authenticated user."""
    # TODO: Query leads from DB with filters
    raise NotImplementedError("List leads endpoint not yet implemented")


@router.post("/{lead_id}/feedback")
async def submit_feedback(lead_id: int, payload: FeedbackCreate) -> dict:
    """Submit quality feedback on a lead."""
    # TODO: Persist feedback and trigger model tuning pipeline
    raise NotImplementedError("Feedback endpoint not yet implemented")
