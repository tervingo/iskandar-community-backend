from pydantic import BaseModel, Field, EmailStr, ConfigDict
from bson import ObjectId
from datetime import datetime
from typing import Optional, Dict
from enum import Enum
from app.models.post import PyObjectId

class UserRole(str, Enum):
    ADMIN = "admin"
    NORMAL = "normal"

class EmailPreferences(BaseModel):
    new_posts: bool = Field(default=True, description="Receive notifications for new posts")
    admin_notifications: bool = Field(default=True, description="Receive admin broadcast messages")
    comment_replies: bool = Field(default=True, description="Receive notifications for comment replies")
    weekly_digest: bool = Field(default=False, description="Receive weekly activity digest")

class TelegramPreferences(BaseModel):
    enabled: bool = Field(default=False, description="Enable Telegram notifications")
    login_notifications: bool = Field(default=True, description="Notify on login events")
    new_posts: bool = Field(default=True, description="Notify on new posts")
    comment_replies: bool = Field(default=True, description="Notify on comment replies")
    admin_notifications: bool = Field(default=True, description="Receive admin broadcast messages")

class UserModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    email: EmailStr = Field(..., description="Email for login (unique)")
    name: str = Field(..., min_length=1, max_length=50, description="Display name")
    password_hash: str = Field(..., description="Hashed password")
    role: UserRole = Field(default=UserRole.NORMAL, description="User role")
    is_active: bool = Field(default=True, description="Account status")
    avatar: Optional[str] = Field(None, description="Avatar image URL")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")
    telegram_id: Optional[str] = Field(None, description="Telegram user ID for notifications")
    email_preferences: EmailPreferences = Field(default_factory=EmailPreferences, description="Email notification preferences")
    telegram_preferences: TelegramPreferences = Field(default_factory=TelegramPreferences, description="Telegram notification preferences")
    last_seen: Optional[datetime] = Field(None, description="Last activity timestamp for presence tracking")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="Email for login")
    name: str = Field(..., min_length=1, max_length=50, description="Display name")
    password: str = Field(..., min_length=6, description="Password (min 6 chars)")
    role: UserRole = Field(default=UserRole.NORMAL, description="User role")
    avatar: Optional[str] = Field(None, description="Avatar image URL")
    phone: Optional[str] = Field(None, max_length=20, description="Phone number")

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr] = Field(None, description="Email address")
    role: Optional[UserRole] = Field(None)
    is_active: Optional[bool] = Field(None)
    avatar: Optional[str] = Field(None)
    phone: Optional[str] = Field(None, max_length=20)
    telegram_id: Optional[str] = Field(None, description="Telegram user ID for notifications")
    email_preferences: Optional[EmailPreferences] = Field(None)
    telegram_preferences: Optional[TelegramPreferences] = Field(None)
    last_seen: Optional[datetime] = Field(None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(alias="_id")
    email: str
    name: str
    role: UserRole
    is_active: bool
    avatar: Optional[str] = None
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    email_preferences: Optional[EmailPreferences] = None
    telegram_preferences: Optional[TelegramPreferences] = None
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

class UserLogin(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Name for login")
    password: str = Field(..., description="Password")

class UserProfile(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    avatar: Optional[str] = Field(None)
    phone: Optional[str] = Field(None, max_length=20)
    telegram_id: Optional[str] = Field(None, description="Telegram user ID for notifications")

class PasswordChange(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, description="New password (min 6 chars)")

class TokenData(BaseModel):
    email: str
    user_id: str
    name: str
    role: UserRole
    is_active: bool