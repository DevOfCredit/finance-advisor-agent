"""
HubSpot service for interacting with HubSpot CRM API.
"""

import httpx
from typing import List, Dict, Optional


class HubSpotService:
    """
    Service for interacting with HubSpot CRM API.
    """
    
    def __init__(self, access_token: str):
        """
        Initialize HubSpot service with access token.
        
        Args:
            access_token: OAuth access token for HubSpot API
        """
        self.access_token = access_token
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    async def get_account_info(self) -> Dict:
        """Get HubSpot account information."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/integrations/v1/me",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def search_contacts(self, query: Optional[str] = None, email: Optional[str] = None) -> List[Dict]:
        """
        Search for contacts in HubSpot.
        
        Args:
            query: Search query string
            email: Search by email address
            
        Returns:
            List of matching contacts
        """
        async with httpx.AsyncClient() as client:
            if email:
                # Search by email
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/contacts/search",
                    headers=self.headers,
                    json={
                        "filterGroups": [{
                            "filters": [{
                                "propertyName": "email",
                                "operator": "EQ",
                                "value": email
                            }]
                        }],
                        "properties": ["email", "firstname", "lastname", "phone", "company"]
                    }
                )
            else:
                # General search
                response = await client.post(
                    f"{self.base_url}/crm/v3/objects/contacts/search",
                    headers=self.headers,
                    json={
                        "query": query or "",
                        "properties": ["email", "firstname", "lastname", "phone", "company"]
                    }
                )
            
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
    
    async def get_contact(self, contact_id: str) -> Dict:
        """
        Get a specific contact by ID.
        
        Args:
            contact_id: HubSpot contact ID
            
        Returns:
            Contact data
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/crm/v3/objects/contacts/{contact_id}",
                headers=self.headers,
                params={
                    "properties": "email,firstname,lastname,phone,company"
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def create_contact(
        self,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None
    ) -> Dict:
        """
        Create a new contact in HubSpot.
        
        Args:
            email: Contact email (required)
            first_name: First name
            last_name: Last name
            phone: Phone number
            company: Company name
            
        Returns:
            Created contact data
        """
        properties = {"email": email}
        if first_name:
            properties["firstname"] = first_name
        if last_name:
            properties["lastname"] = last_name
        if phone:
            properties["phone"] = phone
        if company:
            properties["company"] = company
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/crm/v3/objects/contacts",
                headers=self.headers,
                json={"properties": properties}
            )
            response.raise_for_status()
            return response.json()
    
    async def create_note(self, contact_id: str, note: str) -> Dict:
        """
        Create a note for a contact.
        
        Args:
            contact_id: HubSpot contact ID
            note: Note content
            
        Returns:
            Created note data
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/crm/v3/objects/notes",
                headers=self.headers,
                json={
                    "properties": {
                        "hs_note_body": note
                    },
                    "associations": [{
                        "to": {"id": contact_id},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}]
                    }]
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def get_contact_notes(self, contact_id: str) -> List[Dict]:
        """
        Get all notes for a contact.
        
        Args:
            contact_id: HubSpot contact ID
            
        Returns:
            List of notes
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/crm/v3/objects/contacts/{contact_id}/associations/notes",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            # Get note details
            note_ids = [result["id"] for result in data.get("results", [])]
            notes = []
            for note_id in note_ids:
                note_response = await client.get(
                    f"{self.base_url}/crm/v3/objects/notes/{note_id}",
                    headers=self.headers,
                    params={"properties": "hs_note_body,hs_createdate"}
                )
                if note_response.status_code == 200:
                    notes.append(note_response.json())
            
            return notes
    
    async def list_all_contacts(self, limit: int = 100, after: Optional[str] = None) -> Dict:
        """
        List all contacts with pagination.
        
        Args:
            limit: Number of contacts to retrieve
            after: Pagination token
            
        Returns:
            Dictionary with contacts list and pagination info
        """
        async with httpx.AsyncClient() as client:
            params = {
                "limit": limit,
                "properties": "email,firstname,lastname,phone,company"
            }
            if after:
                params["after"] = after
            
            response = await client.get(
                f"{self.base_url}/crm/v3/objects/contacts",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()

