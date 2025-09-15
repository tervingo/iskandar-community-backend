from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from bson import ObjectId
from datetime import datetime
from app.models.news import NewsModel, NewsCreate, NewsUpdate, NewsResponse
from app.database import get_collection
from app.auth import get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/", response_model=List[NewsResponse])
async def get_all_news():
    """Get all news articles, sorted by creation date (newest first)"""
    collection = get_collection("news")
    news_list = []

    async for news_doc in collection.find().sort("created_at", -1):
        # Convert ObjectId to string and map _id to id
        news_doc["id"] = str(news_doc["_id"])
        news_doc["_id"] = str(news_doc["_id"])
        news_list.append(NewsResponse(**news_doc))

    return news_list

@router.get("/{news_id}", response_model=NewsResponse)
async def get_news_by_id(news_id: str):
    """Get a specific news article by ID"""
    if not ObjectId.is_valid(news_id):
        raise HTTPException(status_code=400, detail="Invalid news ID format")

    collection = get_collection("news")
    news_doc = await collection.find_one({"_id": ObjectId(news_id)})

    if not news_doc:
        raise HTTPException(status_code=404, detail="News article not found")

    # Convert ObjectId to string and map _id to id
    news_doc["id"] = str(news_doc["_id"])
    news_doc["_id"] = str(news_doc["_id"])

    return NewsResponse(**news_doc)

@router.post("/", response_model=NewsResponse, status_code=status.HTTP_201_CREATED)
async def create_news(news_data: NewsCreate, current_user: User = Depends(get_current_user)):
    """Create a new news article (authenticated users only)"""

    # Override created_by with authenticated user's name
    news_data_dict = news_data.model_dump()
    news_data_dict["created_by"] = current_user.name
    news_data_dict["created_at"] = datetime.utcnow()

    try:
        collection = get_collection("news")
        result = await collection.insert_one(news_data_dict)
        created_news = await collection.find_one({"_id": result.inserted_id})

        # Convert ObjectId to string and map _id to id
        created_news["id"] = str(created_news["_id"])
        created_news["_id"] = str(created_news["_id"])

        return NewsResponse(**created_news)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create news article: {str(e)}")

@router.put("/{news_id}", response_model=NewsResponse)
async def update_news(news_id: str, news_update: NewsUpdate, current_user: User = Depends(get_current_user)):
    """Update a news article (only by creator or admin)"""
    if not ObjectId.is_valid(news_id):
        raise HTTPException(status_code=400, detail="Invalid news ID format")

    collection = get_collection("news")
    existing_news = await collection.find_one({"_id": ObjectId(news_id)})

    if not existing_news:
        raise HTTPException(status_code=404, detail="News article not found")

    # Check permissions: only creator or admin can update
    if existing_news["created_by"] != current_user.name and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only edit your own news articles"
        )

    # Prepare update data (only include non-None values)
    update_data = {k: v for k, v in news_update.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields provided for update")

    # Add updated_at timestamp
    update_data["updated_at"] = datetime.utcnow()

    try:
        await collection.update_one(
            {"_id": ObjectId(news_id)},
            {"$set": update_data}
        )

        updated_news = await collection.find_one({"_id": ObjectId(news_id)})

        # Convert ObjectId to string and map _id to id
        updated_news["id"] = str(updated_news["_id"])
        updated_news["_id"] = str(updated_news["_id"])

        return NewsResponse(**updated_news)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update news article: {str(e)}")

@router.delete("/{news_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_news(news_id: str, current_user: User = Depends(get_current_user)):
    """Delete a news article (only by creator or admin)"""
    if not ObjectId.is_valid(news_id):
        raise HTTPException(status_code=400, detail="Invalid news ID format")

    collection = get_collection("news")
    existing_news = await collection.find_one({"_id": ObjectId(news_id)})

    if not existing_news:
        raise HTTPException(status_code=404, detail="News article not found")

    # Check permissions: only creator or admin can delete
    if existing_news["created_by"] != current_user.name and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own news articles"
        )

    try:
        await collection.delete_one({"_id": ObjectId(news_id)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete news article: {str(e)}")