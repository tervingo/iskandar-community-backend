from fastapi import APIRouter, HTTPException, status
from typing import List
from bson import ObjectId
from app.models.comment import CommentModel, CommentCreate, CommentResponse
from app.database import get_collection

router = APIRouter()

@router.get("/post/{post_id}", response_model=List[CommentResponse])
async def get_comments_for_post(post_id: str):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("comments")
    comments = []
    async for comment in collection.find({"post_id": ObjectId(post_id)}).sort("created_at", 1):
        comments.append(CommentResponse(**comment))
    return comments

@router.post("/post/{post_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(post_id: str, comment_data: CommentCreate):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    # Check if post exists
    posts_collection = get_collection("posts")
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    collection = get_collection("comments")
    
    comment_dict = comment_data.dict()
    comment_dict["post_id"] = ObjectId(post_id)
    
    result = await collection.insert_one(comment_dict)
    created_comment = await collection.find_one({"_id": result.inserted_id})
    
    return CommentResponse(**created_comment)

@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: str):
    if not ObjectId.is_valid(comment_id):
        raise HTTPException(status_code=400, detail="Invalid comment ID format")
    
    collection = get_collection("comments")
    result = await collection.delete_one({"_id": ObjectId(comment_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Comment not found")