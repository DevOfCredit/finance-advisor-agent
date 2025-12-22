"""
Google service for interacting with Gmail and Google Calendar APIs.
"""

import httpx
from typing import List, Dict, Optional
from datetime import datetime
import email
from email.utils import parsedate_to_datetime


class GoogleService:
    """
    Service for interacting with Google APIs (Gmail and Calendar).
    """
    
    def __init__(self, access_token: str):
        """
        Initialize Google service with access token.
        
        Args:
            access_token: OAuth access token for Google APIs
        """
        self.access_token = access_token
        self.base_url = "https://www.googleapis.com"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    async def get_gmail_profile(self) -> Dict:
        """Get Gmail profile information."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/gmail/v1/users/me/profile",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def list_emails(self, max_results: int = 100, page_token: Optional[str] = None, query: Optional[str] = None) -> Dict:
        """
        List emails from Gmail.
        
        Args:
            max_results: Maximum number of emails to retrieve
            page_token: Token for pagination
            query: Gmail search query (e.g., "after:1234567890" for emails after timestamp)
            
        Returns:
            Dictionary with emails list and next page token
        """
        async with httpx.AsyncClient() as client:
            params = {"maxResults": max_results}
            if page_token:
                params["pageToken"] = page_token
            if query:
                params["q"] = query
            
            response = await client.get(
                f"{self.base_url}/gmail/v1/users/me/messages",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
    
    async def get_email(self, message_id: str) -> Dict:
        """
        Get full email details including body.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Full email data with headers and body
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/gmail/v1/users/me/messages/{message_id}",
                headers=self.headers,
                params={"format": "full"}
            )
            response.raise_for_status()
            return response.json()
    
    def _parse_email(self, email_data: Dict) -> Dict:
        """
        Parse Gmail API response into structured format.
        
        Args:
            email_data: Raw email data from Gmail API
            
        Returns:
            Parsed email dictionary
        """
        headers = {h["name"]: h["value"] for h in email_data.get("payload", {}).get("headers", [])}
        
        # Extract email addresses
        from_email = headers.get("From", "")
        to_emails = headers.get("To", "").split(",")
        cc_emails = headers.get("Cc", "").split(",") if headers.get("Cc") else []
        
        # Parse body
        body_text = ""
        body_html = ""
        
        payload = email_data.get("payload", {})
        if "parts" in payload:
            # Multipart message
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                body_data = part.get("body", {}).get("data", "")
                if body_data:
                    import base64
                    decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                    if mime_type == "text/plain":
                        body_text = decoded
                    elif mime_type == "text/html":
                        body_html = decoded
        else:
            # Simple message
            mime_type = payload.get("mimeType", "")
            body_data = payload.get("body", {}).get("data", "")
            if body_data:
                import base64
                decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                if mime_type == "text/plain":
                    body_text = decoded
                elif mime_type == "text/html":
                    body_html = decoded
        
        # Parse date
        date_str = headers.get("Date", "")
        received_at = None
        if date_str:
            try:
                received_at = parsedate_to_datetime(date_str)
            except:
                pass
        
        return {
            "gmail_id": email_data["id"],
            "thread_id": email_data.get("threadId"),
            "subject": headers.get("Subject", ""),
            "from_email": from_email,
            "to_emails": [e.strip() for e in to_emails if e.strip()],
            "cc_emails": [e.strip() for e in cc_emails if e.strip()],
            "body_text": body_text,
            "body_html": body_html,
            "received_at": received_at.isoformat() if received_at else None
        }
    
    async def send_email(self, to: str, subject: str, body: str, cc: Optional[List[str]] = None) -> Dict:
        """
        Send an email via Gmail API.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            cc: Optional list of CC email addresses
            
        Returns:
            Sent message data
        """
        import base64
        from email.mime.text import MIMEText
        
        # Create email message
        message = MIMEText(body)
        message["To"] = to
        message["Subject"] = subject
        if cc:
            message["Cc"] = ", ".join(cc)
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/gmail/v1/users/me/messages/send",
                headers=self.headers,
                json={"raw": raw_message}
            )
            response.raise_for_status()
            return response.json()
    
    async def list_calendar_events(self, time_min: Optional[str] = None, time_max: Optional[str] = None) -> List[Dict]:
        """
        List calendar events.
        
        Args:
            time_min: Minimum time (ISO format)
            time_max: Maximum time (ISO format)
            
        Returns:
            List of calendar events
        """
        async with httpx.AsyncClient() as client:
            params = {}
            if time_min:
                params["timeMin"] = time_min
            if time_max:
                params["timeMax"] = time_max
            
            response = await client.get(
                f"{self.base_url}/calendar/v3/calendars/primary/events",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
    
    async def create_calendar_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        attendees: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> Dict:
        """
        Create a calendar event.
        
        Args:
            summary: Event title
            start_time: Start time (ISO format)
            end_time: End time (ISO format)
            attendees: Optional list of attendee email addresses
            description: Optional event description
            
        Returns:
            Created event data
        """
        event_data = {
            "summary": summary,
            "start": {"dateTime": start_time, "timeZone": "UTC"},
            "end": {"dateTime": end_time, "timeZone": "UTC"}
        }
        
        if description:
            event_data["description"] = description
        
        if attendees:
            event_data["attendees"] = [{"email": email} for email in attendees]
            event_data["sendUpdates"] = "all"  # Send email invitations
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calendar/v3/calendars/primary/events",
                headers=self.headers,
                json=event_data
            )
            response.raise_for_status()
            return response.json()
    
    async def get_available_times(
        self,
        time_min: str,
        time_max: str,
        duration_minutes: int = 60
    ) -> List[Dict]:
        """
        Get available time slots in calendar.
        
        Args:
            time_min: Minimum time (ISO format)
            time_max: Maximum time (ISO format)
            duration_minutes: Duration of desired slot in minutes
            
        Returns:
            List of available time slots
        """
        # Get busy times
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/calendar/v3/freeBusy",
                headers=self.headers,
                json={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "items": [{"id": "primary"}]
                }
            )
            response.raise_for_status()
            data = response.json()
            
        # Calculate available slots (simplified - in production, use proper algorithm)
        busy_periods = data.get("calendars", {}).get("primary", {}).get("busy", [])
        # This is a simplified version - full implementation would calculate gaps
        return []

