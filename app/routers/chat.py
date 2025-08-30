from fastapi import APIRouter, HTTPException, status
from typing import List
from datetime import datetime
from app.models.chat import ChatMessageModel, ChatMessageCreate, ChatMessageResponse
from app.database import get_collection

router = APIRouter()

@router.get("/messages", response_model=List[ChatMessageResponse])
async def get_recent_messages(limit: int = 50):
    collection = get_collection("chat_messages")
    messages = []
    
    # First update any messages missing created_at field
    await collection.update_many(
        {"created_at": {"$exists": False}}, 
        {"$set": {"created_at": datetime.utcnow()}}
    )
    
    async for message in collection.find().sort("created_at", -1).limit(limit):
        # Convert ObjectId to string for the response
        message["_id"] = str(message["_id"])
        messages.append(ChatMessageResponse(**message))
    return list(reversed(messages))

@router.post("/messages", response_model=ChatMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(message_data: ChatMessageCreate):
    collection = get_collection("chat_messages")
    
    message_dict = message_data.model_dump()
    message_dict["created_at"] = datetime.utcnow()
    
    result = await collection.insert_one(message_dict)
    created_message = await collection.find_one({"_id": result.inserted_id})
    
    # Convert ObjectId to string for the response
    created_message["_id"] = str(created_message["_id"])
    return ChatMessageResponse(**created_message)