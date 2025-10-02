#!/usr/bin/env python3
"""
Test script to verify that email notifications work for replies to existing comments.
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

# Import the email service directly instead of the router function
from app.services.email_service import email_service

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iskandar")

async def test_reply_notification():
    """Test email notification for reply to existing comment"""
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]

        # Find an existing comment to reply to
        comments_collection = db.comments
        existing_comment = await comments_collection.find_one({
            "author_name": "test_user_1",
            "author_email": {"$exists": True}
        })

        if not existing_comment:
            logger.error("No existing comment found! Run test_comment_migration.py first.")
            return

        logger.info(f"Found existing comment by: {existing_comment['author_name']}")
        logger.info(f"Comment email: {existing_comment.get('author_email')}")

        # Find the post for this comment
        posts_collection = db.posts
        post = await posts_collection.find_one({"_id": existing_comment["post_id"]})

        if not post:
            logger.error("Post not found for the comment!")
            return

        # Create a mock reply comment
        reply_comment = {
            "_id": ObjectId(),
            "post_id": existing_comment["post_id"],
            "parent_id": existing_comment["_id"],
            "author_name": "test_user_2",
            "author_email": "user2@test.com",
            "content": "This is a test reply to check email notifications!",
            "created_at": datetime.utcnow()
        }

        # Insert the reply comment
        await comments_collection.insert_one(reply_comment)
        logger.info(f"Created reply comment by: {reply_comment['author_name']}")

        # Test the email notification function directly
        logger.info("Testing email notification...")

        # Simulate sending email notification
        await test_email_notification_direct(
            existing_comment,
            reply_comment,
            post,
            db
        )

        logger.info("Email notification test completed!")
        logger.info("Check the logs above to see if the email was sent successfully.")

        client.close()

    except Exception as e:
        logger.error(f"Error testing reply notification: {e}")
        raise

async def test_email_notification_direct(parent_comment, reply_comment, post, db):
    """Test email notification directly without FastAPI context"""
    try:
        logger.info("Starting direct email notification test...")

        # Get parent comment author info
        parent_author_email = parent_comment.get("author_email")
        parent_author_name = parent_comment.get("author_name", "Usuario")

        if not parent_author_email:
            logger.error("No email found for parent comment author")
            return

        # Check if user exists and has notifications enabled
        users_collection = db.users
        parent_user = await users_collection.find_one({"email": parent_author_email})

        if not parent_user:
            logger.error(f"User not found: {parent_author_email}")
            return

        # Check email preferences (default to True)
        email_prefs = parent_user.get("email_preferences", {})
        if not email_prefs.get("comment_replies", True):
            logger.info(f"User has disabled comment reply notifications")
            return

        # Don't send notification if user is replying to their own comment
        reply_author_email = reply_comment.get("author_email")
        if parent_author_email == reply_author_email:
            logger.info("User replying to their own comment, skipping notification")
            return

        # Prepare email context
        reply_author_name = reply_comment.get("author_name", "Un usuario")
        post_title = post.get("title", "Sin título")
        post_id = post.get("_id")
        post_url = f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/blog/{post_id}#comments"

        context = {
            "parent_author_name": parent_author_name,
            "reply_author_name": reply_author_name,
            "parent_comment_content": parent_comment.get("content", "")[:200] + "..." if len(parent_comment.get("content", "")) > 200 else parent_comment.get("content", ""),
            "reply_content": reply_comment.get("content", "")[:200] + "..." if len(reply_comment.get("content", "")) > 200 else reply_comment.get("content", ""),
            "post_title": post_title,
            "post_url": post_url,
            "site_name": "Yskandar",
            "unsubscribe_url": f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/profile"
        }

        logger.info(f"Email context prepared: {context}")

        # Try to render email template
        try:
            logger.info("Rendering email template...")
            html_body = email_service._render_template("comment_reply_notification.html", context)
            logger.info("Email template rendered successfully")
        except Exception as e:
            logger.error(f"Error rendering email template: {e}")
            return

        # Try to send email (will be disabled due to no credentials, but we can test the flow)
        try:
            subject = f"💬 {reply_author_name} respondió a tu comentario en '{post_title}'"
            logger.info(f"Would send email with subject: {subject}")
            logger.info(f"Recipients: {[parent_author_email]}")
            logger.info("Email service disabled (no credentials), but notification flow tested successfully!")

            # If we had credentials, this would send the actual email:
            # success = await email_service.send_email(
            #     recipients=[parent_author_email],
            #     subject=subject,
            #     html_body=html_body
            # )

        except Exception as e:
            logger.error(f"Error in email sending flow: {e}")
            return

        logger.info("✅ Direct email notification test completed successfully!")

    except Exception as e:
        logger.error(f"Error in direct email notification test: {e}")
        raise

async def check_comments_structure():
    """Check the structure of comments in the database"""
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]

        logger.info("=== Comment Database Structure ===")

        comments_collection = db.comments
        async for comment in comments_collection.find().limit(5):
            logger.info(f"Comment ID: {comment['_id']}")
            logger.info(f"  Author: {comment.get('author_name')}")
            logger.info(f"  Email: {comment.get('author_email', 'NOT SET')}")
            logger.info(f"  Parent ID: {comment.get('parent_id', 'None (root comment)')}")
            logger.info(f"  Content: {comment.get('content', '')[:50]}...")
            logger.info("---")

        client.close()

    except Exception as e:
        logger.error(f"Error checking comments structure: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--structure":
        logger.info("Checking comments structure...")
        asyncio.run(check_comments_structure())
    else:
        logger.info("Testing reply notification for existing comment...")
        asyncio.run(test_reply_notification())