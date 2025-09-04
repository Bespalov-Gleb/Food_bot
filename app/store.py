from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import User as DBUser, RestaurantAdmin as DBRestaurantAdmin


def ensure_user(user_id: int, username: str | None = None) -> DBUser:
    with get_session() as db:  # type: Session
        u = db.query(DBUser).filter(DBUser.id == user_id).first()
        if not u:
            u = DBUser(id=user_id, is_blocked=False, created_at=datetime.utcnow(), last_activity=datetime.utcnow(), username=username)
            db.add(u)
            db.commit()
        else:
            # Обновляем last_activity и username для существующих пользователей
            u.last_activity = datetime.utcnow()
            if username and not u.username:
                u.username = username
            db.commit()
        return u


def bind_restaurant_admin(user_id: int, restaurant_id: int) -> None:
    print(f"DEBUG: bind_restaurant_admin called with user_id={user_id}, restaurant_id={restaurant_id}")
    with get_session() as db:
        # Сначала убеждаемся, что пользователь существует
        ensure_user(user_id)
        print(f"DEBUG: user {user_id} ensured")
        
        row = db.query(DBRestaurantAdmin).filter(DBRestaurantAdmin.user_id == user_id).first()
        if row:
            print(f"DEBUG: updating existing admin record for user {user_id}")
            row.restaurant_id = restaurant_id
        else:
            print(f"DEBUG: creating new admin record for user {user_id}")
            db.add(DBRestaurantAdmin(user_id=user_id, restaurant_id=restaurant_id))
        db.commit()
        print(f"DEBUG: commit successful")


def unbind_restaurant_admin(user_id: int) -> None:
    with get_session() as db:
        row = db.query(DBRestaurantAdmin).filter(DBRestaurantAdmin.user_id == user_id).first()
        if row:
            db.delete(row)
            db.commit()


def get_restaurant_for_admin(user_id: int) -> int | None:
    print(f"DEBUG: get_restaurant_for_admin called with user_id={user_id}")
    with get_session() as db:
        print(f"DEBUG: Querying RestaurantAdmin table for user_id={user_id}")
        row = db.query(DBRestaurantAdmin).filter(DBRestaurantAdmin.user_id == user_id).first()
        result = row.restaurant_id if row else None
        print(f"DEBUG: get_restaurant_for_admin result: {result}")
        if row:
            print(f"DEBUG: Found row: user_id={row.user_id}, restaurant_id={row.restaurant_id}")
        else:
            print(f"DEBUG: No row found for user_id={user_id}")
            # Проверяем, есть ли вообще записи в таблице
            all_rows = db.query(DBRestaurantAdmin).all()
            print(f"DEBUG: Total rows in RestaurantAdmin table: {len(all_rows)}")
            for r in all_rows:
                print(f"DEBUG: Row: user_id={r.user_id}, restaurant_id={r.restaurant_id}")
        return result


def get_user_by_username(username: str) -> int | None:
    """Находит пользователя по username в базе данных"""
    clean_username = username.lstrip('@')
    with get_session() as db:
        user = db.query(DBUser).filter(DBUser.username == clean_username).first()
        return user.id if user else None


# Временные заглушки для совместимости с существующим кодом, где импортируются эти имена
users: Dict[int, Any] = {}
ORDERS: List[Any] = []
ORDER_SEQ: int = 1
REVIEWS: List[Any] = []
REV_SEQ: int = 1

