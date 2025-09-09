from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import connect_to_mongo, close_mongo_connection
from app.routers import posts, comments, chat, files, auth, categories, notifications
import socketio
import os
from dotenv import load_dotenv

load_dotenv()

# Get CORS origins from environment variable or use defaults
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,https://iskandaria.netlify.app")
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

@app.on_event("shutdown")
async def shutdown_db_client():
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

socket_app = socketio.ASGIApp(sio, app)

# Store online users
online_users = {}

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
    await sio.emit('receive_message', data, skip_sid=sid)

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