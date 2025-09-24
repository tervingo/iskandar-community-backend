import os
import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

class TelegramService:
    """Service for sending notifications via Telegram Bot API"""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = bool(self.bot_token)

        if not self.enabled:
            logger.warning("Telegram service disabled - BOT_TOKEN not configured")
        else:
            logger.info("Telegram service initialized successfully")

    async def send_message(
        self,
        chat_id: str,
        message: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True
    ) -> Dict[str, Any]:
        """
        Send a message to a Telegram chat

        Args:
            chat_id: Telegram chat ID or username
            message: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"
            disable_web_page_preview: Disable link previews

        Returns:
            Dict with success status and response data
        """
        if not self.enabled:
            return {
                "success": False,
                "error": "Telegram service not configured"
            }

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.info(f"Message sent successfully to chat {chat_id}")
                    return {
                        "success": True,
                        "message_id": result["result"]["message_id"],
                        "chat_id": result["result"]["chat"]["id"]
                    }
                else:
                    logger.error(f"Telegram API error: {result}")
                    return {
                        "success": False,
                        "error": result.get("description", "Unknown Telegram API error")
                    }
            else:
                logger.error(f"HTTP error {response.status_code}: {response.text}")
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return {
                "success": False,
                "error": f"Exception: {str(e)}"
            }

    async def send_login_notification(self, user_name: str, user_telegram_id: str) -> Dict[str, Any]:
        """Send login notification to user's Telegram"""
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        message = f"""
🔐 <b>Nuevo Login Detectado</b>

👤 <b>Usuario:</b> {user_name}
🕐 <b>Fecha y hora:</b> {timestamp}
🌐 <b>Aplicación:</b> Yskandar Community

✅ Si fuiste tú, puedes ignorar este mensaje.
❌ Si no reconoces este acceso, cambia tu contraseña inmediatamente.
        """.strip()

        return await self.send_message(user_telegram_id, message)

    async def send_new_post_notification(
        self,
        user_telegram_id: str,
        post_title: str,
        author_name: str,
        post_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send new post notification"""
        message = f"""
📝 <b>Nuevo Post Publicado</b>

📰 <b>Título:</b> {post_title}
✍️ <b>Autor:</b> {author_name}
🕐 <b>Fecha:</b> {datetime.now().strftime("%d/%m/%Y %H:%M")}
        """.strip()

        if post_url:
            message += f"\n\n🔗 <a href='{post_url}'>Leer completo</a>"

        return await self.send_message(user_telegram_id, message)

    async def send_comment_notification(
        self,
        user_telegram_id: str,
        post_title: str,
        commenter_name: str,
        comment_preview: str,
        post_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send new comment notification"""
        # Truncate comment preview
        if len(comment_preview) > 100:
            comment_preview = comment_preview[:100] + "..."

        message = f"""
💬 <b>Nuevo Comentario</b>

📰 <b>Post:</b> {post_title}
👤 <b>Comentario de:</b> {commenter_name}
💭 <b>Comentario:</b> "{comment_preview}"
🕐 <b>Fecha:</b> {datetime.now().strftime("%d/%m/%Y %H:%M")}
        """.strip()

        if post_url:
            message += f"\n\n🔗 <a href='{post_url}'>Ver post completo</a>"

        return await self.send_message(user_telegram_id, message)

    async def send_admin_login_notification(
        self,
        admin_telegram_ids: List[str],
        user_name: str,
        user_role: str
    ) -> List[Dict[str, Any]]:
        """Send login notification to admin users"""
        role_emoji = "👑" if user_role == "admin" else "👤"
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        formatted_message = f"""
🔐 <b>Login Detectado en Yskandar</b>

{role_emoji} <b>Usuario:</b> {user_name}
🛡️ <b>Rol:</b> {user_role.title()}
🕐 <b>Fecha y hora:</b> {timestamp}
🌐 <b>Aplicación:</b> Yskandar Community

ℹ️ <i>Monitoreo de accesos para administradores</i>
        """.strip()

        results = []
        for admin_id in admin_telegram_ids:
            result = await self.send_message(admin_id, formatted_message)
            results.append({
                "admin_id": admin_id,
                **result
            })

        return results

    async def send_admin_notification(
        self,
        admin_telegram_ids: List[str],
        title: str,
        message: str
    ) -> List[Dict[str, Any]]:
        """Send notification to multiple admin users"""
        formatted_message = f"""
📢 <b>{title}</b>

{message}

🕐 <b>Fecha:</b> {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
🤖 <i>Enviado desde Yskandar Community</i>
        """.strip()

        results = []
        for admin_id in admin_telegram_ids:
            result = await self.send_message(admin_id, formatted_message)
            results.append({
                "admin_id": admin_id,
                **result
            })

        return results

    async def get_bot_info(self) -> Dict[str, Any]:
        """Get bot information for verification"""
        if not self.enabled:
            return {
                "success": False,
                "error": "Telegram service not configured"
            }

        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    bot_info = result["result"]
                    logger.info(f"Bot info retrieved: @{bot_info.get('username')}")
                    return {
                        "success": True,
                        "bot_info": {
                            "id": bot_info.get("id"),
                            "username": bot_info.get("username"),
                            "first_name": bot_info.get("first_name"),
                            "is_bot": bot_info.get("is_bot")
                        }
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("description", "Failed to get bot info")
                    }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
            return {
                "success": False,
                "error": f"Exception: {str(e)}"
            }

# Global service instance
telegram_service = TelegramService()