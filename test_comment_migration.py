#!/usr/bin/env python3
"""
Test script to create sample comments and test the migration.
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
import logging

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar")

async def setup_test_data():
    """Create test users, posts, and comments"""
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]

        # Create test users
        users_collection = db.users
        test_users = [
            {
                "_id": ObjectId(),
                "name": "test_user_1",
                "email": "user1@test.com",
                "role": "normal",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            },
            {
                "_id": ObjectId(),
                "name": "test_user_2",
                "email": "user2@test.com",
                "role": "normal",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        ]

        # Insert test users (if they don't exist)
        for user in test_users:
            existing = await users_collection.find_one({"name": user["name"]})
            if not existing:
                await users_collection.insert_one(user)
                logger.info(f"Created test user: {user['name']}")

        # Create a test post
        posts_collection = db.posts
        test_post = {
            "_id": ObjectId(),
            "title": "Test Post for Comment Migration",
            "content": "This is a test post to test comment functionality.",
            "author_name": "test_user_1",
            "is_published": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "pin_priority": 0
        }

        existing_post = await posts_collection.find_one({"title": test_post["title"]})
        if not existing_post:
            await posts_collection.insert_one(test_post)
            logger.info(f"Created test post: {test_post['title']}")
            post_id = test_post["_id"]
        else:
            post_id = existing_post["_id"]
            logger.info(f"Using existing test post: {existing_post['title']}")

        # Create test comments WITHOUT author_email (simulating old comments)
        comments_collection = db.comments
        old_comments = [
            {
                "_id": ObjectId(),
                "post_id": post_id,
                "author_name": "test_user_1",
                "content": "This is an old comment without email field",
                "created_at": datetime.utcnow()
                # Note: NO author_email field - simulating old comment
            },
            {
                "_id": ObjectId(),
                "post_id": post_id,
                "author_name": "test_user_2",
                "content": "This is another old comment without email",
                "created_at": datetime.utcnow()
                # Note: NO author_email field - simulating old comment
            }
        ]

        # Insert old comments
        for comment in old_comments:
            existing = await comments_collection.find_one({"content": comment["content"]})
            if not existing:
                await comments_collection.insert_one(comment)
                logger.info(f"Created old comment by: {comment['author_name']}")

        logger.info("Test data setup completed!")

        # Show current state
        total_comments = await comments_collection.count_documents({})
        comments_without_email = await comments_collection.count_documents({
            "$or": [
                {"author_email": {"$exists": False}},
                {"author_email": None},
                {"author_email": ""}
            ]
        })

        logger.info(f"Total comments: {total_comments}")
        logger.info(f"Comments without email: {comments_without_email}")

        client.close()

    except Exception as e:
        logger.error(f"Error setting up test data: {e}")
        raise

async def cleanup_test_data():
    """Clean up test data"""
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]

        # Remove test data
        await db.users.delete_many({"name": {"$regex": "^test_user_"}})
        await db.posts.delete_many({"title": {"$regex": "^Test Post"}})
        await db.comments.delete_many({"author_name": {"$regex": "^test_user_"}})

        logger.info("Test data cleaned up!")
        client.close()

    except Exception as e:
        logger.error(f"Error cleaning up test data: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        logger.info("Cleaning up test data...")
        asyncio.run(cleanup_test_data())
    else:
        logger.info("Setting up test data...")
        asyncio.run(setup_test_data())