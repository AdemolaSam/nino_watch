from fastapi import APIRouter

from app.api.schemas import OutlookResponse
from app.services.outlooks import load_outlooks

router = APIRouter()


@router.get("/outlooks", response_model=list[OutlookResponse])
def list_outlooks() -> list[OutlookResponse]:
    return [OutlookResponse.model_validate(row) for row in load_outlooks()]
