from fastapi import APIRouter, Depends
from app.deps.auth import require_user_id
from app.store import ensure_user
from app.models import User as DBUser
from sqlalchemy.orm import Session
from app.db import get_db
from pydantic import BaseModel
from typing import Optional


class ActivateUserRequest(BaseModel):
    username: Optional[str] = None


router = APIRouter()


@router.post("/users/activate")
async def activate_user(request: ActivateUserRequest, user_id: int = Depends(require_user_id)) -> dict:
    u = ensure_user(user_id, request.username)
    return {"status": "ok", "user": {"id": u.id, "is_blocked": u.is_blocked}}

class ProfileUpdate(BaseModel):
    phone: Optional[str] = None
    name: Optional[str] = None
    address: Optional[str] = None
    birth_date: Optional[str] = None


@router.get("/users/me")
async def get_profile(user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> dict:
    u = db.query(DBUser).filter(DBUser.id == user_id).first() or ensure_user(user_id)
    return {"id": u.id, "phone": u.phone, "name": u.name, "address": u.address, "birth_date": u.birth_date}


@router.patch("/users/me")
async def update_profile(payload: ProfileUpdate, user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> dict:
    u = db.query(DBUser).filter(DBUser.id == user_id).first() or ensure_user(user_id)
    if payload.phone is not None:
        u.phone = payload.phone
    if payload.name is not None:
        u.name = payload.name
    if payload.address is not None:
        u.address = payload.address
    if payload.birth_date is not None:
        u.birth_date = payload.birth_date
    db.commit()
    return {"status": "ok"}

