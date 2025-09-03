from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId
from datetime import datetime
from typing import Optional
from app.models.post import PyObjectId

class CommentModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    post_id: PyObjectId = Field(...)
    author_name: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CommentCreate(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=1000)

class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)

class CommentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str
    post_id: str
    author_name: str
    content: str
    created_at: datetime