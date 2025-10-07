from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum

class ResponseType(str, Enum):
    YES = "yes"
    NO = "no"
    MAYBE = "maybe"

class DoodleStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"

class DoodleOption(BaseModel):
    option_id: str
    datetime: datetime
    label: str  # "Lunes 15 Oct, 14:00"

class DoodleSettings(BaseModel):
    is_public: bool = True
    deadline: Optional[datetime] = None
    max_participants: Optional[int] = None
    allow_comments: bool = True
    allow_maybe: bool = True

class UserResponse(BaseModel):
    user_id: str
    username: str
    responses: Dict[str, str]  # option_id -> "yes"/"no"/"maybe"
    comment: Optional[str] = None
    responded_at: datetime

class DoodlePoll(BaseModel):
    id: Optional[str] = Field(alias="_id", default=None)
    title: str
    description: Optional[str] = None
    creator_id: str
    creator_name: str
    options: List[DoodleOption]
    responses: List[UserResponse] = Field(default_factory=list)
    settings: DoodleSettings
    status: DoodleStatus = DoodleStatus.ACTIVE
    final_option: Optional[str] = None  # option_id of winning choice
    created_at: datetime
    closed_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Request/Response models
class CreateDoodleRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    options: List[DoodleOption] = Field(..., min_items=2, max_items=20)
    settings: DoodleSettings

class RespondToDoodleRequest(BaseModel):
    responses: Dict[str, str]  # option_id -> "yes"/"no"/"maybe"
    comment: Optional[str] = Field(None, max_length=500)

class CloseDoodleRequest(BaseModel):
    final_option: str  # option_id of chosen option

class DoodleResponse(DoodlePoll):
    # Includes summary statistics
    total_responses: int = 0
    option_stats: Dict[str, Dict[str, int]] = Field(default_factory=dict)  # option_id -> {"yes": 5, "no": 2, "maybe": 1}

class DoodleListItem(BaseModel):
    id: str
    title: str
    description: Optional[str]
    creator_id: str
    creator_name: str
    status: DoodleStatus
    total_options: int
    total_responses: int
    deadline: Optional[datetime]
    created_at: datetime
    is_participant: bool = False  # True if current user has responded