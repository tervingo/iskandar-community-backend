#!/usr/bin/env python3
"""
Database migration script to add category_id field to existing files and assign them 
to the "IA, Informática y Tecnología" category.
"""

import asyncio
import motor.motor_asyncio
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

async def migrate_files_categories():
    """Add category_id field to existing files and assign to IA category"""
    
    # Connect to MongoDB
    MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar_community")
    
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DATABASE_NAME]
    files_collection = db.files
    categories_collection = db.categories
    
    print("Starting files category migration...")
    
    try:
        # Find the "IA, Informática y Tecnología" category
        ia_category = await categories_collection.find_one({
            "name": {"$regex": "^IA, Informática y Tecnología$", "$options": "i"}
        })
        
        if not ia_category:
            print("[ERROR] 'IA, Informática y Tecnología' category not found!")
            print("Please make sure you've initialized the default categories first.")
            return
        
        category_id = str(ia_category["_id"])
        print(f"Found 'IA, Informática y Tecnología' category with ID: {category_id}")
        
        # Find all files that don't have the category_id field
        files_without_category = await files_collection.count_documents({
            "category_id": {"$exists": False}
        })
        
        print(f"Found {files_without_category} files without category_id field")
        
        if files_without_category > 0:
            # Update all files that don't have category_id field
            result = await files_collection.update_many(
                {"category_id": {"$exists": False}},
                {
                    "$set": {
                        "category_id": category_id
                    }
                }
            )
            
            print(f"Updated {result.modified_count} files with category_id='{category_id}' (IA, Informática y Tecnología)")
        
        # Also update files that have category_id = None
        files_with_null_category = await files_collection.count_documents({
            "category_id": None
        })
        
        print(f"Found {files_with_null_category} files with null category_id")
        
        if files_with_null_category > 0:
            result2 = await files_collection.update_many(
                {"category_id": None},
                {
                    "$set": {
                        "category_id": category_id
                    }
                }
            )
            
            print(f"Updated {result2.modified_count} files from null category to 'IA, Informática y Tecnología'")
        
        # Verify the migration
        total_files = await files_collection.count_documents({})
        files_with_category_field = await files_collection.count_documents({
            "category_id": {"$exists": True, "$ne": None}
        })
        files_in_ia_category = await files_collection.count_documents({
            "category_id": category_id
        })
        
        print(f"Migration complete!")
        print(f"Total files in collection: {total_files}")
        print(f"Files with category_id field: {files_with_category_field}")
        print(f"Files assigned to 'IA, Informática y Tecnología': {files_in_ia_category}")
        
        if total_files == files_with_category_field:
            print("[SUCCESS] All files now have a category assigned!")
        else:
            print("[WARNING] Some files might still be missing the category_id field")
            
    except Exception as e:
        print(f"[ERROR] Error during migration: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(migrate_files_categories())