#!/usr/bin/env python3
"""
Test script to debug video call authentication issues
"""

import sys
import os
import logging

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_video_call_endpoints():
    """Test that video call endpoints can be imported and have correct structure"""
    try:
        logger.info("Testing video call endpoints...")

        # Test import
        from app.routers.video_calls import router
        logger.info("✅ Successfully imported video_calls router")

        # Check if create-meeting-room OPTIONS endpoint exists
        routes = router.routes
        options_routes = [route for route in routes if hasattr(route, 'methods') and 'OPTIONS' in route.methods]
        post_routes = [route for route in routes if hasattr(route, 'methods') and 'POST' in route.methods]

        logger.info(f"Found {len(options_routes)} OPTIONS routes")
        logger.info(f"Found {len(post_routes)} POST routes")

        # Check specific endpoints
        create_meeting_room_options = any(
            route.path == "/create-meeting-room" and 'OPTIONS' in route.methods
            for route in routes if hasattr(route, 'methods')
        )

        create_meeting_room_post = any(
            route.path == "/create-meeting-room" and 'POST' in route.methods
            for route in routes if hasattr(route, 'methods')
        )

        if create_meeting_room_options:
            logger.info("✅ Found OPTIONS endpoint for /create-meeting-room")
        else:
            logger.error("❌ Missing OPTIONS endpoint for /create-meeting-room")

        if create_meeting_room_post:
            logger.info("✅ Found POST endpoint for /create-meeting-room")
        else:
            logger.error("❌ Missing POST endpoint for /create-meeting-room")

        # List all routes for debugging
        logger.info("All video call routes:")
        for route in routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                methods_str = ', '.join(route.methods)
                logger.info(f"  {methods_str} {route.path}")

        return create_meeting_room_options and create_meeting_room_post

    except Exception as e:
        logger.error(f"❌ Error in video call endpoints test: {e}")
        return False

if __name__ == "__main__":
    success = test_video_call_endpoints()
    sys.exit(0 if success else 1)