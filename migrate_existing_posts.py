#!/usr/bin/env python3
"""
Migration script to update existing posts in the database.
Sets is_published=false and published_at=null for posts that don't have these fields.
This treats existing posts as drafts until manually published.
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from datetime import datetime

# Database configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar_community")

async def migrate_existing_posts():
    """
    Migrate existing posts to include is_published and published_at fields.
    Posts without these fields will be set as drafts (is_published=False).
    """
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    posts_collection = db.posts
    
    try:
        # Find posts that don't have the is_published field
        posts_without_publish_fields = await posts_collection.find({
            "is_published": {"$exists": False}
        }).to_list(None)
        
        if not posts_without_publish_fields:
            print("No posts found that need migration.")
            return
        
        print(f"Found {len(posts_without_publish_fields)} posts that need migration.")
        
        # Update each post to add the missing fields
        for post in posts_without_publish_fields:
            result = await posts_collection.update_one(
                {"_id": post["_id"]},
                {
                    "$set": {
                        "is_published": False,
                        "published_at": None
                    }
                }
            )
            
            if result.modified_count > 0:
                print(f"✓ Updated post: {post.get('title', 'Untitled')} (ID: {post['_id']})")
            else:
                print(f"✗ Failed to update post: {post.get('title', 'Untitled')} (ID: {post['_id']})")
        
        print(f"\nMigration completed. {len(posts_without_publish_fields)} posts updated.")
        print("All existing posts are now treated as drafts until manually published.")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        raise
    finally:
        client.close()

if __name__ == "__main__":
    print("Starting migration of existing posts...")
    print("This will set is_published=False for all posts missing this field.")
    
    # Ask for confirmation
    response = input("Continue with migration? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        exit(0)
    
    asyncio.run(migrate_existing_posts())