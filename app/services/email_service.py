import os
import logging
from typing import List, Dict, Any, Optional
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from app.database import get_collection
from app.models.user import UserModel
from bson import ObjectId

# Configure logging
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        # Validate required environment variables
        mail_username = os.getenv("MAIL_USERNAME", "").strip()
        mail_password = os.getenv("MAIL_PASSWORD", "").strip()
        
        if mail_username and mail_password:
            # Use SMTP configuration
            self.email_enabled = True
            logger.info(f"Email service initialized with SMTP provider: {mail_username}")
            
            self.conf = ConnectionConfig(
                MAIL_USERNAME=mail_username,
                MAIL_PASSWORD=mail_password,
                MAIL_FROM=os.getenv("MAIL_FROM", mail_username),
                MAIL_FROM_NAME=os.getenv("MAIL_FROM_NAME", "Yskandar"),
                MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
                MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
                MAIL_STARTTLS=os.getenv("MAIL_STARTTLS", "True").lower() == "true",
                MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS", "False").lower() == "true",
                USE_CREDENTIALS=True,
                VALIDATE_CERTS=True
            )
        else:
            logger.warning("Email credentials not configured. Email functionality will be disabled.")
            logger.warning("Please set MAIL_USERNAME/MAIL_PASSWORD environment variables.")
            self.email_enabled = False
            self.conf = None

        # Initialize FastMail only if email is enabled
        if self.email_enabled and self.conf:
            self.fastmail = FastMail(self.conf)
        else:
            self.fastmail = None
        
        # Set up Jinja2 template environment
        template_dir = Path(__file__).parent.parent / "templates" / "email"
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=True
        )
        
        # Add custom filters
        self.jinja_env.filters['nl2br'] = self._nl2br_filter
        self.jinja_env.filters['strftime'] = self._strftime_filter
    
    def _nl2br_filter(self, text: str) -> str:
        """Convert newlines to HTML line breaks"""
        if not text:
            return ""
        from markupsafe import Markup
        return Markup(text.replace('\n', '<br>').replace('\r\n', '<br>'))
    
    def _strftime_filter(self, datetime_obj, format_string: str = '%Y-%m-%d %H:%M:%S') -> str:
        """Format datetime objects using strftime"""
        if not datetime_obj:
            return ""
        try:
            if hasattr(datetime_obj, 'strftime'):
                return datetime_obj.strftime(format_string)
            # Handle string dates
            from datetime import datetime
            if isinstance(datetime_obj, str):
                # Try to parse common date formats
                for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S']:
                    try:
                        parsed_date = datetime.strptime(datetime_obj, fmt)
                        return parsed_date.strftime(format_string)
                    except ValueError:
                        continue
            return str(datetime_obj)
        except Exception as e:
            logger.warning(f"Error formatting date {datetime_obj}: {e}")
            return str(datetime_obj)
    
    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Render email template with context"""
        try:
            template = self.jinja_env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Error rendering email template {template_name}: {e}")
            return f"<p>Error rendering email template: {e}</p>"
    
    async def send_email(
        self,
        recipients: List[str],
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        reply_to: Optional[str] = None
    ) -> bool:
        """Send email to recipients"""
        if not self.email_enabled:
            logger.warning("Email service is disabled - credentials not configured")
            return False
            
        try:
            message = MessageSchema(
                subject=subject,
                recipients=recipients,
                body=text_body or html_body,
                html=html_body,
                subtype="html" if html_body else "plain"
            )
            
            await self.fastmail.send_message(message)
            logger.info(f"Email sent successfully to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            if self.conf:
                logger.error(f"SMTP config - Server: {self.conf.MAIL_SERVER}, Port: {self.conf.MAIL_PORT}, Username: {self.conf.MAIL_USERNAME}")
                logger.error(f"SMTP settings - STARTTLS: {self.conf.MAIL_STARTTLS}, SSL_TLS: {self.conf.MAIL_SSL_TLS}, USE_CREDENTIALS: {self.conf.USE_CREDENTIALS}")
                logger.error(f"Password length: {len(self.conf.MAIL_PASSWORD) if self.conf.MAIL_PASSWORD else 0} characters")
            return False
    
    async def get_subscribed_users(self, notification_type: str = "new_posts") -> List[Dict[str, Any]]:
        """Get users subscribed to specific notification types"""
        try:
            collection = get_collection("users")
            query = {
                "is_active": True,
                f"email_preferences.{notification_type}": True
            }
            
            users = []
            async for user in collection.find(query):
                users.append({
                    "id": str(user["_id"]),
                    "name": user["name"],
                    "email": user["email"]
                })
            return users
            
        except Exception as e:
            logger.error(f"Error getting subscribed users: {e}")
            return []
    
    async def get_all_active_users(self) -> List[Dict[str, Any]]:
        """Get all active users for admin broadcasts"""
        try:
            collection = get_collection("users")
            query = {"is_active": True}
            
            users = []
            async for user in collection.find(query):
                # Check if user allows admin notifications (default to True if not set)
                email_prefs = user.get("email_preferences", {})
                if email_prefs.get("admin_notifications", True):
                    users.append({
                        "id": str(user["_id"]),
                        "name": user["name"],
                        "email": user["email"]
                    })
            return users
            
        except Exception as e:
            logger.error(f"Error getting all active users: {e}")
            return []
    
    async def send_new_post_notification(self, post_data: Dict[str, Any]) -> bool:
        """Send notification about new published post"""
        try:
            # Get subscribed users
            users = await self.get_subscribed_users("new_posts")
            
            if not users:
                logger.info("No users subscribed to new post notifications")
                return True
            
            # Prepare email context
            context = {
                "post_title": post_data.get("title", ""),
                "post_author": post_data.get("author_name", ""),
                "post_category": post_data.get("category_name", "Sin Categoría"),
                "post_content_preview": post_data.get("content", "")[:200] + "..." if len(post_data.get("content", "")) > 200 else post_data.get("content", ""),
                "post_url": f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/blog/{post_data.get('id')}",
                "site_name": "Yskandar",
                "unsubscribe_url": f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/profile"
            }
            
            # Render email template
            html_body = self._render_template("new_post_notification.html", context)
            
            # Send emails in batches to avoid overwhelming the SMTP server
            batch_size = 50
            recipients = [user["email"] for user in users]
            
            for i in range(0, len(recipients), batch_size):
                batch = recipients[i:i + batch_size]
                subject = f"📝 Nuevo post: {post_data.get('title', 'Sin título')}"
                
                success = await self.send_email(
                    recipients=batch,
                    subject=subject,
                    html_body=html_body
                )
                
                if not success:
                    logger.warning(f"Failed to send batch {i//batch_size + 1}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending new post notification: {e}")
            return False
    
    async def send_admin_broadcast(
        self, 
        subject: str, 
        message: str, 
        sender_name: str,
        include_unsubscribed: bool = False
    ) -> Dict[str, Any]:
        """Send admin broadcast to all users"""
        try:
            # Get recipients
            if include_unsubscribed:
                # Get all active users
                collection = get_collection("users")
                users = []
                async for user in collection.find({"is_active": True}):
                    users.append({
                        "id": str(user["_id"]),
                        "name": user["name"],
                        "email": user["email"]
                    })
            else:
                # Get users who accept admin notifications
                users = await self.get_all_active_users()
            
            if not users:
                return {
                    "success": False,
                    "message": "No recipients found",
                    "sent_count": 0,
                    "total_users": 0
                }
            
            # Prepare email context
            context = {
                "subject": subject,
                "message": message,
                "sender_name": sender_name,
                "site_name": "Yskandar",
                "unsubscribe_url": f"{os.getenv('FRONTEND_URL', 'https://yskandar.com')}/profile"
            }
            
            # Render email template
            html_body = self._render_template("admin_broadcast.html", context)
            
            # Send emails in batches
            batch_size = 50
            recipients = [user["email"] for user in users]
            sent_count = 0
            
            for i in range(0, len(recipients), batch_size):
                batch = recipients[i:i + batch_size]
                
                success = await self.send_email(
                    recipients=batch,
                    subject=f"📢 {subject}",
                    html_body=html_body
                )
                
                if success:
                    sent_count += len(batch)
            
            return {
                "success": True,
                "message": f"Broadcast sent successfully to {sent_count} users",
                "sent_count": sent_count,
                "total_users": len(users)
            }
            
        except Exception as e:
            logger.error(f"Error sending admin broadcast: {e}")
            return {
                "success": False,
                "message": f"Error sending broadcast: {str(e)}",
                "sent_count": 0,
                "total_users": 0
            }

# Global email service instance
email_service = EmailService()