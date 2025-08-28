#!/usr/bin/env python3

import asyncio
import sys
from app.database import connect_to_mongo, close_mongo_connection, get_collection

async def test_mongodb_connection():
    """Test MongoDB connection and basic operations."""
    try:
        print("Testing MongoDB connection...")
        
        # Connect to MongoDB
        await connect_to_mongo()
        print("✓ Connected to MongoDB successfully")
        
        # Test inserting a document
        collection = get_collection("test_collection")
        test_doc = {"message": "Hello from Iskandar API", "test": True}
        result = await collection.insert_one(test_doc)
        print(f"✓ Test document inserted with ID: {result.inserted_id}")
        
        # Test retrieving the document
        retrieved_doc = await collection.find_one({"_id": result.inserted_id})
        print(f"✓ Retrieved document: {retrieved_doc}")
        
        # Clean up test document
        await collection.delete_one({"_id": result.inserted_id})
        print("✓ Test document cleaned up")
        
        # Close connection
        await close_mongo_connection()
        print("✓ MongoDB connection closed")
        
        print("\n🎉 All MongoDB tests passed!")
        
    except Exception as e:
        print(f"❌ MongoDB test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_mongodb_connection())