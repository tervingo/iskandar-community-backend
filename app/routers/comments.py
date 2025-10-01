from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from typing import List, Dict, Any
from bson import ObjectId
from datetime import datetime
from app.models.comment import CommentModel, CommentCreate, CommentUpdate, CommentResponse
from app.models.user import TokenData
from app.database import get_collection
from app.auth import get_current_active_user
from app.services.email_service import email_service
import logging
import os

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/post/{post_id}", response_model=List[CommentResponse])
async def get_comments_for_post(post_id: str):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")

    collection = get_collection("comments")

    # Get all comments for the post
    all_comments = []
    async for comment in collection.find({"post_id": ObjectId(post_id)}).sort("created_at", 1):
        # Convert ObjectId to string and map _id to id
        comment["id"] = str(comment["_id"])
        comment["_id"] = str(comment["_id"])
        comment["post_id"] = str(comment["post_id"])
        if comment.get("parent_id"):
            comment["parent_id"] = str(comment["parent_id"])
        all_comments.append(comment)

    # Organize comments into nested structure
    comments_dict = {}
    root_comments = []

    # First pass: create all comment objects
    for comment in all_comments:
        comment_obj = CommentResponse(**comment)
        comments_dict[comment["id"]] = comment_obj

        # If this is a root comment (no parent), add to root list
        if not comment.get("parent_id"):
            root_comments.append(comment_obj)

    # Second pass: attach replies to their parents
    for comment in all_comments:
        if comment.get("parent_id"):
            parent_id = comment["parent_id"]
            if parent_id in comments_dict:
                parent_comment = comments_dict[parent_id]
                reply_comment = comments_dict[comment["id"]]
                parent_comment.replies.append(reply_comment)

    return root_comments

@router.post("/post/{post_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def create_comment(post_id: str, comment_data: CommentCreate, background_tasks: BackgroundTasks):
    if not ObjectId.is_valid(post_id):
        raise HTTPException(status_code=400, detail="Invalid post ID format")

    # Check if post exists
    posts_collection = get_collection("posts")
    post = await posts_collection.find_one({"_id": ObjectId(post_id)})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # If this is a reply, validate parent comment exists
    parent_comment = None
    if comment_data.parent_id:
        if not ObjectId.is_valid(comment_data.parent_id):
            raise HTTPException(status_code=400, detail="Invalid parent comment ID format")

        collection = get_collection("comments")
        parent_comment = await collection.find_one({"_id": ObjectId(comment_data.parent_id)})
        if not parent_comment:
            raise HTTPException(status_code=404, detail="Parent comment not found")

        # Make sure parent belongs to the same post
        if str(parent_comment["post_id"]) != post_id:
            raise HTTPException(status_code=400, detail="Parent comment does not belong to this post")

    collection = get_collection("comments")

    comment_dict = comment_data.model_dump()
    comment_dict["post_id"] = ObjectId(post_id)
    comment_dict["created_at"] = datetime.utcnow()

    # Convert parent_id to ObjectId if present
    if comment_dict.get("parent_id"):
        comment_dict["parent_id"] = ObjectId(comment_dict["parent_id"])

    result = await collection.insert_one(comment_dict)
    created_comment = await collection.find_one({"_id": result.inserted_id})

    # Convert ObjectId to string and map _id to id
    created_comment["id"] = str(created_comment["_id"])
    created_comment["_id"] = str(created_comment["_id"])
    created_comment["post_id"] = str(created_comment["post_id"])
    if created_comment.get("parent_id"):
        created_comment["parent_id"] = str(created_comment["parent_id"])

    # Send email notification if this is a reply to another comment
    if parent_comment and comment_data.parent_id:
        background_tasks.add_task(
            send_comment_reply_notification,
            parent_comment,
            created_comment,
            post
        )

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


async def send_comment_reply_notification(parent_comment: Dict[str, Any], reply_comment: Dict[str, Any], post: Dict[str, Any]):
    """Send email notification when someone replies to a comment"""
    try:
        # Get the parent comment author's email
        parent_author_email = parent_comment.get("author_email")
        parent_author_name = parent_comment.get("author_name", "Usuario")

        if not parent_author_email:
            logger.info(f"No email found for parent comment author: {parent_author_name}")
            return

        # Check if the parent author has email notifications enabled for comment replies
        users_collection = get_collection("users")
        parent_user = await users_collection.find_one({"email": parent_author_email})

        if not parent_user:
            logger.info(f"Parent comment author not found in users collection: {parent_author_email}")
            return

        # Check email preferences (default to True if not set)
        email_prefs = parent_user.get("email_preferences", {})
        if not email_prefs.get("comment_replies", True):
            logger.info(f"User {parent_author_email} has disabled comment reply notifications")
            return

        # Don't send notification if user is replying to their own comment
        reply_author_email = reply_comment.get("author_email")
        if parent_author_email == reply_author_email:
            logger.info("User replying to their own comment, skipping notification")
            return

        # Prepare email context
        reply_author_name = reply_comment.get("author_name", "Un usuario")
        post_title = post.get("title", "Sin título")
        post_url = f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/blog/{post['_id']}#comments"

        context = {
            "parent_author_name": parent_author_name,
            "reply_author_name": reply_author_name,
            "parent_comment_content": parent_comment.get("content", "")[:200] + "..." if len(parent_comment.get("content", "")) > 200 else parent_comment.get("content", ""),
            "reply_content": reply_comment.get("content", "")[:200] + "..." if len(reply_comment.get("content", "")) > 200 else reply_comment.get("content", ""),
            "post_title": post_title,
            "post_url": post_url,
            "site_name": "Yskandar",
            "unsubscribe_url": f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/profile"
        }

        # Render email template
        html_body = email_service._render_template("comment_reply_notification.html", context)

        # Send email
        subject = f"💬 {reply_author_name} respondió a tu comentario en '{post_title}'"
        success = await email_service.send_email(
            recipients=[parent_author_email],
            subject=subject,
            html_body=html_body
        )

        if success:
            logger.info(f"Comment reply notification sent successfully to {parent_author_email}")
        else:
            logger.error(f"Failed to send comment reply notification to {parent_author_email}")

    except Exception as e:
        logger.error(f"Error sending comment reply notification: {e}")