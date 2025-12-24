"""
Authentication routes.

Handles Google OAuth and HubSpot OAuth flows.
"""

from fastapi import APIRouter, Header, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.httpx_client import AsyncOAuth2Client
from app.database import get_db
from app.models import User
from app.auth import create_access_token
from app.config import settings
from app.services.google_service import GoogleService
from app.services.hubspot_service import HubSpotService
from typing import Optional
import httpx

router = APIRouter()


@router.get("/google")
async def google_auth():
    """
    Initiate Google OAuth flow.
    Redirects user to Google consent screen.
    """
    oauth = AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    # Request scopes for Gmail and Calendar
    authorization_url, state = oauth.create_authorization_url(
        "https://accounts.google.com/o/oauth2/v2/auth",
        scope=[
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
            "openid",
            "email",
            "profile",
        ]
    )
    
    # In production, store state in session/redis for CSRF protection
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
async def google_callback(code: str, db: Session = Depends(get_db)):
    """
    Handle Google OAuth callback.
    Exchanges authorization code for tokens and creates/updates user.
    """
    oauth = AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    try:
        # Exchange code for tokens
        token = await oauth.fetch_token(
            "https://oauth2.googleapis.com/token",
            code=code
        )
        
        access_token = token["access_token"]
        refresh_token = token.get("refresh_token")
        expires_at = None
        if "expires_in" in token:
            from datetime import datetime, timedelta, timezone
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=token["expires_in"])
        
        # Get user info
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_info = response.json()
        
        email = user_info.get("email")
        name = user_info.get("name")
        
        if not email:
            raise HTTPException(status_code=400, detail="Could not get user email")
        
        # Get Gmail address (might be different from OAuth email)
        google_service = GoogleService(access_token)
        gmail_profile = await google_service.get_gmail_profile()
        gmail_address = gmail_profile.get("emailAddress", email)
        
        # Find or create user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                name=name,
                google_access_token=access_token,
                google_refresh_token=refresh_token,
                google_token_expires_at=expires_at,
                google_email=gmail_address
            )
            db.add(user)
        else:
            # Update existing user
            user.google_access_token = access_token
            user.google_refresh_token = refresh_token
            user.google_token_expires_at = expires_at
            user.google_email = gmail_address
            if name:
                user.name = name
        
        db.commit()
        db.refresh(user)
        
        # Create JWT token
        jwt_token = create_access_token({"user_id": user.id, "email": user.email})
        
        # Redirect to frontend with token
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/callback?token={jwt_token}"
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"OAuth callback failed: {str(e)}"
        )


@router.get("/hubspot")
async def hubspot_auth(
    token: Optional[str] = Query(None, description="JWT token for authentication"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Initiate HubSpot OAuth flow.
    Redirects user to HubSpot consent screen.
    Requires authentication to identify which user is connecting.
    Accepts token as query parameter or Authorization header.
    """
    # Get token from query parameter or header
    auth_token = token
    if not auth_token and authorization and authorization.startswith("Bearer "):
        auth_token = authorization.split(" ")[1]
    
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in first."
        )
    
    from app.auth import verify_token
    payload = verify_token(auth_token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Encode user_id in state parameter
    import base64
    import json
    state_data = {"user_id": user_id}
    state_encoded = base64.urlsafe_b64encode(
        json.dumps(state_data).encode()
    ).decode()
    
    oauth = AsyncOAuth2Client(
        client_id=settings.HUBSPOT_CLIENT_ID,
        client_secret=settings.HUBSPOT_CLIENT_SECRET,
        redirect_uri=settings.HUBSPOT_REDIRECT_URI
    )
    
    authorization_url, state = oauth.create_authorization_url(
        "https://app.hubspot.com/oauth/authorize",
        scope=[
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "oauth",
        ],
        state=state_encoded  # Use our encoded state with user_id
    )
    
    return RedirectResponse(url=authorization_url)


@router.get("/hubspot/callback")
async def hubspot_callback(code: str, state: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Handle HubSpot OAuth callback.
    Exchanges authorization code for tokens and updates user.
    """
    try:
        # Decode user_id from state parameter
        user_id = None
        if state:
            try:
                import base64
                import json
                state_decoded = base64.urlsafe_b64decode(state.encode()).decode()
                state_data = json.loads(state_decoded)
                user_id = state_data.get("user_id")
            except Exception as e:
                print(f"Error decoding state: {e}")
                # If state decoding fails, fall back to most recent user (backward compatibility)
                pass
        
        # HubSpot's token endpoint requires specific parameters
        # Using direct HTTP request as authlib might not format it correctly
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://api.hubapi.com/oauth/v1/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.HUBSPOT_CLIENT_ID,
                    "client_secret": settings.HUBSPOT_CLIENT_SECRET,
                    "redirect_uri": settings.HUBSPOT_REDIRECT_URI,
                    "code": code
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            token_response.raise_for_status()
            token = token_response.json()
        
        access_token = token["access_token"]
        refresh_token = token.get("refresh_token")
        expires_at = None
        if "expires_in" in token:
            from datetime import datetime, timedelta, timezone
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=token["expires_in"])
        
        # Get account info
        hubspot_service = HubSpotService(access_token)
        account_info = await hubspot_service.get_account_info()
        account_name = account_info.get("portalId") or "HubSpot Account"
        
        # Get user by user_id from state, or fall back to most recent user
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
        else:
            # Fallback: get most recent user (for backward compatibility)
            user = db.query(User).order_by(User.id.desc()).first()
        
        if not user:
            raise HTTPException(
                status_code=404, 
                detail="User not found. Please log in with Google first."
            )
        
        # Update user with HubSpot tokens
        user.hubspot_access_token = access_token
        user.hubspot_refresh_token = refresh_token
        user.hubspot_token_expires_at = expires_at
        user.hubspot_name = account_name
        
        db.commit()
        
        # Redirect to frontend
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/callback?hubspot=connected"
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"HubSpot OAuth callback failed: {str(e)}"
        )


@router.get("/me")
async def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get current user information.
    Requires JWT token in Authorization header.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )
    
    token = authorization.split(" ")[1]
    from app.auth import verify_token
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "google_email": user.google_email,
        "hubspot_name": user.hubspot_name,
        "has_google": bool(user.google_access_token),
        "has_hubspot": bool(user.hubspot_access_token)
    }

