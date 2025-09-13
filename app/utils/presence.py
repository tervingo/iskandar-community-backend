from datetime import datetime, timedelta
from typing import List, Dict, Any
from app.database import get_collection
from bson import ObjectId

ONLINE_THRESHOLD_MINUTES = 5  # Users are considered offline after 5 minutes of inactivity

def is_user_online(last_seen: datetime | None) -> bool:
    """
    Determine if a user is online based on their last_seen timestamp.
    Users are considered online if they were active within the last 5 minutes.
    """
    if not last_seen:
        return False

    threshold = datetime.utcnow() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)
    return last_seen > threshold

async def get_online_users() -> List[Dict[str, Any]]:
    """
    Get all users who are currently online.
    """
    users_collection = get_collection("users")
    threshold = datetime.utcnow() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)

    print(f"Getting online users with threshold: {threshold}")  # Debug log

    # First, let's see all users with last_seen field
    all_users_with_last_seen = []
    async for user in users_collection.find({"last_seen": {"$exists": True}}):
        all_users_with_last_seen.append({
            "name": user.get("name"),
            "last_seen": user.get("last_seen"),
            "is_active": user.get("is_active")
        })

    print(f"All users with last_seen field: {all_users_with_last_seen}")  # Debug log

    online_users = []
    async for user in users_collection.find({
        "last_seen": {"$gte": threshold},
        "is_active": True
    }):
        user["_id"] = str(user["_id"])
        online_users.append({
            "id": user["_id"],
            "name": user.get("name"),
            "avatar": user.get("avatar"),
            "last_seen": user.get("last_seen")
        })
        print(f"Found online user: {user.get('name')} - last_seen: {user.get('last_seen')}")  # Debug log

    print(f"Total online users found: {len(online_users)}")  # Debug log
    return online_users

async def cleanup_offline_users() -> int:
    """
    Mark users as offline if they haven't been seen for more than the threshold.
    This is a cleanup function that can be called periodically.
    Returns the number of users marked as offline.
    """
    users_collection = get_collection("users")
    threshold = datetime.utcnow() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)

    # Find users who have last_seen older than threshold
    result = await users_collection.update_many(
        {
            "last_seen": {"$lt": threshold},
            "last_seen": {"$ne": None}  # Only update users who have a last_seen value
        },
        {"$unset": {"last_seen": ""}}  # Remove last_seen to indicate offline
    )

    return result.modified_count