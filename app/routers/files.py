from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
import cloudinary
import cloudinary.uploader
from app.models.file import FileModel, FileCreate, FileResponse
from app.database import get_collection
from app.config import settings

router = APIRouter()

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret
)

@router.get("/", response_model=List[FileResponse])
async def get_all_files():
    collection = get_collection("files")
    files = []
    
    # First update any files missing uploaded_at field
    await collection.update_many(
        {"uploaded_at": {"$exists": False}}, 
        {"$set": {"uploaded_at": datetime.utcnow()}}
    )
    
    async for file_doc in collection.find().sort("uploaded_at", -1):
        # Convert ObjectId to string and map _id to id
        file_doc["id"] = str(file_doc["_id"])
        file_doc["_id"] = str(file_doc["_id"])
        
        # Note: Don't automatically change URLs for existing files as they may not exist at the new path
        # Existing files uploaded as 'image' type should keep their original URLs to work
        
        files.append(FileResponse(**file_doc))
    return files

@router.post("/upload", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    uploaded_by: str = Form(...),
    description: Optional[str] = Form(None)
):
    try:
        # Check if Cloudinary is configured
        if not all([settings.cloudinary_cloud_name, settings.cloudinary_api_key, settings.cloudinary_api_secret]):
            raise HTTPException(
                status_code=500, 
                detail="Cloudinary not configured. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET environment variables."
            )
        
        # Determine resource type based on file type
        resource_type = "image" if file.content_type and file.content_type.startswith('image/') else "raw"
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file.file,
            resource_type=resource_type,
            folder="iskandar_community"
        )
        
        # Create file record
        file_data = FileCreate(
            filename=upload_result["public_id"],
            original_name=file.filename,
            file_type=file.content_type,
            file_size=upload_result["bytes"],
            cloudinary_url=upload_result["secure_url"],
            uploaded_by=uploaded_by,
            description=description
        )
        
        collection = get_collection("files")
        file_dict = file_data.model_dump()
        file_dict["uploaded_at"] = datetime.utcnow()
        
        result = await collection.insert_one(file_dict)
        created_file = await collection.find_one({"_id": result.inserted_id})
        
        # Convert ObjectId to string and map _id to id
        created_file["id"] = str(created_file["_id"])
        created_file["_id"] = str(created_file["_id"])
        return FileResponse(**created_file)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@router.get("/{file_id}", response_model=FileResponse)
async def get_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID format")
    
    collection = get_collection("files")
    file_doc = await collection.find_one({"_id": ObjectId(file_id)})
    
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Convert ObjectId to string and map _id to id
    file_doc["id"] = str(file_doc["_id"])
    file_doc["_id"] = str(file_doc["_id"])
    return FileResponse(**file_doc)

@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID format")
    
    collection = get_collection("files")
    file_doc = await collection.find_one({"_id": ObjectId(file_id)})
    
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Delete from Cloudinary
        cloudinary.uploader.destroy(file_doc["filename"])
        
        # Delete from database
        await collection.delete_one({"_id": ObjectId(file_id)})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File deletion failed: {str(e)}")