from pydantic import BaseModel, Field, ConfigDict, validator
from bson import ObjectId
from datetime import datetime
from typing import Optional
from app.models.post import PyObjectId

class NewsModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    title: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., min_length=1, max_length=2000)
    comment: Optional[str] = Field(None, max_length=1000)
    created_by: str = Field(..., min_length=1, max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

class NewsCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    url: str = Field(..., min_length=1, max_length=2000)
    comment: Optional[str] = Field(None, max_length=1000)

    @validator('url')
    def validate_url(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError('URL is required and must be a string')
        v = v.strip()
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        if len(v) < 10:  # Minimum reasonable URL length
            raise ValueError('URL too short')
        return v

class NewsUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    url: Optional[str] = Field(None, min_length=1, max_length=2000)
    comment: Optional[str] = Field(None, max_length=1000)

    @validator('url')
    def validate_url(cls, v):
        if v is not None and not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

class NewsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    url: str
    comment: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None