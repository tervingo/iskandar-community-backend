#!/usr/bin/env python3
"""
Test script to verify that the ID field is correctly serialized in meeting rooms
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

def test_id_field_serialization():
    """Test that the VideoCallResponse model serializes the id field correctly"""
    try:
        logger.info("Testing ID field serialization...")

        from app.models.video_calls import VideoCallResponse, CallType, CallStatus

        # Simulate the room data with the new structure (using 'id' instead of '_id')
        room_data = {
            "id": "68e2336f27a273eae825b3b4",  # Direct id field
            "channel_name": "room_v6Cq8KNEEKz1AV-SLHgH2Q",
            "creator_id": "68b3161d756316cfbe0d57c7",
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

        logger.info(f"Creating VideoCallResponse with room: {room_data['room_name']}")

        # Test creating the response model
        response_room = VideoCallResponse(**room_data)
        logger.info(f"✅ Successfully created VideoCallResponse")
        logger.info(f"   Room name: {response_room.room_name}")
        logger.info(f"   ID field: {response_room.id}")

        # Test serialization to dict (this is what gets sent as JSON)
        response_dict = response_room.model_dump()  # Use model_dump instead of deprecated dict()
        logger.info(f"✅ Successfully serialized to dict")
        logger.info(f"   Dict keys: {list(response_dict.keys())}")

        # Check if 'id' field is present in the serialized dict
        if 'id' in response_dict:
            logger.info(f"✅ ID field is present in serialized dict: {response_dict['id']}")
        else:
            logger.error("❌ ID field is missing from serialized dict!")
            logger.error(f"Available fields: {list(response_dict.keys())}")
            return False

        # Test JSON serialization (simulate what FastAPI does)
        import json
        try:
            json_str = json.dumps(response_dict, default=str)
            json_parsed = json.loads(json_str)

            if 'id' in json_parsed:
                logger.info(f"✅ ID field is present in JSON: {json_parsed['id']}")
            else:
                logger.error("❌ ID field is missing from JSON!")
                return False

        except Exception as e:
            logger.error(f"❌ JSON serialization failed: {e}")
            return False

        logger.info("🎉 All ID field tests passed!")
        return True

    except Exception as e:
        logger.error(f"❌ Error in ID field test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_id_field_serialization()

    if success:
        logger.info("🚀 ID field serialization works correctly!")
        logger.info("The meeting room should now have a proper 'id' field for the frontend.")
    else:
        logger.error("❌ ID field serialization failed.")

    sys.exit(0 if success else 1)