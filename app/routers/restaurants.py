from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Restaurant as ORestaurant


router = APIRouter()


class Restaurant(BaseModel):
    id: int
    name: str
    is_enabled: bool
    rating_agg: float
    delivery_min_sum: int
    delivery_fee: int
    delivery_time_minutes: int
    address: str
    phone: str
    description: str = ""
    image: str = ""
    work_open_min: int = 0  # minutes from 00:00
    work_close_min: int = 1440
    is_open_now: bool = True


_RESTAURANTS: List[Restaurant] = []  # legacy in-memory, оставлено для совместимости импорта


def _compute_is_open(r: Restaurant) -> bool:
    from datetime import datetime
    now = datetime.now().time()
    minutes = now.hour * 60 + now.minute
    if r.work_open_min <= r.work_close_min:
        return r.work_open_min <= minutes < r.work_close_min
    # overnight schedule
    return minutes >= r.work_open_min or minutes < r.work_close_min


@router.get("")
async def list_restaurants(is_enabled: Optional[bool] = True, db: Session = Depends(get_db)) -> List[Restaurant]:
    q = db.query(ORestaurant)
    if is_enabled is not None:
        q = q.filter(ORestaurant.is_enabled == bool(is_enabled))
    rows = q.all()
    items: List[Restaurant] = []
    for r in rows:
        item = Restaurant(
            id=r.id,
            name=r.name,
            is_enabled=r.is_enabled,
            rating_agg=r.rating_agg,
            delivery_min_sum=r.delivery_min_sum,
            delivery_fee=r.delivery_fee,
            delivery_time_minutes=r.delivery_time_minutes,
            address=r.address,
            phone=r.phone,
            description=r.description,
            image=r.image,
            work_open_min=r.work_open_min,
            work_close_min=r.work_close_min,
            is_open_now=_compute_is_open(r),
        )
        items.append(item)
    return items


@router.get("/_bulk")
async def get_restaurants_bulk(ids: str = Query(..., description="comma-separated ids"), db: Session = Depends(get_db)) -> List[Restaurant]:
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except Exception as exc:
        raise RuntimeError("Bad ids") from exc
    rows = db.query(ORestaurant).filter(ORestaurant.id.in_(id_list)).all()
    return [Restaurant(
        id=r.id,
        name=r.name,
        is_enabled=r.is_enabled,
        rating_agg=r.rating_agg,
        delivery_min_sum=r.delivery_min_sum,
        delivery_fee=r.delivery_fee,
        delivery_time_minutes=r.delivery_time_minutes,
        address=r.address,
        phone=r.phone,
        description=r.description,
        image=r.image,
        work_open_min=r.work_open_min,
        work_close_min=r.work_close_min,
        is_open_now=_compute_is_open(r),
    ) for r in rows]


@router.get("/_by-ids")
async def get_restaurants_by_ids(ids: str = Query(..., description="comma-separated ids"), db: Session = Depends(get_db)) -> List[Restaurant]:
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except Exception as exc:
        raise RuntimeError("Bad ids") from exc
    rows = db.query(ORestaurant).filter(ORestaurant.id.in_(id_list)).all()
    return [Restaurant(
        id=r.id,
        name=r.name,
        is_enabled=r.is_enabled,
        rating_agg=r.rating_agg,
        delivery_min_sum=r.delivery_min_sum,
        delivery_fee=r.delivery_fee,
        delivery_time_minutes=r.delivery_time_minutes,
        address=r.address,
        phone=r.phone,
        description=r.description,
        image=r.image,
        work_open_min=r.work_open_min,
        work_close_min=r.work_close_min,
        is_open_now=_compute_is_open(r),
    ) for r in rows]


@router.get("/{restaurant_id}")
async def get_restaurant(restaurant_id: int, db: Session = Depends(get_db)) -> Restaurant:
    r = db.query(ORestaurant).filter(ORestaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return Restaurant(
        id=r.id,
        name=r.name,
        is_enabled=r.is_enabled,
        rating_agg=r.rating_agg,
        delivery_min_sum=r.delivery_min_sum,
        delivery_fee=r.delivery_fee,
        delivery_time_minutes=r.delivery_time_minutes,
        address=r.address,
        phone=r.phone,
        description=r.description,
        image=r.image,
        work_open_min=r.work_open_min,
        work_close_min=r.work_close_min,
        is_open_now=_compute_is_open(r),
    )

