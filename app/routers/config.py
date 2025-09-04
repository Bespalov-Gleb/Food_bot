from fastapi import APIRouter
from app.services.telegram import SUPPORT_TG_URL


router = APIRouter()


@router.get("/config")
async def get_config() -> dict:
    return {
        "support_tg_url": SUPPORT_TG_URL,
    }

