from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
# Убираем неиспользуемые импорты
from app.deps.auth import require_user_id
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Cart as DBCart, CartItem as DBCartItem, Dish as ODish, Option as OOption, OptionGroup as OGroup, User as DBUser
import json


router = APIRouter()


class CartItem(BaseModel):
    id: Optional[int] = None
    restaurant_id: int
    dish_id: int
    qty: int
    chosen_options: Optional[List[int]] = None
    
    class Config:
        # Разрешаем дополнительные поля для совместимости
        extra = "allow"



class Cart(BaseModel):
    items: List[CartItem]
    cutlery_count: int = 0


# Константы для корзины
_MAX_RESTAURANTS = 4


def _get_cart_db(user_id: int, db: Session) -> DBCart:
    # ensure user exists to satisfy FK constraint
    u = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not u:
        db.add(DBUser(id=user_id))
        db.commit()
    c = db.query(DBCart).filter(DBCart.user_id == user_id).first()
    if not c:
        c = DBCart(user_id=user_id, cutlery_count=0)
        db.add(c)
        db.commit()
    return c


@router.get("")
async def get_cart(user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> Cart:
    c = _get_cart_db(user_id, db)
    items = db.query(DBCartItem).filter(DBCartItem.cart_id == c.id).all()
    return Cart(
        items=[
            CartItem(id=it.id, restaurant_id=it.restaurant_id, dish_id=it.dish_id, qty=it.qty, chosen_options=json.loads(it.chosen_options or "[]"))
            for it in items
        ],
        cutlery_count=c.cutlery_count or 0,
    )


@router.post("/items")
async def add_item(item: CartItem, force: bool = False, user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> Dict[str, int | str | list]:
    # Убеждаемся, что chosen_options не None
    if item.chosen_options is None:
        item.chosen_options = []
    print(f"DEBUG: Force flag: {force}")
    print(f"DEBUG: User ID: {user_id}")
    print(f"DEBUG: restaurant_id type: {type(item.restaurant_id)}, value: {item.restaurant_id}")
    print(f"DEBUG: dish_id type: {type(item.dish_id)}, value: {item.dish_id}")
    print(f"DEBUG: qty type: {type(item.qty)}, value: {item.qty}")
    print(f"DEBUG: chosen_options type: {type(item.chosen_options)}, value: {item.chosen_options}")
    
    print("DEBUG: Getting cart from database...")
    c = _get_cart_db(user_id, db)
    print(f"DEBUG: Cart ID: {c.id}")
    
    print("DEBUG: Checking existing restaurants...")
    existing_restaurants = {it.restaurant_id for it in db.query(DBCartItem).filter(DBCartItem.cart_id == c.id).all()}
    print(f"DEBUG: Existing restaurants: {existing_restaurants}")
    
    is_new_restaurant = item.restaurant_id not in existing_restaurants
    print(f"DEBUG: Is new restaurant: {is_new_restaurant}")
    print(f"DEBUG: Current restaurant count: {len(existing_restaurants)}")
    print(f"DEBUG: Max restaurants: {_MAX_RESTAURANTS}")
    
    if is_new_restaurant and len(existing_restaurants) >= _MAX_RESTAURANTS and not force:
        print("DEBUG: Too many restaurants, returning error")
        return {
            "status": "too_many_restaurants",
            "current_restaurant_ids": list(existing_restaurants),
            "max": _MAX_RESTAURANTS,
        }
    if is_new_restaurant and len(existing_restaurants) >= _MAX_RESTAURANTS and force:
        print("DEBUG: Force flag is True, clearing other restaurants")
        db.query(DBCartItem).filter(DBCartItem.cart_id == c.id, DBCartItem.restaurant_id != item.restaurant_id).delete()

    print("DEBUG: Validating dish exists...")
    # validate options if needed
    dish = db.query(ODish).filter(ODish.id == item.dish_id).first()
    if not dish:
        print("DEBUG: Dish not found, raising 404")
        raise HTTPException(status_code=404, detail="Dish not found")
    print(f"DEBUG: Dish found: {dish.name}, has_options: {dish.has_options}")
    
    # Проверяем, есть ли реально группы опций в базе данных
    groups = db.query(OGroup).filter(OGroup.dish_id == dish.id).all()
    print(f"DEBUG: Found {len(groups)} option groups for dish {dish.id}")
    
    if groups:  # Если есть группы опций, валидируем
        print("DEBUG: Dish has option groups, validating chosen options...")
        chosen = set(item.chosen_options or [])
        print(f"DEBUG: Chosen options: {chosen}")
        
        opt_map = {}
        g_ids = [g.id for g in groups]
        opts = db.query(OOption).filter(OOption.group_id.in_(g_ids)).all()
        print(f"DEBUG: Found {len(opts)} options")
        
        for g in groups:
            opt_map[g.id] = {o.id for o in opts if o.group_id == g.id}
            print(f"DEBUG: Group {g.id} has options: {opt_map[g.id]}")
        
        for g in groups:
            print(f"DEBUG: Validating group {g.id}: min_select={g.min_select}, max_select={g.max_select}, required={g.required}")
            count = len([oid for oid in chosen if oid in opt_map.get(g.id, set())])
            print(f"DEBUG: Selected count for group {g.id}: {count}")
            
            # Для обязательных групп минимум 1, для необязательных - min_select
            min_required = max(1, g.min_select) if g.required else g.min_select
            print(f"DEBUG: Min required for group {g.id}: {min_required}")
            
            if count < min_required:
                print(f"DEBUG: Validation failed - not enough options for group {g.id}")
                raise HTTPException(status_code=400, detail={"status": "options_required", "group_id": g.id})
            if g.max_select and count > g.max_select:
                print(f"DEBUG: Validation failed - too many options for group {g.id}")
                raise HTTPException(status_code=400, detail={"status": "options_exceeded", "group_id": g.id, "max": g.max_select})
    
    print("DEBUG: All validations passed, creating cart item...")
    db_item = DBCartItem(
        cart_id=c.id,
        restaurant_id=item.restaurant_id,
        dish_id=item.dish_id,
        qty=item.qty,
        chosen_options=json.dumps(item.chosen_options or []),
    )
    print(f"DEBUG: Created DB item: {db_item}")
    
    db.add(db_item)
    db.commit()
    print(f"DEBUG: Item saved to database with ID: {db_item.id}")
    
    return {"status": "ok", "id": db_item.id or 0}


@router.patch("/items/{item_id}")
async def update_item(item_id: int, qty: int, user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> Dict[str, str]:
    c = _get_cart_db(user_id, db)
    it = db.query(DBCartItem).filter(DBCartItem.id == item_id, DBCartItem.cart_id == c.id).first()
    if not it:
        return {"status": "not_found"}
    it.qty = qty
    db.commit()
    return {"status": "ok"}


@router.delete("/items/{item_id}")
async def delete_item(item_id: int, user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> Dict[str, str]:
    c = _get_cart_db(user_id, db)
    deleted = db.query(DBCartItem).filter(DBCartItem.id == item_id, DBCartItem.cart_id == c.id).delete()
    db.commit()
    return {"status": "ok" if deleted else "not_found"}


@router.post("/clear")
async def clear_cart(restaurant_id: int | None = None, user_id: int = Depends(require_user_id), db: Session = Depends(get_db)) -> Dict[str, str]:
    c = _get_cart_db(user_id, db)
    if restaurant_id is None:
        db.query(DBCartItem).filter(DBCartItem.cart_id == c.id).delete()
        db.commit()
        return {"status": "ok"}
    deleted = db.query(DBCartItem).filter(DBCartItem.cart_id == c.id, DBCartItem.restaurant_id == restaurant_id).delete()
    db.commit()
    return {"status": "ok", "removed": str(deleted)}

