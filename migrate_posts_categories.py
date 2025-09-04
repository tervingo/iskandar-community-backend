#!/usr/bin/env python3
"""
Database migration script to add category_id field to existing posts.
This script adds 'category_id' field to posts that don't have it.
"""

import asyncio
import motor.motor_asyncio
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

async def migrate_posts_categories():
    """Add missing category_id field to existing posts"""
    
    # Connect to MongoDB
    MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar_community")
    
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DATABASE_NAME]
    posts_collection = db.posts
    
    print("Starting post category migration...")
    
    try:
        # Find all posts that don't have the category_id field
        posts_without_category = await posts_collection.count_documents({
            "category_id": {"$exists": False}
        })
        
        print(f"Found {posts_without_category} posts without category_id field")
        
        if posts_without_category > 0:
            # Update all posts that don't have category_id field
            result = await posts_collection.update_many(
                {"category_id": {"$exists": False}},
                {
                    "$set": {
                        "category_id": None
                    }
                }
            )
            
            print(f"Updated {result.modified_count} posts with category_id=None")
        
        # Verify the migration
        total_posts = await posts_collection.count_documents({})
        posts_with_category_field = await posts_collection.count_documents({
            "category_id": {"$exists": True}
        })
        
        print(f"Migration complete!")
        print(f"Total posts in collection: {total_posts}")
        print(f"Posts with category_id field: {posts_with_category_field}")
        
        if total_posts == posts_with_category_field:
            print("[SUCCESS] All posts now have the category_id field!")
        else:
            print("[WARNING] Some posts might still be missing the category_id field")
            
    except Exception as e:
        print(f"[ERROR] Error during migration: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(migrate_posts_categories())