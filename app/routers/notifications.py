from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from app.models.notification import EmailNotificationCreate, EmailNotificationResponse, EmailPreferencesUpdate
from app.models.user import TokenData, UserRole, EmailPreferences
from app.auth import get_current_active_user
from app.database import get_collection
from app.services.email_service import email_service
from bson import ObjectId

router = APIRouter()

@router.post("/admin/broadcast", response_model=EmailNotificationResponse)
async def send_admin_broadcast(
    notification: EmailNotificationCreate,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Send admin broadcast email to all users"""
    
    # Check if user is admin
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can send broadcast notifications"
        )
    
    try:
        result = await email_service.send_admin_broadcast(
            subject=notification.subject,
            message=notification.message,
            sender_name=current_user.name,
            include_unsubscribed=notification.include_unsubscribed
        )
        
        return EmailNotificationResponse(**result)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send broadcast notification: {str(e)}"
        )

@router.get("/admin/recipients")
async def get_broadcast_recipients(
    include_unsubscribed: bool = False,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get list of users who would receive admin broadcasts"""
    
    # Check if user is admin
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view recipient lists"
        )
    
    try:
        if include_unsubscribed:
            # Get all active users
            collection = get_collection("users")
            users = []
            async for user in collection.find({"is_active": True}):
                users.append({
                    "id": str(user["_id"]),
                    "name": user["name"],
                    "email": user["email"],
                    "subscribed": user.get("email_preferences", {}).get("admin_notifications", True)
                })
        else:
            # Get only subscribed users
            users_data = await email_service.get_all_active_users()
            users = [
                {
                    "id": user["id"],
                    "name": user["name"], 
                    "email": user["email"],
                    "subscribed": True
                }
                for user in users_data
            ]
        
        return {
            "total_users": len(users),
            "subscribed_count": sum(1 for user in users if user.get("subscribed", True)),
            "users": users
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recipient list: {str(e)}"
        )

@router.put("/preferences", response_model=dict)
async def update_email_preferences(
    preferences: EmailPreferencesUpdate,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Update current user's email notification preferences"""
    
    try:
        collection = get_collection("users")
        
        # Get current preferences
        user = await collection.find_one({"_id": ObjectId(current_user.user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update only provided preferences
        current_prefs = user.get("email_preferences", {})
        
        update_data = {}
        if preferences.new_posts is not None:
            update_data["email_preferences.new_posts"] = preferences.new_posts
        if preferences.admin_notifications is not None:
            update_data["email_preferences.admin_notifications"] = preferences.admin_notifications
        if preferences.comment_replies is not None:
            update_data["email_preferences.comment_replies"] = preferences.comment_replies
        if preferences.weekly_digest is not None:
            update_data["email_preferences.weekly_digest"] = preferences.weekly_digest
        
        if update_data:
            result = await collection.update_one(
                {"_id": ObjectId(current_user.user_id)},
                {"$set": update_data}
            )
            
            if result.matched_count == 0:
                raise HTTPException(status_code=404, detail="User not found")
        
        # Get updated user data
        updated_user = await collection.find_one({"_id": ObjectId(current_user.user_id)})
        
        return {
            "success": True,
            "message": "Email preferences updated successfully",
            "preferences": updated_user.get("email_preferences", {})
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update email preferences: {str(e)}"
        )

@router.get("/preferences")
async def get_email_preferences(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get current user's email notification preferences"""
    
    try:
        collection = get_collection("users")
        user = await collection.find_one({"_id": ObjectId(current_user.user_id)})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Return preferences with defaults
        preferences = user.get("email_preferences", {})
        default_prefs = EmailPreferences()
        
        return {
            "new_posts": preferences.get("new_posts", default_prefs.new_posts),
            "admin_notifications": preferences.get("admin_notifications", default_prefs.admin_notifications),
            "comment_replies": preferences.get("comment_replies", default_prefs.comment_replies),
            "weekly_digest": preferences.get("weekly_digest", default_prefs.weekly_digest)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get email preferences: {str(e)}"
        )

@router.get("/test/new-post")
async def test_new_post_notification(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Test endpoint to send a sample new post notification"""
    
    # Only allow admins to test
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can test notifications"
        )
    
    # Create sample post data
    sample_post = {
        "id": "test-post-id",
        "title": "Test Post Notification",
        "content": "This is a test post to verify email notifications are working correctly.",
        "author_name": current_user.name,
        "category_name": "Test Category",
        "is_published": True
    }
    
    try:
        success = await email_service.send_new_post_notification(sample_post)
        
        return {
            "success": success,
            "message": "Test notification sent successfully" if success else "Failed to send test notification"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Error sending test notification: {str(e)}"
        }