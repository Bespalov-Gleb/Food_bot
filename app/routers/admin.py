from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.deps.auth import require_super_admin
from app.routers.restaurants import Restaurant
from app.services.telegram import send_admin_message
from app.store import ensure_user, bind_restaurant_admin, unbind_restaurant_admin
from app.models import Review as DBReview
from sqlalchemy.orm import Session
from app.db import get_db
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Depends
from app.db import get_db
from app.models import Restaurant as ORestaurant, User as DBUser, RestaurantAdmin as DBRestaurantAdmin, Order as DBOrder
import os


router = APIRouter(dependencies=[Depends(require_super_admin)])


class RestaurantCreate(BaseModel):
    name: str
    delivery_min_sum: int = 0
    delivery_fee: int = 0
    delivery_time_minutes: int = 60
    address: str = ""
    phone: str = ""


class RestaurantUpdate(BaseModel):
    name: str | None = None
    delivery_min_sum: int | None = None
    delivery_fee: int | None = None
    delivery_time_minutes: int | None = None
    address: str | None = None
    phone: str | None = None
    is_enabled: bool | None = None
    description: str | None = None


class AdminCodeUpdate(BaseModel):
    admin_code: str


@router.get("/restaurants")
async def list_restaurants_admin(db: Session = Depends(get_db)) -> List[Restaurant]:
    rows = db.query(ORestaurant).all()
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
        is_open_now=False,
    ) for r in rows]


@router.post("/restaurants")
async def create_restaurant(payload: RestaurantCreate, db: Session = Depends(get_db)) -> dict:
    # generate id
    last = db.query(ORestaurant).order_by(ORestaurant.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    r = ORestaurant(
        id=new_id,
        name=payload.name,
        is_enabled=False,
        rating_agg=0.0,
        delivery_min_sum=payload.delivery_min_sum,
        delivery_fee=payload.delivery_fee,
        delivery_time_minutes=payload.delivery_time_minutes,
        address=payload.address,
        phone=payload.phone,
    )
    db.add(r)
    db.commit()
    try:
        await send_admin_message(f"[admin] Добавлен ресторан {r.name} (id={new_id})")
    except Exception:
        pass
    return {"id": new_id}


@router.patch("/restaurants/{restaurant_id}")
async def update_restaurant(restaurant_id: int, payload: RestaurantUpdate, db: Session = Depends(get_db)) -> dict:
    r = db.query(ORestaurant).filter(ORestaurant.id == restaurant_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    for num_key in ("delivery_min_sum", "delivery_fee", "delivery_time_minutes"):
        if num_key in patch and isinstance(patch[num_key], str):
            try:
                patch[num_key] = int(patch[num_key])
            except ValueError:
                patch.pop(num_key, None)
    for k, v in patch.items():
        if hasattr(r, k):
            setattr(r, k, v)
    db.commit()
    try:
        await send_admin_message(f"[admin] Обновлён ресторан id={restaurant_id}")
    except Exception:
        pass
    return {"status": "ok", "restaurant": Restaurant(
        id=r.id, name=r.name, is_enabled=r.is_enabled, rating_agg=r.rating_agg,
        delivery_min_sum=r.delivery_min_sum, delivery_fee=r.delivery_fee,
        delivery_time_minutes=r.delivery_time_minutes, address=r.address, phone=r.phone,
        description=r.description, image=r.image, work_open_min=r.work_open_min,
        work_close_min=r.work_close_min, is_open_now=False
    ).model_dump()}


@router.patch("/restaurants/{restaurant_id}/status")
async def set_restaurant_status(restaurant_id: int, enabled: bool, db: Session = Depends(get_db)) -> dict:
    r = db.query(ORestaurant).filter(ORestaurant.id == restaurant_id).first()
    if not r:
        return {"status": "not_found"}
    r.is_enabled = bool(enabled)
    db.commit()
    try:
        await send_admin_message(f"[admin] Ресторан id={restaurant_id} статус={'ON' if enabled else 'OFF'}")
    except Exception:
        pass
    return {"status": "ok"}


@router.delete("/restaurants/{restaurant_id}")
async def delete_restaurant(restaurant_id: int, db: Session = Depends(get_db)) -> dict:
    r = db.query(ORestaurant).filter(ORestaurant.id == restaurant_id).first()
    if not r:
        return {"status": "not_found"}
    db.delete(r)
    db.commit()
    try:
        await send_admin_message(f"[admin] Удалён ресторан id={restaurant_id}")
    except Exception:
        pass
    return {"status": "ok"}


class Broadcast(BaseModel):
    text: str


@router.post("/broadcast")
async def broadcast(payload: Broadcast) -> dict:
    try:
        await send_admin_message(f"[broadcast] {payload.text}")
    except Exception:
        pass
    return {"status": "ok"}


# users management
@router.get("/users")
async def list_users(db: Session = Depends(get_db)) -> List[dict]:
    users = db.query(DBUser).all()
    admin_rows = db.query(DBRestaurantAdmin).all()
    admin_map = {r.user_id: r.restaurant_id for r in admin_rows}
    out: List[dict] = []
    for u in users:
        out.append({
            "id": u.id,
            "username": u.username,
            "is_blocked": u.is_blocked,
            "phone": u.phone,
            "name": u.name,
            "address": u.address,
            "birth_date": u.birth_date,
            "created_at": u.created_at,
            "restaurant_admin_of": admin_map.get(u.id),
        })
    return out


@router.post("/users/block")
async def block_user(user_id: int, block: bool = True, db: Session = Depends(get_db)) -> dict:
    u = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not u:
        # создаём пользователя при блокировке, если он ещё не активировался
        ensure_user(user_id)
        u = db.query(DBUser).filter(DBUser.id == user_id).first()
    if u:
        u.is_blocked = block
        db.commit()
    try:
        await send_admin_message(f"[admin] Пользователь {user_id} {'заблокирован' if block else 'разблокирован'}")
    except Exception:
        pass
    return {"status": "ok", "user": {
        "id": u.id if u else user_id,
        "is_blocked": u.is_blocked if u else block,
    }}


@router.get("/users/resolve-username")
async def resolve_username_endpoint(username: str) -> dict:
    """Разрешает username в user_id через Telegram Bot API"""
    from app.services.telegram import resolve_username_to_user_id
    user_id = await resolve_username_to_user_id(username)
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id}

@router.post("/users/bind-admin")
async def make_restaurant_admin(user_id: int, restaurant_id: int, db: Session = Depends(get_db)) -> dict:
    bind_restaurant_admin(user_id, restaurant_id)
    return {"status": "ok"}


@router.post("/users/unbind-admin")
async def revoke_restaurant_admin(user_id: int) -> dict:
    unbind_restaurant_admin(user_id)
    return {"status": "ok"}


@router.get("/restaurant-admins")
async def list_restaurant_admins(db: Session = Depends(get_db)) -> List[dict]:
    """Получить список всех администраторов ресторанов"""
    admin_rows = db.query(DBRestaurantAdmin).all()
    result = []
    for admin in admin_rows:
        user = db.query(DBUser).filter(DBUser.id == admin.user_id).first()
        restaurant = db.query(ORestaurant).filter(ORestaurant.id == admin.restaurant_id).first()
        result.append({
            "user_id": admin.user_id,
            "username": user.username if user else None,
            "restaurant_id": admin.restaurant_id,
            "restaurant_name": restaurant.name if restaurant else None
        })
    return result


# statistics
def _in_same_day(a: datetime, b: datetime) -> bool:
    return a.date() == b.date()


def _in_same_month(a: datetime, b: datetime) -> bool:
    return a.year == b.year and a.month == b.month


def _aggregate(orders, now: datetime) -> dict:
    def summarize(filter_fn):
        filtered = [o for o in orders if filter_fn(o)]
        return {
            "orders": len(filtered),
            "sum": sum(o.total_price for o in filtered),
            "cancelled": sum(1 for o in filtered if o.status == "cancelled"),
            "modified": sum(1 for o in filtered if o.status == "modified"),
        }
    return {
        "today": summarize(lambda o: _in_same_day(o.created_at, now)),
        "month": summarize(lambda o: _in_same_month(o.created_at, now)),
    }


@router.get("/stats")
async def stats_global(db: Session = Depends(get_db)) -> dict:
    now = datetime.utcnow()
    orders = db.query(DBOrder).all()
    return _aggregate(orders, now)


@router.get("/stats/by-restaurant")
async def stats_by_restaurant(restaurant_id: int, db: Session = Depends(get_db)) -> dict:
    now = datetime.utcnow()
    subset = db.query(DBOrder).filter(DBOrder.restaurant_id == restaurant_id).all()
    return _aggregate(subset, now)


@router.get("/stats/users")
async def stats_users(db: Session = Depends(get_db)) -> dict:
    now = datetime.utcnow()
    
    # Общее количество пользователей
    total_users = db.query(DBUser).count()
    
    # Заблокированные пользователи
    blocked_users = db.query(DBUser).filter(DBUser.is_blocked == True).count()
    
    # Новые пользователи за месяц
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    unique_users_month = db.query(DBUser).filter(DBUser.created_at >= month_start).count()
    
    # Новые пользователи за сегодня
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    unique_users_today = db.query(DBUser).filter(DBUser.created_at >= today_start).count()
    
    # Посещения за месяц (активность пользователей)
    visits_month = db.query(DBUser).filter(DBUser.last_activity >= month_start).count()
    
    # Посещения за сегодня
    visits_today = db.query(DBUser).filter(DBUser.last_activity >= today_start).count()
    
    return {
        "total_users": total_users,
        "blocked_users": blocked_users,
        "unique_users_month": unique_users_month,
        "unique_users_today": unique_users_today,
        "visits_month": visits_month,
        "visits_today": visits_today
    }


@router.get("/stats/restaurants")
async def stats_restaurants(db: Session = Depends(get_db)) -> dict:
    restaurants = db.query(ORestaurant).all()
    return {
        "restaurants": [
            {
                "id": r.id,
                "name": r.name,
                "is_enabled": r.is_enabled
            }
            for r in restaurants
        ]
    }


# reviews (простая модерация)
from dataclasses import dataclass, field


@dataclass
class Review:
    id: int
    order_id: int
    restaurant_id: int
    user_id: int
    rating: int
    comment: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    is_deleted: bool = False


_REVIEWS: list[Review] = []
_REV_SEQ = 1


@router.get("/reviews")
async def list_reviews(restaurant_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = db.query(DBReview).filter(DBReview.is_deleted == False)
    if restaurant_id is not None:
        q = q.filter(DBReview.restaurant_id == restaurant_id)
    data = q.all()
    return [{
        "id": r.id, "order_id": r.order_id, "restaurant_id": r.restaurant_id, "user_id": r.user_id,
        "rating": r.rating, "comment": r.comment, "created_at": r.created_at, "is_deleted": r.is_deleted
    } for r in data]


@router.delete("/reviews/{review_id}")
async def delete_review(review_id: int, db: Session = Depends(get_db)) -> dict:
    r = db.query(DBReview).filter(DBReview.id == review_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    r.is_deleted = True
    db.commit()
    try:
        await send_admin_message(f"[admin] Удалён отзыв id={review_id}")
    except Exception:
        pass
    return {"status": "ok"}


# Admin Code Management
@router.get("/admin-code")
async def get_admin_code() -> dict:
    """Получить текущий ADMIN_CODE"""
    admin_code = os.getenv("ADMIN_CODE", "")
    return {"admin_code": admin_code}


@router.post("/admin-code")
async def update_admin_code(payload: AdminCodeUpdate) -> dict:
    """Обновить ADMIN_CODE"""
    new_code = payload.admin_code.strip()
    if not new_code:
        raise HTTPException(status_code=400, detail="Admin code cannot be empty")
    
    # Обновляем переменную окружения
    os.environ["ADMIN_CODE"] = new_code
    
    try:
        await send_admin_message(f"[admin] ADMIN_CODE изменён на: {new_code}")
    except Exception:
        pass
    
    return {"status": "ok", "admin_code": new_code}

