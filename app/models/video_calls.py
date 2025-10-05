from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class CallType(str, Enum):
    PRIVATE = "private"
    MEETING = "meeting"


class CallStatus(str, Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    ENDED = "ended"


class VideoCallParticipant(BaseModel):
    user_id: str
    username: str
    joined_at: datetime


class VideoCallCreate(BaseModel):
    call_type: CallType
    invited_users: List[str] = Field(default_factory=list)
    max_participants: Optional[int] = 50


class VideoCallModel(BaseModel):
    id: Optional[str] = None  # Remove alias to ensure it's always in JSON
    channel_name: str
    creator_id: str
    creator_name: str
    call_type: CallType
    room_name: Optional[str] = None
    description: Optional[str] = None
    invited_users: List[str] = Field(default_factory=list)
    status: CallStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    participants: List[VideoCallParticipant] = Field(default_factory=list)
    max_participants: int = 50
    is_public: bool = True
    password: Optional[str] = None

    class Config:
        populate_by_name = True
        validate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class VideoCallResponse(VideoCallModel):
    pass


class VideoCallInvitation(BaseModel):
    call_id: str
    invited_user_id: str
    message: Optional[str] = None


class MeetingRoomCreate(BaseModel):
    room_name: str
    description: Optional[str] = None
    max_participants: int = Field(default=50, ge=2, le=100)
    is_public: bool = True
    password: Optional[str] = None

    @validator('room_name')
    def validate_room_name(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError('Room name must be at least 3 characters long')
        return v.strip()


class CallHistoryResponse(BaseModel):
    id: str
    call_type: CallType
    creator_name: str
    room_name: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration: Optional[float] = None  # in seconds
    participant_count: int

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ScreenShareRequest(BaseModel):
    call_id: str
    is_sharing: bool


class CallSettingsUpdate(BaseModel):
    audio_enabled: bool = True
    video_enabled: bool = True
    screen_sharing: bool = False