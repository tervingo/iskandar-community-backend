from pydantic import BaseModel, Field, EmailStr, ConfigDict
from bson import ObjectId
from datetime import datetime
from typing import Optional
from enum import Enum
from app.models.post import PyObjectId

class UserRole(str, Enum):
    ADMIN = "admin"
    NORMAL = "normal"

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
    role: Optional[UserRole] = Field(None)
    is_active: Optional[bool] = Field(None)
    avatar: Optional[str] = Field(None)
    phone: Optional[str] = Field(None, max_length=20)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str = Field(alias="_id")
    email: str
    name: str
    role: UserRole
    is_active: bool
    avatar: Optional[str]
    phone: Optional[str]
    created_at: datetime
    updated_at: datetime

class UserLogin(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Name for login")
    password: str = Field(..., description="Password")

class UserProfile(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    avatar: Optional[str] = Field(None)
    phone: Optional[str] = Field(None, max_length=20)

class PasswordChange(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, description="New password (min 6 chars)")

class TokenData(BaseModel):
    email: str
    user_id: str
    name: str
    role: UserRole
    is_active: bool