#!/usr/bin/env python3
"""
Migration script to add email preferences to existing users
Run this script to update existing users with default email preferences
"""

import asyncio
import os
import sys
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar")

async def migrate_user_email_preferences():
    """Add email preferences to users who don't have them"""
    
    if not MONGODB_URL:
        print("Error: MONGODB_URL not found in environment variables")
        sys.exit(1)
    
    print("Starting email preferences migration...")
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    users_collection = db["users"]
    
    try:
        # Default email preferences for existing users
        default_preferences = {
            "new_posts": True,
            "admin_notifications": True, 
            "comment_replies": True,
            "weekly_digest": False
        }
        
        # Find users without email_preferences field
        users_without_preferences = await users_collection.count_documents({
            "email_preferences": {"$exists": False}
        })
        
        print(f"Found {users_without_preferences} users without email preferences")
        
        if users_without_preferences == 0:
            print("All users already have email preferences. Migration not needed.")
            return
        
        # Update users without email preferences
        result = await users_collection.update_many(
            {"email_preferences": {"$exists": False}},
            {
                "$set": {
                    "email_preferences": default_preferences,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        print(f"Successfully updated {result.modified_count} users with default email preferences")
        
        # Verify the migration
        remaining_without_preferences = await users_collection.count_documents({
            "email_preferences": {"$exists": False}
        })
        
        if remaining_without_preferences == 0:
            print("✅ Migration completed successfully! All users now have email preferences.")
        else:
            print(f"⚠️  Warning: {remaining_without_preferences} users still don't have email preferences")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        client.close()

async def main():
    """Main function"""
    print("=" * 60)
    print("EMAIL PREFERENCES MIGRATION FOR ISKANDAR USERS")
    print("=" * 60)
    
    await migrate_user_email_preferences()
    
    print("=" * 60)
    print("Migration complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())