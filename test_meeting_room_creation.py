#!/usr/bin/env python3
"""
Test script to verify meeting room creation functionality
"""

import sys
import os
import logging

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_meeting_room_model():
    """Test that MeetingRoomCreate model works correctly"""
    try:
        logger.info("Testing MeetingRoomCreate model...")

        from app.models.video_calls import MeetingRoomCreate

        # Test valid data
        valid_data = {
            "room_name": "Test Meeting Room",
            "description": "A test room for debugging",
            "max_participants": 10,
            "is_public": True,
            "password": None
        }

        room = MeetingRoomCreate(**valid_data)
        logger.info(f"✅ Valid room created: {room.room_name}")

        # Test minimal data
        minimal_data = {
            "room_name": "Minimal Room"
        }

        minimal_room = MeetingRoomCreate(**minimal_data)
        logger.info(f"✅ Minimal room created: {minimal_room.room_name} (max: {minimal_room.max_participants})")

        # Test room name validation
        try:
            invalid_room = MeetingRoomCreate(room_name="a")  # Too short
            logger.error("❌ Should have failed with short name")
            return False
        except ValueError as e:
            logger.info(f"✅ Validation correctly failed for short name: {e}")

        # Test private room with password
        private_data = {
            "room_name": "Private Room",
            "is_public": False,
            "password": "secret123"
        }

        private_room = MeetingRoomCreate(**private_data)
        logger.info(f"✅ Private room created: {private_room.room_name}")

        logger.info("🎉 All model tests passed!")
        return True

    except Exception as e:
        logger.error(f"❌ Error in model test: {e}")
        return False

def test_meeting_room_function_import():
    """Test that we can import the meeting room creation function"""
    try:
        logger.info("Testing meeting room function import...")

        from app.routers.video_calls import create_meeting_room
        logger.info("✅ Successfully imported create_meeting_room function")

        # Verify it's an async function
        import inspect
        if inspect.iscoroutinefunction(create_meeting_room):
            logger.info("✅ create_meeting_room is correctly defined as an async function")
        else:
            logger.error("❌ create_meeting_room is not an async function")
            return False

        return True

    except Exception as e:
        logger.error(f"❌ Error importing meeting room function: {e}")
        return False

if __name__ == "__main__":
    model_test = test_meeting_room_model()
    function_test = test_meeting_room_function_import()

    success = model_test and function_test

    if success:
        logger.info("🚀 All tests passed! The meeting room creation should work.")
        logger.info("If you're still getting 401 errors, try restarting the backend server.")

    sys.exit(0 if success else 1)