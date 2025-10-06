from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional, Dict, Any
import json
from bson import ObjectId
from datetime import datetime, timedelta
import secrets
from app.models.video_calls import (
    VideoCallModel, VideoCallCreate, VideoCallResponse,
    VideoCallInvitation, MeetingRoomCreate, CallHistoryResponse
)
from app.database import get_collection
from app.auth import get_current_active_user
from app.models.user import TokenData

router = APIRouter()


@router.get("/health")
async def video_calls_health():
    """Simple health check for video calls router"""
    return {"status": "ok", "message": "Video calls router is working"}


@router.options("/generate-token")
async def generate_token_options():
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.post("/generate-token", response_model=Dict[str, Any])
async def generate_agora_token(
    call_id: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Generate Agora RTC token for video call"""
    try:
        print(f"Generating token for call_id: {call_id}")

        # Look up the call to get the channel name
        collection = get_collection("video_calls")
        call = await collection.find_one({"_id": ObjectId(call_id)})

        if not call:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Video call not found"
            )

        channel_name = call.get("channel_name")
        if not channel_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Channel name not found for this call"
            )

        print(f"Found channel name: {channel_name} for call: {call_id}")

        # For testing mode, return null token (Agora allows this for testing)
        # In production, you would integrate with Agora token server
        # For now, use null token which allows testing without valid Agora setup
        token = None  # null token allows testing mode

        return {
            "token": token,
            "channel": channel_name,
            "uid": str(current_user.user_id),
            "appId": "your_agora_app_id"  # This should come from environment
        }
    except Exception as e:
        print(f"Error generating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate token: {str(e)}"
        )


@router.options("/create-call")
async def create_call_options():
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.post("/create-call", response_model=VideoCallResponse)
async def create_video_call(
    call_data: VideoCallCreate,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Create a new video call"""
    try:
        print(f"Creating video call with data: {call_data}")
        print(f"Current user: {current_user.name} ({current_user.user_id})")
        print(f"Current user details: email={current_user.email}, role={current_user.role}")

        collection = get_collection("video_calls")

        # Create unique channel name
        channel_name = f"call_{secrets.token_urlsafe(16)}"

        call_doc = {
            "channel_name": channel_name,
            "creator_id": ObjectId(current_user.user_id),
            "creator_name": current_user.name,
            "call_type": call_data.call_type,
            "invited_users": [ObjectId(uid) for uid in call_data.invited_users],
            "status": "waiting",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None,
            "participants": [],
            "max_participants": call_data.max_participants or 50
        }

        print(f"Inserting call document: {call_doc}")
        result = await collection.insert_one(call_doc)

        # Prepare response data with proper field types
        response_data = {
            "id": str(result.inserted_id),
            "channel_name": channel_name,
            "creator_id": str(current_user.user_id),
            "creator_name": current_user.name,
            "call_type": call_data.call_type,
            "invited_users": call_data.invited_users,  # Keep as string list
            "status": "waiting",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None,
            "participants": [],
            "max_participants": call_data.max_participants or 50,
            "is_public": True,
            "password": None
        }

        print(f"Call created successfully with ID: {result.inserted_id}")
        return VideoCallResponse(**response_data)

    except Exception as e:
        print(f"Error creating video call: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create video call: {str(e)}")


@router.get("/my-calls", response_model=List[VideoCallResponse])
async def get_my_calls(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get all calls for current user"""
    collection = get_collection("video_calls")

    calls = await collection.find({
        "$or": [
            {"creator_id": ObjectId(current_user.user_id)},
            {"invited_users": ObjectId(current_user.user_id)},
            {"participants.user_id": ObjectId(current_user.user_id)}
        ]
    }).sort("created_at", -1).to_list(length=100)

    return [VideoCallResponse(**call) for call in calls]


@router.options("/join-call/{call_id}")
async def join_call_options(call_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.post("/join-call/{call_id}")
async def join_video_call(
    call_id: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Join an existing video call"""
    collection = get_collection("video_calls")

    try:
        call_object_id = ObjectId(call_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid call ID")

    call = await collection.find_one({"_id": call_object_id})
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    # Check if user is invited or it's an open meeting room
    user_id = ObjectId(current_user.user_id)
    if (call["call_type"] == "private" and
        user_id not in call["invited_users"] and
        call["creator_id"] != user_id):
        raise HTTPException(status_code=403, detail="Not invited to this call")

    # Add participant if not already in call
    participant = {
        "user_id": user_id,
        "username": current_user.name,
        "joined_at": datetime.utcnow()
    }

    await collection.update_one(
        {"_id": call_object_id},
        {
            "$addToSet": {"participants": participant},
            "$set": {
                "status": "active",
                "started_at": datetime.utcnow() if call["status"] == "waiting" else call.get("started_at")
            }
        }
    )

    return {"message": "Joined call successfully", "channel_name": call["channel_name"]}


@router.options("/leave-call/{call_id}")
async def leave_call_options(call_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.post("/leave-call/{call_id}")
async def leave_video_call(
    call_id: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Leave a video call"""
    collection = get_collection("video_calls")

    try:
        call_object_id = ObjectId(call_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid call ID")

    user_id = ObjectId(current_user.user_id)

    # Remove participant
    await collection.update_one(
        {"_id": call_object_id},
        {"$pull": {"participants": {"user_id": user_id}}}
    )

    # Check if call should be ended (no participants left)
    call = await collection.find_one({"_id": call_object_id})
    if call and len(call["participants"]) == 0:
        await collection.update_one(
            {"_id": call_object_id},
            {
                "$set": {
                    "status": "ended",
                    "ended_at": datetime.utcnow()
                }
            }
        )

    return {"message": "Left call successfully"}


@router.get("/meeting-rooms", response_model=List[VideoCallResponse])
async def get_meeting_rooms(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get all active meeting rooms"""
    print(f"=== GET MEETING ROOMS ENDPOINT CALLED ===")
    print(f"Current user: {current_user.name} ({current_user.user_id})")

    collection = get_collection("video_calls")

    print(f"Querying for meeting rooms with filters:")
    print(f"  call_type: 'meeting'")
    print(f"  status: ['waiting', 'active']")

    rooms = await collection.find({
        "call_type": "meeting",
        "status": {"$in": ["waiting", "active"]}
    }).sort("created_at", -1).to_list(length=50)

    print(f"Found {len(rooms)} rooms in database")

    if rooms:
        for i, room in enumerate(rooms):
            print(f"Room {i+1}:")
            print(f"  _id: {room.get('_id')}")
            print(f"  room_name: {room.get('room_name')}")
            print(f"  call_type: {room.get('call_type')}")
            print(f"  status: {room.get('status')}")
            print(f"  creator_name: {room.get('creator_name')}")
            print(f"  is_public: {room.get('is_public')}")
    else:
        print("No rooms found!")

    try:
        response_rooms = []
        for room in rooms:
            # Convert ObjectId to string for _id field and other ObjectId fields
            room_data = dict(room)
            room_data["_id"] = str(room_data["_id"])
            room_data["id"] = str(room_data["_id"])  # Also set id field for the model
            if room_data.get("creator_id"):
                room_data["creator_id"] = str(room_data["creator_id"])

            # Convert ObjectIds in invited_users and participants if they exist
            if room_data.get("invited_users"):
                room_data["invited_users"] = [str(uid) if hasattr(uid, '__str__') else uid for uid in room_data["invited_users"]]

            # Ensure participants is a list (even if empty)
            if not room_data.get("participants"):
                room_data["participants"] = []

            # Convert ObjectIds in participants
            for participant in room_data.get("participants", []):
                if participant.get("user_id"):
                    participant["user_id"] = str(participant["user_id"])

            print(f"Converting room to response: {room_data.get('room_name')}")
            print(f"  Room data keys: {list(room_data.keys())}")
            print(f"  _id: {room_data.get('_id')}")
            print(f"  id: {room_data.get('id')}")

            response_room = VideoCallResponse(**room_data)
            response_rooms.append(response_room)
            print(f"Successfully converted room: {response_room.room_name}")
            print(f"  Response room id: {response_room.id}")
            print(f"  Response room dict: {response_room.dict()}")

            # Verify the ID is correctly set in the response
            room_dict = response_room.dict()
            if not room_dict.get('id'):
                print(f"WARNING: ID field missing in response dict!")
                print(f"Available fields: {list(room_dict.keys())}")

        print(f"Returning {len(response_rooms)} rooms")
        return response_rooms
    except Exception as e:
        print(f"Error converting rooms to response: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing rooms: {str(e)}")


@router.options("/create-meeting-room")
async def create_meeting_room_options():
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.post("/create-meeting-room", response_model=VideoCallResponse)
async def create_meeting_room(
    room_data: MeetingRoomCreate,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Create a new meeting room"""
    try:
        print(f"=== CREATE MEETING ROOM ENDPOINT CALLED ===")
        print(f"Creating meeting room with data: {room_data}")
        print(f"Current user: {current_user.name} ({current_user.user_id})")
        print(f"User email: {current_user.email}, role: {current_user.role}, active: {current_user.is_active}")

        collection = get_collection("video_calls")

        channel_name = f"room_{secrets.token_urlsafe(16)}"

        room_doc = {
            "channel_name": channel_name,
            "creator_id": ObjectId(current_user.user_id),
            "creator_name": current_user.name,
            "call_type": "meeting",
            "room_name": room_data.room_name,
            "description": room_data.description,
            "invited_users": [],
            "status": "waiting",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None,
            "participants": [],
            "max_participants": room_data.max_participants,
            "is_public": room_data.is_public,
            "password": room_data.password
        }

        print(f"Inserting room document: {room_doc}")
        result = await collection.insert_one(room_doc)

        # Prepare response data with proper field types
        response_data = {
            "id": str(result.inserted_id),
            "channel_name": channel_name,
            "creator_id": str(current_user.user_id),
            "creator_name": current_user.name,
            "call_type": "meeting",
            "room_name": room_data.room_name,
            "description": room_data.description,
            "invited_users": [],
            "status": "waiting",
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None,
            "participants": [],
            "max_participants": room_data.max_participants,
            "is_public": room_data.is_public,
            "password": room_data.password
        }

        print(f"Meeting room created successfully with ID: {result.inserted_id}")
        return VideoCallResponse(**response_data)

    except Exception as e:
        print(f"Error creating meeting room: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create meeting room: {str(e)}")


@router.get("/call-history", response_model=List[CallHistoryResponse])
async def get_call_history(
    limit: int = 50,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get call history for current user"""
    collection = get_collection("video_calls")

    calls = await collection.find({
        "$or": [
            {"creator_id": ObjectId(current_user.user_id)},
            {"participants.user_id": ObjectId(current_user.user_id)}
        ],
        "status": "ended"
    }).sort("ended_at", -1).limit(limit).to_list(length=limit)

    history = []
    for call in calls:
        duration = None
        if call.get("started_at") and call.get("ended_at"):
            duration = (call["ended_at"] - call["started_at"]).total_seconds()

        history.append(CallHistoryResponse(
            id=str(call["_id"]),
            call_type=call["call_type"],
            creator_name=call["creator_name"],
            room_name=call.get("room_name"),
            started_at=call.get("started_at"),
            ended_at=call.get("ended_at"),
            duration=duration,
            participant_count=len(call.get("participants", []))
        ))

    return history


@router.options("/delete-meeting-room/{room_id}")
async def delete_meeting_room_options(room_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}


@router.delete("/delete-meeting-room/{room_id}")
async def delete_meeting_room(
    room_id: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Delete a meeting room (only by creator)"""
    try:
        print(f"=== DELETE MEETING ROOM ENDPOINT CALLED ===")
        print(f"Room ID: {room_id}")
        print(f"Requesting user: {current_user.name} ({current_user.user_id})")

        collection = get_collection("video_calls")
        room_object_id = ObjectId(room_id)

        # First, find the room to verify ownership
        room = await collection.find_one({"_id": room_object_id})

        if not room:
            print(f"Room {room_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting room not found"
            )

        # Check if current user is the creator
        creator_id = room.get("creator_id")
        if str(creator_id) != current_user.user_id:
            print(f"Access denied: {current_user.user_id} is not creator {creator_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the room creator can delete this meeting room"
            )

        # Check if room has active participants
        participants = room.get("participants", [])
        if len(participants) > 0:
            print(f"Room has {len(participants)} active participants, cannot delete")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete room with active participants. Please wait for all participants to leave."
            )

        # Delete the room
        result = await collection.delete_one({"_id": room_object_id})

        if result.deleted_count == 0:
            print(f"Failed to delete room {room_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete meeting room"
            )

        print(f"Successfully deleted room {room_id} by {current_user.name}")

        return {
            "message": "Meeting room deleted successfully",
            "room_id": room_id,
            "room_name": room.get("room_name", "Unknown")
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting meeting room: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete meeting room: {str(e)}"
        )