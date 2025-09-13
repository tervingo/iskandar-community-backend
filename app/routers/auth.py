from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Dict, Any
import json
from bson import ObjectId
from app.models.user import (
    UserModel, UserCreate, UserUpdate, UserResponse, 
    UserLogin, UserProfile, PasswordChange, TokenData, UserRole
)
from app.database import get_collection
from app.auth import (
    authenticate_user, create_user_token, hash_password, verify_password,
    get_current_active_user, get_current_admin_user
)
from datetime import datetime, timedelta
from app.utils.presence import get_online_users, cleanup_offline_users, is_user_online

router = APIRouter()


@router.post("/login")
async def login(user_credentials: UserLogin):
    """Authenticate user and return JWT token"""
    try:
        user = await authenticate_user(user_credentials.name, user_credentials.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect name or password"
            )

        # Update last_seen timestamp on login
        users_collection = get_collection("users")
        await users_collection.update_one(
            {"_id": ObjectId(user["_id"])},
            {"$set": {"last_seen": datetime.utcnow()}}
        )

        access_token = create_user_token(user)

        response_data = {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "avatar": user.get("avatar"),
                "is_active": user.get("is_active", True)
            }
        }
        return response_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during login"
        )

@router.post("/heartbeat")
async def heartbeat(current_user: TokenData = Depends(get_current_active_user)):
    """Update user's last_seen timestamp for presence tracking"""
    try:
        users_collection = get_collection("users")
        timestamp = datetime.utcnow()
        result = await users_collection.update_one(
            {"_id": ObjectId(current_user.user_id)},
            {"$set": {"last_seen": timestamp}}
        )
        print(f"Heartbeat for user {current_user.user_id} - matched: {result.matched_count}, modified: {result.modified_count}, timestamp: {timestamp}")  # Debug log
        return {"status": "success", "timestamp": timestamp}
    except Exception as e:
        print(f"Error in heartbeat: {e}")  # Debug log
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating presence"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: TokenData = Depends(get_current_active_user)):
    """Get current user profile"""
    users_collection = get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(current_user.user_id)})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user["_id"] = str(user["_id"])
    # Ensure required fields exist with defaults
    user.setdefault("is_active", True)
    user.setdefault("avatar", None)
    user.setdefault("phone", None)
    user.setdefault("last_seen", None)
    # Set default email preferences for existing users
    user.setdefault("email_preferences", {
        "new_posts": True,
        "admin_notifications": True,
        "comment_replies": True,
        "weekly_digest": False
    })
    return UserResponse(**user)

@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    profile_data: UserProfile,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Update current user profile"""
    users_collection = get_collection("users")
    
    update_data = {k: v for k, v in profile_data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    
    result = await users_collection.update_one(
        {"_id": ObjectId(current_user.user_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = await users_collection.find_one({"_id": ObjectId(current_user.user_id)})
    updated_user["_id"] = str(updated_user["_id"])
    return UserResponse(**updated_user)

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Change user password"""
    users_collection = get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(current_user.user_id)})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify current password
    if not verify_password(password_data.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Update password
    new_password_hash = hash_password(password_data.new_password)
    await users_collection.update_one(
        {"_id": ObjectId(current_user.user_id)},
        {"$set": {"password_hash": new_password_hash, "updated_at": datetime.utcnow()}}
    )
    
    return {"message": "Password changed successfully"}

# Admin-only endpoints
@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Create new user (Admin only)"""
    users_collection = get_collection("users")
    
    # Check if email already exists
    existing_email = await users_collection.find_one({"email": user_data.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if name already exists (since names are used for login)
    existing_name = await users_collection.find_one({"name": user_data.name})
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name already taken. Please choose a different name."
        )
    
    # Create user
    user_dict = user_data.model_dump(exclude={"password"})
    user_dict["password_hash"] = hash_password(user_data.password)
    user_dict["created_at"] = datetime.utcnow()
    user_dict["updated_at"] = datetime.utcnow()
    # Ensure required fields are set in the database
    user_dict["is_active"] = True  # Force set instead of setdefault
    user_dict.setdefault("avatar", None)
    user_dict.setdefault("phone", None)
    # Set default email preferences for new users
    user_dict["email_preferences"] = {
        "new_posts": True,
        "admin_notifications": True,
        "comment_replies": True,
        "weekly_digest": False
    }
    
    result = await users_collection.insert_one(user_dict)
    created_user = await users_collection.find_one({"_id": result.inserted_id})
    
    created_user["_id"] = str(created_user["_id"])
    return UserResponse(**created_user)

@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Get all users (Admin only)"""
    try:
        users_collection = get_collection("users")
        users = []
        
        async for user in users_collection.find().sort("created_at", -1):
            user["_id"] = str(user["_id"])
            # Ensure required fields exist with defaults
            user.setdefault("is_active", True)
            user.setdefault("avatar", None)
            user.setdefault("phone", None)
            # Set default email preferences for existing users
            user.setdefault("email_preferences", {
                "new_posts": True,
                "admin_notifications": True,
                "comment_replies": True,
                "weekly_digest": False
            })
            users.append(UserResponse(**user))
        
        return users
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Get user by ID (Admin only)"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    users_collection = get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user["_id"] = str(user["_id"])
    # Ensure required fields exist with defaults
    user.setdefault("is_active", True)
    user.setdefault("avatar", None)
    user.setdefault("phone", None)
    user.setdefault("last_seen", None)
    # Set default email preferences for existing users
    user.setdefault("email_preferences", {
        "new_posts": True,
        "admin_notifications": True,
        "comment_replies": True,
        "weekly_digest": False
    })
    return UserResponse(**user)

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Update user (Admin only)"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    users_collection = get_collection("users")
    
    # Check if email already exists for a different user
    if user_data.email:
        existing_email = await users_collection.find_one({
            "email": user_data.email,
            "_id": {"$ne": ObjectId(user_id)}
        })
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    # Check if name already exists for a different user
    if user_data.name:
        existing_name = await users_collection.find_one({
            "name": user_data.name,
            "_id": {"$ne": ObjectId(user_id)}
        })
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Name already taken. Please choose a different name."
            )
    
    update_data = {k: v for k, v in user_data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    updated_user = await users_collection.find_one({"_id": ObjectId(user_id)})
    updated_user["_id"] = str(updated_user["_id"])
    return UserResponse(**updated_user)

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Delete user (Admin only)"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    # Prevent admin from deleting themselves
    if user_id == current_admin.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    users_collection = get_collection("users")
    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "User deleted successfully"}

@router.post("/users/{user_id}/toggle-status")
async def toggle_user_status(
    user_id: str,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Toggle user active/inactive status (Admin only)"""
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID format")
    
    # Prevent admin from deactivating themselves
    if user_id == current_admin.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own account status"
        )
    
    users_collection = get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    new_status = not user.get("is_active", True)
    
    await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_active": new_status, "updated_at": datetime.utcnow()}}
    )
    
    action = "activated" if new_status else "deactivated"
    return {"message": f"User {action} successfully"}

@router.get("/online-users")
async def get_currently_online_users(current_user: TokenData = Depends(get_current_active_user)):
    """Get list of currently online users"""
    try:
        online_users = await get_online_users()
        print(f"Online users endpoint called - found {len(online_users)} users")  # Debug log
        for user in online_users:
            print(f"  - {user['name']} (last_seen: {user['last_seen']})")  # Debug log
        return {"online_users": online_users, "count": len(online_users)}
    except Exception as e:
        print(f"Error in get_currently_online_users: {e}")  # Debug log
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching online users"
        )

@router.post("/cleanup-offline")
async def cleanup_offline_users_endpoint(current_admin: TokenData = Depends(get_current_admin_user)):
    """Cleanup offline users (Admin only)"""
    try:
        count = await cleanup_offline_users()
        return {"message": f"Marked {count} users as offline"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error cleaning up offline users"
        )

@router.get("/debug-users")
async def debug_users_presence(current_admin: TokenData = Depends(get_current_admin_user)):
    """Debug endpoint to check all users and their last_seen status (Admin only)"""
    try:
        users_collection = get_collection("users")
        threshold = datetime.utcnow() - timedelta(minutes=5)  # 5 minute threshold

        debug_info = []
        async for user in users_collection.find({}, {"name": 1, "last_seen": 1, "is_active": 1}):
            debug_info.append({
                "id": str(user["_id"]),
                "name": user.get("name"),
                "last_seen": user.get("last_seen"),
                "is_active": user.get("is_active", True),
                "is_online": user.get("last_seen") and user.get("last_seen") > threshold if user.get("last_seen") else False
            })

        return {
            "threshold": threshold,
            "current_time": datetime.utcnow(),
            "users": debug_info
        }
    except Exception as e:
        return {"error": str(e)}