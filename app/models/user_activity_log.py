from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from app.models.post import PyObjectId

class ActivityEventType(str, Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    POST_VIEW = "post_view"
    ADMIN_ACTION = "admin_action"
    # Futuros eventos que se pueden añadir:
    # ACCOUNT_CREATED = "account_created"
    # ACCOUNT_UPDATED = "account_updated"
    # ACCOUNT_DEACTIVATED = "account_deactivated"
    # FAILED_LOGIN = "failed_login"

class UserActivityLogModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    username: str = Field(..., min_length=1, max_length=50)
    event_type: ActivityEventType = Field(...)
    ip_address: Optional[str] = Field(None, max_length=45)  # IPv6 max length
    user_agent: Optional[str] = Field(None, max_length=500)
    success: bool = Field(default=True)
    additional_info: Optional[Dict[str, Any]] = Field(None)

class UserActivityLogCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    event_type: ActivityEventType = Field(...)
    ip_address: Optional[str] = Field(None, max_length=45)
    user_agent: Optional[str] = Field(None, max_length=500)
    success: bool = Field(default=True)
    additional_info: Optional[Dict[str, Any]] = Field(None)

class UserActivityLogResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    timestamp: datetime
    username: str
    event_type: ActivityEventType
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool
    additional_info: Optional[Dict[str, Any]] = None

class ActivityLogFilters(BaseModel):
    username: Optional[str] = None
    event_type: Optional[ActivityEventType] = None
    success: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)