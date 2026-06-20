"""GET /api/history — paginated broadcast log."""
from fastapi import APIRouter, Depends, Query

from api.auth import verify_api_secret
import database as db_module

router = APIRouter()


@router.get("/api/history", dependencies=[Depends(verify_api_secret)])
def get_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> dict:
    total, results = db_module.get_history(page=page, per_page=per_page)
    return {"total": total, "page": page, "per_page": per_page, "results": results}
