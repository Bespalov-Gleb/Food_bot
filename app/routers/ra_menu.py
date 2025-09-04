from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.routers.ra import require_restaurant_id
from app.routers.menu import Category, Dish
from app.routers.menu import DishOptionGroup, DishOption
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Category as OCategory, Dish as ODish, OptionGroup as OGroup, Option as OOption


router = APIRouter()


def update_dish_has_options(dish_id: int, db: Session):
    """Обновляет флаг has_options для блюда на основе количества групп опций"""
    groups_count = db.query(OGroup).filter(OGroup.dish_id == dish_id).count()
    dish = db.query(ODish).filter(ODish.id == dish_id).first()
    if dish:
        dish.has_options = groups_count > 0
        db.commit()


class CategoryCreate(BaseModel):
    name: str
    sort: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sort: Optional[int] = None


class DishCreate(BaseModel):
    category_id: int
    name: str
    description: str = ""
    price: int
    image: str = ""
    is_available: bool = True
    has_options: bool = False


class DishUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    image: Optional[str] = None
    is_available: Optional[bool] = None
    has_options: Optional[bool] = None


class GroupCreate(BaseModel):
    dish_id: int
    name: str
    min_select: int = 0
    max_select: int = 1
    required: bool = False


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    min_select: Optional[int] = None
    max_select: Optional[int] = None
    required: Optional[bool] = None


class OptionCreate(BaseModel):
    group_id: int
    name: str
    price_delta: int = 0


class OptionUpdate(BaseModel):
    name: Optional[str] = None
    price_delta: Optional[int] = None


@router.get("/ra/menu")
async def ra_menu(rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    cats = db.query(OCategory).filter(OCategory.restaurant_id == rid).order_by(OCategory.sort.asc()).all()
    dishes = db.query(ODish).filter(ODish.restaurant_id == rid).all()
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


@router.post("/ra/categories")
async def ra_create_category(payload: CategoryCreate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    last = db.query(OCategory).order_by(OCategory.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    cat = OCategory(id=new_id, restaurant_id=rid, name=payload.name, sort=payload.sort)
    db.add(cat)
    db.commit()
    return {"id": new_id}


@router.patch("/ra/categories/{category_id}")
async def ra_update_category(category_id: int, payload: CategoryUpdate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    c = db.query(OCategory).filter(OCategory.id == category_id, OCategory.restaurant_id == rid).first()
    if not c:
        raise HTTPException(status_code=404, detail="not_found")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in data:
        c.name = data["name"]
    if "sort" in data:
        c.sort = int(data["sort"])
    db.commit()
    return {"status": "ok"}


@router.delete("/ra/categories/{category_id}")
async def ra_delete_category(category_id: int, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    c = db.query(OCategory).filter(OCategory.id == category_id, OCategory.restaurant_id == rid).first()
    if not c:
        raise HTTPException(status_code=404, detail="not_found")
    # delete dishes in category
    db.query(ODish).filter(ODish.category_id == category_id).delete()
    db.delete(c)
    db.commit()
    return {"status": "ok"}


@router.post("/ra/dishes")
async def ra_create_dish(payload: DishCreate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    cat = db.query(OCategory).filter(OCategory.id == payload.category_id, OCategory.restaurant_id == rid).first()
    if not cat:
        raise HTTPException(status_code=400, detail="bad_category")
    last = db.query(ODish).order_by(ODish.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    dish = ODish(
        id=new_id,
        restaurant_id=rid,
        category_id=payload.category_id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        image=payload.image,
        is_available=payload.is_available,
        has_options=payload.has_options,
    )
    db.add(dish)
    db.commit()
    return {"id": new_id}


@router.patch("/ra/dishes/{dish_id}")
async def ra_update_dish(dish_id: int, payload: DishUpdate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    d = db.query(ODish).filter(ODish.id == dish_id, ODish.restaurant_id == rid).first()
    if not d:
        raise HTTPException(status_code=404, detail="not_found")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "category_id" in data:
        v = int(data["category_id"])  # type: ignore
        cat = db.query(OCategory).filter(OCategory.id == v, OCategory.restaurant_id == rid).first()
        if not cat:
            raise HTTPException(status_code=400, detail="bad_category")
        d.category_id = v
        data.pop("category_id", None)
    for k, v in data.items():
        if hasattr(d, k):
            setattr(d, k, v)
    db.commit()
    return {"status": "ok"}


@router.delete("/ra/dishes/{dish_id}")
async def ra_delete_dish(dish_id: int, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    d = db.query(ODish).filter(ODish.id == dish_id, ODish.restaurant_id == rid).first()
    if not d:
        return {"status": "not_found"}
    # delete groups and options for dish
    groups = db.query(OGroup).filter(OGroup.dish_id == dish_id).all()
    g_ids = [g.id for g in groups]
    if g_ids:
        db.query(OOption).filter(OOption.group_id.in_(g_ids)).delete(synchronize_session=False)
        db.query(OGroup).filter(OGroup.id.in_(g_ids)).delete(synchronize_session=False)
    db.delete(d)
    db.commit()
    return {"status": "ok"}


# option groups & options
@router.post("/ra/option-groups")
async def ra_create_group(payload: GroupCreate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    d = db.query(ODish).filter(ODish.id == payload.dish_id, ODish.restaurant_id == rid).first()
    if not d:
        raise HTTPException(status_code=400, detail="bad_dish")
    last = db.query(OGroup).order_by(OGroup.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    g = OGroup(id=new_id, dish_id=payload.dish_id, name=payload.name,
               min_select=payload.min_select, max_select=payload.max_select, required=payload.required)
    db.add(g)
    db.commit()
    
    # Обновляем флаг has_options для блюда
    update_dish_has_options(payload.dish_id, db)
    
    return {"id": new_id}


@router.patch("/ra/option-groups/{group_id}")
async def ra_update_group(group_id: int, payload: GroupUpdate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    g = db.query(OGroup).filter(OGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="not_found")
    d = db.query(ODish).filter(ODish.id == g.dish_id).first()
    if not d or d.restaurant_id != rid:
        raise HTTPException(status_code=403, detail="forbidden")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        if hasattr(g, k):
            setattr(g, k, v)
    db.commit()
    return {"status": "ok"}


@router.delete("/ra/option-groups/{group_id}")
async def ra_delete_group(group_id: int, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    g = db.query(OGroup).filter(OGroup.id == group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="not_found")
    d = db.query(ODish).filter(ODish.id == g.dish_id).first()
    if not d or d.restaurant_id != rid:
        raise HTTPException(status_code=403, detail="forbidden")
    db.query(OOption).filter(OOption.group_id == group_id).delete(synchronize_session=False)
    db.delete(g)
    db.commit()
    
    # Обновляем флаг has_options для блюда
    update_dish_has_options(g.dish_id, db)
    
    return {"status": "ok"}


@router.post("/ra/options")
async def ra_create_option(payload: OptionCreate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    g = db.query(OGroup).filter(OGroup.id == payload.group_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="group_not_found")
    d = db.query(ODish).filter(ODish.id == g.dish_id).first()
    if not d or d.restaurant_id != rid:
        raise HTTPException(status_code=403, detail="forbidden")
    last = db.query(OOption).order_by(OOption.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    o = OOption(id=new_id, group_id=payload.group_id, name=payload.name, price_delta=payload.price_delta)
    db.add(o)
    db.commit()
    return {"id": new_id}


@router.patch("/ra/options/{option_id}")
async def ra_update_option(option_id: int, payload: OptionUpdate, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(OOption).filter(OOption.id == option_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    g = db.query(OGroup).filter(OGroup.id == o.group_id).first()
    d = db.query(ODish).filter(ODish.id == (g.dish_id if g else -1)).first()
    if not d or d.restaurant_id != rid:
        raise HTTPException(status_code=403, detail="forbidden")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in data.items():
        if hasattr(o, k):
            setattr(o, k, v)
    db.commit()
    return {"status": "ok"}


@router.delete("/ra/options/{option_id}")
async def ra_delete_option(option_id: int, rid: int = Depends(require_restaurant_id), db: Session = Depends(get_db)) -> dict:
    o = db.query(OOption).filter(OOption.id == option_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="not_found")
    g = db.query(OGroup).filter(OGroup.id == o.group_id).first()
    d = db.query(ODish).filter(ODish.id == (g.dish_id if g else -1)).first()
    if not d or d.restaurant_id != rid:
        raise HTTPException(status_code=403, detail="forbidden")
    db.delete(o)
    db.commit()
    return {"status": "ok"}

