from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import List, Optional
from app.deps.auth import require_user_id
from app.store import get_restaurant_for_admin
from app.services.telegram import send_admin_message, notify_user_order_modified, notify_user_order_accepted, WEBAPP_URL
from app.services.image_processor import ImageProcessor
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db, get_session
from app.models import Restaurant as ORestaurant, Option as OOption, Order as DBOrder, OrderItem as DBOrderItem, RestaurantAdmin as DBRestaurantAdmin
import os
import uuid
from datetime import datetime


router = APIRouter()


def require_restaurant_id(user_id: int = Depends(require_user_id)) -> int:
    print(f"DEBUG: require_restaurant_id called with user_id={user_id}")
    rid = get_restaurant_for_admin(user_id)
    print(f"DEBUG: require_restaurant_id result: rid={rid}")
    if rid is None:
        print(f"DEBUG: require_restaurant_id: raising 403 for user_id={user_id}")
        print(f"DEBUG: User {user_id} is not a restaurant admin")
        raise HTTPException(status_code=403, detail="not_restaurant_admin")
    print(f"DEBUG: require_restaurant_id: returning rid={rid} for user_id={user_id}")
    return rid


@router.get("/ra/me")
async def ra_me(rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    """Проверка прав администратора ресторана"""
    restaurant = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="restaurant_not_found")
    
    return {
        "restaurant_id": rid,
        "restaurant_name": restaurant.name,
        "is_enabled": restaurant.is_enabled
    }


@router.get("/ra/orders")
async def ra_list_orders(rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> List[dict]:
    print(f"DEBUG: ra_list_orders called with rid={rid}")
    orders = db.query(DBOrder).filter(DBOrder.restaurant_id == rid).all()
    print(f"DEBUG: Found {len(orders)} orders for restaurant {rid}")
    
    data: List[dict] = []
    for o in orders:
        items = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).order_by(DBOrderItem.id.asc()).all()
        print(f"DEBUG: Order {o.id} has {len(items)} items")
        data.append({
            "id": o.id,
            "user_id": o.user_id,
            "restaurant_id": o.restaurant_id,
            "status": o.status,
            "total_price": o.total_price,
            "delivery_type": o.delivery_type,
            "address": o.address,
            "phone": o.phone,
            "payment_method": o.payment_method,
            "client_comment": o.client_comment,
            "staff_comment": o.staff_comment,
            "accepted_at": o.accepted_at,
            "eta_minutes": o.eta_minutes,
            "created_at": o.created_at,
            "items": [{"name": it.name, "qty": it.qty} for it in items],
        })
    
    print(f"DEBUG: Returning {len(data)} orders")
    return data


@router.get("/ra/orders/{order_id}")
async def ra_get_order(order_id: int, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id, DBOrder.restaurant_id == rid).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    
    items = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).order_by(DBOrderItem.id.asc()).all()
    
    return {
        "id": o.id,
        "user_id": o.user_id,
        "restaurant_id": o.restaurant_id,
        "status": o.status,
        "total_price": o.total_price,
        "delivery_type": o.delivery_type,
        "address": o.address,
        "phone": o.phone,
        "payment_method": o.payment_method,
        "client_comment": o.client_comment,
        "staff_comment": o.staff_comment,
        "accepted_at": o.accepted_at,
        "eta_minutes": o.eta_minutes,
        "created_at": o.created_at,
        "items": [{"name": it.name, "qty": it.qty} for it in items],
    }


@router.post("/ra/orders/{order_id}/accept")
async def ra_accept(order_id: int, eta_minutes: int = 60, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id, DBOrder.restaurant_id == rid).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    o.status = "accepted"
    o.accepted_at = __import__('datetime').datetime.utcnow()
    o.eta_minutes = eta_minutes
    db.commit()
    try:
        await send_admin_message(f"[ra] Заказ №{o.id} принят рестораном {rid} (~{eta_minutes} мин)")
        if WEBAPP_URL:
            name = str(rid)
            rr = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
            if rr:
                name = rr.name
            await notify_user_order_accepted(o.user_id, f"{WEBAPP_URL}/static/order.html?id={o.id}", name, eta_minutes)
    except Exception:
        pass
    return {"status": "ok"}


@router.post("/ra/orders/{order_id}/cancel")
async def ra_cancel(order_id: int, reason: str = "", rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id, DBOrder.restaurant_id == rid).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    o.status = "cancelled"
    o.staff_comment = reason
    db.commit()
    try:
        await send_admin_message(f"[ra] Заказ №{o.id} отменён рестораном {rid}. Причина: {reason}")
    except Exception:
        pass
    return {"status": "ok"}


@router.post("/ra/orders/{order_id}/delivered")
async def ra_delivered(order_id: int, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id, DBOrder.restaurant_id == rid).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    o.status = "delivered"
    db.commit()
    try:
        await send_admin_message(f"[ra] Заказ №{o.id} доставлен рестораном {rid}")
    except Exception:
        pass
    return {"status": "ok"}


@router.post("/ra/orders/{order_id}/modify")
async def ra_modify(order_id: int, comment: str, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id, DBOrder.restaurant_id == rid).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    o.status = "modified"
    o.staff_comment = comment
    db.commit()
    try:
        await send_admin_message(f"[ra] Заказ №{o.id} изменён рестораном {rid}. Комментарий: {comment}")
        if WEBAPP_URL:
            phone = ""
            rr = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
            if rr:
                phone = rr.phone or ""
            text = (
                "Ваш заказ изменён рестораном.\n"
                f"Комментарий: {comment}\n"
                + (f"Телефон ресторана: {phone}\n" if phone else "")
            )
            await notify_user_order_modified(o.user_id, f"{WEBAPP_URL}/static/order.html?id={o.id}", text=text)
    except Exception:
        pass
    return {"status": "ok"}


class ModifyItemPayload(BaseModel):
    index: int
    qty: int


def _recalc_total_with_options(items, db: Session) -> int:
    # собрать все option_ids из заказа и вытянуть одним запросом
    option_ids: set[int] = set()
    for it in items:
        chosen = getattr(it, 'chosen_options', None)
        if chosen:
            if isinstance(chosen, str):
                try:
                    import json
                    chosen_list = json.loads(chosen or '[]')
                    if isinstance(chosen_list, list):
                        for x in chosen_list:
                            try:
                                option_ids.add(int(x))
                            except (ValueError, TypeError):
                                continue
                except Exception:
                    continue
            else:
                try:
                    for x in chosen:
                        option_ids.add(int(x))
                except (ValueError, TypeError):
                    continue
    
    by_opt: dict[int, int] = {}
    if option_ids:
        rows = db.query(OOption).filter(OOption.id.in_(list(option_ids))).all()
        by_opt = {o.id: (o.price_delta or 0) for o in rows}
    
    subtotal = 0
    for it in items:
        delta = 0
        chosen = getattr(it, 'chosen_options', None)
        if isinstance(chosen, str):
            try:
                import json
                chosen_list = json.loads(chosen or '[]')
            except Exception:
                chosen_list = []
        else:
            chosen_list = chosen or []
        
        if chosen_list:
            for oid in chosen_list:
                try:
                    delta += by_opt.get(int(oid), 0)
                except (ValueError, TypeError):
                    continue
        subtotal += (it.price + delta) * it.qty
    return int(subtotal)


class ModifyItemsRequest(BaseModel):
    items: list[ModifyItemPayload]
    comment: str


@router.post("/ra/orders/{order_id}/modify-items")
async def ra_modify_items(order_id: int, payload: ModifyItemsRequest, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id, DBOrder.restaurant_id == rid).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    # load items in stable order
    items = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).order_by(DBOrderItem.id.asc()).all()
    # apply quantities by index
    for patch in payload.items:
        idx = int(patch.index)
        qty = int(patch.qty)
        if 0 <= idx < len(items):
            items[idx].qty = max(0, qty)
    # delete zero-qty
    for it in list(items):
        if it.qty <= 0:
            db.delete(it)
    db.commit()
    # reload items for totals
    items2 = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).all()
    subtotal = _recalc_total_with_options(items2, db)
    delivery_fee = 0
    r = db.query(ORestaurant).filter(ORestaurant.id == o.restaurant_id).first()
    if o.delivery_type == 'delivery' and r:
        delivery_fee = r.delivery_fee
    o.total_price = subtotal + delivery_fee
    o.status = 'modified'
    o.staff_comment = payload.comment
    db.commit()
    try:
        await send_admin_message(f"[ra] Заказ №{o.id} изменён по составу рестораном {rid}. Комментарий: {payload.comment}")
        if WEBAPP_URL:
            phone = ""
            rr = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
            if rr:
                phone = rr.phone or ""
            text = (
                "Ваш заказ изменён рестораном.\n"
                f"Комментарий: {payload.comment}\n"
                + (f"Телефон ресторана: {phone}\n" if phone else "")
            )
            await notify_user_order_modified(o.user_id, f"{WEBAPP_URL}/static/order.html?id={o.id}", text=text)
    except Exception:
        pass
    return {"status": "ok", "total": o.total_price}


# --- Дополнительные RA-эндпоинты: профиль ресторана и переключение статуса ---

@router.get("/ra/me")
async def ra_me(rid: int = Depends(require_restaurant_id)) -> dict:
    return {"restaurant_id": rid}


@router.get("/ra/restaurant")
async def ra_restaurant(rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    r = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    return {
        "id": r.id,
        "name": r.name,
        "is_enabled": r.is_enabled,
        "rating_agg": r.rating_agg,
        "delivery_min_sum": r.delivery_min_sum,
        "delivery_fee": r.delivery_fee,
        "delivery_time_minutes": r.delivery_time_minutes,
        "address": r.address,
        "phone": r.phone,
        "description": r.description,
        "image": r.image,
        "work_open_min": r.work_open_min,
        "work_close_min": r.work_close_min,
    }


@router.post("/ra/restaurant/status")
async def ra_set_status(enabled: bool, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    r = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    r.is_enabled = bool(enabled)
    db.commit()
    try:
        await send_admin_message(f"[ra] Ресторан id={rid} статус={'ON' if enabled else 'OFF'}")
    except Exception:
        pass
    return {"status": "ok"}


class RestaurantPatch(BaseModel):
    address: Optional[str] = None
    phone: Optional[str] = None
    work_open_min: Optional[int] = None
    work_close_min: Optional[int] = None
    delivery_min_sum: Optional[int] = None
    delivery_time_minutes: Optional[int] = None
    description: Optional[str] = None


@router.patch("/ra/restaurant")
async def ra_update_restaurant(payload: RestaurantPatch, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    r = db.query(ORestaurant).filter(ORestaurant.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="not_found")
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    for num_key in ("work_open_min", "work_close_min", "delivery_min_sum", "delivery_time_minutes"):
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
        await send_admin_message(f"[ra] Обновлены данные ресторана id={rid}")
    except Exception:
        pass
    return {"status": "ok", "restaurant": {
        "id": r.id,
        "name": r.name,
        "is_enabled": r.is_enabled,
        "rating_agg": r.rating_agg,
        "delivery_min_sum": r.delivery_min_sum,
        "delivery_fee": r.delivery_fee,
        "delivery_time_minutes": r.delivery_time_minutes,
        "address": r.address,
        "phone": r.phone,
        "description": r.description,
        "image": r.image,
        "work_open_min": r.work_open_min,
        "work_close_min": r.work_close_min,
    }}


@router.post("/ra/upload-image")
async def ra_upload_image(image: UploadFile = File(...), rid: int = Depends(require_restaurant_id)) -> dict:
    """Загрузка изображения для блюд ресторана с автоматической обработкой"""
    
    # Проверяем тип файла
    if not image.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")
    
    try:
        # Читаем содержимое файла
        content = await image.read()
        
        # Обрабатываем изображение
        result = ImageProcessor.process_image(content, image.filename)
        
        # Возвращаем результат с URL'ами для разных размеров
        return {
            "status": "ok",
            "image_url": result["urls"]["dish_card"],  # Основной URL для карточки блюда
            "urls": result["urls"],  # Все URL'ы для разных размеров
            "original_size": result["original_size"],
            "processed_sizes": result["processed_sizes"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке изображения: {str(e)}")
