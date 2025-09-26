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
from app.models.user import UserModel

router = APIRouter()


@router.post("/generate-token", response_model=Dict[str, str])
async def generate_agora_token(
    channel_name: str,
    current_user: UserModel = Depends(get_current_active_user)
):
    """Generate Agora RTC token for video call"""
    # For now, return a temporary token placeholder
    # In production, you would integrate with Agora token server
    token = f"temp_token_{secrets.token_urlsafe(32)}"

    return {
        "token": token,
        "channel": channel_name,
        "uid": str(current_user.id),
        "appId": "your_agora_app_id"  # This should come from environment
    }


@router.post("/create-call", response_model=VideoCallResponse)
async def create_video_call(
    call_data: VideoCallCreate,
    current_user: UserModel = Depends(get_current_active_user)
):
    """Create a new video call"""
    collection = get_collection("video_calls")

    # Create unique channel name
    channel_name = f"call_{secrets.token_urlsafe(16)}"

    call_doc = {
        "channel_name": channel_name,
        "creator_id": ObjectId(current_user.id),
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

    result = await collection.insert_one(call_doc)
    call_doc["_id"] = result.inserted_id

    return VideoCallResponse(**call_doc)


@router.get("/my-calls", response_model=List[VideoCallResponse])
async def get_my_calls(
    current_user: UserModel = Depends(get_current_active_user)
):
    """Get all calls for current user"""
    collection = get_collection("video_calls")

    calls = await collection.find({
        "$or": [
            {"creator_id": ObjectId(current_user.id)},
            {"invited_users": ObjectId(current_user.id)},
            {"participants.user_id": ObjectId(current_user.id)}
        ]
    }).sort("created_at", -1).to_list(length=100)

    return [VideoCallResponse(**call) for call in calls]


@router.post("/join-call/{call_id}")
async def join_video_call(
    call_id: str,
    current_user: UserModel = Depends(get_current_active_user)
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
    user_id = ObjectId(current_user.id)
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


@router.post("/leave-call/{call_id}")
async def leave_video_call(
    call_id: str,
    current_user: UserModel = Depends(get_current_active_user)
):
    """Leave a video call"""
    collection = get_collection("video_calls")

    try:
        call_object_id = ObjectId(call_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid call ID")

    user_id = ObjectId(current_user.id)

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
    current_user: UserModel = Depends(get_current_active_user)
):
    """Get all active meeting rooms"""
    collection = get_collection("video_calls")

    rooms = await collection.find({
        "call_type": "meeting",
        "status": {"$in": ["waiting", "active"]}
    }).sort("created_at", -1).to_list(length=50)

    return [VideoCallResponse(**room) for room in rooms]


@router.post("/create-meeting-room", response_model=VideoCallResponse)
async def create_meeting_room(
    room_data: MeetingRoomCreate,
    current_user: UserModel = Depends(get_current_active_user)
):
    """Create a new meeting room"""
    collection = get_collection("video_calls")

    channel_name = f"room_{secrets.token_urlsafe(16)}"

    room_doc = {
        "channel_name": channel_name,
        "creator_id": ObjectId(current_user.id),
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

    result = await collection.insert_one(room_doc)
    room_doc["_id"] = result.inserted_id

    return VideoCallResponse(**room_doc)


@router.get("/call-history", response_model=List[CallHistoryResponse])
async def get_call_history(
    limit: int = 50,
    current_user: UserModel = Depends(get_current_active_user)
):
    """Get call history for current user"""
    collection = get_collection("video_calls")

    calls = await collection.find({
        "$or": [
            {"creator_id": ObjectId(current_user.id)},
            {"participants.user_id": ObjectId(current_user.id)}
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