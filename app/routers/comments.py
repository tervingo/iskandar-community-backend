from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from bson import ObjectId
from datetime import datetime
from app.models.comment import CommentModel, CommentCreate, CommentUpdate, CommentResponse
from app.models.user import TokenData
from app.database import get_collection
from app.auth import get_current_active_user

router = APIRouter()

@router.get("/post/{post_id}", response_model=List[CommentResponse])
async def get_comments_for_post(post_id: str):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")
    
    collection = get_collection("comments")
    comments = []
    async for comment in collection.find({"post_id": ObjectId(post_id)}).sort("created_at", 1):
        # Convert ObjectId to string and map _id to id
        comment["id"] = str(comment["_id"])
        comment["_id"] = str(comment["_id"])
        comment["post_id"] = str(comment["post_id"])
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
    
    comment_dict = comment_data.model_dump()
    comment_dict["post_id"] = ObjectId(post_id)
    comment_dict["created_at"] = datetime.utcnow()
    
    result = await collection.insert_one(comment_dict)
    created_comment = await collection.find_one({"_id": result.inserted_id})
    
    # Convert ObjectId to string and map _id to id
    created_comment["id"] = str(created_comment["_id"])
    created_comment["_id"] = str(created_comment["_id"])
    created_comment["post_id"] = str(created_comment["post_id"])
    
    return CommentResponse(**created_comment)

@router.put("/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: str, 
    comment_data: CommentUpdate, 
    current_user: TokenData = Depends(get_current_active_user)
):
    if not ObjectId.is_valid(comment_id):
        raise HTTPException(status_code=400, detail="Invalid comment ID format")
    
    collection = get_collection("comments")
    
    # Find the comment
    comment = await collection.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check authorization: admin can edit any comment, regular users can only edit their own
    if current_user.role != "admin" and comment.get("author_name") != current_user.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own comments"
        )
    
    # Update the comment
    update_data = comment_data.model_dump()
    await collection.update_one(
        {"_id": ObjectId(comment_id)},
        {"$set": update_data}
    )
    
    # Get updated comment
    updated_comment = await collection.find_one({"_id": ObjectId(comment_id)})
    
    # Convert ObjectId to string
    updated_comment["id"] = str(updated_comment["_id"])
    updated_comment["_id"] = str(updated_comment["_id"])
    updated_comment["post_id"] = str(updated_comment["post_id"])
    
    return CommentResponse(**updated_comment)

@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: str, current_user: TokenData = Depends(get_current_active_user)):
    if not ObjectId.is_valid(comment_id):
        raise HTTPException(status_code=400, detail="Invalid comment ID format")
    
    collection = get_collection("comments")
    
    # Find the comment to check authorization
    comment = await collection.find_one({"_id": ObjectId(comment_id)})
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # Check authorization: admin can delete any comment, regular users can only delete their own
    if current_user.role != "admin" and comment.get("author_name") != current_user.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own comments"
        )
    
    # Delete the comment
    result = await collection.delete_one({"_id": ObjectId(comment_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Comment not found")