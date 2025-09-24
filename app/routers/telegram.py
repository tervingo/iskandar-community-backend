from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime

from app.models.user import UserModel, TelegramPreferences, TokenData
from app.database import get_collection
from app.auth import get_current_active_user, get_current_admin_user
from app.services.telegram_service import telegram_service

router = APIRouter(prefix="/telegram", tags=["telegram"])

class TelegramConfig(BaseModel):
    telegram_id: str
    preferences: TelegramPreferences

class TelegramTestMessage(BaseModel):
    message: str

@router.get("/bot-info")
async def get_bot_info(current_user: TokenData = Depends(get_current_admin_user)):
    """Get Telegram bot information (admin only)"""
    result = await telegram_service.get_bot_info()
    return result

@router.post("/configure")
async def configure_telegram(
    config: TelegramConfig,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Configure user's Telegram notifications"""
    try:
        users_collection = get_collection("users")

        # Update user's Telegram configuration
        update_data = {
            "telegram_id": config.telegram_id,
            "telegram_preferences": config.preferences.model_dump(),
            "updated_at": datetime.utcnow()
        }

        result = await users_collection.update_one(
            {"_id": ObjectId(current_user.user_id)},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )

        return {
            "success": True,
            "message": "Configuración de Telegram actualizada exitosamente"
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al configurar Telegram: {str(e)}"
        )

@router.get("/config")
async def get_telegram_config(current_user: TokenData = Depends(get_current_active_user)):
    """Get user's current Telegram configuration"""
    try:
        users_collection = get_collection("users")
        user = await users_collection.find_one({"_id": ObjectId(current_user.user_id)})

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )

        return {
            "telegram_id": user.get("telegram_id"),
            "telegram_preferences": user.get("telegram_preferences", {
                "enabled": False,
                "login_notifications": True,
                "new_posts": True,
                "comment_replies": True,
                "admin_notifications": True
            })
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener configuración: {str(e)}"
        )

@router.post("/test")
async def test_telegram_notification(
    test_data: TelegramTestMessage,
    current_user: TokenData = Depends(get_current_active_user)
):
    """Test Telegram notification"""
    try:
        users_collection = get_collection("users")
        user = await users_collection.find_one({"_id": ObjectId(current_user.user_id)})

        if not user or not user.get("telegram_id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telegram no configurado. Configure su ID de Telegram primero."
            )

        result = await telegram_service.send_message(
            user["telegram_id"],
            f"🧪 <b>Mensaje de Prueba</b>\n\n{test_data.message}\n\n✅ Su configuración de Telegram está funcionando correctamente!"
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al enviar mensaje de prueba: {str(e)}"
        )

@router.post("/admin/broadcast")
async def send_admin_broadcast(
    message_data: TelegramTestMessage,
    current_user: TokenData = Depends(get_current_admin_user)
):
    """Send broadcast message to all users with Telegram enabled (admin only)"""
    try:
        users_collection = get_collection("users")

        # Find all users with Telegram enabled
        users_with_telegram = await users_collection.find({
            "telegram_id": {"$exists": True, "$ne": None},
            "telegram_preferences.enabled": True,
            "telegram_preferences.admin_notifications": True,
            "is_active": True
        }).to_list(None)

        if not users_with_telegram:
            return {
                "success": True,
                "message": "No hay usuarios con Telegram configurado",
                "sent_count": 0
            }

        # Send to all admin Telegram IDs
        admin_telegram_ids = [user["telegram_id"] for user in users_with_telegram]

        results = await telegram_service.send_admin_notification(
            admin_telegram_ids,
            "Notificación Administrativa",
            message_data.message
        )

        successful_sends = sum(1 for result in results if result.get("success"))

        return {
            "success": True,
            "message": f"Mensaje enviado a {successful_sends} de {len(admin_telegram_ids)} usuarios",
            "sent_count": successful_sends,
            "total_users": len(admin_telegram_ids),
            "details": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al enviar broadcast: {str(e)}"
        )

@router.get("/stats")
async def get_telegram_stats(current_user: TokenData = Depends(get_current_admin_user)):
    """Get Telegram usage statistics (admin only)"""
    try:
        users_collection = get_collection("users")

        # Count users with Telegram configured
        total_users = await users_collection.count_documents({"is_active": True})
        telegram_users = await users_collection.count_documents({
            "telegram_id": {"$exists": True, "$ne": None},
            "is_active": True
        })
        enabled_users = await users_collection.count_documents({
            "telegram_id": {"$exists": True, "$ne": None},
            "telegram_preferences.enabled": True,
            "is_active": True
        })

        return {
            "total_users": total_users,
            "telegram_configured": telegram_users,
            "telegram_enabled": enabled_users,
            "configuration_rate": round((telegram_users / total_users) * 100, 1) if total_users > 0 else 0,
            "enabled_rate": round((enabled_users / telegram_users) * 100, 1) if telegram_users > 0 else 0
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener estadísticas: {str(e)}"
        )