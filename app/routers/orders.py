from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Literal
from datetime import datetime
from app.services.telegram import send_admin_message, send_user_message, WEBAPP_URL, notify_user_order_delivered, notify_restaurant_admins
from app.logging_config import get_logger
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Option as OOption, Restaurant as ORestaurant, Order as DBOrder, OrderItem as DBOrderItem
from app.store import ensure_user
from app.email_service import email_service
import json


router = APIRouter()


OrderStatus = Literal["created", "sent", "accepted", "delivered", "cancelled", "modified"]


class OrderItem(BaseModel):
    dish_id: int
    name: str
    price: int
    qty: int
    chosen_options: list[int] | None = None


class Order(BaseModel):
    id: int
    user_id: int
    restaurant_id: int
    status: OrderStatus
    total_price: int
    delivery_type: Literal["delivery", "pickup"]
    address: str | None
    phone: str
    payment_method: Literal["cash", "card_to_courier", "transfer"]
    client_comment: str | None
    staff_comment: str | None = None
    accepted_at: datetime | None = None
    eta_minutes: int | None = None
    created_at: datetime
    items: List[OrderItem]


logger = get_logger("orders")


class OrderCreate(BaseModel):
    user_id: int
    restaurant_id: int
    total_price: int
    delivery_type: Literal["delivery", "pickup"]
    address: str | None = None
    phone: str
    payment_method: Literal["cash", "card_to_courier", "transfer"]
    client_comment: str | None = None
    items: List[OrderItem]


@router.post("")
async def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> dict:
    # check user blocked
    user = ensure_user(payload.user_id)
    if user.is_blocked:
        raise HTTPException(status_code=403, detail="user_blocked")
    # server-side validation: minimal sum for delivery
    if payload.delivery_type == "delivery":
        r = db.query(ORestaurant).filter(ORestaurant.id == payload.restaurant_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        if payload.total_price < r.delivery_min_sum:
            diff = r.delivery_min_sum - payload.total_price
            raise HTTPException(status_code=400, detail=f"Добавьте ещё на {diff} р")
    # snapshot items with option names and compute total server-side
    # options lookup from DB
    chosen_ids: set[int] = set()
    for it in payload.items:
        if it.chosen_options:
            chosen_ids.update(int(x) for x in it.chosen_options)
    opt_map: dict[int, OOption] = {}
    if chosen_ids:
        rows = db.query(OOption).filter(OOption.id.in_(list(chosen_ids))).all()
        opt_map = {o.id: o for o in rows}
    snapped_items: List[OrderItem] = []
    computed_total = 0
    for it in payload.items:
        opts = []
        delta = 0
        if it.chosen_options:
            for oid in it.chosen_options:
                op = opt_map.get(int(oid))
                if op:
                    delta += op.price_delta or 0
                    opts.append(op.name + (f"+{op.price_delta}" if op.price_delta else ""))
        name_with_opts = it.name + (f" ({', '.join(opts)})" if opts else "")
        snapped_items.append(
            OrderItem(
                dish_id=it.dish_id,
                name=name_with_opts,
                price=it.price,
                qty=it.qty,
                chosen_options=it.chosen_options or [],
            )
        )
        computed_total += (it.price + delta) * it.qty

    # add delivery fee if delivery type
    delivery_fee = 0
    r = db.query(ORestaurant).filter(ORestaurant.id == payload.restaurant_id).first()
    if payload.delivery_type == "delivery" and r:
        delivery_fee = r.delivery_fee
    computed_total += delivery_fee

    # Persist order and items in DB
    db_order = DBOrder(
        user_id=payload.user_id,
        restaurant_id=payload.restaurant_id,
        status="sent",
        total_price=computed_total,
        delivery_type=payload.delivery_type,
        address=payload.address,
        phone=payload.phone,
        payment_method=payload.payment_method,
        client_comment=payload.client_comment,
        created_at=datetime.utcnow(),
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    for it in snapped_items:
        db.add(DBOrderItem(
            order_id=db_order.id,
            dish_id=it.dish_id,
            name=it.name,
            price=it.price,
            qty=it.qty,
            chosen_options=json.dumps(it.chosen_options or []),
        ))
    db.commit()
    # journal notification (админ‑канал)
    try:
        def fmt_item(it: OrderItem) -> str:
            return f"{it.name}×{it.qty}"

        items_txt = ", ".join(fmt_item(it) for it in snapped_items)
        msg = (
            f"Новый заказ №{db_order.id} в ресторане {db_order.restaurant_id} на сумму {db_order.total_price} р\n"
            f"Тип: {db_order.delivery_type}, Оплата: {db_order.payment_method}\n"
            f"Адрес: {db_order.address or '-'}\n"
            f"Состав: {items_txt}"
        )
        await send_admin_message(msg)
    except Exception:
        pass

    # Уведомление админам ресторана
    try:
        if WEBAPP_URL:
            # URL для открытия модального окна обработки заказа
            admin_url = f"{WEBAPP_URL}/static/ra.html?order_id={db_order.id}"
            
            def fmt_item(it: OrderItem) -> str:
                return f"{it.name}×{it.qty}"
            
            items_txt = ", ".join(fmt_item(it) for it in snapped_items)
            admin_msg = (
                f"🆕 НОВЫЙ ЗАКАЗ №{db_order.id}\n\n"
                f"💰 Сумма: {db_order.total_price} ₽\n"
                f"🚚 Тип: {db_order.delivery_type}\n"
                f"💳 Оплата: {db_order.payment_method}\n"
                f"📍 Адрес: {db_order.address or 'Самовывоз'}\n"
                f"📱 Телефон: {db_order.phone}\n"
                f"📝 Состав: {items_txt}\n"
                f"💬 Комментарий: {db_order.client_comment or 'Нет'}"
            )
            
            await notify_restaurant_admins(
                restaurant_id=db_order.restaurant_id,
                message=admin_msg,
                button_text="📋 Обработать заказ",
                button_url=admin_url
            )
    except Exception as exc:
        logger.exception("Failed to send notification to restaurant admins: %s", repr(exc))

    # Email уведомление ресторану о новом заказе
    try:
        r = db.query(ORestaurant).filter(ORestaurant.id == db_order.restaurant_id).first()
        if r and r.email:
            # Подготавливаем данные для email
            order_data = {
                'id': db_order.id,
                'user_id': db_order.user_id,
                'created_at': db_order.created_at.strftime('%d.%m.%Y %H:%M'),
                'delivery_address': db_order.address or 'Самовывоз',
                'payment_method': {
                    'cash': 'Наличными',
                    'card_to_courier': 'Картой курьеру',
                    'transfer': 'Переводом'
                }.get(db_order.payment_method, db_order.payment_method),
                'items': [
                    {
                        'name': item.name,
                        'qty': item.qty,
                        'price': item.price
                    } for item in snapped_items
                ]
            }
            
            email_service.send_order_notification(
                restaurant_email=r.email,
                restaurant_name=r.name,
                order_data=order_data
            )
    except Exception as exc:
        logger.exception("Failed to send email notification: %s", repr(exc))

    # notify user with deep‑link to current order (mini app web_app)
    try:
        if WEBAPP_URL:
            url = f"{WEBAPP_URL}/static/order.html?id={db_order.id}"
            # pretty formatted message
            lines = [
                "Заказ отправлен. Ждите подтверждение ресторана",
                "",
                "СОСТАВ ЗАКАЗА",
                "------------------------------",
            ]
            for it in snapped_items:
                lines.append(f"{it.name} × {it.qty} — {it.price} р")
            lines.append("------------------------------")
            lines.append(f"ИТОГО: {db_order.total_price} р")
            lines.append("")
            lines.append("Нажмите кнопку ниже, чтобы открыть подробности заказа.")
            text = "\n".join(lines)
            ok = await send_user_message(
                chat_id=db_order.user_id,
                text=text,
                button_text="Открыть текущий заказ",
                button_url=url,
            )
            logger.info("user_message sent ok=%s chat_id=%s url=%s", ok, db_order.user_id, url)
        else:
            logger.warning("WEBAPP_URL is empty; skip user_message")
    except Exception as exc:
        logger.exception("user_message failed: %s", repr(exc))
    
    return {"id": db_order.id}


@router.get("/{order_id}")
async def get_order(order_id: int, db: Session = Depends(get_db)) -> Order:
    o = db.query(DBOrder).filter(DBOrder.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    items = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).all()
    return Order(
        id=o.id,
        user_id=o.user_id,
        restaurant_id=o.restaurant_id,
        status=o.status,
        total_price=o.total_price,
        delivery_type=o.delivery_type,
        address=o.address,
        phone=o.phone,
        payment_method=o.payment_method,
        client_comment=o.client_comment,
        staff_comment=o.staff_comment,
        accepted_at=o.accepted_at,
        eta_minutes=o.eta_minutes,
        created_at=o.created_at,
        items=[OrderItem(dish_id=it.dish_id, name=it.name, price=it.price, qty=it.qty, chosen_options=json.loads(it.chosen_options or "[]")) for it in items]
    )


@router.get("")
async def list_orders(user_id: int, db: Session = Depends(get_db)) -> List[Order]:
    rows = db.query(DBOrder).filter(DBOrder.user_id == user_id).all()
    result: List[Order] = []
    for o in rows:
        items = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).all()
        result.append(Order(
            id=o.id,
            user_id=o.user_id,
            restaurant_id=o.restaurant_id,
            status=o.status,
            total_price=o.total_price,
            delivery_type=o.delivery_type,
            address=o.address,
            phone=o.phone,
            payment_method=o.payment_method,
            client_comment=o.client_comment,
            staff_comment=o.staff_comment,
            accepted_at=o.accepted_at,
            eta_minutes=o.eta_minutes,
            created_at=o.created_at,
            items=[OrderItem(dish_id=it.dish_id, name=it.name, price=it.price, qty=it.qty, chosen_options=json.loads(it.chosen_options or "[]")) for it in items]
        ))
    return result


@router.get("/by-restaurant/{restaurant_id}")
async def list_orders_by_restaurant(restaurant_id: int, db: Session = Depends(get_db)) -> List[Order]:
    rows = db.query(DBOrder).filter(DBOrder.restaurant_id == restaurant_id).all()
    result: List[Order] = []
    for o in rows:
        items = db.query(DBOrderItem).filter(DBOrderItem.order_id == o.id).all()
        result.append(Order(
            id=o.id,
            user_id=o.user_id,
            restaurant_id=o.restaurant_id,
            status=o.status,
            total_price=o.total_price,
            delivery_type=o.delivery_type,
            address=o.address,
            phone=o.phone,
            payment_method=o.payment_method,
            client_comment=o.client_comment,
            staff_comment=o.staff_comment,
            accepted_at=o.accepted_at,
            eta_minutes=o.eta_minutes,
            created_at=o.created_at,
            items=[OrderItem(dish_id=it.dish_id, name=it.name, price=it.price, qty=it.qty, chosen_options=json.loads(it.chosen_options or "[]")) for it in items]
        ))
    return result


@router.post("/{order_id}/accept")
async def accept_order(order_id: int, eta_minutes: int = 60, db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id).first()
    if not o:
        return {"status": "not_found"}
    
    # Проверяем, что заказ еще не принят
    if o.status == "accepted":
        return {"status": "already_accepted"}
    
    o.status = "accepted"
    o.accepted_at = datetime.utcnow()
    o.eta_minutes = eta_minutes
    db.commit()
    
    try:
        await send_admin_message(
            f"Заказ №{o.id} принят рестораном {o.restaurant_id}. Время доставки ~ {eta_minutes} мин"
        )
    except Exception:
        pass
    
    return {"status": "ok"}


@router.post("/{order_id}/delivered")
async def delivered_order(order_id: int, db: Session = Depends(get_db)) -> dict:
    o = db.query(DBOrder).filter(DBOrder.id == order_id).first()
    if not o:
        return {"status": "not_found"}
    o.status = "delivered"
    db.commit()
    
    try:
        await send_admin_message(
            f"Заказ №{o.id} доставлен рестораном {o.restaurant_id}"
        )
    except Exception:
        pass
    
    # Отправляем уведомление клиенту с предложением оценки
    try:
        r = db.query(ORestaurant).filter(ORestaurant.id == o.restaurant_id).first()
        if r:
            await notify_user_order_delivered(o.user_id, o.id, r.name)
    except Exception as exc:
        logger.exception("Failed to send delivery notification to user: %s", repr(exc))
    
    return {"status": "ok"}

