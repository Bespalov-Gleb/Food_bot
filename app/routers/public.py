from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Collection as DBCollection, CollectionItem as DBCollectionItem, Restaurant as DBRestaurant, Dish as DBDish

router = APIRouter()


@router.get("/collections")
async def get_public_collections(db: Session = Depends(get_db)) -> List[dict]:
    """Получить все активные подборки для главной страницы"""
    collections = db.query(DBCollection).filter(DBCollection.is_enabled == True).order_by(DBCollection.sort_order, DBCollection.id).all()
    result = []
    
    for collection in collections:
        items = db.query(DBCollectionItem).filter(
            DBCollectionItem.collection_id == collection.id,
            DBCollectionItem.is_enabled == True
        ).order_by(DBCollectionItem.sort_order, DBCollectionItem.id).all()
        
        collection_items = []
        for item in items:
            # Получаем дополнительную информацию о ресторане или блюде
            item_data = {
                "id": item.id,
                "type": item.item_type,
                "item_id": item.item_id,
                "title": item.title,
                "subtitle": item.subtitle,
                "image": item.image,
                "link_url": item.link_url
            }
            
            if item.item_type == "restaurant":
                restaurant = db.query(DBRestaurant).filter(DBRestaurant.id == item.item_id).first()
                if restaurant:
                    item_data["restaurant"] = {
                        "id": restaurant.id,
                        "name": restaurant.name,
                        "rating": restaurant.rating_agg,
                        "delivery_min_sum": restaurant.delivery_min_sum,
                        "delivery_fee": restaurant.delivery_fee,
                        "delivery_time_minutes": restaurant.delivery_time_minutes
                    }
            elif item.item_type == "dish":
                dish = db.query(DBDish).filter(DBDish.id == item.item_id).first()
                if dish:
                    item_data["dish"] = {
                        "id": dish.id,
                        "name": dish.name,
                        "price": dish.price,
                        "description": dish.description
                    }
            
            collection_items.append(item_data)
        
        result.append({
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "image": collection.image,
            "items": collection_items
        })
    
    return result 