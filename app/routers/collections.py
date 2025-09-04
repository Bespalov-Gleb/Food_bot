from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps.auth import require_super_admin
from app.models import Collection as DBCollection, CollectionItem as DBCollectionItem, Restaurant as DBRestaurant, Dish as DBDish
from app.services.image_processor import ImageProcessor
from datetime import datetime

router = APIRouter()


class CollectionCreate(BaseModel):
    name: str
    description: str = ""
    image: str = ""
    is_enabled: bool = True
    sort_order: int = 0


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    is_enabled: Optional[bool] = None
    sort_order: Optional[int] = None


class CollectionItemCreate(BaseModel):
    collection_id: int
    item_type: str  # "restaurant" или "dish"
    item_id: int
    title: str
    subtitle: str = ""
    image: str = ""
    link_url: str = ""
    sort_order: int = 0
    is_enabled: bool = True


class CollectionItemUpdate(BaseModel):
    item_type: Optional[str] = None
    item_id: Optional[int] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    image: Optional[str] = None
    link_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_enabled: Optional[bool] = None


class CollectionResponse(BaseModel):
    id: int
    name: str
    description: str
    image: str
    is_enabled: bool
    sort_order: int
    created_at: datetime
    items_count: int


class CollectionItemResponse(BaseModel):
    id: int
    collection_id: int
    item_type: str
    item_id: int
    title: str
    subtitle: str
    image: str
    link_url: str
    sort_order: int
    is_enabled: bool
    item_name: Optional[str] = None  # Название ресторана или блюда


# CRUD для подборок
# API для получения списков ресторанов и блюд для выпадающих списков (публичные)
@router.get("/restaurants", dependencies=[])
async def get_restaurants_for_collections(db: Session = Depends(get_db)) -> List[dict]:
    """Получить список всех ресторанов для выпадающего списка"""
    try:
        restaurants = db.query(DBRestaurant).filter(DBRestaurant.is_enabled == True).order_by(DBRestaurant.name).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "image": r.image or ""
            }
            for r in restaurants
        ]
    except Exception as e:
        print(f"Error in get_restaurants_for_collections: {e}")
        return []


@router.get("/dishes", dependencies=[])
async def get_dishes_for_collections(restaurant_id: Optional[int] = None, db: Session = Depends(get_db)) -> List[dict]:
    """Получить список блюд для выпадающего списка"""
    try:
        query = db.query(DBDish).filter(DBDish.is_available == True)
        
        if restaurant_id:
            query = query.filter(DBDish.restaurant_id == restaurant_id)
        
        dishes = query.order_by(DBDish.name).all()
        
        result = []
        for dish in dishes:
            # Получаем название ресторана для блюда
            restaurant = db.query(DBRestaurant).filter(DBRestaurant.id == dish.restaurant_id).first()
            restaurant_name = restaurant.name if restaurant else "Неизвестный ресторан"
            
            result.append({
                "id": dish.id,
                "name": dish.name,
                "price": dish.price,
                "image": dish.image or "",
                "restaurant_id": dish.restaurant_id,
                "restaurant_name": restaurant_name
            })
        
        return result
    except Exception as e:
        print(f"Error in get_dishes_for_collections: {e}")
        return []
    

@router.get("")
async def list_collections(db: Session = Depends(get_db)) -> List[CollectionResponse]:
    collections = db.query(DBCollection).order_by(DBCollection.sort_order, DBCollection.id).all()
    result = []
    
    for collection in collections:
        items_count = db.query(DBCollectionItem).filter(DBCollectionItem.collection_id == collection.id).count()
        result.append(CollectionResponse(
            id=collection.id,
            name=collection.name,
            description=collection.description,
            image=collection.image,
            is_enabled=collection.is_enabled,
            sort_order=collection.sort_order,
            created_at=collection.created_at,
            items_count=items_count
        ))
    
    return result


@router.post("")
async def create_collection(payload: CollectionCreate, db: Session = Depends(get_db)) -> dict:
    # Генерируем ID
    last = db.query(DBCollection).order_by(DBCollection.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    
    collection = DBCollection(
        id=new_id,
        name=payload.name,
        description=payload.description,
        image=payload.image,
        is_enabled=payload.is_enabled,
        sort_order=payload.sort_order
    )
    
    db.add(collection)
    db.commit()
    
    return {"id": new_id, "status": "created"}


@router.get("/{collection_id}")
async def get_collection(collection_id: int, db: Session = Depends(get_db)) -> CollectionResponse:
    collection = db.query(DBCollection).filter(DBCollection.id == collection_id).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    items_count = db.query(DBCollectionItem).filter(DBCollectionItem.collection_id == collection_id).count()
    
    return CollectionResponse(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        image=collection.image,
        is_enabled=collection.is_enabled,
        sort_order=collection.sort_order,
        created_at=collection.created_at,
        items_count=items_count
    )


@router.patch("/{collection_id}")
async def update_collection(collection_id: int, payload: CollectionUpdate, db: Session = Depends(get_db)) -> dict:
    collection = db.query(DBCollection).filter(DBCollection.id == collection_id).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in update_data.items():
        setattr(collection, key, value)
    
    db.commit()
    return {"status": "updated"}


@router.delete("/{collection_id}")
async def delete_collection(collection_id: int, db: Session = Depends(get_db)) -> dict:
    collection = db.query(DBCollection).filter(DBCollection.id == collection_id).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Удаляем все элементы подборки
    db.query(DBCollectionItem).filter(DBCollectionItem.collection_id == collection_id).delete()
    
    # Удаляем подборку
    db.delete(collection)
    db.commit()
    
    return {"status": "deleted"}





# CRUD для элементов подборок
@router.get("/{collection_id}/items")
async def list_collection_items(collection_id: int, db: Session = Depends(get_db)) -> List[CollectionItemResponse]:
    items = db.query(DBCollectionItem).filter(DBCollectionItem.collection_id == collection_id).order_by(DBCollectionItem.sort_order, DBCollectionItem.id).all()
    result = []
    
    for item in items:
        # Получаем название ресторана или блюда
        item_name = None
        if item.item_type == "restaurant":
            restaurant = db.query(DBRestaurant).filter(DBRestaurant.id == item.item_id).first()
            item_name = restaurant.name if restaurant else None
        elif item.item_type == "dish":
            dish = db.query(DBDish).filter(DBDish.id == item.item_id).first()
            item_name = dish.name if dish else None
        
        result.append(CollectionItemResponse(
            id=item.id,
            collection_id=item.collection_id,
            item_type=item.item_type,
            item_id=item.item_id,
            title=item.title,
            subtitle=item.subtitle,
            image=item.image,
            link_url=item.link_url,
            sort_order=item.sort_order,
            is_enabled=item.is_enabled,
            item_name=item_name
        ))
    
    return result


@router.post("/{collection_id}/items")
async def create_collection_item(collection_id: int, payload: CollectionItemCreate, db: Session = Depends(get_db)) -> dict:
    # Проверяем существование подборки
    collection = db.query(DBCollection).filter(DBCollection.id == collection_id).first()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Проверяем существование ресторана или блюда
    if payload.item_type == "restaurant":
        restaurant = db.query(DBRestaurant).filter(DBRestaurant.id == payload.item_id).first()
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")
    elif payload.item_type == "dish":
        dish = db.query(DBDish).filter(DBDish.id == payload.item_id).first()
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")
    else:
        raise HTTPException(status_code=400, detail="Invalid item_type. Must be 'restaurant' or 'dish'")
    
    # Генерируем ID
    last = db.query(DBCollectionItem).order_by(DBCollectionItem.id.desc()).first()
    new_id = (last.id + 1) if last else 1
    
    item = DBCollectionItem(
        id=new_id,
        collection_id=collection_id,
        item_type=payload.item_type,
        item_id=payload.item_id,
        title=payload.title,
        subtitle=payload.subtitle,
        image=payload.image,
        link_url=payload.link_url,
        sort_order=payload.sort_order,
        is_enabled=payload.is_enabled
    )
    
    db.add(item)
    db.commit()
    
    return {"id": new_id, "status": "created"}


@router.patch("/{collection_id}/items/{item_id}")
async def update_collection_item(collection_id: int, item_id: int, payload: CollectionItemUpdate, db: Session = Depends(get_db)) -> dict:
    item = db.query(DBCollectionItem).filter(
        DBCollectionItem.id == item_id,
        DBCollectionItem.collection_id == collection_id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Collection item not found")
    
    update_data = payload.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    
    db.commit()
    return {"status": "updated"}


@router.delete("/{collection_id}/items/{item_id}")
async def delete_collection_item(collection_id: int, item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.query(DBCollectionItem).filter(
        DBCollectionItem.id == item_id,
        DBCollectionItem.collection_id == collection_id
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Collection item not found")
    
    db.delete(item)
    db.commit()
    
    return {"status": "deleted"}


@router.post("/upload-image")
async def upload_collection_image(image: UploadFile = File(...)) -> dict:
    """Загрузка изображения для элементов подборок с автоматической обработкой"""
    
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
            "image_url": result["urls"]["selection_card"],  # Основной URL для карточки подборки
            "urls": result["urls"],  # Все URL'ы для разных размеров
            "original_size": result["original_size"],
            "processed_sizes": result["processed_sizes"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке изображения: {str(e)}")


 