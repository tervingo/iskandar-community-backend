from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId
from datetime import datetime
from typing import Optional
from app.models.post import PyObjectId

class FileModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: PyObjectId = Field(default_factory=lambda: str(ObjectId()), alias="_id")
    filename: str = Field(..., min_length=1)
    original_name: str = Field(..., min_length=1)
    file_type: str = Field(..., min_length=1)
    file_size: int = Field(..., gt=0)
    cloudinary_url: str = Field(..., min_length=1)
    uploaded_by: str = Field(..., min_length=1, max_length=50)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    description: Optional[str] = Field(None, max_length=500)

class FileCreate(BaseModel):
    filename: str = Field(..., min_length=1)
    original_name: str = Field(..., min_length=1)
    file_type: str = Field(..., min_length=1)
    file_size: int = Field(..., gt=0)
    cloudinary_url: str = Field(..., min_length=1)
    uploaded_by: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=500)

class FileResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str
    filename: str
    original_name: str
    file_type: str
    file_size: int
    cloudinary_url: str
    uploaded_by: str
    uploaded_at: datetime
    description: Optional[str]