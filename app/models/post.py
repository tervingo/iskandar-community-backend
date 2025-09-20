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
    is_published: bool = Field(default=False, description="Whether the post is published or draft")
    published_at: Optional[datetime] = Field(None, description="When the post was published")
    pin_priority: int = Field(default=0, description="Pin priority: 0=Normal, 1=Low, 2=Medium, 3=High")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PostCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    author_name: str = Field(..., min_length=1, max_length=50)
    category_id: Optional[str] = Field(None, description="Category ID")
    is_published: bool = Field(default=False, description="Whether to publish immediately or save as draft")
    pin_priority: int = Field(default=0, description="Pin priority: 0=Normal, 1=Low, 2=Medium, 3=High")

class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1)
    category_id: Optional[str] = Field(None, description="Category ID")
    is_published: Optional[bool] = Field(None, description="Whether to publish or unpublish the post")
    pin_priority: Optional[int] = Field(None, description="Pin priority: 0=Normal, 1=Low, 2=Medium, 3=High")
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class PostPublish(BaseModel):
    is_published: bool = Field(..., description="Whether to publish or unpublish the post")

class PostPinPriority(BaseModel):
    pin_priority: int = Field(..., ge=0, le=3, description="Pin priority: 0=Normal, 1=Low, 2=Medium, 3=High")

class PostResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str
    title: str
    content: str
    author_name: str
    category_id: Optional[str]
    category_name: Optional[str] = None  # Will be populated via lookup
    is_published: bool = Field(default=False, description="Whether the post is published (defaults to False for legacy posts)")
    published_at: Optional[datetime] = Field(default=None, description="When the post was published (None for unpublished posts)")
    pin_priority: int = Field(default=0, description="Pin priority: 0=Normal, 1=Low, 2=Medium, 3=High")
    created_at: datetime
    updated_at: datetime