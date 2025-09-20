from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Request
from app.database import get_collection
from app.models.user_activity_log import ActivityEventType, UserActivityLogCreate
import logging

# Configure Python logging for backup/debugging
logger = logging.getLogger(__name__)

class ActivityLogger:
    """Service for logging user activity events to MongoDB"""

    @staticmethod
    def extract_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
        """Extract IP address and User-Agent from request"""
        try:
            # Try to get real IP from headers (for proxies/load balancers)
            ip_address = (
                request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
                request.headers.get("X-Real-IP") or
                request.client.host if request.client else None
            )

            user_agent = request.headers.get("User-Agent")

            return ip_address, user_agent
        except Exception as e:
            logger.warning(f"Error extracting client info: {e}")
            return None, None

    @staticmethod
    async def log_activity(
        username: str,
        event_type: ActivityEventType,
        success: bool = True,
        request: Optional[Request] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Log user activity event to MongoDB

        Args:
            username: Username of the user
            event_type: Type of activity event
            success: Whether the event was successful
            request: FastAPI request object (for IP/User-Agent)
            additional_info: Additional information to log

        Returns:
            bool: True if logged successfully, False otherwise
        """
        try:
            print(f"ActivityLogger.log_activity called: {username} - {event_type.value}")
            # Extract client information if request is provided
            ip_address, user_agent = None, None
            if request:
                ip_address, user_agent = ActivityLogger.extract_client_info(request)
            print(f"Client info extracted: IP={ip_address}, UA={user_agent}")

            # Create log entry
            log_entry = UserActivityLogCreate(
                username=username,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                success=success,
                additional_info=additional_info
            )
            print(f"Log entry created: {log_entry}")

            # Save to MongoDB
            collection = get_collection("user_activity_logs")
            log_dict = log_entry.model_dump()
            log_dict["timestamp"] = datetime.utcnow()
            print(f"Inserting into MongoDB: {log_dict}")

            result = await collection.insert_one(log_dict)
            print(f"MongoDB insert result: {result.inserted_id}")

            # Also log to Python logger for backup/debugging
            log_level = logging.INFO if success else logging.WARNING
            logger.log(
                log_level,
                f"User activity: {username} - {event_type.value} - {'SUCCESS' if success else 'FAILED'}"
            )

            return True

        except Exception as e:
            # Log error but don't fail the main operation
            logger.error(f"Failed to log user activity: {username} - {event_type.value} - Error: {e}")
            return False

    @staticmethod
    async def log_login(username: str, success: bool, request: Optional[Request] = None) -> bool:
        """Log user login attempt"""
        additional_info = {"login_method": "web_interface"}
        return await ActivityLogger.log_activity(
            username=username,
            event_type=ActivityEventType.LOGIN,
            success=success,
            request=request,
            additional_info=additional_info
        )

    @staticmethod
    async def log_logout(username: str, request: Optional[Request] = None) -> bool:
        """Log user logout"""
        print(f"ActivityLogger.log_logout called for username: {username}")
        additional_info = {"logout_method": "web_interface"}
        result = await ActivityLogger.log_activity(
            username=username,
            event_type=ActivityEventType.LOGOUT,
            success=True,  # Logout is always considered successful
            request=request,
            additional_info=additional_info
        )
        print(f"ActivityLogger.log_logout result: {result}")
        return result

    @staticmethod
    async def log_password_change(username: str, success: bool, request: Optional[Request] = None) -> bool:
        """Log password change attempt"""
        additional_info = {"change_method": "web_interface"}
        return await ActivityLogger.log_activity(
            username=username,
            event_type=ActivityEventType.PASSWORD_CHANGE,
            success=success,
            request=request,
            additional_info=additional_info
        )

    @staticmethod
    async def log_post_view(username: str, post_id: str, post_title: str, request: Optional[Request] = None) -> bool:
        """Log post view event"""
        additional_info = {
            "post_id": post_id,
            "post_title": post_title,
            "view_method": "web_interface"
        }
        return await ActivityLogger.log_activity(
            username=username,
            event_type=ActivityEventType.POST_VIEW,
            success=True,  # Post view is always considered successful
            request=request,
            additional_info=additional_info
        )