from sqlalchemy.orm import Session
from app.db import Base, engine, get_session
from app.models import User, Restaurant, Category, Dish, OptionGroup, Option, RestaurantAdmin, Review, Cart


def init_db_and_seed() -> None:
    Base.metadata.create_all(bind=engine)
    with get_session() as db:  # type: Session
        _seed_restaurants(db)
        _seed_menu(db)
        _seed_carts(db)


def _seed_restaurants(db: Session) -> None:
    if db.query(Restaurant).limit(1).first() is not None:
        return
    # Demo data
    demo = [
        dict(id=1, name="Вкусно и точка", is_enabled=True, rating_agg=4.6, delivery_min_sum=600, delivery_fee=99,
             delivery_time_minutes=60, address="Ленина 1", phone="+7 900 000-00-01",
             image="https://images.unsplash.com/photo-1606756790138-261d2b21cd79?w=800&q=80&auto=format&fit=crop",
             work_open_min=0, work_close_min=1440, description=""),
        dict(id=2, name="Чиббис", is_enabled=True, rating_agg=4.8, delivery_min_sum=800, delivery_fee=0,
             delivery_time_minutes=50, address="Победы 10", phone="+7 900 000-00-02",
             image="https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800&q=80&auto=format&fit=crop",
             work_open_min=0, work_close_min=1440, description=""),
    ]
    for r in demo:
        db.add(Restaurant(**r))
    db.commit()


def _seed_menu(db: Session) -> None:
    if db.query(Category).limit(1).first() is not None:
        return
    # Categories
    cats = [
        dict(id=1, restaurant_id=1, name="Комбо", sort=1),
        dict(id=2, restaurant_id=1, name="Бургеры", sort=2),
        dict(id=3, restaurant_id=2, name="Пицца", sort=1),
    ]
    for c in cats:
        db.add(Category(**c))
    # Dishes
    dishes = [
        dict(id=101, restaurant_id=1, category_id=1, name="Комбо №1", description="Набор", price=399, image="https://via.placeholder.com/300x200?text=Combo+1", is_available=True, has_options=False),
        dict(id=102, restaurant_id=1, category_id=2, name="Бургер", description="Сырный", price=249, image="https://via.placeholder.com/300x200?text=Burger", is_available=True, has_options=True),
        dict(id=201, restaurant_id=2, category_id=3, name="Пицца Маргарита", description="30см", price=549, image="https://via.placeholder.com/300x200?text=Pizza", is_available=True, has_options=True),
    ]
    for d in dishes:
        db.add(Dish(**d))
    # Option groups and options for dish 102 and 201
    groups = [
        dict(id=1, dish_id=102, name="Добавки", min_select=0, max_select=2, required=False),
        dict(id=2, dish_id=102, name="Соус", min_select=1, max_select=1, required=True),
        dict(id=3, dish_id=201, name="Размер", min_select=1, max_select=1, required=True),
    ]
    for g in groups:
        db.add(OptionGroup(**g))
    # commit groups first to satisfy FK for options in Postgres
    db.commit()
    options = [
        dict(id=1001, group_id=1, name="Сыр", price_delta=30),
        dict(id=1002, group_id=1, name="Бекон", price_delta=40),
        dict(id=1101, group_id=2, name="Кетчуп", price_delta=0),
        dict(id=1102, group_id=2, name="BBQ", price_delta=0),
        dict(id=1201, group_id=3, name="30 см", price_delta=0),
        dict(id=1202, group_id=3, name="40 см", price_delta=150),
    ]
    for o in options:
        db.add(Option(**o))
    db.commit()


def _seed_carts(db: Session) -> None:
    # создать пустые корзины для существующих пользователей, если позже будут
    pass

