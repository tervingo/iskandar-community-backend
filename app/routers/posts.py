from fastapi import APIRouter, HTTPException, status
from typing import List
from bson import ObjectId
from app.models.post import PostModel, PostCreate, PostUpdate, PostResponse
from app.database import get_collection
from datetime import datetime

router = APIRouter()

@router.get("/", response_model=List[PostResponse])
async def get_all_posts():
    collection = get_collection("posts")
    posts = []
    async for post in collection.find().sort("created_at", -1):
        # Convert ObjectId to string for the response
        post["_id"] = str(post["_id"])
        posts.append(PostResponse(**post))
    return posts

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: str):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    post = await collection.find_one({"_id": ObjectId(post_id)})
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Convert ObjectId to string for the response
    post["_id"] = str(post["_id"])
    return PostResponse(**post)

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post_data: PostCreate):
    collection = get_collection("posts")
    
    post_dict = post_data.dict()
    post_dict["created_at"] = datetime.utcnow()
    post_dict["updated_at"] = datetime.utcnow()
    
    result = await collection.insert_one(post_dict)
    created_post = await collection.find_one({"_id": result.inserted_id})
    
    # Convert ObjectId to string for the response
    created_post["_id"] = str(created_post["_id"])
    return PostResponse(**created_post)

@router.put("/{post_id}", response_model=PostResponse)
async def update_post(post_id: str, post_data: PostUpdate):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    
    update_data = {k: v for k, v in post_data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    
    result = await collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    
    updated_post = await collection.find_one({"_id": ObjectId(post_id)})
    # Convert ObjectId to string for the response
    updated_post["_id"] = str(updated_post["_id"])
    return PostResponse(**updated_post)

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: str):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    result = await collection.delete_one({"_id": ObjectId(post_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Also delete related comments
    comments_collection = get_collection("comments")
    await comments_collection.delete_many({"post_id": ObjectId(post_id)})