# Iskandar Community Backend

FastAPI backend for the Iskandar private community web application.

## Features

- **Blog System**: CRUD operations for posts and comments
- **Real-time Chat**: Socket.IO integration for group chat
- **File Repository**: File upload/download with Cloudinary storage
- **MongoDB Integration**: Async database operations with Motor

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Run the development server:
```bash
uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables

- `MONGODB_URL`: MongoDB connection string
- `DATABASE_NAME`: MongoDB database name (default: iskandar_community)
- `CLOUDINARY_CLOUD_NAME`: Cloudinary cloud name
- `CLOUDINARY_API_KEY`: Cloudinary API key
- `CLOUDINARY_API_SECRET`: Cloudinary API secret
- `CORS_ORIGINS`: Comma-separated allowed CORS origins

## API Endpoints

### Posts
- `GET /posts` - Get all posts
- `POST /posts` - Create new post
- `GET /posts/{post_id}` - Get specific post
- `PUT /posts/{post_id}` - Update post
- `DELETE /posts/{post_id}` - Delete post

### Comments
- `GET /comments/post/{post_id}` - Get comments for post
- `POST /comments/post/{post_id}` - Add comment to post
- `DELETE /comments/{comment_id}` - Delete comment

### Files
- `GET /files` - Get all files
- `POST /files/upload` - Upload file
- `GET /files/{file_id}` - Get file info
- `DELETE /files/{file_id}` - Delete file

### Chat
- `GET /chat/messages` - Get recent messages
- `POST /chat/messages` - Create message (also use Socket.IO)

## Socket.IO Events

- `connect` - Join chat room
- `send_message` - Send chat message
- `receive_message` - Receive chat message
- `disconnect` - Leave chat room

## Database Collections

- `posts` - Blog posts
- `comments` - Post comments
- `chat_messages` - Chat messages
- `files` - File metadata