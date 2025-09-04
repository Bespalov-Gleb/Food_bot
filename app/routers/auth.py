import time
import hmac
import os
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel


router = APIRouter()

SECRET = os.getenv("ADMIN_SITE_SECRET", "dev-secret")


def _sign(data: str) -> str:
    return hmac.new(SECRET.encode(), data.encode(), 'sha256').hexdigest()


@router.post("/auth/external-link")
async def create_external_link(role: str = "super_admin") -> dict:
    if role != "super_admin":
        raise HTTPException(status_code=400, detail="unsupported_role")
    exp = int(time.time()) + 600  # 10 мин
    payload = f"role={role}&exp={exp}"
    token = payload + "&sig=" + _sign(payload)
    return {"token": token}


class ExchangeRequest(BaseModel):
    token: str


@router.post("/auth/exchange")
async def exchange_token(req: ExchangeRequest, response: Response) -> dict:
    try:
        parts = req.token.split("&")
        data = {k: v for k, v in (p.split("=", 1) for p in parts if "=" in p)}
        role = data.get("role")
        exp = int(data.get("exp", "0"))
        sig = data.get("sig", "")
        base = f"role={role}&exp={exp}"
        if _sign(base) != sig or exp < int(time.time()):
            raise ValueError("bad token")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_token")
    # сетим сессионную куку
    response.set_cookie(
        key="admin_session",
        value=req.token,
        httponly=True,
        samesite="Lax",
        secure=True,
        path="/",
    )
    return {"status": "ok"}

