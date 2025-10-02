#!/usr/bin/env python3
"""
Migration script to add author emails to existing comments.

This script updates all existing comments in the database to include the author_email field
by looking up the email address in the users collection based on the author_name.
"""

import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import logging
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar_community")

async def migrate_comments_add_emails():
    """Main migration function"""
    try:
        # Connect to MongoDB
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]

        logger.info("Connected to MongoDB")
        logger.info(f"Database: {DATABASE_NAME}")

        # Get collections
        comments_collection = db.comments
        users_collection = db.users

        # Count total comments
        total_comments = await comments_collection.count_documents({})
        logger.info(f"Total comments in database: {total_comments}")

        # Count comments without author_email
        comments_without_email = await comments_collection.count_documents({
            "$or": [
                {"author_email": {"$exists": False}},
                {"author_email": None},
                {"author_email": ""}
            ]
        })
        logger.info(f"Comments without author_email: {comments_without_email}")

        if comments_without_email == 0:
            logger.info("All comments already have author_email. No migration needed.")
            return

        # Get all users for email lookup
        users_dict = {}
        async for user in users_collection.find({}, {"name": 1, "email": 1}):
            users_dict[user["name"]] = user["email"]

        logger.info(f"Found {len(users_dict)} users for email lookup")

        # Process comments in batches
        batch_size = 100
        updated_count = 0
        not_found_count = 0

        # Find comments that need email updates
        cursor = comments_collection.find({
            "$or": [
                {"author_email": {"$exists": False}},
                {"author_email": None},
                {"author_email": ""}
            ]
        })

        batch = []
        async for comment in cursor:
            author_name = comment.get("author_name", "")
            comment_id = comment["_id"]

            # Look up email for this author
            author_email = users_dict.get(author_name)

            if author_email:
                batch.append({
                    "comment_id": comment_id,
                    "author_email": author_email,
                    "author_name": author_name
                })

                # Process batch when it reaches batch_size
                if len(batch) >= batch_size:
                    await process_batch(comments_collection, batch)
                    updated_count += len(batch)
                    logger.info(f"Updated {updated_count}/{comments_without_email} comments...")
                    batch = []
            else:
                not_found_count += 1
                logger.warning(f"No user found for author: '{author_name}' (comment ID: {comment_id})")

        # Process remaining batch
        if batch:
            await process_batch(comments_collection, batch)
            updated_count += len(batch)

        logger.info(f"Migration completed successfully!")
        logger.info(f"- Comments updated: {updated_count}")
        logger.info(f"- Authors not found: {not_found_count}")
        logger.info(f"- Total processed: {updated_count + not_found_count}")

        # Verify the migration
        remaining_without_email = await comments_collection.count_documents({
            "$or": [
                {"author_email": {"$exists": False}},
                {"author_email": None},
                {"author_email": ""}
            ]
        })
        logger.info(f"Comments still without email after migration: {remaining_without_email}")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        client.close()

async def process_batch(comments_collection, batch):
    """Process a batch of comment updates"""
    try:
        # Use individual updates instead of bulk_write for simplicity
        updated_count = 0

        for item in batch:
            result = await comments_collection.update_one(
                {"_id": item["comment_id"]},
                {"$set": {"author_email": item["author_email"]}}
            )
            if result.modified_count > 0:
                updated_count += 1

        logger.debug(f"Updated {updated_count} documents in batch")

    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        # Log details about the failed batch
        for item in batch:
            logger.error(f"Failed item: {item}")
        raise

async def verify_migration():
    """Verify the migration results"""
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        comments_collection = db.comments

        # Count comments with and without emails
        total_comments = await comments_collection.count_documents({})
        comments_with_email = await comments_collection.count_documents({
            "author_email": {"$exists": True, "$ne": None, "$ne": ""}
        })
        comments_without_email = total_comments - comments_with_email

        logger.info("=== Migration Verification ===")
        logger.info(f"Total comments: {total_comments}")
        logger.info(f"Comments with email: {comments_with_email}")
        logger.info(f"Comments without email: {comments_without_email}")

        # Show sample of updated comments
        logger.info("\n=== Sample Updated Comments ===")
        async for comment in comments_collection.find(
            {"author_email": {"$exists": True, "$ne": None, "$ne": ""}},
            {"author_name": 1, "author_email": 1, "created_at": 1}
        ).limit(5):
            logger.info(f"Author: {comment.get('author_name')} | Email: {comment.get('author_email')} | Date: {comment.get('created_at')}")

        client.close()

    except Exception as e:
        logger.error(f"Verification failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        # Just run verification
        asyncio.run(verify_migration())
    else:
        # Run the migration
        logger.info("Starting comment email migration...")
        logger.info("This will add author_email field to existing comments")

        # Ask for confirmation
        response = input("Do you want to proceed? (y/N): ")
        if response.lower() != 'y':
            logger.info("Migration cancelled by user")
            sys.exit(0)

        asyncio.run(migrate_comments_add_emails())

        # Run verification after migration
        logger.info("\nRunning verification...")
        asyncio.run(verify_migration())