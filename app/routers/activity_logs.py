from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from bson import ObjectId
from datetime import datetime, timedelta
from app.models.user_activity_log import (
    UserActivityLogResponse,
    ActivityLogFilters,
    ActivityEventType
)
from pydantic import BaseModel
from app.database import get_collection
from app.auth import get_current_admin_user
from app.models.user import TokenData

router = APIRouter()

class BulkDeleteUsersRequest(BaseModel):
    usernames: List[str]

@router.get("/", response_model=List[UserActivityLogResponse])
async def get_activity_logs(
    username: Optional[str] = Query(None, description="Filter by username"),
    event_type: Optional[ActivityEventType] = Query(None, description="Filter by event type"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """
    Get user activity logs with optional filtering (Admin only)

    Returns logs sorted by timestamp (newest first)
    """
    try:
        collection = get_collection("user_activity_logs")

        # Build query filter
        query = {}

        if username:
            query["username"] = {"$regex": username, "$options": "i"}  # Case-insensitive search

        if event_type:
            query["event_type"] = event_type.value

        if success is not None:
            query["success"] = success

        # Date range filtering
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                query["timestamp"]["$gte"] = start_date
            if end_date:
                query["timestamp"]["$lte"] = end_date

        # Execute query with pagination
        cursor = collection.find(query).sort("timestamp", -1).skip(offset).limit(limit)

        logs = []
        async for log_doc in cursor:
            # Convert ObjectId to string and map _id to id
            log_doc["id"] = str(log_doc["_id"])
            log_doc["_id"] = str(log_doc["_id"])
            logs.append(UserActivityLogResponse(**log_doc))

        return logs

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve activity logs: {str(e)}"
        )

@router.get("/stats", response_model=dict)
async def get_activity_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """
    Get activity statistics for the last N days (Admin only)

    Returns aggregated statistics about user activity
    """
    try:
        collection = get_collection("user_activity_logs")

        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Aggregation pipeline for statistics
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": start_date, "$lte": end_date}
                }
            },
            {
                "$group": {
                    "_id": {
                        "event_type": "$event_type",
                        "success": "$success"
                    },
                    "count": {"$sum": 1}
                }
            }
        ]

        # Execute aggregation
        stats_cursor = collection.aggregate(pipeline)
        raw_stats = []
        async for stat in stats_cursor:
            raw_stats.append(stat)

        # Process statistics
        stats = {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "events": {},
            "totals": {
                "total_events": 0,
                "successful_events": 0,
                "failed_events": 0
            }
        }

        for stat in raw_stats:
            event_type = stat["_id"]["event_type"]
            success = stat["_id"]["success"]
            count = stat["count"]

            if event_type not in stats["events"]:
                stats["events"][event_type] = {"successful": 0, "failed": 0, "total": 0}

            if success:
                stats["events"][event_type]["successful"] = count
                stats["totals"]["successful_events"] += count
            else:
                stats["events"][event_type]["failed"] = count
                stats["totals"]["failed_events"] += count

            stats["events"][event_type]["total"] += count
            stats["totals"]["total_events"] += count

        return stats

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve activity statistics: {str(e)}"
        )

@router.get("/users/{username}", response_model=List[UserActivityLogResponse])
async def get_user_activity_logs(
    username: str,
    limit: int = Query(50, ge=1, le=500),
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """
    Get activity logs for a specific user (Admin only)

    Returns the most recent activity for the specified user
    """
    try:
        collection = get_collection("user_activity_logs")

        # Query for specific user
        query = {"username": username}
        cursor = collection.find(query).sort("timestamp", -1).limit(limit)

        logs = []
        async for log_doc in cursor:
            log_doc["id"] = str(log_doc["_id"])
            log_doc["_id"] = str(log_doc["_id"])
            logs.append(UserActivityLogResponse(**log_doc))

        return logs

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve user activity logs: {str(e)}"
        )

@router.delete("/cleanup")
async def cleanup_old_logs(
    days: int = Query(90, ge=30, le=365, description="Delete logs older than N days"),
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """
    Delete activity logs older than specified days (Admin only)

    Use this to manage database size by removing old logs
    """
    try:
        collection = get_collection("user_activity_logs")

        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Delete old logs
        result = await collection.delete_many({"timestamp": {"$lt": cutoff_date}})

        return {
            "message": f"Successfully deleted old activity logs",
            "deleted_count": result.deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
            "days": days
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cleanup activity logs: {str(e)}"
        )

@router.delete("/users/bulk")
async def bulk_delete_user_activity_logs(
    request: BulkDeleteUsersRequest,
    current_admin: TokenData = Depends(get_current_admin_user)
):
    """
    Delete all activity logs for specified users (Admin only)

    This endpoint allows admins to completely remove all activity records
    for selected users. Use with caution as this operation is irreversible.
    """
    try:
        if not request.usernames:
            raise HTTPException(
                status_code=400,
                detail="No usernames provided for deletion"
            )

        collection = get_collection("user_activity_logs")

        # First, get a count of what we're about to delete for each user
        deletion_summary = {}
        total_to_delete = 0

        for username in request.usernames:
            count = await collection.count_documents({"username": username})
            deletion_summary[username] = count
            total_to_delete += count

        if total_to_delete == 0:
            return {
                "message": "No activity logs found for the specified users",
                "usernames": request.usernames,
                "deleted_count": 0,
                "deletion_summary": deletion_summary
            }

        # Perform the bulk deletion
        result = await collection.delete_many({"username": {"$in": request.usernames}})

        # Log this admin action
        from app.services.activity_logger import ActivityLogger
        await ActivityLogger.log_activity(
            username=current_admin.name,
            event_type=ActivityEventType.ADMIN_ACTION,
            success=True,
            additional_info={
                "action": "bulk_delete_user_activity_logs",
                "target_users": request.usernames,
                "deleted_count": result.deleted_count,
                "admin_user": current_admin.name
            }
        )

        return {
            "message": f"Successfully deleted activity logs for {len(request.usernames)} users",
            "usernames": request.usernames,
            "deleted_count": result.deleted_count,
            "deletion_summary": deletion_summary,
            "performed_by": current_admin.name,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        # Log the failed attempt
        try:
            from app.services.activity_logger import ActivityLogger
            await ActivityLogger.log_activity(
                username=current_admin.name,
                event_type=ActivityEventType.ADMIN_ACTION,
                success=False,
                additional_info={
                    "action": "bulk_delete_user_activity_logs",
                    "target_users": request.usernames,
                    "error": str(e),
                    "admin_user": current_admin.name
                }
            )
        except:
            pass  # Don't fail if logging fails

        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete user activity logs: {str(e)}"
        )