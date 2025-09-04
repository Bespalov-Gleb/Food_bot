from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Literal


router = APIRouter()


class SelectionItem(BaseModel):
    title: str
    image: str
    restaurant_id: int | None = None
    dish_id: int | None = None


class Selection(BaseModel):
    id: int
    title: str
    kind: Literal["dishes", "restaurants"]
    items: List[SelectionItem]


_SELECTIONS: List[Selection] = [
    Selection(
        id=1,
        title="Выбор пользователей",
        kind="dishes",
        items=[
            SelectionItem(
                title="Бургер",
                image="https://images.unsplash.com/photo-1550547660-d9450f859349?w=640&q=80&auto=format&fit=crop",
                dish_id=102,
                restaurant_id=1,
            ),
            SelectionItem(
                title="Маргарита",
                image="https://images.unsplash.com/photo-1548365328-9953d527a7c7?w=640&q=80&auto=format&fit=crop",
                dish_id=201,
                restaurant_id=2,
            ),
            SelectionItem(
                title="Филадельфия",
                image="https://images.unsplash.com/photo-1542736667-069246bdbc74?w=640&q=80&auto=format&fit=crop",
                dish_id=401,
                restaurant_id=4,
            ),
            SelectionItem(
                title="Пепперони",
                image="https://images.unsplash.com/photo-1548365328-7a9f3e0a9c5e?w=640&q=80&auto=format&fit=crop",
                dish_id=301,
                restaurant_id=3,
            ),
        ],
    ),
    Selection(
        id=2,
        title="Топ-рестораны",
        kind="restaurants",
        items=[
            SelectionItem(title="Вкусно и точка", image="https://images.unsplash.com/photo-1550547660-71a38c4aa3b5?w=640&q=80&auto=format&fit=crop", restaurant_id=1),
            SelectionItem(title="Чиббис", image="https://images.unsplash.com/photo-1513104890138-7c749659a591?w=640&q=80&auto=format&fit=crop", restaurant_id=2),
            SelectionItem(title="Пиццерия Браво", image="https://images.unsplash.com/photo-1542281286-9e0a16bb7366?w=640&q=80&auto=format&fit=crop", restaurant_id=3),
            SelectionItem(title="СушиМания", image="https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=640&q=80&auto=format&fit=crop", restaurant_id=4),
        ],
    ),
]


@router.get("/selections")
async def list_selections() -> List[Selection]:
    return _SELECTIONS

