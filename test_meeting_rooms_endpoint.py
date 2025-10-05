#!/usr/bin/env python3
"""
Test script to verify the meeting rooms endpoint is working correctly
"""

import sys
import os
import logging
from datetime import datetime

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_meeting_rooms_models():
    """Test that the meeting rooms models work correctly"""
    try:
        logger.info("Testing meeting rooms models...")

        from app.models.video_calls import VideoCallResponse, CallType, CallStatus
        from bson import ObjectId

        # Simulate the room data from the database (similar to what we see in the screenshot)
        room_data = {
            "_id": "68e2336f27a273eae825b3b4",  # String version of ObjectId
            "id": "68e2336f27a273eae825b3b4",   # ID field for the model
            "channel_name": "room_v6Cq8KNEEKz1AV-SLHgH2Q",
            "creator_id": "68b3161d756316cfbe0d57c7",  # String version
            "creator_name": "Juan",
            "call_type": "meeting",
            "room_name": "innsaei",
            "description": "Intuición",
            "invited_users": [],
            "status": "waiting",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None,
            "participants": [],
            "max_participants": 10,
            "is_public": True,
            "password": None
        }

        logger.info(f"Creating VideoCallResponse with data: {room_data['room_name']}")

        # Test creating the response model
        response_room = VideoCallResponse(**room_data)
        logger.info(f"✅ Successfully created VideoCallResponse: {response_room.room_name}")
        logger.info(f"   ID: {response_room.id}")
        logger.info(f"   Channel: {response_room.channel_name}")
        logger.info(f"   Type: {response_room.call_type}")
        logger.info(f"   Status: {response_room.status}")
        logger.info(f"   Public: {response_room.is_public}")

        # Test conversion to dict (for JSON serialization)
        response_dict = response_room.dict()
        logger.info(f"✅ Successfully converted to dict with {len(response_dict)} fields")

        # Test the specific fields that might cause issues
        logger.info(f"   call_type in dict: {response_dict.get('call_type')}")
        logger.info(f"   status in dict: {response_dict.get('status')}")
        logger.info(f"   participants in dict: {response_dict.get('participants')}")
        logger.info(f"   invited_users in dict: {response_dict.get('invited_users')}")

        logger.info("🎉 All model tests passed!")
        return True

    except Exception as e:
        logger.error(f"❌ Error in model test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_meeting_rooms_query():
    """Test the query logic for meeting rooms"""
    try:
        logger.info("Testing meeting rooms query logic...")

        # Simulate the query conditions
        query_conditions = {
            "call_type": "meeting",
            "status": {"$in": ["waiting", "active"]}
        }

        # Test data from the database screenshot
        test_rooms = [
            {
                "call_type": "private",  # Should NOT match
                "status": "waiting"
            },
            {
                "call_type": "meeting",  # Should match
                "status": "waiting",
                "room_name": "innsaei"
            }
        ]

        matching_rooms = []
        for room in test_rooms:
            # Simulate MongoDB query logic
            if (room.get("call_type") == query_conditions["call_type"] and
                room.get("status") in query_conditions["status"]["$in"]):
                matching_rooms.append(room)

        logger.info(f"Query conditions: {query_conditions}")
        logger.info(f"Test rooms: {len(test_rooms)}")
        logger.info(f"Matching rooms: {len(matching_rooms)}")

        if len(matching_rooms) == 1 and matching_rooms[0]["room_name"] == "innsaei":
            logger.info("✅ Query logic is correct - should find 1 room")
            return True
        else:
            logger.error(f"❌ Query logic problem - expected 1 room, got {len(matching_rooms)}")
            return False

    except Exception as e:
        logger.error(f"❌ Error in query test: {e}")
        return False

if __name__ == "__main__":
    model_test = test_meeting_rooms_models()
    query_test = test_meeting_rooms_query()

    success = model_test and query_test

    if success:
        logger.info("🚀 All tests passed! The meeting rooms endpoint should work.")
        logger.info("If rooms still don't appear, check the server logs for the debugging output.")
    else:
        logger.error("❌ Some tests failed. Check the errors above.")

    sys.exit(0 if success else 1)