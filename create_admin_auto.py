#!/usr/bin/env python3
"""
Script to create the first admin user for the Iskandar Community application automatically.
This creates a default admin user with predetermined credentials.
"""

import asyncio
import sys
from datetime import datetime
from app.database import connect_to_mongo, close_mongo_connection, get_collection
from app.auth import hash_password
from app.models.user import UserRole

async def create_default_admin():
    """Create a default admin user"""
    try:
        # Connect to MongoDB
        await connect_to_mongo()
        print("[OK] Connected to MongoDB")
        
        users_collection = get_collection("users")
        
        # Check if any admin user already exists
        existing_admin = await users_collection.find_one({"role": "admin"})
        if existing_admin:
            print("[ERROR] An admin user already exists:")
            print(f"   Email: {existing_admin['email']}")
            print(f"   Name: {existing_admin['name']}")
            print("\nUse the existing admin account to manage users, or delete it first if needed.")
            return
        
        # Default admin credentials
        email = "admin@iskandar.com"
        name = "Admin User"
        password = "admin123"
        phone = "+1234567890"
        
        print("\n[AUTH] Creating default admin user for Iskandar Community")
        print("=" * 50)
        print(f"Email: {email}")
        print(f"Name: {name}")
        print(f"Password: {password}")
        print(f"Phone: {phone}")
        
        # Check if email already exists
        existing_user = await users_collection.find_one({"email": email})
        if existing_user:
            print(f"[ERROR] A user with email {email} already exists")
            return
        
        # Create admin user
        admin_user = {
            "email": email,
            "name": name,
            "password_hash": hash_password(password),
            "role": UserRole.ADMIN,
            "is_active": True,
            "avatar": None,
            "phone": phone,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await users_collection.insert_one(admin_user)
        print(f"\n[SUCCESS] Admin user created successfully!")
        print(f"   ID: {result.inserted_id}")
        print(f"   Email: {email}")
        print(f"   Name: {name}")
        print(f"   Role: Admin")
        
        print(f"\n[LOGIN] You can now login at the application with:")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"\n[IMPORTANT] Change the default password after first login!")
        
        # Close connection
        await close_mongo_connection()
        print("\n[OK] Database connection closed")
        
    except Exception as e:
        print(f"[ERROR] Error creating admin user: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Iskandar Community - Default Admin User Creation")
    print("=" * 50)
    asyncio.run(create_default_admin())