from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId
from datetime import datetime
from typing import Optional, Annotated
from pydantic import BeforeValidator

def validate_object_id(v):
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return v
        raise ValueError("Invalid ObjectId format")
    raise ValueError("ObjectId must be a valid ObjectId or string")

PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]

class PostModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    author_name: str = Field(..., min_length=1, max_length=50)
    category_id: Optional[str] = Field(None, description="Category ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    author_name: str = Field(..., min_length=1, max_length=50)
    category_id: Optional[str] = Field(None, description="Category ID")

class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    category_id: Optional[str] = Field(None, description="Category ID")
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PostResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str
    title: str
    content: str
    author_name: str
    category_id: Optional[str]
    category_name: Optional[str] = None  # Will be populated via lookup
    created_at: datetime
    updated_at: datetime