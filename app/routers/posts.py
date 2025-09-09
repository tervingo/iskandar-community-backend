from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from typing import List
from bson import ObjectId
from app.models.post import PostModel, PostCreate, PostUpdate, PostResponse, PostPublish
from app.models.user import TokenData
from app.database import get_collection
from app.auth import get_current_active_user
from app.services.email_service import email_service
from datetime import datetime

router = APIRouter()

async def populate_category_name(post):
    """Helper function to populate category name"""
    if post.get("category_id"):
        categories_collection = get_collection("categories")
        category = await categories_collection.find_one({"_id": ObjectId(post["category_id"])})
        if category:
            post["category_name"] = category["name"]
        else:
            post["category_name"] = "Unknown Category"
    else:
        post["category_name"] = None
    return post

@router.get("/", response_model=List[PostResponse])
async def get_all_posts(category_id: str = None):
    collection = get_collection("posts")
    posts = []
    
    # Build query filter - only show published posts
    # Handle legacy posts without is_published field by treating them as unpublished
    query = {"is_published": True}
    if category_id:
        if not ObjectId.is_valid(category_id):
            raise HTTPException(status_code=400, detail="Invalid category ID format")
        query["category_id"] = category_id
    
    async for post in collection.find(query).sort("published_at", -1):
        # Convert ObjectId to string and map _id to id
        post["id"] = str(post["_id"])
        post["_id"] = str(post["_id"])
        
        # Populate category name
        post = await populate_category_name(post)
        
        posts.append(PostResponse(**post))
    return posts

@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: str, current_user: TokenData = Depends(get_current_active_user)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    post = await collection.find_one({"_id": ObjectId(post_id)})
    
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Check if post is published or if user is the author or admin
    if not post.get("is_published", False):
        if current_user.role != "admin" and post.get("author_name") != current_user.name:
            raise HTTPException(status_code=404, detail="Post not found")
    
    # Convert ObjectId to string and map _id to id
    post["id"] = str(post["_id"])
    post["_id"] = str(post["_id"])
    
    # Populate category name
    post = await populate_category_name(post)
    
    return PostResponse(**post)

@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    post_data: PostCreate,
    background_tasks: BackgroundTasks
):
    collection = get_collection("posts")
    
    post_dict = post_data.model_dump()
    
    # Validate category_id if provided
    if post_dict.get("category_id"):
        if not ObjectId.is_valid(post_dict["category_id"]):
            raise HTTPException(status_code=400, detail="Invalid category ID format")
        
        categories_collection = get_collection("categories")
        category = await categories_collection.find_one({"_id": ObjectId(post_dict["category_id"]), "is_active": True})
        if not category:
            raise HTTPException(status_code=400, detail="Category not found or inactive")
    
    post_dict["created_at"] = datetime.utcnow()
    post_dict["updated_at"] = datetime.utcnow()
    
    # Set published_at if the post is being published
    if post_dict.get("is_published", False):
        post_dict["published_at"] = datetime.utcnow()
    else:
        post_dict["published_at"] = None
    
    result = await collection.insert_one(post_dict)
    created_post = await collection.find_one({"_id": result.inserted_id})
    
    # Convert ObjectId to string and map _id to id
    created_post["id"] = str(created_post["_id"])
    created_post["_id"] = str(created_post["_id"])
    
    # Populate category name
    created_post = await populate_category_name(created_post)
    
    # Send email notification if post is published
    if created_post.get("is_published", False):
        background_tasks.add_task(email_service.send_new_post_notification, created_post)
    
    return PostResponse(**created_post)

@router.put("/{post_id}", response_model=PostResponse)
async def update_post(post_id: str, post_data: PostUpdate):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    
    update_data = {k: v for k, v in post_data.model_dump().items() if v is not None}
    
    # Validate category_id if provided
    if "category_id" in update_data and update_data["category_id"]:
        if not ObjectId.is_valid(update_data["category_id"]):
            raise HTTPException(status_code=400, detail="Invalid category ID format")
        
        categories_collection = get_collection("categories")
        category = await categories_collection.find_one({"_id": ObjectId(update_data["category_id"]), "is_active": True})
        if not category:
            raise HTTPException(status_code=400, detail="Category not found or inactive")
    
    update_data["updated_at"] = datetime.utcnow()
    
    # Handle publishing/unpublishing
    if "is_published" in update_data:
        if update_data["is_published"]:
            # Publishing the post - set published_at timestamp
            existing_post = await collection.find_one({"_id": ObjectId(post_id)})
            if not existing_post.get("published_at"):
                update_data["published_at"] = datetime.utcnow()
        else:
            # Unpublishing the post - keep published_at for history
            pass
    
    result = await collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    
    updated_post = await collection.find_one({"_id": ObjectId(post_id)})
    # Convert ObjectId to string and map _id to id
    updated_post["id"] = str(updated_post["_id"])
    updated_post["_id"] = str(updated_post["_id"])
    
    # Populate category name
    updated_post = await populate_category_name(updated_post)
    
    return PostResponse(**updated_post)

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: str, current_user: TokenData = Depends(get_current_active_user)):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    
    # First check if post exists and get its details
    post = await collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Check if current user is the author or an admin
    post_author_name = post.get("author_name")
    
    # Check authorization: admin can delete any post, regular users can only delete their own posts
    if current_user.role != "admin" and post_author_name != current_user.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own posts"
        )
    
    result = await collection.delete_one({"_id": ObjectId(post_id)})
    
    # Also delete related comments
    comments_collection = get_collection("comments")
    await comments_collection.delete_many({"post_id": ObjectId(post_id)})

@router.get("/drafts/my", response_model=List[PostResponse])
async def get_my_drafts(current_user: TokenData = Depends(get_current_active_user)):
    """Get all draft posts by the current user"""
    collection = get_collection("posts")
    posts = []
    
    # Build query filter - only drafts by current user
    # Include legacy posts without is_published field (treat as drafts)
    query = {
        "$and": [
            {"author_name": current_user.name},
            {
                "$or": [
                    {"is_published": False},
                    {"is_published": {"$exists": False}}
                ]
            }
        ]
    }
    
    async for post in collection.find(query).sort("updated_at", -1):
        # Convert ObjectId to string and map _id to id
        post["id"] = str(post["_id"])
        post["_id"] = str(post["_id"])
        
        # Populate category name
        post = await populate_category_name(post)
        
        posts.append(PostResponse(**post))
    return posts

@router.put("/{post_id}/publish", response_model=PostResponse)
async def publish_post(
    post_id: str, 
    publish_data: PostPublish, 
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Publish or unpublish a post"""
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("posts")
    
    # First check if post exists and get its details
    post = await collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Check authorization: only author or admin can publish/unpublish
    if current_user.role != "admin" and post.get("author_name") != current_user.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only publish/unpublish your own posts"
        )
    
    update_data = {
        "is_published": publish_data.is_published,
        "updated_at": datetime.utcnow()
    }
    
    # Set published_at timestamp when publishing
    if publish_data.is_published and not post.get("published_at"):
        update_data["published_at"] = datetime.utcnow()
    
    result = await collection.update_one(
        {"_id": ObjectId(post_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")
    
    updated_post = await collection.find_one({"_id": ObjectId(post_id)})
    # Convert ObjectId to string and map _id to id
    updated_post["id"] = str(updated_post["_id"])
    updated_post["_id"] = str(updated_post["_id"])
    
    # Populate category name
    updated_post = await populate_category_name(updated_post)
    
    # Send email notification if post is newly published
    was_published = post.get("is_published", False)
    is_now_published = updated_post.get("is_published", False)
    
    if not was_published and is_now_published:
        background_tasks.add_task(email_service.send_new_post_notification, updated_post)
    
    return PostResponse(**updated_post)