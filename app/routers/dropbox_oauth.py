import os
import json
import requests
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse
import logging

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dropbox", tags=["dropbox-oauth"])

# Dropbox OAuth Configuration
DROPBOX_CLIENT_ID = os.getenv("DROPBOX_CLIENT_ID", "")
DROPBOX_CLIENT_SECRET = os.getenv("DROPBOX_CLIENT_SECRET", "")
DROPBOX_REDIRECT_URI = os.getenv("DROPBOX_REDIRECT_URI", "")

class DropboxTokenManager:
    """Manages Dropbox OAuth tokens including refresh functionality"""

    def __init__(self):
        self.client_id = DROPBOX_CLIENT_ID
        self.client_secret = DROPBOX_CLIENT_SECRET
        self.redirect_uri = DROPBOX_REDIRECT_URI

    def get_authorization_url(self) -> str:
        """Generate Dropbox OAuth authorization URL with offline access"""
        base_url = "https://www.dropbox.com/oauth2/authorize"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "token_access_type": "offline",  # This is key for refresh tokens
            "scope": "files.metadata.write files.content.write files.content.read account_info.read"
        }

        param_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_url}?{param_string}"

    async def exchange_code_for_tokens(self, authorization_code: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens"""
        try:
            url = "https://api.dropboxapi.com/oauth2/token"
            data = {
                "code": authorization_code,
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri
            }

            response = requests.post(url, data=data)

            if response.status_code == 200:
                token_data = response.json()
                logger.info("Successfully obtained Dropbox tokens")
                return {
                    "success": True,
                    "access_token": token_data.get("access_token"),
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_in": token_data.get("expires_in"),
                    "token_type": token_data.get("token_type", "Bearer")
                }
            else:
                error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
                logger.error(f"Failed to exchange code for tokens: {response.status_code} - {error_data}")
                return {
                    "success": False,
                    "error": f"Token exchange failed: {response.status_code}",
                    "details": error_data
                }

        except Exception as e:
            logger.error(f"Error exchanging code for tokens: {e}")
            return {
                "success": False,
                "error": f"Token exchange error: {str(e)}"
            }

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Use refresh token to get a new access token"""
        try:
            url = "https://api.dropboxapi.com/oauth2/token"
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }

            response = requests.post(url, data=data)

            if response.status_code == 200:
                token_data = response.json()
                logger.info("Successfully refreshed Dropbox access token")
                return {
                    "success": True,
                    "access_token": token_data.get("access_token"),
                    "expires_in": token_data.get("expires_in"),
                    "token_type": token_data.get("token_type", "Bearer")
                }
            else:
                error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
                logger.error(f"Failed to refresh access token: {response.status_code} - {error_data}")
                return {
                    "success": False,
                    "error": f"Token refresh failed: {response.status_code}",
                    "details": error_data
                }

        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            return {
                "success": False,
                "error": f"Token refresh error: {str(e)}"
            }

# Global token manager instance
token_manager = DropboxTokenManager()

@router.get("/auth")
async def initiate_dropbox_auth():
    """Initiate Dropbox OAuth flow"""
    if not all([DROPBOX_CLIENT_ID, DROPBOX_CLIENT_SECRET, DROPBOX_REDIRECT_URI]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dropbox OAuth not configured. Missing CLIENT_ID, CLIENT_SECRET, or REDIRECT_URI"
        )

    auth_url = token_manager.get_authorization_url()
    return {"authorization_url": auth_url}

@router.get("/callback")
async def dropbox_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None)
):
    """Handle Dropbox OAuth callback"""
    if error:
        logger.error(f"Dropbox OAuth error: {error} - {error_description}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth authorization failed: {error_description or error}"
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code not provided"
        )

    # Exchange code for tokens
    token_result = await token_manager.exchange_code_for_tokens(code)

    if not token_result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to obtain tokens: {token_result.get('error')}"
        )

    return {
        "message": "Dropbox authorization successful",
        "access_token": token_result.get("access_token"),
        "refresh_token": token_result.get("refresh_token"),
        "expires_in": token_result.get("expires_in"),
        "instructions": {
            "access_token": "Set DROPBOX_ACCESS_TOKEN environment variable with the access_token",
            "refresh_token": "Set DROPBOX_REFRESH_TOKEN environment variable with the refresh_token"
        }
    }

@router.post("/refresh-token")
async def refresh_dropbox_token():
    """Refresh Dropbox access token using stored refresh token"""
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refresh token not configured. Set DROPBOX_REFRESH_TOKEN environment variable."
        )

    result = await token_manager.refresh_access_token(refresh_token)

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to refresh token: {result.get('error')}"
        )

    return {
        "message": "Token refreshed successfully",
        "access_token": result.get("access_token"),
        "expires_in": result.get("expires_in"),
        "instructions": "Update DROPBOX_ACCESS_TOKEN environment variable with the new access_token"
    }