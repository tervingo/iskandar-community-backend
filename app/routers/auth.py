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
from datetime import datetime

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

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: TokenData = Depends(get_current_active_user)):
    """Get current user profile"""
    users_collection = get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(current_user.user_id)})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user["_id"] = str(user["_id"])
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