from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from typing import Dict, Any
from app.models.user import TokenData, UserRole
from app.auth import get_current_active_user
from app.services.backup_service import backup_service
from app.services.scheduler_service import scheduler_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/create", response_model=Dict[str, Any])
async def create_backup(
    background_tasks: BackgroundTasks,
    run_in_background: bool = True,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Create a manual database backup and upload to Dropbox"""

    # Only allow admins to create backups
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create database backups"
        )

    if not backup_service.backup_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup service is not configured. Please set MONGODB_URI and DROPBOX_ACCESS_TOKEN environment variables."
        )

    try:
        if run_in_background:
            # Run backup in background and return immediately
            background_tasks.add_task(backup_service.create_backup)

            return {
                "success": True,
                "message": "Backup process started in background. Check logs for progress.",
                "status": "started",
                "initiated_by": current_user.name,
                "initiated_at": None  # Will be set when backup actually starts
            }
        else:
            # Run backup synchronously (not recommended for production)
            result = await backup_service.create_backup()
            result["initiated_by"] = current_user.name
            return result

    except Exception as e:
        logger.error(f"Backup endpoint error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate backup: {str(e)}"
        )

@router.get("/list")
async def list_backups(
    current_user: TokenData = Depends(get_current_active_user)
):
    """List all available backups in Dropbox"""

    # Only allow admins to view backups
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view backup lists"
        )

    if not backup_service.backup_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup service is not configured"
        )

    try:
        result = await backup_service.list_backups()

        if result["success"]:
            return result
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List backups error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list backups: {str(e)}"
        )

@router.get("/status")
async def backup_status(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get backup service status and configuration"""

    # Only allow admins to view backup status
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view backup status"
        )

    mongodb_configured = bool(backup_service.mongodb_uri)
    dropbox_configured = bool(backup_service.dropbox_access_token)

    # Test Dropbox connection if configured
    dropbox_test_result = None
    if dropbox_configured:
        try:
            import requests
            headers = {"Authorization": f"Bearer {backup_service.dropbox_access_token}"}
            response = requests.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                account_info = response.json()
                dropbox_test_result = {
                    "status": "connected",
                    "account_name": account_info.get("name", {}).get("display_name", "Unknown"),
                    "email": account_info.get("email", "Unknown")
                }
            else:
                dropbox_test_result = {
                    "status": "failed",
                    "error": f"HTTP {response.status_code}",
                    "details": response.text[:200]
                }
        except Exception as e:
            dropbox_test_result = {
                "status": "error",
                "error": str(e)
            }

    return {
        "service_enabled": backup_service.backup_enabled,
        "mongodb_configured": mongodb_configured,
        "dropbox_configured": dropbox_configured,
        "dropbox_test": dropbox_test_result,
        "configuration": {
            "mongodb_uri_set": mongodb_configured,
            "dropbox_token_set": dropbox_configured,
            "database_name": backup_service._extract_db_name() if mongodb_configured else None
        },
        "recommendations": _get_configuration_recommendations(mongodb_configured, dropbox_configured)
    }

def _get_configuration_recommendations(mongodb_configured: bool, dropbox_configured: bool) -> list:
    """Get configuration recommendations"""
    recommendations = []

    if not mongodb_configured:
        recommendations.append("Set MONGODB_URI environment variable with your MongoDB Atlas connection string")

    if not dropbox_configured:
        recommendations.append("Set DROPBOX_ACCESS_TOKEN environment variable with your Dropbox API token")

    if mongodb_configured and dropbox_configured:
        recommendations.append("Backup service is fully configured and ready to use")

    return recommendations

@router.delete("/cleanup")
async def cleanup_old_backups(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Manually cleanup old backups (keeps newest 4)"""

    # Only allow admins to cleanup backups
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can cleanup backups"
        )

    if not backup_service.backup_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup service is not configured"
        )

    try:
        # Get current backup list
        list_result = await backup_service.list_backups()

        if not list_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=list_result["message"]
            )

        total_backups = list_result["total_count"]

        # Perform cleanup
        await backup_service._cleanup_old_backups()

        # Get updated list
        updated_list = await backup_service.list_backups()
        remaining_backups = updated_list["total_count"] if updated_list["success"] else total_backups

        deleted_count = max(0, total_backups - remaining_backups)

        return {
            "success": True,
            "message": f"Cleanup completed successfully",
            "backups_deleted": deleted_count,
            "backups_remaining": remaining_backups,
            "initiated_by": current_user.name
        }

    except Exception as e:
        logger.error(f"Cleanup backups error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup backups: {str(e)}"
        )

@router.get("/download/{backup_name}")
async def get_backup_download_link(
    backup_name: str,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get a temporary download link for a specific backup"""

    # Only allow admins to download backups
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can download backups"
        )

    if not backup_service.backup_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backup service is not configured"
        )

    try:
        # For now, return instructions for manual download
        # In a full implementation, you'd generate a temporary Dropbox share link
        return {
            "success": True,
            "message": "To download this backup, access your Dropbox account and navigate to /yskandar_backups/",
            "backup_name": backup_name,
            "manual_path": f"/yskandar_backups/{backup_name}",
            "note": "Automatic download links can be implemented using Dropbox's temporary link API"
        }

    except Exception as e:
        logger.error(f"Download link error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate download link: {str(e)}"
        )

@router.get("/scheduler/status")
async def get_scheduler_status(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Get backup scheduler status"""

    # Only allow admins to view scheduler status
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view scheduler status"
        )

    try:
        status_info = scheduler_service.get_status()
        return {
            "success": True,
            "scheduler": status_info,
            "backup_service_enabled": backup_service.backup_enabled
        }

    except Exception as e:
        logger.error(f"Scheduler status error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get scheduler status: {str(e)}"
        )

@router.post("/scheduler/start")
async def start_scheduler(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Start the backup scheduler"""

    # Only allow admins to control scheduler
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can control the backup scheduler"
        )

    try:
        if scheduler_service.running:
            return {
                "success": False,
                "message": "Scheduler is already running"
            }

        await scheduler_service.start()

        return {
            "success": True,
            "message": "Backup scheduler started successfully",
            "initiated_by": current_user.name
        }

    except Exception as e:
        logger.error(f"Start scheduler error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start scheduler: {str(e)}"
        )

@router.post("/scheduler/stop")
async def stop_scheduler(
    current_user: TokenData = Depends(get_current_active_user)
):
    """Stop the backup scheduler"""

    # Only allow admins to control scheduler
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can control the backup scheduler"
        )

    try:
        if not scheduler_service.running:
            return {
                "success": False,
                "message": "Scheduler is not running"
            }

        await scheduler_service.stop()

        return {
            "success": True,
            "message": "Backup scheduler stopped successfully",
            "initiated_by": current_user.name
        }

    except Exception as e:
        logger.error(f"Stop scheduler error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop scheduler: {str(e)}"
        )