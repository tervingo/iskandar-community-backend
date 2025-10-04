#!/usr/bin/env python3
"""
Test script to verify that new comment notifications are working correctly.
This is a simple syntax and import test since full DB testing requires the server running.
"""

import sys
import os
import logging

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_new_comment_notification_imports():
    """Test that the new comment notification function can be imported correctly"""
    try:
        logger.info("Testing new comment notification imports...")

        # Test import
        from app.routers.comments import send_new_comment_notification
        logger.info("✅ Successfully imported send_new_comment_notification function")

        # Test that it's a callable async function
        import inspect
        if inspect.iscoroutinefunction(send_new_comment_notification):
            logger.info("✅ send_new_comment_notification is correctly defined as an async function")
        else:
            logger.error("❌ send_new_comment_notification is not an async function")
            return False

        # Test that we can read the comments.py file and verify the function is not commented out
        comments_file = os.path.join(os.path.dirname(__file__), 'app', 'routers', 'comments.py')
        with open(comments_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that the function call is not commented out
        if 'background_tasks.add_task(' in content and 'send_new_comment_notification,' in content:
            logger.info("✅ New comment notification is enabled in the code")
        else:
            logger.error("❌ New comment notification appears to be disabled")
            return False

        # Check that the function call is not within a comment block
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'send_new_comment_notification,' in line:
                if not line.strip().startswith('#'):
                    logger.info(f"✅ Found active notification call at line {i+1}")
                    break
        else:
            logger.error("❌ Could not find active notification call")
            return False

        logger.info("🎉 All tests passed! New comment notifications should be working correctly.")
        logger.info("Note: To fully test email sending, you need the server running with proper DB connection.")
        return True

    except Exception as e:
        logger.error(f"❌ Error in new comment notification test: {e}")
        return False

if __name__ == "__main__":
    success = test_new_comment_notification_imports()
    sys.exit(0 if success else 1)