from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime, timedelta
from bson import ObjectId
import uuid

from app.auth import get_current_active_user, TokenData
from app.database import get_collection
from app.models.doodle import (
    CreateDoodleRequest, RespondToDoodleRequest, CloseDoodleRequest,
    DoodleResponse, DoodleListItem, DoodlePoll, DoodleStatus, UserResponse
)

router = APIRouter()

@router.options("/doodles")
async def doodles_options():
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.post("/doodles", response_model=DoodleResponse)
async def create_doodle(
    doodle_data: CreateDoodleRequest,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Create a new doodle poll"""
    try:
        print(f"=== CREATE DOODLE ENDPOINT CALLED ===")
        print(f"Creating doodle with title: {doodle_data.title}")
        print(f"Creator: {current_user.name} ({current_user.user_id})")
        print(f"Options count: {len(doodle_data.options)}")

        collection = get_collection("doodle_polls")

        # Generate unique option IDs if not provided
        for option in doodle_data.options:
            if not option.option_id:
                option.option_id = str(uuid.uuid4())

        # Create doodle document
        doodle_doc = {
            "title": doodle_data.title,
            "description": doodle_data.description,
            "creator_id": ObjectId(current_user.user_id),
            "creator_name": current_user.name,
            "options": [option.dict() for option in doodle_data.options],
            "responses": [],
            "settings": doodle_data.settings.dict(),
            "status": DoodleStatus.ACTIVE,
            "final_option": None,
            "created_at": datetime.utcnow(),
            "closed_at": None
        }

        print(f"Inserting doodle document: {doodle_doc}")

        result = await collection.insert_one(doodle_doc)
        doodle_id = str(result.inserted_id)

        print(f"Doodle created successfully with ID: {doodle_id}")

        # Prepare response
        response_data = {
            "id": doodle_id,
            "title": doodle_data.title,
            "description": doodle_data.description,
            "creator_id": current_user.user_id,
            "creator_name": current_user.name,
            "options": doodle_data.options,
            "responses": [],
            "settings": doodle_data.settings,
            "status": DoodleStatus.ACTIVE,
            "final_option": None,
            "created_at": datetime.utcnow(),
            "closed_at": None,
            "total_responses": 0,
            "option_stats": {}
        }

        return DoodleResponse(**response_data)

    except Exception as e:
        print(f"Error creating doodle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create doodle: {str(e)}"
        )

@router.get("/doodles", response_model=List[DoodleListItem])
async def get_doodles(
    status_filter: Optional[str] = Query(None, description="Filter by status: active, closed, expired"),
    created_by_me: Optional[bool] = Query(False, description="Show only doodles created by current user"),
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get list of doodle polls"""
    try:
        print(f"=== GET DOODLES ENDPOINT CALLED ===")
        print(f"User: {current_user.name} ({current_user.user_id})")
        print(f"Filters: status={status_filter}, created_by_me={created_by_me}")

        collection = get_collection("doodle_polls")

        # Build query
        query = {}

        if status_filter:
            query["status"] = status_filter

        if created_by_me:
            query["creator_id"] = ObjectId(current_user.user_id)

        # Update expired doodles
        await collection.update_many(
            {
                "status": "active",
                "settings.deadline": {"$lt": datetime.utcnow()}
            },
            {
                "$set": {"status": "expired"}
            }
        )

        # Get doodles
        doodles = await collection.find(query).sort("created_at", -1).to_list(length=100)

        print(f"Found {len(doodles)} doodles")

        # Convert to response format
        response_doodles = []
        for doodle in doodles:
            # Check if current user has responded
            user_has_responded = any(
                str(response.get("user_id")) == current_user.user_id
                for response in doodle.get("responses", [])
            )

            doodle_item = DoodleListItem(
                id=str(doodle["_id"]),
                title=doodle["title"],
                description=doodle.get("description"),
                creator_id=str(doodle["creator_id"]),
                creator_name=doodle["creator_name"],
                status=doodle["status"],
                total_options=len(doodle.get("options", [])),
                total_responses=len(doodle.get("responses", [])),
                deadline=doodle.get("settings", {}).get("deadline"),
                created_at=doodle["created_at"],
                is_participant=user_has_responded
            )
            response_doodles.append(doodle_item)

        print(f"Returning {len(response_doodles)} doodles")
        return response_doodles

    except Exception as e:
        print(f"Error getting doodles: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get doodles: {str(e)}"
        )

@router.options("/doodles/{doodle_id}")
async def doodle_options(doodle_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.get("/doodles/{doodle_id}", response_model=DoodleResponse)
async def get_doodle(
    doodle_id: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get specific doodle poll with full details"""
    try:
        print(f"=== GET DOODLE ENDPOINT CALLED ===")
        print(f"Doodle ID: {doodle_id}")
        print(f"User: {current_user.name}")

        collection = get_collection("doodle_polls")
        doodle = await collection.find_one({"_id": ObjectId(doodle_id)})

        if not doodle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doodle not found"
            )

        # Calculate statistics
        option_stats = {}
        for option in doodle.get("options", []):
            option_id = option["option_id"]
            option_stats[option_id] = {"yes": 0, "no": 0, "maybe": 0}

        for response in doodle.get("responses", []):
            for option_id, vote in response.get("responses", {}).items():
                if option_id in option_stats:
                    option_stats[option_id][vote] = option_stats[option_id].get(vote, 0) + 1

        # Convert to response format
        response_data = {
            "id": str(doodle["_id"]),
            "title": doodle["title"],
            "description": doodle.get("description"),
            "creator_id": str(doodle["creator_id"]),
            "creator_name": doodle["creator_name"],
            "options": doodle["options"],
            "responses": doodle.get("responses", []),
            "settings": doodle["settings"],
            "status": doodle["status"],
            "final_option": doodle.get("final_option"),
            "created_at": doodle["created_at"],
            "closed_at": doodle.get("closed_at"),
            "total_responses": len(doodle.get("responses", [])),
            "option_stats": option_stats
        }

        # Convert ObjectIds to strings in responses
        for response in response_data["responses"]:
            response["user_id"] = str(response["user_id"])

        return DoodleResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting doodle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get doodle: {str(e)}"
        )

@router.options("/doodles/{doodle_id}/respond")
async def respond_doodle_options(doodle_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.put("/doodles/{doodle_id}/respond", response_model=DoodleResponse)
async def respond_to_doodle(
    doodle_id: str,
    response_data: RespondToDoodleRequest,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Respond to a doodle poll"""
    try:
        print(f"=== RESPOND TO DOODLE ENDPOINT CALLED ===")
        print(f"Doodle ID: {doodle_id}")
        print(f"User: {current_user.name}")
        print(f"Responses: {response_data.responses}")

        collection = get_collection("doodle_polls")
        doodle = await collection.find_one({"_id": ObjectId(doodle_id)})

        if not doodle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doodle not found"
            )

        if doodle["status"] != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Doodle is not active for responses"
            )

        # Check deadline
        deadline = doodle.get("settings", {}).get("deadline")
        if deadline and datetime.utcnow() > deadline:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Doodle deadline has passed"
            )

        # Validate response options
        valid_option_ids = {opt["option_id"] for opt in doodle["options"]}
        for option_id in response_data.responses.keys():
            if option_id not in valid_option_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid option ID: {option_id}"
                )

        # Create user response
        user_response = {
            "user_id": ObjectId(current_user.user_id),
            "username": current_user.name,
            "responses": response_data.responses,
            "comment": response_data.comment,
            "responded_at": datetime.utcnow()
        }

        # Remove any existing response from this user and add new one
        await collection.update_one(
            {"_id": ObjectId(doodle_id)},
            {
                "$pull": {"responses": {"user_id": ObjectId(current_user.user_id)}},
            }
        )

        await collection.update_one(
            {"_id": ObjectId(doodle_id)},
            {
                "$push": {"responses": user_response}
            }
        )

        print(f"Response saved for user {current_user.name}")

        # Return updated doodle
        return await get_doodle(doodle_id, current_user)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error responding to doodle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to respond to doodle: {str(e)}"
        )

@router.options("/doodles/{doodle_id}/close")
async def close_doodle_options(doodle_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.put("/doodles/{doodle_id}/close")
async def close_doodle(
    doodle_id: str,
    close_data: CloseDoodleRequest,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Close a doodle and select final option (creator only)"""
    try:
        print(f"=== CLOSE DOODLE ENDPOINT CALLED ===")
        print(f"Doodle ID: {doodle_id}")
        print(f"User: {current_user.name}")
        print(f"Final option: {close_data.final_option}")

        collection = get_collection("doodle_polls")
        doodle = await collection.find_one({"_id": ObjectId(doodle_id)})

        if not doodle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doodle not found"
            )

        # Check if user is creator
        if str(doodle["creator_id"]) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator can close this doodle"
            )

        # Validate final option
        valid_option_ids = {opt["option_id"] for opt in doodle["options"]}
        if close_data.final_option not in valid_option_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid final option"
            )

        # Close the doodle
        await collection.update_one(
            {"_id": ObjectId(doodle_id)},
            {
                "$set": {
                    "status": "closed",
                    "final_option": close_data.final_option,
                    "closed_at": datetime.utcnow()
                }
            }
        )

        print(f"Doodle {doodle_id} closed successfully")

        return {"message": "Doodle closed successfully", "final_option": close_data.final_option}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error closing doodle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close doodle: {str(e)}"
        )

@router.options("/doodles/{doodle_id}/delete")
async def delete_doodle_options(doodle_id: str):
    """Handle OPTIONS request for CORS preflight"""
    return {"message": "OK"}

@router.delete("/doodles/{doodle_id}")
async def delete_doodle(
    doodle_id: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Delete a doodle (creator only)"""
    try:
        print(f"=== DELETE DOODLE ENDPOINT CALLED ===")
        print(f"Doodle ID: {doodle_id}")
        print(f"User: {current_user.name}")

        collection = get_collection("doodle_polls")
        doodle = await collection.find_one({"_id": ObjectId(doodle_id)})

        if not doodle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doodle not found"
            )

        # Check if user is creator
        if str(doodle["creator_id"]) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator can delete this doodle"
            )

        # Delete the doodle
        result = await collection.delete_one({"_id": ObjectId(doodle_id)})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete doodle"
            )

        print(f"Doodle {doodle_id} deleted successfully")

        return {
            "message": "Doodle deleted successfully",
            "doodle_id": doodle_id,
            "title": doodle.get("title", "Unknown")
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting doodle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete doodle: {str(e)}"
        )