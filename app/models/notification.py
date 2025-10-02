from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from app.models.post import PyObjectId

class EmailNotificationCreate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200, description="Email subject")
    message: str = Field(..., min_length=1, description="Email message content")
    include_unsubscribed: bool = Field(default=False, description="Include users who opted out of admin notifications")

class EmailNotificationResponse(BaseModel):
    success: bool
    message: str
    sent_count: int
    total_users: int

class EmailPreferencesUpdate(BaseModel):
    new_posts: Optional[bool] = Field(None, description="Receive notifications for new posts")
    admin_notifications: Optional[bool] = Field(None, description="Receive admin broadcast messages")
    comment_replies: Optional[bool] = Field(None, description="Receive notifications for comment replies")
    new_comments: Optional[bool] = Field(None, description="Receive notifications for any new comment on any post")
    weekly_digest: Optional[bool] = Field(None, description="Receive weekly activity digest")