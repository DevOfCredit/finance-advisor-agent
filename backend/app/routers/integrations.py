"""
Integration routes for syncing data from Gmail, Calendar, and HubSpot.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db, SessionLocal
from app.models import User, Email, Contact
from app.services.google_service import GoogleService
from app.services.hubspot_service import HubSpotService
from app.services.rag_service import get_embedding
from app.routers.chat import get_current_user

router = APIRouter()

# In-memory sync status tracking
# Format: {user_id: {"gmail": {"syncing": bool, "started_at": datetime}, "hubspot": {...}}}
sync_status = {}


@router.post("/sync/gmail")
async def sync_gmail(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Sync emails from Gmail.
    Runs in background to import all emails and create embeddings.
    """
    user = get_current_user(authorization, db)
    
    if not user.google_access_token:
        raise HTTPException(
            status_code=400,
            detail="Google not connected"
        )
    
    # Mark sync as in progress
    if user.id not in sync_status:
        sync_status[user.id] = {}
    sync_status[user.id]["gmail"] = {
        "syncing": True,
        "started_at": datetime.utcnow().isoformat()
    }
    
    # Add background task - don't pass db session, create new one in background task
    background_tasks.add_task(sync_gmail_background, user.id)
    
    return {"message": "Gmail sync started"}


async def sync_gmail_background(user_id: int):
    """
    Background task to sync Gmail emails.
    Creates its own database session since request session will be closed.
    """
    # Create a new database session for the background task
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.google_access_token:
            return
        
        google_service = GoogleService(user.google_access_token)
        
        try:
            # Get all emails
            page_token = None
            imported_count = 0
        
            while True:
                result = await google_service.list_emails(max_results=100, page_token=page_token)
                messages = result.get("messages", [])
                
                for msg in messages:
                    gmail_id = msg["id"]
                    
                    # Check if already imported
                    existing = db.query(Email).filter(
                        Email.user_id == user_id,
                        Email.gmail_id == gmail_id
                    ).first()
                    
                    if existing:
                        continue
                    
                    # Get full email
                    email_data = await google_service.get_email(gmail_id)
                    parsed = google_service._parse_email(email_data)
                    
                    # Create email record
                    email_obj = Email(
                        user_id=user_id,
                        gmail_id=gmail_id,
                        thread_id=parsed.get("thread_id"),
                        subject=parsed.get("subject"),
                        from_email=parsed.get("from_email"),
                        to_emails=parsed.get("to_emails"),
                        cc_emails=parsed.get("cc_emails"),
                        body_text=parsed.get("body_text"),
                        body_html=parsed.get("body_html"),
                        received_at=parsed.get("received_at")
                    )
                    
                    db.add(email_obj)
                    db.commit()
                    db.refresh(email_obj)
                    
                    # Create embedding
                    text_content = f"{parsed.get('subject', '')} {parsed.get('body_text', '')}"
                    if text_content.strip():
                        embedding = get_embedding(text_content)
                        email_obj.embedding = embedding
                        db.commit()
                    
                    imported_count += 1
                    
                    # Process ongoing instructions for new email
                    from app.services.ai_agent import AIAgent
                    agent = AIAgent(db, user)
                    await agent.process_ongoing_instructions("email", {
                        "email_id": gmail_id,
                        "from": parsed.get("from_email"),
                        "subject": parsed.get("subject"),
                        "body": parsed.get("body_text")
                    })
                
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
            
            # Mark sync as completed
            if user_id in sync_status and "gmail" in sync_status[user_id]:
                sync_status[user_id]["gmail"]["syncing"] = False
                sync_status[user_id]["gmail"]["completed_at"] = datetime.utcnow().isoformat()
                sync_status[user_id]["gmail"]["imported_count"] = imported_count
            
            print(f"Gmail sync completed for user {user_id}. Imported {imported_count} emails.")
        
        except Exception as e:
            print(f"Error syncing Gmail for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            # Mark sync as failed
            if user_id in sync_status and "gmail" in sync_status[user_id]:
                sync_status[user_id]["gmail"]["syncing"] = False
                sync_status[user_id]["gmail"]["error"] = str(e)
                sync_status[user_id]["gmail"]["completed_at"] = datetime.utcnow().isoformat()
    finally:
        # Always close the database session
        db.close()


@router.post("/sync/hubspot")
async def sync_hubspot(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Sync contacts from HubSpot.
    Runs in background to import all contacts and create embeddings.
    """
    user = get_current_user(authorization, db)
    
    if not user.hubspot_access_token:
        raise HTTPException(
            status_code=400,
            detail="HubSpot not connected"
        )
    
    # Mark sync as in progress
    if user.id not in sync_status:
        sync_status[user.id] = {}
    sync_status[user.id]["hubspot"] = {
        "syncing": True,
        "started_at": datetime.utcnow().isoformat()
    }
    
    # Add background task - don't pass db session, create new one in background task
    background_tasks.add_task(sync_hubspot_background, user.id)
    
    return {"message": "HubSpot sync started"}


async def sync_hubspot_background(user_id: int):
    """
    Background task to sync HubSpot contacts.
    Creates its own database session since request session will be closed.
    """
    # Create a new database session for the background task
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.hubspot_access_token:
            return
        
        hubspot_service = HubSpotService(user.hubspot_access_token)
        
        try:
            imported_count = 0
            after = None
        
            while True:
                result = await hubspot_service.list_all_contacts(limit=100, after=after)
                contacts = result.get("results", [])
                
                for contact_data in contacts:
                    hubspot_id = contact_data["id"]
                    properties = contact_data.get("properties", {})
                    
                    # Check if already imported
                    existing = db.query(Contact).filter(
                        Contact.user_id == user_id,
                        Contact.hubspot_id == hubspot_id
                    ).first()
                    
                    if existing:
                        # Update existing
                        existing.email = properties.get("email")
                        existing.first_name = properties.get("firstname")
                        existing.last_name = properties.get("lastname")
                        existing.phone = properties.get("phone")
                        existing.company = properties.get("company")
                        existing.raw_data = contact_data
                    else:
                        # Get notes
                        notes_data = await hubspot_service.get_contact_notes(hubspot_id)
                        notes_text = "\n".join([
                            n.get("properties", {}).get("hs_note_body", "")
                            for n in notes_data
                        ])
                        
                        # Create contact
                        contact_obj = Contact(
                            user_id=user_id,
                            hubspot_id=hubspot_id,
                            email=properties.get("email"),
                            first_name=properties.get("firstname"),
                            last_name=properties.get("lastname"),
                            phone=properties.get("phone"),
                            company=properties.get("company"),
                            notes=notes_text,
                            raw_data=contact_data
                        )
                        
                        db.add(contact_obj)
                        db.commit()
                        db.refresh(contact_obj)
                        
                        # Create embedding
                        text_content = f"{properties.get('firstname', '')} {properties.get('lastname', '')} {properties.get('email', '')} {notes_text}"
                        if text_content.strip():
                            embedding = get_embedding(text_content)
                            contact_obj.embedding = embedding
                            db.commit()
                        
                        imported_count += 1
                
                # Check for pagination
                paging = result.get("paging", {})
                after = paging.get("next", {}).get("after")
                if not after:
                    break
            
            # Mark sync as completed
            if user_id in sync_status and "hubspot" in sync_status[user_id]:
                sync_status[user_id]["hubspot"]["syncing"] = False
                sync_status[user_id]["hubspot"]["completed_at"] = datetime.utcnow().isoformat()
                sync_status[user_id]["hubspot"]["imported_count"] = imported_count
            
            print(f"HubSpot sync completed for user {user_id}. Imported {imported_count} contacts.")
        
        except Exception as e:
            print(f"Error syncing HubSpot for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            # Mark sync as failed
            if user_id in sync_status and "hubspot" in sync_status[user_id]:
                sync_status[user_id]["hubspot"]["syncing"] = False
                sync_status[user_id]["hubspot"]["error"] = str(e)
                sync_status[user_id]["hubspot"]["completed_at"] = datetime.utcnow().isoformat()
    finally:
        # Always close the database session
        db.close()


@router.get("/status")
async def get_integration_status(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """
    Get status of all integrations.
    """
    user = get_current_user(authorization, db)
    
    # Count emails and contacts
    email_count = db.query(Email).filter(Email.user_id == user.id).count()
    contact_count = db.query(Contact).filter(Contact.user_id == user.id).count()
    
    # Get sync status
    user_sync_status = sync_status.get(user.id, {})
    gmail_sync = user_sync_status.get("gmail", {"syncing": False})
    hubspot_sync = user_sync_status.get("hubspot", {"syncing": False})
    
    return {
        "google": {
            "connected": bool(user.google_access_token),
            "email": user.google_email,
            "email_count": email_count,
            "syncing": gmail_sync.get("syncing", False)
        },
        "hubspot": {
            "connected": bool(user.hubspot_access_token),
            "name": user.hubspot_name,
            "contact_count": contact_count,
            "syncing": hubspot_sync.get("syncing", False)
        }
    }


async def poll_new_emails(user_id: int):
    """
    Scheduled polling function to check for new emails.
    Only imports emails received in the last 10 minutes (to avoid missing any).
    Runs automatically every 5 minutes.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.google_access_token:
            return
        
        # Don't poll if a manual sync is already in progress
        if user_id in sync_status and sync_status[user_id].get("gmail", {}).get("syncing", False):
            return
        
        google_service = GoogleService(user.google_access_token)
        
        # Get the most recent email's received_at timestamp
        # Check for emails received in the last 10 minutes (to catch any we might have missed)
        cutoff_time = datetime.utcnow() - timedelta(minutes=10)
        
        # Convert to Unix timestamp for Gmail query
        cutoff_timestamp = int(cutoff_time.timestamp())
        
        # Gmail query to get emails after the cutoff time
        query = f"after:{cutoff_timestamp}"
        
        imported_count = 0
        page_token = None
        
        while True:
            result = await google_service.list_emails(
                max_results=100, 
                page_token=page_token,
                query=query
            )
            messages = result.get("messages", [])
            
            if not messages:
                break
            
            for msg in messages:
                gmail_id = msg["id"]
                
                # Check if already imported
                existing = db.query(Email).filter(
                    Email.user_id == user_id,
                    Email.gmail_id == gmail_id
                ).first()
                
                if existing:
                    continue
                
                # Get full email
                email_data = await google_service.get_email(gmail_id)
                parsed = google_service._parse_email(email_data)
                
                # Only import if received after cutoff (double check)
                if parsed.get("received_at"):
                    try:
                        from dateutil import parser
                        received_at = parser.parse(parsed["received_at"])
                        # Convert to UTC naive datetime for comparison
                        if received_at.tzinfo:
                            received_at = received_at.astimezone(tz=None).replace(tzinfo=None)
                        if received_at < cutoff_time:
                            continue
                    except:
                        # If parsing fails, import anyway (better safe than sorry)
                        pass
                
                # Create email record
                email_obj = Email(
                    user_id=user_id,
                    gmail_id=gmail_id,
                    thread_id=parsed.get("thread_id"),
                    subject=parsed.get("subject"),
                    from_email=parsed.get("from_email"),
                    to_emails=parsed.get("to_emails"),
                    cc_emails=parsed.get("cc_emails"),
                    body_text=parsed.get("body_text"),
                    body_html=parsed.get("body_html"),
                    received_at=parsed.get("received_at")
                )
                
                db.add(email_obj)
                db.commit()
                db.refresh(email_obj)
                
                # Create embedding
                text_content = f"{parsed.get('subject', '')} {parsed.get('body_text', '')}"
                if text_content.strip():
                    embedding = get_embedding(text_content)
                    email_obj.embedding = embedding
                    db.commit()
                
                imported_count += 1
                
                # Process ongoing instructions for new email
                from app.services.ai_agent import AIAgent
                agent = AIAgent(db, user)
                await agent.process_ongoing_instructions("email", {
                    "email_id": gmail_id,
                    "from": parsed.get("from_email"),
                    "subject": parsed.get("subject"),
                    "body": parsed.get("body_text")
                })
            
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        
        if imported_count > 0:
            print(f"Polled {imported_count} new emails for user {user_id}")
        
    except Exception as e:
        print(f"Error polling new emails for user {user_id}: {e}")
    finally:
        db.close()


async def scheduled_email_polling():
    """
    Scheduled task that runs every 5 minutes.
    Polls all users with Google connected for new emails.
    """
    db = SessionLocal()
    try:
        # Get all users with Google connected
        users = db.query(User).filter(
            User.google_access_token.isnot(None)
        ).all()
        
        for user in users:
            # Run polling for each user (they run concurrently)
            await poll_new_emails(user.id)
    
    except Exception as e:
        print(f"Error in scheduled email polling: {e}")
    finally:
        db.close()

