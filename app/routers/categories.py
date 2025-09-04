from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from bson import ObjectId
from app.models.category import CategoryModel, CategoryCreate, CategoryUpdate, CategoryResponse
from app.database import get_collection
from app.auth import get_current_admin_user, TokenData
from datetime import datetime

router = APIRouter()

@router.get("/", response_model=List[CategoryResponse])
async def get_categories():
    """Get all active categories"""
    categories_collection = get_collection("categories")
    categories = []
    
    async for category in categories_collection.find({"is_active": True}).sort("name", 1):
        category["id"] = str(category["_id"])
        category["_id"] = str(category["_id"])
        categories.append(CategoryResponse(**category))
    
    return categories

@router.get("/all", response_model=List[CategoryResponse])
async def get_all_categories(current_admin: TokenData = Depends(get_current_admin_user)):
    """Get all categories including inactive (Admin only)"""
    categories_collection = get_collection("categories")
    categories = []
    
    async for category in categories_collection.find().sort("name", 1):
        category["id"] = str(category["_id"])
        category["_id"] = str(category["_id"])
        categories.append(CategoryResponse(**category))
    
    return categories

@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(category_id: str):
    """Get category by ID"""
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid category ID format")
    
    categories_collection = get_collection("categories")
    category = await categories_collection.find_one({"_id": ObjectId(category_id)})
    
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    category["id"] = str(category["_id"])
    category["_id"] = str(category["_id"])
    return CategoryResponse(**category)

@router.post("/", response_model=CategoryResponse)
async def create_category(
    category_data: CategoryCreate,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Create new category (Admin only)"""
    categories_collection = get_collection("categories")
    
    # Check if category name already exists
    existing_category = await categories_collection.find_one({"name": {"$regex": f"^{category_data.name}$", "$options": "i"}})
    if existing_category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists"
        )
    
    # Create category
    category_dict = category_data.model_dump()
    category_dict["created_at"] = datetime.utcnow()
    category_dict["updated_at"] = datetime.utcnow()
    category_dict["is_active"] = True
    
    result = await categories_collection.insert_one(category_dict)
    created_category = await categories_collection.find_one({"_id": result.inserted_id})
    
    created_category["id"] = str(created_category["_id"])
    created_category["_id"] = str(created_category["_id"])
    return CategoryResponse(**created_category)

@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Update category (Admin only)"""
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid category ID format")
    
    categories_collection = get_collection("categories")
    
    # Check if category name already exists (excluding current category)
    if category_data.name:
        existing_category = await categories_collection.find_one({
            "name": {"$regex": f"^{category_data.name}$", "$options": "i"},
            "_id": {"$ne": ObjectId(category_id)}
        })
        if existing_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name already exists"
            )
    
    update_data = {k: v for k, v in category_data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    
    result = await categories_collection.update_one(
        {"_id": ObjectId(category_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    
    updated_category = await categories_collection.find_one({"_id": ObjectId(category_id)})
    updated_category["id"] = str(updated_category["_id"])
    updated_category["_id"] = str(updated_category["_id"])
    return CategoryResponse(**updated_category)

@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """Delete category (Admin only)"""
    if not ObjectId.is_valid(category_id):
        raise HTTPException(status_code=400, detail="Invalid category ID format")
    
    categories_collection = get_collection("categories")
    posts_collection = get_collection("posts")
    
    # Check if any posts are using this category
    posts_using_category = await posts_collection.count_documents({"category_id": category_id})
    if posts_using_category > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete category. {posts_using_category} posts are using this category."
        )
    
    result = await categories_collection.delete_one({"_id": ObjectId(category_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return {"message": "Category deleted successfully"}

@router.post("/initialize")
async def initialize_default_categories(current_admin: TokenData = Depends(get_current_admin_user)):
    """Initialize default categories (Admin only)"""
    categories_collection = get_collection("categories")
    
    default_categories = [
        {"name": "IA, Informática y Tecnología", "description": "Inteligencia artificial, programación, tecnología digital"},
        {"name": "Física y Matemáticas", "description": "Ciencias exactas, física teórica y aplicada, matemáticas"},
        {"name": "Filosofía", "description": "Filosofía, ética, pensamiento crítico"},
        {"name": "Biología", "description": "Ciencias de la vida, biología molecular, ecología"},
        {"name": "Ciencias de la Salud", "description": "Medicina, salud pública, investigación médica"},
        {"name": "Cosmología", "description": "Astronomía, cosmología, ciencias del espacio"},
        {"name": "Lengua y Literatura", "description": "Literatura, lingüística, análisis textual"}
    ]
    
    created_count = 0
    for cat_data in default_categories:
        # Check if category already exists
        existing = await categories_collection.find_one({"name": {"$regex": f"^{cat_data['name']}$", "$options": "i"}})
        if not existing:
            cat_data["created_at"] = datetime.utcnow()
            cat_data["updated_at"] = datetime.utcnow()
            cat_data["is_active"] = True
            await categories_collection.insert_one(cat_data)
            created_count += 1
    
    return {"message": f"Initialized {created_count} default categories"}