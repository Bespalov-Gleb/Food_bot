from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Category as OCategory, Dish as ODish, Option as OOption, OptionGroup as OGroup


router = APIRouter()


class Category(BaseModel):
    id: int
    restaurant_id: int
    name: str
    sort: int


class Dish(BaseModel):
    id: int
    restaurant_id: int
    category_id: int
    name: str
    description: str
    price: int
    image: str
    is_available: bool
    has_options: bool


class DishOption(BaseModel):
    id: int
    group_id: int
    name: str
    price_delta: int


class DishOptionGroup(BaseModel):
    id: int
    dish_id: int
    name: str
    min_select: int
    max_select: int
    required: bool


_CATEGORIES: List[Category] = []  # legacy placeholders
_DISHES: List[Dish] = []
_GROUPS: List[DishOptionGroup] = []
_OPTIONS: List[DishOption] = []


@router.get("/categories")
async def get_categories(restaurant_id: int, uid: Optional[int] = None, db: Session = Depends(get_db)) -> List[Category]:
    cats = db.query(OCategory).filter(OCategory.restaurant_id == restaurant_id).order_by(OCategory.sort.asc()).all()
    return [Category(id=c.id, restaurant_id=c.restaurant_id, name=c.name, sort=c.sort) for c in cats]


@router.get("/dishes")
async def get_dishes(restaurant_id: int, uid: Optional[int] = None, db: Session = Depends(get_db)) -> List[Dish]:
    dishes = db.query(ODish).filter(ODish.restaurant_id == restaurant_id).all()
    return [Dish(
        id=d.id, restaurant_id=d.restaurant_id, category_id=d.category_id, name=d.name,
        description=d.description, price=d.price, image=d.image, is_available=d.is_available, has_options=d.has_options
    ) for d in dishes]


@router.get("/restaurants/{restaurant_id}/menu")
async def get_menu(restaurant_id: int, db: Session = Depends(get_db)) -> Dict[str, List[dict]]:
    cats = db.query(OCategory).filter(OCategory.restaurant_id == restaurant_id).order_by(OCategory.sort.asc()).all()
    dishes = db.query(ODish).filter(ODish.restaurant_id == restaurant_id).all()
    return {
        "categories": [
            {"id": c.id, "restaurant_id": c.restaurant_id, "name": c.name, "sort": c.sort}
            for c in cats
        ],
        "dishes": [
            {
                "id": d.id,
                "restaurant_id": d.restaurant_id,
                "category_id": d.category_id,
                "name": d.name,
                "description": d.description,
                "price": d.price,
                "image": d.image,
                "is_available": d.is_available,
                "has_options": d.has_options,
            }
            for d in dishes
        ],
    }


@router.get("/dishes/{dish_id}")
async def get_dish(dish_id: int, db: Session = Depends(get_db)) -> Dish:
    d = db.query(ODish).filter(ODish.id == dish_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dish not found")
    return Dish(
        id=d.id, restaurant_id=d.restaurant_id, category_id=d.category_id, name=d.name,
        description=d.description, price=d.price, image=d.image, is_available=d.is_available, has_options=d.has_options
    )


@router.get("/dishes")
async def get_dishes_bulk(ids: str, db: Session = Depends(get_db)) -> List[Dish]:
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except Exception as exc:
        raise RuntimeError("Bad ids") from exc
    rows = db.query(ODish).filter(ODish.id.in_(id_list)).all()
    return [Dish(
        id=d.id, restaurant_id=d.restaurant_id, category_id=d.category_id, name=d.name,
        description=d.description, price=d.price, image=d.image, is_available=d.is_available, has_options=d.has_options
    ) for d in rows]


@router.get("/dishes/{dish_id}/options")
async def get_dish_options(dish_id: int, db: Session = Depends(get_db)) -> Dict[str, List[dict]]:
    groups = db.query(OGroup).filter(OGroup.dish_id == dish_id).all()
    group_ids = [g.id for g in groups]
    options = db.query(OOption).filter(OOption.group_id.in_(group_ids) if group_ids else False).all()
    return {
        "groups": [
            {"id": g.id, "dish_id": g.dish_id, "name": g.name, "min_select": g.min_select, "max_select": g.max_select, "required": g.required}
            for g in groups
        ],
        "options": [
            {"id": o.id, "group_id": o.group_id, "name": o.name, "price_delta": o.price_delta}
            for o in options
        ],
    }


@router.get("/options/lookup")
async def options_lookup(ids: str, db: Session = Depends(get_db)) -> List[DishOption]:
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip()]
    except Exception as exc:
        raise RuntimeError("Bad ids") from exc
    rows = db.query(OOption).filter(OOption.id.in_(id_list)).all()
    return [DishOption(id=o.id, group_id=o.group_id, name=o.name, price_delta=o.price_delta) for o in rows]

