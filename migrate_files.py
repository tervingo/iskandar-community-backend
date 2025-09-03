#!/usr/bin/env python3
"""
Database migration script to add missing fields to existing file records.
This script adds 'source_type' and 'original_url' fields to files that don't have them.
"""

import asyncio
import motor.motor_asyncio
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

async def migrate_files():
    """Add missing fields to existing file records"""
    
    # Connect to MongoDB
    MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar_community")
    
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DATABASE_NAME]
    files_collection = db.files
    
    print("Starting file migration...")
    
    try:
        # Find all files that don't have the source_type field
        files_without_source_type = await files_collection.count_documents({
            "source_type": {"$exists": False}
        })
        
        print(f"Found {files_without_source_type} files without source_type field")
        
        if files_without_source_type > 0:
            # Update all files that don't have source_type field
            result = await files_collection.update_many(
                {"source_type": {"$exists": False}},
                {
                    "$set": {
                        "source_type": "upload",
                        "original_url": None
                    }
                }
            )
            
            print(f"Updated {result.modified_count} files with source_type='upload' and original_url=None")
        
        # Verify the migration
        total_files = await files_collection.count_documents({})
        files_with_source_type = await files_collection.count_documents({
            "source_type": {"$exists": True}
        })
        
        print(f"Migration complete!")
        print(f"Total files in collection: {total_files}")
        print(f"Files with source_type field: {files_with_source_type}")
        
        if total_files == files_with_source_type:
            print("[SUCCESS] All files now have the required fields!")
        else:
            print("[WARNING] Some files might still be missing the source_type field")
            
    except Exception as e:
        print(f"[ERROR] Error during migration: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(migrate_files())