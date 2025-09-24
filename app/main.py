from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import connect_to_mongo, close_mongo_connection
from app.routers import posts, comments, chat, files, auth, categories, notifications, news, activity_logs, backup, dropbox_oauth, telegram
from app.services.scheduler_service import scheduler_service
from app.services.telegram_service import telegram_service
from app.database import get_collection
import socketio
import os
from datetime import datetime, timedelta
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# Get CORS origins from environment variable or use defaults
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,https://yskandar.com")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",")]

sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=cors_origins
)

app = FastAPI(
    title="Iskandar Community API",
    description="Private community web application API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()
    # Start the backup scheduler
    await scheduler_service.start()

@app.on_event("shutdown")
async def shutdown_db_client():
    # Stop the backup scheduler
    await scheduler_service.stop()
    await close_mongo_connection()

@app.get("/")
async def root():
    return {"message": "Welcome to Iskandar Community API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(categories.router, prefix="/categories", tags=["categories"])
app.include_router(posts.router, prefix="/posts", tags=["posts"])
app.include_router(comments.router, prefix="/comments", tags=["comments"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(files.router, prefix="/files", tags=["files"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(news.router, prefix="/news", tags=["news"])
app.include_router(activity_logs.router, prefix="/activity-logs", tags=["activity_logs"])
app.include_router(backup.router, prefix="/backup", tags=["backup"])
app.include_router(dropbox_oauth.router, tags=["dropbox-oauth"])
app.include_router(telegram.router, tags=["telegram"])

socket_app = socketio.ASGIApp(sio, app)

# Store online users
online_users = {}

# Track last chat activity for admin notifications
last_chat_notification = None

@sio.event
async def connect(sid, environ):
    print(f"Client {sid} connected")

@sio.event
async def disconnect(sid):
    print(f"Client {sid} disconnected")
    # Remove user from online users if they were tracked
    user_to_remove = None
    for user_id, user_data in online_users.items():
        if user_data.get('socket_id') == sid:
            user_to_remove = user_id
            break
    
    if user_to_remove:
        del online_users[user_to_remove]
        # Broadcast updated user list
        await sio.emit('users_online_update', list(online_users.values()))

@sio.event
async def send_message(sid, data):
    global last_chat_notification

    # Emit the message to other users
    await sio.emit('receive_message', data, skip_sid=sid)

    # Check if we should send Telegram notification to admins
    await check_and_send_chat_notification(data)

@sio.event
async def user_online(sid, data):
    """Handle user coming online"""
    user_id = data.get('id')
    user_name = data.get('name')
    user_role = data.get('role')
    
    if user_id and user_name:
        online_users[user_id] = {
            'id': user_id,
            'name': user_name,
            'role': user_role,
            'socket_id': sid
        }
        
        # Broadcast updated user list to all clients
        await sio.emit('users_online_update', list(online_users.values()))
        print(f"User {user_name} is now online")

@sio.event
async def user_offline(sid, user_id):
    """Handle user going offline"""
    if user_id in online_users:
        user_name = online_users[user_id]['name']
        del online_users[user_id]
        
        # Broadcast updated user list to all clients
        await sio.emit('users_online_update', list(online_users.values()))
        print(f"User {user_name} went offline")

async def check_and_send_chat_notification(message_data):
    """Check if we should send chat activity notification to admins"""
    global last_chat_notification

    try:
        current_time = datetime.utcnow()

        # Determine if we should send notification
        should_notify = False

        if last_chat_notification is None:
            # First message ever
            should_notify = True
            reason = "primera actividad de chat detectada"
        else:
            time_diff = current_time - last_chat_notification
            # Notify if more than 2 hours have passed
            if time_diff > timedelta(hours=2):
                should_notify = True
                reason = f"nueva sesión después de {int(time_diff.total_seconds() / 3600)} horas de silencio"

        if should_notify:
            # Update last notification time
            last_chat_notification = current_time

            # Get admin users with Telegram configured
            users_collection = get_collection("users")
            admin_users = await users_collection.find({
                "role": "admin",
                "is_active": True,
                "telegram_id": {"$exists": True, "$ne": None},
                "telegram_preferences.enabled": True,
                "telegram_preferences.admin_notifications": True
            }).to_list(None)

            if admin_users:
                admin_telegram_ids = [admin["telegram_id"] for admin in admin_users]

                # Get user name from message data
                user_name = message_data.get('user', 'Usuario Desconocido')
                message_preview = message_data.get('message', '')[:50]
                if len(message_data.get('message', '')) > 50:
                    message_preview += "..."

                # Send notification using the new chat notification method
                await telegram_service.send_admin_chat_notification(
                    admin_telegram_ids,
                    user_name,
                    message_preview,
                    reason
                )

                print(f"Sent chat notification to {len(admin_telegram_ids)} admins: {reason}")

    except Exception as e:
        print(f"Error sending chat notification: {e}")