from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import connect_to_mongo, close_mongo_connection
from app.routers import posts, comments, chat, files, auth, categories, notifications, news, activity_logs, backup, dropbox_oauth, telegram, video_calls, calendar
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
app.include_router(video_calls.router, prefix="/video-calls", tags=["video_calls"])
app.include_router(calendar.router, prefix="/calendar", tags=["calendar"])

socket_app = socketio.ASGIApp(sio, app)

# Store online users
online_users = {}

# Store active video call participants: sid -> (call_id, user_id, username)
active_video_calls = {}

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

    # Handle video call cleanup for sudden disconnections
    if sid in active_video_calls:
        call_id, user_id, username = active_video_calls[sid]
        print(f"Cleaning up video call for disconnected user {username} in call {call_id}")

        # Remove from tracking
        del active_video_calls[sid]

        # Update database: remove participant
        try:
            from app.database import get_collection
            from bson import ObjectId

            collection = get_collection("video_calls")

            # Remove participant
            await collection.update_one(
                {"_id": ObjectId(call_id)},
                {"$pull": {"participants": {"user_id": ObjectId(user_id)}}}
            )
            print(f"Cleaned up DB: Removed participant {username} from call {call_id}")

            # Check if call should be reset (no participants left)
            call = await collection.find_one({"_id": ObjectId(call_id)})
            if call and len(call.get("participants", [])) == 0:
                await collection.update_one(
                    {"_id": ObjectId(call_id)},
                    {
                        "$set": {
                            "status": "waiting",
                            "started_at": None
                        }
                    }
                )
                print(f"Call {call_id} reset to waiting (no participants after disconnect)")

        except Exception as e:
            print(f"Error cleaning up video call on disconnect: {e}")

        # Notify others in the room about the disconnection
        await sio.emit('webrtc_user_left', {
            'userId': user_id
        }, room=f"webrtc_call_{call_id}")

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

@sio.event
async def send_video_call_invitation(sid, data):
    """Handle video call invitation"""
    caller_id = data.get('caller_id')
    callee_id = data.get('callee_id')
    call_id = data.get('call_id')
    channel_name = data.get('channel_name')
    call_type = data.get('call_type')

    # Find the target user's socket ID
    target_socket_id = None
    if callee_id in online_users:
        target_socket_id = online_users[callee_id]['socket_id']

    if target_socket_id:
        # Send invitation to specific user
        invitation_data = {
            'call_id': call_id,
            'caller_name': data.get('caller_name'),
            'caller_id': caller_id,
            'channel_name': channel_name,
            'call_type': call_type
        }
        print(f"Sending video call invitation: {invitation_data}")
        await sio.emit('video_call_invitation', invitation_data, room=target_socket_id)
        print(f"Sent video call invitation from {caller_id} to {callee_id}")

@sio.event
async def video_call_response(sid, data):
    """Handle video call response (accept/decline)"""
    print(f"Received video_call_response: {data}")
    caller_id = data.get('caller_id')
    response = data.get('response')  # 'accepted' or 'declined'
    call_id = data.get('call_id')
    print(f"Extracted call_id: {call_id} (type: {type(call_id)})")

    # Find the caller's socket ID
    target_socket_id = None
    if caller_id in online_users:
        target_socket_id = online_users[caller_id]['socket_id']

    if target_socket_id:
        # Send response to caller
        await sio.emit('video_call_response', {
            'call_id': call_id,
            'response': response,
            'responder_name': data.get('responder_name')
        }, room=target_socket_id)
        print(f"Video call {response} for call {call_id}")

@sio.event
async def join_video_call_room(sid, data):
    """Handle user joining video call room"""
    call_id = data.get('call_id')
    user_name = data.get('user_name')

    # Join the socket room for this call
    await sio.enter_room(sid, f"video_call_{call_id}")

    # Notify others in the room
    await sio.emit('user_joined_call', {
        'user_name': user_name
    }, room=f"video_call_{call_id}", skip_sid=sid)

@sio.event
async def leave_video_call_room(sid, data):
    """Handle user leaving video call room"""
    call_id = data.get('call_id')
    user_name = data.get('user_name')

    # Leave the socket room for this call
    await sio.leave_room(sid, f"video_call_{call_id}")

    # Notify others in the room
    await sio.emit('user_left_call', {
        'user_name': user_name
    }, room=f"video_call_{call_id}")

@sio.event
async def video_call_signal(sid, data):
    """Handle video call signaling (screen share, mute, etc.)"""
    call_id = data.get('call_id')
    signal_type = data.get('signal_type')
    signal_data = data.get('signal_data')
    user_name = data.get('user_name')

    # Broadcast signal to others in the call
    await sio.emit('video_call_signal', {
        'signal_type': signal_type,
        'signal_data': signal_data,
        'user_name': user_name
    }, room=f"video_call_{call_id}", skip_sid=sid)

# WebRTC signaling events
@sio.event
async def join_webrtc_room(sid, data):
    """Handle user joining WebRTC room (new multi-participant format)"""
    call_id = data.get('callId')
    user_id = data.get('userId')
    username = data.get('username')

    print(f"User {username} joining WebRTC room {call_id}")

    # Track this connection
    active_video_calls[sid] = (call_id, user_id, username)

    # Join the socket room for this call
    await sio.enter_room(sid, f"webrtc_call_{call_id}")

    # Update database: add participant to the call
    try:
        from app.database import get_collection
        from bson import ObjectId
        from datetime import datetime

        collection = get_collection("video_calls")

        # Add participant if not already in the call
        participant = {
            "user_id": ObjectId(user_id),
            "username": username,
            "joined_at": datetime.utcnow()
        }

        # Remove any existing participant with same user_id to avoid duplicates
        await collection.update_one(
            {"_id": ObjectId(call_id)},
            {"$pull": {"participants": {"user_id": ObjectId(user_id)}}}
        )

        # Add the participant
        await collection.update_one(
            {"_id": ObjectId(call_id)},
            {
                "$addToSet": {"participants": participant},
                "$set": {
                    "status": "active",
                    "started_at": datetime.utcnow()
                }
            }
        )
        print(f"Updated DB: Added participant {username} to call {call_id}")

    except Exception as e:
        print(f"Error updating DB for join: {e}")

    # Notify others in the room
    await sio.emit('webrtc_user_joined', {
        'userId': user_id,
        'username': username
    }, room=f"webrtc_call_{call_id}", skip_sid=sid)

@sio.event
async def join_webrtc_call(sid, data):
    """Handle user joining WebRTC call"""
    call_id = data.get('callId')
    user_id = data.get('userId')
    username = data.get('username')

    print(f"User {username} joining WebRTC call {call_id}")

    # Track this connection
    active_video_calls[sid] = (call_id, user_id, username)

    # Join the socket room for this call
    await sio.enter_room(sid, f"webrtc_call_{call_id}")

    # Update database: add participant to the call
    try:
        from app.database import get_collection
        from bson import ObjectId
        from datetime import datetime

        collection = get_collection("video_calls")

        # Add participant if not already in the call
        participant = {
            "user_id": ObjectId(user_id),
            "username": username,
            "joined_at": datetime.utcnow()
        }

        # Remove any existing participant with same user_id to avoid duplicates
        await collection.update_one(
            {"_id": ObjectId(call_id)},
            {"$pull": {"participants": {"user_id": ObjectId(user_id)}}}
        )

        # Add the participant
        await collection.update_one(
            {"_id": ObjectId(call_id)},
            {
                "$addToSet": {"participants": participant},
                "$set": {
                    "status": "active",
                    "started_at": datetime.utcnow()
                }
            }
        )
        print(f"Updated DB: Added participant {username} to call {call_id}")

    except Exception as e:
        print(f"Error updating DB for join: {e}")

    # Notify others in the room
    await sio.emit('webrtc_user_joined', {
        'userId': user_id,
        'username': username
    }, room=f"webrtc_call_{call_id}", skip_sid=sid)

@sio.event
async def leave_webrtc_room(sid, data):
    """Handle user leaving WebRTC room (new multi-participant format)"""
    call_id = data.get('callId')
    user_id = data.get('userId')

    print(f"User {user_id} leaving WebRTC room {call_id}")

    # Get username before removing from tracking
    username = None
    if sid in active_video_calls:
        username = active_video_calls[sid][2]
        del active_video_calls[sid]

    # Leave the socket room for this call
    await sio.leave_room(sid, f"webrtc_call_{call_id}")

    # Update database: remove participant from the call
    try:
        from app.database import get_collection
        from bson import ObjectId
        from datetime import datetime

        collection = get_collection("video_calls")

        # Remove participant
        result = await collection.update_one(
            {"_id": ObjectId(call_id)},
            {"$pull": {"participants": {"user_id": ObjectId(user_id)}}}
        )
        print(f"Updated DB: Removed participant {user_id} from call {call_id}")

        # Check if call should be ended (no participants left)
        call = await collection.find_one({"_id": ObjectId(call_id)})
        if call and len(call.get("participants", [])) == 0:
            await collection.update_one(
                {"_id": ObjectId(call_id)},
                {
                    "$set": {
                        "status": "waiting",  # Reset to waiting instead of ended for meeting rooms
                        "started_at": None    # Reset start time
                    }
                }
            )
            print(f"Reset call {call_id} to waiting state (no participants left)")

    except Exception as e:
        print(f"Error updating DB for leave: {e}")

    # Notify others in the room
    await sio.emit('webrtc_user_left', {
        'userId': user_id,
        'username': username or 'Unknown'
    }, room=f"webrtc_call_{call_id}")

@sio.event
async def leave_webrtc_call(sid, data):
    """Handle user leaving WebRTC call"""
    call_id = data.get('callId')
    user_id = data.get('userId')

    print(f"User {user_id} leaving WebRTC call {call_id}")

    # Remove from tracking
    if sid in active_video_calls:
        del active_video_calls[sid]

    # Leave the socket room for this call
    await sio.leave_room(sid, f"webrtc_call_{call_id}")

    # Update database: remove participant from the call
    try:
        from app.database import get_collection
        from bson import ObjectId
        from datetime import datetime

        collection = get_collection("video_calls")

        # Remove participant
        result = await collection.update_one(
            {"_id": ObjectId(call_id)},
            {"$pull": {"participants": {"user_id": ObjectId(user_id)}}}
        )
        print(f"Updated DB: Removed participant {user_id} from call {call_id}")

        # Check if call should be ended (no participants left)
        call = await collection.find_one({"_id": ObjectId(call_id)})
        if call and len(call.get("participants", [])) == 0:
            await collection.update_one(
                {"_id": ObjectId(call_id)},
                {
                    "$set": {
                        "status": "waiting",  # Reset to waiting instead of ended for meeting rooms
                        "started_at": None    # Reset start time
                    }
                }
            )
            print(f"Call {call_id} reset to waiting (no participants)")

    except Exception as e:
        print(f"Error updating DB for leave: {e}")

    # Notify others in the room
    await sio.emit('webrtc_user_left', {
        'userId': user_id
    }, room=f"webrtc_call_{call_id}")

@sio.event
async def webrtc_offer(sid, data):
    """Handle WebRTC offer"""
    call_id = data.get('callId')
    offer = data.get('offer')
    from_user_id = data.get('fromUserId')
    target_user_id = data.get('targetUserId')

    print(f"Received WebRTC offer from {from_user_id} to {target_user_id} for call {call_id}")

    # Find target user's socket ID
    target_socket_id = None
    for socket_id, (stored_call_id, stored_user_id, username) in active_video_calls.items():
        if stored_user_id == target_user_id and stored_call_id == call_id:
            target_socket_id = socket_id
            break

    if target_socket_id:
        # Send offer directly to target user
        await sio.emit('webrtc_offer', {
            'offer': offer,
            'fromUserId': from_user_id
        }, room=target_socket_id)
        print(f"Forwarded offer from {from_user_id} to {target_user_id}")
    else:
        print(f"Target user {target_user_id} not found in active calls")

@sio.event
async def webrtc_answer(sid, data):
    """Handle WebRTC answer"""
    call_id = data.get('callId')
    answer = data.get('answer')
    from_user_id = data.get('fromUserId')
    target_user_id = data.get('targetUserId')

    print(f"Received WebRTC answer from {from_user_id} to {target_user_id} for call {call_id}")

    # Find target user's socket ID
    target_socket_id = None
    for socket_id, (stored_call_id, stored_user_id, username) in active_video_calls.items():
        if stored_user_id == target_user_id and stored_call_id == call_id:
            target_socket_id = socket_id
            break

    if target_socket_id:
        # Send answer directly to target user
        await sio.emit('webrtc_answer', {
            'answer': answer,
            'fromUserId': from_user_id
        }, room=target_socket_id)
        print(f"Forwarded answer from {from_user_id} to {target_user_id}")
    else:
        print(f"Target user {target_user_id} not found in active calls")

@sio.event
async def webrtc_ice_candidate(sid, data):
    """Handle WebRTC ICE candidate"""
    call_id = data.get('callId')
    candidate = data.get('candidate')
    from_user_id = data.get('fromUserId')
    target_user_id = data.get('targetUserId')

    print(f"Received ICE candidate from {from_user_id} to {target_user_id} for call {call_id}")

    # Find target user's socket ID
    target_socket_id = None
    for socket_id, (stored_call_id, stored_user_id, username) in active_video_calls.items():
        if stored_user_id == target_user_id and stored_call_id == call_id:
            target_socket_id = socket_id
            break

    if target_socket_id:
        # Send ICE candidate directly to target user
        await sio.emit('webrtc_ice_candidate', {
            'candidate': candidate,
            'fromUserId': from_user_id
        }, room=target_socket_id)
        print(f"Forwarded ICE candidate from {from_user_id} to {target_user_id}")
    else:
        print(f"Target user {target_user_id} not found in active calls")

@sio.event
async def webrtc_screen_share_status(sid, data):
    """Handle WebRTC screen share status updates"""
    call_id = data.get('callId')
    user_id = data.get('userId')
    is_screen_sharing = data.get('isScreenSharing')

    print(f"Screen share status update: {user_id} - sharing: {is_screen_sharing} for call {call_id}")

    # Forward screen share status to others in the room
    await sio.emit('webrtc_screen_share_status', {
        'userId': user_id,
        'isScreenSharing': is_screen_sharing
    }, room=f"webrtc_call_{call_id}", skip_sid=sid)

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