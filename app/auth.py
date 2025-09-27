import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Union
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from app.config import settings
from app.database import get_collection
from app.models.user import TokenData, UserRole

# Security
security = HTTPBearer()

# JWT Settings
SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> TokenData:
    """Verify and decode JWT token"""
    try:
        print(f"Verifying token: {token[:50]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"Token payload: {payload}")
        email: str = payload.get("sub")
        if email is None:
            print("Error: No email in token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        
        token_data = TokenData(
            email=email,
            user_id=payload.get("user_id"),
            name=payload.get("name"),
            role=UserRole(payload.get("role")),
            is_active=payload.get("is_active", True)
        )
        print(f"Token verification successful for user: {token_data.name}")
        return token_data
    except jwt.PyJWTError as e:
        print(f"JWT Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenData:
    """Get current authenticated user"""
    token = credentials.credentials
    token_data = verify_token(token)
    
    # Verify user still exists and is active
    users_collection = get_collection("users")
    user = await users_collection.find_one({"_id": ObjectId(token_data.user_id), "is_active": True})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    return token_data

async def get_current_active_user(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user

async def get_current_admin_user(current_user: TokenData = Depends(get_current_active_user)) -> TokenData:
    """Get current admin user (role-based access control)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

async def authenticate_user(name: str, password: str) -> Optional[dict]:
    """Authenticate user credentials"""
    users_collection = get_collection("users")
    user = await users_collection.find_one({"name": name})
    
    if not user:
        return None
    
    if not verify_password(password, user["password_hash"]):
        return None
    
    if not user.get("is_active", True):
        return None
    
    return user

def create_user_token(user: dict) -> str:
    """Create JWT token for user"""
    token_data = {
        "sub": user["email"],
        "user_id": str(user["_id"]),
        "name": user["name"],
        "role": user["role"],
        "is_active": user.get("is_active", True)
    }
    return create_access_token(token_data)